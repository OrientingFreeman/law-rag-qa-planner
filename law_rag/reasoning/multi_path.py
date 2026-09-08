from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

MAX_CONCRETE_BASIS_PATHS = 3

from law_rag.generation.composer import CompositionPlan, LegalRule
from law_rag.reasoning.legal_strategy import (
    build_strategy_comparison,
    build_decision_support,
    explain_non_recommendation,
    explain_recommendation,
    recommendation_score,
    strategy_profile,
)
from law_rag.reasoning.reasoning_quality import build_reasoning_quality_score
from law_rag.reasoning.failure_analyzer import build_failure_analysis
from law_rag.reasoning.consistency_checker import build_consistency_report
from law_rag.reasoning.scenario_simulation import build_scenario_simulation

ISSUE_LABELS = {
    "cross_border_transfer": "개인정보 국외이전",
    "processing_delegation": "개인정보 처리위탁",
}


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            rows.append(value)
    return rows


def _issue_for_rule(rule: LegalRule) -> str | None:
    article = rule.article_no.replace(" ", "")
    if article == "제26조":
        return "processing_delegation"
    if article in {"제28조의8", "제28조의9"}:
        return "cross_border_transfer"
    return None


def _branch_key(text: str, index: int) -> str:
    match = re.match(r"^\s*(\d+)\.", text)
    return match.group(1) if match else str(index)


def _branch_title(text: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", text).strip()


def _display_title(text: str, limit: int = 60) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _fact_index(missing_fact_detector: dict[str, object] | None) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for fact in (missing_fact_detector or {}).get("facts", []):
        if isinstance(fact, dict) and fact.get("fact_id"):
            rows[str(fact["fact_id"])] = fact
    return rows


def _required_facts(issue_id: str, branch_key: str | None = None) -> list[str]:
    if issue_id == "processing_delegation":
        return ["delegation_purpose", "delegate_identity", "subdelegation"]
    if issue_id != "cross_border_transfer":
        return []

    baseline = ["transfer_basis", "transfer_country", "transfer_items", "recipient_safeguards"]
    branch_requirements = {
        "1": ["consent_obtained", "consent_notice_items", "transfer_country", "transfer_items", "recipient_identity"],
        "2": ["special_legal_basis", "legal_basis_scope", "transfer_country", "transfer_items"],
        "3": ["contract_necessity", "delegation_or_storage", "transfer_country", "transfer_items", "transfer_notice_method"],
        "4": ["recipient_certification", "certification_scope", "recipient_safeguards", "local_implementation"],
        "5": ["adequacy_recognition", "recognition_scope", "transfer_country", "recipient_safeguards"],
    }
    branch = branch_requirements.get(branch_key)
    return ["transfer_basis", *branch] if branch else baseline


def _path_status(required_fact_ids: list[str], facts: dict[str, dict[str, object]]) -> tuple[str, list[str]]:
    missing = [fact_id for fact_id in required_fact_ids if fact_id in facts]
    if missing:
        return "conditional", missing
    return "available", []


def _rule_score(rule: LegalRule) -> float:
    role_weight = 1.0 if rule.role == "primary" else 0.72
    source_weight = 1.0 if rule.evidence_nodes else 0.6
    return round(0.65 * role_weight + 0.35 * source_weight, 4)


def _not_applicable_result(question: str, issue_order: list[str]) -> dict[str, object]:
    """Return a neutral result when the query does not contain branching legal paths."""

    return {
        "enabled": False,
        "applicable": False,
        "status": "not_applicable",
        "engine": "multi_path_reasoning",
        "version": "1.8",
        "question": question,
        "issue_order": issue_order,
        "path_count": 0,
        "candidate_path_count": 0,
        "pruned_path_count": 0,
        "max_concrete_basis_paths": MAX_CONCRETE_BASIS_PATHS,
        "alternative_path_count": 0,
        "cumulative_path_count": 0,
        "cumulative_basis_path_count": 0,
        "status_counts": {},
        "path_type_counts": {},
        "recommended_path_id": None,
        "recommended_path_rank": None,
        "ranking_mode": "not_applicable",
        "recommendation_reason": "분기형 법적 경로가 필요한 질문이 아닙니다.",
        "recommended_path_confidence": None,
        "recommended_path_recommendation_score": None,
        "strategy_comparison": {"enabled": False, "recommended_path_id": None, "alternatives": []},
        "decision_support": {
            "enabled": False,
            "recommended_path_id": None,
            "why_selected": [],
            "why_not_selected": [],
            "tradeoff_summary": None,
            "when_to_switch": [],
            "required_next_facts": [],
        },
        "reasoning_quality": {
            "enabled": False,
            "status": "not_applicable",
            "overall_score": None,
            "overall_percent": None,
            "grade": "not_applicable",
            "components": {},
            "strengths": [],
            "weaknesses": [],
        },
        "failure_analysis": {
            "enabled": False,
            "status": "not_applicable",
            "failure_count": 0,
            "critical_failure_count": 0,
            "high_failure_count": 0,
            "primary_failure": None,
            "failures": [],
            "missing_fact_ids": [],
            "validation_valid": True,
            "safe_to_execute": None,
            "summary": "분기형 경로 평가 대상이 아닙니다.",
        },
        "consistency_report": {
            "enabled": False,
            "status": "not_applicable",
            "consistent": True,
            "issue_count": 0,
            "severity_counts": {},
            "issues": [],
            "checked_rules": [],
            "summary": "분기형 경로 평가 대상이 아닙니다.",
        },
        "scenario_simulation": {
            "enabled": False,
            "mode": "not_applicable",
            "scenario_count": 0,
            "scenarios": [],
            "limitations": [],
        },
        "strategy_layer": {"enabled": False, "dimensions": []},
        "confidence_model": {"version": "1.0", "components": [], "weights": {}},
        "all_paths_conditional": False,
        "validation": {
            "valid": True,
            "applicable": False,
            "dangling_dependency_ids": [],
            "unbound_evidence_node_ids": [],
            "duplicate_path_id_count": 0,
        },
        "paths": [],
    }


def build_multi_path_reasoning(
    question: str,
    composition_plan: CompositionPlan,
    legal_reasoning_path: dict[str, object] | None = None,
    *,
    legal_argument_graph: dict[str, object] | None = None,
    missing_fact_detector: dict[str, object] | None = None,
    conflict_resolution: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build deterministic alternative and cumulative legal reasoning paths.

    A path is an independently auditable candidate route. Alternative statutory
    bases are separated, while distinct issues can be combined into a cumulative
    compliance path. Unknown facts keep a route conditional rather than being
    silently assumed.
    """
    reasoning_path = legal_reasoning_path or {}
    facts = _fact_index(missing_fact_detector)
    issue_order = _unique(reasoning_path.get("issue_order", []))
    rules_by_issue: dict[str, list[LegalRule]] = {}
    for rule in composition_plan.rules:
        issue_id = _issue_for_rule(rule)
        if issue_id:
            rules_by_issue.setdefault(issue_id, []).append(rule)
            if issue_id not in issue_order:
                issue_order.append(issue_id)

    selected_rule_ids = set()
    resolution = conflict_resolution or {}
    if isinstance(resolution.get("selected_rule_ids"), list):
        selected_rule_ids = {str(value) for value in resolution["selected_rule_ids"]}

    paths: list[dict[str, object]] = []

    def add_path(
        path_id: str,
        path_type: str,
        title: str,
        issue_ids: list[str],
        rules: list[LegalRule],
        *,
        branch_key: str | None = None,
        branch_text: str | None = None,
        branch_node: object | None = None,
        depends_on: list[str] | None = None,
    ) -> None:
        required_fact_ids = _unique(
            fact_id for issue_id in issue_ids for fact_id in _required_facts(issue_id, branch_key)
        )
        status, missing = _path_status(required_fact_ids, facts)
        branch_citation = str(getattr(branch_node, "citation", "") or "")
        branch_node_id = str(getattr(branch_node, "node_id", "") or "")
        citations = _unique(([branch_citation] if branch_citation else []) + [rule.citation for rule in rules])
        evidence_node_ids = _unique(
            ([branch_node_id] if branch_node_id else [])
            + [node.node_id for rule in rules for node in rule.evidence_nodes]
        )
        evidence_strength = sum(_rule_score(rule) for rule in rules) / max(1, len(rules))
        fact_completeness = 1.0 - (len(missing) / max(1, len(required_fact_ids)))
        issue_coverage = len(set(issue_ids)) / max(1, len(set(issue_order)))
        directness = 1.0 if branch_node_id and branch_citation else (0.82 if path_type == "issue_baseline" else 0.88)
        selection_support = 1.0 if any(rule.rule_id in selected_rule_ids for rule in rules) else 0.75
        context_fit = 0.9 if branch_key == "3" and "processing_delegation" in issue_order else 0.75
        # Context may distinguish otherwise equal candidates, but cannot overcome
        # unresolved path-specific facts by itself.
        confidence_components = {
            "evidence_strength": round(evidence_strength, 4),
            "fact_completeness": round(fact_completeness, 4),
            "issue_coverage": round(issue_coverage, 4),
            "directness": round(directness, 4),
            "selection_support": round(selection_support, 4),
            "context_fit": round(context_fit, 4),
        }
        confidence = round(max(0.0, min(1.0,
            0.34 * evidence_strength
            + 0.30 * fact_completeness
            + 0.16 * issue_coverage
            + 0.10 * directness
            + 0.06 * selection_support
            + 0.04 * context_fit
        )), 4)
        profile = strategy_profile(path_type, branch_key, status)
        recommendation = recommendation_score(
            confidence, profile, issue_coverage=issue_coverage, status=status
        )
        score = confidence
        paths.append({
            "path_id": path_id,
            "path_type": path_type,
            "title": title,
            "display_title": _display_title(title),
            "issue_ids": issue_ids,
            "issue_labels": [ISSUE_LABELS.get(issue_id, issue_id) for issue_id in issue_ids],
            "status": status,
            "branch_key": branch_key,
            "branch_text": branch_text,
            "source_rule_ids": [rule.rule_id for rule in rules],
            "source_document_ids": _unique(rule.source_document_id for rule in rules),
            "citations": citations,
            "evidence_node_ids": evidence_node_ids,
            "required_fact_ids": required_fact_ids,
            "missing_fact_ids": missing,
            "depends_on_path_ids": depends_on or [],
            "score": score,
            "confidence": confidence,
            "confidence_components": confidence_components,
            "recommendation_score": recommendation,
            "strategy_profile": profile,
            "conclusion": (
                "현재 확인된 근거만으로는 조건부 경로이며 누락 사실 확인이 필요합니다."
                if status == "conditional"
                else "현재 확인된 근거상 적용 가능한 경로입니다."
            ),
        })

    # One baseline path per identified issue.
    for issue_id in issue_order:
        issue_rules = rules_by_issue.get(issue_id, [])
        if not issue_rules:
            continue
        add_path(
            f"path:{issue_id}:baseline",
            "issue_baseline",
            f"{ISSUE_LABELS.get(issue_id, issue_id)} 기본 적용 경로",
            [issue_id],
            issue_rules,
        )

        # Statutory sub-provisions under a primary rule are alternative bases.
        for rule in issue_rules:
            children = [node for node in rule.evidence_nodes if node.node_type == "sub_provision"]
            if issue_id != "cross_border_transfer" or len(children) < 2:
                continue
            # Only top-level numbered alternatives become independent paths;
            # nested 가/나 requirements remain evidence of their parent route.
            top_level = [node for node in children if re.match(r"^\s*\d+\.", node.source_text)]
            for index, node in enumerate(top_level, start=1):
                key = _branch_key(node.source_text, index)
                add_path(
                    f"path:{issue_id}:basis:{key}",
                    "alternative_basis",
                    f"국외이전 근거 {key}: {_branch_title(node.source_text)}",
                    [issue_id],
                    [rule],
                    branch_key=key,
                    branch_text=node.source_text,
                    branch_node=node,
                )
            break

    # Distinct issues are cumulative, not competing, when the question raises both.
    baseline_ids = [f"path:{issue}:baseline" for issue in issue_order if rules_by_issue.get(issue)]
    if len(baseline_ids) >= 2:
        combined_rules = [rule for issue in issue_order for rule in rules_by_issue.get(issue, [])]
        add_path(
            "path:cumulative:all_issues",
            "cumulative",
            "복수 쟁점 누적 적용 경로",
            issue_order,
            combined_rules,
            depends_on=baseline_ids,
        )

        # Bind each concrete cross-border basis to the other mandatory issue baseline.
        delegation_id = "path:processing_delegation:baseline"
        if delegation_id in baseline_ids:
            transfer_rule = next(iter(rules_by_issue.get("cross_border_transfer", [])), None)
            if transfer_rule:
                top_level = [
                    node for node in transfer_rule.evidence_nodes
                    if node.node_type == "sub_provision" and re.match(r"^\s*\d+\.", node.source_text)
                ]
                for index, node in enumerate(top_level, start=1):
                    key = _branch_key(node.source_text, index)
                    basis_id = f"path:cross_border_transfer:basis:{key}"
                    add_path(
                        f"path:cumulative:delegation+basis:{key}",
                        "cumulative_basis",
                        f"처리위탁 + 국외이전 근거 {key} 누적 경로",
                        ["processing_delegation", "cross_border_transfer"],
                        combined_rules,
                        branch_key=key,
                        branch_text=node.source_text,
                        branch_node=node,
                        depends_on=[delegation_id, basis_id],
                    )

    # Candidate pruning: retain mandatory baselines and the generic cumulative
    # route, then keep only the strongest concrete basis pairs. This prevents
    # path explosion while preserving auditable dependencies.
    before_pruning_count = len(paths)
    if before_pruning_count == 0:
        return _not_applicable_result(question, issue_order)
    concrete = [row for row in paths if row["path_type"] == "cumulative_basis"]
    concrete.sort(key=lambda row: (-float(row["confidence"]), str(row["path_id"])))
    kept_concrete = concrete[:MAX_CONCRETE_BASIS_PATHS]
    kept_concrete_ids = {str(row["path_id"]) for row in kept_concrete}
    required_basis_ids = {
        dependency
        for row in kept_concrete
        for dependency in row["depends_on_path_ids"]
        if ":basis:" in str(dependency)
    }
    retained: list[dict[str, object]] = []
    for row in paths:
        path_type = str(row["path_type"])
        path_id = str(row["path_id"])
        if path_type == "cumulative_basis" and path_id not in kept_concrete_ids:
            continue
        if concrete and path_type == "alternative_basis" and path_id not in required_basis_ids:
            continue
        retained.append(row)
    paths = retained

    full_issue_set = set(issue_order)
    full_coverage = [row for row in paths if set(row["issue_ids"]) == full_issue_set and len(full_issue_set) > 1]
    available_full = [row for row in full_coverage if row["status"] == "available"]
    if available_full:
        recommended = max(available_full, key=lambda row: float(row["confidence"]))
        recommendation_reason = "복합질문의 모든 필수 쟁점을 충족하고 사실관계가 확인된 구체적 경로를 우선했습니다."
    elif full_coverage:
        generic = next((row for row in full_coverage if row["path_id"] == "path:cumulative:all_issues"), None)
        recommended = generic or max(full_coverage, key=lambda row: float(row["confidence"]))
        recommendation_reason = "경로별 핵심 사실이 미확정이므로 특정 법적 근거를 단정하지 않고 전체 쟁점 누적 경로를 우선했습니다."
    else:
        available = [row for row in paths if row["status"] == "available"]
        recommended = max(available or paths, key=lambda row: float(row["confidence"])) if paths else None
        recommendation_reason = "단일 쟁점에서 확인된 사실과 분해 신뢰도를 기준으로 선택했습니다." if recommended else None

    if recommended:
        recommended["recommendation_reasons"] = explain_recommendation(recommended, paths)
    for row in paths:
        if recommended and row["path_id"] != recommended["path_id"]:
            row["recommendation_reasons"] = explain_non_recommendation(row, recommended)
        else:
            row.setdefault("recommendation_reasons", [])

    # Recommendation score is the public ranking value. The selected route is
    # still pinned first when a conservative legal policy overrides a marginal
    # score difference; all remaining paths are sorted by recommendation score.
    confidence_order = sorted(paths, key=lambda row: (-float(row["confidence"]), str(row["path_id"])))
    for rank, row in enumerate(confidence_order, start=1):
        row["confidence_rank"] = rank
    paths.sort(key=lambda row: (
        0 if recommended and row["path_id"] == recommended["path_id"] else 1,
        -float(row["recommendation_score"]),
        -float(row["confidence"]),
        str(row["path_id"]),
    ))
    for rank, row in enumerate(paths, start=1):
        row["rank"] = rank
        row["is_recommended"] = bool(recommended and row["path_id"] == recommended["path_id"])

    strategy_comparison = build_strategy_comparison(paths, recommended)
    decision_support = build_decision_support(paths, recommended, recommendation_reason, strategy_comparison)

    path_ids = {str(row["path_id"]) for row in paths}
    dangling_dependencies = [
        dependency
        for row in paths
        for dependency in row["depends_on_path_ids"]
        if dependency not in path_ids
    ]
    status_counts = Counter(str(row["status"]) for row in paths)
    type_counts = Counter(str(row["path_type"]) for row in paths)
    alternative_paths = [row for row in paths if row["path_type"] == "alternative_basis"]

    graph_node_ids = {
        str(node.get("node_id")) for node in (legal_argument_graph or {}).get("nodes", []) if isinstance(node, dict)
    }
    unbound_evidence = _unique(
        evidence_id for row in paths for evidence_id in row["evidence_node_ids"]
        if graph_node_ids and f"evidence:{evidence_id}" not in graph_node_ids
    )

    validation = {
        "valid": not dangling_dependencies and not unbound_evidence and bool(paths),
        "dangling_dependency_ids": dangling_dependencies,
        "unbound_evidence_node_ids": unbound_evidence,
        "duplicate_path_id_count": len(paths) - len(path_ids),
    }
    reasoning_quality = build_reasoning_quality_score(
        paths, recommended, validation, decision_support, strategy_comparison
    )
    failure_analysis = build_failure_analysis(reasoning_quality, recommended, validation, paths)
    consistency_report = build_consistency_report(
        paths, recommended, validation, strategy_comparison, decision_support
    )
    scenario_simulation = build_scenario_simulation(paths, recommended, decision_support)

    return {
        "enabled": True,
        "engine": "multi_path_reasoning",
        "version": "1.8",
        "question": question,
        "issue_order": issue_order,
        "path_count": len(paths),
        "candidate_path_count": before_pruning_count,
        "pruned_path_count": before_pruning_count - len(paths),
        "max_concrete_basis_paths": MAX_CONCRETE_BASIS_PATHS,
        "alternative_path_count": len(alternative_paths),
        "cumulative_path_count": sum(str(row["path_type"]).startswith("cumulative") for row in paths),
        "cumulative_basis_path_count": sum(row["path_type"] == "cumulative_basis" for row in paths),
        "status_counts": dict(sorted(status_counts.items())),
        "path_type_counts": dict(sorted(type_counts.items())),
        "recommended_path_id": recommended["path_id"] if recommended else None,
        "recommended_path_rank": 1 if recommended else None,
        "ranking_mode": "recommended_policy_override_then_recommendation_score_then_confidence",
        "recommendation_reason": recommendation_reason,
        "recommended_path_confidence": recommended["confidence"] if recommended else None,
        "recommended_path_recommendation_score": recommended["recommendation_score"] if recommended else None,
        "strategy_comparison": strategy_comparison,
        "decision_support": decision_support,
        "reasoning_quality": reasoning_quality,
        "failure_analysis": failure_analysis,
        "consistency_report": consistency_report,
        "scenario_simulation": scenario_simulation,
        "strategy_layer": {
            "enabled": True,
            "version": "1.3",
            "dimensions": ["legal_risk", "implementation_cost", "implementation_speed", "proof_burden", "reversibility"],
            "note": "confidence는 분석상 지지 정도이고 recommendation_score는 실행 추천 우선도입니다.",
        },
        "confidence_model": {
            "version": "1.0",
            "components": ["evidence_strength", "fact_completeness", "issue_coverage", "directness", "selection_support", "context_fit"],
            "weights": {"evidence_strength": 0.34, "fact_completeness": 0.30, "issue_coverage": 0.16, "directness": 0.10, "selection_support": 0.06, "context_fit": 0.04},
        },
        "all_paths_conditional": bool(paths) and all(row["status"] == "conditional" for row in paths),
        "validation": validation,
        "paths": paths,
    }
