from fastapi.testclient import TestClient

from law_rag import __version__

from law_rag.api.app import create_app


def client() -> TestClient:
    return TestClient(
        create_app(
            data_path="tests/fixtures/legal_corpus.json",
            domains_path="domains",
        )
    )


def test_health_reports_loaded_resources():
    with client() as api:
        response = api.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["provision_count"] > 0
    assert body["domain_count"] >= 4


def test_domains_and_laws_metadata():
    with client() as api:
        domains = api.get("/domains")
        laws = api.get("/laws", params={"domain": "digital_business"})
    assert domains.status_code == 200
    assert any(item["domain_id"] == "digital_business" for item in domains.json())
    assert laws.status_code == 200
    assert any(item["law_name"] == "개인정보 보호법" for item in laws.json())


def test_retrieve_excludes_prompt_and_query_includes_prompt():
    payload = {
        "question": "개인정보 수집 동의 요건은?",
        "domain": "digital_business",
        "top_k": 1,
    }
    with client() as api:
        retrieve = api.post("/retrieve", json=payload)
        query = api.post("/query", json=payload)
    assert retrieve.status_code == 200
    assert "prompt" not in retrieve.json()
    assert retrieve.json()["results"][0]["citation"] == "개인정보 보호법 제15조 제1항"
    assert query.status_code == 200
    assert "[검색 근거]" in query.json()["prompt"]


def test_unknown_domain_returns_structured_404():
    with client() as api:
        response = api.post(
            "/query",
            json={"question": "질문입니다", "domain": "unknown"},
        )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "domain_not_found"


def test_validation_rejects_invalid_top_k():
    with client() as api:
        response = api.post(
            "/query",
            json={"question": "질문입니다", "top_k": 0},
        )
    assert response.status_code == 422


def test_web_ui_and_static_assets_are_served():
    with client() as api:
        home = api.get("/")
        script = api.get("/static/app.js")
        internal_evaluation = api.get("/internal/evaluation")
        evaluation_script = api.get("/static/evaluation.js")
    assert home.status_code == 200
    assert "기업 법무·컴플라이언스를 위한" in home.text
    assert "평가 리포트" not in home.text
    assert home.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert script.status_code == 200
    assert "run-evaluation" not in script.text
    assert internal_evaluation.status_code == 200
    assert "회귀 평가와 실패 사례 점검" in internal_evaluation.text
    assert evaluation_script.status_code == 200
    assert "run-evaluation" in evaluation_script.text


def test_evaluation_latest_and_run_endpoints(tmp_path):
    report_path = tmp_path / "latest.json"
    api_client = TestClient(
        create_app(
            data_path="tests/fixtures/legal_corpus.json",
            domains_path="domains",
            evaluation_dataset_path="evaluation/datasets/core_cases.json",
            evaluation_report_path=report_path,
        )
    )
    with api_client as api:
        missing = api.get("/evaluation/latest")
        run = api.post("/evaluation/run", json={"limit": 2})
        latest = api.get("/evaluation/latest")
    assert missing.status_code == 404
    assert run.status_code == 200
    assert run.json()["version"] == __version__
    assert run.json()["summary"]["total_cases"] == 2
    assert report_path.exists()
    assert latest.status_code == 200
    assert latest.json()["summary"]["total_cases"] == 2


def test_v1_answer_metadata_confidence_and_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_LOG_DIR", str(tmp_path / "logs"))
    with client() as api:
        response = api.post("/answer", json={
            "question": "개인정보 수집 동의 요건은?",
            "domain": "digital_business",
            "top_k": 1,
        })
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["service_version"] == __version__
    assert body["prompt_version"] == "answer_v22"
    assert body["confidence"]["level"] in {"medium", "high"}
    assert body["results"][0]["matched_signals"]["semantic"] >= 0
    assert list((tmp_path / "logs").glob("*.jsonl"))


def test_unknown_ontology_issue_abstains():
    from law_rag.service import LawRagService

    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    body = service.answer(
        "AI 학습용 개인정보 판매 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    assert body["evidence_graph"]["issues"] == []
    assert body["evidence_graph"]["coverage"] == 0.0
    assert body["abstain"] is True
    assert body["generation_status"] == "abstained"



def test_supported_question_generates_answer(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    with client() as api:
        response = api.post("/answer", json={
            "question": "개인정보 수집 동의 요건은 무엇인가요?",
            "domain": "digital_business",
            "top_k": 3,
        })
    assert response.status_code == 200
    body = response.json()
    assert body["abstain"] is False
    assert body["generation_status"] == "completed"
    assert body["evidence_status"]["level"] in {"partial", "usable"}
    assert body["answer"]


def test_abstained_candidates_are_marked_insufficient():
    from law_rag.service import LawRagService

    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    body = service.answer(
        "법인 설립 후 반드시 해야 하는 신고나 등기에는 무엇이 있나요?",
        domain_id=None,
        top_k=3,
    )
    assert body["abstain"] is True
    assert body["generation_status"] == "abstained"
    assert body["evidence_status"]["level"] == "insufficient"
    assert "검색 후보" not in body["answer"]
