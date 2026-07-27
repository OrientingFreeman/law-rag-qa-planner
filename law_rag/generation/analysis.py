from __future__ import annotations

import re

from law_rag.domain.models import SearchResult

QUESTION_TYPES = {"list", "requirement", "procedure", "period", "permission", "effect", "general"}


def classify_question(question: str) -> str:
    text = question.strip()
    if any(term in text for term in ("어떤 내용", "무엇을 포함", "어떤 사항", "항목", "목록", "종류")):
        return "list"
    if any(term in text for term in ("요건", "조건", "성립", "필요한가", "갖춰야")):
        return "requirement"
    if any(term in text for term in ("절차", "방법", "어떻게", "신청", "통지")):
        return "procedure"
    if any(term in text for term in ("기간", "기한", "언제까지", "며칠", "몇 년")):
        return "period"
    if any(term in text for term in ("가능", "허용", "금지", "할 수 있", "위법")):
        return "permission"
    if any(term in text for term in ("효력", "책임", "효과", "처벌", "과태료", "손해배상")):
        return "effect"
    return "general"


def build_answer_structure(question: str, results: list[SearchResult]) -> dict[str, object]:
    question_type = classify_question(question)
    if not results:
        return {
            "answer_type": question_type,
            "conclusion": "검색된 법령 근거가 없어 결론을 제시할 수 없습니다.",
            "key_points": [],
            "legal_basis": [],
            "exceptions_and_cautions": ["질문 범위, 도메인 또는 기준일을 조정해 다시 검색해야 합니다."],
            "facts_to_confirm": [],
        }

    primary = results[0]
    key_points = _extract_key_points(primary, question_type)
    basis = [
        {
            "citation": result.provision.citation_label(),
            "law_id": result.provision.law_id,
            "article_no": result.provision.article_no,
            "scope": result.evidence_scope,
            "role": "primary" if index == 0 else ("related" if result.retrieval_reason == "related" else "supporting"),
            "summary": _summarize_text(result.provision.text),
        }
        for index, result in enumerate(results)
    ]

    conclusion = _build_conclusion(question_type, primary, key_points)
    cautions = [
        "법령 적용은 사실관계와 기준일에 따라 달라질 수 있습니다.",
        "시행령·고시 또는 관련 조문이 별도의 세부 요건이나 예외를 정할 수 있습니다.",
    ]
    return {
        "answer_type": question_type,
        "conclusion": conclusion,
        "key_points": key_points,
        "legal_basis": basis,
        "exceptions_and_cautions": cautions,
        "facts_to_confirm": _facts_to_confirm(question, question_type),
    }


def build_related_provisions(results: list[SearchResult]) -> list[dict[str, object]]:
    if not results:
        return []
    primary = results[0]
    primary_key = (primary.provision.law_id, primary.provision.article_no)
    rows = []
    seen = {primary_key}
    for result in results[1:]:
        key = (result.provision.law_id, result.provision.article_no)
        if key in seen or not _is_related_enough(primary, result):
            continue
        seen.add(key)
        rows.append({
            "citation": result.provision.citation_label(),
            "law_id": result.provision.law_id,
            "article_no": result.provision.article_no,
            "relationship": "explicit_relation" if result.retrieval_reason == "related" else "retrieval_support",
            "score": round(result.score, 4),
            "summary": _summarize_text(result.provision.text),
        })
        if len(rows) >= 3:
            break
    return rows


def build_retrieval_explanation(results: list[SearchResult]) -> dict[str, object]:
    if not results:
        return {"selected": False, "reasons": ["검색 결과가 없습니다."], "signals": {}}
    top = results[0]
    signals = {"lexical": round(top.lexical_score, 4), "semantic": round(top.semantic_score, 4), "title": round(top.title_score, 4), "coverage": round(top.coverage_score, 4), "relation": round(top.relation_score, 4)}
    labels = {"semantic": "질문과 조문 내용의 의미 유사도가 높습니다.", "lexical": "질문의 핵심 표현이 조문에 직접 포함되어 있습니다.", "title": "질문과 조문 제목이 유사합니다.", "coverage": "질문의 핵심어가 조문에 폭넓게 포함되어 있습니다.", "relation": "상위 근거와 명시적인 관련 조문 관계가 있습니다."}
    reasons = [labels[name] for name, value in sorted(signals.items(), key=lambda item: item[1], reverse=True)[:3] if value > 0]
    if top.evidence_scope in {"article", "paragraph"}:
        reasons.append("하위 항·호를 같은 근거 단위로 집계했습니다.")
    return {"selected": True, "citation": top.provision.citation_label(), "score": round(top.score, 4), "evidence_scope": top.evidence_scope, "reasons": reasons, "signals": signals}


def _extract_key_points(result: SearchResult, question_type: str) -> list[str]:
    if result.sub_provisions and question_type in {"list", "requirement", "procedure"}:
        points = []
        for item in result.sub_provisions:
            text = re.sub(r"^\s*(?:\d+(?:의\d+)?\.|[가-하]\.)\s*", "", item.get("text", "")).strip()
            if text and text not in points:
                points.append(text)
        return points[:20]
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", result.provision.text) if part.strip()]
    return [_summarize_text(sentence, 220) for sentence in sentences[:5]]


def _build_conclusion(question_type: str, primary: SearchResult, key_points: list[str]) -> str:
    citation = primary.provision.citation_label()
    if question_type == "list" and key_points:
        return f"{citation}에 따르면 다음 {len(key_points)}개 사항을 중심으로 포함해야 합니다."
    if question_type == "requirement" and key_points:
        return f"{citation}에 따른 주요 요건은 다음과 같습니다."
    if question_type == "procedure" and key_points:
        return f"{citation}에 따른 절차와 방법은 다음과 같습니다."
    if question_type == "period":
        return f"기간·기한은 {citation}의 문언과 기준일을 중심으로 확인해야 합니다."
    if question_type == "permission":
        return f"허용 또는 금지 여부는 우선 {citation}을 기준으로 판단해야 합니다."
    if question_type == "effect":
        return f"법적 효과와 책임은 우선 {citation}을 중심으로 검토해야 합니다."
    return f"질문은 우선 {citation}을 중심으로 검토해야 합니다."


def _is_related_enough(primary: SearchResult, candidate: SearchResult) -> bool:
    if candidate.retrieval_reason == "related" or candidate.relation_score > 0:
        return True
    if candidate.score < max(0.45, primary.score * 0.62):
        return False
    primary_article = primary.provision.article_no.replace("제", "").replace("조", "")
    candidate_article = candidate.provision.article_no.replace("제", "").replace("조", "")
    explicit_cross_reference = (
        bool(primary_article and re.search(rf"(?:법\s*)?제{re.escape(primary_article)}조", candidate.provision.text))
        or bool(candidate_article and re.search(rf"제{re.escape(candidate_article)}조", primary.provision.text))
    )
    if explicit_cross_reference:
        return True
    primary_terms = _content_terms(primary.provision.text)
    candidate_terms = _content_terms(candidate.provision.text)
    overlap = len(primary_terms & candidate_terms) / max(1, min(len(primary_terms), len(candidate_terms)))
    same_law_family = primary.provision.law_name.replace(" 시행령", "").replace(" 시행규칙", "") in candidate.provision.law_name
    return overlap >= 0.30 and candidate.semantic_score >= 0.82 and same_law_family


def _content_terms(text: str) -> set[str]:
    stop = {"한다", "하여야", "따라", "경우", "대한", "관한", "있는", "없는", "등의", "사항"}
    return {token for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", text) if token not in stop}


def _summarize_text(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _facts_to_confirm(question: str, question_type: str) -> list[str]:
    if "처리방침" in question:
        return ["실제 제3자 제공 여부", "개인정보 처리 위탁 여부", "가명정보 처리 여부", "자동 수집 장치 사용 여부"]
    if any(term in question for term in ("동의", "수집", "제공", "처리")):
        return ["처리 목적과 대상 정보", "정보주체에게 실제로 고지한 내용", "보유 기간과 제3자 제공 여부"]
    if question_type == "period":
        return ["기간 계산의 기산점", "법정 연장·중단 사유", "질문에 적용할 기준일"]
    if any(term in question for term in ("계약", "취소", "손해", "해고")):
        return ["계약 또는 처분의 구체적 경위", "통지 시점과 방법", "예외 사유의 존재 여부"]
    return []
