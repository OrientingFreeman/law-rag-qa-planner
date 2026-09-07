from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_rag.reasoning.legal_schema import (
    LegalReasoningSchema,
    SchemaValidationError,
)


FIXTURE = Path("examples/legal_reasoning/loan_repayment_claim.v0.json")


def _raw() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_loan_repayment_pilot_is_valid_and_covers_vertical_slice() -> None:
    schema = LegalReasoningSchema.load_json(FIXTURE)
    schema.validate()

    node_types = {node.node_type.value for node in schema.nodes}
    assert {
        "claim", "cause_of_action", "element", "defense", "counter_defense",
        "burden_of_pleading", "burden_of_proof", "fact_requirement",
        "evidence_type", "follow_up_question", "legal_basis",
    } <= node_types
    relation_types = {relation.relation_type for relation in schema.relations}
    assert {"has_cause_of_action", "requires_element", "defeats"} <= relation_types
    assert all(node.provenance for node in schema.nodes)


def test_json_round_trip_is_deterministic() -> None:
    first = LegalReasoningSchema.load_json(FIXTURE)
    encoded = first.to_json()
    second = LegalReasoningSchema.from_json(encoded)
    assert second == first
    assert second.to_json() == encoded


@pytest.mark.parametrize("field", ["source_id", "target_id"])
def test_dangling_internal_reference_is_rejected(field: str) -> None:
    row = _raw()
    row["relations"][0][field] = "missing.node"
    with pytest.raises(SchemaValidationError, match="unknown .* node"):
        LegalReasoningSchema.from_dict(row)


def test_duplicate_node_and_relation_ids_are_rejected() -> None:
    row = _raw()
    row["nodes"].append(dict(row["nodes"][0]))
    row["relations"].append(dict(row["relations"][0]))
    with pytest.raises(SchemaValidationError, match="duplicate node_id"):
        LegalReasoningSchema.from_dict(row)


def test_invalid_relation_endpoint_types_are_rejected() -> None:
    row = _raw()
    row["relations"][0] = {
        "relation_id": "rel.invalid",
        "relation_type": "has_cause_of_action",
        "source_id": "defense.payment",
        "target_id": "cause.loan_contract_return",
    }
    with pytest.raises(SchemaValidationError, match="invalid relation endpoints"):
        LegalReasoningSchema.from_dict(row)


def test_approved_node_requires_provenance() -> None:
    row = _raw()
    row["nodes"][0]["review_status"] = "approved"
    row["nodes"][0]["provenance"] = []
    with pytest.raises(SchemaValidationError, match="approved node lacks provenance"):
        LegalReasoningSchema.from_dict(row)
