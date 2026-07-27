from __future__ import annotations

from dataclasses import replace
import re

from law_rag.domain.models import LegalProvision, SearchResult


def _group_key(provision: LegalProvision) -> tuple[str, str, str | None]:
    """Aggregate item/subitem fragments at article-paragraph evidence scope."""
    return (provision.law_id, provision.article_no, provision.paragraph_no)


def _legal_number(value: str | None) -> tuple[int, int, str]:
    if not value:
        return (0, 0, "")
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    return (numbers[0] if numbers else 0, numbers[1] if len(numbers) > 1 else 0, value)


def _sort_key(provision: LegalProvision) -> tuple[int, tuple[int, int, str], tuple[int, int, str]]:
    return (
        0 if not provision.item_no and not provision.subitem_no else 1,
        _legal_number(provision.item_no),
        _legal_number(provision.subitem_no),
    )


def aggregate_evidence(
    results: list[SearchResult],
    corpus: list[LegalProvision],
    *,
    limit: int | None = None,
) -> list[SearchResult]:
    """Collapse ranked fragments into unique legal evidence units.

    A hit on an item or subitem is promoted to its article/paragraph scope and
    sibling items are attached so answer generation receives the complete list
    rather than an isolated fragment.
    """
    if not results:
        return []

    siblings: dict[tuple[str, str, str | None], list[LegalProvision]] = {}
    for provision in corpus:
        siblings.setdefault(_group_key(provision), []).append(provision)

    aggregated: list[SearchResult] = []
    seen: set[tuple[str, str, str | None]] = set()
    max_results = limit or len(results)

    for result in results:
        key = _group_key(result.provision)
        if key in seen:
            continue
        seen.add(key)

        group = sorted(siblings.get(key, [result.provision]), key=_sort_key)
        parent = next(
            (item for item in group if not item.item_no and not item.subitem_no),
            None,
        )
        representative = parent or result.provision

        child_rows = [
            item for item in group
            if item.item_no or item.subitem_no
        ]
        text_parts: list[str] = []
        if parent and parent.text.strip():
            text_parts.append(parent.text.strip())
        for item in child_rows:
            text = item.text.strip()
            if text and text not in text_parts:
                text_parts.append(text)

        should_aggregate = bool(child_rows)
        if should_aggregate:
            merged = replace(
                representative,
                document_id=(
                    f"{representative.law_id}:{representative.article_no}"
                    + (f":{representative.paragraph_no}" if representative.paragraph_no else "")
                ),
                item_no=None,
                subitem_no=None,
                text="\n".join(text_parts) or representative.text,
            )
            scope = "paragraph" if merged.paragraph_no else "article"
        else:
            merged = result.provision
            scope = "fragment"
        aggregated.append(SearchResult(
            provision=merged,
            score=result.score,
            lexical_score=result.lexical_score,
            semantic_score=result.semantic_score,
            rank=len(aggregated) + 1,
            retrieval_reason=result.retrieval_reason,
            relation_score=result.relation_score,
            title_score=result.title_score,
            coverage_score=result.coverage_score,
            evidence_scope=scope,
            ontology_score=result.ontology_score,
            issue_coverage_score=result.issue_coverage_score,
            evidence_role=result.evidence_role,
            issue_ids=list(result.issue_ids),
            sub_provisions=[
                {
                    "document_id": item.document_id,
                    "citation": item.citation_label(),
                    "text": item.text,
                }
                for item in child_rows
            ] if should_aggregate else [],
        ))
        if len(aggregated) >= max_results:
            break

    return aggregated
