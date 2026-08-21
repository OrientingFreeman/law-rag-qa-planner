from __future__ import annotations

import hashlib
import json
import platform
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from law_rag import __version__
from law_rag.evaluation.datasets import sha256_file


TRAINING_SCHEMA_VERSION = "1.0.0"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass(frozen=True, slots=True)
class EmbeddingTrainingConfig:
    base_model: str = DEFAULT_EMBEDDING_MODEL
    seed: int = 42
    validation_ratio: float = 0.2
    loss: str = "triplet"
    triplet_margin: float = 0.25
    epochs: int = 1
    batch_size: int = 8
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    max_seq_length: int = 512

    def validate(self) -> None:
        if not self.base_model.strip():
            raise ValueError("base_model must not be empty")
        if not 0 <= self.validation_ratio < 1:
            raise ValueError("validation_ratio must be in [0, 1)")
        if self.loss != "triplet":
            raise ValueError("only triplet loss is currently supported")
        if self.triplet_margin <= 0 or self.epochs < 1 or self.batch_size < 1:
            raise ValueError("margin, epochs, and batch_size must be positive")
        if self.learning_rate <= 0 or not 0 <= self.warmup_ratio < 1:
            raise ValueError("learning_rate and warmup_ratio must be valid")
        if self.max_seq_length < 8:
            raise ValueError("max_seq_length must be at least 8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"training dataset not found: {path}")
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid training JSONL: {exc}") from exc


def _document_text(document: dict[str, Any]) -> str:
    text = str(document.get("text", "")).strip()
    if not text:
        raise ValueError("positive and hard-negative documents must contain text")
    return text


def _split_aliases(row: dict[str, Any]) -> tuple[str, str]:
    source = row.get("source") or {}
    case_id = str(source.get("case_id", "")).strip()
    query = str(row.get("query", "")).strip()
    case_alias = (
        f"case:{source.get('dataset_id', 'unknown')}:{case_id}"
        if case_id else ""
    )
    query_alias = "query:" + hashlib.sha256(query.encode("utf-8")).hexdigest()
    return case_alias, query_alias


def prepare_embedding_training_dataset(
    dataset_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    output_dir: str | Path,
    config: EmbeddingTrainingConfig,
) -> dict[str, Any]:
    """Validate an approved dataset and create deterministic, group-safe triplet splits."""
    config.validate()
    source = Path(dataset_path)
    manifest_file = Path(manifest_path) if manifest_path else source.with_name(f"{source.stem}.manifest.json")
    if not manifest_file.exists():
        raise ValueError(f"dataset manifest not found: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    actual_hash = sha256_file(source)
    if manifest.get("content_sha256") != actual_hash:
        raise ValueError("dataset content hash does not match its manifest")
    rows = _read_jsonl(source)
    if len(rows) != int(manifest.get("record_count", -1)):
        raise ValueError("dataset record count does not match its manifest")
    dataset_version = str(manifest.get("dataset_version", "")).strip()
    if not dataset_version:
        raise ValueError("dataset_version is required")
    manifest_domains = set(map(str, manifest.get("domains") or []))
    manifest_pool_versions = set(map(str, manifest.get("candidate_pool_versions") or []))

    triplets: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if row.get("review", {}).get("review_status") != "approved":
            raise ValueError("unapproved records cannot be used for training")
        if str(row.get("dataset_version")) != dataset_version:
            raise ValueError("record dataset_version does not match its manifest")
        row_domain = str(row.get("domain", "all"))
        row_pool_version = str(row.get("candidate_pool_version", "unknown"))
        if manifest_domains and row_domain not in manifest_domains:
            raise ValueError("record domain does not match its manifest")
        if manifest_pool_versions and row_pool_version not in manifest_pool_versions:
            raise ValueError("record candidate pool version does not match its manifest")
        query = str(row.get("query", "")).strip()
        if not query:
            raise ValueError("query must not be empty")
        positives = row.get("positive_documents") or []
        negatives = row.get("hard_negative_documents") or []
        positive_ids = {str(item.get("document_id")) for item in positives}
        negative_ids = {str(item.get("document_id")) for item in negatives}
        if not positive_ids or not negative_ids or positive_ids.intersection(negative_ids):
            raise ValueError("positive/hard-negative documents are missing or conflicting")
        case_alias, query_alias = _split_aliases(row)
        for positive in positives:
            for negative in negatives:
                identity = (query, str(positive.get("document_id")), str(negative.get("document_id")))
                if identity in seen:
                    continue
                seen.add(identity)
                triplets.append({
                    "training_example_id": "tr_" + hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()[:24],
                    "candidate_id": row.get("candidate_id"),
                    "split_group": "",
                    "_split_aliases": [alias for alias in (case_alias, query_alias) if alias],
                    "query": query,
                    "positive": _document_text(positive),
                    "hard_negative": _document_text(negative),
                    "positive_document_id": positive.get("document_id"),
                    "hard_negative_document_id": negative.get("document_id"),
                    "failure_types": row.get("failure_types") or [],
                    "domain": row_domain,
                    "candidate_pool_version": row_pool_version,
                })
    if not triplets:
        raise ValueError("approved training examples not found")

    parents: dict[str, str] = {}

    def find(alias: str) -> str:
        parents.setdefault(alias, alias)
        if parents[alias] != alias:
            parents[alias] = find(parents[alias])
        return parents[alias]

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    for row in triplets:
        aliases = row.pop("_split_aliases")
        for alias in aliases:
            find(alias)
        for alias in aliases[1:]:
            union(aliases[0], alias)
    for row in triplets:
        query_alias = "query:" + hashlib.sha256(row["query"].encode("utf-8")).hexdigest()
        # Every row always has the query alias; unioning above also attaches its case alias.
        row["split_group"] = find(query_alias)

    groups = sorted({row["split_group"] for row in triplets})
    random.Random(config.seed).shuffle(groups)
    validation_count = 0
    if config.validation_ratio and len(groups) > 1:
        validation_count = max(1, round(len(groups) * config.validation_ratio))
        validation_count = min(validation_count, len(groups) - 1)
    validation_groups = set(groups[:validation_count])
    train_rows = [row for row in triplets if row["split_group"] not in validation_groups]
    validation_rows = [row for row in triplets if row["split_group"] in validation_groups]

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    train_path = destination / "train.jsonl"
    validation_path = destination / "validation.jsonl"
    for path, split_rows in ((train_path, train_rows), (validation_path, validation_rows)):
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in split_rows), encoding="utf-8")
    split_manifest = {
        "dataset_id": "legal_retrieval_embedding_triplets",
        "dataset_version": dataset_version,
        "schema_version": TRAINING_SCHEMA_VERSION,
        "source_dataset": str(source),
        "source_content_sha256": actual_hash,
        "config": asdict(config),
        "record_count": len(triplets),
        "train_count": len(train_rows),
        "validation_count": len(validation_rows),
        "train_group_count": len(set(row["split_group"] for row in train_rows)),
        "validation_group_count": len(validation_groups),
        "domains": sorted({str(row["domain"]) for row in triplets}),
        "candidate_pool_versions": sorted({str(row["candidate_pool_version"]) for row in triplets}),
        "train_groups": sorted({str(row["split_group"]) for row in train_rows}),
        "validation_groups": sorted(validation_groups),
        "train_content_sha256": sha256_file(train_path),
        "validation_content_sha256": sha256_file(validation_path),
        "leakage_check": "passed",
    }
    split_manifest_path = destination / "manifest.json"
    split_manifest_path.write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"train": train_path, "validation": validation_path, "manifest": split_manifest_path, **split_manifest}


def create_embedding_training_run(
    prepared_manifest_path: str | Path,
    *,
    output_dir: str | Path,
    config: EmbeddingTrainingConfig,
    status: str = "planned",
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an experiment-compatible record without claiming unexecuted metrics."""
    config.validate()
    manifest_path = Path(prepared_manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "experiment_id": f"exp_embedding_{uuid4().hex}",
        "experiment_kind": "embedding_fine_tuning",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "dataset_id": manifest["dataset_id"],
            "dataset_version": manifest["dataset_version"],
            "case_count": manifest["record_count"],
            "content_sha256": sha256_file(manifest_path),
            "path": str(manifest_path),
        },
        "corpus": {"path": "training_dataset", "content_sha256": manifest["source_content_sha256"], "provision_count": 0},
        "code_version": __version__,
        "config": {"mode": "embedding_training", **asdict(config)},
        "model": {"provider": "sentence-transformers", "model": config.base_model, "prompt_version": "not_applicable"},
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "summary": {
            "status": status,
            "train_count": manifest["train_count"],
            "validation_count": manifest["validation_count"],
            "metrics": metrics or {},
            "metrics_note": "No performance claim is recorded until retrieval evaluation is executed.",
        },
        "artifacts": {"checkpoint_directory": str(Path(output_dir)), "prepared_manifest": str(manifest_path)},
        "cases": [],
    }
