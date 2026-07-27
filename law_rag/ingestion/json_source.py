from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from law_rag.domain.models import LegalProvision


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", value).strip("-")
    return cleaned.lower() or "unknown"


class JsonLegalDocumentSource:
    """Adapter for legacy and normalized JSON legal datasets."""

    def load(self, path: str | Path) -> list[LegalProvision]:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            raise ValueError("법령 JSON의 최상위 값은 배열이어야 합니다.")
        return [self.normalize(record, index) for index, record in enumerate(records)]

    def normalize(self, record: dict[str, Any], index: int) -> LegalProvision:
        law_name = record["law_name"]
        article_no = record["article_no"]
        paragraph_no = record.get("paragraph_no", record.get("clause_no"))
        effective_from = record.get("effective_from", record.get("effective_date"))
        text = record.get("text", record.get("content"))
        if not text:
            raise ValueError(f"{law_name} {article_no}: text/content가 없습니다.")

        law_id = record.get("law_id") or _slug(law_name)
        document_id = record.get("document_id") or ":".join(
            filter(None, [law_id, article_no, paragraph_no, record.get("item_no"), str(index)])
        )

        return LegalProvision(
            document_id=document_id,
            law_id=law_id,
            law_name=law_name,
            article_no=article_no,
            article_title=record.get("article_title"),
            paragraph_no=paragraph_no,
            item_no=record.get("item_no"),
            subitem_no=record.get("subitem_no"),
            text=text,
            document_type=record.get("document_type", "법령"),
            promulgation_date=_parse_date(record.get("promulgation_date")),
            effective_from=_parse_date(effective_from),
            effective_to=_parse_date(record.get("effective_to")),
            revision_date=_parse_date(record.get("revision_date")),
            is_current=record.get("is_current", True),
            authority=record.get("authority", "법제처"),
            reliability=record.get("reliability", "공식"),
            source_url=record.get("source_url"),
            version_id=record.get("version_id", "current"),
            domain_tags=record.get("domain_tags", []),
            topic=record.get("topic"),
            keywords=record.get("keywords", []),
            related_article_ids=record.get("related_article_ids", []),
            content_kind=record.get("content_kind", "official_text"),
            source_checked_at=_parse_date(record.get("source_checked_at")),
        )
