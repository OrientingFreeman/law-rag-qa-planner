from __future__ import annotations

import argparse
import json

from law_rag.evaluation.retrieval_ablation import (
    ABLATION_METHODS,
    RetrievalAblationConfig,
    RetrievalAblationRunner,
    save_ablation_report,
)
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL
from law_rag.retrieval.reranker import DEFAULT_RERANKER_MODEL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute a versioned retrieval ablation matrix")
    parser.add_argument("--dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--corpus", default="data/legal_corpus.json")
    parser.add_argument("--domains", default="domains")
    parser.add_argument("--methods", nargs="+", choices=ABLATION_METHODS, default=list(ABLATION_METHODS))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--retrieval-top-n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--fine-tuned-embedding-model")
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--regression-tolerance", type=float, default=0.0)
    parser.add_argument("--no-query-rewrite", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Actually execute available methods; omitted means plan-only")
    parser.add_argument("--experiment-dir", default="evaluation/experiments")
    args = parser.parse_args(argv)
    try:
        report = RetrievalAblationRunner(RetrievalAblationConfig(
            dataset_path=args.dataset,
            corpus_path=args.corpus,
            domains_path=args.domains,
            methods=tuple(args.methods),
            top_k=args.top_k,
            retrieval_top_n=args.retrieval_top_n,
            seed=args.seed,
            embedding_model=args.embedding_model,
            fine_tuned_embedding_model=args.fine_tuned_embedding_model,
            reranker_model=args.reranker_model,
            query_rewrite=not args.no_query_rewrite,
            regression_tolerance=args.regression_tolerance,
        )).run(execute=args.execute)
        path = save_ablation_report(report, args.experiment_dir)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"output": str(path), "experiment_id": report["experiment_id"], **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
