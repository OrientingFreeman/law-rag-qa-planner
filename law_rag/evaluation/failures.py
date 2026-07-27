from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class FailureCaseLogger:
    """Append evaluation failures as newline-delimited JSON records."""

    def __init__(self, path: str | Path = "evaluation/failures/failure_cases.jsonl") -> None:
        self.path = Path(path)

    def append(self, payload: dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.path

    def append_many(self, payloads: Iterable[dict[str, Any]]) -> int:
        count = 0
        for payload in payloads:
            self.append(payload)
            count += 1
        return count


def diagnose_failure(case: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not case.get("abstention_correct", True):
        reasons.append("abstention_mismatch")
    if not case.get("temporal_valid", True):
        reasons.append("temporal_filter_failure")
    if case.get("citation_valid") is False:
        reasons.append("citation_validation_failure")
    if not case.get("expected_abstain", False) and not case.get("hit_at_k", False):
        reasons.append("expected_evidence_not_retrieved")
    if case.get("expected_abstain", False) and not case.get("actual_abstain", False):
        reasons.append("unexpected_evidence_retrieved")
    return reasons or ["evaluation_failure"]


def failure_payload(case: dict[str, Any], *, dataset: str | None = None) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "question": case.get("question"),
        "domain": case.get("domain"),
        "dataset": dataset,
        "expected": {
            "document_ids": case.get("expected_document_ids", []),
            "law_id": case.get("expected_law_id"),
            "article_nos": case.get("expected_article_nos", []),
            "abstain": case.get("expected_abstain", False),
        },
        "retrieved": {
            "document_ids": case.get("retrieved_document_ids", []),
            "articles": case.get("retrieved_articles", []),
            "abstain": case.get("actual_abstain", False),
        },
        "reason": diagnose_failure(case),
        "metrics": {
            "top1_hit": case.get("top1_hit", False),
            "hit_at_k": case.get("hit_at_k", False),
            "recall_at_k": case.get("recall_at_k", 0.0),
            "reciprocal_rank": case.get("reciprocal_rank", 0.0),
            "citation_valid": case.get("citation_valid"),
            "latency_ms": case.get("latency_ms", 0.0),
        },
    }
