from __future__ import annotations

import argparse
import json

from law_rag.evaluation.hard_negatives import JsonlCandidateStore, export_approved_training_dataset
from law_rag.evaluation.reviews import JsonReviewStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export approved hard negatives as a versioned dataset")
    parser.add_argument("--candidates", default="evaluation/training/hard_negative_candidates.jsonl")
    parser.add_argument("--reviews", default="evaluation/reviews/review_records.jsonl")
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--output", default="evaluation/training/hard_negative_dataset.jsonl")
    parser.add_argument("--domains", nargs="+", help="Export only approved candidates in these domains")
    parser.add_argument(
        "--candidate-pool-versions", nargs="+",
        help="Export only approved candidates from these candidate pool versions",
    )
    args = parser.parse_args(argv)
    try:
        output, manifest_path, manifest = export_approved_training_dataset(
            JsonlCandidateStore(args.candidates), JsonReviewStore(args.reviews),
            output_path=args.output, dataset_version=args.dataset_version,
            domains=set(args.domains) if args.domains else None,
            candidate_pool_versions=(
                set(args.candidate_pool_versions) if args.candidate_pool_versions else None
            ),
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"output": str(output), "manifest": str(manifest_path), **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
