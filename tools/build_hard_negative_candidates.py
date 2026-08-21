from __future__ import annotations

import argparse
import json
from pathlib import Path

from law_rag.evaluation.hard_negatives import (
    JsonlCandidateStore,
    build_hard_negative_candidates,
    select_review_candidates,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build review-required hard-negative candidates")
    parser.add_argument("benchmark", help="retrieval benchmark JSON")
    parser.add_argument("--corpus", default="data/legal_corpus.json")
    parser.add_argument("--methods", nargs="+", default=["hybrid"])
    parser.add_argument("--candidate-pool-version", default="0.1.0")
    parser.add_argument("--max-negatives", type=int, default=3)
    parser.add_argument("--domains", nargs="+", help="Only keep candidates from these domains")
    parser.add_argument("--limit", type=int, help="Maximum candidates written after filtering")
    parser.add_argument("--one-per-case", action="store_true", help="Keep one review candidate per evaluation case")
    parser.add_argument("--output", default="evaluation/training/hard_negative_candidates.jsonl")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    candidates = build_hard_negative_candidates(
        report,
        corpus_path=args.corpus,
        methods=set(args.methods),
        candidate_pool_version=args.candidate_pool_version,
        max_negatives=args.max_negatives,
    )
    generated = len(candidates)
    candidates = select_review_candidates(
        candidates,
        domains=set(args.domains) if args.domains else None,
        limit=args.limit,
        one_per_case=args.one_per_case,
    )
    result = JsonlCandidateStore(args.output).append_unique(candidates)
    print(json.dumps({
        "generated": generated,
        "selected": len(candidates),
        "domains": args.domains,
        **result,
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
