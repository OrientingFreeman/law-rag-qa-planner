from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from law_rag.domain.models import LegalProvision
from law_rag.retrieval.embedding import searchable_provision_text


DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


@dataclass(frozen=True, slots=True)
class RerankedProvision:
    provision: LegalProvision
    score: float
    original_rank: int


class ProvisionReranker(Protocol):
    model_name: str

    def rerank(
        self, query: str, provisions: Sequence[LegalProvision], *, top_k: int
    ) -> list[RerankedProvision]: ...


class CrossEncoderProvisionReranker:
    """Optional CrossEncoder adapter; imports model dependencies only when enabled."""

    def __init__(self, *, model_name: str = DEFAULT_RERANKER_MODEL, model: Any | None = None) -> None:
        if model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError("cross-encoder reranker에는 '.[ml]' 설치가 필요합니다.") from exc
            model = CrossEncoder(model_name)
        self.model_name = model_name
        self.model = model

    def rerank(
        self, query: str, provisions: Sequence[LegalProvision], *, top_k: int
    ) -> list[RerankedProvision]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        candidates = list(provisions)
        if not candidates:
            return []
        scores = self.model.predict(
            [(query, searchable_provision_text(row)) for row in candidates],
            show_progress_bar=False,
        )
        if len(scores) != len(candidates):
            raise ValueError("reranker returned a score count that does not match candidates")
        ranked = sorted(
            (
                RerankedProvision(provision=row, score=float(score), original_rank=index + 1)
                for index, (row, score) in enumerate(zip(candidates, scores))
            ),
            key=lambda item: (-item.score, item.original_rank),
        )
        return ranked[:top_k]
