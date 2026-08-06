import json

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService
from tools.evaluate_business_legal_practical_actions import evaluate


DATASET = "evaluation/datasets/business_legal_multi_issue_cases.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_expected_actions_are_stable_and_issue_bound():
    rows = _load(DATASET)
    for row in rows:
        expected_issues = {citation["issue_id"] for citation in row["expected_citations"]}
        actions = row["expected_actions"]
        assert len(actions) >= 4
        assert len({action["action_id"] for action in actions}) == len(actions)
        assert {action["issue_id"] for action in actions} <= expected_issues


def test_practical_action_generation_regression():
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    report = evaluate(service, _load(DATASET))

    assert report["summary"]["passed_cases"] == 8
    assert report["summary"]["mean_practical_action_recall"] == 1.0
    assert report["summary"]["mean_action_issue_coverage"] == 1.0
    assert report["summary"]["source_binding_rate"] == 1.0
    assert report["summary"]["mean_answer_plan_action_recall"] == 1.0
