from copy import deepcopy

from tools.validate_amendment_case_candidates import (
    DEFAULT_CANDIDATES,
    DEFAULT_CORPUS,
    DEFAULT_EVALUATION,
    DEFAULT_KB,
    load_json,
    validate_candidates,
)


def _inputs():
    return (
        load_json(DEFAULT_CANDIDATES),
        load_json(DEFAULT_KB),
        load_json(DEFAULT_CORPUS),
        load_json(DEFAULT_EVALUATION),
    )


def test_selected_amendment_case_is_linked_and_verified():
    assert validate_candidates(*_inputs()) == []


def test_unknown_impacted_concept_is_rejected():
    payload, kb, corpus, evaluation = _inputs()
    broken = deepcopy(payload)
    broken["candidates"][0]["impacted_concept_ids"] = ["missing-concept"]
    assert any("unknown concept_id" in error for error in validate_candidates(broken, kb, corpus, evaluation))


def test_non_official_source_is_rejected():
    payload, kb, corpus, evaluation = _inputs()
    broken = deepcopy(payload)
    broken["candidates"][0]["official_sources"]["after_text_url"] = "https://example.com/law"
    assert any("not an official law.go.kr URL" in error for error in validate_candidates(broken, kb, corpus, evaluation))


def test_after_text_must_match_current_corpus():
    payload, kb, corpus, evaluation = _inputs()
    broken = deepcopy(payload)
    broken["candidates"][0]["after"]["text"] = "존재하지 않는 개정 조문"
    assert any("does not exactly match current corpus" in error for error in validate_candidates(broken, kb, corpus, evaluation))
