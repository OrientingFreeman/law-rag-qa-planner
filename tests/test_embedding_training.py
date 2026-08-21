import json
from pathlib import Path

import pytest

from law_rag.evaluation.datasets import sha256_file
from law_rag.evaluation.embedding_training import (
    EmbeddingTrainingConfig,
    create_embedding_training_run,
    prepare_embedding_training_dataset,
)
from law_rag.evaluation.experiments import ExperimentStore
from tools.train_embedding_model import main as train_main


def _approved_dataset(tmp_path: Path, *, approved: bool = True) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dataset = tmp_path / "approved.jsonl"
    rows = []
    for index in range(5):
        rows.append({
            "candidate_id": f"hn_{index}",
            "query": f"질문 {index}",
            "domain": "civil_transactions",
            "candidate_pool_version": "civil-0.1.0",
            "positive_documents": [{"document_id": f"law:제{index}조", "text": f"정답 조문 {index}"}],
            "hard_negative_documents": [{"document_id": f"law:제{index + 10}조", "text": f"유사 오답 조문 {index}"}],
            "source": {"dataset_id": "official_core_cases", "case_id": f"case-{index}"},
            "failure_types": ["wrong_top1"],
            "review": {"review_status": "approved" if approved else "review_required"},
            "dataset_version": "1.0.0",
        })
    dataset.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest = tmp_path / "approved.manifest.json"
    manifest.write_text(json.dumps({
        "dataset_id": "legal_retrieval_hard_negatives",
        "dataset_version": "1.0.0",
        "record_count": len(rows),
        "content_sha256": sha256_file(dataset),
        "domains": ["civil_transactions"],
        "candidate_pool_versions": ["civil-0.1.0"],
    }), encoding="utf-8")
    return dataset, manifest


def test_prepare_embedding_dataset_is_reproducible_and_group_safe(tmp_path: Path):
    dataset, manifest = _approved_dataset(tmp_path)
    config = EmbeddingTrainingConfig(seed=7, validation_ratio=0.4)
    first = prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "first", config=config)
    second = prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "second", config=config)

    assert first["record_count"] == 5
    assert first["train_count"] == 3
    assert first["validation_count"] == 2
    assert first["leakage_check"] == "passed"
    assert first["domains"] == ["civil_transactions"]
    assert first["candidate_pool_versions"] == ["civil-0.1.0"]
    assert set(first["train_groups"]).isdisjoint(first["validation_groups"])
    assert first["train_content_sha256"] == second["train_content_sha256"]
    assert first["validation_content_sha256"] == second["validation_content_sha256"]
    train_rows = [json.loads(line) for line in first["train"].read_text(encoding="utf-8").splitlines()]
    validation_rows = [json.loads(line) for line in first["validation"].read_text(encoding="utf-8").splitlines()]
    assert {row["split_group"] for row in train_rows}.isdisjoint(row["split_group"] for row in validation_rows)
    assert all(row["positive"] and row["hard_negative"] for row in train_rows + validation_rows)
    assert all(row["domain"] == "civil_transactions" for row in train_rows + validation_rows)


def test_split_groups_same_case_or_same_query_to_prevent_leakage(tmp_path: Path):
    dataset, manifest_path = _approved_dataset(tmp_path)
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    same_case = {
        **rows[0], "candidate_id": "hn_same_case", "query": "같은 사례의 다른 표현",
        "positive_documents": [{"document_id": "law:제20조", "text": "정답 조문 20"}],
        "hard_negative_documents": [{"document_id": "law:제30조", "text": "유사 오답 30"}],
    }
    same_query = {
        **rows[0], "candidate_id": "hn_same_query",
        "source": {**rows[0]["source"], "case_id": "different-case"},
        "positive_documents": [{"document_id": "law:제21조", "text": "정답 조문 21"}],
        "hard_negative_documents": [{"document_id": "law:제31조", "text": "유사 오답 31"}],
    }
    rows.extend([same_case, same_query])
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(record_count=len(rows), content_sha256=sha256_file(dataset))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    prepared = prepare_embedding_training_dataset(
        dataset, manifest_path=manifest_path, output_dir=tmp_path / "prepared",
        config=EmbeddingTrainingConfig(seed=7, validation_ratio=0.4),
    )
    prepared_rows = [
        json.loads(line)
        for path in (prepared["train"], prepared["validation"])
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    connected = [
        row for row in prepared_rows
        if row["candidate_id"] in {rows[0]["candidate_id"], "hn_same_case", "hn_same_query"}
    ]
    assert len({row["split_group"] for row in connected}) == 1


def test_prepare_rejects_tampered_or_unapproved_dataset(tmp_path: Path):
    dataset, manifest = _approved_dataset(tmp_path)
    dataset.write_text(dataset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "out", config=EmbeddingTrainingConfig())

    dataset, manifest = _approved_dataset(tmp_path / "unapproved", approved=False)
    with pytest.raises(ValueError, match="unapproved"):
        prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "out2", config=EmbeddingTrainingConfig())


def test_plan_records_configuration_without_unexecuted_metrics(tmp_path: Path):
    dataset, manifest = _approved_dataset(tmp_path)
    prepared = prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "prepared", config=EmbeddingTrainingConfig())
    config = EmbeddingTrainingConfig(seed=11, epochs=2)
    report = create_embedding_training_run(prepared["manifest"], output_dir=tmp_path / "checkpoint", config=config)
    saved = ExperimentStore(tmp_path / "experiments").save(report)

    assert saved.exists()
    assert report["experiment_kind"] == "embedding_fine_tuning"
    assert report["summary"]["status"] == "planned"
    assert report["summary"]["metrics"] == {}
    assert report["config"]["seed"] == 11
    assert report["dataset"]["dataset_version"] == "1.0.0"


def test_training_cli_defaults_to_plan_only(tmp_path: Path, capsys):
    dataset, manifest = _approved_dataset(tmp_path)
    prepared = prepare_embedding_training_dataset(dataset, manifest_path=manifest, output_dir=tmp_path / "prepared", config=EmbeddingTrainingConfig())
    result = train_main([
        "--prepared-manifest", str(prepared["manifest"]),
        "--checkpoint-dir", str(tmp_path / "checkpoint"),
        "--experiment-dir", str(tmp_path / "experiments"),
    ])
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "planned"
    assert output["metrics"] == {}
    assert not (tmp_path / "checkpoint").exists()
