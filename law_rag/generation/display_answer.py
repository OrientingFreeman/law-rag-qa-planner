from __future__ import annotations

import re
from typing import Iterable


_CITATION_SUFFIX = re.compile(r"\s*\(([^()]*(?:법|령|규칙)\s*제\d+조[^()]*)\)\s*$")


def _compact(text: object, *, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip(" -")
    if len(value) <= limit:
        return value
    shortened = value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return (shortened or value[:limit]).rstrip() + "…"


def _without_citation(text: str) -> str:
    return _CITATION_SUFFIX.sub("", text).strip()


def _citation_key(citation: str) -> str:
    article = re.search(r"(.+?\s제\d+조(?:의\d+)?)", citation)
    return article.group(1).strip() if article else citation.strip()


def _unique_rows(rows: Iterable[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen_text: set[str] = set()
    seen_citations: set[tuple[str, ...]] = set()
    for row in rows:
        text = _compact(row.get("text"))
        citations = tuple(str(item) for item in row.get("citations", []) if str(item).strip())
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", _without_citation(text))[:120]
        if not text or key in seen_text:
            continue
        if citations and citations in seen_citations:
            continue
        seen_text.add(key)
        if citations:
            seen_citations.add(citations)
        selected.append({"text": text, "citations": citations})
        if len(selected) >= limit:
            break
    return selected


def _render_row(row: dict[str, object], cited: set[str]) -> str:
    text = _without_citation(str(row["text"]))
    fresh = []
    for citation in row.get("citations", ()):
        key = _citation_key(citation)
        if key in cited:
            continue
        cited.add(key)
        fresh.append(citation)
    suffix = f" ({', '.join(fresh)})" if fresh else ""
    return f"- {text}{suffix}"


def build_display_answer(
    audited_answer: str,
    composition: dict[str, object] | None,
    *,
    precedents: list[dict[str, object]] | None = None,
    precedent_only: bool = False,
) -> str:
    """Create a concise web projection while preserving the audited API answer."""
    if precedent_only and precedents:
        primary = precedents[0]
        citation = " ".join(part for part in (
            str(primary.get("court", "")).strip(),
            str(primary.get("decision_date", "")).strip(),
            "선고",
            str(primary.get("case_number", "")).strip(),
            "판결",
        ) if part)
        return "\n".join([
            "결론",
            _compact(primary.get("holding_summary"), limit=300),
            "",
            "판단 기준",
            f"- {_compact(primary.get('reasoning_summary'), limit=300)} ({citation})",
            "",
            "사안 적용",
            f"- {_compact(primary.get('legal_context_note'), limit=260)}",
            "",
            "유보사항",
            "- 판례의 구체적 사건관계와 현재 적용 법령 및 적용 시점을 함께 확인해야 합니다.",
        ]).strip()
    if not composition:
        return audited_answer

    plan = composition.get("answer_plan", {})
    sections = {
        str(section.get("section_id")): list(section.get("sentences", []))
        for section in plan.get("sections", [])
        if isinstance(section, dict)
    }
    if not sections:
        return audited_answer

    conclusion_rows = _unique_rows(sections.get("conclusion", []), limit=1)
    criteria_rows = _unique_rows(sections.get("requirements", []), limit=3)
    application_rows = _unique_rows(sections.get("legal_analysis", []), limit=2)
    reservation_rows = _unique_rows(sections.get("additional_facts", []), limit=2)

    cited: set[str] = set()
    lines = ["결론"]
    lines.append(
        _without_citation(str(conclusion_rows[0]["text"]))
        if conclusion_rows
        else "검색된 근거를 기준으로 질문의 요건과 제한을 확인해야 합니다."
    )

    lines.extend(["", "판단 기준"])
    lines.extend(_render_row(row, cited) for row in criteria_rows)

    lines.extend(["", "사안 적용"])
    lines.extend(_render_row(row, cited) for row in application_rows)
    for precedent in (precedents or [])[:1]:
        holding = _compact(precedent.get("holding_summary"), limit=240)
        if not holding:
            continue
        label = " ".join(part for part in (
            str(precedent.get("court", "")).strip(),
            str(precedent.get("decision_date", "")).strip(),
            "선고",
            str(precedent.get("case_number", "")).strip(),
            "판결",
        ) if part)
        lines.append(f"- 관련 판례는 {holding} ({label})")

    lines.extend(["", "유보사항"])
    if reservation_rows:
        lines.extend(f"- {_without_citation(str(row['text']))}" for row in reservation_rows)
    else:
        lines.append("- 구체적 사실관계와 적용 시점은 별도로 확인해야 합니다.")
    return "\n".join(lines).strip()
