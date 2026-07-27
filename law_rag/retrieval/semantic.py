from __future__ import annotations

import math
from collections import Counter

from law_rag.domain.models import LegalProvision
from law_rag.retrieval.tokenizer import char_ngrams


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class CharNgramSemanticRetriever:
    """Dependency-free semantic-lite baseline; replaceable with an embedding adapter."""

    def __init__(self, provisions: list[LegalProvision], n: int = 2) -> None:
        self.provisions = provisions
        self.n = n
        self.vectors = [char_ngrams(self._searchable_text(p), n=n) for p in provisions]

    @staticmethod
    def _searchable_text(p: LegalProvision) -> str:
        return " ".join(filter(None, [p.law_name, p.article_no, p.article_title, p.topic, *p.keywords, p.text]))

    def score(self, query: str) -> list[float]:
        query_vector = char_ngrams(query, n=self.n)
        return [_cosine(query_vector, vector) for vector in self.vectors]
