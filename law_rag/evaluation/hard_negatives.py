from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from law_rag.evaluation.datasets import sha256_file
from law_rag.evaluation.reviews import JsonReviewStore
from law_rag.ingestion.json_source import JsonLegalDocumentSource


CANDIDATE_SCHEMA_VERSION = "1.0.0"


def _stable_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "hn_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _document_indexes(corpus_path: str | Path) -> tuple[dict[str, list[Any]], dict[str, list[Any]]]:
    provisions = JsonLegalDocumentSource().load(corpus_path)
    by_document: dict[str, list[Any]] = {}
    by_article: dict[str, list[Any]] = {}
    for row in provisions:
        by_document[row.document_id] = [row]
        by_article.setdefault(f"{row.law_id}:{row.article_no}", []).append(row)
    return by_document, by_article


def _resolve_document(
    identifier: str,
    by_document: dict[str, list[Any]],
    by_article: dict[str, list[Any]],
) -> dict[str, Any] | None:
    rows = by_article.get(identifier) or by_document.get(identifier)
    if not rows:
        return None
    substantive = [
        row for row in rows
        if row.paragraph_no or row.item_no or row.subitem_no or row.article_title
    ]
    if substantive:
        rows = substantive
    first = rows[0]
    texts = list(dict.fromkeys(row.text.strip() for row in rows if row.text.strip()))
    return {
        "document_id": identifier,
        "law_id": first.law_id,
        "law_name": first.law_name,
        "article_no": first.article_no,
        "text": "\n".join(texts),
        "source_document_ids": [row.document_id for row in rows],
    }


def _failure_types(case: dict[str, Any]) -> list[str]:
    expected = set(map(str, case.get("expected", [])))
    retrieved = list(map(str, case.get("retrieved", [])))
    matched = expected.intersection(retrieved)
    failures: list[str] = []
    if not matched:
        failures.append("retrieval_miss")
    elif retrieved and retrieved[0] not in expected:
        failures.append("wrong_top1")
    if expected and expected.issubset(retrieved) and any(row not in expected for row in retrieved):
        failures.append("over_retrieval")
    return failures


def build_hard_negative_candidates(
    benchmark: dict[str, Any],
    *,
    corpus_path: str | Path,
    methods: set[str] | None = None,
    candidate_pool_version: str = "0.1.0",
    max_negatives: int = 3,
) -> list[dict[str, Any]]:
    if max_negatives < 1:
        raise ValueError("max_negatives must be at least 1")
    by_document, by_article = _document_indexes(corpus_path)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in benchmark.get("results", []):
        method = str(result.get("method", "unknown"))
        if methods is not None and method not in methods:
            continue
        for case in result.get("cases", []):
            failures = _failure_types(case)
            if not failures:
                continue
            positive_ids = list(dict.fromkeys(map(str, case.get("expected", []))))
            negative_ids = [
                row for row in dict.fromkeys(map(str, case.get("retrieved", [])))
                if row not in set(positive_ids)
            ][:max_negatives]
            if not positive_ids or not negative_ids or set(positive_ids).intersection(negative_ids):
                continue
            positives = [
                resolved for identifier in positive_ids
                if (resolved := _resolve_document(identifier, by_document, by_article)) is not None
            ]
            resolved_negatives = [
                resolved for identifier in negative_ids
                if (resolved := _resolve_document(identifier, by_document, by_article)) is not None
            ]
            if not positives or not resolved_negatives:
                continue
            for negative in resolved_negatives:
                identity = {
                    "case_id": str(case.get("case_id", "")),
                    "method": method,
                    "positive_ids": [row["document_id"] for row in positives],
                    "negative_id": negative["document_id"],
                }
                candidate_id = _stable_id(identity)
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                candidates.append({
                    "candidate_id": candidate_id,
                    "schema_version": CANDIDATE_SCHEMA_VERSION,
                    "candidate_pool_version": candidate_pool_version,
                    "query": str(case.get("question", "")),
                    "domain": str(case.get("domain", "all")),
                    "category": str(case.get("category", "")),
                    "positive_documents": positives,
                    "negative_documents": [negative],
                    "hard_negative_documents": [negative],
                    "source": {
                        "benchmark_id": str(benchmark.get("benchmark_id", "unknown")),
                        "method": method,
                        "case_id": str(case.get("case_id", "")),
                        "dataset_id": str(benchmark.get("dataset", {}).get("dataset_id", "unknown")),
                        "dataset_version": str(benchmark.get("dataset", {}).get("dataset_version", "unknown")),
                        "ground_truth_version": str(benchmark.get("dataset", {}).get("ground_truth_version", "unknown")),
                        "corpus_sha256": str(benchmark.get("corpus", {}).get("content_sha256", "unknown")),
                    },
                    "failure_types": failures,
                    "review_status": "review_required",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    return candidates


def select_review_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    domains: set[str] | None = None,
    limit: int | None = None,
    one_per_case: bool = False,
) -> list[dict[str, Any]]:
    """Deterministically select a human-review batch without changing candidates."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    priority = {"wrong_top1": 0, "retrieval_miss": 1, "over_retrieval": 2}
    selected = [
        row for row in candidates
        if domains is None or str(row.get("domain", "all")) in domains
    ]
    selected.sort(key=lambda row: (
        min((priority.get(value, 99) for value in row.get("failure_types", [])), default=99),
        str(row.get("source", {}).get("case_id", "")),
        str(row.get("candidate_id", "")),
    ))
    if one_per_case:
        deduplicated: list[dict[str, Any]] = []
        seen_cases: set[str] = set()
        for row in selected:
            case_id = str(row.get("source", {}).get("case_id", ""))
            if case_id in seen_cases:
                continue
            seen_cases.add(case_id)
            deduplicated.append(row)
        selected = deduplicated
    return selected[:limit] if limit is not None else selected


class JsonlCandidateStore:
    """Immutable candidate records; review decisions live in JsonReviewStore."""

    def __init__(self, path: str | Path = "evaluation/training/hard_negative_candidates.jsonl") -> None:
        self.path = Path(path)
        self._lock = RLock()

    def list(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return next((row for row in self.list() if row.get("candidate_id") == candidate_id), None)

    def append_unique(self, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
        with self._lock:
            existing = {str(row.get("candidate_id")) for row in self.list()}
            added = skipped = 0
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                for row in rows:
                    candidate_id = str(row["candidate_id"])
                    if candidate_id in existing:
                        skipped += 1
                        continue
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    existing.add(candidate_id)
                    added += 1
            return {"added": added, "skipped_duplicates": skipped, "total": len(existing)}


def export_approved_training_dataset(
    candidate_store: JsonlCandidateStore,
    review_store: JsonReviewStore,
    *,
    output_path: str | Path,
    dataset_version: str,
    domains: set[str] | None = None,
    candidate_pool_versions: set[str] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    if not dataset_version.strip():
        raise ValueError("dataset_version is required")
    latest = review_store.latest(target_type="training_candidate")
    rows: list[dict[str, Any]] = []
    matched_candidate_count = 0
    for candidate in candidate_store.list():
        if domains is not None and str(candidate.get("domain", "all")) not in domains:
            continue
        if (
            candidate_pool_versions is not None
            and str(candidate.get("candidate_pool_version", "unknown")) not in candidate_pool_versions
        ):
            continue
        matched_candidate_count += 1
        review = latest.get(str(candidate["candidate_id"]))
        if not review or review.get("review_status") != "approved":
            continue
        positive_ids = {str(row["document_id"]) for row in candidate["positive_documents"]}
        negative_ids = {str(row["document_id"]) for row in candidate["hard_negative_documents"]}
        if not positive_ids or not negative_ids or positive_ids.intersection(negative_ids):
            continue
        rows.append({
            "candidate_id": candidate["candidate_id"],
            "query": candidate["query"],
            "domain": candidate.get("domain", "all"),
            "category": candidate.get("category", ""),
            "candidate_pool_version": candidate.get("candidate_pool_version", "unknown"),
            "positive_documents": candidate["positive_documents"],
            "hard_negative_documents": candidate["hard_negative_documents"],
            "source": candidate["source"],
            "failure_types": candidate["failure_types"],
            "review": {
                "review_id": review["review_id"],
                "reviewer_id": review["reviewer_id"],
                "reviewed_at": review["reviewed_at"],
                "review_status": review["review_status"],
            },
            "dataset_version": dataset_version,
        })
    if not rows:
        raise ValueError("approved training candidates not found")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset_id": "legal_retrieval_hard_negatives",
        "dataset_version": dataset_version,
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "status": "released",
        "record_count": len(rows),
        "content_sha256": sha256_file(output),
        "review_policy": "single_reviewer_approval_required",
        "released_at": datetime.now(timezone.utc).isoformat(),
        "source_candidate_store": str(candidate_store.path),
        "selection": {
            "domains": sorted(domains) if domains is not None else [],
            "candidate_pool_versions": (
                sorted(candidate_pool_versions) if candidate_pool_versions is not None else []
            ),
            "matched_candidate_count": matched_candidate_count,
            "approved_record_count": len(rows),
        },
        "domains": sorted({str(row["domain"]) for row in rows}),
        "candidate_pool_versions": sorted({str(row["candidate_pool_version"]) for row in rows}),
        "source_dataset_versions": sorted({
            str(row.get("source", {}).get("dataset_version", "unknown")) for row in rows
        }),
        "source_corpus_sha256": sorted({
            str(row.get("source", {}).get("corpus_sha256", "unknown")) for row in rows
        }),
    }
    manifest_path = output.with_name(f"{output.stem}.manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return output, manifest_path, manifest
