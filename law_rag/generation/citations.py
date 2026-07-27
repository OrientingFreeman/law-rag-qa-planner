from __future__ import annotations

import re

from law_rag.domain.models import SearchResult
from law_rag.generation.article_refs import extract_article_refs
from law_rag.generation.citation_scope import build_citation_scope

_CIRCLED = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10}


def normalize_citation_label(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label).strip()
    for symbol, number in _CIRCLED.items():
        normalized = normalized.replace(symbol, f"제{number}항")
    normalized = re.sub(r"(?<!제)(\d+(?:의\d+)?)호", r"제\1호", normalized)
    return normalized


def validate_citations(answer: str, results: list[SearchResult]) -> dict[str, object]:
    cited = set(extract_article_refs(answer))
    scope = build_citation_scope(results)
    allowed = set(scope.allowed_articles)
    unsupported = sorted(cited - allowed)
    citation_scopes = {
        article: scope.classify(article) or "unsupported"
        for article in sorted(cited)
    }
    return {
        "valid": not unsupported,
        "cited_articles": sorted(cited),
        # Backward-compatible field: all articles accepted by the validator.
        "retrieved_articles": sorted(allowed),
        "unsupported_articles": unsupported,
        "citation_scopes": citation_scopes,
        "scope": scope.to_dict(),
    }
