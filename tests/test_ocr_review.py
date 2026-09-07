from __future__ import annotations

from pathlib import Path
import stat

import pytest

from law_rag.reasoning.ocr_audit import OcrPageInput, OcrSourceManifest, audit_ocr_source
from law_rag.reasoning.ocr_review import build_private_ocr_review_queue, save_private_ocr_review_queue


def test_review_queue_classifies_front_matter_gaps_and_includes_only_limited_risk_snippets(tmp_path: Path) -> None:
    manifest = OcrSourceManifest("fixture.queue", "queue", "test", "authored_fixture", "authored", 1, 3)
    pages = [
        OcrPageInput(1, "머리말에 해당하는 충분한 길이의 직접 작성 문장입니다."),
        OcrPageInput(2, "호환 한자 豈가 포함된 충분한 길이의 직접 작성 문장입니다.", "1"),
        OcrPageInput(3, "본문에 해당하는 충분한 길이의 직접 작성 문장입니다."),
    ]
    report = audit_ocr_source(manifest, pages)
    queue = build_private_ocr_review_queue(report, pages)
    classifications = {item["page_number"]: item["classification"] for item in queue["items"] if item["code"] == "missing_printed_page_label"}
    assert classifications == {1: "front_matter_candidate", 3: "manual_label_review"}
    compatibility = next(item for item in queue["items"] if item["code"] == "compatibility_ideograph")
    assert "豈" in compatibility["snippet"]
    output = save_private_ocr_review_queue(queue, tmp_path / "queue.json")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_private_review_queue_is_refused_inside_git_worktree() -> None:
    with pytest.raises(ValueError, match="Git worktree"):
        save_private_ocr_review_queue({"items": []}, Path.cwd() / "evaluation" / "ocr" / "private-review.json")


def test_dominant_offset_suggests_labels_without_auto_approval() -> None:
    manifest = OcrSourceManifest("fixture.offset", "offset", "test", "authored_fixture", "authored", 1, 30)
    pages = []
    for physical in range(1, 31):
        label = str(physical - 2) if physical >= 3 and physical not in {12, 13} else None
        pages.append(OcrPageInput(physical, f"물리면 {physical}의 충분한 직접 작성 본문입니다.", label))
    report = audit_ocr_source(manifest, pages)
    queue = build_private_ocr_review_queue(report, pages)
    inferred = [item for item in queue["items"] if item["classification"] == "offset_sequence_inferable"]
    assert {item["page_number"]: item["suggested_printed_page_label"] for item in inferred} == {12: "10", 13: "11"}
    assert all(item["inference_confidence"] == "high" for item in inferred)
    assert queue["summary"]["printed_page_inference"]["dominant_offset"] == 2
