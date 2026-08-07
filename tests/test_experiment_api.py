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
