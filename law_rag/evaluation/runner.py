from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from law_rag.service import LawRagService


@dataclass(slots=True)
class EvaluationCase:
    case_id: str
    question: str
    domain: str = "all"
    top_k: int = 5
    as_of_date: date | None = None
    expected_document_ids: list[str] | None = None
    expected_law_id: str | None = None
    expected_article_nos: list[str] | None = None
    expected_abstain: bool = False
    evaluate_answer: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvaluationCase":
        parsed_date = date.fromisoformat(raw["as_of_date"]) if raw.get("as_of_date") else None
        return cls(
            case_id=str(raw["case_id"]),
            question=str(raw["question"]),
            domain=str(raw.get("domain", "all")),
            top_k=int(raw.get("top_k", 5)),
            as_of_date=parsed_date,
            expected_document_ids=list(raw.get("expected_document_ids", [])),
            expected_law_id=str(raw["expected_law_id"]) if raw.get("expected_law_id") else None,
            expected_article_nos=list(raw.get("expected_article_nos", [])),
            expected_abstain=bool(raw.get("expected_abstain", False)),
            evaluate_answer=bool(raw.get("evaluate_answer", False)),
        )

    @property
    def uses_article_expectation(self) -> bool:
        return bool(self.expected_law_id and self.expected_article_nos)


@dataclass(slots=True)
class CaseResult:
    case_id: str
    question: str
    domain: str
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

        retrieval_pass = actual_abstain if case.expected_abstain else bool(matched)
        citation_pass = citation_valid is not False
        passed = retrieval_pass and abstention_correct and temporal_valid and citation_pass

        return CaseResult(
            case_id=case.case_id,
            question=case.question,
            domain=case.domain,
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
            latency_ms=round(latency_ms, 3),
            passed=passed,
        )

    def run(self, cases: list[EvaluationCase]) -> dict[str, Any]:
        case_results = [self.run_case(case) for case in cases]
        total = len(case_results)
        retrieval_cases = [
            r for r in case_results
            if r.expected_document_ids or (r.expected_law_id and r.expected_article_nos)
        ]
        answer_cases = [r for r in case_results if r.citation_valid is not None]
        summary = {
            "total_cases": total,
            "passed_cases": sum(r.passed for r in case_results),
            "pass_rate": round(sum(r.passed for r in case_results) / total, 4) if total else 0.0,
            "top1_accuracy": round(mean(r.top1_hit for r in retrieval_cases), 4) if retrieval_cases else 0.0,
            "hit_at_k": round(mean(r.hit_at_k for r in retrieval_cases), 4) if retrieval_cases else 0.0,
            "mean_recall_at_k": round(mean(r.recall_at_k for r in retrieval_cases), 4) if retrieval_cases else 0.0,
            "mean_reciprocal_rank": round(mean(r.reciprocal_rank for r in retrieval_cases), 4) if retrieval_cases else 0.0,
            "abstention_accuracy": round(mean(r.abstention_correct for r in case_results), 4) if total else 0.0,
            "temporal_accuracy": round(mean(r.temporal_valid for r in case_results), 4) if total else 0.0,
            "citation_accuracy": round(mean(bool(r.citation_valid) for r in answer_cases), 4) if answer_cases else None,
            "average_latency_ms": round(mean(r.latency_ms for r in case_results), 3) if total else 0.0,
        }
        return {
            "version": "1.0.0",
            "summary": summary,
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
