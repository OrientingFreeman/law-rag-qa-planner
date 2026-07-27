from law_rag.service import LawRagService
from law_rag.domain.models import LegalProvision, SearchResult
from law_rag.planning import LegalIntentPlanner
from law_rag.retrieval.evidence_graph import build_evidence_graph
from law_rag.retrieval.ontology_filter import rerank_with_ontology


def _r(doc, text, score):
    return SearchResult(LegalProvision(doc, "011357", "개인정보 보호법", "제26조", text), score=score, lexical_score=score, semantic_score=score)

def test_calibrated_scores_do_not_all_saturate():
    plan = LegalIntentPlanner().plan("개인정보를 위탁하면서 국외 이전하는 절차는?")
    rows = rerank_with_ontology("개인정보를 위탁하면서 국외 이전하는 절차는?", plan, [
        _r("a", "개인정보 처리업무를 위탁한다", .91),
        _r("b", "개인정보를 국외로 이전한다", .82),
        _r("c", "최소한의 개인정보를 수집한다", .80),
    ])
    assert len({round(x.score, 4) for x in rows}) > 1
    assert all(x.score < 1.0 for x in rows)

def test_evidence_graph_reports_issue_coverage():
    plan = LegalIntentPlanner().plan("개인정보를 위탁하면서 국외 이전하는 절차는?")
    rows = rerank_with_ontology("개인정보를 위탁하면서 국외 이전하는 절차는?", plan, [
        _r("a", "개인정보 처리업무를 위탁한다", .91),
        _r("b", "개인정보를 국외로 이전한다", .82),
    ])
    graph = build_evidence_graph(plan, rows)
    assert graph["coverage"] == 1.0
    assert not graph["missing_issues"]
    assert {n["role"] for n in graph["nodes"]} >= {"primary"}


def test_generic_purpose_does_not_create_processing_delegation_issue():
    plan = LegalIntentPlanner().plan("개인정보를 위탁하면서 국외 이전하는 절차는?")
    unrelated = _r(
        "sensitive",
        "특정 개인을 알아볼 목적으로 생성한 생체정보와 유전정보",
        .95,
    )
    rows = rerank_with_ontology("개인정보를 위탁하면서 국외 이전하는 절차는?", plan, [unrelated])
    assert rows[0].issue_coverage_score == 0.0
    assert rows[0].ontology_score == 0.0


def test_aggregation_preserves_ontology_metadata():
    from law_rag.retrieval.aggregation import aggregate_evidence

    plan = LegalIntentPlanner().plan("개인정보 처리위탁 절차는?")
    row = _r("a", "개인정보 처리업무를 위탁한다", .9)
    row = rerank_with_ontology("개인정보 처리위탁 절차는?", plan, [row])[0]
    aggregated = aggregate_evidence([row], [row.provision])
    assert aggregated[0].ontology_score == row.ontology_score
    assert aggregated[0].issue_coverage_score == row.issue_coverage_score


def test_v33_evidence_graph_uses_typed_legal_relations():
    from law_rag.service import LawRagService

    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    graph = response["evidence_graph"]
    assert graph["reasoning_path"]["enabled"] is True
    assert graph["reasoning_path"]["complete"] is True
    assert graph["reasoning_path"]["steps"]
    assert all("confidence" in edge and "reason" in edge for edge in graph["edges"])
    assert any(edge["relation"] != "supports_same_issue" for edge in graph["edges"])


def test_v33_reasoning_path_covers_each_detected_issue():
    from law_rag.service import LawRagService

    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    path = response["legal_reasoning_path"]
    issue_steps = {
        step["issue_id"] for step in path["steps"] if step["type"] == "identify_issue"
    }
    assert issue_steps == set(response["evidence_graph"]["issues"])
    assert path["final_instruction"]


def test_v34_issue_transition_connects_delegation_to_cross_border_transfer():
    from law_rag.service import LawRagService
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve("개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?", domain_id="digital_business", top_k=5)
    transitions = response["legal_reasoning_path"]["issue_transitions"]
    assert any(row["relation"] == "triggers_additional_rule" for row in transitions)
    assert response["legal_reasoning_path"]["answer_contract"]["must_follow_step_order"] is True

def test_v34_same_article_prohibition_is_not_mislabeled_as_exception():
    from law_rag.service import LawRagService
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve("개인정보 처리위탁 절차는?", domain_id="digital_business", top_k=5)
    relations = {edge["relation"] for edge in response["evidence_graph"]["edges"]}
    assert "prohibition_of" in relations or "supplements" in relations
    assert "exception_or_limitation_of" not in relations


def test_v341_same_article_relation_priority_distinguishes_prohibition_and_delegation():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    edges = response["evidence_graph"]["edges"]
    relations = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in edges}
    assert ("011357:제26조:⑤", "prohibition_of", "011357:제26조:①") in relations
    assert ("011357:제28조의8:⑥", "supplements", "011357:제28조의8:①") in relations
    assert ("011357:제28조의8:①", "prohibition_of", "011357:제28조의8:⑥") not in relations
