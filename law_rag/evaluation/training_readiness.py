from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from law_rag import __version__
from law_rag.domain.config import DomainRegistry
from law_rag.evaluation.datasets import dataset_snapshot, sha256_file
from law_rag.evaluation.hard_negatives import (
    build_hard_negative_candidates,
    select_review_candidates,
)
from law_rag.evaluation.retrieval_benchmark import is_retrieval_case
from law_rag.evaluation.runner import load_dataset
from law_rag.ingestion.json_source import JsonLegalDocumentSource


def audit_training_readiness(
    *,
    target_domain: str,
    dataset_path: str | Path,
    corpus_path: str | Path,
    domains_path: str | Path,
    benchmark: dict[str, Any] | None = None,
    method: str = "hybrid",
    review_limit: int = 20,
) -> dict[str, Any]:
    if review_limit < 1:
        raise ValueError("review_limit must be at least 1")
    domain = DomainRegistry(domains_path).load_all().get(target_domain)
    if domain is None:
        raise ValueError(f"unknown target domain: {target_domain}")

    corpus = JsonLegalDocumentSource().load(corpus_path)
    domain_provisions = [
        row for row in corpus
        if row.law_name in domain.laws or target_domain in row.domain_tags
    ]
    cases = [case for case in load_dataset(dataset_path) if case.domain == target_domain]
    retrieval_cases = [case for case in cases if is_retrieval_case(case)]
    available_articles = {(row.law_id, row.article_no) for row in domain_provisions}
    missing_gold: list[dict[str, str]] = []
    for case in retrieval_cases:
        if case.uses_article_expectation:
            for article in case.expected_article_nos or []:
                if (str(case.expected_law_id), article) not in available_articles:
                    missing_gold.append({"case_id": case.case_id, "document_id": f"{case.expected_law_id}:{article}"})
        else:
            ids = {row.document_id for row in domain_provisions}
            for document_id in case.expected_document_ids or []:
                if document_id not in ids:
                    missing_gold.append({"case_id": case.case_id, "document_id": document_id})

    candidates: list[dict[str, Any]] = []
    benchmark_cases: list[dict[str, Any]] = []
    benchmark_id = None
    if benchmark is not None:
        benchmark_id = str(benchmark.get("benchmark_id", "unknown"))
        selected_results = [row for row in benchmark.get("results", []) if row.get("method") == method]
        if not selected_results:
            raise ValueError(f"benchmark method not found: {method}")
        benchmark_cases = [
            row for row in selected_results[0].get("cases", [])
            if row.get("domain") == target_domain
        ]
        candidates = build_hard_negative_candidates(
            benchmark,
            corpus_path=corpus_path,
            methods={method},
            candidate_pool_version=f"{target_domain}-readiness",
        )
    domain_candidates = select_review_candidates(candidates, domains={target_domain})
    review_batch = select_review_candidates(
        domain_candidates,
        domains={target_domain},
        limit=review_limit,
        one_per_case=True,
    )
    failures = Counter(
        failure
        for row in benchmark_cases
        for failure in _case_failure_types(row)
    )
    category_counts = Counter(case.category for case in cases)
    difficulty_counts = Counter(case.difficulty for case in cases)
    snapshot = dataset_snapshot(dataset_path, case_count=len(load_dataset(dataset_path)))
    return {
        "report_type": "training_readiness_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": __version__,
        "target_domain": target_domain,
        "dataset": {**snapshot, "path": str(dataset_path)},
        "corpus": {
            "path": str(corpus_path),
            "content_sha256": sha256_file(corpus_path),
            "domain_laws": domain.laws,
            "provision_count": len(domain_provisions),
            "current_provision_count": sum(row.is_current for row in domain_provisions),
            "distinct_article_count": len(available_articles),
        },
        "evaluation": {
            "domain_case_count": len(cases),
            "retrieval_case_count": len(retrieval_cases),
            "category_counts": dict(sorted(category_counts.items())),
            "difficulty_counts": dict(sorted(difficulty_counts.items())),
            "gold_reference_count": sum(
                len(case.expected_article_nos or case.expected_document_ids or [])
                for case in retrieval_cases
            ),
            "missing_gold_references": missing_gold,
        },
        "failure_analysis": {
            "benchmark_id": benchmark_id,
            "method": method if benchmark is not None else None,
            "benchmark_case_count": len(benchmark_cases),
            "failure_type_counts": dict(sorted(failures.items())),
            "candidate_count": len(domain_candidates),
        },
        "manual_review_batch": {
            "requested_limit": review_limit,
            "selected_count": len(review_batch),
            "selection_policy": "failure_priority_then_case_id_one_candidate_per_case",
            "candidates": review_batch,
        },
        "gates": {
            "corpus_available": bool(domain_provisions),
            "minimum_evaluation_cases": len(retrieval_cases) >= 10,
            "all_gold_references_resolved": not missing_gold,
            "failure_candidates_available": bool(domain_candidates) if benchmark is not None else None,
            "manual_review_required": True,
            "automatic_training_allowed": False,
        },
    }


def _case_failure_types(case: dict[str, Any]) -> list[str]:
    expected = set(map(str, case.get("expected", [])))
    retrieved = list(map(str, case.get("retrieved", [])))
    matched = expected.intersection(retrieved)
    failures: list[str] = []
    if not matched:
        failures.append("retrieval_miss")
    elif retrieved and retrieved[0] not in expected:
        failures.append("wrong_top1")
    if expected and expected.issubset(retrieved) and any(value not in expected for value in retrieved):
        failures.append("over_retrieval")
    return failures


def save_readiness_report(report: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
