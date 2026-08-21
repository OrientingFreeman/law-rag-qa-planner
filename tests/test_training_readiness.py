import json

import pytest

from law_rag.evaluation.training_readiness import audit_training_readiness
from tools.audit_training_readiness import main


def _benchmark() -> dict:
    return {
        "benchmark_id": "benchmark-civil",
        "dataset": {"dataset_id": "fixture", "dataset_version": "1"},
        "corpus": {"content_sha256": "x"},
        "results": [{
            "method": "hybrid",
            "cases": [{
                "case_id": "civil-case", "question": "채무불이행 책임은?",
                "domain": "civil_transactions", "category": "similar_provision_disambiguation",
                "expected": ["001706:제390조"],
                "retrieved": ["001706:제750조", "001706:제390조"],
            }],
        }],
    }


def test_readiness_audit_reports_corpus_gold_and_review_batch():
    report = audit_training_readiness(
        target_domain="civil_transactions",
        dataset_path="evaluation/datasets/official_core_cases.json",
        corpus_path="data/legal_corpus.json",
        domains_path="domains",
        benchmark=_benchmark(),
        review_limit=20,
    )
    assert report["evaluation"]["retrieval_case_count"] >= 10
    assert report["corpus"]["provision_count"] > 0
    assert report["evaluation"]["missing_gold_references"] == []
    assert report["failure_analysis"]["candidate_count"] == 1
    assert report["manual_review_batch"]["selected_count"] == 1
    assert report["gates"]["manual_review_required"] is True
    assert report["gates"]["automatic_training_allowed"] is False


def test_readiness_audit_rejects_unknown_domain():
    with pytest.raises(ValueError, match="unknown target domain"):
        audit_training_readiness(
            target_domain="missing", dataset_path="evaluation/datasets/official_core_cases.json",
            corpus_path="data/legal_corpus.json", domains_path="domains",
        )


def test_readiness_cli_writes_report_without_benchmark(tmp_path, capsys):
    output = tmp_path / "readiness.json"
    assert main(["--output", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary["target_domain"] == "civil_transactions"
    assert report["failure_analysis"]["candidate_count"] == 0
    assert report["gates"]["failure_candidates_available"] is None
