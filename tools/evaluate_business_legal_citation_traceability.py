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
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_citation_traceability_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_citation_traceability_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_CITATION_TRACEABILITY.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(service: LawRagService, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        response = service.answer(row["question"], top_k=int(row["top_k"]))
        plan = response.get("composition", {}).get("answer_plan", {})
        sentences = [
            sentence
            for section in plan.get("sections", [])
            for sentence in section.get("sentences", [])
            if sentence.get("citations")
        ]
        fully_bound = []
        issue_attributed = []
        unbound_ids = []
        unattributed_ids = []
        for sentence in sentences:
            citations = {str(value) for value in sentence.get("citations", [])}
            bound = {str(value.get("citation")) for value in sentence.get("citation_bindings", [])}
            if citations.issubset(bound):
                fully_bound.append(sentence["sentence_id"])
            else:
                unbound_ids.append(sentence["sentence_id"])
            if str(sentence.get("issue_id") or "").strip():
                issue_attributed.append(sentence["sentence_id"])
            else:
                unattributed_ids.append(sentence["sentence_id"])

        count = len(sentences)
        binding_coverage = len(fully_bound) / count if count else 1.0
        issue_coverage = len(issue_attributed) / count if count else 1.0
        korean_issue_headings = all(
            f"### {index}. {issue_id}" not in str(response.get("answer") or "")
            for index, issue_id in enumerate(plan.get("issue_order", []), start=1)
        )
        passed = binding_coverage == 1.0 and issue_coverage == 1.0 and korean_issue_headings
        errors = []
        if binding_coverage < 1.0:
            errors.append("incomplete_citation_binding")
        if issue_coverage < 1.0:
            errors.append("missing_issue_attribution")
        if not korean_issue_headings:
            errors.append("untranslated_issue_heading")
        cases.append({
            "case_id": row["case_id"],
            "cited_sentence_count": count,
            "citation_binding_coverage": round(binding_coverage, 4),
            "issue_attribution_coverage": round(issue_coverage, 4),
            "korean_issue_headings": korean_issue_headings,
            "unbound_sentence_ids": unbound_ids,
            "unattributed_sentence_ids": unattributed_ids,
            "error_types": errors,
            "passed": passed,
        })

    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "mean_citation_binding_coverage": round(mean(case["citation_binding_coverage"] for case in cases), 4),
        "mean_issue_attribution_coverage": round(mean(case["issue_attribution_coverage"] for case in cases), 4),
        "korean_issue_heading_rate": round(mean(case["korean_issue_headings"] for case in cases), 4),
    }
    return {
        "evaluation_name": "business_legal_citation_traceability_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "provider": "deterministic/offline-template",
        "summary": summary,
        "cases": cases,
        "limitations": [
            "인용이 실제 근거 노드에 결속되고 쟁점 ID가 부여됐는지 구조적으로 평가한다.",
            "인용 조문의 법률적 충분성이나 외부 생성형 LLM의 답변 정확도를 측정하지 않는다.",
            "내부 설계 8문항에 한정된 재현 평가다.",
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
    return f"""# 기업 법무 답변 인용 추적성 평가

## 평가 목적

복수 쟁점 답변의 각 인용이 실제 검색 근거 노드에 결속되고, 인용 문장이 어느
법률 쟁점에 속하는지 추적 가능한지 평가한다. 내부 식별자 대신 한국어 쟁점명이
사용자 답변에 표시되는지도 함께 확인한다.

## 전후 결과

| 지표 | 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 평균 인용-근거 결속률 | {_pct(before['mean_citation_binding_coverage'])} | {_pct(now['mean_citation_binding_coverage'])} |
| 평균 쟁점 귀속률 | {_pct(before['mean_issue_attribution_coverage'])} | {_pct(now['mean_issue_attribution_coverage'])} |
| 한국어 쟁점 제목률 | {_pct(before['korean_issue_heading_rate'])} | {_pct(now['korean_issue_heading_rate'])} |

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python tools/evaluate_business_legal_citation_traceability.py
```

## 해석상 한계

- 인용과 쟁점의 구조적 추적성을 평가하며 해당 인용의 법률적 충분성을 자동 확정하지 않는다.
- 외부 생성형 LLM의 유창성·사실성·법률답변 정확도를 의미하지 않는다.
- 내부 설계 8문항의 오프라인 결정론적 평가이며 실제 사건 분포를 대표하지 않는다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate issue-to-citation traceability")
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
    print(f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; binding={summary['mean_citation_binding_coverage']:.4f}; issue={summary['mean_issue_attribution_coverage']:.4f}")
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
