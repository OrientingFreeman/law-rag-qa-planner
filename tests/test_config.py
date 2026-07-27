from __future__ import annotations

import os
from pathlib import Path

from law_rag.config import load_environment


def test_dotenv_loads_values_without_overriding_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LAW_RAG_LLM_PROVIDER=openai\n"
        "LAW_RAG_LLM_API_KEY=file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.delenv("LAW_RAG_LLM_API_KEY", raising=False)

    loaded = load_environment(env_file)

    assert loaded == env_file.resolve()
    assert os.environ["LAW_RAG_LLM_PROVIDER"] == "deterministic"
    assert os.environ["LAW_RAG_LLM_API_KEY"] == "file-secret"


def test_missing_dotenv_is_non_fatal(tmp_path):
    assert load_environment(tmp_path / "missing.env") is None


def test_explicit_env_file_from_environment(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text("LAW_RAG_PROMPT_VERSION=custom_v1\n", encoding="utf-8")
    monkeypatch.setenv("LAW_RAG_ENV_FILE", str(env_file))
    monkeypatch.setenv("LAW_RAG_PROMPT_VERSION", "baseline")

    assert load_environment() == env_file.resolve()
    assert os.environ["LAW_RAG_PROMPT_VERSION"] == "baseline"
