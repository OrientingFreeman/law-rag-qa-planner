from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from law_rag.generation.composer import CompositionPlan, LegalRule

ISSUE_LABELS = {
    "cross_border_transfer": "개인정보 국외이전",
    "processing_delegation": "개인정보 처리위탁",
}

STEP_TO_LOGIC = {
    "apply_primary_rule": "rule",
    "check_exception_or_limitation": "exception",
    "check_legal_consequence": "consequence",
    "confirm_supplementary_rules": "requirement",
    "identify_issue": "issue_marker",
}

PRIORITY_BY_ROLE = {"exception": 10, "primary": 20, "supporting": 30}


@dataclass(frozen=True)
class LogicNode:
    node_id: str
    node_type: str
    issue_id: str | None
    label: str
    conclusion: str
    citations: tuple[str, ...] = ()
    source_step: int | None = None
    source_rule_ids: tuple[str, ...] = ()
    priority: int = 50

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "issue_id": self.issue_id,
            "issue_label": ISSUE_LABELS.get(self.issue_id or "", self.issue_id),
            "label": self.label,
            "conclusion": self.conclusion,
            "citations": list(self.citations),
            "source_step": self.source_step,
            "source_rule_ids": list(self.source_rule_ids),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class LogicEdge:
    source_id: str
    relation: str
    target_id: str

    def to_dict(self) -> dict[str, str]:
        return {"source_id": self.source_id, "relation": self.relation, "target_id": self.target_id}


@dataclass(frozen=True)
class LegalLogicTree:
    root_id: str
    issue_order: tuple[str, ...]
    nodes: tuple[LogicNode, ...]
    edges: tuple[LogicEdge, ...]
    rule_priority: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": True,
            "root_id": self.root_id,
            "issue_order": list(self.issue_order),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "rule_priority": list(self.rule_priority),
        }


def _unique(values: Iterable[object]) -> tuple[str, ...]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            rows.append(text)
    return tuple(rows)


def _rules_by_citation(plan: CompositionPlan) -> dict[str, list[LegalRule]]:
    lookup: dict[str, list[LegalRule]] = {}
    for rule in plan.rules:
        lookup.setdefault(rule.citation, []).append(rule)
    return lookup


def _priority_rows(plan: CompositionPlan, steps: list[dict[str, object]]) -> tuple[dict[str, object], ...]:
    exception_citations = {
        str(citation)
        for step in steps
        if str(step.get("type", "")) == "check_exception_or_limitation"
        for citation in step.get("citations", [])
    }
    effective_roles = {
        rule.rule_id: ("exception" if rule.citation in exception_citations else rule.role)
        for rule in plan.rules
    }
    ordered = sorted(plan.rules, key=lambda rule: (PRIORITY_BY_ROLE.get(effective_roles[rule.rule_id], 40), int(rule.rule_id[1:])))
    return tuple({
        "rank": index,
        "rule_id": rule.rule_id,
        "citation": rule.citation,
        "role": effective_roles[rule.rule_id],
        "retrieval_role": rule.role,
        "basis": "exception_over_primary" if effective_roles[rule.rule_id] == "exception" else ("primary_before_supporting" if effective_roles[rule.rule_id] == "primary" else "supporting_last"),
    } for index, rule in enumerate(ordered, start=1))


def build_legal_logic_tree(
    composition_plan: CompositionPlan,
    legal_reasoning_path: dict[str, object] | None,
) -> LegalLogicTree:
    path = legal_reasoning_path or {}
    issue_order = tuple(str(item) for item in path.get("issue_order", []))
    steps = [dict(item) for item in path.get("steps", [])]
    transitions = [dict(item) for item in path.get("issue_transitions", [])]
    lookup = _rules_by_citation(composition_plan)

    nodes: list[LogicNode] = [LogicNode("logic:root", "root", None, "법적 논리", "질문의 쟁점과 적용 규칙을 구조화합니다.", priority=0)]
    edges: list[LogicEdge] = []

    issue_node_ids: dict[str, str] = {}
    for order, issue_id in enumerate(issue_order, start=1):
        node_id = f"issue:{issue_id}"
        issue_node_ids[issue_id] = node_id
        nodes.append(LogicNode(node_id, "issue", issue_id, ISSUE_LABELS.get(issue_id, issue_id), "쟁점별 규칙·예외·효과를 검토합니다.", priority=order))
        edges.append(LogicEdge("logic:root", "contains_issue", node_id))

    last_by_issue: dict[str, str] = {}
    has_rule: set[str] = set()
    for raw in steps:
        step_type = str(raw.get("type", ""))
        if step_type == "identify_issue":
            continue
        issue_id = str(raw.get("issue_id", "")) or None
        node_type = STEP_TO_LOGIC.get(step_type, "reasoning")
        step_no = int(raw.get("step", len(nodes)))
        citations = _unique(raw.get("citations", []))
        source_rules = _unique(rule.rule_id for citation in citations for rule in lookup.get(citation, []))
        priority = min((PRIORITY_BY_ROLE.get(rule.role, 40) for citation in citations for rule in lookup.get(citation, [])), default=40)
        node_id = f"logic:step:{step_no}"
        nodes.append(LogicNode(
            node_id=node_id,
            node_type=node_type,
            issue_id=issue_id,
            label=str(raw.get("question", "법적 판단")),
            conclusion=str(raw.get("conclusion", "")).strip(),
            citations=citations,
            source_step=step_no,
            source_rule_ids=source_rules,
            priority=priority,
        ))
        parent = issue_node_ids.get(issue_id or "", "logic:root")
        relation = {
            "rule": "applies_rule",
            "exception": "limits_rule",
            "requirement": "supplements_rule",
            "consequence": "produces_consequence",
        }.get(node_type, "supports_reasoning")
        edges.append(LogicEdge(parent, relation, node_id))
        if issue_id and issue_id in last_by_issue:
            edges.append(LogicEdge(last_by_issue[issue_id], "followed_by", node_id))
        if issue_id:
            last_by_issue[issue_id] = node_id
            if node_type == "rule":
                has_rule.add(issue_id)

    for index, transition in enumerate(transitions, start=1):
        target_issue = str(transition.get("target_issue_id", "")) or None
        node_id = f"logic:transition:{index}"
        nodes.append(LogicNode(
            node_id=node_id,
            node_type="conclusion",
            issue_id=target_issue,
            label=str(transition.get("condition", "쟁점 간 적용 관계")),
            conclusion=str(transition.get("conclusion", "")).strip(),
            citations=_unique(transition.get("citations", [])),
            priority=5,
        ))
        edges.append(LogicEdge("logic:root", "concludes_transition", node_id))
        if target_issue in issue_node_ids:
            edges.append(LogicEdge(node_id, "concludes_issue", issue_node_ids[target_issue]))

    # Ensure every covered issue has an explicit conclusion node, without inventing a new legal proposition.
    for issue_id in issue_order:
        node_id = f"logic:conclusion:{issue_id}"
        source = last_by_issue.get(issue_id)
        conclusion = "관련 규칙과 제한을 함께 적용하여 판단합니다." if issue_id in has_rule else "직접 적용 규칙의 추가 확인이 필요합니다."
        nodes.append(LogicNode(node_id, "conclusion", issue_id, f"{ISSUE_LABELS.get(issue_id, issue_id)} 결론", conclusion, priority=90))
        edges.append(LogicEdge(source or issue_node_ids.get(issue_id, "logic:root"), "supports_conclusion", node_id))

    return LegalLogicTree("logic:root", issue_order, tuple(nodes), tuple(edges), _priority_rows(composition_plan, steps))


def validate_legal_logic_tree(tree: LegalLogicTree) -> dict[str, object]:
    nodes = {node.node_id: node for node in tree.nodes}
    issues = [node for node in tree.nodes if node.node_type == "issue"]
    rules_by_issue = {issue.issue_id: [node for node in tree.nodes if node.issue_id == issue.issue_id and node.node_type == "rule"] for issue in issues}
    conclusions_by_issue = {issue.issue_id: [node for node in tree.nodes if node.issue_id == issue.issue_id and node.node_type == "conclusion"] for issue in issues}
    exceptions = [node for node in tree.nodes if node.node_type == "exception"]
    consequences = [node for node in tree.nodes if node.node_type == "consequence"]

    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for issue in issues:
        if not rules_by_issue.get(issue.issue_id):
            errors.append({"code": "missing_rule", "issue_id": issue.issue_id})
        if not conclusions_by_issue.get(issue.issue_id):
            errors.append({"code": "missing_conclusion", "issue_id": issue.issue_id})
    for node in exceptions:
        if not rules_by_issue.get(node.issue_id):
            errors.append({"code": "orphan_exception", "node_id": node.node_id, "issue_id": node.issue_id})
    for node in consequences:
        if not node.citations:
            errors.append({"code": "ungrounded_consequence", "node_id": node.node_id})
    for node in tree.nodes:
        if node.node_type in {"rule", "exception", "requirement", "consequence"} and not node.citations:
            warnings.append({"code": "missing_citation", "node_id": node.node_id})
    dangling = [edge.to_dict() for edge in tree.edges if edge.source_id not in nodes or edge.target_id not in nodes]
    if dangling:
        errors.append({"code": "dangling_edges", "edges": dangling})

    return {
        "valid": not errors,
        "issue_count": len(issues),
        "covered_issue_count": sum(bool(rules_by_issue.get(issue.issue_id) and conclusions_by_issue.get(issue.issue_id)) for issue in issues),
        "rule_count": sum(node.node_type == "rule" for node in tree.nodes),
        "exception_count": len(exceptions),
        "consequence_count": len(consequences),
        "errors": errors,
        "warnings": warnings,
    }


def build_answer_skeleton(tree: LegalLogicTree) -> dict[str, object]:
    nodes_by_issue: dict[str, list[LogicNode]] = {issue: [] for issue in tree.issue_order}
    transition_conclusions: list[LogicNode] = []
    for node in tree.nodes:
        if node.node_type == "conclusion" and node.node_id.startswith("logic:transition:"):
            transition_conclusions.append(node)
        if node.issue_id in nodes_by_issue and node.node_type not in {"issue", "issue_marker"}:
            nodes_by_issue[node.issue_id].append(node)

    return {
        "enabled": True,
        "section_order": ["conclusion", "legal_analysis", "requirements", "practical_actions", "additional_facts"],
        "sections": [
            {"section_id": "conclusion", "source_node_ids": [node.node_id for node in transition_conclusions]},
            {"section_id": "legal_analysis", "issues": [
                {
                    "issue_id": issue,
                    "issue_label": ISSUE_LABELS.get(issue, issue),
                    "source_node_ids": [node.node_id for node in sorted(nodes_by_issue[issue], key=lambda row: (row.source_step or 9999, row.priority)) if node.node_type in {"rule", "exception", "consequence", "requirement"}],
                }
                for issue in tree.issue_order
            ]},
            {"section_id": "requirements", "source_node_ids": [node.node_id for node in tree.nodes if node.node_type in {"rule", "exception", "requirement"}]},
            {"section_id": "practical_actions", "source_node_ids": [node.node_id for node in tree.nodes if node.node_type == "rule"]},
            {"section_id": "additional_facts", "source_node_ids": []},
        ],
    }



def build_rule_competition(tree: LegalLogicTree) -> dict[str, object]:
    """Group source-bound legal rules that may compete within each issue."""
    groups: list[dict[str, object]] = []
    for issue_id in tree.issue_order:
        candidates = [
            node for node in tree.nodes
            if node.issue_id == issue_id and node.node_type in {"rule", "exception", "requirement"}
        ]
        if not candidates:
            continue
        rows = []
        for node in sorted(candidates, key=lambda n: (n.priority, n.source_step or 9999, n.node_id)):
            rows.append({
                "node_id": node.node_id,
                "node_type": node.node_type,
                "conclusion": node.conclusion,
                "citations": list(node.citations),
                "priority": node.priority,
                "source_rule_ids": list(node.source_rule_ids),
            })
        groups.append({
            "competition_id": f"competition:{issue_id}",
            "issue_id": issue_id,
            "issue_label": ISSUE_LABELS.get(issue_id, issue_id),
            "candidate_count": len(rows),
            "has_conflict": any(row["node_type"] == "exception" for row in rows) and any(row["node_type"] == "rule" for row in rows),
            "candidates": rows,
        })
    return {
        "enabled": True,
        "source": "legal_logic_tree",
        "competition_count": len(groups),
        "conflict_candidate_count": sum(bool(group["has_conflict"]) for group in groups),
        "groups": groups,
    }


def resolve_rule_conflicts(
    tree: LegalLogicTree,
    rule_competition: dict[str, object] | None = None,
) -> dict[str, object]:
    """Resolve rule competition deterministically without inventing doctrine.

    Only relations already encoded by node type and priority are used. An
    exception/limitation controls over the primary rule for the scope it
    addresses; otherwise the primary rule remains selected and supplementary
    requirements are retained as cumulative obligations.
    """
    competition = rule_competition or build_rule_competition(tree)
    decisions: list[dict[str, object]] = []
    for group in competition.get("groups", []):
        candidates = list(group.get("candidates", []))
        rules = [row for row in candidates if row.get("node_type") == "rule"]
        exceptions = [row for row in candidates if row.get("node_type") == "exception"]
        requirements = [row for row in candidates if row.get("node_type") == "requirement"]
        selected: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []
        if exceptions and rules:
            selected.extend(exceptions)
            selected.extend(requirements)
            rejected.extend({**row, "rejection_reason": "exception_or_limitation_controls_scope"} for row in rules)
            resolution_type = "exception_controls"
            rationale = "예외·금지·범위 제한 규칙이 기본 규칙의 적용 범위를 제한하므로 제한 해석을 채택합니다."
        else:
            selected.extend(rules)
            selected.extend(requirements)
            resolution_type = "cumulative_application" if requirements else "primary_rule_controls"
            rationale = "직접 충돌하는 예외가 확인되지 않아 기본 규칙을 적용하고 보충 규정은 누적적으로 반영합니다."
        citations = _unique(
            citation
            for row in [*selected, *rejected]
            for citation in row.get("citations", [])
        )
        decisions.append({
            "decision_id": f"decision:{group.get('issue_id')}",
            "competition_id": group.get("competition_id"),
            "issue_id": group.get("issue_id"),
            "issue_label": group.get("issue_label"),
            "resolution_type": resolution_type,
            "selected_node_ids": [row.get("node_id") for row in selected],
            "rejected_node_ids": [row.get("node_id") for row in rejected],
            "rejections": rejected,
            "rationale": rationale,
            "citations": list(citations),
            "resolved": bool(selected),
        })
    return {
        "enabled": True,
        "source_bound": True,
        "decision_count": len(decisions),
        "resolved_count": sum(bool(row["resolved"]) for row in decisions),
        "conflict_count": sum(row["resolution_type"] == "exception_controls" for row in decisions),
        "decisions": decisions,
    }


def build_decision_trace(
    tree: LegalLogicTree,
    rule_competition: dict[str, object],
    conflict_resolution: dict[str, object],
) -> dict[str, object]:
    """Create an auditable accepted/rejected rule trace for each issue."""
    node_lookup = {node.node_id: node for node in tree.nodes}
    traces: list[dict[str, object]] = []
    for decision in conflict_resolution.get("decisions", []):
        selected_ids = [str(item) for item in decision.get("selected_node_ids", [])]
        rejected_ids = [str(item) for item in decision.get("rejected_node_ids", [])]
        steps: list[dict[str, object]] = []
        sequence = 1
        for node_id in selected_ids:
            node = node_lookup.get(node_id)
            if node:
                steps.append({
                    "sequence": sequence,
                    "action": "accepted",
                    "node_id": node_id,
                    "node_type": node.node_type,
                    "reason": decision.get("rationale"),
                    "citations": list(node.citations),
                })
                sequence += 1
        rejection_map = {str(row.get("node_id")): row for row in decision.get("rejections", [])}
        for node_id in rejected_ids:
            node = node_lookup.get(node_id)
            if node:
                steps.append({
                    "sequence": sequence,
                    "action": "rejected_as_unqualified",
                    "node_id": node_id,
                    "node_type": node.node_type,
                    "reason": rejection_map.get(node_id, {}).get("rejection_reason", "lower_priority_rule"),
                    "citations": list(node.citations),
                })
                sequence += 1
        traces.append({
            "trace_id": f"trace:{decision.get('issue_id')}",
            "issue_id": decision.get("issue_id"),
            "issue_label": decision.get("issue_label"),
            "resolution_type": decision.get("resolution_type"),
            "final_rule_node_ids": selected_ids,
            "steps": steps,
        })
    return {
        "enabled": True,
        "source": "conflict_resolution",
        "trace_count": len(traces),
        "traces": traces,
    }

def derive_reasoning_path_from_logic_tree(
    tree: LegalLogicTree,
    original_path: dict[str, object] | None = None,
    conflict_resolution: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create the planner-facing reasoning path from the validated logic tree.

    The original path is retained only for issue-transition metadata and the
    answer contract. Rule, exception, requirement and consequence steps are
    regenerated from logic nodes, making the tree the authoritative source for
    downstream planning.
    """
    original = original_path or {}
    type_map = {
        "rule": "apply_primary_rule",
        "exception": "check_exception_or_limitation",
        "requirement": "confirm_supplementary_rules",
        "consequence": "check_legal_consequence",
    }
    steps: list[dict[str, object]] = []
    step_no = 1
    for issue_id in tree.issue_order:
        issue_node = next((n for n in tree.nodes if n.node_type == "issue" and n.issue_id == issue_id), None)
        issue_citations = tuple(
            citation
            for node in tree.nodes
            if node.issue_id == issue_id and node.node_type in type_map
            for citation in node.citations
        )
        steps.append({
            "step": step_no,
            "type": "identify_issue",
            "issue_id": issue_id,
            "question": f"{ISSUE_LABELS.get(issue_id, issue_id)} 쟁점이 질문 사실관계에 포함되는가?",
            "conclusion": "포함됨",
            "citations": list(_unique(issue_citations))[:2],
            "source_logic_node_id": issue_node.node_id if issue_node else None,
        })
        step_no += 1
        issue_nodes = sorted(
            (n for n in tree.nodes if n.issue_id == issue_id and n.node_type in type_map),
            key=lambda n: (n.source_step or 9999, n.priority, n.node_id),
        )
        for node in issue_nodes:
            steps.append({
                "step": step_no,
                "type": type_map[node.node_type],
                "issue_id": issue_id,
                "question": node.label,
                "conclusion": node.conclusion,
                "citations": list(node.citations),
                "source_logic_node_id": node.node_id,
            })
            step_no += 1

        decision = next((
            row for row in (conflict_resolution or {}).get("decisions", [])
            if str(row.get("issue_id")) == issue_id
        ), None)
        if decision and decision.get("resolved"):
            steps.append({
                "step": step_no,
                "type": "resolve_rule_conflict",
                "issue_id": issue_id,
                "question": "경쟁하는 규칙 중 어떤 규칙을 최종 적용할 것인가?",
                "conclusion": str(decision.get("rationale", "")).strip(),
                "citations": list(decision.get("citations", [])),
                "source_logic_node_id": (list(decision.get("selected_node_ids", [])) or [None])[0],
                "source_decision_id": decision.get("decision_id"),
                "selected_node_ids": list(decision.get("selected_node_ids", [])),
                "rejected_node_ids": list(decision.get("rejected_node_ids", [])),
            })
            step_no += 1

    return {
        "enabled": bool(tree.issue_order),
        "complete": bool(tree.issue_order) and all(
            any(step["issue_id"] == issue and step["type"] == "apply_primary_rule" for step in steps)
            for issue in tree.issue_order
        ),
        "source": "legal_logic_tree",
        "issue_order": list(tree.issue_order),
        "steps": steps,
        "issue_transitions": list(original.get("issue_transitions", [])),
        "answer_contract": dict(original.get("answer_contract", {})),
        "conflict_resolution": conflict_resolution or {},
        "final_instruction": "Legal Logic Tree와 충돌 해결 결정의 순서에 따라 답변을 구성",
    }


def build_counter_reasoning(tree: LegalLogicTree) -> dict[str, object]:
    """Build deterministic, source-bound counter-reasoning candidates.

    This does not invent a contrary legal proposition. It records which rule
    could appear to support a broader reading, which exception or limitation
    narrows it, and why the narrower reading controls in the generated answer.
    """
    rows: list[dict[str, object]] = []
    for issue_id in tree.issue_order:
        rules = [n for n in tree.nodes if n.issue_id == issue_id and n.node_type == "rule"]
        limitations = [n for n in tree.nodes if n.issue_id == issue_id and n.node_type == "exception"]
        for rule in rules:
            if limitations:
                for limitation in limitations:
                    rows.append({
                        "issue_id": issue_id,
                        "issue_label": ISSUE_LABELS.get(issue_id, issue_id),
                        "candidate_interpretation": rule.conclusion,
                        "counter_rule": limitation.conclusion,
                        "resolution": "예외·금지·범위 제한 규칙을 우선 반영",
                        "selected": "limited_interpretation",
                        "rule_node_id": rule.node_id,
                        "counter_node_id": limitation.node_id,
                        "citations": list(_unique([*rule.citations, *limitation.citations])),
                    })
            else:
                rows.append({
                    "issue_id": issue_id,
                    "issue_label": ISSUE_LABELS.get(issue_id, issue_id),
                    "candidate_interpretation": rule.conclusion,
                    "counter_rule": None,
                    "resolution": "검색된 근거에서 직접 충돌하는 예외 규칙이 확인되지 않음",
                    "selected": "primary_rule",
                    "rule_node_id": rule.node_id,
                    "counter_node_id": None,
                    "citations": list(rule.citations),
                })
    return {
        "enabled": True,
        "source_bound": True,
        "candidate_count": len(rows),
        "resolved_count": sum(row["selected"] == "limited_interpretation" for row in rows),
        "candidates": rows,
    }
