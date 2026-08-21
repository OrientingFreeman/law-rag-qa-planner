import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from law_rag.api.app import create_app
from law_rag.evaluation.datasets import DatasetManifest, dataset_snapshot, sha256_file
from law_rag.evaluation.reviews import JsonReviewStore, ReviewRecord


def test_official_dataset_manifest_matches_released_dataset():
    dataset = Path("evaluation/datasets/official_core_cases.json")
    rows = json.loads(dataset.read_text(encoding="utf-8"))
    snapshot = dataset_snapshot(dataset, case_count=len(rows))
    assert snapshot["status"] == "released"
    assert snapshot["approved_case_count"] == 61
    assert snapshot["content_sha256"] == sha256_file(dataset)


def test_manifest_rejects_checksum_mismatch(tmp_path: Path):
    dataset = tmp_path / "cases.json"
    dataset.write_text("[]", encoding="utf-8")
    manifest = DatasetManifest(
        dataset_id="cases", dataset_version="1.0.0", ground_truth_version="1.0.0",
        schema_version="1.0.0", case_count=0, content_sha256="0" * 64,
        status="draft", created_at="2026-08-10T00:00:00+00:00", released_at=None,
        review_policy="single_reviewer", approved_case_count=0, source_snapshot_id="fixture",
    )
    assert manifest.verify(dataset, actual_case_count=0) == ["dataset_checksum_mismatch"]


def test_json_checksum_is_independent_of_line_endings_and_formatting(tmp_path: Path):
    compact = tmp_path / "compact.json"
    windows = tmp_path / "windows.json"
    compact.write_text('[{"b":2,"a":1}]', encoding="utf-8", newline="\n")
    windows.write_text('[\r\n  {"a": 1, "b": 2}\r\n]\r\n', encoding="utf-8", newline="")
    assert sha256_file(compact) == sha256_file(windows)


def test_review_store_is_append_only_and_returns_latest(tmp_path: Path):
    store = JsonReviewStore(tmp_path / "reviews.jsonl")
    first = ReviewRecord.create(
        target_type="evaluation_case", target_id="case-1", dataset_id="official",
        dataset_version="2.0.0", ground_truth_version="1.0.0", decision="revise",
        reviewer_id="reviewer", review_comment="정답 근거 재확인",
    )
    second = ReviewRecord.create(
        target_type="evaluation_case", target_id="case-1", dataset_id="official",
        dataset_version="2.0.0", ground_truth_version="1.0.0", decision="approve",
        reviewer_id="reviewer", review_comment="수정 확인",
    )
    store.append(first)
    store.append(second)
    assert len(store.list()) == 2
    assert store.latest(target_type="evaluation_case")["case-1"]["review_status"] == "approved"


def test_non_approval_review_requires_comment():
    with pytest.raises(ValueError):
        ReviewRecord.create(
            target_type="evaluation_case", target_id="case-1", dataset_id="official",
            dataset_version="2.0.0", ground_truth_version="1.0.0", decision="reject",
            reviewer_id="reviewer", review_comment="",
        )


def test_review_api_records_decision_and_updates_queue(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_REVIEW_STORE", str(tmp_path / "reviews.jsonl"))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )
    with TestClient(app) as api:
        saved = api.post("/evaluation/reviews", json={
            "target_id": "pipa-collection-basis",
            "decision": "revise",
            "reviewer_id": "local-reviewer",
            "review_comment": "정답 근거 범위를 재검토합니다.",
        })
        queue = api.get("/evaluation/reviews/queue")
        gated = api.post("/evaluation/run", json={"case_ids": ["pipa-collection-basis"]})
    assert saved.status_code == 200
    assert saved.json()["review_status"] == "review_required"
    assert queue.status_code == 200
    assert any(row["case_id"] == "pipa-collection-basis" for row in queue.json()["cases"])
    assert gated.status_code == 409
    assert gated.json()["detail"]["code"] == "evaluation_review_gate_failed"
