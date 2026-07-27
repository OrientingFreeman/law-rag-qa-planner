from __future__ import annotations

import math
from collections import Counter

from law_rag.domain.models import LegalProvision
from law_rag.retrieval.tokenizer import tokenize


class BM25Retriever:
    def __init__(self, provisions: list[LegalProvision], k1: float = 1.5, b: float = 0.75) -> None:
        self.provisions = provisions
        self.k1 = k1
        self.b = b
        self.documents = [tokenize(self._searchable_text(p)) for p in provisions]
        self.doc_freq: Counter[str] = Counter()
        for document in self.documents:
            self.doc_freq.update(set(document))
        self.avgdl = sum(map(len, self.documents)) / len(self.documents) if self.documents else 0.0

    @staticmethod
    def _searchable_text(p: LegalProvision) -> str:
        return " ".join(
            filter(None, [p.law_name, p.article_no, p.article_title, p.topic, *p.keywords, p.text])
        )

    def score(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        total_docs = len(self.documents)
        scores: list[float] = []
        for document in self.documents:
            frequencies = Counter(document)
            doc_len = len(document)
            score = 0.0
            for token in query_tokens:
                df = self.doc_freq[token]
                if not df:
                    continue
                idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                tf = frequencies[token]
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
                score += idf * (tf * (self.k1 + 1) / denominator) if denominator else 0.0
            scores.append(score)
        return scores
