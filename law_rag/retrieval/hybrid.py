from __future__ import annotations

import re
from datetime import date

from law_rag.domain.config import DomainConfig
from law_rag.domain.models import LegalProvision, SearchResult
from law_rag.retrieval.bm25 import BM25Retriever
from law_rag.retrieval.semantic import CharNgramSemanticRetriever
from law_rag.retrieval.tokenizer import char_ngrams, tokenize


_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "에", "에서", "의", "와", "과", "로", "으로",
    "때", "경우", "하나", "하는", "해야", "할", "수", "있는가", "되는가", "어떤", "무엇",
    "얼마", "동안", "몇", "일", "전에", "대하여", "관한", "사항", "요건",
}


def _normalize(scores: list[float]) -> list[float]:
    if not scores:
        return []
    highest = max(scores)
    return [score / highest if highest > 0 else 0.0 for score in scores]


def _cosine(left, right) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = sum(value * value for value in left.values()) ** 0.5
    right_norm = sum(value * value for value in right.values()) ** 0.5
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _query_terms(query: str) -> set[str]:
    return {token for token in tokenize(query) if len(token) >= 2 and token not in _STOPWORDS}


def _term_coverage(query: str, provision: LegalProvision) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    searchable = " ".join(filter(None, [provision.article_title, provision.text])).lower()
    matched = sum(1 for term in terms if term in searchable)
    return matched / len(terms)


def _title_score(query: str, provision: LegalProvision) -> float:
    if not provision.article_title:
        return 0.0
    return _cosine(char_ngrams(query, n=2), char_ngrams(provision.article_title, n=2))


def _is_heading_only(provision: LegalProvision) -> bool:
    if provision.article_title or provision.paragraph_no or provision.item_no or provision.subitem_no:
        return False
    text = provision.text.strip()
    return bool(re.match(r"^제?\d*장(?:\s|$)|^제?\d*절(?:\s|$)", text))


def _hierarchy_bonus(provision: LegalProvision) -> float:
    # Broad legal questions generally need the governing article/paragraph before a narrow item/subitem.
    if provision.subitem_no:
        return -0.035
    if provision.item_no:
        return -0.02
    if provision.paragraph_no:
        return 0.015
    return 0.025



def _article_anchor_bonus(query: str, provision: LegalProvision) -> float:
    anchors = set(re.findall(r"제\d+조(?:의\d+)?", query))
    if not anchors:
        return 0.0
    if provision.article_no not in anchors:
        return -0.015

    # An article number is not a cross-instrument foreign key. A query anchored to
    # the Act must not promote the same-numbered Enforcement Decree article unless
    # the decree is explicitly named.
    mentions_decree = "시행령" in query
    is_decree = "시행령" in provision.law_name or provision.document_type == "시행령"
    if is_decree and not mentions_decree:
        return -0.22
    if mentions_decree and not is_decree:
        return -0.08
    return 0.38


def _sanction_penalty(query: str, provision: LegalProvision) -> float:
    title = provision.article_title or ""
    asks_sanction = any(term in query for term in ("벌금", "징역", "처벌", "벌칙", "과태료", "제재"))
    if not asks_sanction and any(term in title for term in ("벌칙", "과태료", "양벌규정")):
        return -0.12
    return 0.0


class HybridRetriever:
    def __init__(self, provisions: list[LegalProvision]) -> None:
        self.provisions = provisions

    @staticmethod
    def expand_query(query: str, config: DomainConfig | None) -> str:
        if not config:
            return query
        expansions: list[str] = []
        for canonical, aliases in config.aliases.items():
            terms = [canonical, *aliases]
            if any(term.lower() in query.lower() for term in terms):
                expansions.extend(terms)
        lowered = query.lower()
        for rule in config.query_rules:
            triggers = [str(term).lower() for term in rule.get("all", [])]
            any_terms = [str(term).lower() for term in rule.get("any", [])]
            if triggers and not all(term in lowered for term in triggers):
                continue
            if any_terms and not any(term in lowered for term in any_terms):
                continue
            expansions.extend(str(term) for term in rule.get("expand", []))
        return " ".join([query, *dict.fromkeys(expansions)])

    @staticmethod
    def _in_force(provision: LegalProvision, as_of_date: date | None) -> bool:
        if not as_of_date:
            return provision.is_current
        if provision.effective_from and provision.effective_from > as_of_date:
            return False
        if provision.effective_to and provision.effective_to < as_of_date:
            return False
        return True

    def retrieve(
        self,
        query: str,
        *,
        domain: DomainConfig | None = None,
        top_k: int | None = None,
        as_of_date: date | None = None,
        include_related: bool = True,
        strategy: str = "hybrid",
        query_rewrite: bool = True,
    ) -> list[SearchResult]:
        candidates = [
            p for p in self.provisions
            if self._in_force(p, as_of_date)
            and (not domain or p.law_name in domain.laws or domain.domain_id in p.domain_tags)
        ]
        if not candidates:
            return []

        if strategy not in {"lexical", "semantic", "hybrid"}:
            raise ValueError(f"unsupported retrieval strategy: {strategy}")
        expanded_query = self.expand_query(query, domain) if query_rewrite else query
        lexical = _normalize(BM25Retriever(candidates).score(expanded_query))
        semantic = _normalize(CharNgramSemanticRetriever(candidates).score(expanded_query))
        if strategy == "lexical":
            lexical_weight, semantic_weight = 1.0, 0.0
        elif strategy == "semantic":
            lexical_weight, semantic_weight = 0.0, 1.0
        else:
            lexical_weight = domain.retrieval.lexical_weight if domain else 0.55
            semantic_weight = domain.retrieval.semantic_weight if domain else 0.45

        results = []
        for provision, lexical_score, semantic_score in zip(candidates, lexical, semantic):
            base_score = lexical_weight * lexical_score + semantic_weight * semantic_score
            title_score = _title_score(expanded_query, provision)
            coverage = _term_coverage(expanded_query, provision)
            score = (
                base_score * 0.76
                + title_score * 0.16
                + coverage * 0.08
                + _hierarchy_bonus(provision)
                + _sanction_penalty(query, provision)
                + _article_anchor_bonus(expanded_query, provision)
            )
            if _is_heading_only(provision):
                score *= 0.25
            results.append(SearchResult(
                provision=provision,
                score=max(0.0, min(1.0, score)),
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                title_score=title_score,
                coverage_score=coverage,
            ))

        results.sort(key=lambda result: result.score, reverse=True)
        limit = top_k or (domain.retrieval.top_k if domain else 5)

        # Prevent one article's item/subitem fragments from monopolizing Top-K.
        filtered: list[SearchResult] = []
        per_article: dict[tuple[str, str], int] = {}
        for result in results:
            if result.score <= 0:
                continue
            key = (result.provision.law_id, result.provision.article_no)
            if per_article.get(key, 0) >= 2:
                continue
            filtered.append(result)
            per_article[key] = per_article.get(key, 0) + 1
            if len(filtered) >= limit:
                break

        if include_related and filtered:
            by_id = {p.document_id: p for p in candidates}
            score_by_id = {r.provision.document_id: r for r in results}
            included = {r.provision.document_id for r in filtered}
            related_results: list[SearchResult] = []
            for parent in list(filtered):
                for related_id in parent.provision.related_article_ids:
                    provision = by_id.get(related_id)
                    if not provision or related_id in included:
                        continue
                    baseline = score_by_id.get(related_id)
                    lexical_score = baseline.lexical_score if baseline else 0.0
                    semantic_score = baseline.semantic_score if baseline else 0.0
                    query_relevance = baseline.score if baseline else 0.0
                    relation_score = max(parent.score * 0.35, 0.0001)
                    final_score = min(1.0, query_relevance * 0.65 + relation_score)
                    related_results.append(SearchResult(
                        provision=provision,
                        score=final_score,
                        lexical_score=lexical_score,
                        semantic_score=semantic_score,
                        retrieval_reason="related",
                        relation_score=relation_score,
                        title_score=baseline.title_score if baseline else 0.0,
                        coverage_score=baseline.coverage_score if baseline else 0.0,
                    ))
                    included.add(related_id)
            filtered.extend(related_results)
            filtered.sort(key=lambda result: result.score, reverse=True)

        for rank, result in enumerate(filtered, start=1):
            result.rank = rank
        return filtered
