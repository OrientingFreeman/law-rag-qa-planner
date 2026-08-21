import json
from pathlib import Path

from law_rag.evaluation.experiments import ExperimentStore
from law_rag.evaluation.retrieval_ablation import (
    RetrievalAblationConfig,
    RetrievalAblationRunner,
    compare_ablation_methods,
)
from tools.run_retrieval_ablation import main


def _case(case_id: str, domain: str, hit: bool, top1: bool, rank: float, latency: float) -> dict:
    return {
        "case_id": case_id, "domain": domain, "top1_hit": top1, "hit_at_k": hit,
        "recall_at_k": 1.0 if hit else 0.0, "reciprocal_rank": rank,
        "ndcg_at_k": rank, "latency_ms": latency,
        "retrieval_latency_ms": latency, "reranking_latency_ms": 0.0,
    }


class FakeBenchmarkRunner:
    def __init__(self, config):
        self.config = config

    def run(self):
        method = self.config.methods[0]
        improved = method == "semantic_lite"
        cases = [
            _case("civil-1", "civil_transactions", True, improved, 1.0 if improved else 0.5, 2.0),
            _case("pipa-1", "digital_business", True, True, 1.0, 3.0),
        ]
        from law_rag.evaluation.retrieval_ablation import _aggregate
        return {
            "dataset": {"content_sha256": "d" * 64, "dataset_version": "2.0.0", "case_count": 2},
            "corpus": {"content_sha256": "c" * 64, "provision_count": 10},
            "selection": {"selected_case_count": 2, "excluded_case_count": 0},
            "environment": {"python": "test"},
            "results": [{"method": method, "metrics": _aggregate(cases), "cases": cases}],
        }


def test_plan_records_unavailable_and_not_run_without_metrics():
    report = RetrievalAblationRunner(
        RetrievalAblationConfig(methods=("bm25", "pretrained_embedding", "fine_tuned_embedding")),
        availability_overrides={
            "bm25": (True, None),
            "pretrained_embedding": (False, "ML dependency missing"),
            "fine_tuned_embedding": (False, "checkpoint missing"),
        },
    ).run(execute=False)
    methods = {row["method"]: row for row in report["ablation"]["methods"]}
    assert methods["bm25"]["status"] == "not_run"
    assert methods["pretrained_embedding"]["status"] == "unavailable"
    assert "result" not in methods["pretrained_embedding"]
    assert report["summary"]["status"] == "planned"


def test_execute_compares_completed_methods_and_slices_by_domain():
    report = RetrievalAblationRunner(
        RetrievalAblationConfig(methods=("bm25", "semantic_lite")),
        runner_factory=FakeBenchmarkRunner,
        availability_overrides={"bm25": (True, None), "semantic_lite": (True, None)},
    ).run(execute=True)
    comparison = report["ablation"]["comparisons"][0]
    semantic = report["ablation"]["methods"][1]["result"]
    assert report["summary"]["status_counts"]["completed"] == 2
    assert comparison["baseline_method"] == "bm25"
    assert comparison["metric_deltas"]["top1_accuracy"] == 0.5
    assert comparison["case_changes"] == {"improved": 1, "regressed": 0, "unchanged": 1}
    assert set(semantic["metrics_by_domain"]) == {"civil_transactions", "digital_business"}


def test_quality_drop_is_regression_but_latency_tradeoff_alone_is_not():
    base_cases = [_case("a", "civil_transactions", True, True, 1.0, 2.0)]
    slow_cases = [_case("a", "civil_transactions", True, True, 1.0, 20.0)]
    bad_cases = [_case("a", "civil_transactions", False, False, 0.0, 1.0)]
    from law_rag.evaluation.retrieval_ablation import _aggregate, _domain_metrics
    base = {"method": "bm25", "metrics": _aggregate(base_cases), "metrics_by_domain": _domain_metrics(base_cases), "cases": base_cases}
    slow = {"method": "semantic_lite", "metrics": _aggregate(slow_cases), "metrics_by_domain": _domain_metrics(slow_cases), "cases": slow_cases}
    bad = {"method": "hybrid", "metrics": _aggregate(bad_cases), "metrics_by_domain": _domain_metrics(bad_cases), "cases": bad_cases}
    assert compare_ablation_methods(base, slow)["regression_status"] == "passed"
    assert compare_ablation_methods(base, bad)["regression_status"] == "regressed"


def test_ablation_report_round_trip_and_cli_plan(tmp_path: Path, capsys):
    exit_code = main([
        "--methods", "bm25", "semantic_lite",
        "--experiment-dir", str(tmp_path),
    ])
    output = json.loads(capsys.readouterr().out)
    reports = ExperimentStore(tmp_path).list_ablation_reports()
    assert exit_code == 0
    assert output["status"] == "planned"
    assert reports[0]["experiment_kind"] == "retrieval_ablation"
    assert reports[0]["ablation"]["methods"][0]["status"] == "not_run"
