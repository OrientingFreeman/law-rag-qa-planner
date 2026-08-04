from copy import deepcopy

from tools.analyze_legal_kb_update import (
    DEFAULT_CORPUS,
    DEFAULT_EVALUATION,
    DEFAULT_KB,
    build_manifest,
    compare_corpora,
    load_json,
    validate_temporal_consistency,
)


def _fixtures():
    return load_json(DEFAULT_CORPUS), load_json(DEFAULT_KB), load_json(DEFAULT_EVALUATION)


def _row(corpus, document_id):
    return next(row for row in corpus if row["document_id"] == document_id)


def test_unchanged_snapshot_records_no_changes():
    corpus, kb, cases = _fixtures()
    manifest = build_manifest(corpus, deepcopy(corpus), kb, cases, generated_at="2026-08-04T00:00:00Z", mode="test")
    assert manifest["status"] == "no_changes"
    assert manifest["summary"]["changed_documents"] == 0
    assert manifest["required_actions"] == ["record_baseline_check"]


def test_content_change_traces_concept_and_evaluation_case():
    corpus, kb, cases = _fixtures()
    candidate = deepcopy(corpus)
    row = _row(candidate, "001872:제54조:①")
    row["text"] += " [TEST FIXTURE CHANGE]"
    manifest = build_manifest(corpus, candidate, kb, cases, generated_at="2026-08-04T00:00:00Z", mode="simulation")
    assert manifest["status"] == "changes_detected"
    assert manifest["changes"] == [{
        "change_type": "content_changed",
        "document_id": "001872:제54조:①",
        "law_id": "001872",
        "law_name": "근로기준법",
        "article_no": "제54조",
        "changed_fields": ["text"],
    }]
    assert any(row["concept_id"] == "labor_break" for row in manifest["impacted_concepts"])
    assert any(row["case_id"] == "labor-break" for row in manifest["impacted_evaluation_cases"])


def test_article_level_impact_includes_all_paragraph_changes():
    corpus, kb, cases = _fixtures()
    candidate = deepcopy(corpus)
    row = next(row for row in candidate if row["law_id"] == "011357" and row["article_no"] == "제17조")
    row["article_title"] = "TEST TITLE"
    manifest = build_manifest(corpus, candidate, kb, cases, generated_at="2026-08-04T00:00:00Z")
    assert any(row["concept_id"] == "pipa_third_party_provision" for row in manifest["impacted_concepts"])
    assert any(row["case_id"] == "pipa-third-party-provision" for row in manifest["impacted_evaluation_cases"])


def test_removed_document_is_detected():
    corpus, _, _ = _fixtures()
    candidate = [row for row in corpus if row["document_id"] != "001706:제750조"]
    changes = compare_corpora(corpus, candidate)
    assert any(change.change_type == "removed" and change.document_id == "001706:제750조" for change in changes)


def test_invalid_effective_period_rejects_candidate():
    corpus, kb, cases = _fixtures()
    candidate = deepcopy(corpus)
    row = _row(candidate, "001706:제750조")
    row["effective_to"] = "2020-01-01"
    manifest = build_manifest(corpus, candidate, kb, cases, generated_at="2026-08-04T00:00:00Z")
    assert manifest["status"] == "invalid"
    assert "reject_candidate_corpus" in manifest["required_actions"]
    assert any("effective_to precedes" in error for error in manifest["temporal_errors"])


def test_current_document_with_end_date_is_temporal_error():
    corpus, _, _ = _fixtures()
    candidate = deepcopy(corpus[:1])
    candidate[0]["effective_to"] = "2099-01-01"
    assert any("current document has effective_to" in error for error in validate_temporal_consistency(candidate))
