from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

from law_rag.evaluation.datasets import sha256_file
from law_rag.evaluation.embedding_training import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingTrainingConfig,
    create_embedding_training_run,
)
from law_rag.evaluation.experiments import ExperimentStore


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validate_prepared_dataset(manifest_path: Path) -> tuple[dict[str, Any], Path, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    train_path = manifest_path.parent / "train.jsonl"
    validation_path = manifest_path.parent / "validation.jsonl"
    if sha256_file(train_path) != manifest["train_content_sha256"]:
        raise ValueError("train split hash does not match its manifest")
    if sha256_file(validation_path) != manifest["validation_content_sha256"]:
        raise ValueError("validation split hash does not match its manifest")
    train_groups = {row["split_group"] for row in _read_rows(train_path)}
    validation_groups = {row["split_group"] for row in _read_rows(validation_path)}
    if train_groups.intersection(validation_groups):
        raise ValueError("train/validation leakage detected")
    return manifest, train_path, validation_path


def _execute_training(train_path: Path, validation_path: Path, output_dir: Path, config: EmbeddingTrainingConfig) -> dict[str, Any]:
    try:
        import torch
        from sentence_transformers import InputExample, SentenceTransformer, evaluation, losses
        from torch.utils.data import DataLoader
    except ImportError as exc:
        raise RuntimeError("install the optional ML dependencies first: pip install -e '.[ml]'") from exc
    random.seed(config.seed)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    model = SentenceTransformer(config.base_model)
    model.max_seq_length = config.max_seq_length
    train_rows = _read_rows(train_path)
    train_examples = [InputExample(texts=[row["query"], row["positive"], row["hard_negative"]]) for row in train_rows]
    loader = DataLoader(train_examples, shuffle=True, batch_size=config.batch_size)
    loss = losses.TripletLoss(model=model, triplet_margin=config.triplet_margin)
    validation_rows = _read_rows(validation_path)
    evaluator = None
    if validation_rows:
        evaluator = evaluation.TripletEvaluator(
            anchors=[row["query"] for row in validation_rows],
            positives=[row["positive"] for row in validation_rows],
            negatives=[row["hard_negative"] for row in validation_rows],
            name="legal-retrieval-validation",
        )
    warmup_steps = math.ceil(len(loader) * config.epochs * config.warmup_ratio)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.fit(
        train_objectives=[(loader, loss)],
        evaluator=evaluator,
        epochs=config.epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": config.learning_rate},
        output_path=str(output_dir),
        show_progress_bar=True,
    )
    return {
        "training_completed": True,
        "device": str(model.device),
        "train_examples": len(train_rows),
        "validation_examples": len(validation_rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute legal retrieval embedding fine-tuning")
    parser.add_argument("--prepared-manifest", default="evaluation/training/embedding_dataset/manifest.json")
    parser.add_argument("--checkpoint-dir", default="evaluation/training/checkpoints/legal-retrieval")
    parser.add_argument("--experiment-dir", default="evaluation/experiments")
    parser.add_argument("--execute", action="store_true", help="Download/load the model and actually train; omitted means plan-only")
    parser.add_argument("--base-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--triplet-margin", type=float, default=0.25)
    args = parser.parse_args(argv)
    config = EmbeddingTrainingConfig(
        base_model=args.base_model,
        seed=args.seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        triplet_margin=args.triplet_margin,
    )
    try:
        _, train_path, validation_path = _validate_prepared_dataset(Path(args.prepared_manifest))
        metrics = _execute_training(train_path, validation_path, Path(args.checkpoint_dir), config) if args.execute else {}
        report = create_embedding_training_run(
            args.prepared_manifest,
            output_dir=args.checkpoint_dir,
            config=config,
            status="completed" if args.execute else "planned",
            metrics=metrics,
        )
        saved = ExperimentStore(args.experiment_dir).save(report)
    except (ValueError, OSError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"experiment": str(saved), **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
