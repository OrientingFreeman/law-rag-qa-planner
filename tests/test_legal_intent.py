from law_rag.planning import LegalIntentPlanner
from law_rag.service import LawRagService


def test_planner_decomposes_compound_privacy_question():
    plan = LegalIntentPlanner().plan("개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?")
    assert plan.is_compound is True
    assert plan.actions == ["처리위탁", "국외이전"]
    assert any("제26조" in query for query in plan.subqueries)
    assert any("제28조의8" in query for query in plan.subqueries)


def test_single_intent_preserves_simple_search_contract():
    plan = LegalIntentPlanner().plan("개인정보 처리방침에는 어떤 내용을 포함해야 하나?")
    assert plan.is_compound is False
    assert plan.actions == ["처리방침"]
    assert plan.subqueries[0].startswith("개인정보 처리방침")


def test_compound_query_surfaces_both_governing_articles():
    service = LawRagService(llm_provider=None)
    response = service.retrieve(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=8,
    )
    articles = {item["article_no"] for item in response["results"]}
    assert response["legal_intent"]["is_compound"] is True
    assert "제28조의8" in articles
    assert "제26조" in articles
