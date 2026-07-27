from law_rag.domain.models import LegalProvision, SearchResult
from law_rag.reasoning import LawGraph, ReasoningChainBuilder


def test_graph_expands_explicit_article_reference():
    provisions = [
        LegalProvision(
            document_id="law:제1조:①", law_id="law", law_name="테스트법",
            article_no="제1조", paragraph_no="①", text="제2조에 따른 절차를 준수한다."
        ),
        LegalProvision(
            document_id="law:제2조:①", law_id="law", law_name="테스트법",
            article_no="제2조", paragraph_no="①", text="신고 절차를 정한다."
        ),
    ]
    graph = LawGraph(provisions)
    direct = [SearchResult(provision=provisions[0], score=0.9, rank=1)]
    expanded = graph.expand(direct, max_hops=1, limit=3)
    assert [item.provision.article_no for item in expanded] == ["제2조"]
    assert expanded[0].retrieval_reason == "related"


def test_reasoning_chain_distinguishes_direct_and_related():
    provisions = [
        LegalProvision(document_id="law:제1조", law_id="law", law_name="테스트법", article_no="제1조", text="본문"),
        LegalProvision(document_id="law:제2조", law_id="law", law_name="테스트법", article_no="제2조", text="본문"),
    ]
    direct = [SearchResult(provision=provisions[0], score=0.9, rank=1)]
    related = [SearchResult(provision=provisions[1], score=0.7, retrieval_reason="related", relation_score=0.7)]
    chain = ReasoningChainBuilder().build(direct, related)
    assert [step["relation"] for step in chain] == ["direct", "related"]
    assert [step["step"] for step in chain] == [1, 2]
