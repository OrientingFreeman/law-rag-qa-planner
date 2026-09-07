from __future__ import annotations

from law_rag.reasoning.ocr_audit import OcrPageInput, OcrSourceManifest, audit_ocr_source
from law_rag.reasoning.printed_page_decisions import PrintedPageDecision, apply_printed_page_decisions, decisions_from_review_queue


def test_high_confidence_and_verified_absent_decisions_apply_with_audit_history() -> None:
    queue = {
        "content_sha256": "fixture-hash",
        "items": [
            {
                "code": "missing_printed_page_label", "page_number": 1,
                "classification": "front_matter_candidate", "inference_confidence": None,
            },
            {
                "code": "missing_printed_page_label", "page_number": 41,
                "classification": "offset_sequence_inferable", "inference_confidence": "high",
                "suggested_printed_page_label": "1", "inference_evidence": "dominant_offset=40",
            },
        ],
    }
    payload = decisions_from_review_queue(queue, reviewer="reviewer-1", reviewed_at="2026-08-22", verified_absent_pages={1})
    assert len(payload["decisions"]) == 2
    pages, absent, mapping_audit = apply_printed_page_decisions(
        [OcrPageInput(1, "서문에 해당하는 충분한 길이의 직접 작성 문장입니다."), OcrPageInput(41, "본문에 해당하는 충분한 길이의 직접 작성 문장입니다.")],
        [PrintedPageDecision(**row) for row in payload["decisions"]],
    )
    assert pages[1].printed_page_label == "1"
    assert absent == {1}
    assert mapping_audit[1]["decision_sha256"]
    manifest = OcrSourceManifest("fixture.mapping", "mapping", "test", "authored_fixture", "authored", 1, 41)
    report = audit_ocr_source(manifest, pages, verified_absent_printed_pages=absent)
    assert not any(item.code == "missing_printed_page_label" for item in report.warnings if item.page_number in {1, 41})
