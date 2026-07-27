from __future__ import annotations

from collections import Counter
from typing import Iterable

from law_rag.generation.composer import CompositionPlan
from law_rag.generation.planner import AnswerPlan

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


def _node(node_id: str, node_type: str, label: str, **payload: object) -> dict[str, object]:
    return {"node_id": node_id, "node_type": node_type, "label": label, **payload}


def _edge(source_id: str, relation: str, target_id: str, *, confidence: float = 1.0, reason: str = "") -> dict[str, object]:
    return {
        "source_id": source_id,
        "relation": relation,
        "target_id": target_id,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "reason": reason,
    }


def _counter_rows(counter_reasoning: dict[str, object] | None) -> list[dict[str, object]]:
    payload = counter_reasoning or {}
    for key in ("alternatives", "counter_arguments", "rows", "arguments"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def build_legal_argument_graph(
    question: str,
    composition_plan: CompositionPlan,
    answer_plan: AnswerPlan,
    legal_reasoning_path: dict[str, object] | None = None,
    *,
    counter_reasoning: dict[str, object] | None = None,
    conflict_resolution: dict[str, object] | None = None,
    missing_fact_detector: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a deterministic, source-bound legal argument graph.

    The graph is an argumentation layer rather than a retrieval graph. It connects
    legal issues and unresolved facts to rules, planned applications, counterarguments,
    conclusions, and their evidence provenance.
    """
    path = legal_reasoning_path or {}
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    node_ids: set[str] = set()

    def add_node(row: dict[str, object]) -> None:
        node_id = str(row["node_id"])
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append(row)

    add_node(_node("question:root", "question", question, text=question))

    issue_order = _unique(path.get("issue_order", answer_plan.issue_order))
    issue_ids = set(issue_order)
    for section in answer_plan.sections:
        for sentence in section.sentences:
            if sentence.issue_id:
                issue_ids.add(str(sentence.issue_id))
    for issue_id in sorted(issue_ids, key=lambda value: (issue_order.index(value) if value in issue_order else 999, value)):
        issue_node_id = f"issue:{issue_id}"
        add_node(_node(issue_node_id, "issue", ISSUE_LABELS.get(issue_id, issue_id), issue_id=issue_id))
        edges.append(_edge("question:root", "raises", issue_node_id, reason="질문에서 식별된 법적 쟁점"))

    evidence_ids: dict[str, str] = {}
    rule_ids: dict[str, str] = {}
    for rule in composition_plan.rules:
        rule_node_id = f"rule:{rule.rule_id}"
        rule_ids[rule.rule_id] = rule_node_id
        issue_id = next((issue for issue in issue_ids if issue in str(rule.to_dict())), None)
        add_node(_node(
            rule_node_id,
            "rule",
            rule.citation,
            rule_id=rule.rule_id,
            citation=rule.citation,
            article_no=rule.article_no,
            role=rule.role,
            text=rule.text,
            source_document_id=rule.source_document_id,
            issue_id=issue_id,
        ))
        if issue_id:
            edges.append(_edge(rule_node_id, "governs", f"issue:{issue_id}", confidence=0.95, reason="해당 쟁점을 규율하는 검색 근거"))
        for evidence in rule.evidence_nodes:
            evidence_node_id = f"evidence:{evidence.node_id}"
            evidence_ids[evidence.node_id] = evidence_node_id
            add_node(_node(
                evidence_node_id,
                "evidence",
                evidence.title,
                evidence_node_id=evidence.node_id,
                citation=evidence.citation,
                source_document_id=evidence.source_document_id,
                source_text=evidence.source_text,
            ))
            edges.append(_edge(evidence_node_id, "supports", rule_node_id, confidence=1.0, reason="규칙을 구성한 직접 법령 근거"))

    sentence_nodes: dict[str, str] = {}
    conclusion_ids: list[str] = []
    application_ids: list[str] = []
    fact_ids: list[str] = []
    role_by_type = {
        "identify_issue": "fact",
        "additional_fact": "fact",
        "apply_primary_rule": "rule_claim",
        "check_exception_or_limitation": "rule_claim",
        "confirm_supplementary_rules": "rule_claim",
        "rule_requirement": "rule_claim",
        "sub_requirement": "rule_claim",
        "check_legal_consequence": "application",
        "resolve_rule_conflict": "application",
        "practical_action": "application",
        "issue_transition": "conclusion",
        "conclusion": "conclusion",
    }
    previous_by_issue: dict[str, str] = {}
    for section in answer_plan.sections:
        for sentence in section.sentences:
            semantic_type = role_by_type.get(sentence.sentence_type, "application")
            node_id = f"claim:{sentence.sentence_id}"
            sentence_nodes[sentence.sentence_id] = node_id
            add_node(_node(
                node_id,
                semantic_type,
                sentence.text,
                sentence_id=sentence.sentence_id,
                sentence_type=sentence.sentence_type,
                section_id=section.section_id,
                issue_id=sentence.issue_id,
                text=sentence.text,
                citations=list(sentence.citations),
                source_step=sentence.source_step,
                rendered_hash=sentence.rendered_hash,
            ))
            if semantic_type == "conclusion":
                conclusion_ids.append(node_id)
            elif semantic_type == "application":
                application_ids.append(node_id)
            elif semantic_type == "fact":
                fact_ids.append(node_id)

            if sentence.issue_id and f"issue:{sentence.issue_id}" in node_ids:
                relation = "frames" if semantic_type == "fact" else "addresses"
                edges.append(_edge(f"issue:{sentence.issue_id}", relation, node_id, reason="쟁점별 답변 계획 연결"))
                previous = previous_by_issue.get(str(sentence.issue_id))
                if previous:
                    edges.append(_edge(previous, "leads_to", node_id, confidence=0.9, reason="동일 쟁점 내 논증 순서"))
                previous_by_issue[str(sentence.issue_id)] = node_id

            for binding in sentence.citation_bindings:
                evidence_node_id = evidence_ids.get(binding.evidence_node_id)
                if evidence_node_id:
                    edges.append(_edge(evidence_node_id, "supports", node_id, confidence=1.0, reason="문장 단위 인용 바인딩"))

    # Explicit reasoning-path dependencies connect statutory steps to planned claims.
    step_claims = {str(node.get("source_step")): str(node["node_id"]) for node in nodes if node.get("source_step")}
    for step in path.get("steps", []):
        if not isinstance(step, dict):
            continue
        claim_id = step_claims.get(str(step.get("step")))
        issue_id = str(step.get("issue_id") or "")
        if claim_id and issue_id and f"issue:{issue_id}" in node_ids:
            edges.append(_edge(f"issue:{issue_id}", "requires_analysis", claim_id, confidence=0.95, reason=str(step.get("question") or "법적 판단 단계")))

    # Missing facts are explicit assumptions/gaps, never silently treated as established facts.
    for fact in (missing_fact_detector or {}).get("facts", []):
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id") or "unknown")
        node_id = f"missing_fact:{fact_id}"
        issue_id = str(fact.get("issue_id") or "")
        add_node(_node(node_id, "missing_fact", str(fact.get("label") or fact_id), issue_id=issue_id, question=fact.get("question"), reason=fact.get("reason"), material=bool(fact.get("material", True))))
        if issue_id and f"issue:{issue_id}" in node_ids:
            edges.append(_edge(node_id, "conditions", f"issue:{issue_id}", confidence=1.0, reason="사실 확인 결과에 따라 법적 적용 경로가 달라질 수 있음"))
        for conclusion_id in conclusion_ids:
            conclusion = next((node for node in nodes if node["node_id"] == conclusion_id), {})
            if not issue_id or conclusion.get("issue_id") == issue_id:
                edges.append(_edge(node_id, "limits", conclusion_id, confidence=0.9, reason="미확인 중요 사실로 인해 결론 확정성이 제한됨"))

    # Counterarguments attack a target conclusion/application while retaining their own sources.
    for index, row in enumerate(_counter_rows(counter_reasoning), start=1):
        node_id = f"counterargument:{index}"
        text = str(row.get("argument") or row.get("interpretation") or row.get("reason") or row.get("conclusion") or "대안 해석")
        issue_id = str(row.get("issue_id") or "")
        citations = _unique(row.get("citations", [])) if isinstance(row.get("citations"), list) else []
        add_node(_node(node_id, "counterargument", text, issue_id=issue_id or None, text=text, citations=citations, status=row.get("status") or row.get("disposition")))
        targets = [node for node in [*application_ids, *conclusion_ids] if not issue_id or next((n for n in nodes if n["node_id"] == node), {}).get("issue_id") == issue_id]
        for target in targets[-1:]:
            edges.append(_edge(node_id, "attacks", target, confidence=0.8, reason="검색 근거 내 대안 해석 또는 제한 논거"))

    resolution = conflict_resolution or {}
    selected_rule_ids = _unique(resolution.get("selected_rule_ids", [])) if isinstance(resolution.get("selected_rule_ids"), list) else []
    rejected_rule_ids = _unique(resolution.get("rejected_rule_ids", [])) if isinstance(resolution.get("rejected_rule_ids"), list) else []
    for rule_id in selected_rule_ids:
        if rule_id in rule_ids:
            for target in conclusion_ids[-1:]:
                edges.append(_edge(rule_ids[rule_id], "justifies", target, confidence=1.0, reason="충돌 해결에서 채택된 규칙"))
    for rule_id in rejected_rule_ids:
        if rule_id in rule_ids:
            for target in conclusion_ids[-1:]:
                edges.append(_edge(rule_ids[rule_id], "defeated_for", target, confidence=0.9, reason="충돌 해결에서 배제된 규칙"))

    # Deduplicate deterministic edges and discard dangling references.
    valid_edges: list[dict[str, object]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for row in edges:
        marker = (str(row["source_id"]), str(row["relation"]), str(row["target_id"]))
        if marker in seen_edges or marker[0] not in node_ids or marker[2] not in node_ids:
            continue
        seen_edges.add(marker)
        valid_edges.append(row)

    type_counts = Counter(str(node["node_type"]) for node in nodes)
    relation_counts = Counter(str(edge["relation"]) for edge in valid_edges)
    supported_claim_ids = {str(edge["target_id"]) for edge in valid_edges if edge["relation"] == "supports" and str(edge["target_id"]).startswith("claim:")}
    citation_required_claims = [node for node in nodes if str(node["node_id"]).startswith("claim:") and node.get("citations")]
    unsupported_claims = [str(node["node_id"]) for node in citation_required_claims if str(node["node_id"]) not in supported_claim_ids]

    return {
        "enabled": True,
        "graph_type": "legal_argument_graph",
        "version": "1.0",
        "root_node_id": "question:root",
        "node_count": len(nodes),
        "edge_count": len(valid_edges),
        "node_type_counts": dict(sorted(type_counts.items())),
        "relation_counts": dict(sorted(relation_counts.items())),
        "issue_order": issue_order,
        "conclusion_node_ids": conclusion_ids,
        "validation": {
            "valid": not unsupported_claims,
            "dangling_edge_count": 0,
            "citation_required_claim_count": len(citation_required_claims),
            "supported_claim_count": len(citation_required_claims) - len(unsupported_claims),
            "unsupported_claim_ids": unsupported_claims,
        },
        "nodes": nodes,
        "edges": valid_edges,
    }
