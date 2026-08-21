from __future__ import annotations

import argparse
import json

from law_rag.evaluation.retrieval_benchmark import (
    RetrievalBenchmarkConfig,
    RetrievalBenchmarkRunner,
    write_retrieval_benchmark,
)
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL
from law_rag.retrieval.reranker import DEFAULT_RERANKER_MODEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare retrieval methods on one versioned dataset")
    parser.add_argument("--dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--corpus", default="data/legal_corpus.json")
    parser.add_argument("--domains", default="domains")
    parser.add_argument(
        "--methods", nargs="+", default=["bm25", "semantic_lite", "hybrid"],
        choices=sorted(RetrievalBenchmarkRunner.supported_methods),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--fine-tuned-embedding-model")
    parser.add_argument("--reranker-model", default=DEFAULT_RERANKER_MODEL)
    parser.add_argument("--retrieval-top-n", type=int, default=20)
    parser.add_argument("--no-query-rewrite", action="store_true")
    parser.add_argument("--output", default="evaluation/benchmarks/retrieval_latest.json")
    parser.add_argument("--fail-under-hit-at-k", type=float)
    parser.add_argument("--fail-under-mrr", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RetrievalBenchmarkConfig(
        dataset_path=args.dataset,
        corpus_path=args.corpus,
        domains_path=args.domains,
        methods=tuple(args.methods),
        top_k=args.top_k,
        seed=args.seed,
        embedding_model=args.embedding_model,
        fine_tuned_embedding_model=args.fine_tuned_embedding_model,
        reranker_model=args.reranker_model,
        retrieval_top_n=args.retrieval_top_n,
        query_rewrite=not args.no_query_rewrite,
    )
    report = RetrievalBenchmarkRunner(config).run()
    path = write_retrieval_benchmark(report, args.output)
    print(json.dumps({
        "output": str(path),
        "selection": report["selection"],
        "results": [
            {"method": row["method"], **row["metrics"]} for row in report["results"]
        ],
    }, ensure_ascii=False, indent=2))
    failures = []
    for result in report["results"]:
        metrics = result["metrics"]
        if args.fail_under_hit_at_k is not None and metrics["hit_at_k"] < args.fail_under_hit_at_k:
            failures.append(
                f"{result['method']} hit_at_k {metrics['hit_at_k']:.6f} < {args.fail_under_hit_at_k:.6f}"
            )
        if args.fail_under_mrr is not None and metrics["mrr"] < args.fail_under_mrr:
            failures.append(
                f"{result['method']} mrr {metrics['mrr']:.6f} < {args.fail_under_mrr:.6f}"
            )
    if failures:
        print("retrieval regression: " + "; ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
