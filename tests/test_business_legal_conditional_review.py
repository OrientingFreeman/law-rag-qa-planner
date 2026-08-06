import json

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService
from tools.evaluate_business_legal_conditional_review import evaluate


DATASET = "evaluation/datasets/business_legal_multi_issue_cases.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_conditional_review_generation_regression():
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    report = evaluate(service, _load(DATASET))

    assert report["summary"]["passed_cases"] == 8
    assert report["summary"]["conditional_conclusion_rate"] == 1.0
    assert report["summary"]["mean_priority_fact_recall"] == 1.0
    assert report["summary"]["critical_priority_accuracy"] == 1.0
    assert report["summary"]["fact_issue_action_linkage_rate"] == 1.0
    assert report["summary"]["linked_issue_source_binding_rate"] == 1.0


def test_conditional_review_is_exposed_without_replacing_existing_fields():
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(_load(DATASET)[1]["question"], top_k=10)
    review = response["conditional_review"]

    assert response["missing_fact_detector"]["facts"]
    assert response["practical_action_generator"]["actions"]
    assert review["review_status"] == "additional_facts_required"
    assert review["definitive_conclusion"] is False
    assert review["priority_facts"][0]["priority_label"] == "핵심"
    assert review["fact_issue_action_links"]
    assert all(link["citations"] for link in review["fact_issue_action_links"])
    assert "조건부 검토" in response["answer"]
