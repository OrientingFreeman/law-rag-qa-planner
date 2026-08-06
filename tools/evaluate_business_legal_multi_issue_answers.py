from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "business_legal_multi_issue_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_DOMAINS = ROOT / "domains"
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_multi_issue_answer_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_multi_issue_answer_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_MULTI_ISSUE_ANSWER_EVALUATION.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _law_names(corpus: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row["law_id"]): str(row["law_name"]) for row in corpus}


def _contains_citation(text: str, law_name: str, article_no: str) -> bool:
    normalized = " ".join(text.replace("\n", " ").split())
    return f"{law_name} {article_no}" in normalized


def evaluate(service: LawRagService, rows: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    law_names = _law_names(corpus)
    cases = []
    for row in rows:
        started = perf_counter()
        response = service.answer(row["question"], top_k=int(row["top_k"]))
        latency_ms = (perf_counter() - started) * 1000
        expected = list(row["expected_citations"])
        expected_issue_ids = list(dict.fromkeys(str(item["issue_id"]) for item in expected))
        detected_issue_ids = [str(value) for value in response.get("evidence_graph", {}).get("issues", [])]
        matched_issues = [issue_id for issue_id in expected_issue_ids if issue_id in detected_issue_ids]

        plan_citations = response.get("composition", {}).get("answer_plan", {}).get("allowed_citations", [])
        plan_text = "\n".join(str(value) for value in plan_citations)
        answer_text = str(response.get("answer") or "")
        plan_matches = []
        answer_matches = []
        for item in expected:
            law_id = str(item["law_id"])
            article_no = str(item["article_no"])
            law_name = law_names[law_id]
            label = f"{law_id}:{article_no}"
            if _contains_citation(plan_text, law_name, article_no):
                plan_matches.append(label)
            if _contains_citation(answer_text, law_name, article_no):
                answer_matches.append(label)

        issue_recall = len(matched_issues) / len(expected_issue_ids)
        plan_recall = len(plan_matches) / len(expected)
        answer_recall = len(answer_matches) / len(expected)
        citation_valid = bool(response.get("citation_validation", {}).get("valid"))
        grounding_coverage = float(response.get("grounding_validation", {}).get("coverage", 0.0))
        completed = response.get("generation_status") == "completed"
        passed = (
            issue_recall == 1.0
            and plan_recall == 1.0
            and answer_recall == 1.0
            and citation_valid
            and grounding_coverage >= 0.80
            and completed
        )
        errors = []
        if issue_recall < 1.0:
            errors.append("incomplete_issue_detection")
        if plan_recall < 1.0:
            errors.append("incomplete_answer_plan")
        if answer_recall < 1.0:
            errors.append("incomplete_answer_citation")
        if not citation_valid:
            errors.append("unsupported_citation")
        if grounding_coverage < 0.80:
            errors.append("low_grounding_coverage")
        if not completed:
            errors.append("generation_not_completed")
        cases.append({
            "case_id": row["case_id"],
            "expected_issue_ids": expected_issue_ids,
            "detected_issue_ids": detected_issue_ids,
            "matched_issue_ids": matched_issues,
            "issue_detection_recall": round(issue_recall, 4),
            "answer_plan_citation_recall": round(plan_recall, 4),
            "final_answer_citation_recall": round(answer_recall, 4),
            "citation_valid": citation_valid,
            "grounding_coverage": round(grounding_coverage, 4),
            "generation_status": response.get("generation_status"),
            "error_types": errors,
            "passed": passed,
            "latency_ms": round(latency_ms, 3),
        })

    summary = {
        "total_cases": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "pass_rate": round(mean(case["passed"] for case in cases), 4),
        "mean_issue_detection_recall": round(mean(case["issue_detection_recall"] for case in cases), 4),
        "mean_answer_plan_citation_recall": round(mean(case["answer_plan_citation_recall"] for case in cases), 4),
        "mean_final_answer_citation_recall": round(mean(case["final_answer_citation_recall"] for case in cases), 4),
        "citation_validity_rate": round(mean(case["citation_valid"] for case in cases), 4),
        "mean_grounding_coverage": round(mean(case["grounding_coverage"] for case in cases), 4),
        "completed_generation_rate": round(mean(case["generation_status"] == "completed" for case in cases), 4),
        "average_latency_ms": round(mean(case["latency_ms"] for case in cases), 3),
    }
    return {
        "evaluation_name": "business_legal_multi_issue_answer_v1",
        "dataset": str(DEFAULT_DATASET.relative_to(ROOT)),
        "provider": "deterministic/offline-template",
        "summary": summary,
        "cases": cases,
        "limitations": [
            "오프라인 결정론적 제공자로 답변 구조·인용·grounding 파이프라인을 평가한다.",
            "외부 생성형 LLM의 자연어 법률답변 정확도를 측정하지 않는다.",
            "내부 설계 8문항이며 독립된 제3자 블라인드 평가가 아니다.",
        ],
    }


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    now = current["summary"]
    before = baseline["summary"]
    failures = [case for case in current["cases"] if not case["passed"]]
    failure_rows = "\n".join(
        f"| `{case['case_id']}` | {', '.join(case['error_types']) or '없음'} |"
        for case in failures
    ) or "| 없음 | 없음 |"
    return f"""# 기업 법무 복수 쟁점 답변·인용 평가

## 평가 목적

V4에서 검색한 복수 쟁점 근거가 답변 단계에서도 독립 쟁점으로 식별되고,
답변 계획과 최종 답변에 필요한 조문이 모두 인용되는지 평가한다. 외부 LLM을
호출하지 않고 저장소의 결정론적 오프라인 제공자를 사용해 재현 가능성을 확보한다.

## 전후 결과

| 지표 | 답변 쟁점 보강 전 | 보강 후 |
|---|---:|---:|
| 문항 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| 평균 쟁점 식별 Recall | {_pct(before['mean_issue_detection_recall'])} | {_pct(now['mean_issue_detection_recall'])} |
| 답변 계획 인용 Recall | {_pct(before['mean_answer_plan_citation_recall'])} | {_pct(now['mean_answer_plan_citation_recall'])} |
| 최종 답변 인용 Recall | {_pct(before['mean_final_answer_citation_recall'])} | {_pct(now['mean_final_answer_citation_recall'])} |
| 인용 유효성 | {_pct(before['citation_validity_rate'])} | {_pct(now['citation_validity_rate'])} |
| 평균 grounding coverage | {_pct(before['mean_grounding_coverage'])} | {_pct(now['mean_grounding_coverage'])} |

## 현재 실패 문항

| case_id | 진단 |
|---|---|
{failure_rows}

## 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python tools/evaluate_business_legal_multi_issue_answers.py
```

## 해석상 한계

- 이 평가는 저장소의 오프라인 결정론적 제공자가 생성한 구조화 답변을 대상으로 한다.
- 외부 생성형 LLM의 유창성, 사실성 또는 실제 법률답변 정확도를 의미하지 않는다.
- 8개 내부 설계 문항의 쟁점·인용 완전성을 측정하며 실제 사건 분포를 대표하지 않는다.
- 구체적인 법률 판단에는 사실관계, 최신 법령, 판례·행정해석과 전문가 검토가 추가로 필요하다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate multi-issue business legal answers")
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
    service = LawRagService(
        data_path=args.corpus,
        domains_path=args.domains,
        llm_provider=DeterministicProvider(),
    )
    report = evaluate(service, rows, corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.baseline.exists():
        args.report.write_text(render_markdown(report, load_json(args.baseline)), encoding="utf-8")
    summary = report["summary"]
    print(
        f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; "
        f"issue_recall={summary['mean_issue_detection_recall']:.4f}; "
        f"answer_citation_recall={summary['mean_final_answer_citation_recall']:.4f}"
    )
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
