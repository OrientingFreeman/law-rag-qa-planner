import json
from pathlib import Path

from law_rag.benchmark import format_summary, main
from law_rag.evaluation.failures import FailureCaseLogger, diagnose_failure, failure_payload


def test_failure_logger_writes_structured_jsonl(tmp_path):
    case = {
        "case_id": "missing",
        "question": "질문",
        "domain": "digital_business",
        "expected_document_ids": ["expected:1"],
        "expected_law_id": None,
        "expected_article_nos": [],
        "retrieved_document_ids": ["actual:2"],
        "retrieved_articles": ["law:제2조"],
        "expected_abstain": False,
        "actual_abstain": False,
        "top1_hit": False,
        "hit_at_k": False,
        "recall_at_k": 0.0,
        "reciprocal_rank": 0.0,
        "abstention_correct": True,
        "temporal_valid": True,
        "citation_valid": None,
        "latency_ms": 12.3,
        "passed": False,
    }
    path = tmp_path / "failures.jsonl"
    FailureCaseLogger(path).append(failure_payload(case, dataset="dataset.json"))
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["case_id"] == "missing"
    assert record["expected"]["document_ids"] == ["expected:1"]
    assert record["retrieved"]["document_ids"] == ["actual:2"]
    assert record["reason"] == ["expected_evidence_not_retrieved"]


def test_failure_diagnosis_can_report_multiple_reasons():
    reasons = diagnose_failure({
        "expected_abstain": True,
        "actual_abstain": False,
        "abstention_correct": False,
        "temporal_valid": False,
        "citation_valid": False,
        "hit_at_k": False,
    })
    assert "abstention_mismatch" in reasons
    assert "temporal_filter_failure" in reasons
    assert "citation_validation_failure" in reasons
    assert "unexpected_evidence_retrieved" in reasons


def test_summary_formatter_contains_core_metrics():
    text = format_summary({
        "passed_cases": 2,
        "total_cases": 2,
        "pass_rate": 1.0,
        "top1_accuracy": 1.0,
        "hit_at_k": 1.0,
        "mean_recall_at_k": 0.75,
        "mean_reciprocal_rank": 1.0,
        "citation_accuracy": None,
        "average_latency_ms": 4.2,
    })
    assert "Pass rate" in text
    assert "Recall@K" in text
    assert "Average latency" in text


def test_benchmark_main_writes_report(tmp_path):
    report = tmp_path / "report.json"
    failures = tmp_path / "failures.jsonl"
    exit_code = main([
        "--dataset", "evaluation/datasets/core_cases.json",
        "--data", "tests/fixtures/legal_corpus.json",
        "--output", str(report),
        "--failures", str(failures),
        "--fail-under", "0",
        "--no-log-failures",
    ])
    assert exit_code == 0
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert "summary" in payload
    assert payload["dataset"].endswith("core_cases.json")
