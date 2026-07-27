from law_rag.ontology import DEFAULT_LEGAL_ONTOLOGY, LegalConcept, LegalOntology
from law_rag.planning import LegalIntentPlanner


def test_ontology_matches_concepts_and_expands_relations():
    matches = DEFAULT_LEGAL_ONTOLOGY.match_text("위탁업무 목적 외 개인정보 처리를 금지하고 기술적·관리적 보호조치를 둔다")
    ids = {match.concept_id for match in matches}
    assert "processing_delegation" in ids
    assert "purpose_limitation" in ids
    assert "security_measures" in ids

    view = DEFAULT_LEGAL_ONTOLOGY.describe_matches(matches)
    assert "safeguards" in view["expanded_concept_ids"]
    assert any(
        row["source_id"] == "security_measures" and row["relation"] == "is_a"
        for row in view["relations"]
    )


def test_planner_exposes_shared_ontology_contract():
    plan = LegalIntentPlanner().plan("개인정보 처리위탁 계약서에 목적과 재위탁 제한을 어떻게 적어야 하나?")
    ids = {row["concept_id"] for row in plan.ontology["concepts"]}
    assert "processing_delegation" in ids
    assert "purpose_and_scope" in ids
    assert "subcontracting" in ids
    assert "processing_delegation" in plan.ontology["expanded_concept_ids"]


def test_ontology_rejects_unknown_relation_targets():
    try:
        LegalOntology((LegalConcept("a", "A", ("a",), "test", parent_id="missing"),))
    except ValueError as exc:
        assert "Unknown ontology parent" in str(exc)
    else:
        raise AssertionError("invalid ontology should fail fast")


def test_definition_intent_is_detected():
    plan = LegalIntentPlanner().plan("개인정보의 처리위탁이란 무엇인가?")
    assert "definition" in plan.requested_outputs
