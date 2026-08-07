from __future__ import annotations

from typing import Any


def compare_experiments(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("dataset") != candidate.get("dataset"):
        raise ValueError("experiments must use the same dataset and case count")
    base_cases = {row["case_id"]: row for row in baseline["cases"]}
    candidate_cases = {row["case_id"]: row for row in candidate["cases"]}
    if set(base_cases) != set(candidate_cases):
        raise ValueError("experiments must contain identical case IDs")
    groups = {"improved": [], "regressed": [], "unchanged_pass": [], "unchanged_failure": []}
    for case_id in sorted(base_cases):
        before = bool(base_cases[case_id]["passed"])
        after = bool(candidate_cases[case_id]["passed"])
        key = "improved" if not before and after else "regressed" if before and not after else "unchanged_pass" if before else "unchanged_failure"
        groups[key].append({
            "case_id": case_id,
            "baseline_failures": base_cases[case_id]["failure_types"],
            "candidate_failures": candidate_cases[case_id]["failure_types"],
            "candidate_run_id": candidate_cases[case_id].get("run_id"),
        })

    def delta(path: tuple[str, ...]) -> float | None:
        left: Any = baseline["summary"]
        right: Any = candidate["summary"]
        for key in path:
            left, right = left.get(key), right.get(key)
            if left is None or right is None:
                return None
        return round(float(right) - float(left), 4)

    all_failure_types = set(baseline["summary"]["failure_type_counts"]) | set(candidate["summary"]["failure_type_counts"])
    return {
        "baseline_experiment_id": baseline["experiment_id"],
        "candidate_experiment_id": candidate["experiment_id"],
        "dataset": baseline["dataset"],
        "metric_deltas": {
            "overall_pass_rate": delta(("overall_pass_rate",)),
            "top1_accuracy": delta(("retrieval", "top1_accuracy")),
            "hit_at_k": delta(("retrieval", "hit_at_k")),
            "citation_accuracy": delta(("answer", "citation_accuracy")),
            "outcome_accuracy": delta(("safety", "outcome_accuracy")),
            "false_abstention_rate": delta(("safety", "false_abstention_rate")),
            "average_latency_ms": delta(("average_latency_ms",)),
            "average_retry_count": delta(("safety", "average_retry_count")),
            "retry_improvement_rate": delta(("safety", "retry_improvement_rate")),
        },
        "failure_type_deltas": {
            tag: candidate["summary"]["failure_type_counts"].get(tag, 0) - baseline["summary"]["failure_type_counts"].get(tag, 0)
            for tag in sorted(all_failure_types)
        },
        "case_groups": groups,
        "counts": {key: len(value) for key, value in groups.items()},
    }
