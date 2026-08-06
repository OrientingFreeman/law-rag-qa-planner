from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from law_rag.service import LawRagService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "business_legal_multi_issue_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_DOMAINS = ROOT / "domains"
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_multi_issue_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_multi_issue_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_MULTI_ISSUE_EVALUATION.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_cases(rows: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    article_keys = {(str(row["law_id"]), str(row["article_no"])) for row in corpus}
    ids: set[str] = set()
    if len(rows) != 8:
        errors.append(f"dataset must contain 8 cases, got {len(rows)}")
    for index, row in enumerate(rows):
        case_id = str(row.get("case_id", f"row-{index}"))
        if case_id in ids:
            errors.append(f"{case_id}: duplicate case_id")
        ids.add(case_id)
        if not case_id.startswith("multi-"):
            errors.append(f"{case_id}: case_id must start with multi-")
        citations = list(row.get("expected_citations") or [])
        if len(citations) < 2:
            errors.append(f"{case_id}: at least two expected citations are required")
        for citation in citations:
            key = (str(citation.get("law_id") or ""), str(citation.get("article_no") or ""))
            if key not in article_keys:
                errors.append(f"{case_id}: missing corpus article {key[0]}:{key[1]}")
            if not str(citation.get("issue_id") or "").strip():
                errors.append(f"{case_id}: issue_id is required for every citation")
        expected_issue_ids = {str(citation.get("issue_id")) for citation in citations}
        facts = list(row.get("expected_missing_facts") or [])
        if len(facts) < 4:
            errors.append(f"{case_id}: at least four expected missing facts are required")
        fact_ids = [str(fact.get("fact_id") or "").strip() for fact in facts]
        if any(not fact_id for fact_id in fact_ids):
            errors.append(f"{case_id}: fact_id is required for every expected missing fact")
        if len(fact_ids) != len(set(fact_ids)):
            errors.append(f"{case_id}: expected missing fact IDs must be unique")
        for fact in facts:
            issue_id = str(fact.get("issue_id") or "").strip()
            if issue_id not in expected_issue_ids:
                errors.append(f"{case_id}: missing fact issue_id must match an expected citation issue")
        actions = list(row.get("expected_actions") or [])
        if len(actions) < 4:
            errors.append(f"{case_id}: at least four expected actions are required")
        action_ids = [str(action.get("action_id") or "").strip() for action in actions]
        if any(not action_id for action_id in action_ids):
            errors.append(f"{case_id}: action_id is required for every expected action")
        if len(action_ids) != len(set(action_ids)):
            errors.append(f"{case_id}: expected action IDs must be unique")
        for action in actions:
            issue_id = str(action.get("issue_id") or "").strip()
            if issue_id not in expected_issue_ids:
                errors.append(f"{case_id}: action issue_id must match an expected citation issue")
        if row.get("expected_abstain"):
            errors.append(f"{case_id}: multi-issue cases must be answerable")
    return errors


def evaluate(service: LawRagService, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    for row in rows:
        started = perf_counter()
        response = service.retrieve(row["question"], top_k=int(row["top_k"]))
        latency_ms = (perf_counter() - started) * 1000
        retrieved = list(dict.fromkeys(
            (str(item["law_id"]), str(item["article_no"])) for item in response["results"]
        ))
        expected = [
            (str(item["law_id"]), str(item["article_no"]))
            for item in row["expected_citations"]
        ]
        matched = [key for key in expected if key in retrieved]
        full_coverage = len(matched) == len(expected)
        abstention_correct = bool(response["abstain"]) == bool(row["expected_abstain"])
        error_types = []
        if not full_coverage:
            error_types.append("issue_under_retrieval")
        if not abstention_correct:
            error_types.append("incorrect_abstention")
        cases.append({
            "case_id": row["case_id"],
            "question": row["question"],
            "expected_citations": [f"{law}:{article}" for law, article in expected],
            "retrieved_citations": [f"{law}:{article}" for law, article in retrieved],
            "matched_citations": [f"{law}:{article}" for law, article in matched],
            "issue_recall_at_k": round(len(matched) / len(expected), 4),
            "full_issue_coverage": full_coverage,
            "expected_abstain": bool(row["expected_abstain"]),
            "actual_abstain": bool(response["abstain"]),
            "abstention_correct": abstention_correct,
            "error_types": error_types,
            "passed": full_coverage and abstention_correct,
            "latency_ms": round(latency_ms, 3),
        })
    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "full_issue_coverage_rate": round(mean(case["full_issue_coverage"] for case in cases), 4),
        "mean_issue_recall_at_k": round(mean(case["issue_recall_at_k"] for case in cases), 4),
        "abstention_accuracy": round(mean(case["abstention_correct"] for case in cases), 4),
        "average_latency_ms": round(mean(case["latency_ms"] for case in cases), 3),
    }
    return {
        "evaluation_name": "business_legal_multi_issue_retrieval_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "summary": summary,
        "cases": cases,
        "limitations": [
            "내부 설계 8문항의 검색 평가이며 독립된 제3자 블라인드 벤치마크가 아니다.",
            "쟁점 회수는 생성형 답변의 법적 정확도나 실제 법률 실무 능력을 측정하지 않는다.",
            "Top-K 10 범위에서 필요한 조문을 모두 찾았는지 평가한다.",
        ],
    }


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    now = current["summary"]
    before = baseline["summary"]
    failures = [case for case in current["cases"] if not case["passed"]]
    failure_rows = "\n".join(
        f"| `{case['case_id']}` | {', '.join(case['error_types'])} | {case['issue_recall_at_k']:.2f} |"
        for case in failures
    ) or "| 없음 | 없음 | 1.00 |"
    return f"""# 기업 법무 복수 쟁점 검색 평가

## 평가 목적

한 질문에 전자금융·개인정보·특허·직무발명·저작권 쟁점이 둘 이상 포함됐을 때
각 쟁점의 근거 조문을 Top-10에서 빠짐없이 회수하는지 평가한다. 단일 정답
Top-1 평가와 달리, 이 평가는 질문 전체를 검토하는 `쟁점 완전성`에 초점을 둔다.

## 전후 결과

| 지표 | 복수 쟁점 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| Pass rate | {_pct(before['pass_rate'])} | {_pct(now['pass_rate'])} |
| 전체 쟁점 회수 문항 비율 | {_pct(before['full_issue_coverage_rate'])} | {_pct(now['full_issue_coverage_rate'])} |
| 평균 쟁점 Recall@10 | {_pct(before['mean_issue_recall_at_k'])} | {_pct(now['mean_issue_recall_at_k'])} |
| 유보 판단 정확도 | {_pct(before['abstention_accuracy'])} | {_pct(now['abstention_accuracy'])} |

## 현재 실패 문항

| case_id | 진단 | 쟁점 Recall@10 |
|---|---|---:|
{failure_rows}

## 재현 명령

```bash
python tools/evaluate_business_legal_multi_issue.py
```

## 해석상 한계

- 8문항은 공개 법령을 사용해 내부 설계한 평가이며 실제 사건 분포를 대표하지 않는다.
- 모든 쟁점의 정답 조문이 Top-10에 포함됐는지를 측정하며 검색 결과의 모든 후보가 정답이라는 뜻은 아니다.
- 생성형 답변의 법적 정확도, 계약 검토, 출원 가능성 또는 권리귀속 판단을 직접 평가하지 않는다.
- 구체적 사안에는 사실관계, 최신 법령, 판례·행정해석과 전문가 검토가 추가로 필요하다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate multi-issue business legal retrieval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--domains", type=Path, default=DEFAULT_DOMAINS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fail-under", type=float, default=1.0)
    args = parser.parse_args()
    rows = load_json(args.dataset)
    errors = validate_cases(rows, load_json(args.corpus))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    report = evaluate(LawRagService(data_path=args.corpus, domains_path=args.domains), rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.baseline.exists():
        args.report.write_text(render_markdown(report, load_json(args.baseline)), encoding="utf-8")
    summary = report["summary"]
    print(
        f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; "
        f"full_coverage={summary['full_issue_coverage_rate']:.4f}; "
        f"issue_recall@10={summary['mean_issue_recall_at_k']:.4f}"
    )
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
