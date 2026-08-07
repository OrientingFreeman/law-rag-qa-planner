from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


StepStatus = Literal["pending", "running", "completed", "warning", "abstained", "failed", "skipped"]
Outcome = Literal["answered", "abstained", "needs_clarification", "failed"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class WorkflowConfig:
    search_strategy: str = "hybrid"
    query_rewrite: bool = True
    reranking: bool = True
    max_retries: int = 1
    retry_top_k_increment: int = 3
    abstention_policy: bool = True

    def __post_init__(self) -> None:
        if self.search_strategy not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("search_strategy must be lexical, semantic, or hybrid")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")
        if not 1 <= self.retry_top_k_increment <= 20:
            raise ValueError("retry_top_k_increment must be between 1 and 20")


@dataclass(slots=True)
class TraceStep:
    step_id: str
    step_name: str
    status: StepStatus = "pending"
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: float | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    search_strategy: str | None = None
    selected_evidence_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    retry: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentRun:
    run_id: str
    question: str
    domain: str
    config: WorkflowConfig
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    status: Literal["running", "completed"] = "running"
    outcome: Outcome | None = None
    stop_reason: str | None = None
    retry_count: int = 0
    final_quality: str | None = None
    execution_trace: list[TraceStep] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["config"] = asdict(self.config)
        return data
