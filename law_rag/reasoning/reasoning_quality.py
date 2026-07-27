from __future__ import annotations

from statistics import mean
from typing import Iterable


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _grade(score: float) -> str:
    if score >= 0.9:
        return "excellent"
    if score >= 0.8:
        return "strong"
    if score >= 0.65:
        return "moderate"
    if score >= 0.5:
        return "weak"
    return "critical"


def _component(path: dict[str, object], name: str) -> float:
    components = path.get("confidence_components") or {}
    if not isinstance(components, dict):
        return 0.0
    try:
        return float(components.get(name, 0.0))
    except (TypeError, ValueError):
        return 0.0


def build_reasoning_quality_score(
    paths: Iterable[dict[str, object]],
    recommended: dict[str, object] | None,
    validation: dict[str, object],
    decision_support: dict[str, object],
    strategy_comparison: dict[str, object],
) -> dict[str, object]:
    """Score reasoning quality independently from route confidence.

    Confidence estimates support for a path. This scorer evaluates whether the
    reasoning product is complete, internally valid, differentiated, and usable.
    """
    rows = list(paths)
    if not recommended:
        return {
            "enabled": False,
            "version": "1.0",
            "overall_score": 0.0,
            "overall_percent": 0,
            "grade": "critical",
            "components": {},
            "strengths": [],
            "weaknesses": ["추천 가능한 추론 경로가 생성되지 않았습니다."],
        }

    evidence = _component(recommended, "evidence_strength")
    facts = _component(recommended, "fact_completeness")
    issues = _component(recommended, "issue_coverage")

    structural = 1.0 if bool(validation.get("valid")) else 0.0
    if validation.get("dangling_dependency_ids"):
        structural -= 0.35
    if validation.get("unbound_evidence_node_ids"):
        structural -= 0.35
    if int(validation.get("duplicate_path_id_count") or 0) > 0:
        structural -= 0.3
    structural = _bounded(structural)

    why_selected = list(decision_support.get("why_selected") or [])
    why_not = list(decision_support.get("why_not_selected") or [])
    switches = list(decision_support.get("when_to_switch") or [])
    required = list(decision_support.get("required_next_facts") or [])
    decision_clarity = _bounded(
        0.3 * bool(why_selected)
        + 0.25 * bool(why_not)
        + 0.25 * bool(switches)
        + 0.2 * (bool(required) or recommended.get("status") == "available")
    )

    alternatives = list(strategy_comparison.get("alternatives") or [])
    semantic_scores: list[float] = []
    for row in alternatives:
        if not isinstance(row, dict):
            continue
        semantic_scores.append(mean([
            1.0 if row.get("advantages") else 0.0,
            1.0 if row.get("requirements") else 0.0,
            1.0 if row.get("risks") else 0.0,
            1.0 if row.get("disadvantages") else 0.0,
        ]))
    semantic_completeness = mean(semantic_scores) if semantic_scores else 0.5
    switch_distinction = mean([
        1.0 if isinstance(row, dict) and row.get("differentiating_fact_ids") else 0.0
        for row in switches
    ]) if switches else 0.0
    strategy_differentiation = _bounded(0.55 * semantic_completeness + 0.45 * switch_distinction)

    components = {
        "evidence_quality": _bounded(evidence),
        "fact_completeness": _bounded(facts),
        "issue_coverage": _bounded(issues),
        "structural_integrity": structural,
        "decision_clarity": decision_clarity,
        "strategy_differentiation": strategy_differentiation,
    }
    weights = {
        "evidence_quality": 0.22,
        "fact_completeness": 0.22,
        "issue_coverage": 0.16,
        "structural_integrity": 0.16,
        "decision_clarity": 0.14,
        "strategy_differentiation": 0.10,
    }
    overall = _bounded(sum(components[key] * weights[key] for key in weights))

    strengths = [
        key for key, value in components.items() if value >= 0.8
    ]
    weaknesses = [
        key for key, value in components.items() if value < 0.65
    ]
    return {
        "enabled": True,
        "version": "1.0",
        "overall_score": overall,
        "overall_percent": round(overall * 100),
        "grade": _grade(overall),
        "components": components,
        "weights": weights,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "interpretation": "confidence는 선택 경로의 지지 정도이고 reasoning_quality는 전체 추론 산출물의 완전성·무결성·실행 가능성을 평가합니다.",
    }
