from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Iterable, Optional

from law_rag.domain.models import LegalProvision


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _tag(node: ET.Element) -> str:
    return node.tag.split("}")[-1]


def _first_text(root: ET.Element, names: Iterable[str]) -> Optional[str]:
    """Return the first populated alias, respecting alias priority."""
    nodes = list(root.iter())
    for name in names:
        for node in nodes:
            if _tag(node) == name and _clean(node.text):
                return _clean(node.text)
    return None


def _parse_yyyymmdd(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _number_label(prefix: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = _clean(value)
    if value.startswith("제"):
        return value
    digits = re.sub(r"[^0-9의]", "", value)
    return "제{}{}".format(digits, prefix) if digits else value


def _article_label(number: Optional[str], branch: Optional[str]) -> Optional[str]:
    if not number:
        return None
    base = _number_label("조", number)
    branch_digits = re.sub(r"\D", "", branch or "")
    if base and branch_digits and branch_digits != "0":
        return "{}의{}".format(base, int(branch_digits))
    return base


def _direct_children(node: ET.Element, tags: set[str]) -> list[ET.Element]:
    return [child for child in node if _tag(child) in tags]


class KoreanLawXmlParser:
    """Tolerant parser for Korean statute XML exports.

    Normalization follows the legal hierarchy 조 > 항 > 호 > 목. An article,
    paragraph, item and subitem may each become a searchable provision so the
    retriever can return the narrowest available legal basis.
    """

    ARTICLE_TAGS = {"조문단위", "조문", "article"}
    PARAGRAPH_TAGS = {"항", "paragraph"}
    ITEM_TAGS = {"호", "item"}
    SUBITEM_TAGS = {"목", "subitem"}

    def parse(
        self,
        xml_bytes: bytes,
        *,
        domain_id: str,
        source_url: Optional[str] = None,
        checked_at: Optional[date] = None,
    ) -> list[LegalProvision]:
        root = ET.fromstring(xml_bytes)
        law_id = _first_text(root, ["법령ID", "lawId", "law_id", "법령일련번호"]) or "unknown"
        law_name = _first_text(root, ["법령명_한글", "법령명한글", "법령명", "lawName", "law_name"]) or "미상 법령"
        promulgation = _parse_yyyymmdd(_first_text(root, ["공포일자", "promulgationDate"]))
        effective = _parse_yyyymmdd(_first_text(root, ["시행일자", "effectiveDate"]))
        revision = _parse_yyyymmdd(_first_text(root, ["개정일자", "revisionDate"])) or promulgation
        version_id = _first_text(root, ["법령일련번호", "versionId", "version_id"]) or "current"

        provisions: list[LegalProvision] = []
        seen: set[tuple[str, str]] = set()
        for article in root.iter():
            if _tag(article) not in self.ARTICLE_TAGS:
                continue
            article_no = _article_label(
                _first_text(article, ["조문번호", "articleNo", "article_no", "조문키"]),
                _first_text(article, ["조문가지번호", "articleBranchNo"]),
            )
            if not article_no:
                continue
            article_title = _first_text(article, ["조문제목", "articleTitle", "article_title"])
            article_effective = _parse_yyyymmdd(_first_text(article, ["조문시행일자"])) or effective
            article_content = _first_text(article, ["조문내용", "articleText", "text"])

            paragraph_nodes = _direct_children(article, self.PARAGRAPH_TAGS)
            if not paragraph_nodes:
                text = article_content or _clean(" ".join(article.itertext()))
                self._append(
                    provisions, seen, law_id, law_name, article_no, article_title,
                    None, None, None, text, domain_id, source_url, checked_at,
                    promulgation, article_effective, revision, version_id,
                )
                continue

            for p_index, paragraph in enumerate(paragraph_nodes, start=1):
                paragraph_no = _number_label(
                    "항", _first_text(paragraph, ["항번호", "paragraphNo", "paragraph_no"])
                ) or "제{}항".format(p_index)
                paragraph_text = _first_text(paragraph, ["항내용", "paragraphText", "text"])
                item_nodes = _direct_children(paragraph, self.ITEM_TAGS)
                base_text = paragraph_text or _clean(" ".join(paragraph.itertext()))
                self._append(
                    provisions, seen, law_id, law_name, article_no, article_title,
                    paragraph_no, None, None, base_text, domain_id, source_url,
                    checked_at, promulgation, article_effective, revision, version_id,
                )

                for i_index, item in enumerate(item_nodes, start=1):
                    item_no = _number_label(
                        "호", _first_text(item, ["호번호", "itemNo", "item_no"])
                    ) or "제{}호".format(i_index)
                    item_text = _first_text(item, ["호내용", "itemText", "text"]) or _clean(" ".join(item.itertext()))
                    self._append(
                        provisions, seen, law_id, law_name, article_no, article_title,
                        paragraph_no, item_no, None, item_text, domain_id, source_url,
                        checked_at, promulgation, article_effective, revision, version_id,
                    )

                    for s_index, subitem in enumerate(_direct_children(item, self.SUBITEM_TAGS), start=1):
                        subitem_no = _first_text(subitem, ["목번호", "subitemNo", "subitem_no"]) or str(s_index)
                        subitem_text = _first_text(subitem, ["목내용", "subitemText", "text"]) or _clean(" ".join(subitem.itertext()))
                        self._append(
                            provisions, seen, law_id, law_name, article_no, article_title,
                            paragraph_no, item_no, subitem_no, subitem_text, domain_id,
                            source_url, checked_at, promulgation, article_effective,
                            revision, version_id,
                        )
        return provisions

    @classmethod
    def _append(
        cls, provisions, seen, law_id, law_name, article_no, article_title,
        paragraph_no, item_no, subitem_no, text, domain_id, source_url,
        checked_at, promulgation, effective, revision, version_id,
    ) -> None:
        text = _clean(text)
        if not text:
            return
        provision = cls._make(
            law_id, law_name, article_no, article_title, paragraph_no, item_no,
            subitem_no, text, domain_id, source_url, checked_at, promulgation,
            effective, revision, version_id,
        )
        key = (provision.document_id, provision.version_id)
        if key not in seen:
            seen.add(key)
            provisions.append(provision)

    @staticmethod
    def _make(
        law_id, law_name, article_no, article_title, paragraph_no, item_no,
        subitem_no, text, domain_id, source_url, checked_at, promulgation,
        effective, revision, version_id,
    ):
        parts = [str(law_id), article_no]
        if paragraph_no:
            parts.append(paragraph_no)
        if item_no:
            parts.append(item_no)
        if subitem_no:
            parts.append(subitem_no)
        document_id = ":".join(re.sub(r"\s+", "", str(part)) for part in parts)
        return LegalProvision(
            document_id=document_id,
            law_id=str(law_id),
            law_name=law_name,
            article_no=article_no,
            article_title=article_title,
            paragraph_no=paragraph_no,
            item_no=item_no,
            subitem_no=subitem_no,
            text=text,
            promulgation_date=promulgation,
            effective_from=effective,
            revision_date=revision,
            is_current=True,
            authority="국가법령정보센터",
            reliability="공식",
            source_url=source_url,
            version_id=str(version_id),
            domain_tags=[domain_id],
            content_kind="official_text",
            source_checked_at=checked_at,
        )
