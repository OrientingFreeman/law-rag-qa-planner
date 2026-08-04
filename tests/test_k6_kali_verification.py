from copy import deepcopy
from pathlib import Path
import subprocess

from tools.run_kali_verification import (
    ROOT,
    build_result,
    collect_metrics,
    run_step,
    verify_document_claims,
)


def test_metrics_are_computed_from_current_artifacts():
    metrics = collect_metrics()
    assert metrics["corpus_documents"] == 4833
    assert metrics["knowledge_concepts"] == 41
    assert metrics["kb_evaluation_cases"] == 30
    assert metrics["verified_amendment_cases"] == 1
    assert metrics["temporal_boundary_passed"] == metrics["temporal_boundary_cases"] == 2
    assert metrics["k5_passed_checks"] == metrics["k5_required_checks"] == 9


def test_submission_document_claims_match_current_artifacts():
    assert all(row["passed"] for row in verify_document_claims(collect_metrics()))


def test_stale_submission_number_is_detected(tmp_path: Path):
    metrics = collect_metrics()
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("stale", encoding="utf-8")
    (tmp_path / "docs" / "APPLICATION_PROJECT_SUMMARY_KALI.md").write_text("stale", encoding="utf-8")
    assert any(not row["passed"] for row in verify_document_claims(metrics, tmp_path))


def test_failed_step_makes_final_result_fail():
    metrics = collect_metrics()
    claims = verify_document_claims(metrics)
    steps = [{"name": "example", "status": "fail"}]
    result = build_result(steps, metrics, claims)
    assert result["status"] == "fail"
    assert result["summary"]["failed_steps"] == ["example"]


def test_run_step_records_pytest_count_with_injected_runner():
    def fake_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="..... [100%]\n5 passed in 0.10s\n")

    result = run_step("sample", ["-m", "pytest", "-q"], root=ROOT, runner=fake_runner)
    assert result["status"] == "pass"
    assert result["pytest_passed"] == 5
