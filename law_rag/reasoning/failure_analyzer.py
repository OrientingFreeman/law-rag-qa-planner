from __future__ import annotations

from typing import Iterable


COMPONENT_MESSAGES = {
    "evidence_quality": ("insufficient_evidence", "근거 강도가 충분하지 않습니다.", "직접 적용되는 조문·하위 규정·공식 근거를 추가 확보하십시오."),
    "fact_completeness": ("missing_critical_facts", "핵심 사실이 부족해 결론이 조건부에 머뭅니다.", "required_next_facts를 우선순위에 따라 확인하십시오."),
    "issue_coverage": ("incomplete_issue_coverage", "질문의 필수 법적 쟁점이 완전히 포괄되지 않았습니다.", "누락 쟁점을 재분해하고 해당 쟁점의 근거를 검색하십시오."),
    "structural_integrity": ("reasoning_graph_integrity", "추론 그래프의 참조 무결성 문제가 있습니다.", "dangling dependency, unbound evidence, duplicate path ID를 수정하십시오."),
    "decision_clarity": ("unclear_decision_contract", "추천·배제·전환 조건이 충분히 설명되지 않았습니다.", "why_selected, why_not_selected, when_to_switch를 보강하십시오."),
    "strategy_differentiation": ("weak_strategy_differentiation", "대안 전략 간 차이가 충분히 구분되지 않습니다.", "대안별 장점·요건·위험과 고유 전환 사실을 분리하십시오."),
}


def _severity(value: float) -> str:
    if value < 0.4:
        return "critical"
    if value < 0.65:
        return "high"
    if value < 0.8:
        return "medium"
    return "none"


def build_failure_analysis(
    quality: dict[str, object],
    recommended: dict[str, object] | None,
    validation: dict[str, object],
    paths: Iterable[dict[str, object]],
) -> dict[str, object]:
    components = quality.get("components") or {}
    failures: list[dict[str, object]] = []
    if isinstance(components, dict):
        for component, raw in components.items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 0.0
            severity = _severity(value)
            if severity == "none":
                continue
            failure_type, message, remediation = COMPONENT_MESSAGES.get(
                str(component), (str(component), "추론 품질 저하가 감지되었습니다.", "해당 품질 축을 보강하십시오.")
            )
            failures.append({
                "failure_type": failure_type,
                "component": component,
                "severity": severity,
                "score": round(value, 4),
                "message": message,
                "remediation": remediation,
            })

    if not recommended:
        failures.insert(0, {
            "failure_type": "no_recommended_path",
            "component": "recommendation",
            "severity": "critical",
            "score": 0.0,
            "message": "추천 가능한 법적 경로가 생성되지 않았습니다.",
            "remediation": "쟁점 분해, 근거 검색 및 경로 생성 단계를 재실행하십시오.",
        })

    failures.sort(key=lambda row: ({"critical": 0, "high": 1, "medium": 2}.get(str(row["severity"]), 3), float(row["score"])))
    critical_count = sum(row["severity"] == "critical" for row in failures)
    high_count = sum(row["severity"] == "high" for row in failures)
    status = "blocked" if critical_count else "degraded" if high_count else "acceptable"

    missing = list((recommended or {}).get("missing_fact_ids") or [])
    return {
        "enabled": True,
        "version": "1.0",
        "status": status,
        "failure_count": len(failures),
        "critical_failure_count": critical_count,
        "high_failure_count": high_count,
        "primary_failure": failures[0] if failures else None,
        "failures": failures,
        "missing_fact_ids": missing,
        "validation_valid": bool(validation.get("valid")),
        "safe_to_execute": bool(recommended) and not failures and (recommended or {}).get("status") == "available",
        "summary": (
            "중대한 추론 실패가 감지되었습니다." if status == "blocked"
            else "추가 사실 또는 품질 보강 후 실행해야 합니다." if status == "degraded"
            else "치명적 실패는 없으며 현재 품질 범위에서 검토를 계속할 수 있습니다."
        ),
    }
