from pathlib import Path


def test_docker_artifacts_exist_and_use_healthcheck():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["python", "-m", "law_rag.api"]' in dockerfile
    assert "law-rag-api:" in compose
    assert "/health" in compose
    assert "./logs:/app/logs" in compose


def test_ci_pipeline_has_tests_evaluation_and_smoke_test():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in workflow
    assert "--fail-under 0.8" in workflow
    assert "docker build" in workflow
    assert "Smoke-test answer endpoint" in workflow


def test_public_demo_structures_answer_and_avoids_citation_duplication():
    root = Path(__file__).resolve().parents[1]
    html = (root / "law_rag/api/static/index.html").read_text(encoding="utf-8")
    script = (root / "law_rag/api/static/app.js").read_text(encoding="utf-8")
    assert 'id="answer-content" class="structured-answer"' in html
    assert "renderStructuredAnswer" in script
    assert "section.title !== '근거 조문'" in script
    assert "근거 검증 완료" in script
