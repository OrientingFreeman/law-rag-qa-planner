from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from law_rag import __version__
from law_rag.evaluation.datasets import sha256_file
from law_rag.evaluation.runner import load_dataset
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL
from law_rag.retrieval.reranker import DEFAULT_RERANKER_MODEL


@dataclass(frozen=True, slots=True)
class CivilMlGateConfig:
    prepared_manifest: str = "evaluation/training/civil_embedding_dataset/manifest.json"
    evaluation_dataset: str = "evaluation/datasets/official_core_cases.json"
    target_domain: str = "civil_transactions"
    checkpoint_path: str = "evaluation/training/checkpoints/civil-retrieval-v1"
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    reranker_model: str = DEFAULT_RERANKER_MODEL


def _blocked(name: str, reason: str) -> dict[str, Any]:
    return {"gate": name, "status": "blocked", "reason": reason}


def _validate_prepared(config: CivilMlGateConfig) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    path = Path(config.prepared_manifest)
    if not path.exists():
        return None, _blocked("approved_training_data", "prepared manifest does not exist")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        train_path = path.parent / "train.jsonl"
        validation_path = path.parent / "validation.jsonl"
        if sha256_file(train_path) != manifest["train_content_sha256"]:
            return None, _blocked("approved_training_data", "train split hash mismatch")
        if sha256_file(validation_path) != manifest["validation_content_sha256"]:
            return None, _blocked("approved_training_data", "validation split hash mismatch")
        domains = set(map(str, manifest.get("domains") or []))
        if domains != {config.target_domain}:
            return None, _blocked("approved_training_data", "prepared dataset is not isolated to the target domain")
        if int(manifest.get("train_count", 0)) < 1 or int(manifest.get("validation_count", 0)) < 1:
            return None, _blocked("approved_training_data", "both train and validation examples are required")
        train_groups = set(map(str, manifest.get("train_groups") or []))
        validation_groups = set(map(str, manifest.get("validation_groups") or []))
        if train_groups.intersection(validation_groups):
            return None, _blocked("approved_training_data", "train/validation group leakage detected")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return None, _blocked("approved_training_data", f"invalid prepared dataset: {exc}")
    return manifest, {
        "gate": "approved_training_data", "status": "passed",
        "dataset_version": manifest.get("dataset_version"),
        "train_count": manifest["train_count"], "validation_count": manifest["validation_count"],
        "candidate_pool_versions": manifest.get("candidate_pool_versions", []),
    }


def _validate_evaluation(config: CivilMlGateConfig) -> dict[str, Any]:
    path = Path(config.evaluation_dataset)
    if not path.exists():
        return _blocked("civil_evaluation", "evaluation dataset does not exist")
    try:
        cases = [case for case in load_dataset(path) if case.domain == config.target_domain]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return _blocked("civil_evaluation", f"invalid evaluation dataset: {exc}")
    retrieval_cases = [
        case for case in cases
        if not case.expected_abstain and (case.expected_document_ids or case.uses_article_expectation)
    ]
    if not retrieval_cases:
        return _blocked("civil_evaluation", "no gold-bearing retrieval cases for the target domain")
    return {
        "gate": "civil_evaluation", "status": "passed", "case_count": len(cases),
        "retrieval_case_count": len(retrieval_cases), "content_sha256": sha256_file(path),
    }


def build_civil_ml_gate_report(
    config: CivilMlGateConfig,
    *,
    ml_dependency_available: bool | None = None,
) -> dict[str, Any]:
    manifest, training_gate = _validate_prepared(config)
    evaluation_gate = _validate_evaluation(config)
    if ml_dependency_available is None:
        ml_dependency_available = importlib.util.find_spec("sentence_transformers") is not None
    dependency_gate = {
        "gate": "ml_dependency",
        "status": "passed" if ml_dependency_available else "blocked",
        "reason": None if ml_dependency_available else "optional dependency '.[ml]' is not installed",
    }
    checkpoint = Path(config.checkpoint_path)
    checkpoint_available = checkpoint.is_dir() and any(checkpoint.iterdir())
    checkpoint_gate = {
        "gate": "fine_tuned_checkpoint",
        "status": "passed" if checkpoint_available else "blocked",
        "reason": None if checkpoint_available else "fine-tuned checkpoint does not exist",
        "path": str(checkpoint),
    }
    base_ready = (
        training_gate["status"] == "passed"
        and evaluation_gate["status"] == "passed"
        and dependency_gate["status"] == "passed"
    )

    def method(name: str, *, needs_checkpoint: bool = False) -> dict[str, Any]:
        ready = base_ready and (checkpoint_available or not needs_checkpoint)
        reasons = []
        if training_gate["status"] != "passed":
            reasons.append(training_gate["reason"])
        if evaluation_gate["status"] != "passed":
            reasons.append(evaluation_gate["reason"])
        if dependency_gate["status"] != "passed":
            reasons.append(dependency_gate["reason"])
        if needs_checkpoint and not checkpoint_available:
            reasons.append(checkpoint_gate["reason"])
        return {
            "method": name, "status": "not_run" if ready else "unavailable",
            "availability_reason": None if ready else "; ".join(map(str, reasons)),
        }

    matrix = [
        method("pretrained_embedding"),
        method("pretrained_embedding_reranker"),
        method("embedding_fine_tuning"),
        method("fine_tuned_embedding", needs_checkpoint=True),
        method("fine_tuned_embedding_reranker", needs_checkpoint=True),
    ]
    gates = [training_gate, evaluation_gate, dependency_gate, checkpoint_gate]
    return {
        "experiment_id": f"exp_civil_ml_gate_{uuid4().hex}",
        "experiment_kind": "civil_ml_readiness_gate",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "dataset_id": "civil_legal_retrieval_embedding_triplets",
            "dataset_version": manifest.get("dataset_version", "not_available") if manifest else "not_available",
            "case_count": int(manifest.get("record_count", 0)) if manifest else 0,
            "content_sha256": sha256_file(config.prepared_manifest) if manifest else "not_available",
            "path": config.prepared_manifest,
        },
        "corpus": {"path": "prepared_training_dataset", "content_sha256": manifest.get("source_content_sha256", "not_available") if manifest else "not_available", "provision_count": 0},
        "code_version": __version__,
        "config": {"mode": "civil_ml_readiness_gate", **asdict(config)},
        "model": {"provider": "sentence-transformers", "model": config.embedding_model, "reranker_model": config.reranker_model, "prompt_version": "not_applicable"},
        "environment": {},
        "summary": {
            "status": "ready" if base_ready else "blocked",
            "passed_gate_count": sum(gate["status"] == "passed" for gate in gates),
            "blocked_gate_count": sum(gate["status"] == "blocked" for gate in gates),
            "metrics": {},
            "metrics_note": "No model was executed and no performance metric was generated.",
        },
        "gates": gates,
        "experiment_matrix": matrix,
        "cases": [],
    }
