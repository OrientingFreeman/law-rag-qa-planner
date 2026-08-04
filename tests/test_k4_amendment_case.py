from copy import deepcopy

from tools.analyze_legal_kb_update import load_json
from tools.run_k4_amendment_case import (
    DEFAULT_AFTER,
    DEFAULT_BEFORE,
    DEFAULT_CANDIDATES,
    DEFAULT_CASES,
    DEFAULT_CURRENT_CORPUS,
    DEFAULT_EVALUATION,
    DEFAULT_KB,
    build_k4_result,
    evaluate_temporal_cases,
)


def _result():
    return build_k4_result(
        load_json(DEFAULT_BEFORE),
        load_json(DEFAULT_AFTER),
        load_json(DEFAULT_KB),
        load_json(DEFAULT_EVALUATION),
        load_json(DEFAULT_CASES),
        load_json(DEFAULT_CANDIDATES),
        load_json(DEFAULT_CURRENT_CORPUS),
        generated_at="2026-08-04T00:00:00Z",
    )


def test_actual_amendment_detects_article_15_item_7_addition():
    result = _result()
    assert result["status"] == "pass"
    assert result["substantive_changes"] == [{
        "change_type": "added",
        "document_id": "011357:제15조:①:제7호",
        "law_id": "011357",
        "law_name": "개인정보 보호법",
        "article_no": "제15조",
        "changed_fields": [],
    }]


def test_actual_amendment_traces_existing_concept_and_official_case():
    result = _result()
    assert [row["concept_id"] for row in result["comparison"]["impacted_concepts"]] == ["pipa_collection_use"]
    assert [row["case_id"] for row in result["comparison"]["impacted_evaluation_cases"]] == ["pipa-collection-basis"]


def test_effective_date_boundary_cases_pass():
    result = _result()
    assert result["temporal_evaluation"]["accuracy"] == 1.0
    before, after = result["temporal_evaluation"]["results"]
    assert before["as_of_date"] == "2025-10-01" and before["actual_present"] is False
    assert after["as_of_date"] == "2025-10-02" and after["actual_present"] is True


def test_wrong_temporal_gold_is_detected():
    before = load_json(DEFAULT_BEFORE)
    after = load_json(DEFAULT_AFTER)
    cases = deepcopy(load_json(DEFAULT_CASES))
    cases[0]["expected_present"] = True
    results = evaluate_temporal_cases(before, after, cases)
    assert results[0]["passed"] is False


def test_after_fixture_matches_current_official_corpus_text():
    assert _result()["fixture_provenance_errors"] == []
