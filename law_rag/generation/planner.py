from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Iterable

from law_rag.generation.composer import CompositionPlan, LegalRule

ISSUE_LABELS = {
    "cross_border_transfer": "개인정보 국외이전",
    "processing_delegation": "개인정보 처리위탁",
    "privacy_breach": "개인정보 유출 대응",
    "employee_invention": "직무발명",
    "patent_novelty": "특허 신규성",
    "disclosure_exception": "공지예외",
    "work_made_for_hire": "업무상 프로그램 저작자",
    "eft_accident_liability": "전자금융사고 책임",
    "eft_record_retention": "전자금융거래 기록 보존",
    "destruction": "개인정보 파기",
    "eft_terms_notice": "전자금융 약관 고지",
    "eft_dispute_handling": "전자금융 분쟁처리",
}

STEP_LABELS = {
    "identify_issue": "쟁점 확인",
    "apply_primary_rule": "기본 규칙과 요건",
    "check_exception_or_limitation": "예외·금지·범위 제한",
    "check_legal_consequence": "위반 효과",
    "confirm_supplementary_rules": "보충 규정",
    "resolve_rule_conflict": "규칙 충돌 해결",
}


@dataclass(frozen=True)
class CitationBinding:
    citation: str
    source_document_id: str
    evidence_node_id: str
    binding_type: str = "direct"

    def to_dict(self) -> dict[str, str]:
        return {
            "citation": self.citation,
            "source_document_id": self.source_document_id,
            "evidence_node_id": self.evidence_node_id,
            "binding_type": self.binding_type,
        }


@dataclass(frozen=True)
class PlannedSentence:
    sentence_id: str
    sentence_type: str
    issue_id: str | None
    text: str
    citations: tuple[str, ...]
    source_step: int | None = None
    source_transition: str | None = None
    citation_bindings: tuple[CitationBinding, ...] = ()
    rendered_text: str = ""
    rendered_hash: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sentence_id": self.sentence_id,
            "sentence_type": self.sentence_type,
            "issue_id": self.issue_id,
            "text": self.text,
            "citations": list(self.citations),
            "source_step": self.source_step,
            "source_transition": self.source_transition,
            "citation_bindings": [binding.to_dict() for binding in self.citation_bindings],
            "rendered_text": self.rendered_text,
            "rendered_hash": self.rendered_hash,
        }


@dataclass(frozen=True)
class PlannedSection:
    section_id: str
    title: str
    sentences: tuple[PlannedSentence, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "sentences": [sentence.to_dict() for sentence in self.sentences],
        }


@dataclass(frozen=True)
class AnswerPlan:
    issue_order: tuple[str, ...]
    sections: tuple[PlannedSection, ...]
    allowed_citations: tuple[str, ...]
    source_step_order: tuple[int, ...]
    transition_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "issue_order": list(self.issue_order),
            "sections": [section.to_dict() for section in self.sections],
            "allowed_citations": list(self.allowed_citations),
            "source_step_order": list(self.source_step_order),
            "transition_count": self.transition_count,
        }


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _rule_by_citation(plan: CompositionPlan) -> dict[str, LegalRule]:
    return {rule.citation: rule for rule in plan.rules}


def _lead(rule: LegalRule) -> str:
    return rule.text.splitlines()[0].strip()


def _bindings(citations: Iterable[str], plan: CompositionPlan) -> tuple[CitationBinding, ...]:
    lookup = _rule_by_citation(plan)
    rows: list[CitationBinding] = []
    for citation in _unique(citations):
        rule = lookup.get(citation)
        if not rule:
            continue
        node = rule.evidence_nodes[0] if rule.evidence_nodes else None
        rows.append(CitationBinding(
            citation=citation,
            source_document_id=rule.source_document_id,
            evidence_node_id=node.node_id if node else rule.rule_id,
        ))
    return tuple(rows)


def _step_text(step: dict[str, object], plan: CompositionPlan) -> str:
    step_type = str(step.get("type", ""))
    conclusion = str(step.get("conclusion", "")).strip()
    citations = _unique(step.get("citations", []))
    lookup = _rule_by_citation(plan)
    rules = [lookup[citation] for citation in citations if citation in lookup]
    label = STEP_LABELS.get(step_type, step_type or "법적 판단")
    if step_type == "identify_issue":
        return f"{label}: 질문의 사실관계에 이 쟁점이 포함됩니다."
    if rules:
        return f"{label}: {' '.join(_lead(rule) for rule in rules[:2])}"
    if conclusion:
        return f"{label}: {conclusion}."
    return f"{label}: 검색된 근거를 순서대로 검토합니다."


def _practical_text(rule: LegalRule) -> str:
    title = rule.evidence_nodes[0].title if rule.evidence_nodes else rule.article_no
    return f"{title} 사항을 계약서, 고지·동의 화면 또는 내부 절차에 반영하고 실제 이행 여부를 확인합니다."


def _sentence(**kwargs) -> PlannedSentence:
    return PlannedSentence(**kwargs)


def build_answer_plan(
    question: str,
    composition_plan: CompositionPlan,
    legal_reasoning_path: dict[str, object] | None,
    answer_skeleton: dict[str, object] | None = None,
    practical_actions: dict[str, object] | None = None,
    missing_facts: dict[str, object] | None = None,
) -> AnswerPlan:
    path = legal_reasoning_path or {}
    issue_order = tuple(str(item) for item in path.get("issue_order", []))
    steps = [dict(item) for item in path.get("steps", [])]
    transitions = [dict(item) for item in path.get("issue_transitions", [])]
    # The reasoning graph may contain more candidates than the final composition
    # plan can serialize. Keep the answer contract inside the evidence cards that
    # can supply a concrete source binding.
    allowed = _unique(composition_plan.allowed_citations)
    allowed_set = set(allowed)
    citation_issues: dict[str, list[str]] = {}
    for step in steps:
        issue_id = str(step.get("issue_id", "")).strip()
        for citation in _unique(step.get("citations", [])):
            if issue_id and citation in allowed_set:
                citation_issues.setdefault(citation, []).append(issue_id)

    def issue_for_citation(citation: str) -> str | None:
        candidates = _unique(citation_issues.get(citation, []))
        return next((issue for issue in issue_order if issue in candidates), candidates[0] if candidates else None)

    # Do not expose a citation in the final contract when the reasoning path
    # cannot explain which detected issue it supports.
    allowed = tuple(citation for citation in allowed if issue_for_citation(citation))
    allowed_set = set(allowed)

    conclusion: list[PlannedSentence] = []
    for index, transition in enumerate(transitions, start=1):
        citations = tuple(citation for citation in _unique(transition.get("citations", [])) if citation in allowed_set)
        conclusion.append(_sentence(
            sentence_id=f"transition:{index}", sentence_type="issue_transition", issue_id=None,
            text=f"{transition.get('condition')}에는 {transition.get('conclusion')}해야 합니다.",
            citations=citations, source_transition=str(transition.get("relation", "")),
            citation_bindings=_bindings(citations, composition_plan),
        ))
    if not conclusion:
        conclusion.append(_sentence(
            sentence_id="conclusion:1", sentence_type="conclusion", issue_id=issue_order[0] if issue_order else None,
            text="검색된 법령 근거에 따라 질문과 직접 관련된 요건과 제한을 순서대로 검토해야 합니다.",
            citations=allowed[:1], citation_bindings=_bindings(allowed[:1], composition_plan),
        ))

    judgments: list[PlannedSentence] = []
    for step in steps:
        step_no = int(step.get("step", len(judgments) + 1))
        issue_id = str(step.get("issue_id", "")) or None
        citations = tuple(citation for citation in _unique(step.get("citations", [])) if citation in allowed_set)
        judgments.append(_sentence(
            sentence_id=f"step:{step_no}", sentence_type=str(step.get("type", "reasoning_step")), issue_id=issue_id,
            text=_step_text(step, composition_plan), citations=citations, source_step=step_no,
            citation_bindings=_bindings(citations, composition_plan),
        ))

    requirements: list[PlannedSentence] = []
    for index, rule in enumerate(composition_plan.rules, start=1):
        rule_issue = issue_for_citation(rule.citation)
        if not rule_issue:
            continue
        requirements.append(_sentence(
            sentence_id=f"requirement:{index}", sentence_type="rule_requirement", issue_id=rule_issue,
            text=_lead(rule), citations=(rule.citation,), citation_bindings=_bindings((rule.citation,), composition_plan),
        ))
        for node_index, node in enumerate(rule.evidence_nodes[1:4], start=1):
            if node.source_text.strip():
                requirements.append(_sentence(
                    sentence_id=f"requirement:{index}:{node_index}", sentence_type="sub_requirement", issue_id=rule_issue,
                    text=node.source_text.strip(), citations=(node.citation,),
                    citation_bindings=(CitationBinding(node.citation, node.source_document_id, node.node_id),),
                ))

    practical_rows = list((practical_actions or {}).get("actions", []))
    if practical_rows:
        practical = tuple(
            _sentence(
                sentence_id=str(row.get("action_id") or f"action:{index}"),
                sentence_type="practical_action",
                issue_id=str(row.get("issue_id", "")) or None,
                text=f"{row.get('title')}: {row.get('instruction')}",
                citations=_unique(row.get("citations", [])),
                citation_bindings=_bindings(row.get("citations", []), composition_plan),
            )
            for index, row in enumerate(practical_rows, start=1)
        )
    else:
        practical = tuple(_sentence(
            sentence_id=f"action:{index}", sentence_type="practical_action", issue_id=issue_for_citation(rule.citation),
            text=_practical_text(rule), citations=(rule.citation,), citation_bindings=_bindings((rule.citation,), composition_plan),
        ) for index, rule in enumerate(composition_plan.rules, start=1) if issue_for_citation(rule.citation))

    missing_rows = list((missing_facts or {}).get("facts", []))
    if missing_rows:
        additional = tuple(
            _sentence(
                sentence_id=f"additional:{row.get('fact_id', index)}",
                sentence_type="additional_fact",
                issue_id=str(row.get("issue_id", "")) or None,
                # Missing-fact prompts are verification questions, not legal claims.
                # Mark them explicitly so the grounding validator does not score
                # an unanswered question as an unsupported substantive conclusion.
                text=(
                    f"추가 확인 - {row.get('label')}: "
                    f"{str(row.get('question', '')).rstrip('?')} — {row.get('reason')}"
                ),
                citations=(),
            )
            for index, row in enumerate(missing_rows, start=1)
        )
        conclusion.insert(0, _sentence(
            sentence_id="conclusion:conditional",
            sentence_type="conclusion",
            issue_id=issue_order[0] if issue_order else None,
            text="중요 사실이 확인되지 않아 현재 답변은 검색된 근거에 따른 조건부 검토이며 최종 판단이 아닙니다.",
            citations=(),
        ))
    else:
        additional = (_sentence(
            sentence_id="additional:1", sentence_type="additional_fact", issue_id=None,
            text="검색된 근거만으로 추가 확인이 필요한 핵심 사실은 식별되지 않았습니다.", citations=(),
        ),)

    section_map = {
        "conclusion": PlannedSection("conclusion", "결론", tuple(conclusion)),
        "legal_analysis": PlannedSection("legal_analysis", "쟁점별 법적 판단", tuple(judgments)),
        "requirements": PlannedSection("requirements", "적용 요건과 예외", tuple(requirements)),
        "practical_actions": PlannedSection("practical_actions", "실무상 조치", practical),
        "additional_facts": PlannedSection("additional_facts", "추가 확인 사실", additional),
    }
    requested_order = [str(item) for item in (answer_skeleton or {}).get("section_order", [])]
    order = requested_order or list(section_map)
    sections = tuple(section_map[section_id] for section_id in order if section_id in section_map)
    sections += tuple(section for section_id, section in section_map.items() if section_id not in order)
    return AnswerPlan(issue_order, sections, allowed, tuple(int(step.get("step", i)) for i, step in enumerate(steps, 1)), len(transitions))


def _render_sentence(sentence: PlannedSentence) -> str:
    suffix = f" ({', '.join(sentence.citations)})" if sentence.citations else ""
    return f"- {sentence.text}{suffix}"


def bind_rendered_sentences(plan: AnswerPlan) -> AnswerPlan:
    sections: list[PlannedSection] = []
    for section in plan.sections:
        bound = []
        for sentence in section.sentences:
            rendered = _render_sentence(sentence)
            bound.append(replace(sentence, rendered_text=rendered, rendered_hash=sha256(rendered.encode("utf-8")).hexdigest()))
        sections.append(replace(section, sentences=tuple(bound)))
    return replace(plan, sections=tuple(sections))


def serialize_answer_plan(plan: AnswerPlan) -> str:
    lines: list[str] = []
    current_issue: str | None = None
    issue_counter = 0
    for section in plan.sections:
        if lines:
            lines.append("")
        lines.append(section.title)
        current_issue = None
        issue_counter = 0
        for sentence in section.sentences:
            if section.section_id == "legal_analysis" and sentence.issue_id != current_issue:
                current_issue = sentence.issue_id
                issue_counter += 1
                lines.append(f"### {issue_counter}. {ISSUE_LABELS.get(current_issue or '', current_issue or '공통 쟁점')}")
            lines.append(sentence.rendered_text or _render_sentence(sentence))
    return "\n".join(lines).strip()


def validate_sentence_plan(answer: str, plan: AnswerPlan) -> dict[str, object]:
    expected = [s.rendered_text or _render_sentence(s) for sec in plan.sections for s in sec.sentences]
    missing = [s.sentence_id for sec in plan.sections for s in sec.sentences if (s.rendered_text or _render_sentence(s)) not in answer]
    positions: list[int] = []
    cursor = 0
    for text in expected:
        position = answer.find(text, cursor)
        if position >= 0:
            positions.append(position)
            cursor = position + len(text)
    order_valid = len(positions) == len(expected) and positions == sorted(positions)
    unbound = [s.sentence_id for sec in plan.sections for s in sec.sentences if s.citations and not s.citation_bindings]
    hash_invalid = [s.sentence_id for sec in plan.sections for s in sec.sentences if s.rendered_text and sha256(s.rendered_text.encode("utf-8")).hexdigest() != s.rendered_hash]
    return {
        "valid": not missing and order_valid and not unbound and not hash_invalid,
        "sentence_count": len(expected),
        "missing_sentence_ids": missing,
        "sentence_order_valid": order_valid,
        "unbound_citation_sentence_ids": unbound,
        "hash_invalid_sentence_ids": hash_invalid,
    }
