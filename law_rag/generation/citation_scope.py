from __future__ import annotations

from dataclasses import dataclass

from law_rag.domain.models import SearchResult
from law_rag.generation.article_refs import extract_article_refs


@dataclass(frozen=True)
class CitationScope:
    direct_articles: tuple[str, ...]
    referenced_articles: tuple[str, ...]
    graph_articles: tuple[str, ...]

    @property
    def allowed_articles(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.direct_articles) | set(self.referenced_articles) | set(self.graph_articles)))

    def classify(self, article: str) -> str | None:
        if article in self.direct_articles:
            return "direct"
        if article in self.referenced_articles:
            return "referenced"
        if article in self.graph_articles:
            return "graph"
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "direct_articles": list(self.direct_articles),
            "referenced_articles": list(self.referenced_articles),
            "graph_articles": list(self.graph_articles),
            "allowed_articles": list(self.allowed_articles),
        }


def build_citation_scope(results: list[SearchResult]) -> CitationScope:
    """Build a provenance-aware citation allowlist.

    Direct/planned results are primary evidence. Related results are graph evidence.
    Article references appearing inside official evidence text are treated as referenced
    citations, not hallucinations, even when the referenced article was not separately
    retrieved as its own SearchResult.
    """
    direct: set[str] = set()
    graph: set[str] = set()
    referenced: set[str] = set()

    for result in results:
        article = result.provision.article_no.replace(" ", "")
        if result.retrieval_reason == "related":
            graph.add(article)
        else:
            direct.add(article)

        referenced.update(extract_article_refs(result.provision.text))
        for sub in result.sub_provisions:
            referenced.update(extract_article_refs(str(sub.get("text", ""))))
            referenced.update(extract_article_refs(str(sub.get("citation", ""))))

    referenced.difference_update(direct)
    referenced.difference_update(graph)
    return CitationScope(
        direct_articles=tuple(sorted(direct)),
        referenced_articles=tuple(sorted(referenced)),
        graph_articles=tuple(sorted(graph)),
    )
