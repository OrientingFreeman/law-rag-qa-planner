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
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_practical_actions_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_practical_actions_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_PRACTICAL_ACTION_EVALUATION.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(service: LawRagService, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        response = service.answer(row["question"], top_k=int(row["top_k"]))
        generator = response.get("composition", {}).get("practical_action_generator", {})
        actions = {str(item["action_id"]): item for item in generator.get("actions", [])}
        expected = {str(item["action_id"]): item for item in row["expected_actions"]}
        matched = sorted(set(expected).intersection(actions))
        expected_issues = {str(item["issue_id"]) for item in expected.values()}
        covered_issues = {str(actions[action_id].get("issue_id")) for action_id in matched}
        plan_action_ids = {
            str(sentence.get("sentence_id"))
            for section in response.get("composition", {}).get("answer_plan", {}).get("sections", [])
            for sentence in section.get("sentences", [])
            if sentence.get("sentence_type") == "practical_action"
        }
        source_bound = [
            action_id for action_id in matched
            if actions[action_id].get("citations")
            and actions[action_id].get("source_rule_ids")
            and actions[action_id].get("source_document_ids")
        ]
        action_recall = len(matched) / len(expected)
        issue_coverage = len(expected_issues.intersection(covered_issues)) / len(expected_issues)
        source_binding = len(source_bound) / len(expected)
        answer_plan_recall = len(set(expected).intersection(plan_action_ids)) / len(expected)
        passed = action_recall == 1.0 and issue_coverage == 1.0 and source_binding == 1.0 and answer_plan_recall == 1.0
        errors = []
        if action_recall < 1.0:
            errors.append("missing_practical_actions")
        if issue_coverage < 1.0:
            errors.append("incomplete_action_issue_coverage")
        if source_binding < 1.0:
            errors.append("unbound_practical_actions")
        if answer_plan_recall < 1.0:
            errors.append("actions_not_in_answer_plan")
        cases.append({
            "case_id": row["case_id"],
            "expected_action_ids": sorted(expected),
            "generated_action_ids": sorted(actions),
            "matched_action_ids": matched,
            "practical_action_recall": round(action_recall, 4),
            "action_issue_coverage": round(issue_coverage, 4),
            "source_binding_rate": round(source_binding, 4),
            "answer_plan_action_recall": round(answer_plan_recall, 4),
            "error_types": errors,
            "passed": passed,
        })

    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "mean_practical_action_recall": round(mean(case["practical_action_recall"] for case in cases), 4),
        "mean_action_issue_coverage": round(mean(case["action_issue_coverage"] for case in cases), 4),
        "source_binding_rate": round(mean(case["source_binding_rate"] for case in cases), 4),
        "mean_answer_plan_action_recall": round(mean(case["answer_plan_action_recall"] for case in cases), 4),
    }
    return {
        "evaluation_name": "business_legal_practical_actions_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "provider": "deterministic/offline-template",
        "summary": summary,
        "cases": cases,
        "limitations": [
            "내부 8문항에 사전 정의한 실무 조치 ID의 생성·근거 연결을 평가한다.",
            "조치의 법률적 충분성이나 개별 조직의 실제 업무절차 적합성을 자동 보증하지 않는다.",
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
    return f"""# 기업 법무 실무 조치 평가

## 평가 목적

복수 쟁점 답변이 획일적인 안내 대신 쟁점별로 구체적인 후속 조치를 제시하고,
각 조치가 검색된 규칙과 원문 문서에 연결되는지 평가한다.

## 전후 결과

| 지표 | 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 평균 실무 조치 Recall | {_pct(before['mean_practical_action_recall'])} | {_pct(now['mean_practical_action_recall'])} |
| 평균 쟁점별 조치 커버리지 | {_pct(before['mean_action_issue_coverage'])} | {_pct(now['mean_action_issue_coverage'])} |
| 조치-근거 결속률 | {_pct(before['source_binding_rate'])} | {_pct(now['source_binding_rate'])} |
| 답변 계획 조치 Recall | {_pct(before['mean_answer_plan_action_recall'])} | {_pct(now['mean_answer_plan_action_recall'])} |

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python tools/evaluate_business_legal_practical_actions.py
```

## 해석상 한계

- 내부 8문항에 사전 정의한 실무 조치의 생성과 근거 연결을 평가한다.
- 조치의 법률적 충분성이나 개별 조직의 실제 절차 적합성을 자동 보증하지 않는다.
- 외부 생성형 LLM의 유창성·사실성·법률답변 정확도를 의미하지 않는다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate issue-specific practical actions")
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
    print(f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; action_recall={summary['mean_practical_action_recall']:.4f}; source_binding={summary['source_binding_rate']:.4f}")
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
