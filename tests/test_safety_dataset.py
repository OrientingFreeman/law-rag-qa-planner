import json
from pathlib import Path

from law_rag.evaluation.runner import load_dataset
from tools.validate_evaluation_dataset import validate


DATASET = Path("evaluation/datasets/official_core_cases.json")


def test_safety_cases_extend_official_dataset_without_fake_gold_articles():
    cases = load_dataset(DATASET)
    safety = [case for case in cases if case.case_id.startswith("safety-")]
    assert len(cases) == 61
    assert len(safety) == 12
    assert all(not case.expected_article_nos for case in safety if case.expected_abstain)
    assert all(case.expected_outcome for case in safety)


def test_extended_dataset_validation_passes():
    assert validate(DATASET, Path("data/legal_corpus.json")) == []


def test_fake_articles_exist_only_in_negative_questions():
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    corpus = json.loads(Path("data/legal_corpus.json").read_text(encoding="utf-8"))
    article_keys = {(row["law_name"], row["article_no"]) for row in corpus}
    assert ("개인정보 보호법", "제999조") not in article_keys
    assert ("근로기준법", "제999조") not in article_keys
    assert ("민법", "제9999조") not in article_keys
    assert ("개인정보 보호법 시행령", "제999조") not in article_keys
    safety = [row for row in rows if row["case_id"].startswith("safety-unknown-")]
    assert len(safety) == 4
    assert all("제999" in row["question"] for row in safety)
