from fastapi.testclient import TestClient

from law_rag.api.app import create_app


def test_agent_run_and_trace_lookup(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    with TestClient(create_app(
        data_path="tests/fixtures/legal_corpus.json", domains_path="domains"
    )) as api:
        created = api.post("/agent/runs", json={
            "question": "개인정보 수집 동의 요건은?",
            "domain": "digital_business",
            "top_k": 3,
        })
        assert created.status_code == 200
        body = created.json()
        fetched = api.get(f"/agent/runs/{body['run_id']}")
        listed = api.get("/agent/runs")
    assert body["outcome"] == "answered"
    assert len(body["execution_trace"]) == 10
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == body["run_id"]
    assert listed.json()[0]["run_id"] == body["run_id"]


def test_missing_agent_run_returns_structured_404():
    with TestClient(create_app(
        data_path="tests/fixtures/legal_corpus.json", domains_path="domains"
    )) as api:
        response = api.get("/agent/runs/not-found")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_run_not_found"
