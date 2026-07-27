from law_rag.domain.models import LegalProvision
from law_rag.planning import LegalIntentPlanner
from law_rag.retrieval.hybrid import HybridRetriever
from law_rag.retrieval.ontology_filter import rerank_with_ontology


def _p(document_id, law_name, article_no, text, document_type="법률"):
    return LegalProvision(
        document_id=document_id,
        law_id=document_id.split(":")[0],
        law_name=law_name,
        article_no=article_no,
        text=text,
        document_type=document_type,
    )


def test_act_article_anchor_does_not_promote_same_numbered_decree_article():
    provisions = [
        _p("act:26", "개인정보 보호법", "제26조", "개인정보 처리업무를 위탁하는 경우 문서로 하여야 한다."),
        _p("decree:26", "개인정보 보호법 시행령", "제26조", "공공기관이 고정형 영상정보처리기기의 설치 운영 사무를 위탁하는 경우", "시행령"),
    ]
    results = HybridRetriever(provisions).retrieve("개인정보 보호법 제26조 위탁", top_k=2, include_related=False)
    assert results[0].provision.law_name == "개인정보 보호법"


def test_ontology_reranker_demotes_issue_unrelated_candidate():
    plan = LegalIntentPlanner().plan("개인정보의 처리위탁이란 무엇인가?")
    provisions = [
        _p("act:16", "개인정보 보호법", "제16조", "최소한의 개인정보 외의 개인정보 수집에 동의하지 아니한다는 이유로 거절해서는 안 된다."),
        _p("act:26", "개인정보 보호법", "제26조", "개인정보 처리업무를 제3자에게 위탁하는 경우 문서로 하여야 한다."),
    ]
    results = HybridRetriever(provisions).retrieve("개인정보의 처리위탁이란 무엇인가?", top_k=2, include_related=False)
    reranked = rerank_with_ontology("개인정보의 처리위탁이란 무엇인가?", plan, results)
    assert reranked[0].provision.article_no == "제26조"
