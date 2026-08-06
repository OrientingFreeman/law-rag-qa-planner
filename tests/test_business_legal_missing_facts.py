import json

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService
from tools.evaluate_business_legal_missing_facts import evaluate


DATASET = "evaluation/datasets/business_legal_multi_issue_cases.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_expected_missing_facts_are_stable_and_issue_bound():
    rows = _load(DATASET)
    for row in rows:
        expected_issues = {citation["issue_id"] for citation in row["expected_citations"]}
        facts = row["expected_missing_facts"]
        assert len(facts) >= 4
        assert len({fact["fact_id"] for fact in facts}) == len(facts)
        assert {fact["issue_id"] for fact in facts} <= expected_issues


def test_missing_fact_detection_regression():
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    report = evaluate(service, _load(DATASET))

    assert report["summary"]["passed_cases"] == 8
    assert report["summary"]["mean_missing_fact_recall"] == 1.0
    assert report["summary"]["mean_issue_fact_coverage"] == 1.0
    assert report["summary"]["mean_answer_plan_fact_recall"] == 1.0
    assert report["summary"]["conditional_advice_rate"] == 1.0
