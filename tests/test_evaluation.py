from datetime import date

from law_rag.evaluation.runner import EvaluationCase, EvaluationRunner, load_dataset
from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService


def service():
    return LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )


def test_dataset_loads():
    cases = load_dataset("evaluation/datasets/core_cases.json")
    assert len(cases) >= 6
    assert cases[0].case_id == "privacy-consent"


def test_runner_calculates_retrieval_metrics():
    case = EvaluationCase(
        case_id="privacy",
        question="개인정보 수집 동의 요건은?",
        domain="digital_business",
        top_k=1,
        expected_document_ids=["pipa:15:1"],
    )
    result = EvaluationRunner(service()).run_case(case)
    assert result.top1_hit is True
    assert result.hit_at_k is True
    assert result.reciprocal_rank == 1.0
    assert result.passed is True


def test_runner_checks_temporal_filter_and_abstention():
    case = EvaluationCase(
        case_id="future",
        question="전자금융거래 기록 보존 의무는?",
        domain="electronic_finance",
        top_k=5,
        as_of_date=date(2026, 7, 24),
        expected_document_ids=[],
        expected_abstain=True,
    )
    result = EvaluationRunner(service()).run_case(case)
    assert result.actual_abstain is True
    assert result.abstention_correct is True
    assert result.temporal_valid is True
    assert result.passed is True


def test_answer_case_includes_citation_metric():
    case = EvaluationCase(
        case_id="answer",
        question="개인정보 수집 동의 요건은?",
        domain="digital_business",
        top_k=1,
        expected_document_ids=["pipa:15:1"],
        evaluate_answer=True,
    )
    result = EvaluationRunner(service()).run_case(case)
    assert result.citation_valid is True
    assert result.generation_status == "completed"


def test_full_report_has_summary():
    cases = load_dataset("evaluation/datasets/core_cases.json")[:2]
    report = EvaluationRunner(service()).run(cases)
    assert report["version"] == "1.0.0"
    assert report["summary"]["total_cases"] == 2
    assert 0 <= report["summary"]["pass_rate"] <= 1


def test_runner_supports_official_article_expectation():
    case = EvaluationCase(
        case_id="official",
        question="개인정보 처리방침에는 어떤 내용을 포함해야 하나?",
        domain="digital_business",
        top_k=5,
        expected_law_id="011357",
        expected_article_nos=["제30조"],
    )
    result = EvaluationRunner(LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )).run_case(case)
    assert result.top1_hit is True
    assert result.passed is True
