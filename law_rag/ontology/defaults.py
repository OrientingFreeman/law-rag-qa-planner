from __future__ import annotations

from law_rag.ontology.core import LegalConcept, LegalOntology


DEFAULT_CONCEPTS: tuple[LegalConcept, ...] = (
    LegalConcept("processing_delegation", "개인정보 처리위탁", ("처리위탁", "위탁", "수탁자", "위탁업무"), "legal_act", action_ids=("처리위탁",)),
    LegalConcept("cross_border_transfer", "개인정보 국외이전", ("국외 이전", "국외이전", "해외 이전", "국외로 이전"), "legal_act", action_ids=("국외이전",)),
    LegalConcept("third_party_provision", "개인정보 제3자 제공", ("제3자 제공", "제삼자 제공", "외부 제공"), "legal_act", action_ids=("제3자제공",)),
    LegalConcept("collection_use", "개인정보 수집·이용", ("수집 이용", "수집·이용", "수집", "이용"), "legal_act", action_ids=("수집·이용",)),
    LegalConcept("destruction", "개인정보 파기", ("파기", "삭제", "폐기"), "legal_act", action_ids=("파기",)),
    LegalConcept("privacy_policy", "개인정보 처리방침", ("처리방침", "개인정보 처리 방침"), "legal_act", action_ids=("처리방침",)),
    LegalConcept("safeguards", "안전성 확보조치", ("안전조치", "보안조치", "보호조치", "안전성 확보"), "legal_act", action_ids=("안전조치",)),
    LegalConcept("privacy_breach", "개인정보 유출 통지·신고", ("개인정보 유출", "고객정보 유출", "유출등", "정보주체에게 알", "관계기관 신고"), "legal_act", action_ids=("유출통지",)),
    LegalConcept("eft_accident_liability", "전자금융사고 책임", ("전자금융사고", "접근매체의 위조", "접근매체 위조", "인증수단 위조"), "legal_act", action_ids=("전자금융사고책임",)),
    LegalConcept("eft_record_retention", "전자금융거래기록 보존", ("전자금융거래기록", "거래기록의 생성", "거래기록을 보존", "결제 거래기록"), "legal_act", action_ids=("전자금융기록보존",)),
    LegalConcept("eft_terms_notice", "전자금융 약관 명시·변경통지", ("약관의 명시", "약관 변경", "변경통지", "결제서비스 약관"), "legal_act", action_ids=("전자금융약관",)),
    LegalConcept("eft_dispute_handling", "전자금융 분쟁처리·조정", ("분쟁처리", "분쟁조정", "이의제기", "결제 분쟁"), "legal_act", action_ids=("전자금융분쟁",)),
    LegalConcept("patent_novelty", "특허 신규성", ("특허 신규성", "특허출원 전", "공지되었거나 공연히 실시", "출원 전에 공개"), "legal_act", action_ids=("특허신규성",)),
    LegalConcept("disclosure_exception", "특허 공지예외", ("공지예외", "12개월 이내에 특허출원", "공지 등이 되지 아니한 발명", "공개 후 출원"), "legal_act", action_ids=("공지예외",)),
    LegalConcept("employee_invention", "직무발명", ("직무발명", "종업원등의 현재 또는 과거의 직무", "사용자등의 업무 범위"), "legal_act", action_ids=("직무발명",)),
    LegalConcept("work_made_for_hire", "업무상저작물 저작자", ("업무상저작물", "업무상저작물의 저작자", "법인등의 명의로 공표", "컴퓨터프로그램저작물"), "legal_act", action_ids=("업무상저작물",)),

    LegalConcept("purpose_limitation", "목적 외 처리 금지", ("목적 외", "목적외", "처리 금지", "이용 금지", "범위 초과"), "duty", parent_id="processing_delegation"),
    LegalConcept("purpose_and_scope", "위탁 목적·범위", ("목적 및 범위", "사무의 목적", "업무 범위", "위탁 목적", "위탁업무", "목적"), "requirement", parent_id="processing_delegation"),
    LegalConcept("written_contract", "서면 위탁계약", ("문서로", "위탁계약", "계약서", "서면"), "formality", parent_id="processing_delegation"),
    LegalConcept("security_measures", "기술적·관리적 보호조치", ("기술적", "관리적", "보호조치", "안전조치", "안전성 확보"), "duty", parent_id="safeguards", related_ids=("safe_management", "access_restriction")),
    LegalConcept("safe_management", "안전관리", ("안전한 관리", "안전관리", "관리 현황 점검"), "duty", parent_id="processing_delegation", related_ids=("security_measures",)),
    LegalConcept("subcontracting", "재위탁 제한", ("재위탁", "재 위탁"), "restriction", parent_id="processing_delegation"),
    LegalConcept("liability", "위반 책임", ("손해배상", "책임", "위반한 경우"), "legal_effect"),
    LegalConcept("separate_consent", "국외이전 별도 동의", ("별도 동의", "동의를 받은"), "legal_basis", parent_id="cross_border_transfer"),
    LegalConcept("treaty_basis", "법률·조약·국제협정 근거", ("조약", "국제협정", "특별한 규정"), "legal_basis", parent_id="cross_border_transfer"),
    LegalConcept("contract_performance_transfer", "계약 이행 목적 이전", ("계약의 체결", "계약 이행", "보관이 필요"), "legal_basis", parent_id="cross_border_transfer"),
    LegalConcept("privacy_notice", "공개·고지", ("처리방침", "공개", "알린 경우", "전자우편", "고지"), "disclosure_duty", related_ids=("privacy_policy",)),
    LegalConcept("certification", "보호 인증", ("인증", "인증받은", "보호 인증"), "legal_basis", parent_id="cross_border_transfer"),
    LegalConcept("adequacy", "동등 보호수준", ("동등한 수준", "보호체계", "국가 또는 국제기구"), "legal_basis", parent_id="cross_border_transfer"),
    LegalConcept("access_restriction", "접근 제한", ("접근 제한", "접근권한"), "security_control", parent_id="safeguards", related_ids=("security_measures",)),
)

DEFAULT_LEGAL_ONTOLOGY = LegalOntology(DEFAULT_CONCEPTS)
