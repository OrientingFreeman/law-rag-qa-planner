from __future__ import annotations

from typing import Iterable


def _project_path(path: dict[str, object], assumed_true_fact_ids: set[str]) -> dict[str, object]:
    required = list(path.get("required_fact_ids") or [])
    current_missing = set(path.get("missing_fact_ids") or [])
    projected_missing = [fact for fact in required if fact in current_missing and fact not in assumed_true_fact_ids]
    completeness = 1.0 - len(projected_missing) / max(1, len(required))
    components = dict(path.get("confidence_components") or {})
    components["fact_completeness"] = round(completeness, 4)
    confidence = round(max(0.0, min(1.0,
        0.34 * float(components.get("evidence_strength", 0.0))
        + 0.30 * completeness
        + 0.16 * float(components.get("issue_coverage", 0.0))
        + 0.10 * float(components.get("directness", 0.0))
        + 0.06 * float(components.get("selection_support", 0.0))
        + 0.04 * float(components.get("context_fit", 0.0))
    )), 4)
    original_confidence = float(path.get("confidence") or 0.0)
    original_recommendation = float(path.get("recommendation_score") or 0.0)
    recommendation = round(max(0.0, min(1.0, original_recommendation + (confidence - original_confidence))), 4)
    return {
        "path_id": path.get("path_id"),
        "title": path.get("title"),
        "projected_status": "available" if not projected_missing else "conditional",
        "projected_missing_fact_ids": projected_missing,
        "projected_confidence": confidence,
        "projected_recommendation_score": recommendation,
        "confidence_delta": round(confidence - original_confidence, 4),
        "recommendation_score_delta": round(recommendation - original_recommendation, 4),
    }


def build_scenario_simulation(
    paths: Iterable[dict[str, object]],
    recommended: dict[str, object] | None,
    decision_support: dict[str, object],
) -> dict[str, object]:
    """Project recommendation changes when path-specific missing facts are assumed true."""
    rows = list(paths)
    current_id = str(recommended.get("path_id")) if recommended else None
    scenarios: list[dict[str, object]] = []
    switches = [row for row in decision_support.get("when_to_switch", []) if isinstance(row, dict)]

    for index, switch in enumerate(switches, start=1):
        facts = set(str(value) for value in switch.get("differentiating_fact_ids") or [])
        target_id = str(switch.get("target_path_id") or "")
        projections = [_project_path(path, facts) for path in rows]
        available = [row for row in projections if row["projected_status"] == "available"]
        ranked = sorted(
            available or projections,
            key=lambda row: (-float(row["projected_recommendation_score"]), -float(row["projected_confidence"]), str(row["path_id"])),
        )
        winner = ranked[0] if ranked else None
        target_projection = next((row for row in projections if str(row["path_id"]) == target_id), None)
        scenarios.append({
            "scenario_id": f"scenario:{index}",
            "title": f"{switch.get('condition', '대안 경로 요건 충족')} 가정",
            "assumed_true_fact_ids": sorted(facts),
            "target_path_id": target_id,
            "target_projection": target_projection,
            "projected_recommended_path_id": winner.get("path_id") if winner else None,
            "recommendation_changed": bool(winner and str(winner.get("path_id")) != current_id),
            "projected_safe_to_execute": bool(winner and winner.get("projected_status") == "available"),
            "top_projected_paths": ranked[:3],
        })

    return {
        "enabled": True,
        "version": "1.0",
        "mode": "deterministic_fact_assumption_projection",
        "current_recommended_path_id": current_id,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "limitations": [
            "가정된 사실의 법적 진실성 자체는 검증하지 않습니다.",
            "검색 근거는 재수집하지 않고 현재 경로와 점수 구성요소를 재평가합니다.",
            "실제 실행 전에는 가정 사실의 증거와 최신 법령을 별도로 확인해야 합니다.",
        ],
    }
