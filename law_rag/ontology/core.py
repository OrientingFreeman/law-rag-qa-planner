from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable


@dataclass(frozen=True, slots=True)
class LegalConcept:
    concept_id: str
    label: str
    aliases: tuple[str, ...]
    category: str
    parent_id: str | None = None
    related_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OntologyMatch:
    concept_id: str
    label: str
    category: str
    matched_aliases: tuple[str, ...]
    confidence: float
    parent_id: str | None = None
    related_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OntologyRelation:
    source_id: str
    relation: str
    target_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class LegalOntology:
    """Deterministic, inspectable ontology for legal concepts and relations.

    This layer does not infer legal conclusions. It normalizes vocabulary shared by
    planning, retrieval, composition, and grounding so the same concept identifiers
    remain stable throughout the request lifecycle.
    """

    def __init__(self, concepts: Iterable[LegalConcept]) -> None:
        self._concepts = {concept.concept_id: concept for concept in concepts}
        self._validate()

    def _validate(self) -> None:
        for concept in self._concepts.values():
            if concept.parent_id and concept.parent_id not in self._concepts:
                raise ValueError(f"Unknown ontology parent: {concept.parent_id}")
            unknown = [item for item in concept.related_ids if item not in self._concepts]
            if unknown:
                raise ValueError(f"Unknown related concepts for {concept.concept_id}: {unknown}")

    def get(self, concept_id: str) -> LegalConcept | None:
        return self._concepts.get(concept_id)

    def concepts(self) -> tuple[LegalConcept, ...]:
        return tuple(self._concepts.values())

    def match_text(self, text: str, *, action_ids: Iterable[str] = ()) -> list[OntologyMatch]:
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        action_set = set(action_ids)
        matches: list[OntologyMatch] = []
        for concept in self._concepts.values():
            aliases = tuple(
                alias for alias in concept.aliases
                if alias.lower() in normalized
            )
            action_match = bool(action_set.intersection(concept.action_ids))
            if not aliases and not action_match:
                continue
            alias_strength = min(1.0, 0.62 + 0.12 * len(aliases)) if aliases else 0.0
            confidence = max(alias_strength, 0.55 if action_match else 0.0)
            if aliases and action_match:
                confidence = min(1.0, confidence + 0.1)
            matches.append(OntologyMatch(
                concept_id=concept.concept_id,
                label=concept.label,
                category=concept.category,
                matched_aliases=aliases,
                confidence=round(confidence, 4),
                parent_id=concept.parent_id,
                related_ids=concept.related_ids,
            ))
        matches.sort(key=lambda item: (-item.confidence, item.concept_id))
        return matches

    def expand(self, concept_ids: Iterable[str], *, include_parents: bool = True, include_related: bool = True) -> list[str]:
        expanded: list[str] = []
        for concept_id in concept_ids:
            concept = self.get(concept_id)
            if not concept:
                continue
            for candidate in (
                concept_id,
                concept.parent_id if include_parents else None,
                *(concept.related_ids if include_related else ()),
            ):
                if candidate and candidate not in expanded:
                    expanded.append(candidate)
        return expanded

    def relations_for(self, concept_ids: Iterable[str]) -> list[OntologyRelation]:
        relations: list[OntologyRelation] = []
        seen: set[tuple[str, str, str]] = set()
        for concept_id in concept_ids:
            concept = self.get(concept_id)
            if not concept:
                continue
            candidates: list[OntologyRelation] = []
            if concept.parent_id:
                candidates.append(OntologyRelation(concept_id, "is_a", concept.parent_id))
            candidates.extend(OntologyRelation(concept_id, "related_to", target) for target in concept.related_ids)
            for relation in candidates:
                key = (relation.source_id, relation.relation, relation.target_id)
                if key not in seen:
                    seen.add(key)
                    relations.append(relation)
        return relations

    def describe_matches(self, matches: Iterable[OntologyMatch]) -> dict[str, object]:
        rows = list(matches)
        ids = [row.concept_id for row in rows]
        return {
            "concepts": [row.to_dict() for row in rows],
            "expanded_concept_ids": self.expand(ids),
            "relations": [row.to_dict() for row in self.relations_for(ids)],
        }
