from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "business_legal_multi_issue_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_DOMAINS = ROOT / "domains"
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_missing_facts_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_missing_facts_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_MISSING_FACT_EVALUATION.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(service: LawRagService, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        response = service.answer(row["question"], top_k=int(row["top_k"]))
        detector = response.get("composition", {}).get("missing_fact_detector", {})
        detected = {str(item["fact_id"]): item for item in detector.get("facts", [])}
        expected = {str(item["fact_id"]): item for item in row["expected_missing_facts"]}
        matched = sorted(set(expected).intersection(detected))
        expected_issues = {str(item["issue_id"]) for item in expected.values()}
        covered_issues = {
            str(detected[fact_id].get("issue_id"))
            for fact_id in matched
            if detected[fact_id].get("issue_id")
        }
        plan_facts = {
            str(sentence.get("sentence_id", "")).removeprefix("additional:")
            for section in response.get("composition", {}).get("answer_plan", {}).get("sections", [])
            for sentence in section.get("sentences", [])
            if sentence.get("sentence_type") == "additional_fact"
        }
        fact_recall = len(matched) / len(expected)
        issue_coverage = len(expected_issues.intersection(covered_issues)) / len(expected_issues)
        answer_plan_recall = len(set(expected).intersection(plan_facts)) / len(expected)
        conditional = detector.get("complete_for_final_advice") is False
        passed = fact_recall == 1.0 and issue_coverage == 1.0 and answer_plan_recall == 1.0 and conditional
        errors = []
        if fact_recall < 1.0:
            errors.append("missing_material_fact_questions")
        if issue_coverage < 1.0:
            errors.append("incomplete_issue_fact_coverage")
        if answer_plan_recall < 1.0:
            errors.append("missing_facts_not_in_answer_plan")
        if not conditional:
            errors.append("unqualified_final_advice")
        cases.append({
            "case_id": row["case_id"],
            "expected_fact_ids": sorted(expected),
            "detected_fact_ids": sorted(detected),
            "matched_fact_ids": matched,
            "missing_fact_recall": round(fact_recall, 4),
            "issue_fact_coverage": round(issue_coverage, 4),
            "answer_plan_fact_recall": round(answer_plan_recall, 4),
            "conditional_advice": conditional,
            "error_types": errors,
            "passed": passed,
        })

    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "mean_missing_fact_recall": round(mean(case["missing_fact_recall"] for case in cases), 4),
        "mean_issue_fact_coverage": round(mean(case["issue_fact_coverage"] for case in cases), 4),
        "mean_answer_plan_fact_recall": round(mean(case["answer_plan_fact_recall"] for case in cases), 4),
        "conditional_advice_rate": round(mean(case["conditional_advice"] for case in cases), 4),
    }
    return {
        "evaluation_name": "business_legal_missing_facts_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "provider": "deterministic/offline-template",
        "summary": summary,
        "cases": cases,
        "limitations": [
            "내부 8문항에 사전 정의한 핵심 확인 사실의 회수 여부를 평가한다.",
            "사실 확인 질문의 법률적 완전성이나 실제 사건에 대한 최종 판단을 자동 보증하지 않는다.",
            "외부 생성형 LLM의 답변 정확도를 측정하지 않는다.",
        ],
    }


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    now, before = current["summary"], baseline["summary"]
    failures = [case for case in current["cases"] if not case["passed"]]
    failure_rows = "\n".join(
        f"| `{case['case_id']}` | {', '.join(case['error_types']) or '없음'} |" for case in failures
    ) or "| 없음 | 없음 |"
    return f"""# 기업 법무 핵심 사실 확인 평가

## 평가 목적

복수 쟁점 질문에 법률 판단을 바꿀 수 있는 핵심 사실이 빠져 있을 때, 쟁점별
확인 질문을 생성하고 최종 조언을 조건부로 유지하는지 평가한다.

## 전후 결과

| 지표 | 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 평균 핵심 사실 Recall | {_pct(before['mean_missing_fact_recall'])} | {_pct(now['mean_missing_fact_recall'])} |
| 평균 쟁점별 사실 커버리지 | {_pct(before['mean_issue_fact_coverage'])} | {_pct(now['mean_issue_fact_coverage'])} |
| 답변 계획 사실 Recall | {_pct(before['mean_answer_plan_fact_recall'])} | {_pct(now['mean_answer_plan_fact_recall'])} |
| 조건부 조언 유지율 | {_pct(before['conditional_advice_rate'])} | {_pct(now['conditional_advice_rate'])} |

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python tools/evaluate_business_legal_missing_facts.py
```

## 해석상 한계

- 내부 8문항에 사전 정의한 확인 사실의 회수 여부를 평가한다.
- 확인 질문의 법률적 완전성이나 개별 사건의 최종 결론을 자동 보증하지 않는다.
- 외부 생성형 LLM의 유창성·사실성·법률답변 정확도를 의미하지 않는다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate material missing-fact questions")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--domains", type=Path, default=DEFAULT_DOMAINS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fail-under", type=float, default=1.0)
    args = parser.parse_args()
    service = LawRagService(data_path=args.corpus, domains_path=args.domains, llm_provider=DeterministicProvider())
    report = evaluate(service, load_json(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.baseline.exists():
        args.report.write_text(render_markdown(report, load_json(args.baseline)), encoding="utf-8")
    summary = report["summary"]
    print(f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; fact_recall={summary['mean_missing_fact_recall']:.4f}; issue_coverage={summary['mean_issue_fact_coverage']:.4f}")
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
