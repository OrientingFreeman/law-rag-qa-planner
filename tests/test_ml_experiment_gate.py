import json
from pathlib import Path

from law_rag.evaluation.datasets import sha256_file
from law_rag.evaluation.embedding_training import EmbeddingTrainingConfig, prepare_embedding_training_dataset
from law_rag.evaluation.ml_experiment_gate import CivilMlGateConfig, build_civil_ml_gate_report
from tools.plan_civil_ml_experiment import main


def _prepared_civil_dataset(tmp_path: Path) -> Path:
    source = tmp_path / "civil-approved.jsonl"
    rows = [{
        "candidate_id": f"hn_{index}", "query": f"민법 질문 {index}",
        "domain": "civil_transactions", "candidate_pool_version": "civil-0.1.0",
        "positive_documents": [{"document_id": f"civil:제{index}조", "text": f"정답 {index}"}],
        "hard_negative_documents": [{"document_id": f"civil:제{index + 10}조", "text": f"오답 {index}"}],
        "source": {"dataset_id": "official_core_cases", "case_id": f"civil-{index}"},
        "failure_types": ["wrong_top1"], "review": {"review_status": "approved"},
        "dataset_version": "civil-1.0.0",
    } for index in range(5)]
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest = source.with_name("civil-approved.manifest.json")
    manifest.write_text(json.dumps({
        "dataset_id": "legal_retrieval_hard_negatives", "dataset_version": "civil-1.0.0",
        "record_count": len(rows), "content_sha256": sha256_file(source),
        "domains": ["civil_transactions"], "candidate_pool_versions": ["civil-0.1.0"],
    }), encoding="utf-8")
    prepared = prepare_embedding_training_dataset(
        source, manifest_path=manifest, output_dir=tmp_path / "prepared",
        config=EmbeddingTrainingConfig(seed=42, validation_ratio=0.2),
    )
    return prepared["manifest"]


def _civil_evaluation(tmp_path: Path) -> Path:
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps([{
        "case_id": "civil-eval", "question": "민법상 효력은?",
        "domain": "civil_transactions", "expected_law_id": "civil",
        "expected_article_nos": ["제1조"], "expected_abstain": False,
    }], ensure_ascii=False), encoding="utf-8")
    return path


def test_gate_marks_runnable_stages_not_run_without_metrics(tmp_path: Path):
    report = build_civil_ml_gate_report(CivilMlGateConfig(
        prepared_manifest=str(_prepared_civil_dataset(tmp_path)),
        evaluation_dataset=str(_civil_evaluation(tmp_path)),
        checkpoint_path=str(tmp_path / "missing-checkpoint"),
    ), ml_dependency_available=True)
    matrix = {row["method"]: row for row in report["experiment_matrix"]}

    assert report["summary"]["status"] == "ready"
    assert report["summary"]["metrics"] == {}
    assert matrix["pretrained_embedding"]["status"] == "not_run"
    assert matrix["embedding_fine_tuning"]["status"] == "not_run"
    assert matrix["fine_tuned_embedding"]["status"] == "unavailable"
    assert "checkpoint" in matrix["fine_tuned_embedding"]["availability_reason"]


def test_gate_blocks_non_civil_or_missing_prepared_dataset(tmp_path: Path):
    report = build_civil_ml_gate_report(CivilMlGateConfig(
        prepared_manifest=str(tmp_path / "missing.json"),
        evaluation_dataset=str(_civil_evaluation(tmp_path)),
    ), ml_dependency_available=False)

    assert report["summary"]["status"] == "blocked"
    assert report["summary"]["metrics"] == {}
    assert all(row["status"] == "unavailable" for row in report["experiment_matrix"])


def test_gate_cli_saves_blocked_plan_and_returns_two(tmp_path: Path, capsys):
    result = main([
        "--prepared-manifest", str(tmp_path / "missing.json"),
        "--evaluation-dataset", str(_civil_evaluation(tmp_path)),
        "--experiment-dir", str(tmp_path / "experiments"),
    ])
    output = json.loads(capsys.readouterr().out)

    assert result == 2
    assert output["status"] == "blocked"
    assert output["metrics"] == {}
    assert Path(output["output"]).exists()
