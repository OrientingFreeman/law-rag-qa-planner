from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from law_rag.evaluation.runner import EvaluationRunner, load_dataset, write_report
from law_rag.service import LawRagService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "business_legal_robustness_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_DOMAINS = ROOT / "domains"
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_robustness_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_robustness_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_QUERY_ROBUSTNESS.md"

ALLOWED_DOMAINS = {"electronic_finance", "digital_business", "intellectual_property"}
ALLOWED_VARIANTS = {"reference", "lay"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_cases(rows: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    article_keys = {(str(row["law_id"]), str(row["article_no"])) for row in corpus}
    ids: set[str] = set()
    pairs: dict[str, set[str]] = defaultdict(set)
    if len(rows) != 24:
        errors.append(f"dataset must contain 24 cases, got {len(rows)}")
    for index, row in enumerate(rows):
        case_id = str(row.get("case_id", f"row-{index}"))
        if case_id in ids:
            errors.append(f"{case_id}: duplicate case_id")
        ids.add(case_id)
        if not case_id.startswith("robust-"):
            errors.append(f"{case_id}: case_id must start with robust-")
        pair_id = str(row.get("pair_id") or "")
        variant = str(row.get("variant") or "")
        if not pair_id:
            errors.append(f"{case_id}: pair_id is required")
        if variant not in ALLOWED_VARIANTS:
            errors.append(f"{case_id}: unsupported variant {variant}")
        pairs[pair_id].add(variant)
        if row.get("domain") not in ALLOWED_DOMAINS:
            errors.append(f"{case_id}: unsupported domain {row.get('domain')}")
        if row.get("expected_abstain"):
            errors.append(f"{case_id}: robustness cases must be answerable")
        law_id = str(row.get("expected_law_id") or "")
        articles = [str(value) for value in row.get("expected_article_nos") or []]
        if not law_id or not articles:
            errors.append(f"{case_id}: gold law and articles are required")
        for article in articles:
            if (law_id, article) not in article_keys:
                errors.append(f"{case_id}: missing corpus article {law_id}:{article}")
    if len(pairs) != 12:
        errors.append(f"dataset must contain 12 pairs, got {len(pairs)}")
    for pair_id, variants in pairs.items():
        if variants != ALLOWED_VARIANTS:
            errors.append(f"{pair_id}: pair must contain reference and lay variants")
    return errors


def add_pair_metrics(report: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    metadata = {str(row["case_id"]): row for row in rows}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in report["cases"]:
        source = metadata[str(result["case_id"])]
        result["pair_id"] = source["pair_id"]
        result["variant"] = source["variant"]
        grouped[str(source["pair_id"])].append(result)

    pair_rows = []
    for pair_id, cases in sorted(grouped.items()):
        passed = len(cases) == 2 and all(bool(case["passed"]) for case in cases)
        top1_stable = len(cases) == 2 and all(bool(case["top1_hit"]) for case in cases)
        pair_rows.append({"pair_id": pair_id, "passed": passed, "top1_gold_stable": top1_stable})
    report["pair_metrics"] = {
        "total_pairs": len(pair_rows),
        "passed_pairs": sum(row["passed"] for row in pair_rows),
        "pair_pass_rate": round(sum(row["passed"] for row in pair_rows) / len(pair_rows), 4),
        "top1_gold_stable_pairs": sum(row["top1_gold_stable"] for row in pair_rows),
        "top1_gold_stability": round(sum(row["top1_gold_stable"] for row in pair_rows) / len(pair_rows), 4),
        "pairs": pair_rows,
    }


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    now = current["summary"]
    before = baseline["summary"]
    now_pairs = current["pair_metrics"]
    before_pairs = baseline["pair_metrics"]
    failures = [row for row in current["cases"] if not row["passed"]]
    failure_rows = "\n".join(
        f"| `{row['case_id']}` | {', '.join(row['error_types']) or '없음'} |"
        for row in failures
    ) or "| 없음 | 없음 |"
    return f"""# 기업 법무 질의 표현 견고성 평가

## 평가 목적

같은 법적 쟁점을 전문용어가 포함된 기준 질문과 일상적인 업무 표현으로 각각
질문했을 때 동일한 정답 조문을 회수하는지 확인한다. 전자금융·개인정보·
지식재산 12개 쟁점에 2개 표현을 구성하여 총 24문항을 실제 하이브리드 검색
파이프라인으로 평가했다.

## 전후 결과

| 지표 | 표현 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 문항 Pass rate | {_pct(before['pass_rate'])} | {_pct(now['pass_rate'])} |
| Top-1 Accuracy | {_pct(before['top1_accuracy'])} | {_pct(now['top1_accuracy'])} |
| Hit@5 | {_pct(before['hit_at_k'])} | {_pct(now['hit_at_k'])} |
| Recall@5 | {_pct(before['mean_recall_at_k'])} | {_pct(now['mean_recall_at_k'])} |
| MRR | {before['mean_reciprocal_rank']:.4f} | {now['mean_reciprocal_rank']:.4f} |
| 쌍 단위 통과 | {before_pairs['passed_pairs']}/{before_pairs['total_pairs']} | {now_pairs['passed_pairs']}/{now_pairs['total_pairs']} |
| 쌍 단위 Top-1 정답 안정성 | {_pct(before_pairs['top1_gold_stability'])} | {_pct(now_pairs['top1_gold_stability'])} |

`쌍 단위 통과`는 기준 표현과 일상 표현이 모두 정답 조문을 회수하고 유보 판단도
맞아야 통과한다. `Top-1 정답 안정성`은 두 표현 모두 첫 번째 검색 결과가 정답
조문인지 측정하며, 두 결과의 점수가 동일하다는 뜻은 아니다.

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
python tools/evaluate_business_legal_robustness.py
```

## 해석상 한계

- 24문항은 공개 법령을 사용해 내부 설계한 평가이며 독립된 제3자 블라인드 평가가 아니다.
- 표현 변형은 법률용어 제거, 업무식 서술, 동의어 치환을 중심으로 작성했으며 실제 사용자 질의 분포를 대표하지 않는다.
- 검색 지표는 정답 조문 회수 성능을 뜻하며 생성형 답변의 법적 정확도나 법률 실무 능력을 직접 측정하지 않는다.
- 구체적 사안은 사실관계, 최신 법령, 판례·행정해석 및 전문가 검토가 추가로 필요하다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate business legal query robustness")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--domains", type=Path, default=DEFAULT_DOMAINS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fail-under", type=float, default=1.0)
    args = parser.parse_args()

    rows = load_json(args.dataset)
    corpus = load_json(args.corpus)
    errors = validate_cases(rows, corpus)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1

    service = LawRagService(data_path=args.corpus, domains_path=args.domains)
    report = EvaluationRunner(service).run(load_dataset(args.dataset))
    report["evaluation_name"] = "business_legal_query_robustness_v1"
    report["dataset"] = str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset)
    add_pair_metrics(report, rows)
    report["limitations"] = [
        "설계된 24문항의 표현 변형 평가이며 독립된 제3자 블라인드 벤치마크가 아니다.",
        "검색 지표는 생성형 답변의 법적 정확도를 측정하지 않는다.",
        "실제 사용자 질의 분포를 대표하지 않는다.",
    ]
    write_report(report, args.output)
    if args.baseline.exists():
        args.report.write_text(render_markdown(report, load_json(args.baseline)), encoding="utf-8")
    summary = report["summary"]
    pairs = report["pair_metrics"]
    print(
        f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; "
        f"top1={summary['top1_accuracy']:.4f}; hit@5={summary['hit_at_k']:.4f}; "
        f"pairs={pairs['passed_pairs']}/{pairs['total_pairs']}"
    )
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
