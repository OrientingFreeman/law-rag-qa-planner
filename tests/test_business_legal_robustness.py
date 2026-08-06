import json
from collections import defaultdict

from law_rag.evaluation.runner import EvaluationRunner, load_dataset
from law_rag.service import LawRagService
from tools.evaluate_business_legal_robustness import add_pair_metrics, validate_cases


DATASET = "evaluation/datasets/business_legal_robustness_cases.json"
CORPUS = "data/legal_corpus.json"


def _load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def test_robustness_dataset_has_twelve_complete_pairs():
    rows = _load(DATASET)
    pairs = defaultdict(set)
    for row in rows:
        pairs[row["pair_id"]].add(row["variant"])
    assert len(rows) == 24
    assert len(pairs) == 12
    assert all(variants == {"reference", "lay"} for variants in pairs.values())


def test_robustness_dataset_references_existing_articles():
    assert validate_cases(_load(DATASET), _load(CORPUS)) == []


def test_business_legal_query_robustness_regression():
    rows = _load(DATASET)
    service = LawRagService(data_path=CORPUS, domains_path="domains")
    report = EvaluationRunner(service).run(load_dataset(DATASET))
    add_pair_metrics(report, rows)
    assert report["summary"]["passed_cases"] == 24
    assert report["summary"]["hit_at_k"] == 1.0
    assert report["summary"]["top1_accuracy"] >= 0.95
    assert report["pair_metrics"]["passed_pairs"] == 12
    assert report["pair_metrics"]["top1_gold_stability"] >= 0.90
