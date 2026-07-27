from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from law_rag.domain.models import LegalProvision, SearchResult

ARTICLE_RE = re.compile(r"제\s*(\d+(?:의\d+)?)\s*조")


def article_key(provision: LegalProvision) -> str:
    return f"{provision.law_id}:{provision.article_no}"


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float


class LawGraph:
    """Article-level graph built from explicit statutory references and metadata."""

    def __init__(self, provisions: list[LegalProvision]) -> None:
        self.provisions = provisions
        self.by_article: dict[str, list[LegalProvision]] = defaultdict(list)
        self.edges: dict[str, list[GraphEdge]] = defaultdict(list)
        for provision in provisions:
            self.by_article[article_key(provision)].append(provision)
        self._build()

    def _build(self) -> None:
        seen: set[tuple[str, str, str]] = set()
        for provision in self.provisions:
            source = article_key(provision)
            targets: list[tuple[str, str, float]] = []
            for raw in provision.related_article_ids:
                target = self._normalize_related_id(provision, raw)
                if target:
                    targets.append((target, "metadata_reference", 1.0))
            for number in ARTICLE_RE.findall(provision.text):
                target = f"{provision.law_id}:제{number}조"
                if target != source and target in self.by_article:
                    targets.append((target, "explicit_reference", 0.9))
            for target, relation, weight in targets:
                marker = (source, target, relation)
                if marker in seen:
                    continue
                seen.add(marker)
                self.edges[source].append(GraphEdge(source, target, relation, weight))

    def _normalize_related_id(self, provision: LegalProvision, raw: str) -> str | None:
        value = str(raw).strip()
        if value in self.by_article:
            return value
        match = ARTICLE_RE.search(value)
        if match:
            candidate = f"{provision.law_id}:제{match.group(1)}조"
            return candidate if candidate in self.by_article else None
        return None

    def expand(
        self,
        seeds: list[SearchResult],
        *,
        max_hops: int = 2,
        limit: int = 5,
    ) -> list[SearchResult]:
        if not seeds or limit <= 0:
            return []
        seed_keys = {article_key(result.provision) for result in seeds}
        best: dict[str, tuple[float, str, int]] = {}
        queue: deque[tuple[str, float, int]] = deque(
            (article_key(result.provision), max(result.score, 0.01), 0) for result in seeds
        )
        while queue:
            current, base_score, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for edge in self.edges.get(current, []):
                score = base_score * edge.weight * (0.82 ** depth)
                previous = best.get(edge.target)
                if edge.target not in seed_keys and (previous is None or score > previous[0]):
                    best[edge.target] = (score, edge.relation, depth + 1)
                if previous is None or score > previous[0]:
                    queue.append((edge.target, score, depth + 1))

        expanded: list[SearchResult] = []
        for target, (score, relation, _depth) in sorted(best.items(), key=lambda item: item[1][0], reverse=True)[:limit]:
            candidates = self.by_article.get(target, [])
            if not candidates:
                continue
            provision = sorted(candidates, key=lambda p: (p.paragraph_no is None, p.document_id))[0]
            expanded.append(SearchResult(
                provision=provision,
                score=round(min(score, 0.99), 4),
                rank=0,
                retrieval_reason="related",
                relation_score=round(min(score, 1.0), 4),
                evidence_scope="paragraph" if provision.paragraph_no else "article",
            ))
        return expanded


class ReasoningChainBuilder:
    def build(self, direct: list[SearchResult], expanded: list[SearchResult]) -> list[dict[str, object]]:
        chain: list[dict[str, object]] = []
        seen: set[str] = set()
        for result in [*direct, *expanded]:
            key = article_key(result.provision)
            if key in seen:
                continue
            seen.add(key)
            chain.append({
                "step": len(chain) + 1,
                "citation": result.provision.citation_label(),
                "document_id": result.provision.document_id,
                "law_id": result.provision.law_id,
                "article_no": result.provision.article_no,
                "reason": "질문과 직접 일치하는 핵심 근거" if result.retrieval_reason == "direct" else "핵심 조문이 명시적으로 참조하는 연계 근거",
                "relation": result.retrieval_reason,
                "score": round(result.score, 4),
            })
        return chain
