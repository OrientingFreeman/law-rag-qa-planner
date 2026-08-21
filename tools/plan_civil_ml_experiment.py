from __future__ import annotations

import argparse
import json

from law_rag.evaluation.experiments import ExperimentStore
from law_rag.evaluation.ml_experiment_gate import CivilMlGateConfig, build_civil_ml_gate_report
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL
from law_rag.retrieval.reranker import DEFAULT_RERANKER_MODEL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check civil-law ML experiment prerequisites without running a model")
    parser.add_argument("--prepared-manifest", default="evaluation/training/civil_embedding_dataset/manifest.json")
    parser.add_argument("--evaluation-dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--target-domain", default="civil_transactions")
    parser.add_argument("--checkpoint", default="evaluation/training/checkpoints/civil-retrieval-v1")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--experiment-dir", default="evaluation/experiments")
    args = parser.parse_args(argv)
    report = build_civil_ml_gate_report(CivilMlGateConfig(
        prepared_manifest=args.prepared_manifest,
        evaluation_dataset=args.evaluation_dataset,
        target_domain=args.target_domain,
        checkpoint_path=args.checkpoint,
        embedding_model=args.embedding_model,
        reranker_model=args.reranker_model,
    ))
    output = ExperimentStore(args.experiment_dir).save(report)
    print(json.dumps({
        "output": str(output), "experiment_id": report["experiment_id"],
        **report["summary"], "experiment_matrix": report["experiment_matrix"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
