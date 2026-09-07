from __future__ import annotations

import pytest

from law_rag.reasoning.ocr_audit import OcrAuditValidationError, OcrPageInput
from law_rag.reasoning.ocr_corrections import OcrTextCorrection, apply_ocr_text_corrections


def _correction(original: str = "아니 된 다") -> OcrTextCorrection:
    return OcrTextCorrection(1, original, "아니 된다", "원본 대조", "approved", "reviewer-1", "2026-08-22")


def test_approved_correction_overlay_preserves_hash_audit_without_mutating_input() -> None:
    page = OcrPageInput(1, "그 기간을 넘어서는 아니 된 다.", "1")
    corrected, audit = apply_ocr_text_corrections([page], [_correction()])
    assert page.text.endswith("아니 된 다.")
    assert corrected[0].text.endswith("아니 된다.")
    assert audit[0]["before_sha256"] != audit[0]["after_sha256"]
    assert audit[0]["correction"]["reviewer"] == "reviewer-1"


def test_stale_or_ambiguous_correction_is_rejected() -> None:
    with pytest.raises(OcrAuditValidationError, match="found 0"):
        apply_ocr_text_corrections([OcrPageInput(1, "이미 교정된 문장")], [_correction()])
    with pytest.raises(OcrAuditValidationError, match="found 2"):
        apply_ocr_text_corrections([OcrPageInput(1, "아니 된 다 그리고 아니 된 다")], [_correction()])
