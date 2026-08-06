from __future__ import annotations

from dataclasses import dataclass

from law_rag.domain.models import SearchResult
from law_rag.generation.citations import validate_citations
from law_rag.generation.answer_composer import (
    build_answer_composer, build_conditional_review, build_missing_fact_detector,
    build_practical_action_generator, build_sentence_citation_map,
)
from law_rag.generation.composer import (
    build_composition_plan,
    build_presentation_outline,
    compose_evidence_fallback,
    repair_ambiguous_article_citations,
)
from law_rag.generation.grounding import validate_grounding
from law_rag.generation.prompt import build_grounded_prompt
from law_rag.generation.planner import build_answer_plan, bind_rendered_sentences, serialize_answer_plan, validate_sentence_plan
from law_rag.generation.providers import GenerationError, LlmProvider
from law_rag.generation.presentation import build_dual_output
from law_rag.reasoning import (
    build_answer_skeleton, build_counter_reasoning, build_decision_trace,
    build_legal_logic_tree, build_rule_competition, resolve_rule_conflicts,
    derive_reasoning_path_from_logic_tree, validate_legal_logic_tree,
)
from law_rag.reasoning.legal_argument_graph import build_legal_argument_graph
from law_rag.reasoning.multi_path import build_multi_path_reasoning
from law_rag.generation.verifier import (
    analyze_semantic_citation_coverage,
    build_explainability_report,
    build_reasoning_score,
    verify_reasoning_plan,
)


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    provider: str
    model: str
    citation_validation: dict[str, object]
    generation_status: str
    grounding_validation: dict[str, object]
    composition: dict[str, object]
    error: str | None = None
    request_id: str | None = None
    usage: dict[str, int] | None = None




def _validate_answer_contract(answer: str, legal_reasoning_path: dict[str, object] | None) -> dict[str, object]:
    path = legal_reasoning_path or {}
    contract = path.get("answer_contract", {}) if isinstance(path, dict) else {}
    sections = [str(item) for item in contract.get("section_order", [])]
    positions = {section: answer.find(section) for section in sections}
    missing = [section for section, pos in positions.items() if pos < 0]
    present_positions = [positions[section] for section in sections if positions[section] >= 0]
    order_valid = present_positions == sorted(present_positions)
    transitions = path.get("issue_transitions", []) if isinstance(path, dict) else []
    transition_required = bool(contract.get("must_explain_transitions"))
    transition_terms = ("추가 적용", "누적적으로", "함께 적용", "별도로")
    transition_explained = (not transition_required) or any(term in answer for term in transition_terms)
    valid = not missing and order_valid and transition_explained
    return {
        "valid": valid,
        "missing_sections": missing,
        "section_order_valid": order_valid,
        "transition_required": transition_required,
        "transition_explained": transition_explained,
        "expected_sections": sections,
    }


def _compose_contract_fallback(
    question: str,
    plan,
    legal_reasoning_path: dict[str, object] | None,
) -> str:
    path = legal_reasoning_path or {}
    issue_order = [str(item) for item in path.get("issue_order", [])]
    transitions = list(path.get("issue_transitions", []))
    labels = {
        "cross_border_transfer": "개인정보 국외이전",
        "processing_delegation": "개인정보 처리위탁",
    }
    rules = list(plan.rules)
    lines = ["결론", "검색된 근거를 기준으로 아래 쟁점과 조문을 순서대로 확인합니다.", "", "쟁점별 법적 판단"]
    if issue_order:
        for index, issue in enumerate(issue_order, start=1):
            label = labels.get(issue, issue)
            lines.append(f"### {index}. {label}")
            issue_rules = [rule for rule in rules if (issue == "processing_delegation" and rule.article_no == "제26조") or (issue == "cross_border_transfer" and rule.article_no == "제28조의8") or (issue == "cross_border_transfer" and rule.article_no == "제28조의9")]
            for rule in issue_rules or rules[:1]:
                lead = rule.text.splitlines()[0].strip()
                lines.append(f"- {rule.evidence_nodes[0].title}: {lead} ({rule.citation})")
            for row in transitions:
                if str(row.get("source_issue_id")) == issue:
                    cites = row.get("citations") or []
                    suffix = f" ({cites[0]})" if cites else ""
                    lines.append(f"- 쟁점 전이: {row.get('condition')}에는 {row.get('conclusion')}됩니다.{suffix}")
                    break
    else:
        for index, rule in enumerate(rules, start=1):
            lines.append(f"### {index}. 검색 근거")
            lines.append(f"- {rule.evidence_nodes[0].title}: {rule.text.splitlines()[0].strip()} ({rule.citation})")

    lines.extend(["", "적용 요건과 예외"])
    for rule in rules:
        lead = rule.text.splitlines()[0].strip()
        lines.append(f"- {rule.evidence_nodes[0].title}: {lead} ({rule.citation})")
        for node in rule.evidence_nodes[1:4]:
            if node.source_text.strip():
                lines.append(f"  - {node.source_text.strip()} ({node.citation})")

    lines.extend(["", "실무상 조치"])
    for rule in rules:
        lead = rule.text.splitlines()[0].strip()
        lines.append(f"- 다음 근거 문구를 실제 문서와 절차에 대조합니다: {lead} ({rule.citation})")

    lines.extend(["", "추가 확인 사실", "- 구체적 사실관계와 하위 규정의 적용 여부는 추가 확인이 필요합니다."])
    return "\n".join(lines).strip()


def generate_grounded_answer(
    question: str,
    results: list[SearchResult],
    provider: LlmProvider,
    *,
    reasoning_chain: list[dict[str, object]] | None = None,
    legal_intent: dict[str, object] | None = None,
    legal_reasoning_path: dict[str, object] | None = None,
) -> AnswerResult:
    if not results:
        return AnswerResult(
            answer=(
                "검색된 법령 근거가 없어 답변을 생성하지 않았습니다. "
                "질문 범위나 도메인을 조정한 뒤 다시 검색해야 합니다."
            ),
            provider=provider.name,
            model="none",
            citation_validation={
                "valid": True,
                "cited_articles": [],
                "retrieved_articles": [],
                "unsupported_articles": [],
            },
            generation_status="abstained",
            grounding_validation={"valid": True, "claim_count": 0, "supported_claim_count": 0, "coverage": 1.0, "unsupported_claims": [], "claims": []},
            composition={"mode": "abstained", "fallback_used": False, "citation_repairs": [], "plan": {"rules": [], "allowed_citations": [], "required_actions": []}},
        )

    plan = build_composition_plan(results, legal_intent)
    prompt = build_grounded_prompt(
        question,
        results,
        reasoning_chain=reasoning_chain,
        legal_intent=legal_intent,
        legal_reasoning_path=legal_reasoning_path,
        composition_plan=plan,
    )
    try:
        output = provider.generate(prompt)
    except GenerationError as exc:
        return AnswerResult(
            answer="LLM 답변 생성에 실패했습니다. 검색 결과와 grounding prompt는 정상적으로 생성되었습니다.",
            provider=provider.name,
            model="unknown",
            citation_validation={
                "valid": False,
                "cited_articles": [],
                "retrieved_articles": sorted({r.provision.article_no for r in results}),
                "unsupported_articles": [],
            },
            generation_status="failed",
            grounding_validation={"valid": False, "claim_count": 0, "supported_claim_count": 0, "coverage": 0.0, "unsupported_claims": [], "claims": []},
            composition={"mode": "failed", "fallback_used": False, "citation_repairs": [], "plan": plan.to_dict()},
            error=str(exc),
        )

    repaired_text, repairs = repair_ambiguous_article_citations(output.text, results)
    initial_citations = validate_citations(repaired_text, results)
    initial_grounding = validate_grounding(repaired_text, results)
    initial_contract = _validate_answer_contract(repaired_text, legal_reasoning_path)
    minimum_coverage = 0.80
    fallback_used = (
        (not initial_citations["valid"])
        or (not initial_grounding["valid"])
        or float(initial_grounding["coverage"]) < minimum_coverage
        or (not initial_contract["valid"])
    )

    legal_logic_tree = build_legal_logic_tree(plan, legal_reasoning_path)
    logic_validation = validate_legal_logic_tree(legal_logic_tree)
    answer_skeleton = build_answer_skeleton(legal_logic_tree)
    counter_reasoning = build_counter_reasoning(legal_logic_tree)
    rule_competition = build_rule_competition(legal_logic_tree)
    conflict_resolution = resolve_rule_conflicts(legal_logic_tree, rule_competition)
    decision_trace = build_decision_trace(legal_logic_tree, rule_competition, conflict_resolution)
    logic_driven_reasoning_path = derive_reasoning_path_from_logic_tree(
        legal_logic_tree, legal_reasoning_path, conflict_resolution
    )
    missing_fact_detector = build_missing_fact_detector(question, plan, legal_intent)
    practical_action_generator = build_practical_action_generator(plan, legal_intent)
    conditional_review = build_conditional_review(missing_fact_detector, practical_action_generator)
    answer_plan = bind_rendered_sentences(build_answer_plan(
        question, plan, logic_driven_reasoning_path, answer_skeleton=answer_skeleton,
        practical_actions=practical_action_generator, missing_facts=missing_fact_detector,
    ))
    answer_composer = build_answer_composer(answer_plan, logic_driven_reasoning_path)
    sentence_citation_map = build_sentence_citation_map(answer_plan)
    legal_argument_graph = build_legal_argument_graph(
        question, plan, answer_plan, logic_driven_reasoning_path,
        counter_reasoning=counter_reasoning,
        conflict_resolution=conflict_resolution,
        missing_fact_detector=missing_fact_detector,
    )
    multi_path_reasoning = build_multi_path_reasoning(
        question, plan, logic_driven_reasoning_path,
        legal_argument_graph=legal_argument_graph,
        missing_fact_detector=missing_fact_detector,
        conflict_resolution=conflict_resolution,
    )
    planner_enabled = bool(logic_driven_reasoning_path.get("enabled")) and bool(logic_driven_reasoning_path.get("steps"))
    final_text = serialize_answer_plan(answer_plan) if planner_enabled else (_compose_contract_fallback(question, plan, legal_reasoning_path) if fallback_used else repaired_text)
    validation = validate_citations(final_text, results)
    grounding = validate_grounding(final_text, results)
    sentence_plan_validation = validate_sentence_plan(final_text, answer_plan)
    reasoning_verification = verify_reasoning_plan(answer_plan, logic_driven_reasoning_path)
    semantic_citation_coverage = analyze_semantic_citation_coverage(answer_plan)
    reasoning_score = build_reasoning_score(
        reasoning_verification, semantic_citation_coverage, sentence_plan_validation
    )
    explainability_report = build_explainability_report(
        answer_plan, reasoning_verification, semantic_citation_coverage, reasoning_score
    )
    dual_output = build_dual_output(
        answer_plan, logic_driven_reasoning_path, reasoning_score, reasoning_verification,
        legal_logic_tree=legal_logic_tree.to_dict(),
        logic_validation=logic_validation,
        answer_skeleton=answer_skeleton,
        counter_reasoning=counter_reasoning,
        rule_competition=rule_competition,
        conflict_resolution=conflict_resolution,
        decision_trace=decision_trace,
        logic_driven_reasoning_path=logic_driven_reasoning_path,
        answer_composer=answer_composer,
        sentence_citation_map=sentence_citation_map,
        missing_fact_detector=missing_fact_detector,
        practical_action_generator=practical_action_generator,
        conditional_review=conditional_review,
        legal_argument_graph=legal_argument_graph,
        multi_path_reasoning=multi_path_reasoning,
    )
    status = "completed" if validation["valid"] else "citation_invalid"
    return AnswerResult(
        answer=final_text,
        provider=output.provider,
        model=output.model,
        citation_validation=validation,
        generation_status=status,
        grounding_validation=grounding,
        composition={
            "mode": "sentence_plan_bound" if planner_enabled else ("evidence_fallback" if fallback_used else "llm_composed"),
            "fallback_used": fallback_used,
            "minimum_grounding_coverage": minimum_coverage,
            "citation_repairs": repairs,
            "initial_citation_validation": initial_citations,
            "initial_grounding_coverage": initial_grounding["coverage"],
            "answer_contract_validation": _validate_answer_contract(final_text, logic_driven_reasoning_path),
            "initial_answer_contract_validation": initial_contract,
            "repair_reason": "reasoning_plan_serialization" if planner_enabled else ("answer_contract_or_grounding" if fallback_used else None),
            "answer_plan": answer_plan.to_dict(),
            "sentence_plan_validation": sentence_plan_validation,
            "reasoning_verification": reasoning_verification,
            "semantic_citation_coverage": semantic_citation_coverage,
            "reasoning_score": reasoning_score,
            "explainability_report": explainability_report,
            "dual_output": dual_output,
            "graph_answer_structure": dual_output["expert"]["graph_answer_structure"],
            "reasoning_trace": dual_output["expert"]["reasoning_trace"],
            "legal_logic_tree": legal_logic_tree.to_dict(),
            "logic_validation": logic_validation,
            "answer_skeleton": answer_skeleton,
            "rule_priority": list(legal_logic_tree.rule_priority),
            "counter_reasoning": counter_reasoning,
            "rule_competition": rule_competition,
            "conflict_resolution": conflict_resolution,
            "decision_trace": decision_trace,
            "logic_driven_reasoning_path": logic_driven_reasoning_path,
            "answer_composer": answer_composer,
            "sentence_citation_map": sentence_citation_map,
            "missing_fact_detector": missing_fact_detector,
            "practical_action_generator": practical_action_generator,
            "conditional_review": conditional_review,
            "legal_argument_graph": legal_argument_graph,
            "multi_path_reasoning": multi_path_reasoning,
            "citation_binding_count": sum(len(sentence.citation_bindings) for section in answer_plan.sections for sentence in section.sentences),
            "planner_enabled": planner_enabled,
            "plan": plan.to_dict(),
            "presentation": build_presentation_outline(plan),
        },
        request_id=output.request_id,
        usage=output.usage,
    )
