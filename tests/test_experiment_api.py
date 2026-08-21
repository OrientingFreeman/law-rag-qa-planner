import json

from fastapi.testclient import TestClient

from law_rag.api.app import create_app


def test_experiment_run_list_get_compare_and_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )
    with TestClient(app) as api:
        baseline = api.post("/experiments/run", json={"mode": "baseline", "limit": 2})
        agent = api.post("/experiments/run", json={"mode": "agent", "limit": 2})
        assert baseline.status_code == 200
        assert agent.status_code == 200
        base_id = baseline.json()["experiment_id"]
        agent_id = agent.json()["experiment_id"]
        listed = api.get("/experiments")
        fetched = api.get(f"/experiments/{agent_id}")
        compared = api.post("/experiments/compare", json={
            "baseline_experiment_id": base_id,
            "candidate_experiment_id": agent_id,
        })
        failures = api.get(f"/experiments/{agent_id}/failures")
    assert len(listed.json()) == 2
    assert fetched.json()["experiment_id"] == agent_id
    assert compared.status_code == 200
    assert sum(compared.json()["counts"].values()) == 2
    assert failures.status_code == 200


def test_list_experiments_accepts_legacy_report_without_corpus_or_model(tmp_path, monkeypatch):
    experiment_dir = tmp_path / "experiments"
    experiment_dir.mkdir()
    legacy_report = {
        "experiment_id": "exp_legacy",
        "executed_at": "2026-01-01T00:00:00+00:00",
        "dataset": {"case_count": 1},
        "code_version": "4.16.0",
        "config": {"mode": "baseline", "prompt_version": "answer_v21"},
        "environment": {},
        "summary": {},
        "cases": [],
    }
    (experiment_dir / "exp_legacy.json").write_text(
        json.dumps(legacy_report), encoding="utf-8"
    )
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_EXPERIMENT_DIR", str(experiment_dir))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )

    with TestClient(app) as api:
        response = api.get("/experiments")

    assert response.status_code == 200
    assert response.json()[0]["corpus"]["path"] == "unknown"
    assert response.json()[0]["model"]["prompt_version"] == "answer_v21"


def test_list_retrieval_ablations_returns_full_ablation_report(tmp_path, monkeypatch):
    experiment_dir = tmp_path / "experiments"
    experiment_dir.mkdir()
    report = {
        "experiment_id": "exp_ablation_test",
        "experiment_kind": "retrieval_ablation",
        "executed_at": "2026-08-20T00:00:00+00:00",
        "dataset": {"path": "dataset.json", "case_count": 0},
        "corpus": {"path": "corpus.json", "content_sha256": "not_executed"},
        "code_version": "4.22.0",
        "config": {"mode": "retrieval_ablation"},
        "model": {"provider": "multiple", "model": "ablation_matrix"},
        "environment": {},
        "summary": {"status": "planned", "status_counts": {"not_run": 1}},
        "cases": [],
        "ablation": {
            "methods": [{"method": "bm25", "status": "not_run"}],
            "comparisons": [],
        },
    }
    (experiment_dir / "exp_ablation_test.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_EXPERIMENT_DIR", str(experiment_dir))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )

    with TestClient(app) as api:
        response = api.get("/experiments/ablations")

    assert response.status_code == 200
    assert response.json()[0]["ablation"]["methods"][0] == {
        "method": "bm25", "status": "not_run",
    }
