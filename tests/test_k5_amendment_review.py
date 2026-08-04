from copy import deepcopy

from tools.review_k5_amendment_update import (
    DEFAULT_INPUT,
    DEFAULT_MANIFEST,
    evaluate_review,
    file_sha256,
    load_json,
)


def _inputs():
    return load_json(DEFAULT_INPUT), load_json(DEFAULT_MANIFEST), file_sha256(DEFAULT_MANIFEST)


def test_reviewed_k4_case_passes_release_gate():
    review, manifest, digest = _inputs()
    result = evaluate_review(review, manifest, digest)
    assert result["decision"] == "pass"
    assert result["baseline_promotion_allowed"] is True
    assert result["check_summary"]["passed"] == 9


def test_manifest_hash_mismatch_is_rejected():
    review, manifest, _ = _inputs()
    result = evaluate_review(review, manifest, "0" * 64)
    assert result["decision"] == "reject"
    assert "input_manifest_hash_mismatch" in result["reject_reasons"]


def test_non_official_source_is_rejected():
    review, manifest, digest = _inputs()
    broken = deepcopy(manifest)
    broken["official_amendment"]["official_sources"]["after_text_url"] = "https://example.com/law"
    result = evaluate_review(review, broken, digest)
    assert result["decision"] == "reject"
    assert "non_official_source" in result["reject_reasons"]


def test_pending_impact_review_requires_revision():
    review, manifest, digest = _inputs()
    broken = deepcopy(review)
    next(row for row in broken["checklist"] if row["check_id"] == "knowledge_impact")["status"] = "pending"
    result = evaluate_review(broken, manifest, digest)
    assert result["decision"] == "revise"
    assert result["baseline_promotion_allowed"] is False


def test_critical_check_rejection_cannot_be_overridden_by_requested_pass():
    review, manifest, digest = _inputs()
    broken = deepcopy(review)
    next(row for row in broken["checklist"] if row["check_id"] == "effective_date")["status"] = "reject"
    result = evaluate_review(broken, manifest, digest)
    assert result["decision"] == "reject"
    assert result["decision_matches_request"] is False
    assert "requested pass cannot override gate decision" in result["evidence_errors"]


def test_invalid_stage_order_requires_revision():
    review, manifest, digest = _inputs()
    broken = deepcopy(review)
    broken["stages"][1], broken["stages"][2] = broken["stages"][2], broken["stages"][1]
    result = evaluate_review(broken, manifest, digest)
    assert result["decision"] == "revise"
    assert any("review stages" in reason for reason in result["revise_reasons"])
