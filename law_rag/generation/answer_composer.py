from __future__ import annotations

from typing import Iterable

from law_rag.generation.composer import CompositionPlan, LegalRule
from law_rag.generation.planner import AnswerPlan


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

PRIORITY_LABELS = {1: "핵심", 2: "중요", 3: "추가"}


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


def _rule_for_citation(plan: CompositionPlan, law_name: str, article: str) -> LegalRule | None:
    normalized = article.replace(" ", "")
    return next(
        (rule for rule in plan.rules if law_name in rule.citation and rule.article_no == normalized),
        None,
    )


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

    if "유출통지" in actions:
        add("breach_discovery_time", "유출 인지 시점", "개인정보 유출을 언제 인지했으며 현재까지 어떤 조치를 했는가?", "통지·신고의 시기와 지체 여부를 검토하기 위해 필요합니다.", "privacy_breach")
        add("breach_scope", "유출 범위와 정보 유형", "영향받은 정보주체 수와 유출된 개인정보의 항목·민감도를 확인했는가?", "통지·신고 범위와 후속 조치를 판단하기 위해 필요합니다.", "privacy_breach")

    if "직무발명" in actions:
        add("employee_duties", "종업원의 직무 범위", "발명 당시 종업원의 담당 업무와 회사가 부여한 과업은 무엇인가?", "발명이 종업원의 현재 또는 과거 직무에 속하는지 판단하기 위해 필요합니다.", "employee_invention")
        add("invention_circumstances", "발명 경위와 회사 기여", "발명의 착상·완성 과정과 회사 설비·정보·인력의 기여는 어떠했는가?", "발명 경위와 사용자 업무 관련성을 구체화하기 위해 필요합니다.", "employee_invention")

    if "특허신규성" in actions:
        add("disclosure_timing", "공개일과 출원일", "기술이 처음 공개된 날짜와 예정 또는 실제 특허출원일은 언제인가?", "출원 전 공개 여부와 시간적 선후관계를 확인하기 위해 필요합니다.", "patent_novelty")
        add("disclosure_confidentiality", "공개의 내용과 비밀유지", "누구에게 어떤 기술 내용이 공개됐으며 비밀유지 의무가 있었는가?", "공중이 발명을 알 수 있었는지와 공개 범위를 판단하기 위해 필요합니다.", "patent_novelty")

    if "공지예외" in actions:
        add("disclosure_actor", "공개 주체와 경위", "공개를 한 주체는 누구이며 권리자의 의사에 따른 공개인지 제3자의 공개인지 확인했는가?", "적용 가능한 공지예외 경로와 증명사항을 구분하기 위해 필요합니다.", "disclosure_exception")
        add("exception_filing_deadline", "공지예외 기간과 증빙", "공개일로부터 출원일까지의 기간과 공개 경위를 입증할 자료가 있는가?", "공지예외의 기간 및 절차 요건 검토를 위해 필요합니다.", "disclosure_exception")

    if "업무상저작물" in actions:
        add("program_creation_duties", "프로그램 작성의 기획·직무성", "프로그램이 회사의 기획 아래 종업원의 업무상 작성된 것인지 확인했는가?", "업무상저작물 성립 요건을 사실관계에 적용하기 위해 필요합니다.", "work_made_for_hire")
        add("authorship_agreement", "계약·근무규칙의 별도 정함", "근로계약, 개발계약 또는 근무규칙에 저작자 귀속을 달리 정한 내용이 있는가?", "법정 귀속과 별도 약정의 관계를 확인하기 위해 필요합니다.", "work_made_for_hire")

    if "전자금융사고책임" in actions:
        add("incident_cause", "사고 유형과 발생 원인", "접근매체 위조·변조 등 사고의 구체적 유형과 발생 경로가 확인됐는가?", "적용되는 사고 책임 규정과 원인관계를 특정하기 위해 필요합니다.", "eft_accident_liability")
        add("user_fault", "이용자의 고의·중과실 관련 사실", "이용자의 행위, 보안수단 관리 및 사고 인지 후 통지 경위는 어떠한가?", "책임 제한 또는 분담 가능성을 검토하기 위해 필요합니다.", "eft_accident_liability")

    if "전자금융기록보존" in actions:
        add("record_type", "거래기록의 종류", "보존하려는 기록이 거래 종류·금액·상대방·접속 기록 중 무엇에 해당하는가?", "기록별 보존 범위와 기간을 구분하기 위해 필요합니다.", "eft_record_retention")
        add("transaction_date", "거래일과 보존 경과기간", "각 거래 또는 기록이 생성된 날짜와 현재까지의 보존 기간은 얼마인가?", "보존기간의 기산점과 만료 여부를 확인하기 위해 필요합니다.", "eft_record_retention")

    if "파기" in actions:
        add("purpose_end_date", "처리 목적 달성 시점", "개인정보의 처리 목적이 언제 달성됐고 더 이상 필요한 업무가 남아 있는가?", "파기 의무의 발생 시점을 확인하기 위해 필요합니다.", "destruction")
        add("statutory_retention_basis", "별도 보존 근거", "다른 법령에 따른 보존 의무가 있는 정보와 그 기간을 구분했는가?", "즉시 파기 대상과 분리 보관 대상을 구분하기 위해 필요합니다.", "destruction")

    if "전자금융약관" in actions:
        add("terms_change_notice", "약관 변경의 내용과 고지", "변경 조항과 고객에게 사용한 고지 방법·내용·발송일은 무엇인가?", "변경통지 절차의 이행 여부를 검토하기 위해 필요합니다.", "eft_terms_notice")
        add("terms_effective_date", "변경 시행일과 유예기간", "변경 약관의 시행일과 고객에게 부여한 확인·이의제기 기간은 언제인가?", "고지 시점과 변경 효력의 관계를 확인하기 위해 필요합니다.", "eft_terms_notice")

    if "전자금융분쟁" in actions:
        add("dispute_details", "분쟁 내용과 고객 요구", "문제가 된 거래, 고객의 이의 내용과 요청한 구제조치는 무엇인가?", "분쟁의 대상과 필요한 조사 범위를 특정하기 위해 필요합니다.", "eft_dispute_handling")
        add("internal_dispute_process", "내부 접수·조사·회신 경과", "분쟁 접수일, 조사 담당자, 증빙 보존과 고객 회신 경과는 어떠한가?", "내부 분쟁처리 절차와 외부 조정 연계를 검토하기 위해 필요합니다.", "eft_dispute_handling")

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
    privacy_breach = _rule_for_citation(composition_plan, "개인정보 보호법", "제34조")
    employee_invention = _rule_for_citation(composition_plan, "발명진흥법", "제2조")
    patent_novelty = _rule_for_citation(composition_plan, "특허법", "제29조")
    disclosure_exception = _rule_for_citation(composition_plan, "특허법", "제30조")
    work_made_for_hire = _rule_for_citation(composition_plan, "저작권법", "제9조")
    eft_accident = _rule_for_citation(composition_plan, "전자금융거래법", "제9조")
    eft_records = _rule_for_citation(composition_plan, "전자금융거래법", "제22조")
    destruction = _rule_for_citation(composition_plan, "개인정보 보호법", "제21조")
    eft_terms = _rule_for_citation(composition_plan, "전자금융거래법", "제24조")
    eft_dispute = _rule_for_citation(composition_plan, "전자금융거래법", "제27조")

    if "처리위탁" in actions or delegation:
        add("document_delegation", "위탁계약 문서화", "위탁업무 목적 외 처리 금지, 보호조치 등 검색된 필수사항을 포함해 위탁계약을 문서로 작성합니다.", delegation, "processing_delegation", order=10)
        add("control_delegate_scope", "수탁자 처리범위 통제", "수탁자가 위탁받은 업무 범위를 초과해 이용하거나 제3자에게 제공하지 않도록 권한과 절차를 통제합니다.", delegation, "processing_delegation", order=20)

    if "유출통지" in actions:
        add("record_breach_response", "유출 대응 기록화", "유출 인지 시점, 영향 범위, 원인과 현재까지의 차단·회수 조치를 하나의 사건 기록으로 정리합니다.", privacy_breach, "privacy_breach", order=70)
        add("prepare_breach_notice", "통지·신고 자료 준비", "정보주체 통지와 기관 신고 여부를 검토하고 필요한 항목, 전달 수단과 이행 시점을 기록합니다.", privacy_breach, "privacy_breach", order=80)

    if "직무발명" in actions:
        add("document_invention_context", "발명 경위 문서화", "종업원의 담당 직무, 발명 착상·완성 과정과 회사 자원의 기여를 문서로 정리합니다.", employee_invention, "employee_invention", order=90)
        add("review_invention_rules", "직무발명 규정 검토", "근로계약·취업규칙·직무발명 규정의 신고, 승계와 보상 절차를 확인합니다.", employee_invention, "employee_invention", order=100)

    if "특허신규성" in actions:
        add("freeze_external_disclosure", "추가 외부 공개 통제", "출원 전략을 검토할 때까지 기술자료의 추가 배포와 비밀유지 없는 설명을 통제합니다.", patent_novelty, "patent_novelty", order=110)
        add("compare_disclosure_and_filing", "공개·출원 일정 대조", "최초 공개일, 공개된 기술 내용과 출원일을 대조해 신규성 검토표를 작성합니다.", patent_novelty, "patent_novelty", order=120)

    if "공지예외" in actions:
        add("preserve_disclosure_evidence", "공개 경위 증빙 보존", "공개 주체, 일시, 대상, 자료와 공개 경위를 확인할 이메일·배포본·접속기록을 보존합니다.", disclosure_exception, "disclosure_exception", order=130)
        add("calendar_exception_deadline", "공지예외 일정 관리", "공개일을 기준으로 출원 및 증명서류 제출에 필요한 일정을 별도 관리합니다.", disclosure_exception, "disclosure_exception", order=140)

    if "업무상저작물" in actions:
        add("document_program_creation", "프로그램 작성 경위 정리", "회사의 기획 내용, 개발자의 직무와 작성·공표 경위를 프로젝트 기록으로 정리합니다.", work_made_for_hire, "work_made_for_hire", order=150)
        add("review_authorship_terms", "저작자 귀속 규정 검토", "근로계약·개발계약·근무규칙에서 저작자 귀속을 달리 정한 조항이 있는지 확인합니다.", work_made_for_hire, "work_made_for_hire", order=160)

    if "전자금융사고책임" in actions:
        add("preserve_incident_evidence", "전자금융사고 증거 보존", "인증·접속·거래 로그, 접근매체 처리와 이용자 통지 기록을 사건 단위로 보존합니다.", eft_accident, "eft_accident_liability", order=170)
        add("assess_incident_liability", "사고 책임 검토표 작성", "사고 유형, 원인, 이용자 행위와 적용 가능한 책임 제한 사유를 구분해 검토합니다.", eft_accident, "eft_accident_liability", order=180)

    if "전자금융기록보존" in actions:
        add("classify_transaction_records", "전자금융기록 분류", "거래 종류, 금액, 상대방과 접속 관련 기록을 보존 기준별로 분류합니다.", eft_records, "eft_record_retention", order=190)
        add("apply_retention_schedule", "기록 보존표 적용", "기록 생성일과 적용 보존기간, 만료 예정일을 연결한 보존표를 관리합니다.", eft_records, "eft_record_retention", order=200)

    if "파기" in actions:
        add("separate_retained_data", "법정 보존정보 분리", "다른 법령상 보존이 필요한 정보는 목적이 종료된 일반 개인정보와 분리해 접근을 제한합니다.", destruction, "destruction", order=210)
        add("execute_documented_destruction", "파기 이행 기록", "파기 대상, 방법, 일시와 담당자를 기록하고 복구 가능성이 남지 않았는지 확인합니다.", destruction, "destruction", order=220)

    if "전자금융약관" in actions:
        add("preserve_terms_versions", "약관 버전 이력 보존", "변경 전후 약관, 변경 사유, 승인일과 시행일을 버전별로 보존합니다.", eft_terms, "eft_terms_notice", order=230)
        add("verify_terms_notice", "변경통지 이행 확인", "고객별 고지 수단·발송일·내용과 이의제기 기간을 확인할 수 있도록 기록합니다.", eft_terms, "eft_terms_notice", order=240)

    if "전자금융분쟁" in actions:
        add("open_dispute_case", "분쟁 사건 등록", "대상 거래, 고객 주장, 요청사항과 관련 증빙을 하나의 사건번호로 관리합니다.", eft_dispute, "eft_dispute_handling", order=250)
        add("track_dispute_response", "조사·회신 기한 관리", "접수일, 담당자, 조사 경과, 고객 회신과 외부 조정 연계 여부를 기록합니다.", eft_dispute, "eft_dispute_handling", order=260)

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


def build_conditional_review(
    missing_fact_detector: dict[str, object] | None,
    practical_action_generator: dict[str, object] | None,
) -> dict[str, object]:
    """Join missing facts and source-bound actions into an auditable review result.

    This structure does not decide the merits of an individual matter.  It makes
    the answer's provisional status explicit and records which unanswered facts
    must be checked before each issue-specific action can be finalized.
    """
    facts = [dict(row) for row in (missing_fact_detector or {}).get("facts", [])]
    actions = [dict(row) for row in (practical_action_generator or {}).get("actions", [])]
    issue_order = _unique([
        *(str(row.get("issue_id", "")) for row in facts),
        *(str(row.get("issue_id", "")) for row in actions),
    ])

    priority_rows: list[dict[str, object]] = []
    issue_reviews: list[dict[str, object]] = []
    links: list[dict[str, object]] = []
    global_order = 0
    for issue_order_no, issue_id in enumerate(issue_order, start=1):
        issue_facts = [row for row in facts if str(row.get("issue_id")) == issue_id]
        issue_actions = [row for row in actions if str(row.get("issue_id")) == issue_id]
        for local_order, fact in enumerate(issue_facts, start=1):
            global_order += 1
            priority_level = min(local_order, 3)
            fact["priority"] = priority_level
            fact["priority_label"] = PRIORITY_LABELS[priority_level]
            fact["priority_order"] = global_order
            fact["decision_impact"] = "이 사실의 확인 결과에 따라 해당 쟁점의 판단 또는 조치가 달라질 수 있습니다."
            priority_rows.append(fact)

        fact_ids = [str(row.get("fact_id")) for row in issue_facts]
        action_ids = [str(row.get("action_id")) for row in issue_actions]
        citations = _unique(
            citation
            for action in issue_actions
            for citation in action.get("citations", [])
        )
        issue_label = ISSUE_LABELS.get(issue_id, issue_id)
        issue_reviews.append({
            "issue_order": issue_order_no,
            "issue_id": issue_id,
            "issue_label": issue_label,
            "review_status": "conditional" if issue_facts else "evidence_scoped",
            "conditional_conclusion": (
                f"{issue_label} 쟁점은 아래 핵심 사실을 확인한 후 검색된 근거에 따라 최종 판단해야 합니다."
                if issue_facts else
                f"{issue_label} 쟁점은 현재 검색된 근거 범위에서 검토합니다."
            ),
            "priority_fact_ids": fact_ids,
            "action_ids": action_ids,
            "citations": citations,
        })
        if fact_ids or action_ids:
            links.append({
                "link_id": f"review:{issue_id}",
                "issue_id": issue_id,
                "issue_label": issue_label,
                "fact_ids": fact_ids,
                "action_ids": action_ids,
                "citations": citations,
                "relation": "facts_condition_issue_actions",
            })

    conditional = bool(facts)
    return {
        "enabled": True,
        "review_status": "additional_facts_required" if conditional else "evidence_scoped",
        "review_status_label": "추가 사실 확인 필요" if conditional else "검색 근거 범위 검토",
        "definitive_conclusion": False,
        "conclusion": (
            "중요 사실이 확인되지 않아 현재 답변은 조건부 검토이며 최종 법률 판단이 아닙니다."
            if conditional else
            "현재 답변은 검색된 근거 범위의 검토이며 개별 사안의 최종 법률 판단이 아닙니다."
        ),
        "priority_fact_count": len(priority_rows),
        "priority_facts": priority_rows,
        "issue_review_count": len(issue_reviews),
        "issue_reviews": issue_reviews,
        "link_count": len(links),
        "fact_issue_action_links": links,
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
