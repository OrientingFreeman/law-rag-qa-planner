"""Run a reproducible baseline or Agent Workflow experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from law_rag.evaluation.experiments import ExperimentConfig, ExperimentRunner, ExperimentStore
from law_rag.service import LawRagService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "agent"), required=True)
    parser.add_argument("--dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--dataset-version", default="2.0")
    parser.add_argument("--search-strategy", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    parser.add_argument("--no-query-rewrite", action="store_true")
    parser.add_argument("--no-reranking", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--output-dir", default="evaluation/experiments")
    args = parser.parse_args()
    config = ExperimentConfig(
        mode=args.mode,
        dataset_path=args.dataset,
        dataset_version=args.dataset_version,
        search_strategy=args.search_strategy,
        query_rewrite=not args.no_query_rewrite,
        reranking=not args.no_reranking,
        max_retries=args.max_retries,
    )
    report = ExperimentRunner(LawRagService()).run(config, limit=args.limit)
    path = ExperimentStore(args.output_dir).save(report)
    print(json.dumps({
        "experiment_id": report["experiment_id"],
        "mode": args.mode,
        "cases": report["summary"]["total_cases"],
        "pass_rate": report["summary"]["overall_pass_rate"],
        "average_latency_ms": report["summary"]["average_latency_ms"],
        "output": str(path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
