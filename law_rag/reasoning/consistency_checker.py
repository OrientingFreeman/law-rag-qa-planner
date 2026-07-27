from __future__ import annotations

from collections import Counter
from typing import Iterable


def _issue(code: str, severity: str, message: str, remediation: str, **context: object) -> dict[str, object]:
    return {
        "issue_code": code,
        "severity": severity,
        "message": message,
        "remediation": remediation,
        "context": context,
    }


def build_consistency_report(
    paths: Iterable[dict[str, object]],
    recommended: dict[str, object] | None,
    validation: dict[str, object],
    strategy_comparison: dict[str, object],
    decision_support: dict[str, object],
) -> dict[str, object]:
    """Detect internal contradictions and contract mismatches in legal reasoning output."""
    rows = list(paths)
    issues: list[dict[str, object]] = []
    path_index = {str(row.get("path_id")): row for row in rows}

    if not validation.get("valid"):
        issues.append(_issue(
            "graph_validation_failed", "critical",
            "추론 그래프 참조 무결성 검증에 실패했습니다.",
            "dangling dependency, unbound evidence, duplicate path ID를 먼저 수정하십시오.",
            validation=validation,
        ))

    if recommended:
        recommended_id = str(recommended.get("path_id"))
        marked = [row for row in rows if row.get("is_recommended")]
        if len(marked) != 1 or str(marked[0].get("path_id")) != recommended_id:
            issues.append(_issue(
                "recommendation_marker_mismatch", "high",
                "추천 경로 ID와 경로 목록의 추천 표시가 일치하지 않습니다.",
                "recommended_path_id와 is_recommended 표시를 단일 경로로 동기화하십시오.",
                recommended_path_id=recommended_id,
                marked_path_ids=[row.get("path_id") for row in marked],
            ))
        if recommended.get("status") == "available" and recommended.get("missing_fact_ids"):
            issues.append(_issue(
                "available_path_has_missing_facts", "critical",
                "적용 가능 경로에 미확정 핵심 사실이 남아 있습니다.",
                "상태 판정 또는 missing_fact_ids 계산을 수정하십시오.",
                path_id=recommended_id,
                missing_fact_ids=recommended.get("missing_fact_ids"),
            ))
        profile = recommended.get("strategy_profile") or {}
        if isinstance(profile, dict):
            ready = bool(profile.get("execution_ready"))
            if ready != (recommended.get("status") == "available"):
                issues.append(_issue(
                    "execution_readiness_mismatch", "high",
                    "경로 상태와 전략 실행 가능 표시가 일치하지 않습니다.",
                    "strategy_profile.execution_ready를 경로 status와 동기화하십시오.",
                    path_id=recommended_id,
                    status=recommended.get("status"),
                    execution_ready=ready,
                ))
    elif rows:
        issues.append(_issue(
            "missing_recommendation", "critical",
            "경로가 존재하지만 추천 경로가 지정되지 않았습니다.",
            "추천 정책과 정렬 결과를 재검토하십시오.",
        ))

    comparison_id = strategy_comparison.get("recommended_path_id")
    decision_id = decision_support.get("recommended_path_id")
    recommended_id = str(recommended.get("path_id")) if recommended else None
    for source, value in (("strategy_comparison", comparison_id), ("decision_support", decision_id)):
        if value != recommended_id:
            issues.append(_issue(
                "decision_contract_path_mismatch", "high",
                f"{source}의 추천 경로가 최종 추천 경로와 일치하지 않습니다.",
                "모든 의사결정 산출물에서 동일한 recommended_path_id를 사용하십시오.",
                source=source, expected=recommended_id, actual=value,
            ))

    switches = list(decision_support.get("when_to_switch") or [])
    seen_targets: Counter[str] = Counter()
    for switch in switches:
        if not isinstance(switch, dict):
            continue
        target = str(switch.get("target_path_id") or "")
        seen_targets[target] += 1
        if target not in path_index:
            issues.append(_issue(
                "switch_target_missing", "high",
                "전환 조건이 존재하지 않는 경로를 가리킵니다.",
                "when_to_switch의 target_path_id를 현재 경로 집합과 동기화하십시오.",
                target_path_id=target,
            ))
        differentiating = set(switch.get("differentiating_fact_ids") or [])
        required = set(switch.get("required_fact_ids") or [])
        if not differentiating or not differentiating.issubset(required):
            issues.append(_issue(
                "invalid_switch_facts", "high",
                "전환 고유 사실이 비어 있거나 해당 경로의 필수 사실에 포함되지 않습니다.",
                "differentiating_fact_ids를 required_fact_ids의 고유 부분집합으로 구성하십시오.",
                target_path_id=target,
            ))
    for target, count in seen_targets.items():
        if target and count > 1:
            issues.append(_issue(
                "duplicate_switch_target", "medium",
                "동일 대안 경로에 중복 전환 조건이 생성되었습니다.",
                "대안 경로별 전환 조건을 하나로 병합하십시오.",
                target_path_id=target, count=count,
            ))

    # A concrete statutory path must not cite another numbered alternative as its own branch evidence.
    for row in rows:
        branch_key = str(row.get("branch_key") or "")
        if not branch_key:
            continue
        branch_text = str(row.get("branch_text") or "").lstrip()
        if branch_text and not branch_text.startswith(f"{branch_key}."):
            issues.append(_issue(
                "statutory_basis_mixing", "critical",
                "경로의 법적 근거 번호와 연결된 조문 분기 텍스트가 일치하지 않습니다.",
                "branch_key와 branch_text의 동일 호수 연결을 복원하십시오.",
                path_id=row.get("path_id"), branch_key=branch_key, branch_text=branch_text,
            ))

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda row: (severity_order.get(str(row["severity"]), 9), str(row["issue_code"])))
    counts = Counter(str(row["severity"]) for row in issues)
    status = "inconsistent" if counts["critical"] else "warning" if counts["high"] or counts["medium"] else "consistent"
    return {
        "enabled": True,
        "version": "1.0",
        "status": status,
        "consistent": not issues,
        "issue_count": len(issues),
        "severity_counts": dict(sorted(counts.items())),
        "issues": issues,
        "checked_rules": [
            "graph_reference_integrity",
            "single_recommendation_contract",
            "status_and_execution_readiness",
            "cross_output_recommendation_alignment",
            "switch_condition_integrity",
            "statutory_basis_isolation",
        ],
        "summary": (
            "내부 모순이 발견되지 않았습니다." if not issues
            else "치명적 논리 모순이 발견되었습니다." if counts["critical"]
            else "의사결정 계약의 일관성 보강이 필요합니다."
        ),
    }
