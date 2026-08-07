from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from law_rag.service import LawRagService
from law_rag.evaluation.failures import diagnose_failure


@dataclass(slots=True)
class EvaluationCase:
    case_id: str
    question: str
    category: str = "direct_statute_retrieval"
    difficulty: str = "medium"
    domain: str = "all"
    top_k: int = 5
    as_of_date: date | None = None
    expected_document_ids: list[str] | None = None
    expected_law_id: str | None = None
    expected_article_nos: list[str] | None = None
    expected_abstain: bool = False
    expected_answer_points: list[str] | None = None
    annotation_note: str = ""
    evaluate_answer: bool = False
    expected_outcome: str | None = None
    required_facts: list[str] | None = None
    failure_tags: list[str] | None = None
    dataset_version: str = "1.0"
    review_status: str | None = None
    review_comment: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvaluationCase":
        parsed_date = date.fromisoformat(raw["as_of_date"]) if raw.get("as_of_date") else None
        return cls(
            case_id=str(raw["case_id"]),
            question=str(raw["question"]),
            category=str(raw.get("category", "direct_statute_retrieval")),
            difficulty=str(raw.get("difficulty", "medium")),
            domain=str(raw.get("domain", "all")),
            top_k=int(raw.get("top_k", 5)),
            as_of_date=parsed_date,
            expected_document_ids=list(raw.get("expected_document_ids", [])),
            expected_law_id=str(raw["expected_law_id"]) if raw.get("expected_law_id") else None,
            expected_article_nos=list(raw.get("expected_article_nos", [])),
            expected_abstain=bool(raw.get("expected_abstain", False)),
            expected_answer_points=list(raw.get("expected_answer_points", [])),
            annotation_note=str(raw.get("annotation_note", "")),
            evaluate_answer=bool(raw.get("evaluate_answer", False)),
            expected_outcome=str(raw["expected_outcome"]) if raw.get("expected_outcome") else None,
            required_facts=list(raw.get("required_facts", [])),
            failure_tags=list(raw.get("failure_tags", [])),
            dataset_version=str(raw.get("dataset_version", "1.0")),
            review_status=str(raw["review_status"]) if raw.get("review_status") else None,
            review_comment=str(raw["review_comment"]) if raw.get("review_comment") else None,
        )

    @property
    def uses_article_expectation(self) -> bool:
        return bool(self.expected_law_id and self.expected_article_nos)


@dataclass(slots=True)
class CaseResult:
    case_id: str
    question: str
    domain: str
    category: str
    difficulty: str
    expected_document_ids: list[str]
    expected_law_id: str | None
    expected_article_nos: list[str]
    retrieved_document_ids: list[str]
    retrieved_articles: list[str]
    expected_abstain: bool
    actual_abstain: bool
    top1_hit: bool
    hit_at_k: bool
    recall_at_k: float
    reciprocal_rank: float
    abstention_correct: bool
    temporal_valid: bool
    citation_valid: bool | None
    generation_status: str | None
    answer_point_coverage: float | None
    error_types: list[str]
    latency_ms: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationRunner:
    def __init__(self, service: LawRagService) -> None:
        self.service = service

    @staticmethod
    def _article_key(item: dict[str, Any]) -> str:
        return f"{item.get('law_id', '')}:{item.get('article_no', '')}"

    @staticmethod
    def _answer_point_coverage(answer: object, points: list[str]) -> float | None:
        """Return a conservative lexical completeness signal for generated answers.

        Retrieval-only cases return ``None``. This is a screening metric rather
        than a semantic correctness judgment; the report must label it as such.
        """
        if not isinstance(answer, str) or not answer.strip() or not points:
            return None
        answer_tokens = set(re.findall(r"[0-9A-Za-z가-힣]+", answer.lower()))
        covered = 0
        for point in points:
            tokens = {
                token for token in re.findall(r"[0-9A-Za-z가-힣]+", point.lower())
                if len(token) >= 2 and token not in {"한다", "있다", "확인한다", "밝힌다", "구분한다"}
            }
            if tokens and len(tokens & answer_tokens) / len(tokens) >= 0.5:
                covered += 1
        return round(covered / len(points), 4)

    def run_case(self, case: EvaluationCase) -> CaseResult:
        started = time.perf_counter()
        if case.evaluate_answer:
            response = self.service.answer(
                case.question,
                domain_id=case.domain,
                top_k=case.top_k,
                as_of_date=case.as_of_date,
            )
        else:
            response = self.service.retrieve(
                case.question,
                domain_id=case.domain,
                top_k=case.top_k,
                as_of_date=case.as_of_date,
            )
        latency_ms = (time.perf_counter() - started) * 1000

        results = list(response.get("results", []))
        retrieved = [str(item["document_id"]) for item in results]
        retrieved_articles = [self._article_key(item) for item in results]
        expected_docs = set(case.expected_document_ids or [])
        expected_articles = {
            f"{case.expected_law_id}:{article_no}"
            for article_no in (case.expected_article_nos or [])
        } if case.expected_law_id else set()
        expected = expected_articles if case.uses_article_expectation else expected_docs
        actual = retrieved_articles if case.uses_article_expectation else retrieved

        actual_abstain = bool(response.get("abstain", False))
        first_rank = next((i for i, value in enumerate(actual, 1) if value in expected), None)
        top1_hit = bool(expected and actual and actual[0] in expected)
        matched = expected.intersection(actual)
        hit_at_k = bool(matched) if expected else actual_abstain
        recall_at_k = len(matched) / len(expected) if expected else float(actual_abstain)
        reciprocal_rank = 1 / first_rank if first_rank else 0.0
        abstention_correct = actual_abstain == case.expected_abstain

        temporal_valid = True
        if case.as_of_date:
            temporal_valid = all(
                not item.get("effective_from")
                or date.fromisoformat(str(item["effective_from"])) <= case.as_of_date
                for item in results
            )

        citation_validation = response.get("citation_validation")
        citation_valid = (
            bool(citation_validation.get("valid"))
            if isinstance(citation_validation, dict)
            else None
        )
        generation_status = response.get("generation_status")
        answer_point_coverage = self._answer_point_coverage(
            response.get("answer"), list(case.expected_answer_points or [])
        ) if case.evaluate_answer else None

        retrieval_pass = actual_abstain if case.expected_abstain else bool(matched)
        citation_pass = citation_valid is not False
        passed = retrieval_pass and abstention_correct and temporal_valid and citation_pass

        result = CaseResult(
            case_id=case.case_id,
            question=case.question,
            domain=case.domain,
            category=case.category,
            difficulty=case.difficulty,
            expected_document_ids=list(case.expected_document_ids or []),
            expected_law_id=case.expected_law_id,
            expected_article_nos=list(case.expected_article_nos or []),
            retrieved_document_ids=retrieved,
            retrieved_articles=retrieved_articles,
            expected_abstain=case.expected_abstain,
            actual_abstain=actual_abstain,
            top1_hit=top1_hit,
            hit_at_k=hit_at_k,
            recall_at_k=round(recall_at_k, 4),
            reciprocal_rank=round(reciprocal_rank, 4),
            abstention_correct=abstention_correct,
            temporal_valid=temporal_valid,
            citation_valid=citation_valid,
            generation_status=str(generation_status) if generation_status is not None else None,
            answer_point_coverage=answer_point_coverage,
            error_types=[],
            latency_ms=round(latency_ms, 3),
            passed=passed,
        )
        # Diagnostics are independent from the legacy boolean pass criterion.
        # For example, a case may retrieve every gold article and still be
        # flagged as over_retrieval for later qualitative review.
        result.error_types = diagnose_failure(result.to_dict())
        return result

    @staticmethod
    def _metric_block(results: list[CaseResult]) -> dict[str, Any]:
        retrieval = [
            row for row in results
            if row.expected_document_ids or (row.expected_law_id and row.expected_article_nos)
        ]
        answer_rows = [row for row in results if row.citation_valid is not None]
        dated_rows = [row for row in results if row.category == "temporal_revision"]
        return {
            "total_cases": len(results),
            "passed_cases": sum(row.passed for row in results),
            "pass_rate": round(mean(row.passed for row in results), 4) if results else 0.0,
            "top1_accuracy": round(mean(row.top1_hit for row in retrieval), 4) if retrieval else None,
            "hit_at_k": round(mean(row.hit_at_k for row in retrieval), 4) if retrieval else None,
            "mean_recall_at_k": round(mean(row.recall_at_k for row in retrieval), 4) if retrieval else None,
            "mean_reciprocal_rank": round(mean(row.reciprocal_rank for row in retrieval), 4) if retrieval else None,
            "abstention_accuracy": round(mean(row.abstention_correct for row in results), 4) if results else None,
            "temporal_accuracy": round(mean(row.temporal_valid for row in dated_rows), 4) if dated_rows else None,
            "citation_accuracy": round(mean(bool(row.citation_valid) for row in answer_rows), 4) if answer_rows else None,
            "average_latency_ms": round(mean(row.latency_ms for row in results), 3) if results else 0.0,
        }

    def _grouped_metrics(self, results: list[CaseResult], field: str) -> dict[str, dict[str, Any]]:
        values = sorted({str(getattr(row, field)) for row in results})
        return {
            value: self._metric_block([row for row in results if str(getattr(row, field)) == value])
            for value in values
        }

    def run(self, cases: list[EvaluationCase]) -> dict[str, Any]:
        case_results = [self.run_case(case) for case in cases]
        summary = self._metric_block(case_results)
        error_counts: dict[str, int] = {}
        for row in case_results:
            for error_type in row.error_types:
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        summary["error_type_counts"] = dict(sorted(error_counts.items()))
        return {
            "version": "1.1.0",
            "summary": summary,
            "metrics_by_category": self._grouped_metrics(case_results, "category"),
            "metrics_by_difficulty": self._grouped_metrics(case_results, "difficulty"),
            "cases": [result.to_dict() for result in case_results],
        }


def load_dataset(path: str | Path) -> list[EvaluationCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw["cases"] if isinstance(raw, dict) else raw
    return [EvaluationCase.from_dict(item) for item in rows]


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
