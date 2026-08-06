from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

from law_rag.ontology import DEFAULT_LEGAL_ONTOLOGY, LegalOntology


@dataclass(slots=True)
class LegalIntent:
    actions: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    requested_outputs: list[str] = field(default_factory=list)
    qualifiers: list[str] = field(default_factory=list)
    subqueries: list[str] = field(default_factory=list)
    is_compound: bool = False
    ontology: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_ACTION_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("처리위탁", ("위탁", "수탁", "처리위탁"), ("개인정보 처리위탁 의무 계약 공개", "개인정보 보호법 제26조 위탁")),
    ("국외이전", ("국외 이전", "해외 이전", "국외로 이전", "해외로 이전", "해외 클라우드", "외국 클라우드"), ("개인정보 국외 이전 요건 절차", "개인정보 보호법 제28조의8 국외 이전")),
    ("제3자제공", ("제3자 제공", "제삼자 제공", "외부 제공"), ("개인정보 제3자 제공 요건", "개인정보 보호법 제17조 제3자 제공")),
    ("수집·이용", ("수집", "이용", "수집 이용"), ("개인정보 수집 이용 법적 근거", "개인정보 보호법 제15조 수집 이용")),
    ("파기", ("파기", "삭제", "폐기"), ("개인정보 파기 절차 보존", "개인정보 보호법 제21조 파기")),
    ("처리방침", ("처리방침", "개인정보 처리 방침"), ("개인정보 처리방침 포함 사항 공개", "개인정보 보호법 제30조 처리방침")),
    ("안전조치", ("안전조치", "보안조치", "보호조치"), ("개인정보 안전성 확보 조치", "개인정보 보호법 제29조 안전조치")),
    ("유출통지", ("개인정보 유출", "고객정보 유출", "정보주체 통지", "기관 신고"), ("개인정보 유출 통지 신고", "개인정보 보호법 제34조 유출 통지 신고")),
    ("전자금융사고책임", ("전자금융사고", "인증수단 위조", "접근매체 위조"), ("전자금융사고 책임", "전자금융거래법 제9조 책임")),
    ("전자금융기록보존", ("결제 거래기록", "전자금융거래기록", "승인 내역", "접속 흔적"), ("전자금융거래기록 생성 보존", "전자금융거래법 제22조 기록 보존")),
    ("전자금융약관", ("결제서비스 약관", "결제 약관", "약관 변경통지", "약관 변경"), ("약관 명시 변경통지", "전자금융거래법 제24조 약관")),
    ("전자금융분쟁", ("결제 분쟁", "분쟁처리", "분쟁조정", "외부 조정"), ("분쟁처리 분쟁조정", "전자금융거래법 제27조 분쟁")),
    ("특허신규성", ("특허 신규성", "출원 전 공개", "특허 출원 전 공개", "기술을 출원 전에 공개"), ("특허요건 신규성", "특허법 제29조 신규성")),
    ("공지예외", ("공지예외", "공개 후 출원", "12개월 이내", "공개로 생긴 불이익", "특허 출원 전 공개", "특허출원 전 공개", "특허출원 전에", "출원 전에 공개"), ("공지 등이 되지 아니한 발명으로 보는 경우", "특허법 제30조 공지예외")),
    ("직무발명", ("직무발명", "직원이 업무 중 만든 기술", "직원이 회사 업무로 기술", "직원이 만든 기술"), ("직무발명 정의", "발명진흥법 제2조 직무발명")),
    ("업무상저작물", ("업무상저작물", "업무상 프로그램", "직원이 만든 프로그램", "직원이 만든 소프트웨어", "프로그램 저작자", "프로그램을 개발"), ("업무상저작물 저작자", "저작권법 제9조 업무상저작물")),
)

_OUTPUT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("procedure", ("절차", "방법", "어떻게", "해야")),
    ("requirements", ("요건", "조건", "가능", "필요")),
    ("period", ("기간", "언제", "며칠", "기한")),
    ("sanction", ("처벌", "벌금", "과태료", "제재")),
    ("documents", ("서류", "문서", "계약서", "양식")),
    ("definition", ("란 무엇", "무엇인가", "뜻", "의미", "정의")),
)


class LegalIntentPlanner:
    """Deterministic first-pass planner for decomposing compound legal questions.

    It deliberately emits search intents rather than legal conclusions. Domain rules can
    later replace or extend these heuristics without changing the retrieval contract.
    """

    def __init__(self, ontology: LegalOntology | None = None) -> None:
        self.ontology = ontology or DEFAULT_LEGAL_ONTOLOGY

    def plan(self, question: str) -> LegalIntent:
        normalized = re.sub(r"\s+", " ", question.strip())
        lowered = normalized.lower()
        actions: list[str] = []
        subqueries: list[str] = []
        for action, triggers, expansions in _ACTION_RULES:
            if any(trigger.lower() in lowered for trigger in triggers):
                actions.append(action)
                subqueries.extend(expansions)

        outputs = [name for name, triggers in _OUTPUT_RULES if any(term in lowered for term in triggers)]
        subjects = [term for term in ("개인정보처리자", "정보주체", "수탁자", "위탁자", "공공기관") if term in normalized]
        objects = [term for term in ("개인정보", "민감정보", "고유식별정보", "가명정보") if term in normalized]
        qualifiers = [term for term in ("국외", "해외", "위탁", "동의", "계약", "처리방침") if term in normalized]

        ontology_matches = self.ontology.match_text(normalized, action_ids=actions)
        ontology_view = self.ontology.describe_matches(ontology_matches)

        # Keep the original wording as the primary query, and add only deduplicated
        # action-specific queries. This preserves single-issue regression behavior.
        deduped_subqueries = list(dict.fromkeys([normalized, *subqueries]))
        return LegalIntent(
            actions=actions,
            subjects=subjects,
            objects=objects,
            requested_outputs=outputs or ["general"],
            qualifiers=qualifiers,
            subqueries=deduped_subqueries,
            is_compound=len(actions) >= 2,
            ontology=ontology_view,
        )
