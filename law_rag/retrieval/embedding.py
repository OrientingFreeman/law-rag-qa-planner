from __future__ import annotations

import math
from typing import Any, Sequence

from law_rag.domain.models import LegalProvision


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def searchable_provision_text(provision: LegalProvision) -> str:
    return " ".join(filter(None, [
        provision.law_name,
        provision.article_no,
        provision.article_title,
        provision.topic,
        *provision.keywords,
        provision.text,
    ]))


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    denominator = math.sqrt(_dot(left, left)) * math.sqrt(_dot(right, right))
    return _dot(left, right) / denominator if denominator else 0.0


class SentenceTransformerEmbeddingRetriever:
    """Optional real embedding retriever backed by Sentence Transformers.

    The model is injected in tests and imported lazily in production so the core
    application remains dependency-light. Document vectors are built once and
    reused for every benchmark query.
    """

    def __init__(
        self,
        provisions: list[LegalProvision],
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        model: Any | None = None,
    ) -> None:
        if model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "pretrained embedding benchmark에는 '.[ml]' 설치가 필요합니다."
                ) from exc
            model = SentenceTransformer(model_name)
        self.provisions = provisions
        self.model_name = model_name
        self.model = model
        self.vectors = self._encode([searchable_provision_text(row) for row in provisions])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [list(map(float, row)) for row in encoded]

    def score(self, query: str) -> list[float]:
        query_vector = self._encode([query])[0]
        # normalize_embeddings makes dot product sufficient, while cosine keeps
        # injected or third-party compatible models correct as well.
        return [_cosine(query_vector, vector) for vector in self.vectors]
