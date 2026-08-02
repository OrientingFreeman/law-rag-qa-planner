import json
from pathlib import Path

from law_rag.retrieval.precedent import PrecedentRetriever
from law_rag.service import LawRagService


def test_direct_statute_question_does_not_route_to_precedents():
    result = PrecedentRetriever().retrieve("개인정보 수집 동의 요건은 무엇인가요?")
    assert result["routed"] is False
    assert result["results"] == []


def test_interpretation_question_routes_to_correct_precedent():
    result = PrecedentRetriever().retrieve(
        "통상임금이 되려면 고정성이 반드시 있어야 하나요?",
        allowed_laws={"근로기준법"},
    )
    assert result["routed"] is True
    assert result["results"][0]["case_number"] == "2020다247190"
    assert result["results"][0]["evidence_type"] == "precedent"


def test_domain_filter_prevents_cross_domain_precedents():
    result = PrecedentRetriever().retrieve(
        "통상임금 판례의 고정성 해석은?",
        allowed_laws={"개인정보 보호법"},
    )
    assert result["routed"] is True
    assert result["results"] == []


def test_service_keeps_statutes_and_precedents_separate(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    service = LawRagService()
    body = service.answer(
        "계약할 때부터 예상했던 재개발 지연이면 불안의 항변권으로 거절할 수 있나요?",
        domain_id="civil_transactions",
        top_k=3,
    )
    assert body["results"]
    assert all("precedent_id" not in row for row in body["results"])
    assert body["precedent_evidence"][0]["case_number"] == "2021다264673"
    assert body["evidence_routing"]["precedent"] is True
    assert body["abstain"] is False
    assert body["provider"] == "verified-precedent"
    assert body["precedent_validation"]["support_method"] == "verified_official_summary"


def test_low_score_precedent_cannot_override_abstention(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    service = LawRagService()
    service.precedent_retriever.retrieve = lambda *args, **kwargs: {
        "routed": True,
        "reason": "test low score",
        "results": [{
            "score": 0.3499,
            "precedent_id": "low-score-case",
            "case_number": "0000다0",
            "holding_summary": "낮은 점수의 테스트 요약",
            "source_url": "https://www.law.go.kr/test",
        }],
    }
    body = service.answer(
        "AI 학습용 개인정보 판매 절차 판례는?",
        domain_id="digital_business",
        top_k=3,
    )
    assert body["precedent_validation"]["answer_supported"] is False
    assert body["abstain"] is True
    assert body["generation_status"] == "abstained"


def test_wrong_statute_top1_is_not_promoted_over_verified_precedent(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    service = LawRagService()
    body = service.answer(
        "계약 당시부터 이행할 수 없었던 경우와 계약 후 이행할 수 없게 된 경우의 구제수단은 같은가?",
        domain_id="civil_transactions",
        top_k=3,
    )
    alignment = body["evidence_routing"]["statute_precedent_alignment"]
    assert body["results"][0]["article_no"] == "제535조"
    assert body["results"][0]["retrieval_reason"] == "precedent_linked"
    assert body["results"][1]["article_no"] == "제537조"
    assert body["results"][1]["retrieval_reason"] == "precedent_linked"
    assert alignment["checked"] is True
    assert alignment["aligned"] is False
    assert alignment["top1"]["article_no"] == "제538조"
    assert {row["article_no"] for row in alignment["linked_statutes"]} >= {"제535조", "제537조", "제741조"}
    assert body["evidence_routing"]["statute_sufficient"] is False
    assert body["evidence_routing"]["answer_basis"] == "precedent"
    assert body["provider"] == "verified-precedent"
    assert "2016다9643" in body["display_answer"]
    assert "제538조" not in body["display_answer"]


def test_precedent_linked_article_merges_all_available_paragraphs(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    service = LawRagService()
    body = service.retrieve(
        "불안의 항변권은 막연한 불안만으로 인정되나?",
        domain_id="civil_transactions",
        top_k=3,
    )
    linked = body["results"][0]
    assert linked["article_no"] == "제536조"
    assert linked["retrieval_reason"] == "precedent_linked"
    assert "①" in linked["text"] and "②" in linked["text"]
    assert "상대방의 이행이 곤란할 현저한 사유" in linked["text"]


def test_direct_statute_hit_is_not_replaced_by_precedent_link(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    service = LawRagService()
    body = service.retrieve(
        "개인정보 처리위탁 시 필요한 조치는 무엇인가요?",
        domain_id="digital_business",
        top_k=3,
    )
    assert body["results"][0]["article_no"] == "제26조"
    assert body["results"][0]["retrieval_reason"] != "precedent_linked"
    assert body["evidence_routing"]["precedent_linked_statutes"] == []


def test_precedent_poc_dataset_top1_regression():
    cases = json.loads(
        Path("evaluation/datasets/precedent_poc_cases.json").read_text(encoding="utf-8")
    )["cases"]
    retriever = PrecedentRetriever()
    for case in cases:
        result = retriever.retrieve(case["question"], top_k=3)
        assert result["results"], case["case_id"]
        assert result["results"][0]["case_number"] in case["expected_case_numbers"], case["case_id"]
