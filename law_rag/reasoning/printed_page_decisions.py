from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Iterable

from law_rag.reasoning.ocr_audit import OcrAuditValidationError, OcrPageInput


PRINTED_PAGE_DECISIONS_SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class PrintedPageDecision:
    page_number: int
    action: str
    printed_page_label: str | None
    reason: str
    review_status: str
    reviewer: str
    reviewed_at: str
    inference_confidence: str | None = None
    inference_evidence: str | None = None

    def validate(self) -> None:
        if self.page_number < 1:
            raise OcrAuditValidationError("printed-page decision page_number must be positive")
        if self.action not in {"assign_label", "verified_label_absent"}:
            raise OcrAuditValidationError(f"unsupported printed-page decision action: {self.action}")
        if self.action == "assign_label" and not (self.printed_page_label or "").strip():
            raise OcrAuditValidationError("assign_label requires printed_page_label")
        if self.action == "verified_label_absent" and self.printed_page_label is not None:
            raise OcrAuditValidationError("verified_label_absent must not include printed_page_label")
        if self.review_status not in {"draft", "approved", "rejected"}:
            raise OcrAuditValidationError(f"unsupported printed-page review_status: {self.review_status}")
        if not all(value.strip() for value in (self.reason, self.reviewer, self.reviewed_at)):
            raise OcrAuditValidationError("reason, reviewer, and reviewed_at are required")


def load_printed_page_decisions(path: str | Path) -> list[PrintedPageDecision]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != PRINTED_PAGE_DECISIONS_SCHEMA_VERSION or not isinstance(payload.get("decisions"), list):
        raise OcrAuditValidationError("invalid printed-page decisions envelope")
    decisions = [PrintedPageDecision(**row) for row in payload["decisions"]]
    for decision in decisions:
        decision.validate()
    if len({item.page_number for item in decisions}) != len(decisions):
        raise OcrAuditValidationError("duplicate printed-page decision")
    return decisions


def apply_printed_page_decisions(
    pages: Iterable[OcrPageInput], decisions: Iterable[PrintedPageDecision]
) -> tuple[list[OcrPageInput], set[int], list[dict[str, object]]]:
    rows = {page.page_number: page for page in pages}
    verified_absent: set[int] = set()
    audit: list[dict[str, object]] = []
    for decision in decisions:
        decision.validate()
        if decision.review_status != "approved":
            continue
        page = rows.get(decision.page_number)
        if page is None:
            raise OcrAuditValidationError(f"printed-page decision page not found: {decision.page_number}")
        before = page.printed_page_label
        if decision.action == "assign_label":
            if before is not None and before != decision.printed_page_label:
                raise OcrAuditValidationError(f"printed-page decision conflicts with detected label on page {page.page_number}")
            rows[page.page_number] = replace(page, printed_page_label=decision.printed_page_label)
        else:
            if before is not None:
                raise OcrAuditValidationError(f"verified absent conflicts with detected label on page {page.page_number}")
            verified_absent.add(page.page_number)
        audit.append({
            "page_number": page.page_number,
            "before_label": before,
            "after_label": rows[page.page_number].printed_page_label,
            "decision_sha256": hashlib.sha256(
                json.dumps(asdict(decision), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "decision": asdict(decision),
        })
    return [rows[number] for number in sorted(rows)], verified_absent, audit


def decisions_from_review_queue(
    queue: dict[str, object], *, reviewer: str, reviewed_at: str, verified_absent_pages: set[int]
) -> dict[str, object]:
    decisions: list[PrintedPageDecision] = []
    for raw in queue.get("items", []):
        if not isinstance(raw, dict) or raw.get("code") != "missing_printed_page_label":
            continue
        page_number = int(raw["page_number"])
        if page_number in verified_absent_pages:
            decision = PrintedPageDecision(
                page_number, "verified_label_absent", None, "원본 페이지에서 인쇄면수 부재 확인",
                "approved", reviewer, reviewed_at,
            )
        elif raw.get("classification") == "offset_sequence_inferable" and raw.get("inference_confidence") == "high":
            decision = PrintedPageDecision(
                page_number, "assign_label", str(raw["suggested_printed_page_label"]),
                "고신뢰도 물리면-인쇄면 오프셋 및 주변 연속성 검토",
                "approved", reviewer, reviewed_at,
                str(raw.get("inference_confidence")), str(raw.get("inference_evidence")),
            )
        else:
            continue
        decision.validate()
        decisions.append(decision)
    return {
        "schema_version": PRINTED_PAGE_DECISIONS_SCHEMA_VERSION,
        "source_content_sha256": queue.get("content_sha256"),
        "decisions": [asdict(item) for item in decisions],
    }


def save_private_printed_page_decisions(payload: dict[str, object], output_path: str | Path) -> Path:
    output = Path(output_path).expanduser().resolve()
    current = Path.cwd().resolve()
    worktree = next((candidate for candidate in (current, *current.parents) if (candidate / ".git").exists()), None)
    if worktree is not None and output.is_relative_to(worktree):
        raise ValueError(f"refusing to write private printed-page decisions inside Git worktree: {worktree}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return output
