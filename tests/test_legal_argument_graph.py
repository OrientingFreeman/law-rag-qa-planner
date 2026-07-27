from law_rag.domain.models import LegalProvision, SearchResult
from law_rag.generation.composer import build_composition_plan
from law_rag.generation.planner import build_answer_plan, bind_rendered_sentences
from law_rag.reasoning.legal_argument_graph import build_legal_argument_graph


def _result(document_id: str, article_no: str, text: str, score: float = 0.95) -> SearchResult:
    provision = LegalProvision(
        document_id=document_id,
        law_id="pipa",
        law_name="개인정보 보호법",
        article_no=article_no,
        text=text,
    )
    return SearchResult(provision=provision, score=score, rank=1, evidence_role="primary")


def test_argument_graph_connects_evidence_rules_and_claims():
    results = [_result("pipa:26", "제26조", "개인정보처리자는 위탁업무의 목적과 범위를 문서에 명시하여야 한다.")]
    composition = build_composition_plan(results, {"actions": ["처리위탁"]})
    path = {
        "enabled": True,
        "issue_order": ["processing_delegation"],
        "steps": [
            {"step": 1, "type": "identify_issue", "issue_id": "processing_delegation", "question": "처리위탁인가?", "conclusion": "포함됨", "citations": ["개인정보 보호법 제26조"]},
            {"step": 2, "type": "apply_primary_rule", "issue_id": "processing_delegation", "question": "기본 규칙은?", "conclusion": "위탁계약 문서화", "citations": ["개인정보 보호법 제26조"]},
        ],
    }
    plan = bind_rendered_sentences(build_answer_plan("처리위탁 요건은?", composition, path))
    graph = build_legal_argument_graph("처리위탁 요건은?", composition, plan, path)

    assert graph["enabled"] is True
    assert graph["validation"]["valid"] is True
    assert graph["validation"]["dangling_edge_count"] == 0
    assert graph["node_type_counts"]["issue"] == 1
    assert graph["node_type_counts"]["evidence"] >= 1
    assert any(edge["relation"] == "supports" for edge in graph["edges"])
    assert any(edge["relation"] == "raises" for edge in graph["edges"])


def test_argument_graph_marks_missing_fact_as_conclusion_limit():
    results = [_result("pipa:28-8", "제28조의8", "개인정보의 국외 이전은 법률상 근거를 갖추어야 한다.")]
    composition = build_composition_plan(results, {"actions": ["국외이전"]})
    path = {
        "enabled": True,
        "issue_order": ["cross_border_transfer"],
        "steps": [
            {"step": 1, "type": "identify_issue", "issue_id": "cross_border_transfer", "question": "국외이전인가?", "conclusion": "포함됨", "citations": ["개인정보 보호법 제28조의8"]},
            {"step": 2, "type": "conclusion", "issue_id": "cross_border_transfer", "question": "결론은?", "conclusion": "근거 확인 필요", "citations": ["개인정보 보호법 제28조의8"]},
        ],
    }
    plan = bind_rendered_sentences(build_answer_plan("해외 서버 이전이 가능한가?", composition, path))
    missing = {"facts": [{"fact_id": "transfer_country", "issue_id": "cross_border_transfer", "label": "이전 국가", "question": "어느 국가인가?", "reason": "보호수준 확인", "material": True}]}
    graph = build_legal_argument_graph("해외 서버 이전이 가능한가?", composition, plan, path, missing_fact_detector=missing)

    assert any(node["node_type"] == "missing_fact" for node in graph["nodes"])
    assert any(edge["relation"] == "limits" for edge in graph["edges"])
