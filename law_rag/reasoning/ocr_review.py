from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from law_rag.reasoning.ocr_audit import NonTextPageDecision, OcrAuditReport, OcrPageInput


OCR_REVIEW_QUEUE_SCHEMA_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class OcrReviewQueueItem:
    warning_id: str
    code: str
    page_number: int | None
    classification: str
    snippet: str | None
    snippet_sha256: str | None
    suggested_action: str
    suggested_printed_page_label: str | None = None
    inference_confidence: str | None = None
    inference_evidence: str | None = None


def _printed_label_inference(pages: dict[int, OcrPageInput]) -> tuple[int | None, float, int]:
    offsets = [
        page.page_number - int(page.printed_page_label)
        for page in pages.values()
        if (page.printed_page_label or "").isdigit() and int(page.printed_page_label or 0) > 0
    ]
    if not offsets:
        return None, 0.0, 0
    offset, support = Counter(offsets).most_common(1)[0]
    return offset, support / len(offsets), support


def _neighbor_support(page_number: int, pages: dict[int, OcrPageInput], offset: int) -> int:
    support = 0
    for distance in (1, 2, 3):
        for number in (page_number - distance, page_number + distance):
            page = pages.get(number)
            if page and (page.printed_page_label or "").isdigit() and number - int(page.printed_page_label or 0) == offset:
                support += 1
    return support


def _active_git_worktree_root() -> Path | None:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _snippet(text: str, code: str, radius: int = 80) -> str | None:
    pattern = {
        "compatibility_ideograph": re.compile(r"[\uf900-\ufaff]"),
        "suspect_negation_spacing": re.compile(r"아니\s+된\s+다"),
    }.get(code)
    match = pattern.search(text) if pattern else None
    if not match:
        return None
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def build_private_ocr_review_queue(
    report: OcrAuditReport,
    pages: Iterable[OcrPageInput],
    *,
    page_decisions: Iterable[NonTextPageDecision] = (),
    correction_audit: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    page_by_number = {page.page_number: page for page in pages}
    approved_non_text = {item.page_number for item in page_decisions if item.review_status == "approved"}
    numeric_labels = [page.page_number for page in page_by_number.values() if (page.printed_page_label or "").isdigit()]
    first_numeric_page = min(numeric_labels) if numeric_labels else None
    dominant_offset, offset_ratio, offset_support = _printed_label_inference(page_by_number)
    items: list[OcrReviewQueueItem] = []
    for warning in report.warnings:
        if warning.severity != "warning":
            continue
        page = page_by_number.get(warning.page_number or -1)
        snippet = _snippet(page.text, warning.code) if page else None
        suggested_label = confidence = evidence = None
        if warning.code == "missing_printed_page_label":
            if warning.page_number in approved_non_text:
                classification = "approved_non_text"
            elif page and not page.text.strip():
                classification = "unreviewed_non_text"
            elif first_numeric_page is not None and warning.page_number is not None and warning.page_number < first_numeric_page:
                classification = "front_matter_candidate"
            elif dominant_offset is not None and warning.page_number is not None and warning.page_number - dominant_offset > 0 and offset_support >= 20 and offset_ratio >= 0.80:
                neighbor_support = _neighbor_support(warning.page_number, page_by_number, dominant_offset)
                classification = "offset_sequence_inferable"
                suggested_label = str(warning.page_number - dominant_offset)
                confidence = "high" if neighbor_support >= 2 else "medium"
                evidence = f"dominant_offset={dominant_offset}; support={offset_support}; ratio={offset_ratio:.4f}; neighbors={neighbor_support}"
            else:
                classification = "manual_label_review"
            action = "review_suggested_label" if classification == "offset_sequence_inferable" else ("verified_label_absent" if classification != "manual_label_review" else "inspect_page_header")
        else:
            classification = "text_quality_review"
            action = "inspect_source_text"
        digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest() if snippet else None
        items.append(OcrReviewQueueItem(warning.warning_id, warning.code, warning.page_number, classification, snippet, digest, action, suggested_label, confidence, evidence))
    counts: dict[str, int] = {}
    for item in items:
        counts[item.classification] = counts.get(item.classification, 0) + 1
    return {
        "schema_version": OCR_REVIEW_QUEUE_SCHEMA_VERSION,
        "document_id": report.document["document_id"],
        "content_sha256": report.content_sha256,
        "private_review_required": True,
        "correction_audit": list(correction_audit),
        "summary": {
            "queue_count": len(items),
            "classification_counts": counts,
            "printed_page_inference": {
                "dominant_offset": dominant_offset,
                "support_count": offset_support,
                "support_ratio": round(offset_ratio, 4),
            },
        },
        "items": [asdict(item) for item in items],
    }


def save_private_ocr_review_queue(queue: dict[str, object], output_path: str | Path) -> Path:
    output = Path(output_path).expanduser().resolve()
    worktree = _active_git_worktree_root()
    if worktree is not None and output.is_relative_to(worktree):
        raise ValueError(f"refusing to write private OCR review snippets inside Git worktree: {worktree}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(queue, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return output
