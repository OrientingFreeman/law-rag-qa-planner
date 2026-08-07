from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from law_rag import __version__
from law_rag.evaluation.runner import EvaluationCase, load_dataset
from law_rag.service import LawRagService
from law_rag.workflow import AgentWorkflowRunner, WorkflowConfig


Mode = Literal["baseline", "agent"]


@dataclass(slots=True)
class ExperimentConfig:
    mode: Mode
    dataset_path: str = "evaluation/datasets/official_core_cases.json"
    dataset_version: str = "2.0"
    search_strategy: str = "hybrid"
    query_rewrite: bool = True
    reranking: bool = True
    abstention_policy: bool = True
    max_retries: int = 1
    retry_top_k_increment: int = 3


def _article_key(item: dict[str, Any]) -> str:
    return f"{item.get('law_id', '')}:{item.get('article_no', '')}"


def _expected_outcome(case: EvaluationCase) -> str:
    if case.expected_outcome:
        return case.expected_outcome
    return "abstain" if case.expected_abstain else "answer"


class ExperimentRunner:
    def __init__(self, service: LawRagService) -> None:
        self.service = service

    def _run_case(self, case: EvaluationCase, config: ExperimentConfig) -> dict[str, Any]:
        started = perf_counter()
        trace: list[dict[str, Any]] = []
        run_id = None
        if config.mode == "agent":
            run = AgentWorkflowRunner(self.service).run(
                case.question,
                domain_id=case.domain,
                top_k=case.top_k,
                as_of_date=case.as_of_date,
                config=WorkflowConfig(
                    search_strategy=config.search_strategy,
                    query_rewrite=config.query_rewrite,
                    reranking=config.reranking,
                    max_retries=config.max_retries,
                    retry_top_k_increment=config.retry_top_k_increment,
                    abstention_policy=config.abstention_policy,
                ),
            )
            response = run.response
            actual_outcome = {
                "answered": "answer",
                "abstained": "abstain",
                "needs_clarification": "request_more_facts",
                "failed": "failed",
            }.get(str(run.outcome), "failed")
            trace = [step.to_dict() for step in run.execution_trace]
            run_id = run.run_id
            retry_count = run.retry_count
            stop_reason = run.stop_reason
            retry_step = next((step for step in trace if step["step_id"] == "retry_control"), {})
            retry_improved = bool((retry_step.get("output_summary") or {}).get("quality_improved")) if retry_count else None
        else:
            response = self.service.answer(
                case.question,
                domain_id=None if case.domain == "all" else case.domain,
                top_k=case.top_k,
                as_of_date=case.as_of_date,
                search_strategy=config.search_strategy,
                query_rewrite=config.query_rewrite,
                reranking=config.reranking,
            )
            actual_outcome = "abstain" if response.get("abstain") else "answer"
            retry_count = 0
            retry_improved = None
            stop_reason = "insufficient_evidence" if response.get("abstain") else None
        latency_ms = round((perf_counter() - started) * 1000, 3)
        results = list(response.get("results", []))
        actual_articles = [_article_key(row) for row in results]
        expected = {
            f"{case.expected_law_id}:{article}" for article in (case.expected_article_nos or [])
        } if case.expected_law_id else set(case.expected_document_ids or [])
        actual = actual_articles if case.expected_law_id else [str(row.get("document_id")) for row in results]
        first_rank = next((index for index, value in enumerate(actual, 1) if value in expected), None)
        matched = expected.intersection(actual)
        citation = response.get("citation_validation") or {}
        grounding = response.get("grounding_validation") or {}
        expected_outcome = _expected_outcome(case)
        outcome_correct = actual_outcome == expected_outcome
        retrieval_pass = bool(matched) if expected else actual_outcome in {"abstain", "request_more_facts"}
        citation_valid = citation.get("valid") if isinstance(citation, dict) else None
        grounding_coverage = float(grounding.get("coverage", 0.0) or 0.0) if isinstance(grounding, dict) else None
        answer_pass = (
            actual_outcome != "answer"
            or ((citation_valid is not False) and (grounding_coverage is None or grounding_coverage >= 0.75))
        )
        safety_pass = outcome_correct and retry_count <= config.max_retries and bool(stop_reason or actual_outcome == "answer")
        failure_types: list[str] = []
        if expected and not matched:
            failure_types.append("retrieval_miss")
        elif expected and actual and actual[0] not in expected:
            failure_types.append("wrong_top1")
        if expected and matched and len(actual) > len(expected):
            failure_types.append("over_retrieval")
        if not outcome_correct:
            failure_types.append("incorrect_outcome")
        if citation_valid is False:
            failure_types.append("unsupported_citation")
        if retry_count > config.max_retries:
            failure_types.append("retry_limit_exceeded")
        return {
            "case_id": case.case_id,
            "question": case.question,
            "category": case.category,
            "difficulty": case.difficulty,
            "expected_outcome": expected_outcome,
            "actual_outcome": actual_outcome,
            "expected_articles": sorted(expected),
            "retrieved_articles": actual_articles,
            "top1_hit": bool(expected and actual and actual[0] in expected),
            "hit_at_k": bool(matched),
            "recall_at_k": round(len(matched) / len(expected), 4) if expected else None,
            "reciprocal_rank": round(1 / first_rank, 4) if first_rank else 0.0,
            "retrieval_pass": retrieval_pass,
            "citation_valid": citation_valid,
            "grounding_coverage": grounding_coverage,
            "answer_pass": answer_pass,
            "outcome_correct": outcome_correct,
            "safety_pass": safety_pass,
            "retry_count": retry_count,
            "retry_improved": retry_improved,
            "stop_reason": stop_reason,
            "failure_reason_complete": bool(stop_reason) if actual_outcome != "answer" else True,
            "failure_types": failure_types,
            "latency_ms": latency_ms,
            "run_id": run_id,
            "execution_trace": trace,
            "passed": retrieval_pass and answer_pass and safety_pass,
        }

    @staticmethod
    def _summary(rows: list[dict[str, Any]], config: ExperimentConfig) -> dict[str, Any]:
        retrieval = [row for row in rows if row["expected_articles"]]
        abstain_rows = [row for row in rows if row["expected_outcome"] != "answer"]
        answer_rows = [row for row in rows if row["expected_outcome"] == "answer"]
        retry_rows = [row for row in rows if row["retry_count"] > 0]
        failures = Counter(tag for row in rows for tag in row["failure_types"])
        return {
            "total_cases": len(rows),
            "passed_cases": sum(row["passed"] for row in rows),
            "overall_pass_rate": round(mean(row["passed"] for row in rows), 4) if rows else 0.0,
            "retrieval": {
                "top1_accuracy": round(mean(row["top1_hit"] for row in retrieval), 4) if retrieval else None,
                "hit_at_k": round(mean(row["hit_at_k"] for row in retrieval), 4) if retrieval else None,
                "mean_recall_at_k": round(mean(row["recall_at_k"] for row in retrieval), 4) if retrieval else None,
                "mrr": round(mean(row["reciprocal_rank"] for row in retrieval), 4) if retrieval else None,
                "failure_rate": round(mean(not row["retrieval_pass"] for row in rows), 4) if rows else 0.0,
            },
            "answer": {
                "citation_accuracy": round(mean(bool(row["citation_valid"]) for row in rows if row["citation_valid"] is not None), 4) if any(row["citation_valid"] is not None for row in rows) else None,
                "grounding_pass_rate": round(mean(row["answer_pass"] for row in rows), 4) if rows else None,
            },
            "safety": {
                "expected_abstention_accuracy": round(mean(row["outcome_correct"] for row in abstain_rows), 4) if abstain_rows else None,
                "false_abstention_rate": round(mean(row["actual_outcome"] != "answer" for row in answer_rows), 4) if answer_rows else None,
                "outcome_accuracy": round(mean(row["outcome_correct"] for row in rows), 4) if rows else None,
                "retry_limit_compliance": round(mean(row["retry_count"] <= config.max_retries for row in rows), 4) if rows else None,
                "failure_reason_completeness": round(mean(row["failure_reason_complete"] for row in rows), 4) if rows else None,
                "retry_case_count": len(retry_rows),
                "average_retry_count": round(mean(row["retry_count"] for row in rows), 4) if rows else 0.0,
                "retry_improvement_rate": round(mean(bool(row["retry_improved"]) for row in retry_rows), 4) if retry_rows else None,
            },
            "average_latency_ms": round(mean(row["latency_ms"] for row in rows), 3) if rows else 0.0,
            "failure_type_counts": dict(sorted(failures.items())),
        }

    def run(self, config: ExperimentConfig, *, case_ids: list[str] | None = None,
            limit: int | None = None) -> dict[str, Any]:
        cases = load_dataset(config.dataset_path)
        if case_ids:
            selected = set(case_ids)
            cases = [case for case in cases if case.case_id in selected]
        if limit is not None:
            cases = cases[:limit]
        rows = [self._run_case(case, config) for case in cases]
        return {
            "experiment_id": f"exp_{uuid4().hex}",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "dataset": {"path": config.dataset_path, "version": config.dataset_version, "case_count": len(cases)},
            "code_version": __version__,
            "config": asdict(config),
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "summary": self._summary(rows, config),
            "cases": rows,
        }


class ExperimentStore:
    def __init__(self, directory: str | Path = "evaluation/experiments") -> None:
        self.directory = Path(directory)

    def save(self, report: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{report['experiment_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        path = self.directory / f"{experiment_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def list(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in self.directory.glob("exp_*.json")]
        reports.sort(key=lambda row: row["executed_at"], reverse=True)
        return [{key: row[key] for key in ("experiment_id", "executed_at", "dataset", "code_version", "config", "summary")} for row in reports]
