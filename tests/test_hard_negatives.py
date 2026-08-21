import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from law_rag.api.app import create_app
from law_rag.evaluation.hard_negatives import (
    JsonlCandidateStore,
    build_hard_negative_candidates,
    export_approved_training_dataset,
    select_review_candidates,
)
from law_rag.evaluation.reviews import JsonReviewStore, ReviewRecord


def benchmark_fixture() -> dict:
    return {
        "benchmark_id": "retrieval_fixture",
        "dataset": {
            "dataset_id": "official_core_cases",
            "dataset_version": "2.0.0",
            "ground_truth_version": "1.0.0",
        },
        "corpus": {"content_sha256": "a" * 64},
        "results": [{
            "method": "hybrid",
            "cases": [
                {
                    "case_id": "wrong-top1", "question": "개인정보 수집 근거는?",
                    "domain": "digital_business", "category": "similar_provision_disambiguation",
                    "expected": ["pipa:제15조"],
                    "retrieved": ["pipa:제16조", "pipa:제15조"],
                },
                {
                    "case_id": "miss", "question": "개인정보 동의 고지는?",
                    "domain": "digital_business", "category": "direct_statute_retrieval",
                    "expected": ["pipa:제15조"], "retrieved": ["pipa:제22조"],
                },
                {
                    "case_id": "pass", "question": "정상 검색",
                    "domain": "digital_business", "category": "direct_statute_retrieval",
                    "expected": ["pipa:제15조"], "retrieved": ["pipa:제15조"],
                },
            ],
        }],
    }


def built_candidates() -> list[dict]:
    return build_hard_negative_candidates(
        benchmark_fixture(), corpus_path="tests/fixtures/legal_corpus.json", methods={"hybrid"}
    )


def test_builder_creates_review_required_candidates_without_positive_negative_conflict():
    candidates = built_candidates()
    assert len(candidates) == 2
    wrong_top1 = next(row for row in candidates if row["source"]["case_id"] == "wrong-top1")
    assert wrong_top1["failure_types"] == ["wrong_top1", "over_retrieval"]
    assert wrong_top1["review_status"] == "review_required"
    positive_ids = {row["document_id"] for row in wrong_top1["positive_documents"]}
    negative_ids = {row["document_id"] for row in wrong_top1["hard_negative_documents"]}
    assert positive_ids == {"pipa:제15조"}
    assert negative_ids == {"pipa:제16조"}
    assert positive_ids.isdisjoint(negative_ids)
    assert wrong_top1["positive_documents"][0]["text"]
    assert "법률이 정한 근거" in wrong_top1["positive_documents"][0]["text"]


def test_candidate_store_skips_deterministic_duplicates(tmp_path: Path):
    store = JsonlCandidateStore(tmp_path / "candidates.jsonl")
    first = store.append_unique(built_candidates())
    second = store.append_unique(built_candidates())
    assert first == {"added": 2, "skipped_duplicates": 0, "total": 2}
    assert second == {"added": 0, "skipped_duplicates": 2, "total": 2}


def test_review_candidate_selection_filters_domain_and_keeps_one_per_case():
    rows = built_candidates()
    duplicate = {**rows[0], "candidate_id": "hn_duplicate"}
    civil = {
        **rows[1], "candidate_id": "hn_civil", "domain": "civil_transactions",
        "source": {**rows[1]["source"], "case_id": "civil-mistake"},
    }
    selected = select_review_candidates(
        [*rows, duplicate, civil], domains={"civil_transactions"},
        limit=20, one_per_case=True,
    )
    assert [row["candidate_id"] for row in selected] == ["hn_civil"]


def test_export_contains_only_approved_candidates(tmp_path: Path):
    candidate_store = JsonlCandidateStore(tmp_path / "candidates.jsonl")
    candidates = built_candidates()
    candidate_store.append_unique(candidates)
    review_store = JsonReviewStore(tmp_path / "reviews.jsonl")
    approved = ReviewRecord.create(
        target_type="training_candidate", target_id=candidates[0]["candidate_id"],
        dataset_id="hard_negative_candidates", dataset_version="0.1.0",
        ground_truth_version="1.0.0", decision="approve", reviewer_id="reviewer",
        review_comment="법적으로 구별되는 유사 조문임을 확인",
    )
    rejected = ReviewRecord.create(
        target_type="training_candidate", target_id=candidates[1]["candidate_id"],
        dataset_id="hard_negative_candidates", dataset_version="0.1.0",
        ground_truth_version="1.0.0", decision="reject", reviewer_id="reviewer",
        review_comment="실제 관련 문서이므로 negative로 부적절",
    )
    review_store.append(approved)
    review_store.append(rejected)

    output, manifest_path, manifest = export_approved_training_dataset(
        candidate_store, review_store,
        output_path=tmp_path / "training.jsonl", dataset_version="1.0.0",
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == candidates[0]["candidate_id"]
    assert rows[0]["review"]["review_status"] == "approved"
    assert rows[0]["domain"] == "digital_business"
    assert rows[0]["candidate_pool_version"] == "0.1.0"
    assert manifest["record_count"] == 1
    assert manifest["domains"] == ["digital_business"]
    assert manifest["candidate_pool_versions"] == ["0.1.0"]
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["content_sha256"]


def test_export_filters_approved_candidates_by_domain_and_pool_version(tmp_path: Path):
    candidates = built_candidates()
    civil = {
        **candidates[0],
        "candidate_id": "hn_1234567890abcdef12345678",
        "domain": "civil_transactions",
        "candidate_pool_version": "civil-0.1.0",
        "source": {**candidates[0]["source"], "case_id": "civil-case"},
    }
    candidate_store = JsonlCandidateStore(tmp_path / "candidates.jsonl")
    candidate_store.append_unique([*candidates, civil])
    review_store = JsonReviewStore(tmp_path / "reviews.jsonl")
    for candidate in (candidates[0], civil):
        review_store.append(ReviewRecord.create(
            target_type="training_candidate", target_id=candidate["candidate_id"],
            dataset_id="hard_negative_candidates", dataset_version="civil-0.1.0",
            ground_truth_version="1.0.0", decision="approve", reviewer_id="reviewer",
            review_comment="positive와 hard negative의 법적 구별을 확인",
        ))

    output, _, manifest = export_approved_training_dataset(
        candidate_store, review_store,
        output_path=tmp_path / "civil.jsonl", dataset_version="civil-1.0.0",
        domains={"civil_transactions"}, candidate_pool_versions={"civil-0.1.0"},
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert [row["candidate_id"] for row in rows] == [civil["candidate_id"]]
    assert manifest["selection"] == {
        "domains": ["civil_transactions"],
        "candidate_pool_versions": ["civil-0.1.0"],
        "matched_candidate_count": 1,
        "approved_record_count": 1,
    }
    assert manifest["source_dataset_versions"] == ["2.0.0"]
    assert manifest["source_corpus_sha256"] == ["a" * 64]


def test_export_rejects_empty_approved_set(tmp_path: Path):
    store = JsonlCandidateStore(tmp_path / "candidates.jsonl")
    store.append_unique(built_candidates())
    with pytest.raises(ValueError, match="approved training candidates not found"):
        export_approved_training_dataset(
            store, JsonReviewStore(tmp_path / "reviews.jsonl"),
            output_path=tmp_path / "training.jsonl", dataset_version="1.0.0",
        )


def test_training_candidate_api_validates_target_and_updates_queue(tmp_path: Path, monkeypatch):
    candidate_path = tmp_path / "candidates.jsonl"
    review_path = tmp_path / "reviews.jsonl"
    candidate_store = JsonlCandidateStore(candidate_path)
    candidate = built_candidates()[0]
    candidate_store.append_unique([candidate])
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_HARD_NEGATIVE_CANDIDATES", str(candidate_path))
    monkeypatch.setenv("LAW_RAG_REVIEW_STORE", str(review_path))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json", domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )
    with TestClient(app) as api:
        initial = api.get("/training/hard-negatives/queue")
        civil_only = api.get("/training/hard-negatives/queue?domain=civil_transactions")
        saved = api.post("/evaluation/reviews", json={
            "target_type": "training_candidate",
            "target_id": candidate["candidate_id"],
            "decision": "approve",
            "reviewer_id": "local-reviewer",
            "review_comment": "positive와 구별되는 hard negative 확인",
        })
        remaining = api.get("/training/hard-negatives/queue")
        approved = api.get("/training/hard-negatives/queue?include_approved=true")
        missing = api.post("/evaluation/reviews", json={
            "target_type": "training_candidate", "target_id": "hn_missing",
            "decision": "approve", "reviewer_id": "local-reviewer",
        })
    assert initial.status_code == 200
    assert initial.json()["queue_count"] == 1
    assert civil_only.json()["queue_count"] == 0
    assert civil_only.json()["candidate_pool"]["total_candidate_count"] == 1
    assert saved.status_code == 200
    assert saved.json()["review_status"] == "approved"
    assert remaining.json()["queue_count"] == 0
    assert approved.json()["candidates"][0]["review_status"] == "approved"
    assert missing.status_code == 404


def test_training_queue_hides_every_processed_decision_and_can_show_records(tmp_path: Path, monkeypatch):
    candidate_path = tmp_path / "candidates.jsonl"
    candidates = built_candidates()
    JsonlCandidateStore(candidate_path).append_unique(candidates)
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_HARD_NEGATIVE_CANDIDATES", str(candidate_path))
    monkeypatch.setenv("LAW_RAG_REVIEW_STORE", str(tmp_path / "reviews.jsonl"))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json", domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )

    with TestClient(app) as api:
        revised = api.post("/evaluation/reviews", json={
            "target_type": "training_candidate", "target_id": candidates[0]["candidate_id"],
            "decision": "revise", "reviewer_id": "local-reviewer",
            "review_comment": "positive와 negative 관계를 다시 확인",
        })
        rejected = api.post("/evaluation/reviews", json={
            "target_type": "training_candidate", "target_id": candidates[1]["candidate_id"],
            "decision": "reject", "reviewer_id": "local-reviewer",
            "review_comment": "필수 보조 근거이므로 negative로 부적절",
        })
        pending = api.get("/training/hard-negatives/queue?one_per_case=false")
        processed = api.get(
            "/training/hard-negatives/queue?include_processed=true&one_per_case=false"
        )

    assert revised.status_code == 200
    assert rejected.status_code == 200
    assert pending.json()["queue_count"] == 0
    assert pending.json()["pending_count"] == 0
    assert pending.json()["processed_count"] == 2
    assert processed.json()["queue_count"] == 2
    assert all(row["review_processed"] for row in processed.json()["candidates"])
    assert {row["latest_review"]["decision"] for row in processed.json()["candidates"]} == {
        "revise", "reject",
    }


def test_training_queue_groups_same_case_and_filters_candidate_pool_version(tmp_path: Path, monkeypatch):
    candidate_path = tmp_path / "candidates.jsonl"
    first = built_candidates()[0]
    second = {
        **first,
        "candidate_id": "hn_same_case_second_negative",
        "candidate_pool_version": "civil-0.2.0",
        "hard_negative_documents": [{
            **first["hard_negative_documents"][0], "document_id": "pipa:제22조",
        }],
        "negative_documents": [{
            **first["negative_documents"][0], "document_id": "pipa:제22조",
        }],
    }
    JsonlCandidateStore(candidate_path).append_unique([first, second])
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("LAW_RAG_HARD_NEGATIVE_CANDIDATES", str(candidate_path))
    monkeypatch.setenv("LAW_RAG_REVIEW_STORE", str(tmp_path / "reviews.jsonl"))
    app = create_app(
        data_path="tests/fixtures/legal_corpus.json", domains_path="domains",
        evaluation_dataset_path="evaluation/datasets/official_core_cases.json",
    )

    with TestClient(app) as api:
        grouped = api.get("/training/hard-negatives/queue?domain=digital_business")
        expanded = api.get(
            "/training/hard-negatives/queue?domain=digital_business&one_per_case=false"
        )
        versioned = api.get(
            "/training/hard-negatives/queue?domain=digital_business&candidate_pool_version=civil-0.2.0"
        )

    assert grouped.status_code == 200
    assert grouped.json()["queue_count"] == 1
    assert grouped.json()["ungrouped_queue_count"] == 2
    assert grouped.json()["hidden_additional_count"] == 1
    assert grouped.json()["candidates"][0]["additional_candidate_count"] == 1
    assert expanded.json()["queue_count"] == 2
    assert expanded.json()["hidden_additional_count"] == 0
    assert versioned.json()["queue_count"] == 1
    assert versioned.json()["candidate_pool"]["selected_version"] == "civil-0.2.0"
    assert set(versioned.json()["candidate_pool"]["versions"]) == {"0.1.0", "civil-0.2.0"}
