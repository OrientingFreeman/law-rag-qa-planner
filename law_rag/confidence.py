from __future__ import annotations

from law_rag.domain.models import SearchResult


def score_confidence(
    results: list[SearchResult],
    citation_valid: bool | None = None,
    grounding_coverage: float | None = None,
) -> dict[str, object]:
    if not results:
        return {
            "score": 0.0,
            "level": "low",
            "reasons": ["no_evidence"],
            "components": {"retrieval": 0.0, "coverage": 0.0, "citation": 0.0, "grounding": 0.0},
        }
    top = results[0]
    retrieval = min(1.0, max(0.0, top.score))
    direct_count = sum(1 for item in results if item.retrieval_reason == "direct")
    evidence_coverage = min(1.0, direct_count / 2)
    citation = 1.0 if citation_valid is True else 0.0 if citation_valid is False else 0.5
    grounding = 0.5 if grounding_coverage is None else min(1.0, max(0.0, grounding_coverage))
    value = 0.45 * retrieval + 0.15 * evidence_coverage + 0.15 * citation + 0.25 * grounding
    reasons = ["direct_match"] if direct_count else ["related_only"]
    if citation_valid is True:
        reasons.append("citation_validated")
    elif citation_valid is False:
        reasons.append("citation_invalid")
    if grounding >= 0.9:
        reasons.append("claims_grounded")
    elif grounding < 0.6:
        reasons.append("weak_claim_grounding")
    value = round(max(0.0, min(1.0, value)), 4)
    level = "high" if value >= 0.8 else "medium" if value >= 0.55 else "low"
    return {
        "score": value,
        "level": level,
        "reasons": reasons,
        "components": {
            "retrieval": round(retrieval, 4),
            "coverage": round(evidence_coverage, 4),
            "citation": round(citation, 4),
            "grounding": round(grounding, 4),
        },
    }
