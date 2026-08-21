from __future__ import annotations

import argparse
import json

from law_rag.evaluation.embedding_training import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingTrainingConfig,
    prepare_embedding_training_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare deterministic train/validation triplets for embedding fine-tuning")
    parser.add_argument("--dataset", default="evaluation/training/hard_negative_dataset.jsonl")
    parser.add_argument("--manifest")
    parser.add_argument("--output-dir", default="evaluation/training/embedding_dataset")
    parser.add_argument("--base-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    args = parser.parse_args(argv)
    try:
        result = prepare_embedding_training_dataset(
            args.dataset,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            config=EmbeddingTrainingConfig(
                base_model=args.base_model,
                seed=args.seed,
                validation_ratio=args.validation_ratio,
            ),
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    printable = {key: str(value) if key in {"train", "validation", "manifest"} else value for key, value in result.items()}
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
