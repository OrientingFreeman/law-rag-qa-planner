import json
from pathlib import Path


def test_verified_summary_is_scoped_and_internally_consistent():
    report = json.loads(Path(
        "evaluation/baselines/v4.16.0_baseline_vs_agent_summary.json"
    ).read_text(encoding="utf-8"))
    assert report["dataset"]["case_count"] == 61
    assert report["comparison"]["improved_cases"] + report["comparison"]["regressed_cases"] + report["comparison"]["unchanged_pass_cases"] + report["comparison"]["unchanged_failure_cases"] == 61
    assert report["agent"]["retry_improvement_rate"] == 0.0
    assert report["limitations"]
