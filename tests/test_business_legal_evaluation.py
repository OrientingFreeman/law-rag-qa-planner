from copy import deepcopy

from tools.evaluate_business_legal_cases import (
    DEFAULT_CORPUS,
    DEFAULT_DATASET,
    DEFAULT_DOMAINS,
    load_json,
    validate_cases,
)
from law_rag.evaluation.runner import EvaluationRunner, load_dataset
from law_rag.service import LawRagService


def _fixtures():
    return load_json(DEFAULT_DATASET), load_json(DEFAULT_CORPUS)


def test_business_legal_dataset_has_12_valid_cases():
    cases, corpus = _fixtures()
    assert len(cases) == 12
    assert len({case["case_id"] for case in cases}) == 12
    assert validate_cases(cases, corpus) == []


def test_business_legal_dataset_covers_three_domains():
    cases, _ = _fixtures()
    assert {case["domain"] for case in cases} == {
        "electronic_finance", "digital_business", "intellectual_property"
    }


def test_business_legal_gold_article_must_exist():
    cases, corpus = _fixtures()
    broken = deepcopy(cases)
    broken[0]["expected_article_nos"] = ["제999조"]
    assert any("missing corpus article" in error for error in validate_cases(broken, corpus))


def test_business_legal_case_id_must_be_unique():
    cases, corpus = _fixtures()
    broken = deepcopy(cases)
    broken[1]["case_id"] = broken[0]["case_id"]
    assert any("duplicate case_id" in error for error in validate_cases(broken, corpus))


def test_business_legal_retrieval_regression():
    service = LawRagService(data_path=DEFAULT_CORPUS, domains_path=DEFAULT_DOMAINS)
    report = EvaluationRunner(service).run(load_dataset(DEFAULT_DATASET))
    summary = report["summary"]
    assert summary["passed_cases"] == summary["total_cases"] == 12
    assert summary["top1_accuracy"] == 1.0
    assert summary["hit_at_k"] == 1.0
    assert summary["mean_recall_at_k"] == 1.0
