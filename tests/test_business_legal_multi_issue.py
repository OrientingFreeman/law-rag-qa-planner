import json

from law_rag.service import LawRagService
from tools.evaluate_business_legal_multi_issue import evaluate, validate_cases


DATASET = "evaluation/datasets/business_legal_multi_issue_cases.json"
CORPUS = "data/legal_corpus.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_multi_issue_dataset_has_eight_valid_cases():
    rows = _load(DATASET)
    assert len(rows) == 8
    assert validate_cases(rows, _load(CORPUS)) == []
    assert all(len(row["expected_citations"]) >= 2 for row in rows)


def test_domain_router_detects_explicit_privacy_and_ip_paths():
    service = LawRagService(data_path=CORPUS, domains_path="domains")
    routes = service._matched_domain_query_paths(
        "개인정보 처리위탁과 직원이 만든 프로그램의 저작자 근거를 함께 알려주세요."
    )
    domain_ids = {config.domain_id for config, _ in routes}
    assert "digital_business" in domain_ids
    assert "intellectual_property" in domain_ids


def test_domain_router_does_not_force_unmentioned_business_domains():
    service = LawRagService(data_path=CORPUS, domains_path="domains")
    routes = service._matched_domain_query_paths("민법상 계약 해제의 요건은 무엇인가요?")
    domain_ids = {config.domain_id for config, _ in routes}
    assert "digital_business" not in domain_ids
    assert "electronic_finance" not in domain_ids
    assert "intellectual_property" not in domain_ids


def test_business_legal_multi_issue_retrieval_regression():
    rows = _load(DATASET)
    service = LawRagService(data_path=CORPUS, domains_path="domains")
    report = evaluate(service, rows)
    assert report["summary"]["passed_cases"] == 8
    assert report["summary"]["full_issue_coverage_rate"] == 1.0
    assert report["summary"]["mean_issue_recall_at_k"] == 1.0
    assert report["summary"]["abstention_accuracy"] == 1.0
