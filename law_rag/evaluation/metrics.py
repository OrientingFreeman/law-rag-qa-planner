from __future__ import annotations

from dataclasses import dataclass

from law_rag.domain.models import SearchResult


@dataclass(slots=True)
class RetrievalEvaluation:
    query: str
    expected_document_ids: list[str]
    retrieved_document_ids: list[str]
    top1_hit: bool
    hit_at_k: bool
    reciprocal_rank: float

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "expected_document_ids": self.expected_document_ids,
            "retrieved_document_ids": self.retrieved_document_ids,
            "top1_hit": self.top1_hit,
            "hit_at_k": self.hit_at_k,
            "reciprocal_rank": self.reciprocal_rank,
        }


def evaluate_results(
    query: str,
    results: list[SearchResult],
    expected_document_ids: list[str],
) -> RetrievalEvaluation:
    retrieved = [result.provision.document_id for result in results]
    expected = set(expected_document_ids)
    first_relevant_rank = next((i for i, doc_id in enumerate(retrieved, 1) if doc_id in expected), None)
    return RetrievalEvaluation(
        query=query,
        expected_document_ids=expected_document_ids,
        retrieved_document_ids=retrieved,
        top1_hit=bool(retrieved and retrieved[0] in expected),
        hit_at_k=bool(expected.intersection(retrieved)),
        reciprocal_rank=1 / first_relevant_rank if first_relevant_rank else 0.0,
    )
