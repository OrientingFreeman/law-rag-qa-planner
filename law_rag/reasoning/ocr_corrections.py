from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Iterable

from law_rag.reasoning.ocr_audit import OcrAuditValidationError, OcrPageInput


OCR_TEXT_CORRECTIONS_SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class OcrTextCorrection:
    page_number: int
    original_text: str
    replacement_text: str
    reason: str
    review_status: str
    reviewer: str
    reviewed_at: str

    def validate(self) -> None:
        if self.page_number < 1 or not self.original_text or self.original_text == self.replacement_text:
            raise OcrAuditValidationError("invalid OCR text correction")
        if self.review_status not in {"draft", "approved", "rejected"}:
            raise OcrAuditValidationError(f"unsupported correction review_status: {self.review_status}")
        if not all(value.strip() for value in (self.reason, self.reviewer, self.reviewed_at)):
            raise OcrAuditValidationError("reason, reviewer, and reviewed_at are required")


def load_ocr_text_corrections(path: str | Path) -> list[OcrTextCorrection]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != OCR_TEXT_CORRECTIONS_SCHEMA_VERSION or not isinstance(payload.get("corrections"), list):
        raise OcrAuditValidationError("invalid OCR text corrections envelope")
    corrections = [OcrTextCorrection(**row) for row in payload["corrections"]]
    for correction in corrections:
        correction.validate()
    return corrections


def apply_ocr_text_corrections(
    pages: Iterable[OcrPageInput], corrections: Iterable[OcrTextCorrection]
) -> tuple[list[OcrPageInput], list[dict[str, object]]]:
    rows = {page.page_number: page for page in pages}
    audit: list[dict[str, object]] = []
    for correction in corrections:
        correction.validate()
        if correction.review_status != "approved":
            continue
        page = rows.get(correction.page_number)
        if page is None:
            raise OcrAuditValidationError(f"correction page not found: {correction.page_number}")
        occurrences = page.text.count(correction.original_text)
        if occurrences != 1:
            raise OcrAuditValidationError(
                f"correction original_text must match exactly once on page {correction.page_number}; found {occurrences}"
            )
        before_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        corrected = page.text.replace(correction.original_text, correction.replacement_text, 1)
        after_hash = hashlib.sha256(corrected.encode("utf-8")).hexdigest()
        rows[page.page_number] = replace(page, text=corrected)
        audit.append({
            "page_number": page.page_number,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "correction": asdict(correction),
        })
    return [rows[number] for number in sorted(rows)], audit
