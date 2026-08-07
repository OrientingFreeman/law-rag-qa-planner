from pathlib import Path

import pytest

from law_rag.evaluation.comparison import compare_experiments
from law_rag.evaluation.experiments import ExperimentConfig, ExperimentRunner, ExperimentStore
from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService


def service() -> LawRagService:
    return LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )


def test_baseline_and_agent_reports_separate_metric_groups():
    runner = ExperimentRunner(service())
    case_ids = ["safety-unknown-pipa-article", "safety-supported-pipa-control"]
    baseline = runner.run(ExperimentConfig(mode="baseline"), case_ids=case_ids)
    agent = runner.run(ExperimentConfig(mode="agent"), case_ids=case_ids)
    for report in (baseline, agent):
        assert report["dataset"]["case_count"] == 2
        assert set(report["summary"]) >= {"retrieval", "answer", "safety", "average_latency_ms"}
    assert agent["cases"][0]["run_id"]
    assert len(agent["cases"][0]["execution_trace"]) == 10


def test_comparison_classifies_every_identical_case():
    runner = ExperimentRunner(service())
    ids = ["safety-unknown-pipa-article", "safety-supported-pipa-control"]
    baseline = runner.run(ExperimentConfig(mode="baseline"), case_ids=ids)
    agent = runner.run(ExperimentConfig(mode="agent"), case_ids=ids)
    comparison = compare_experiments(baseline, agent)
    assert sum(comparison["counts"].values()) == 2
    assert "average_latency_ms" in comparison["metric_deltas"]


def test_comparison_rejects_different_case_sets():
    runner = ExperimentRunner(service())
    baseline = runner.run(ExperimentConfig(mode="baseline"), limit=1)
    candidate = runner.run(ExperimentConfig(mode="agent"), limit=2)
    with pytest.raises(ValueError):
        compare_experiments(baseline, candidate)


def test_experiment_store_round_trip(tmp_path: Path):
    report = ExperimentRunner(service()).run(ExperimentConfig(mode="baseline"), limit=1)
    store = ExperimentStore(tmp_path)
    path = store.save(report)
    assert path.exists()
    assert store.get(report["experiment_id"])["experiment_id"] == report["experiment_id"]
    assert store.list()[0]["experiment_id"] == report["experiment_id"]
