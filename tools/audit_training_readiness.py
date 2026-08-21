from __future__ import annotations

import argparse
import json
from pathlib import Path

from law_rag.evaluation.training_readiness import audit_training_readiness, save_readiness_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit domain training and human-review readiness")
    parser.add_argument("--domain", default="civil_transactions")
    parser.add_argument("--dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--corpus", default="data/legal_corpus.json")
    parser.add_argument("--domains-path", default="domains")
    parser.add_argument("--benchmark", help="Optional retrieval benchmark JSON used for failure candidates")
    parser.add_argument("--method", default="hybrid")
    parser.add_argument("--review-limit", type=int, default=20)
    parser.add_argument("--output", default="evaluation/training/readiness_civil_transactions.json")
    args = parser.parse_args(argv)
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8")) if args.benchmark else None
    report = audit_training_readiness(
        target_domain=args.domain,
        dataset_path=args.dataset,
        corpus_path=args.corpus,
        domains_path=args.domains_path,
        benchmark=benchmark,
        method=args.method,
        review_limit=args.review_limit,
    )
    output = save_readiness_report(report, args.output)
    print(json.dumps({
        "output": str(output),
        "target_domain": report["target_domain"],
        "retrieval_case_count": report["evaluation"]["retrieval_case_count"],
        "candidate_count": report["failure_analysis"]["candidate_count"],
        "manual_review_selected_count": report["manual_review_batch"]["selected_count"],
        "gates": report["gates"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
