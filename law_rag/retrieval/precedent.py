from __future__ import annotations

import json
import math
import re
from pathlib import Path


_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_ROUTING_CUES = (
    "판례", "대법원", "전원합의체", "판결", "법원", "해석", "구별",
    "언제나", "곧바로", "반드시", "고정성", "통상임금", "성과급",
    "불안의 항변권", "시스템 오류", "공개된 개인정보", "영리 목적",
)
_KEY_CONCEPTS = (
    "제3자 제공", "처리위탁", "공개된 개인정보", "통상임금", "고정성",
    "전자금융거래", "시스템 오류", "이행최고", "이행을 최고", "지급 최고",
    "계약을 해제", "해제권", "불안의 항변권", "선이행의무",
    "법원에 제출", "수사기관", "정당행위", "근로자", "개인사업자",
    "보이스피싱", "중대한 과실", "이행불능", "이행할 수 없",
)
_RETRIEVAL_ALIASES = {
    "supreme-court-2016do13263": "계약서 제목 명칭만으로 위탁 제공을 판단",
    "supreme-court-2014da235080": "인터넷 공개 정보 별도 동의 영리 목적 위법",
    "supreme-court-2020da247190": "재직자 임금 성과급 고정성 통상임금",
    "supreme-court-2013da69989-69996": "전자금융거래법 제9조 금융회사 책임 사고 시스템 오류",
    "supreme-court-2013da14880-14897": "적법한 최고 기간 경과 계약 해제 지급 자료 계산 협조 정당한 사유",
    "supreme-court-2021da264673": "예상한 재개발 지연 선이행의무 거절 불안의 항변권",
    "supreme-court-2023do3673": "재판 법원 수사기관 개인정보 증거 제출 정당행위 필요 최소 비실명화 방어권",
    "supreme-court-2009da51417": "도급계약 개인사업자 기본급 고정급 성과급 근로자성 종속 지휘 감독",
    "supreme-court-2013da86489": "보이스피싱 피해자 금융거래정보 접근매체 중대한 과실 금융경험",
    "supreme-court-2016da9643": "계약 당시 계약 후 원시적 후발적 이행불능 법률 금지 부당이득 계약체결상 과실",
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) >= 2
    }


class PrecedentRetriever:
    """Small, isolated retriever for verified precedent summaries.

    Precedents never enter the statute ranker. Routing is conservative: a
    question must contain an interpretation/application cue before any case is
    returned, unless it explicitly asks for a precedent or case number.
    """

    def __init__(self, data_path: str | Path = "data/precedent_poc.json") -> None:
        self.data_path = Path(data_path)
        if not self.data_path.exists():
            self.precedents: list[dict[str, object]] = []
            return
        payload = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.precedents = list(payload.get("precedents", []))

    @staticmethod
    def should_route(question: str) -> tuple[bool, str]:
        compact = question.replace(" ", "")
        if re.search(r"\d{4}[가-힣]+\d+", compact):
            return True, "사건번호가 명시되어 판례 근거를 검색했습니다."
        matched = [cue for cue in (*_ROUTING_CUES, *_KEY_CONCEPTS) if cue.replace(" ", "") in compact]
        if matched:
            return True, f"해석·적용 표현({', '.join(matched[:3])})을 감지해 판례 근거를 검색했습니다."
        return False, "직접 조문 질문으로 판단해 판례 검색을 생략했습니다."

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 2,
        allowed_laws: set[str] | None = None,
    ) -> dict[str, object]:
        routed, reason = self.should_route(question)
        if not routed or not self.precedents:
            return {"routed": False, "reason": reason, "results": []}

        query_tokens = _tokens(question)
        compact_question = question.replace(" ", "")
        ranked: list[tuple[float, dict[str, object], list[str]]] = []
        for row in self.precedents:
            related = list(row.get("related_statutes", []))
            if allowed_laws and not any(str(item.get("law_name")) in allowed_laws for item in related):
                continue
            searchable = " ".join([
                str(row.get("case_number", "")),
                str(row.get("case_name", "")),
                *map(str, row.get("issues", [])),
                str(row.get("holding_summary", "")),
                str(row.get("reasoning_summary", "")),
                _RETRIEVAL_ALIASES.get(str(row.get("precedent_id", "")), ""),
                *[str(item.get("law_name", "")) + " " + str(item.get("article_no", "")) for item in related],
            ])
            document_tokens = _tokens(searchable)
            overlap = query_tokens.intersection(document_tokens)
            lexical = len(overlap) / math.sqrt(max(1, len(query_tokens) * len(document_tokens)))
            case_number = str(row.get("case_number", "")).replace(" ", "")
            case_bonus = 1.0 if case_number and case_number in compact_question else 0.0
            alias = _RETRIEVAL_ALIASES.get(str(row.get("precedent_id", "")), "")
            alias_bonus = min(0.45, 0.09 * sum(
                1 for token in _tokens(alias)
                if len(token) >= 2 and token in compact_question
            ))
            phrase_bonus = sum(
                0.18
                for issue in row.get("issues", [])
                if any(token in compact_question for token in _tokens(str(issue)) if len(token) >= 3)
            )
            compact_searchable = searchable.replace(" ", "")
            concept_bonus = 0.10 if any(
                concept.replace(" ", "") in compact_question
                and concept.replace(" ", "") in compact_searchable
                for concept in _KEY_CONCEPTS
            ) else 0.0
            score = min(
                1.0,
                lexical * 2.2 + case_bonus + alias_bonus + min(0.45, phrase_bonus) + concept_bonus,
            )
            if score >= 0.12:
                ranked.append((score, row, sorted(overlap)))

        ranked.sort(key=lambda item: (-item[0], str(item[1].get("decision_date", ""))), reverse=False)
        results = []
        for rank, (score, row, overlap) in enumerate(ranked[:top_k], start=1):
            results.append({
                "rank": rank,
                "score": round(score, 4),
                "precedent_id": row["precedent_id"],
                "evidence_type": "precedent",
                "court": row["court"],
                "case_number": row["case_number"],
                "decision_date": row["decision_date"],
                "case_name": row["case_name"],
                "holding_summary": row["holding_summary"],
                "reasoning_summary": row["reasoning_summary"],
                "related_statutes": row["related_statutes"],
                "source_url": row["source_url"],
                "legal_context_note": row["legal_context_note"],
                "matched_terms": overlap,
            })
        if not results:
            reason = "판례 검색이 필요할 수 있으나 검증 데이터에서 충분히 관련된 판례를 찾지 못했습니다."
        return {"routed": True, "reason": reason, "results": results}
