from __future__ import annotations

from typing import Iterable

from law_rag.generation.composer import CompositionPlan, LegalRule
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


def _rule_for_article(plan: CompositionPlan, article: str) -> LegalRule | None:
    normalized = article.replace(" ", "")
    return next((rule for rule in plan.rules if rule.article_no == normalized), None)


def build_missing_fact_detector(
    question: str,
    composition_plan: CompositionPlan,
    legal_intent: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return concrete unanswered facts that can materially change the legal route.

    The detector does not infer facts. It only records questions to verify before
    applying the retrieved rules to an actual transaction.
    """
    intent = legal_intent or {}
    actions = {str(item) for item in intent.get("actions", [])}
    lowered = question.lower()
    candidates: list[dict[str, object]] = []

    def add(fact_id: str, label: str, question_text: str, reason: str, issue_id: str) -> None:
        if fact_id not in {row["fact_id"] for row in candidates}:
            candidates.append({
                "fact_id": fact_id,
                "issue_id": issue_id,
                "issue_label": ISSUE_LABELS.get(issue_id, issue_id),
                "label": label,
                "question": question_text,
                "reason": reason,
                "material": True,
            })

    if "처리위탁" in actions or "위탁" in question:
        add("delegation_purpose", "위탁 목적과 업무 범위", "수탁자에게 맡기는 구체적인 업무와 처리 범위는 무엇인가?", "문서화할 위탁업무와 범위 초과 여부를 판단하기 위해 필요합니다.", "processing_delegation")
        add("delegate_identity", "수탁자와 재수탁자", "직접 수탁자와 재수탁자가 누구이며 각자의 역할은 무엇인가?", "계약·관리·감독 대상을 특정하기 위해 필요합니다.", "processing_delegation")
        if "재위탁" not in lowered:
            add("subdelegation", "재위탁 여부", "수탁자가 다른 사업자에게 업무를 다시 위탁하는가?", "재위탁 구조와 추가 관리조치의 필요성을 확인하기 위해 필요합니다.", "processing_delegation")

    if "국외이전" in actions or "국외" in question or "해외" in question:
        add("transfer_country", "이전 국가", "개인정보가 실제로 저장·조회·처리되는 국가는 어디인가?", "이전 국가와 보호체계를 특정하기 위해 필요합니다.", "cross_border_transfer")
        add("transfer_basis", "국외이전의 법적 근거", "별도 동의, 계약 이행상 필요성 등 어떤 국외이전 근거를 적용할 것인가?", "허용되는 국외이전 근거를 선택하기 위해 필요합니다.", "cross_border_transfer")
        add("transfer_items", "이전 정보와 시기", "이전되는 개인정보 항목, 이전 시기와 방법, 보유·이용 기간은 무엇인가?", "고지·공개 또는 동의 대상 사항을 확정하기 위해 필요합니다.", "cross_border_transfer")
        add("recipient_safeguards", "국외 수령자의 보호조치", "국외 수령자가 적용하는 안전조치와 정보주체 권리보장 절차는 무엇인가?", "국외이전 후 보호수준과 계약상 조치를 검토하기 위해 필요합니다.", "cross_border_transfer")
        # Basis-specific facts keep alternative statutory routes independently evaluable.
        add("consent_obtained", "국외이전 별도 동의", "정보주체로부터 국외이전에 관한 별도 동의를 받았는가?", "제1호 동의 경로의 성립 여부를 판단하기 위해 필요합니다.", "cross_border_transfer")
        add("consent_notice_items", "동의 고지사항", "별도 동의 시 법정 고지사항을 모두 제시했는가?", "동의의 적법성과 구체성을 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("recipient_identity", "국외 수령자 신원", "개인정보를 이전받는 자는 누구인가?", "동의·고지 및 보호조치의 상대방을 특정하기 위해 필요합니다.", "cross_border_transfer")
        add("special_legal_basis", "특별 법적 근거", "국외이전을 허용하는 법률·조약·국제협정의 특별 규정이 존재하는가?", "제2호 경로의 직접 근거를 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("legal_basis_scope", "특별 근거의 적용범위", "해당 특별 규정이 이번 이전의 대상과 방식에 적용되는가?", "특별 규정의 적용범위를 검토하기 위해 필요합니다.", "cross_border_transfer")
        add("contract_necessity", "계약 이행상 필요성", "정보주체와의 계약 체결·이행을 위해 국외 위탁·보관이 필요한가?", "제3호 경로의 필요성 요건을 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("delegation_or_storage", "위탁·보관 해당성", "국외이전 방식이 처리위탁 또는 보관에 해당하는가?", "제3호가 허용하는 이전 유형인지 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("transfer_notice_method", "공개·통지 방식", "처리방침 공개 또는 개별 통지 중 어느 방식으로 이전사항을 알렸는가?", "제3호의 공개·통지 요건을 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("recipient_certification", "국외 수령자 인증", "국외 수령자가 보호위원회 고시 인증을 유효하게 보유하고 있는가?", "제4호 인증 경로의 성립 여부를 판단하기 위해 필요합니다.", "cross_border_transfer")
        add("certification_scope", "인증 적용범위", "해당 인증이 이번 처리와 이전 범위를 포함하는가?", "인증의 실질적 적용 여부를 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("local_implementation", "이전국 내 인증사항 이행", "인증받은 보호조치를 이전 국가에서 실제로 이행할 수 있는가?", "제4호의 현지 이행 요건을 확인하기 위해 필요합니다.", "cross_border_transfer")
        add("adequacy_recognition", "동등성 인정", "이전 국가 또는 국제기구가 보호위원회의 동등성 인정을 받았는가?", "제5호 경로의 성립 여부를 판단하기 위해 필요합니다.", "cross_border_transfer")
        add("recognition_scope", "동등성 인정 범위", "동등성 인정의 범위와 조건이 이번 이전에 적용되는가?", "인정 결정의 적용범위를 확인하기 위해 필요합니다.", "cross_border_transfer")

    return {
        "enabled": True,
        "source": "question_and_legal_intent",
        "missing_fact_count": len(candidates),
        "complete_for_final_advice": not candidates,
        "facts": candidates,
    }


def build_practical_action_generator(
    composition_plan: CompositionPlan,
    legal_intent: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create a source-bound operational checklist from retrieved rules."""
    intent = legal_intent or {}
    actions = {str(item) for item in intent.get("actions", [])}
    rows: list[dict[str, object]] = []

    def add(action_id: str, title: str, instruction: str, rule: LegalRule | None, issue_id: str, *, order: int) -> None:
        if not rule:
            return
        rows.append({
            "action_id": action_id,
            "order": order,
            "issue_id": issue_id,
            "issue_label": ISSUE_LABELS.get(issue_id, issue_id),
            "title": title,
            "instruction": instruction,
            "citations": [rule.citation],
            "source_rule_ids": [rule.rule_id],
            "source_document_ids": [rule.source_document_id],
        })

    delegation = _rule_for_article(composition_plan, "제26조")
    transfer = _rule_for_article(composition_plan, "제28조의8")
    sanction = _rule_for_article(composition_plan, "제28조의9")

    if "처리위탁" in actions or delegation:
        add("document_delegation", "위탁계약 문서화", "위탁업무 목적 외 처리 금지, 보호조치 등 검색된 필수사항을 포함해 위탁계약을 문서로 작성합니다.", delegation, "processing_delegation", order=10)
        add("control_delegate_scope", "수탁자 처리범위 통제", "수탁자가 위탁받은 업무 범위를 초과해 이용하거나 제3자에게 제공하지 않도록 권한과 절차를 통제합니다.", delegation, "processing_delegation", order=20)

    if "국외이전" in actions or transfer:
        add("select_transfer_basis", "국외이전 근거 확정", "별도 동의, 계약 이행상 필요성 등 검색된 허용 근거 중 실제 거래에 적용할 근거를 하나 이상 확정합니다.", transfer, "cross_border_transfer", order=30)
        add("disclose_transfer_details", "국외이전 사항 고지·공개", "이전 항목, 국가, 시기·방법, 수령자, 이용 목적과 보유기간 등 적용 근거가 요구하는 사항을 고지하거나 처리방침에 공개합니다.", transfer, "cross_border_transfer", order=40)
        add("contract_safeguards", "국외 수령자 보호조치 반영", "국외 수령자의 안전조치, 권리보장과 계약상 의무를 확인하고 관련 문서에 반영합니다.", transfer, "cross_border_transfer", order=50)

    if sanction:
        add("monitor_transfer_compliance", "이전 중지 위험 점검", "국외이전 요건 위반이나 보호수준 저하가 발생하지 않는지 정기적으로 점검하고 시정 절차를 마련합니다.", sanction, "cross_border_transfer", order=60)

    rows.sort(key=lambda row: (int(row["order"]), str(row["action_id"])))
    return {
        "enabled": True,
        "source_bound": True,
        "action_count": len(rows),
        "actions": rows,
    }


def build_answer_composer(
    answer_plan: AnswerPlan,
    legal_reasoning_path: dict[str, object] | None = None,
) -> dict[str, object]:
    """Expose the final plan as an auditable IRAC-style composition model."""
    path = legal_reasoning_path or {}
    role_map = {
        "identify_issue": "fact",
        "apply_primary_rule": "rule",
        "check_exception_or_limitation": "rule",
        "confirm_supplementary_rules": "rule",
        "check_legal_consequence": "application",
        "resolve_rule_conflict": "application",
        "issue_transition": "conclusion",
        "conclusion": "conclusion",
        "rule_requirement": "rule",
        "sub_requirement": "rule",
        "practical_action": "application",
        "additional_fact": "fact",
    }
    blocks: list[dict[str, object]] = []
    for section in answer_plan.sections:
        sentences = []
        for sentence in section.sentences:
            sentences.append({
                "sentence_id": sentence.sentence_id,
                "irac_role": role_map.get(sentence.sentence_type, "application"),
                "sentence_type": sentence.sentence_type,
                "issue_id": sentence.issue_id,
                "text": sentence.text,
                "citations": list(sentence.citations),
                "source_step": sentence.source_step,
            })
        blocks.append({
            "section_id": section.section_id,
            "title": section.title,
            "sentences": sentences,
        })
    counts = {role: 0 for role in ("fact", "rule", "application", "conclusion")}
    for block in blocks:
        for sentence in block["sentences"]:
            counts[str(sentence["irac_role"])] += 1
    return {
        "enabled": True,
        "framework": "FRAC",
        "framework_labels": ["fact", "rule", "application", "conclusion"],
        "issue_order": list(path.get("issue_order", answer_plan.issue_order)),
        "role_counts": counts,
        "blocks": blocks,
    }


def build_sentence_citation_map(answer_plan: AnswerPlan) -> dict[str, object]:
    """Publish sentence-level citation bindings as a stable audit surface."""
    rows: list[dict[str, object]] = []
    for section in answer_plan.sections:
        for sentence in section.sentences:
            rows.append({
                "sentence_id": sentence.sentence_id,
                "section_id": section.section_id,
                "rendered_hash": sentence.rendered_hash,
                "citations": list(sentence.citations),
                "bindings": [binding.to_dict() for binding in sentence.citation_bindings],
                "citation_required": bool(sentence.citations),
                "fully_bound": (not sentence.citations) or len(sentence.citation_bindings) == len(sentence.citations),
            })
    required = [row for row in rows if row["citation_required"]]
    return {
        "enabled": True,
        "sentence_count": len(rows),
        "citation_required_count": len(required),
        "fully_bound_count": sum(bool(row["fully_bound"]) for row in required),
        "valid": all(bool(row["fully_bound"]) for row in required),
        "sentences": rows,
    }
