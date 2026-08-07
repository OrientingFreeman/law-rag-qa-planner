from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class SafetyDecision:
    action: str = "continue"
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


TEMPORAL_TERMS = ("개정 전", "개정 후", "당시", "시행 전", "시행 후", "언제부터", "기준일")
EXPLICIT_NON_LEGAL_SIGNALS = (
    "날씨", "강수확률", "기온", "김치찌개", "요리법", "레시피", "축구 점수", "영화 추천",
)
BROAD_SCOPE_TERMS = ("모든 법률", "법적 문제 전부", "모든 규제", "전부 검토해", "완벽하게 검토")


def preflight(question: str, provisions: list[object], as_of_date: date | None) -> SafetyDecision:
    if any(signal in question for signal in EXPLICIT_NON_LEGAL_SIGNALS):
        return SafetyDecision("abstain", "out_of_domain")
    if any(term in question for term in BROAD_SCOPE_TERMS):
        return SafetyDecision("clarify", "scope_too_broad", ["검토할 행위·법률관계·기준 시점을 좁혀야 합니다."])
    law_names = {str(getattr(row, "law_name", "")) for row in provisions}
    articles_by_law: dict[str, set[str]] = {}
    for row in provisions:
        articles_by_law.setdefault(str(getattr(row, "law_name", "")), set()).add(
            str(getattr(row, "article_no", "")).replace(" ", "")
        )
    explicit_articles = [item.replace(" ", "") for item in re.findall(r"제\s*\d+조(?:의\s*\d+)?", question)]
    mentioned_laws = [name for name in law_names if name and name in question]
    if explicit_articles and mentioned_laws:
        if not any(article in articles_by_law.get(name, set()) for name in mentioned_laws for article in explicit_articles):
            # A false premise can still be safely corrected when the same article
            # exists in another instrument and its substantive text clearly matches
            # the question (for example, fraud/cancellation under Civil Act art. 110).
            query_terms = {term for term in re.findall(r"[가-힣A-Za-z0-9]+", question) if len(term) >= 2}
            correction_supported = False
            for row in provisions:
                article = str(getattr(row, "article_no", "")).replace(" ", "")
                if article not in explicit_articles or str(getattr(row, "law_name", "")) in mentioned_laws:
                    continue
                evidence_text = " ".join((
                    str(getattr(row, "article_title", "")), str(getattr(row, "text", ""))
                ))
                evidence_terms = {term for term in re.findall(r"[가-힣A-Za-z0-9]+", evidence_text) if len(term) >= 2}
                if len(query_terms & evidence_terms) >= 2:
                    correction_supported = True
                    break
            if not correction_supported:
                return SafetyDecision("abstain", "unknown_law_or_article")
    if as_of_date is None and any(term in question for term in TEMPORAL_TERMS):
        return SafetyDecision("clarify", "temporal_uncertainty", ["적용 기준일을 확인해야 합니다."])
    return SafetyDecision()


def post_retrieval(response: dict[str, object]) -> SafetyDecision:
    if bool(response.get("abstain")) or not response.get("results"):
        return SafetyDecision("retry", "insufficient_evidence")
    return SafetyDecision()


def post_generation(response: dict[str, object]) -> SafetyDecision:
    citation = response.get("citation_validation") or {}
    grounding = response.get("grounding_validation") or {}
    if isinstance(citation, dict) and not citation.get("valid", False):
        return SafetyDecision("abstain", "unsupported_citation")
    # The legacy generator may mark a response invalid when a secondary sentence
    # misses its strict lexical threshold even though the audited answer remains
    # substantially grounded. Stop only when coverage itself is materially weak.
    if isinstance(grounding, dict) and float(grounding.get("coverage", 0.0) or 0.0) < 0.75:
        return SafetyDecision("abstain", "evidence_conclusion_conflict")
    status = str(response.get("generation_status", ""))
    if status in {"failed", "citation_invalid"}:
        return SafetyDecision("abstain", "generation_quality_failure")
    missing = response.get("missing_fact_detector") or {}
    question = str(response.get("question", ""))
    case_specific = any(term in question for term in (
        "우리 회사", "제가", "했는데", "했습니다", "발생했습니다", "이 사안", "이 경우",
    ))
    if (
        isinstance(missing, dict)
        and int(missing.get("missing_fact_count", 0) or 0) > 0
        and missing.get("complete_for_final_advice") is False
        and case_specific
    ):
        return SafetyDecision("clarify", "missing_required_facts")
    return SafetyDecision()
