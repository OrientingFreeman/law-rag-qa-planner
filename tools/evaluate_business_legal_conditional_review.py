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
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_conditional_review_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_conditional_review_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_CONDITIONAL_REVIEW_EVALUATION.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(service: LawRagService, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        response = service.answer(row["question"], top_k=int(row["top_k"]))
        review = response.get("composition", {}).get("conditional_review", {})
        priority = {str(item["fact_id"]): item for item in review.get("priority_facts", [])}
        links = {str(item["issue_id"]): item for item in review.get("fact_issue_action_links", [])}
        expected_facts = {str(item["fact_id"]): item for item in row["expected_missing_facts"]}
        expected_actions = {str(item["action_id"]): item for item in row["expected_actions"]}
        expected_issues = {str(item["issue_id"]) for item in row["expected_citations"]}

        matched_facts = set(expected_facts).intersection(priority)
        priority_recall = len(matched_facts) / len(expected_facts)
        first_fact_by_issue: dict[str, str] = {}
        for fact_id, item in expected_facts.items():
            first_fact_by_issue.setdefault(str(item["issue_id"]), fact_id)
        critical_hits = sum(
            priority.get(fact_id, {}).get("priority") == 1
            for fact_id in first_fact_by_issue.values()
        )
        critical_priority_accuracy = critical_hits / len(first_fact_by_issue)

        linked_issues = 0
        source_bound_issues = 0
        for issue_id in expected_issues:
            link = links.get(issue_id, {})
            fact_ids = {
                fact_id for fact_id, item in expected_facts.items()
                if str(item["issue_id"]) == issue_id
            }
            action_ids = {
                action_id for action_id, item in expected_actions.items()
                if str(item["issue_id"]) == issue_id
            }
            if fact_ids <= set(link.get("fact_ids", [])) and action_ids <= set(link.get("action_ids", [])):
                linked_issues += 1
            if link.get("citations"):
                source_bound_issues += 1
        linkage_coverage = linked_issues / len(expected_issues)
        source_binding = source_bound_issues / len(expected_issues)

        conditional_status = (
            review.get("review_status") == "additional_facts_required"
            and review.get("definitive_conclusion") is False
            and "조건부" in str(review.get("conclusion", ""))
            and "조건부 검토" in str(response.get("answer", ""))
        )
        passed = all((
            conditional_status,
            priority_recall == 1.0,
            critical_priority_accuracy == 1.0,
            linkage_coverage == 1.0,
            source_binding == 1.0,
        ))
        errors = []
        if not conditional_status:
            errors.append("missing_conditional_conclusion")
        if priority_recall < 1.0:
            errors.append("incomplete_fact_priority")
        if critical_priority_accuracy < 1.0:
            errors.append("incorrect_critical_fact_priority")
        if linkage_coverage < 1.0:
            errors.append("incomplete_fact_issue_action_links")
        if source_binding < 1.0:
            errors.append("unbound_issue_actions")
        cases.append({
            "case_id": row["case_id"],
            "conditional_conclusion": conditional_status,
            "priority_fact_recall": round(priority_recall, 4),
            "critical_priority_accuracy": round(critical_priority_accuracy, 4),
            "fact_issue_action_linkage": round(linkage_coverage, 4),
            "linked_issue_source_binding": round(source_binding, 4),
            "error_types": errors,
            "passed": passed,
        })

    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "conditional_conclusion_rate": round(mean(case["conditional_conclusion"] for case in cases), 4),
        "mean_priority_fact_recall": round(mean(case["priority_fact_recall"] for case in cases), 4),
        "critical_priority_accuracy": round(mean(case["critical_priority_accuracy"] for case in cases), 4),
        "fact_issue_action_linkage_rate": round(mean(case["fact_issue_action_linkage"] for case in cases), 4),
        "linked_issue_source_binding_rate": round(mean(case["linked_issue_source_binding"] for case in cases), 4),
    }
    return {
        "evaluation_name": "business_legal_conditional_review_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "provider": "deterministic/offline-template",
        "summary": summary,
        "cases": cases,
        "limitations": [
            "내부 8문항의 사전 정의 사실·쟁점·조치 ID를 이용한 구조 평가다.",
            "우선순위와 연결 구조가 개별 사건의 최종 법률 판단을 보증하지 않는다.",
            "외부 생성형 LLM의 법률답변 정확도를 측정하지 않는다.",
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
    return f"""# 기업 법무 조건부 검토·우선순위 평가

## 평가 목적

복수 쟁점 Q&A가 미확인 사실이 있는 상태에서 결론을 확정하지 않고, 중요 사실을
우선순위화한 뒤 각 사실을 쟁점·근거·실무 조치와 연결하는지 평가한다.

## 전후 결과

| 지표 | 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 조건부 결론 표시율 | {_pct(before['conditional_conclusion_rate'])} | {_pct(now['conditional_conclusion_rate'])} |
| 우선순위 사실 Recall | {_pct(before['mean_priority_fact_recall'])} | {_pct(now['mean_priority_fact_recall'])} |
| 쟁점별 핵심 우선순위 정확도 | {_pct(before['critical_priority_accuracy'])} | {_pct(now['critical_priority_accuracy'])} |
| 사실–쟁점–조치 연결률 | {_pct(before['fact_issue_action_linkage_rate'])} | {_pct(now['fact_issue_action_linkage_rate'])} |
| 연결 쟁점 근거 결속률 | {_pct(before['linked_issue_source_binding_rate'])} | {_pct(now['linked_issue_source_binding_rate'])} |

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python tools/evaluate_business_legal_conditional_review.py
```

## 해석상 한계

- 내부 8문항의 사전 정의 사실·쟁점·조치 ID를 사용한 결정론적 구조 평가다.
- 우선순위는 쟁점별 첫 번째 핵심 확인사항을 기준으로 검증하며 실제 사건별 긴급도를 자동 보증하지 않는다.
- 외부 생성형 LLM의 유창성·사실성·법률답변 정확도를 의미하지 않는다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate conditional review and fact-action linkage")
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
    print(
        f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; "
        f"conditional={summary['conditional_conclusion_rate']:.4f}; "
        f"linkage={summary['fact_issue_action_linkage_rate']:.4f}"
    )
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
