from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from law_rag.generation.planner import AnswerPlan, PlannedSentence


def _sentences(plan: AnswerPlan) -> list[PlannedSentence]:
    return [sentence for section in plan.sections for sentence in section.sentences]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def verify_reasoning_plan(
    answer_plan: AnswerPlan,
    legal_reasoning_path: dict[str, object] | None,
) -> dict[str, object]:
    path = legal_reasoning_path or {}
    sentences = _sentences(answer_plan)

    expected_steps = [int(row.get("step")) for row in path.get("steps", []) if row.get("step") is not None]
    mapped_steps = [int(sentence.source_step) for sentence in sentences if sentence.source_step is not None]
    missing_steps = [step for step in expected_steps if step not in mapped_steps]
    unexpected_steps = [step for step in mapped_steps if step not in expected_steps]
    step_order_valid = [step for step in mapped_steps if step in expected_steps] == expected_steps

    expected_transitions = [str(row.get("relation", "")) for row in path.get("issue_transitions", [])]
    mapped_transitions = [str(sentence.source_transition) for sentence in sentences if sentence.source_transition]
    missing_transitions = [relation for relation in expected_transitions if relation not in mapped_transitions]

    expected_issues = [str(issue) for issue in path.get("issue_order", [])]
    mapped_issues = {str(sentence.issue_id) for sentence in sentences if sentence.issue_id}
    missing_issues = [issue for issue in expected_issues if issue not in mapped_issues]

    contract = path.get("answer_contract", {}) if isinstance(path, dict) else {}
    required_sections = [str(section) for section in contract.get("section_order", [])]
    actual_sections = [section.title for section in answer_plan.sections]
    missing_sections = [section for section in required_sections if section not in actual_sections]

    step_coverage = _ratio(len(expected_steps) - len(missing_steps), len(expected_steps))
    transition_coverage = _ratio(len(expected_transitions) - len(missing_transitions), len(expected_transitions))
    issue_coverage = _ratio(len(expected_issues) - len(missing_issues), len(expected_issues))
    section_coverage = _ratio(len(required_sections) - len(missing_sections), len(required_sections))

    valid = not any((missing_steps, unexpected_steps, missing_transitions, missing_issues, missing_sections)) and step_order_valid
    return {
        "valid": valid,
        "expected_step_count": len(expected_steps),
        "mapped_step_count": len(mapped_steps),
        "missing_steps": missing_steps,
        "unexpected_steps": unexpected_steps,
        "step_order_valid": step_order_valid,
        "expected_transition_count": len(expected_transitions),
        "mapped_transition_count": len(mapped_transitions),
        "missing_transitions": missing_transitions,
        "missing_issues": missing_issues,
        "missing_sections": missing_sections,
        "step_coverage": step_coverage,
        "transition_coverage": transition_coverage,
        "issue_coverage": issue_coverage,
        "section_coverage": section_coverage,
    }


def analyze_semantic_citation_coverage(answer_plan: AnswerPlan) -> dict[str, object]:
    sentences = _sentences(answer_plan)
    cited_sentences = [sentence for sentence in sentences if sentence.citations]
    bound_sentences = [sentence for sentence in cited_sentences if sentence.citation_bindings]
    grounded_sentences = [
        sentence for sentence in cited_sentences
        if {binding.citation for binding in sentence.citation_bindings}.issuperset(set(sentence.citations))
    ]

    all_evidence_nodes = {
        binding.evidence_node_id
        for sentence in sentences
        for binding in sentence.citation_bindings
        if binding.evidence_node_id
    }
    used_evidence_nodes = {
        binding.evidence_node_id
        for sentence in cited_sentences
        for binding in sentence.citation_bindings
        if binding.evidence_node_id
    }
    all_citations = set(answer_plan.allowed_citations)
    used_citations = {citation for sentence in cited_sentences for citation in sentence.citations}

    unbound_sentence_ids = [sentence.sentence_id for sentence in cited_sentences if not sentence.citation_bindings]
    partially_bound_sentence_ids = [
        sentence.sentence_id for sentence in cited_sentences
        if sentence.citation_bindings
        and not {binding.citation for binding in sentence.citation_bindings}.issuperset(set(sentence.citations))
    ]

    return {
        "valid": not unbound_sentence_ids and not partially_bound_sentence_ids,
        "sentence_count": len(sentences),
        "cited_sentence_count": len(cited_sentences),
        "bound_sentence_count": len(bound_sentences),
        "fully_grounded_sentence_count": len(grounded_sentences),
        "sentence_binding_coverage": _ratio(len(bound_sentences), len(cited_sentences)),
        "semantic_grounding_coverage": _ratio(len(grounded_sentences), len(cited_sentences)),
        "used_citations": sorted(used_citations),
        "unused_allowed_citations": sorted(all_citations - used_citations),
        "used_evidence_node_ids": sorted(used_evidence_nodes),
        "unused_evidence_node_ids": sorted(all_evidence_nodes - used_evidence_nodes),
        "unbound_sentence_ids": unbound_sentence_ids,
        "partially_bound_sentence_ids": partially_bound_sentence_ids,
    }


def build_reasoning_score(
    reasoning_verification: dict[str, object],
    citation_coverage: dict[str, object],
    sentence_plan_validation: dict[str, object],
) -> dict[str, object]:
    components = {
        "step_coverage": float(reasoning_verification.get("step_coverage", 0.0)),
        "transition_coverage": float(reasoning_verification.get("transition_coverage", 0.0)),
        "issue_coverage": float(reasoning_verification.get("issue_coverage", 0.0)),
        "section_coverage": float(reasoning_verification.get("section_coverage", 0.0)),
        "citation_binding_coverage": float(citation_coverage.get("sentence_binding_coverage", 0.0)),
        "semantic_grounding_coverage": float(citation_coverage.get("semantic_grounding_coverage", 0.0)),
        "sentence_plan_integrity": 1.0 if sentence_plan_validation.get("valid") else 0.0,
        "step_order_integrity": 1.0 if reasoning_verification.get("step_order_valid") else 0.0,
    }
    weights = {
        "step_coverage": 0.20,
        "transition_coverage": 0.15,
        "issue_coverage": 0.10,
        "section_coverage": 0.10,
        "citation_binding_coverage": 0.15,
        "semantic_grounding_coverage": 0.15,
        "sentence_plan_integrity": 0.10,
        "step_order_integrity": 0.05,
    }
    score = round(sum(components[key] * weights[key] for key in components), 4)
    if score >= 0.95:
        level = "high"
    elif score >= 0.80:
        level = "medium"
    else:
        level = "low"
    return {"score": score, "level": level, "components": components, "weights": weights}


def build_explainability_report(
    answer_plan: AnswerPlan,
    reasoning_verification: dict[str, object],
    citation_coverage: dict[str, object],
    reasoning_score: dict[str, object],
) -> dict[str, object]:
    trace: list[dict[str, object]] = []
    for section in answer_plan.sections:
        for sentence in section.sentences:
            trace.append({
                "sentence_id": sentence.sentence_id,
                "section_id": section.section_id,
                "sentence_type": sentence.sentence_type,
                "issue_id": sentence.issue_id,
                "source_step": sentence.source_step,
                "source_transition": sentence.source_transition,
                "citations": list(sentence.citations),
                "evidence_node_ids": [binding.evidence_node_id for binding in sentence.citation_bindings],
                "rendered_hash": sentence.rendered_hash,
            })
    return {
        "auditable": bool(reasoning_verification.get("valid")) and bool(citation_coverage.get("valid")),
        "reasoning_score": reasoning_score,
        "summary": {
            "sentence_count": len(trace),
            "reasoning_step_count": int(reasoning_verification.get("expected_step_count", 0)),
            "transition_count": int(reasoning_verification.get("expected_transition_count", 0)),
            "used_citation_count": len(citation_coverage.get("used_citations", [])),
            "used_evidence_node_count": len(citation_coverage.get("used_evidence_node_ids", [])),
        },
        "reasoning_verification": reasoning_verification,
        "semantic_citation_coverage": citation_coverage,
        "sentence_trace": trace,
    }
