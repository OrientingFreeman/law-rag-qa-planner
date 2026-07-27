from __future__ import annotations

from law_rag.generation.planner import AnswerPlan, PlannedSentence

ISSUE_LABELS = {
    "cross_border_transfer": "개인정보 국외이전",
    "processing_delegation": "개인정보 처리위탁",
}


def _all_sentences(plan: AnswerPlan) -> list[tuple[str, PlannedSentence]]:
    return [
        (section.section_id, sentence)
        for section in plan.sections
        for sentence in section.sentences
    ]


def _plain_sentence(sentence: PlannedSentence) -> str:
    return sentence.text.strip().removeprefix("-").strip()


def build_user_answer(plan: AnswerPlan) -> dict[str, object]:
    sections = {section.section_id: section for section in plan.sections}
    conclusion = [_plain_sentence(row) for row in sections.get("conclusion", ()).sentences] if sections.get("conclusion") else []
    requirements = [_plain_sentence(row) for row in sections.get("requirements", ()).sentences] if sections.get("requirements") else []
    actions = [_plain_sentence(row) for row in sections.get("practical_actions", ()).sentences] if sections.get("practical_actions") else []
    cautions = [_plain_sentence(row) for row in sections.get("additional_facts", ()).sentences] if sections.get("additional_facts") else []
    return {
        "mode": "user",
        "summary": conclusion[0] if conclusion else "검색된 법령 근거에 따라 관련 요건을 검토해야 합니다.",
        "conclusions": conclusion,
        "requirements": requirements,
        "practical_actions": actions,
        "cautions": cautions,
        "citation_count": len({citation for _, sentence in _all_sentences(plan) for citation in sentence.citations}),
    }


def build_graph_answer_structure(plan: AnswerPlan) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    previous_id: str | None = None
    for section_id, sentence in _all_sentences(plan):
        node = {
            "node_id": sentence.sentence_id,
            "section_id": section_id,
            "node_type": sentence.sentence_type,
            "issue_id": sentence.issue_id,
            "issue_label": ISSUE_LABELS.get(sentence.issue_id or "", sentence.issue_id),
            "text": sentence.text,
            "citations": list(sentence.citations),
            "evidence_node_ids": [binding.evidence_node_id for binding in sentence.citation_bindings],
        }
        nodes.append(node)
        if previous_id is not None:
            edges.append({"source_id": previous_id, "relation": "followed_by", "target_id": sentence.sentence_id})
        previous_id = sentence.sentence_id
    return {
        "root_node_id": nodes[0]["node_id"] if nodes else None,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def build_reasoning_trace(plan: AnswerPlan) -> list[dict[str, object]]:
    trace: list[dict[str, object]] = []
    for order, (section_id, sentence) in enumerate(_all_sentences(plan), start=1):
        trace.append({
            "order": order,
            "sentence_id": sentence.sentence_id,
            "section_id": section_id,
            "sentence_type": sentence.sentence_type,
            "issue_id": sentence.issue_id,
            "issue_label": ISSUE_LABELS.get(sentence.issue_id or "", sentence.issue_id),
            "source_step": sentence.source_step,
            "source_transition": sentence.source_transition,
            "rendered_text": sentence.rendered_text,
            "citations": list(sentence.citations),
            "evidence_node_ids": [binding.evidence_node_id for binding in sentence.citation_bindings],
            "rendered_hash": sentence.rendered_hash,
        })
    return trace


def build_expert_report(
    plan: AnswerPlan,
    legal_reasoning_path: dict[str, object] | None,
    reasoning_score: dict[str, object],
    reasoning_verification: dict[str, object],
    *,
    legal_logic_tree: dict[str, object] | None = None,
    logic_validation: dict[str, object] | None = None,
    answer_skeleton: dict[str, object] | None = None,
    counter_reasoning: dict[str, object] | None = None,
    rule_competition: dict[str, object] | None = None,
    conflict_resolution: dict[str, object] | None = None,
    decision_trace: dict[str, object] | None = None,
    logic_driven_reasoning_path: dict[str, object] | None = None,
    answer_composer: dict[str, object] | None = None,
    sentence_citation_map: dict[str, object] | None = None,
    missing_fact_detector: dict[str, object] | None = None,
    practical_action_generator: dict[str, object] | None = None,
    legal_argument_graph: dict[str, object] | None = None,
    multi_path_reasoning: dict[str, object] | None = None,
) -> dict[str, object]:
    path = legal_reasoning_path or {}
    return {
        "mode": "expert",
        "auditable": bool(reasoning_verification.get("valid")),
        "reasoning_score": reasoning_score,
        "issue_order": [
            {"issue_id": issue, "label": ISSUE_LABELS.get(str(issue), str(issue))}
            for issue in path.get("issue_order", [])
        ],
        "reasoning_steps": list(path.get("steps", [])),
        "issue_transitions": list(path.get("issue_transitions", [])),
        "answer_contract": dict(path.get("answer_contract", {})),
        "graph_answer_structure": build_graph_answer_structure(plan),
        "reasoning_trace": build_reasoning_trace(plan),
        "legal_logic_tree": legal_logic_tree or {},
        "logic_validation": logic_validation or {},
        "answer_skeleton": answer_skeleton or {},
        "rule_priority": list((legal_logic_tree or {}).get("rule_priority", [])),
        "counter_reasoning": counter_reasoning or {},
        "rule_competition": rule_competition or {},
        "conflict_resolution": conflict_resolution or {},
        "decision_trace": decision_trace or {},
        "logic_driven_reasoning_path": logic_driven_reasoning_path or {},
        "answer_composer": answer_composer or {},
        "sentence_citation_map": sentence_citation_map or {},
        "missing_fact_detector": missing_fact_detector or {},
        "practical_action_generator": practical_action_generator or {},
        "legal_argument_graph": legal_argument_graph or {},
        "multi_path_reasoning": multi_path_reasoning or {},
    }


def build_dual_output(
    plan: AnswerPlan,
    legal_reasoning_path: dict[str, object] | None,
    reasoning_score: dict[str, object],
    reasoning_verification: dict[str, object],
    *,
    legal_logic_tree: dict[str, object] | None = None,
    logic_validation: dict[str, object] | None = None,
    answer_skeleton: dict[str, object] | None = None,
    counter_reasoning: dict[str, object] | None = None,
    rule_competition: dict[str, object] | None = None,
    conflict_resolution: dict[str, object] | None = None,
    decision_trace: dict[str, object] | None = None,
    logic_driven_reasoning_path: dict[str, object] | None = None,
    answer_composer: dict[str, object] | None = None,
    sentence_citation_map: dict[str, object] | None = None,
    missing_fact_detector: dict[str, object] | None = None,
    practical_action_generator: dict[str, object] | None = None,
    legal_argument_graph: dict[str, object] | None = None,
    multi_path_reasoning: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "default_mode": "user",
        "available_modes": ["user", "expert"],
        "user": build_user_answer(plan),
        "expert": build_expert_report(
            plan, legal_reasoning_path, reasoning_score, reasoning_verification,
            legal_logic_tree=legal_logic_tree, logic_validation=logic_validation,
            answer_skeleton=answer_skeleton, counter_reasoning=counter_reasoning,
            rule_competition=rule_competition, conflict_resolution=conflict_resolution,
            decision_trace=decision_trace, logic_driven_reasoning_path=logic_driven_reasoning_path,
            answer_composer=answer_composer, sentence_citation_map=sentence_citation_map,
            missing_fact_detector=missing_fact_detector, practical_action_generator=practical_action_generator,
            legal_argument_graph=legal_argument_graph, multi_path_reasoning=multi_path_reasoning,
        ),
    }
