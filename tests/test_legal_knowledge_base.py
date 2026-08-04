from copy import deepcopy

from tools.validate_legal_knowledge_base import DEFAULT_CORPUS, DEFAULT_KB, load_json, validate_knowledge_base


def _fixtures():
    return load_json(DEFAULT_KB), load_json(DEFAULT_CORPUS)


def test_legal_knowledge_base_has_41_reviewed_concepts():
    kb, corpus = _fixtures()
    assert len(kb["concepts"]) == 41
    assert {row["annotation_status"] for row in kb["concepts"]} == {"reviewed"}
    assert validate_knowledge_base(kb, corpus) == []


def test_legal_knowledge_base_covers_all_supported_laws():
    kb, _ = _fixtures()
    assert {row["law_id"] for row in kb["concepts"]} == {"011357", "011468", "010199", "001872", "001706"}


def test_duplicate_concept_id_is_rejected():
    kb, corpus = _fixtures()
    broken = deepcopy(kb)
    broken["concepts"][1]["concept_id"] = broken["concepts"][0]["concept_id"]
    assert any("duplicate concept_id" in e for e in validate_knowledge_base(broken, corpus))


def test_dangling_article_reference_is_rejected():
    kb, corpus = _fixtures()
    broken = deepcopy(kb)
    broken["concepts"][0]["article_refs"] = ["제999조"]
    assert any("corpus article not found" in e for e in validate_knowledge_base(broken, corpus))


def test_invalid_effective_period_is_rejected():
    kb, corpus = _fixtures()
    broken = deepcopy(kb)
    broken["concepts"][0]["effective_to"] = "2025-01-01"
    assert any("effective_to precedes" in e for e in validate_knowledge_base(broken, corpus))
