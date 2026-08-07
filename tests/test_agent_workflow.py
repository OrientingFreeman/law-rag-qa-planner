from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService
from law_rag.workflow import AgentWorkflowRunner, InMemoryTraceStore, WorkflowConfig


def service() -> LawRagService:
    return LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )


def test_supported_question_completes_all_core_steps():
    run = AgentWorkflowRunner(service()).run(
        "개인정보 수집 동의 요건은 무엇인가요?",
        domain_id="digital_business",
        top_k=3,
    )
    assert run.outcome == "answered"
    assert run.status == "completed"
    assert run.response["generation_status"] == "completed"
    assert [step.step_id for step in run.execution_trace] == [
        "query_analysis", "search_strategy", "evidence_retrieval", "evidence_validation",
        "reasoning_path", "answer_generation", "citation_validation", "quality_decision",
        "retry_control", "finalization",
    ]
    assert all(step.status != "pending" for step in run.execution_trace)
    assert all(step.duration_ms is not None for step in run.execution_trace if step.status not in {"skipped"})


def test_unknown_explicit_article_abstains_without_generation():
    run = AgentWorkflowRunner(service()).run(
        "개인정보 보호법 제999조에 따른 신고 절차는?",
        domain_id="digital_business",
    )
    assert run.outcome == "abstained"
    assert run.stop_reason == "unknown_law_or_article"
    assert next(step for step in run.execution_trace if step.step_id == "answer_generation").status == "skipped"


def test_temporal_question_without_date_requests_clarification():
    run = AgentWorkflowRunner(service()).run(
        "개정 전 개인정보 수집 요건은 무엇인가요?",
        domain_id="digital_business",
    )
    assert run.outcome == "needs_clarification"
    assert run.stop_reason == "temporal_uncertainty"


def test_retry_is_bounded_and_records_changed_top_k():
    run = AgentWorkflowRunner(service()).run(
        "존재하지 않는 우주 조약상 화성 토지 등기 절차는?",
        config=WorkflowConfig(max_retries=1, retry_top_k_increment=4),
        top_k=2,
    )
    retry = next(step for step in run.execution_trace if step.step_id == "retry_control")
    assert run.retry_count <= 1
    assert retry.retry_count <= 1
    if retry.retry:
        assert retry.input_summary["previous_top_k"] == 2
        assert retry.output_summary["top_k"] == 6


def test_trace_store_can_retrieve_completed_run():
    store = InMemoryTraceStore()
    runner = AgentWorkflowRunner(service(), store)
    run = runner.run("개인정보 수집 동의 요건은?", domain_id="digital_business")
    assert store.get(run.run_id) is run
    assert store.list(1)[0].run_id == run.run_id


def test_workflow_records_selected_retrieval_strategy():
    run = AgentWorkflowRunner(service()).run(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        config=WorkflowConfig(search_strategy="lexical", query_rewrite=False, reranking=False),
    )
    strategy = next(step for step in run.execution_trace if step.step_id == "search_strategy")
    assert strategy.search_strategy == "lexical"
    assert strategy.output_summary["query_rewrite"] is False
    assert strategy.output_summary["ontology_reranking"] is False
