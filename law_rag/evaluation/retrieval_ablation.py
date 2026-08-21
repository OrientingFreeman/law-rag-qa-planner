from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable
from uuid import uuid4

from law_rag import __version__
from law_rag.evaluation.experiments import ExperimentStore
from law_rag.evaluation.retrieval_benchmark import RetrievalBenchmarkConfig, RetrievalBenchmarkRunner
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL
from law_rag.retrieval.reranker import DEFAULT_RERANKER_MODEL


ABLATION_METHODS = (
    "bm25",
    "semantic_lite",
    "hybrid",
    "pretrained_embedding",
    "pretrained_embedding_reranker",
    "fine_tuned_embedding",
    "fine_tuned_embedding_reranker",
)

BASELINE_METHOD = {
    "bm25": None,
    "semantic_lite": "bm25",
    "hybrid": "bm25",
    "pretrained_embedding": "hybrid",
    "pretrained_embedding_reranker": "pretrained_embedding",
    "fine_tuned_embedding": "pretrained_embedding",
    "fine_tuned_embedding_reranker": "fine_tuned_embedding",
}

QUALITY_METRICS = ("top1_accuracy", "hit_at_k", "mean_recall_at_k", "mrr", "ndcg_at_k")
LATENCY_METRICS = (
    "average_latency_ms", "average_retrieval_latency_ms", "average_reranking_latency_ms",
)


@dataclass(frozen=True, slots=True)
class RetrievalAblationConfig:
    dataset_path: str = "evaluation/datasets/official_core_cases.json"
    corpus_path: str = "data/legal_corpus.json"
    domains_path: str = "domains"
    methods: tuple[str, ...] = ABLATION_METHODS
    top_k: int = 5
    retrieval_top_n: int = 20
    seed: int = 42
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    fine_tuned_embedding_model: str | None = None
    reranker_model: str = DEFAULT_RERANKER_MODEL
    query_rewrite: bool = True
    regression_tolerance: float = 0.0

    def validate(self) -> None:
        unknown = set(self.methods) - set(ABLATION_METHODS)
        if unknown:
            raise ValueError(f"unsupported ablation methods: {', '.join(sorted(unknown))}")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("ablation methods must be unique")
        if self.top_k < 1 or self.retrieval_top_n < self.top_k:
            raise ValueError("retrieval_top_n must be greater than or equal to top_k")
        if self.regression_tolerance < 0:
            raise ValueError("regression_tolerance must not be negative")


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(rows),
        "top1_accuracy": round(mean(bool(row["top1_hit"]) for row in rows), 6),
        "hit_at_k": round(mean(bool(row["hit_at_k"]) for row in rows), 6),
        "mean_recall_at_k": round(mean(float(row["recall_at_k"]) for row in rows), 6),
        "mrr": round(mean(float(row["reciprocal_rank"]) for row in rows), 6),
        "ndcg_at_k": round(mean(float(row["ndcg_at_k"]) for row in rows), 6),
        "average_latency_ms": round(mean(float(row["latency_ms"]) for row in rows), 3),
        "average_retrieval_latency_ms": round(mean(float(row["retrieval_latency_ms"]) for row in rows), 3),
        "average_reranking_latency_ms": round(mean(float(row["reranking_latency_ms"]) for row in rows), 3),
    }


def _domain_metrics(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    domains = sorted({str(row.get("domain", "all")) for row in cases})
    return {domain: _aggregate([row for row in cases if str(row.get("domain", "all")) == domain]) for domain in domains}


def _deltas(baseline: dict[str, Any], treatment: dict[str, Any]) -> dict[str, float]:
    return {
        key: round(float(treatment[key]) - float(baseline[key]), 6)
        for key in QUALITY_METRICS + LATENCY_METRICS
    }


def _case_changes(baseline: list[dict[str, Any]], treatment: list[dict[str, Any]]) -> dict[str, int]:
    before = {str(row["case_id"]): row for row in baseline}
    after = {str(row["case_id"]): row for row in treatment}
    if set(before) != set(after):
        raise ValueError("ablation methods must contain identical case IDs")
    counts = {"improved": 0, "regressed": 0, "unchanged": 0}
    for case_id in before:
        left = (bool(before[case_id]["hit_at_k"]), bool(before[case_id]["top1_hit"]), float(before[case_id]["reciprocal_rank"]))
        right = (bool(after[case_id]["hit_at_k"]), bool(after[case_id]["top1_hit"]), float(after[case_id]["reciprocal_rank"]))
        counts["improved" if right > left else "regressed" if right < left else "unchanged"] += 1
    return counts


def compare_ablation_methods(
    baseline: dict[str, Any], treatment: dict[str, Any], *, tolerance: float = 0.0
) -> dict[str, Any]:
    overall = _deltas(baseline["metrics"], treatment["metrics"])
    common_domains = sorted(set(baseline["metrics_by_domain"]) & set(treatment["metrics_by_domain"]))
    quality_regressions = [key for key in QUALITY_METRICS if overall[key] < -tolerance]
    return {
        "baseline_method": baseline["method"],
        "treatment_method": treatment["method"],
        "metric_deltas": overall,
        "metrics_by_domain": {
            domain: _deltas(baseline["metrics_by_domain"][domain], treatment["metrics_by_domain"][domain])
            for domain in common_domains
        },
        "case_changes": _case_changes(baseline["cases"], treatment["cases"]),
        "quality_regressions": quality_regressions,
        "regression_status": "regressed" if quality_regressions else "passed",
    }


class RetrievalAblationRunner:
    def __init__(
        self,
        config: RetrievalAblationConfig,
        *,
        runner_factory: Callable[[RetrievalBenchmarkConfig], Any] | None = None,
        availability_overrides: dict[str, tuple[bool, str | None]] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.runner_factory = runner_factory or RetrievalBenchmarkRunner
        self.availability_overrides = availability_overrides or {}

    def _availability(self, method: str) -> tuple[bool, str | None]:
        if method in self.availability_overrides:
            return self.availability_overrides[method]
        requires_ml = "embedding" in method or method.endswith("_reranker")
        if requires_ml and importlib.util.find_spec("sentence_transformers") is None:
            return False, "optional dependency '.[ml]' is not installed"
        if method.startswith("fine_tuned_embedding"):
            checkpoint = self.config.fine_tuned_embedding_model
            if not checkpoint:
                return False, "fine-tuned checkpoint is not configured"
            if not Path(checkpoint).exists():
                return False, "fine-tuned checkpoint does not exist"
        return True, None

    def _benchmark_config(self, method: str) -> RetrievalBenchmarkConfig:
        return RetrievalBenchmarkConfig(
            dataset_path=self.config.dataset_path,
            corpus_path=self.config.corpus_path,
            domains_path=self.config.domains_path,
            methods=(method,),
            top_k=self.config.top_k,
            seed=self.config.seed,
            embedding_model=self.config.embedding_model,
            fine_tuned_embedding_model=self.config.fine_tuned_embedding_model,
            reranker_model=self.config.reranker_model,
            retrieval_top_n=self.config.retrieval_top_n,
            query_rewrite=self.config.query_rewrite,
        )

    @staticmethod
    def _assert_same_conditions(reference: dict[str, Any], candidate: dict[str, Any]) -> None:
        if reference["dataset"].get("content_sha256") != candidate["dataset"].get("content_sha256"):
            raise ValueError("ablation methods must use the same dataset content hash")
        if reference["corpus"].get("content_sha256") != candidate["corpus"].get("content_sha256"):
            raise ValueError("ablation methods must use the same corpus content hash")
        if reference["selection"] != candidate["selection"]:
            raise ValueError("ablation methods must use the same case selection")

    def run(self, *, execute: bool = False) -> dict[str, Any]:
        method_records: list[dict[str, Any]] = []
        benchmark_reports: list[dict[str, Any]] = []
        for method in self.config.methods:
            available, reason = self._availability(method)
            record: dict[str, Any] = {
                "method": method,
                "baseline_method": BASELINE_METHOD[method],
                "status": "not_run" if available else "unavailable",
                "availability_reason": reason,
            }
            if execute and available:
                try:
                    benchmark = self.runner_factory(self._benchmark_config(method)).run()
                    if benchmark_reports:
                        self._assert_same_conditions(benchmark_reports[0], benchmark)
                    result = benchmark["results"][0]
                    result["metrics_by_domain"] = _domain_metrics(result["cases"])
                    record.update({"status": "completed", "result": result})
                    benchmark_reports.append(benchmark)
                except Exception as exc:  # isolate one treatment without inventing metrics
                    record.update({"status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})
            method_records.append(record)

        completed = {row["method"]: row["result"] for row in method_records if row["status"] == "completed"}
        comparisons = []
        for method, result in completed.items():
            baseline_method = BASELINE_METHOD[method]
            if baseline_method and baseline_method in completed:
                comparisons.append(compare_ablation_methods(
                    completed[baseline_method], result, tolerance=self.config.regression_tolerance,
                ))
        reference = benchmark_reports[0] if benchmark_reports else None
        status_counts = {status: sum(row["status"] == status for row in method_records) for status in ("completed", "not_run", "unavailable", "failed")}
        experiment_id = f"exp_ablation_{uuid4().hex}"
        return {
            "experiment_id": experiment_id,
            "experiment_kind": "retrieval_ablation",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "dataset": reference["dataset"] if reference else {"path": self.config.dataset_path, "case_count": 0, "status": "not_executed"},
            "corpus": reference["corpus"] if reference else {"path": self.config.corpus_path, "content_sha256": "not_executed", "provision_count": 0},
            "code_version": __version__,
            "config": {"mode": "retrieval_ablation", **asdict(self.config)},
            "model": {"provider": "multiple", "model": "ablation_matrix", "prompt_version": "not_applicable"},
            "environment": reference["environment"] if reference else {},
            "summary": {"status": "completed" if execute and status_counts["failed"] == 0 else "planned" if not execute else "completed_with_failures", "status_counts": status_counts, "comparison_count": len(comparisons)},
            "cases": [],
            "ablation": {"methods": method_records, "comparisons": comparisons},
        }


def save_ablation_report(report: dict[str, Any], directory: str | Path = "evaluation/experiments") -> Path:
    return ExperimentStore(directory).save(report)
