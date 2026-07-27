from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class LegalProvision:
    """Domain-neutral normalized representation of a legal provision."""

    document_id: str
    law_id: str
    law_name: str
    article_no: str
    text: str
    document_type: str = "법령"
    article_title: str | None = None
    paragraph_no: str | None = None
    item_no: str | None = None
    subitem_no: str | None = None
    promulgation_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    revision_date: date | None = None
    is_current: bool = True
    authority: str = "법제처"
    reliability: str = "공식"
    source_url: str | None = None
    version_id: str = "current"
    domain_tags: list[str] = field(default_factory=list)
    topic: str | None = None
    keywords: list[str] = field(default_factory=list)
    related_article_ids: list[str] = field(default_factory=list)
    content_kind: str = "official_text"
    source_checked_at: date | None = None

    def citation_label(self) -> str:
        parts = [self.law_name, self.article_no]
        if self.paragraph_no:
            parts.append(self.paragraph_no)
        if self.item_no:
            parts.append(self.item_no)
        if self.subitem_no:
            parts.append(self.subitem_no)
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("promulgation_date", "effective_from", "effective_to", "revision_date", "source_checked_at"):
            value = result[key]
            result[key] = value.isoformat() if value else None
        return result


@dataclass(slots=True)
class SearchResult:
    provision: LegalProvision
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rank: int = 0
    retrieval_reason: str = "direct"
    relation_score: float = 0.0
    title_score: float = 0.0
    coverage_score: float = 0.0
    evidence_scope: str = "fragment"
    sub_provisions: list[dict[str, str]] = field(default_factory=list)
    ontology_score: float = 0.0
    issue_coverage_score: float = 0.0
    evidence_role: str = "supporting"
    issue_ids: list[str] = field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        metadata = self.provision.to_dict()
        metadata["clause_no"] = metadata.pop("paragraph_no")
        metadata["effective_date"] = metadata.pop("effective_from")
        metadata["content"] = metadata.pop("text")
        return {
            "score": self.score,
            "chunk": {
                "text": format_provision_text(self.provision),
                "metadata": metadata,
                "provision": self.provision,
            },
        }


def format_provision_text(provision: LegalProvision) -> str:
    lines = [
        f"법령명: {provision.law_name}",
        f"조문: {provision.article_no}",
    ]
    if provision.paragraph_no:
        lines.append(f"항: {provision.paragraph_no}")
    if provision.item_no:
        lines.append(f"호: {provision.item_no}")
    if provision.subitem_no:
        lines.append(f"목: {provision.subitem_no}")
    if provision.topic:
        lines.append(f"주제: {provision.topic}")
    if provision.effective_from:
        lines.append(f"시행일자: {provision.effective_from.isoformat()}")
    lines.append(f"내용: {provision.text}")
    return "\n".join(lines)
