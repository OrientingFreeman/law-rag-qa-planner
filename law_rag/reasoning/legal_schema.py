from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "0.1.0"
ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]*$")


class NodeType(str, Enum):
    CLAIM = "claim"
    CAUSE_OF_ACTION = "cause_of_action"
    ELEMENT = "element"
    DEFENSE = "defense"
    COUNTER_DEFENSE = "counter_defense"
    BURDEN_OF_PLEADING = "burden_of_pleading"
    BURDEN_OF_PROOF = "burden_of_proof"
    FACT_REQUIREMENT = "fact_requirement"
    EVIDENCE_TYPE = "evidence_type"
    FOLLOW_UP_QUESTION = "follow_up_question"
    LEGAL_BASIS = "legal_basis"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REVISE = "revise"
    REJECTED = "rejected"


class FactStatus(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNCERTAIN = "uncertain"
    MISSING = "missing"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_id: str
    source_type: str
    title: str
    edition: str | None = None
    chapter: str | None = None
    section: str | None = None
    page: str | None = None
    span: str | None = None
    uri: str | None = None
    note: str = ""

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SourceProvenance":
        return cls(**row)


@dataclass(frozen=True, slots=True)
class ExternalReference:
    reference_id: str
    reference_type: str
    label: str = ""

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ExternalReference":
        return cls(**row)


@dataclass(frozen=True, slots=True)
class ReasoningNode:
    node_id: str
    node_type: NodeType
    label: str
    description: str = ""
    review_status: ReviewStatus = ReviewStatus.REVIEW_REQUIRED
    provenance: tuple[SourceProvenance, ...] = ()
    fact_status: FactStatus | None = None
    burden_holder: str | None = None
    question_template: str | None = None
    statute_references: tuple[ExternalReference, ...] = ()
    case_references: tuple[ExternalReference, ...] = ()
    ontology_concept_ids: tuple[str, ...] = ()
    evidence_references: tuple[ExternalReference, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ReasoningNode":
        payload = dict(row)
        payload["node_type"] = NodeType(payload["node_type"])
        payload["review_status"] = ReviewStatus(payload.get("review_status", ReviewStatus.REVIEW_REQUIRED))
        if payload.get("fact_status") is not None:
            payload["fact_status"] = FactStatus(payload["fact_status"])
        payload["provenance"] = tuple(SourceProvenance.from_dict(item) for item in payload.get("provenance", []))
        for key in ("statute_references", "case_references", "evidence_references"):
            payload[key] = tuple(ExternalReference.from_dict(item) for item in payload.get(key, []))
        payload["ontology_concept_ids"] = tuple(payload.get("ontology_concept_ids", []))
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class ReasoningRelation:
    relation_id: str
    source_id: str
    relation_type: str
    target_id: str
    description: str = ""

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ReasoningRelation":
        return cls(**row)


ALLOWED_RELATIONS: dict[str, set[tuple[NodeType, NodeType]]] = {
    "has_cause_of_action": {(NodeType.CLAIM, NodeType.CAUSE_OF_ACTION)},
    "requires_element": {
        (NodeType.CAUSE_OF_ACTION, NodeType.ELEMENT),
        (NodeType.DEFENSE, NodeType.ELEMENT),
        (NodeType.COUNTER_DEFENSE, NodeType.ELEMENT),
    },
    "defeats": {
        (NodeType.DEFENSE, NodeType.CLAIM),
        (NodeType.DEFENSE, NodeType.CAUSE_OF_ACTION),
        (NodeType.DEFENSE, NodeType.ELEMENT),
        (NodeType.COUNTER_DEFENSE, NodeType.DEFENSE),
    },
    "requires_fact": {(NodeType.ELEMENT, NodeType.FACT_REQUIREMENT)},
    "supported_by_type": {(NodeType.FACT_REQUIREMENT, NodeType.EVIDENCE_TYPE)},
    "clarified_by": {(NodeType.FACT_REQUIREMENT, NodeType.FOLLOW_UP_QUESTION)},
    "governed_by": {
        (NodeType.CLAIM, NodeType.LEGAL_BASIS),
        (NodeType.CAUSE_OF_ACTION, NodeType.LEGAL_BASIS),
        (NodeType.ELEMENT, NodeType.LEGAL_BASIS),
        (NodeType.DEFENSE, NodeType.LEGAL_BASIS),
        (NodeType.COUNTER_DEFENSE, NodeType.LEGAL_BASIS),
    },
    "pleading_burden_for": {(NodeType.BURDEN_OF_PLEADING, item) for item in (NodeType.CLAIM, NodeType.CAUSE_OF_ACTION, NodeType.ELEMENT, NodeType.DEFENSE, NodeType.COUNTER_DEFENSE)},
    "proof_burden_for": {(NodeType.BURDEN_OF_PROOF, item) for item in (NodeType.CLAIM, NodeType.CAUSE_OF_ACTION, NodeType.ELEMENT, NodeType.DEFENSE, NodeType.COUNTER_DEFENSE)},
}


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LegalReasoningSchema:
    schema_version: str
    knowledge_id: str
    domain: str
    title: str
    nodes: tuple[ReasoningNode, ...]
    relations: tuple[ReasoningRelation, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        errors: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errors.append(f"unsupported schema_version: {self.schema_version}")
        if not ID_RE.fullmatch(self.knowledge_id):
            errors.append(f"invalid knowledge_id: {self.knowledge_id}")

        nodes: dict[str, ReasoningNode] = {}
        for node in self.nodes:
            if not ID_RE.fullmatch(node.node_id):
                errors.append(f"invalid node_id: {node.node_id}")
            if node.node_id in nodes:
                errors.append(f"duplicate node_id: {node.node_id}")
            nodes[node.node_id] = node
            if node.review_status == ReviewStatus.APPROVED and not node.provenance:
                errors.append(f"approved node lacks provenance: {node.node_id}")
            if node.node_type == NodeType.FOLLOW_UP_QUESTION and not node.question_template:
                errors.append(f"follow-up question lacks template: {node.node_id}")
            if node.fact_status is not None and node.node_type != NodeType.FACT_REQUIREMENT:
                errors.append(f"fact_status is only valid on fact requirements: {node.node_id}")
            if node.node_type in {NodeType.BURDEN_OF_PLEADING, NodeType.BURDEN_OF_PROOF} and not node.burden_holder:
                errors.append(f"burden node lacks burden_holder: {node.node_id}")

        relation_ids: set[str] = set()
        relation_keys: set[tuple[str, str, str]] = set()
        for relation in self.relations:
            if not ID_RE.fullmatch(relation.relation_id):
                errors.append(f"invalid relation_id: {relation.relation_id}")
            if relation.relation_id in relation_ids:
                errors.append(f"duplicate relation_id: {relation.relation_id}")
            relation_ids.add(relation.relation_id)
            source = nodes.get(relation.source_id)
            target = nodes.get(relation.target_id)
            if source is None:
                errors.append(f"unknown source node: {relation.source_id}")
            if target is None:
                errors.append(f"unknown target node: {relation.target_id}")
            key = (relation.source_id, relation.relation_type, relation.target_id)
            if key in relation_keys:
                errors.append(f"duplicate relation: {key}")
            relation_keys.add(key)
            allowed = ALLOWED_RELATIONS.get(relation.relation_type)
            if allowed is None:
                errors.append(f"unknown relation_type: {relation.relation_type}")
            elif source is not None and target is not None and (source.node_type, target.node_type) not in allowed:
                errors.append(
                    f"invalid relation endpoints for {relation.relation_id}: "
                    f"{source.node_type.value}->{target.node_type.value}"
                )

        claim_ids = {node.node_id for node in self.nodes if node.node_type == NodeType.CLAIM}
        cause_ids = {node.node_id for node in self.nodes if node.node_type == NodeType.CAUSE_OF_ACTION}
        linked_claims = {row.source_id for row in self.relations if row.relation_type == "has_cause_of_action"}
        linked_causes = {row.target_id for row in self.relations if row.relation_type == "has_cause_of_action"}
        if claim_ids - linked_claims:
            errors.append(f"claims without cause of action: {sorted(claim_ids - linked_claims)}")
        if cause_ids - linked_causes:
            errors.append(f"orphan causes of action: {sorted(cause_ids - linked_causes)}")
        if errors:
            raise SchemaValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        self.validate()
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent) + "\n"

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "LegalReasoningSchema":
        schema = cls(
            schema_version=str(row["schema_version"]),
            knowledge_id=str(row["knowledge_id"]),
            domain=str(row["domain"]),
            title=str(row["title"]),
            nodes=tuple(ReasoningNode.from_dict(item) for item in row.get("nodes", [])),
            relations=tuple(ReasoningRelation.from_dict(item) for item in row.get("relations", [])),
            metadata=dict(row.get("metadata", {})),
        )
        schema.validate()
        return schema

    @classmethod
    def from_json(cls, payload: str) -> "LegalReasoningSchema":
        row = json.loads(payload)
        if not isinstance(row, dict):
            raise SchemaValidationError("schema document must be a JSON object")
        return cls.from_dict(row)

    @classmethod
    def load_json(cls, path: str | Path) -> "LegalReasoningSchema":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def dump_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


def validate_many(schemas: Iterable[LegalReasoningSchema]) -> None:
    knowledge_ids: set[str] = set()
    for schema in schemas:
        schema.validate()
        if schema.knowledge_id in knowledge_ids:
            raise SchemaValidationError(f"duplicate knowledge_id: {schema.knowledge_id}")
        knowledge_ids.add(schema.knowledge_id)
