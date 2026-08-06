import json

from law_rag.generation.providers import DeterministicProvider
from law_rag.planning import LegalIntentPlanner
from law_rag.service import LawRagService
from tools.evaluate_business_legal_multi_issue_answers import evaluate


DATASET = "evaluation/datasets/business_legal_multi_issue_cases.json"
CORPUS = "data/legal_corpus.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_multi_issue_dataset_has_stable_issue_ids():
    rows = _load(DATASET)
    issue_ids = {
        citation["issue_id"]
        for row in rows
        for citation in row["expected_citations"]
    }
    assert {
        "processing_delegation",
        "privacy_breach",
        "eft_accident_liability",
        "eft_record_retention",
        "eft_terms_notice",
        "eft_dispute_handling",
        "patent_novelty",
        "disclosure_exception",
        "employee_invention",
        "work_made_for_hire",
        "destruction",
    } <= issue_ids


def test_planner_detects_four_distinct_technology_release_issues():
    plan = LegalIntentPlanner().plan(
        "직원이 만든 기술과 소프트웨어를 외부에 공개하려 합니다. "
        "직무발명, 특허 출원 전 공개, 업무상저작물 귀속을 함께 확인해 주세요."
    )
    concept_ids = {
        row["concept_id"] for row in plan.ontology.get("concepts", [])
    }
    assert {
        "employee_invention",
        "patent_novelty",
        "disclosure_exception",
        "work_made_for_hire",
    } <= concept_ids
    assert plan.is_compound is True


def test_multi_issue_answer_and_citation_regression():
    rows = _load(DATASET)
    corpus = _load(CORPUS)
    service = LawRagService(
        data_path=CORPUS,
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    report = evaluate(service, rows, corpus)
    assert report["summary"]["passed_cases"] == 8
    assert report["summary"]["mean_issue_detection_recall"] == 1.0
    assert report["summary"]["mean_answer_plan_citation_recall"] == 1.0
    assert report["summary"]["mean_final_answer_citation_recall"] == 1.0
    assert report["summary"]["citation_validity_rate"] == 1.0
    assert report["summary"]["mean_grounding_coverage"] >= 0.90
