from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_rag.reasoning.ocr_audit import (
    OcrAuditValidationError,
    OcrPageInput,
    OcrSourceManifest,
    NonTextPageDecision,
    OcrWarningDecision,
    audit_ocr_source,
    detect_footnote_boundary,
    load_ocr_import,
)


FIXTURE = Path("tests/fixtures/ocr_import.authored.json")


def test_authored_fixture_passes_and_preserves_segment_locations() -> None:
    manifest, pages = load_ocr_import(FIXTURE)
    report = audit_ocr_source(manifest, pages)
    assert report.quality_gate == "passed"
    assert report.page_count == 2
    assert report.segment_count == 4
    assert report.segments[0].segment_id == "segment.fixture.loan_pilot.p1.para1"
    assert report.segments[0].char_start == 0
    assert report.segments[0].text_sha256
    assert all(segment.review_status == "draft" for segment in report.segments)


def test_public_report_excludes_text_private_path_and_private_metadata() -> None:
    manifest, pages = load_ocr_import(FIXTURE)
    payload = audit_ocr_source(manifest, pages).to_json()
    assert "private://" not in payload
    assert "operator_note" not in payload
    assert "금전을 빌려주고" not in payload
    assert "public_purpose" in payload


def test_missing_page_blocks_quality_gate() -> None:
    manifest, pages = load_ocr_import(FIXTURE)
    report = audit_ocr_source(manifest, pages[:1])
    assert report.quality_gate == "blocked"
    assert report.summary["missing_page_count"] == 1
    assert any(item.code == "missing_page" and item.page_number == 2 for item in report.warnings)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("민법 제598죠에 따른다. 충분한 길이의 직접 작성 문장이다.", "suspect_article_number"),
        ("그 사실을 인정하면 아니 뇐다. 충분한 길이의 직접 작성 문장이다.", "suspect_negation"),
        ("판독할 수 없는 문자는 □로 표시됐다. 충분한 길이의 문장이다.", "replacement_glyph"),
        ("호환 한자 豈가 포함됐다. 충분한 길이의 직접 작성 문장이다.", "compatibility_ideograph"),
    ],
)
def test_legal_meaning_risk_patterns_are_flagged(text: str, code: str) -> None:
    manifest = OcrSourceManifest(
        document_id="fixture.risk",
        title="risk fixture",
        edition="test-1",
        source_type="authored_fixture",
        rights_status="authored",
        page_start=1,
        page_end=1,
    )
    report = audit_ocr_source(manifest, [OcrPageInput(1, text, printed_page_label="1")])
    assert report.quality_gate in {"blocked", "review_required"}
    assert any(item.code == code for item in report.warnings)


def test_duplicate_page_number_and_invalid_manifest_are_rejected_or_blocked() -> None:
    manifest, pages = load_ocr_import(FIXTURE)
    report = audit_ocr_source(manifest, [pages[0], pages[0]])
    assert report.quality_gate == "blocked"
    assert any(item.code == "duplicate_page_number" for item in report.warnings)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["manifest"]["page_start"] = 0
    with pytest.raises(OcrAuditValidationError, match="invalid page range"):
        OcrSourceManifest.from_dict(raw["manifest"])


def test_standard_negation_is_not_an_ocr_error_but_malformed_spacing_is_reviewable() -> None:
    manifest = OcrSourceManifest(
        document_id="fixture.negation",
        title="negation fixture",
        edition="test-1",
        source_type="authored_fixture",
        rights_status="authored",
        page_start=1,
        page_end=1,
    )
    standard = audit_ocr_source(manifest, [OcrPageInput(1, "그 요건에 해당하지 아니 된다. 충분한 길이의 정상 문장이다.", "1")])
    assert not any(item.code.startswith("suspect_negation") for item in standard.warnings)
    spaced = audit_ocr_source(manifest, [OcrPageInput(1, "그 요건에 해당하지 아니 된 다. 충분한 길이의 검토 문장이다.", "1")])
    assert spaced.quality_gate == "review_required"
    assert any(item.code == "suspect_negation_spacing" and item.severity == "warning" for item in spaced.warnings)


def test_approved_non_text_page_does_not_block_but_draft_does() -> None:
    manifest = OcrSourceManifest("fixture.blank", "blank", "test", "authored_fixture", "authored", 1, 1)
    approved = NonTextPageDecision(1, "blank", "visual inspection", "approved", "reviewer-1", "2026-08-22")
    report = audit_ocr_source(manifest, [OcrPageInput(1, "")], page_decisions=[approved])
    assert report.quality_gate == "passed"
    assert report.summary["expected_non_text_count"] == 1
    draft = NonTextPageDecision(1, "blank", "pending", "draft", "reviewer-1", "2026-08-22")
    assert audit_ocr_source(manifest, [OcrPageInput(1, "")], page_decisions=[draft]).quality_gate == "blocked"


def test_variable_footnote_boundary_is_a_hint_not_a_half_page_split() -> None:
    text = "본문 첫 문단입니다. " * 18 + "\n\n1) 첫 각주 설명입니다.\n\n2) 둘째 각주 설명입니다."
    boundary = detect_footnote_boundary(text)
    assert boundary is not None and boundary / len(text) > 0.7
    manifest = OcrSourceManifest("fixture.notes", "notes", "test", "authored_fixture", "authored", 1, 1)
    report = audit_ocr_source(manifest, [OcrPageInput(1, text, "1")], infer_footnotes=True)
    assert {segment.zone_hint for segment in report.segments} == {"body_candidate", "footnote_candidate"}
    assert detect_footnote_boundary("1) 본문 목록 하나\n긴 본문만 있고 각주 군집은 없습니다.") is None


def test_approved_warning_decision_is_downgraded_with_audit_history() -> None:
    manifest = OcrSourceManifest("fixture.review", "review", "test", "authored_fixture", "authored", 1, 1)
    pages = [OcrPageInput(1, "호환 한자 豈가 포함된 충분한 길이의 검토 문장입니다.", "1")]
    first = audit_ocr_source(manifest, pages)
    warning = next(item for item in first.warnings if item.code == "compatibility_ideograph")
    decision = OcrWarningDecision(
        warning.warning_id, "accepted_as_is", "원본 대조 완료", "approved", "reviewer-1", "2026-08-22"
    )
    reviewed = audit_ocr_source(manifest, pages, warning_decisions=[decision])
    assert reviewed.quality_gate == "passed"
    assert reviewed.summary["reviewed_warning_count"] == 1
    assert next(item for item in reviewed.warnings if item.warning_id == warning.warning_id).severity == "info"
