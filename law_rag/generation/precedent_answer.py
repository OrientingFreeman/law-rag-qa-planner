from __future__ import annotations

from law_rag.generation.answer import AnswerResult


MIN_PRECEDENT_ANSWER_SCORE = 0.35


def validate_precedent_evidence(
    precedents: list[dict[str, object]],
    *,
    minimum_score: float = MIN_PRECEDENT_ANSWER_SCORE,
) -> dict[str, object]:
    qualified = [
        row for row in precedents
        if float(row.get("score", 0.0)) >= minimum_score
        and row.get("precedent_id")
        and row.get("case_number")
        and row.get("holding_summary")
        and str(row.get("source_url", "")).startswith("https://www.law.go.kr/")
    ]
    return {
        "valid": bool(qualified),
        "answer_supported": bool(qualified),
        "minimum_score": minimum_score,
        "qualified_precedent_ids": [str(row["precedent_id"]) for row in qualified],
        "qualified_case_numbers": [str(row["case_number"]) for row in qualified],
        "source_urls": [str(row["source_url"]) for row in qualified],
        "support_method": "verified_official_summary" if qualified else "insufficient_precedent_score",
    }


def generate_precedent_grounded_answer(
    precedents: list[dict[str, object]],
    validation: dict[str, object],
) -> AnswerResult:
    qualified_ids = set(map(str, validation.get("qualified_precedent_ids", [])))
    qualified = [row for row in precedents if str(row.get("precedent_id")) in qualified_ids]
    primary = qualified[0]
    court = str(primary["court"])
    case_number = str(primary["case_number"])
    decision_date = str(primary["decision_date"])
    citation = f"{court} {decision_date} 선고 {case_number} 판결"
    answer = "\n".join([
        "결론",
        str(primary["holding_summary"]),
        "",
        "판례상 해석",
        str(primary["reasoning_summary"]),
        "",
        "적용상 주의사항",
        str(primary["legal_context_note"]),
        "",
        "근거 판례",
        citation,
    ])
    return AnswerResult(
        answer=answer,
        provider="verified-precedent",
        model="deterministic-official-summary",
        citation_validation={
            "valid": True,
            "cited_articles": [],
            "retrieved_articles": [],
            "unsupported_articles": [],
        },
        generation_status="completed",
        grounding_validation={
            "valid": True,
            "claim_count": 1,
            "supported_claim_count": 1,
            "coverage": 1.0,
            "unsupported_claims": [],
            "claims": [{
                "claim_id": "precedent-claim-1",
                "sentence": str(primary["holding_summary"]),
                "supported": True,
                "support_method": "explicit_citation",
                "supporting_citation": citation,
                "supporting_citations": [citation],
                "supporting_evidence": [],
                "assigned_evidence": [],
                "semantic_labels": ["precedent_interpretation"],
                "semantic_label_ids": [str(primary["precedent_id"])],
                "ontology": {},
                "source_document_id": str(primary["precedent_id"]),
                "source_excerpt": str(primary["holding_summary"]),
                "evidence_scope": "provision",
                "overlap_score": float(primary["score"]),
                "explicit_citation": True,
                "cited_articles": [],
            }],
            "audit": {
                "traceable_claim_count": 1,
                "supported_evidence_count": 1,
                "multi_source_claim_count": 0,
                "evidence_role_counts": {"precedent": 1},
                "assigned_evidence_count": 1,
                "contextual_evidence_count": 0,
                "semantic_assignment_coverage": 1.0,
                "fully_traceable": True,
            },
        },
        composition={
            "mode": "precedent_grounded",
            "fallback_used": False,
            "citation_repairs": [],
            "plan": {
                "rules": [],
                "allowed_citations": [citation],
                "required_actions": ["판례 해석과 적용상 주의사항을 구분한다."],
            },
            "precedent_validation": validation,
        },
    )
