from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4


ReviewStatus = Literal["draft", "review_required", "approved", "rejected", "deprecated"]
ReviewDecision = Literal["approve", "revise", "reject", "deprecate"]

DECISION_STATUS: dict[ReviewDecision, ReviewStatus] = {
    "approve": "approved",
    "revise": "review_required",
    "reject": "rejected",
    "deprecate": "deprecated",
}


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    review_id: str
    target_type: str
    target_id: str
    dataset_id: str
    dataset_version: str
    ground_truth_version: str
    decision: ReviewDecision
    review_status: ReviewStatus
    reviewer_id: str
    review_comment: str
    reviewed_at: str

    @classmethod
    def create(
        cls, *, target_type: str, target_id: str, dataset_id: str,
        dataset_version: str, ground_truth_version: str, decision: ReviewDecision,
        reviewer_id: str, review_comment: str,
    ) -> "ReviewRecord":
        if not reviewer_id.strip():
            raise ValueError("reviewer_id is required")
        if decision in {"revise", "reject", "deprecate"} and not review_comment.strip():
            raise ValueError(f"review_comment is required for {decision}")
        return cls(
            review_id=f"review_{uuid4().hex}",
            target_type=target_type,
            target_id=target_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            ground_truth_version=ground_truth_version,
            decision=decision,
            review_status=DECISION_STATUS[decision],
            reviewer_id=reviewer_id.strip(),
            review_comment=review_comment.strip(),
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class JsonReviewStore:
    """Append-only JSONL review history with latest-state lookup."""

    def __init__(self, path: str | Path = "evaluation/reviews/review_records.jsonl") -> None:
        self.path = Path(path)
        self._lock = RLock()

    def append(self, record: ReviewRecord) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def list(self, *, target_type: str | None = None) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [row for row in rows if target_type is None or row["target_type"] == target_type]

    def latest(self, *, target_type: str) -> dict[str, dict[str, str]]:
        latest: dict[str, dict[str, str]] = {}
        for row in self.list(target_type=target_type):
            latest[row["target_id"]] = row
        return latest
