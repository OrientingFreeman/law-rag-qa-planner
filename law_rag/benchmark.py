from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from law_rag.evaluation.failures import FailureCaseLogger, failure_payload
from law_rag.evaluation.runner import EvaluationRunner, load_dataset, write_report
from law_rag.service import LawRagService


def _percent(value: Any) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def format_summary(summary: dict[str, Any]) -> str:
    rows = [
        ("Cases", f"{summary['passed_cases']}/{summary['total_cases']}"),
        ("Pass rate", _percent(summary["pass_rate"])),
        ("Top-1 accuracy", _percent(summary["top1_accuracy"])),
        ("Hit@K", _percent(summary["hit_at_k"])),
        ("Recall@K", _percent(summary["mean_recall_at_k"])),
        ("MRR", f"{float(summary['mean_reciprocal_rank']):.4f}"),
        ("Citation accuracy", "n/a" if summary["citation_accuracy"] is None else _percent(summary["citation_accuracy"])),
        ("Average latency", f"{float(summary['average_latency_ms']):.1f} ms"),
    ]
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label:<{width}}  {value}" for label, value in rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Law RAG benchmark CLI")
    parser.add_argument("--dataset", default="evaluation/datasets/official_core_cases.json")
    parser.add_argument("--output", default="evaluation/reports/latest.json")
    parser.add_argument("--failures", default="evaluation/failures/failure_cases.jsonl")
    parser.add_argument("--data", default="data/legal_corpus.json")
    parser.add_argument("--domains", default="domains")
    parser.add_argument("--fail-under", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="Print summary as JSON")
    parser.add_argument("--no-log-failures", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = LawRagService(data_path=args.data, domains_path=args.domains)
    report = EvaluationRunner(service).run(load_dataset(args.dataset))
    report["dataset"] = str(Path(args.dataset))
    write_report(report, args.output)

    failed = [case for case in report["cases"] if not case["passed"]]
    if failed and not args.no_log_failures:
        logger = FailureCaseLogger(args.failures)
        logger.append_many(failure_payload(case, dataset=args.dataset) for case in failed)

    if args.json:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    else:
        print(format_summary(report["summary"]))
        print(f"Report           {args.output}")
        if failed and not args.no_log_failures:
            print(f"Failure log      {args.failures} ({len(failed)} new)")

    return 1 if float(report["summary"]["pass_rate"]) < args.fail_under else 0


if __name__ == "__main__":
    raise SystemExit(main())
