from __future__ import annotations

from typing import Iterable


BRANCH_STRATEGIES: dict[str, dict[str, object]] = {
    "1": {
        "strategy_label": "별도 동의 확보 전략",
        "legal_risk": "low",
        "implementation_cost": "high",
        "implementation_speed": "slow",
        "proof_burden": "medium",
        "reversibility": "high",
        "tradeoffs": [
            "명시적 동의 증적을 확보하면 법적 근거가 비교적 선명합니다.",
            "동의 문구·고지 항목·철회 절차를 별도로 설계해야 합니다.",
            "다수 정보주체를 대상으로 하면 운영 비용과 이탈 가능성이 커질 수 있습니다.",
        ],
    },
    "2": {
        "strategy_label": "특별 법적 근거 확인 전략",
        "legal_risk": "medium",
        "implementation_cost": "low",
        "implementation_speed": "fast",
        "proof_burden": "high",
        "reversibility": "medium",
        "tradeoffs": [
            "특별 규정이 실제 이전 행위와 대상 정보에 적용되는지 먼저 확인해야 합니다.",
            "적용 범위가 명확하다면 별도 동의 절차를 줄일 수 있습니다.",
            "근거 규정의 적용 범위를 과도하게 해석하면 사후 분쟁 위험이 큽니다.",
        ],
    },
    "3": {
        "strategy_label": "계약 이행 필요성 기반 전략",
        "legal_risk": "medium",
        "implementation_cost": "medium",
        "implementation_speed": "fast",
        "proof_burden": "high",
        "reversibility": "medium",
        "tradeoffs": [
            "처리위탁·보관이 계약 체결 또는 이행에 실제로 필요한지 입증해야 합니다.",
            "처리방침 공개 또는 개별 통지 절차를 정확히 이행해야 합니다.",
            "질문의 위탁 맥락과 가장 직접적으로 연결되지만 필요성 사실이 확인되지 않으면 단정할 수 없습니다.",
        ],
    },
    "4": {
        "strategy_label": "수령자 인증 활용 전략",
        "legal_risk": "low",
        "implementation_cost": "medium",
        "implementation_speed": "medium",
        "proof_burden": "medium",
        "reversibility": "low",
        "tradeoffs": [
            "수령자의 유효한 인증과 인증 범위를 확인해야 합니다.",
            "이전 국가에서 인증 사항을 실제 이행할 조치까지 마련해야 합니다.",
            "인증된 수령자를 선택할 수 있다면 보호조치 설명이 용이해집니다.",
        ],
    },
    "5": {
        "strategy_label": "적정성 인정 국가·기구 활용 전략",
        "legal_risk": "low",
        "implementation_cost": "low",
        "implementation_speed": "fast",
        "proof_burden": "low",
        "reversibility": "low",
        "tradeoffs": [
            "보호위원회의 인정 여부와 인정 범위를 확인해야 합니다.",
            "인정 범위 내라면 개별 동의나 인증 검토 부담을 줄일 수 있습니다.",
            "이전 국가나 수령자를 변경하면 근거를 다시 검토해야 합니다.",
        ],
    },
}

FACT_LABELS: dict[str, str] = {
    "transfer_basis": "국외이전의 법적 근거",
    "transfer_country": "이전 국가",
    "transfer_items": "이전 개인정보 항목",
    "recipient_safeguards": "수령자의 보호조치",
    "delegation_purpose": "처리위탁 목적",
    "delegate_identity": "수탁자 신원",
    "subdelegation": "재위탁 여부",
    "special_legal_basis": "특별 법적 근거",
    "legal_basis_scope": "특별 규정의 적용 범위",
    "contract_necessity": "계약 체결·이행상 필요성",
    "delegation_or_storage": "처리위탁·보관 해당성",
    "transfer_notice_method": "처리방침 공개 또는 개별 통지 방법",
    "consent_obtained": "국외이전 별도 동의 취득",
    "consent_notice_items": "동의 시 필수 고지사항",
    "recipient_identity": "국외 수령자 신원",
    "recipient_certification": "수령자의 유효한 인증",
    "certification_scope": "인증 범위",
    "foreign_execution_measures": "이전 국가에서의 인증 이행조치",
    "adequacy_recognition": "적정성 인정 여부",
    "adequacy_scope": "적정성 인정 범위",
}

BRANCH_SEMANTICS: dict[str, dict[str, list[str]]] = {
    "1": {
        "advantages": ["명시적 동의 증적을 확보하면 법적 근거와 감사 추적성이 비교적 선명합니다."],
        "requirements": ["동의 문구, 필수 고지사항, 철회 절차를 별도로 설계하고 동의 증적을 보관해야 합니다."],
        "risks": ["대상자가 많으면 운영 비용과 서비스 이탈 가능성이 커질 수 있습니다."],
    },
    "2": {
        "advantages": ["특별 규정의 적용 범위가 명확하면 별도 동의 절차를 줄일 수 있습니다."],
        "requirements": ["특별 규정이 실제 이전 행위와 대상 개인정보에 적용되는지 확인해야 합니다."],
        "risks": ["특별 규정의 적용 범위를 과도하게 해석하면 사후 분쟁 위험이 커집니다."],
    },
    "3": {
        "advantages": ["질문의 처리위탁 맥락과 직접 연결되며 요건 충족 시 별도 동의 없이 이전 근거를 구성할 수 있습니다."],
        "requirements": ["처리위탁·보관이 계약 체결 또는 이행에 실제로 필요하고, 처리방침 공개 또는 개별 통지 요건을 충족해야 합니다."],
        "risks": ["계약상 필요성이나 통지 절차를 입증하지 못하면 해당 근거를 적용하기 어렵습니다."],
    },
    "4": {
        "advantages": ["인증된 수령자를 활용하면 보호조치와 권리보장 체계를 설명하기 쉽습니다."],
        "requirements": ["수령자의 인증 유효성·범위와 이전 국가에서의 실제 이행조치를 확인해야 합니다."],
        "risks": ["인증 범위 밖의 처리나 현지 이행 부족이 확인되면 근거가 약화될 수 있습니다."],
    },
    "5": {
        "advantages": ["인정 범위 내에서는 개별 동의나 수령자 인증 검토 부담을 줄일 수 있습니다."],
        "requirements": ["보호위원회의 적정성 인정 여부와 대상 국가·기구·처리 범위를 확인해야 합니다."],
        "risks": ["이전 국가, 수령자 또는 처리 범위가 바뀌면 법적 근거를 다시 검토해야 합니다."],
    },
}

LEVEL_SCORE = {"low": 1.0, "medium": 0.6, "high": 0.25}
SPEED_SCORE = {"fast": 1.0, "medium": 0.65, "slow": 0.3}
COST_SCORE = {"low": 1.0, "medium": 0.65, "high": 0.3}


def strategy_profile(path_type: str, branch_key: str | None, status: str) -> dict[str, object]:
    if branch_key in BRANCH_STRATEGIES:
        profile = dict(BRANCH_STRATEGIES[branch_key])
        profile["strategy_type"] = "concrete_legal_basis"
    elif path_type == "cumulative":
        profile = {
            "strategy_type": "issue_coverage_and_fact_gathering",
            "strategy_label": "전체 쟁점 보전 및 사실확인 전략",
            "legal_risk": "low",
            "implementation_cost": "medium",
            "implementation_speed": "medium",
            "proof_burden": "medium",
            "reversibility": "high",
            "tradeoffs": [
                "특정 법적 근거를 성급하게 단정하지 않고 모든 필수 쟁점을 보전합니다.",
                "추가 사실 확인 전에는 최종 실행 근거로 사용할 수 없습니다.",
                "누락 사실을 수집한 뒤 구체적 법적 근거 경로로 전환해야 합니다.",
            ],
        }
    else:
        profile = {
            "strategy_type": "baseline_review",
            "strategy_label": "기본 의무 확인 전략",
            "legal_risk": "medium",
            "implementation_cost": "medium",
            "implementation_speed": "medium",
            "proof_burden": "medium",
            "reversibility": "high",
            "tradeoffs": ["기본 의무를 누락하지 않도록 검토 범위를 유지합니다."],
        }
    semantics = BRANCH_SEMANTICS.get(str(branch_key)) if branch_key is not None else None
    if semantics:
        profile.update({key: list(value) for key, value in semantics.items()})
    elif path_type == "cumulative":
        profile.update({
            "advantages": ["특정 근거를 성급히 단정하지 않고 복수 쟁점과 후속 사실조사를 모두 보전합니다."],
            "requirements": ["누락된 핵심 사실을 수집한 뒤 구체적 법적 근거 경로로 전환해야 합니다."],
            "risks": ["사실 확인 전에는 최종 실행 근거로 사용할 수 없습니다."],
        })
    else:
        profile.update({
            "advantages": ["기본 의무 누락을 방지하며 검토 범위를 유지합니다."],
            "requirements": ["쟁점별 구체 사실과 적용 근거를 추가 확인해야 합니다."],
            "risks": ["기본 검토만으로는 최종 실행 결론을 확정하기 어렵습니다."],
        })
    profile["execution_ready"] = status == "available" and path_type in {"alternative_basis", "cumulative_basis"}
    return profile


def recommendation_score(confidence: float, profile: dict[str, object], *, issue_coverage: float, status: str) -> float:
    risk = LEVEL_SCORE.get(str(profile.get("legal_risk")), 0.5)
    cost = COST_SCORE.get(str(profile.get("implementation_cost")), 0.5)
    speed = SPEED_SCORE.get(str(profile.get("implementation_speed")), 0.5)
    readiness = 1.0 if status == "available" else 0.45
    return round(min(1.0, max(0.0,
        0.42 * confidence + 0.22 * issue_coverage + 0.16 * risk + 0.08 * cost + 0.06 * speed + 0.06 * readiness
    )), 4)


def explain_non_recommendation(path: dict[str, object], recommended: dict[str, object] | None) -> list[str]:
    if not recommended or path.get("path_id") == recommended.get("path_id"):
        return []
    reasons: list[str] = []
    if path.get("status") != "available":
        missing = list(path.get("missing_fact_ids") or [])
        if missing:
            reasons.append(f"{len(missing)}개 핵심 사실이 미확정되어 즉시 실행 가능한 경로가 아닙니다.")
    profile = path.get("strategy_profile") or {}
    if isinstance(profile, dict):
        risk = str(profile.get("legal_risk") or "")
        burden = str(profile.get("proof_burden") or "")
        cost = str(profile.get("implementation_cost") or "")
        if risk == "high":
            reasons.append("법적 위험이 높아 우선 추천에서 제외했습니다.")
        elif burden == "high":
            reasons.append("적용 요건에 대한 입증 부담이 높습니다.")
        if cost == "high":
            reasons.append("구현 비용이 높아 더 효율적인 대안을 우선 검토할 필요가 있습니다.")
    gap = round(float(recommended.get("recommendation_score", 0)) - float(path.get("recommendation_score", 0)), 4)
    if gap > 0:
        reasons.append(f"최종 추천 경로보다 실행 추천 점수가 {gap:.4f} 낮습니다.")
    return reasons[:3]


def build_strategy_comparison(paths: Iterable[dict[str, object]], recommended: dict[str, object] | None, limit: int = 3) -> dict[str, object]:
    rows = list(paths)
    if not recommended:
        return {"enabled": False, "recommended_path_id": None, "alternatives": []}
    candidates = [row for row in rows if row.get("path_id") != recommended.get("path_id")]
    candidates.sort(key=lambda row: (-float(row.get("recommendation_score", 0)), -float(row.get("confidence", 0)), str(row.get("path_id"))))
    alternatives = []
    for row in candidates[:limit]:
        profile = row.get("strategy_profile") or {}
        alternatives.append({
            "path_id": row.get("path_id"),
            "title": row.get("title"),
            "recommendation_score": row.get("recommendation_score"),
            "confidence": row.get("confidence"),
            "score_gap": round(float(recommended.get("recommendation_score", 0)) - float(row.get("recommendation_score", 0)), 4),
            "advantages": list(profile.get("advantages", [])) if isinstance(profile, dict) else [],
            "requirements": list(profile.get("requirements", [])) if isinstance(profile, dict) else [],
            "risks": list(profile.get("risks", [])) if isinstance(profile, dict) else [],
            "disadvantages": list(row.get("recommendation_reasons") or []),
            "strategy_profile": profile,
        })
    return {
        "enabled": True,
        "version": "1.1",
        "recommended_path_id": recommended.get("path_id"),
        "comparison_basis": ["recommendation_score", "confidence", "legal_risk", "implementation_cost", "implementation_speed", "proof_burden", "reversibility"],
        "alternatives": alternatives,
    }



def _has_final_consonant(text: str) -> bool:
    if not text:
        return False
    code = ord(text[-1])
    return 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0


def _subject_particle(text: str) -> str:
    return "이" if _has_final_consonant(text) else "가"


def _and_particle(text: str) -> str:
    return "과" if _has_final_consonant(text) else "와"


def build_decision_support(
    paths: Iterable[dict[str, object]],
    recommended: dict[str, object] | None,
    recommendation_reason: str | None,
    comparison: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build an execution-oriented decision contract from ranked legal paths."""
    rows = list(paths)
    if not recommended:
        return {
            "enabled": False,
            "version": "1.1",
            "recommended_path_id": None,
            "why_selected": [],
            "why_not_selected": [],
            "tradeoff_summary": None,
            "when_to_switch": [],
            "required_next_facts": [],
        }

    selected_profile = recommended.get("strategy_profile") or {}
    alternatives = [row for row in rows if row.get("path_id") != recommended.get("path_id")]
    alternatives.sort(key=lambda row: (
        -float(row.get("recommendation_score", 0)),
        -float(row.get("confidence", 0)),
        str(row.get("path_id")),
    ))

    why_selected = list(recommended.get("recommendation_reasons") or [])
    if recommendation_reason and recommendation_reason not in why_selected:
        why_selected.insert(0, recommendation_reason)

    why_not_selected = []
    for row in alternatives[:3]:
        why_not_selected.append({
            "path_id": row.get("path_id"),
            "title": row.get("title"),
            "reasons": list(row.get("recommendation_reasons") or []),
        })

    switch_rules = []
    selected_missing = set(str(item) for item in (recommended.get("missing_fact_ids") or []))
    for row in alternatives[:3]:
        missing = [str(item) for item in (row.get("missing_fact_ids") or [])]
        differentiating = [item for item in missing if item not in selected_missing]
        decisive = differentiating or missing
        if not decisive:
            condition = "해당 경로의 적용 요건이 모두 확인되는 경우"
        else:
            labels = [FACT_LABELS.get(item, item) for item in decisive]
            if len(labels) == 1:
                fact_phrase = labels[0]
            elif len(labels) == 2:
                fact_phrase = f"{labels[0]}{_and_particle(labels[0])} {labels[1]}"
            else:
                fact_phrase = ", ".join(labels[:-1]) + f" 및 {labels[-1]}"
            condition = f"{fact_phrase}{_subject_particle(fact_phrase)} 확인되어 해당 경로의 고유 적용 요건이 충족되는 경우"
        switch_rules.append({
            "target_path_id": row.get("path_id"),
            "condition": condition,
            "required_fact_ids": missing,
            "differentiating_fact_ids": decisive,
        })

    selected_label = selected_profile.get("strategy_label") if isinstance(selected_profile, dict) else None
    risk = selected_profile.get("legal_risk") if isinstance(selected_profile, dict) else None
    cost = selected_profile.get("implementation_cost") if isinstance(selected_profile, dict) else None
    speed = selected_profile.get("implementation_speed") if isinstance(selected_profile, dict) else None
    tradeoff_summary = (
        f"{selected_label or recommended.get('title')}을 우선하되, "
        f"법적 위험 {risk or '미평가'}, 구현 비용 {cost or '미평가'}, 실행 속도 {speed or '미평가'}의 균형을 전제로 합니다."
    )

    return {
        "enabled": True,
        "version": "1.1",
        "recommended_path_id": recommended.get("path_id"),
        "recommended_strategy": {
            "path_id": recommended.get("path_id"),
            "title": recommended.get("title"),
            "recommendation_score": recommended.get("recommendation_score"),
            "confidence": recommended.get("confidence"),
            "strategy_profile": selected_profile,
        },
        "why_selected": why_selected,
        "why_not_selected": why_not_selected,
        "tradeoff_summary": tradeoff_summary,
        "when_to_switch": switch_rules,
        "required_next_facts": list(recommended.get("missing_fact_ids") or []),
        "comparison_ref": {
            "enabled": bool((comparison or {}).get("enabled")),
            "alternative_count": len((comparison or {}).get("alternatives") or []),
        },
    }

def explain_recommendation(path: dict[str, object], alternatives: Iterable[dict[str, object]]) -> list[str]:
    reasons: list[str] = []
    if path.get("path_type") == "cumulative":
        reasons.append("질문이 처리위탁과 국외이전의 복수 쟁점을 동시에 포함하므로 두 규율을 누적 검토해야 합니다.")
        reasons.append("현재는 국외이전의 구체적 법적 근거를 확정할 핵심 사실이 부족하므로 특정 호를 단정하지 않았습니다.")
    elif path.get("branch_key"):
        reasons.append(f"확인된 사실과 경로 신뢰도를 기준으로 국외이전 근거 {path['branch_key']} 경로가 가장 우선됩니다.")
    missing = list(path.get("missing_fact_ids") or [])
    if missing:
        reasons.append(f"최종 적용 전 {len(missing)}개 핵심 사실을 추가 확인해야 합니다.")
    higher_confidence = [row for row in alternatives if float(row.get("confidence", 0)) > float(path.get("confidence", 0))]
    if higher_confidence:
        reasons.append("일부 구체 경로의 분석 신뢰도는 더 높지만, 사실 미확정 상태에서의 성급한 법적 근거 선택을 피하기 위해 추천 우선순위를 조정했습니다.")
    return reasons
