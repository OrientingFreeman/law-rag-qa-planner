from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from law_rag.evaluation.runner import EvaluationRunner, load_dataset, write_report
from law_rag.service import LawRagService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "business_legal_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_DOMAINS = ROOT / "domains"
DEFAULT_BASELINE = ROOT / "evaluation" / "reports" / "business_legal_baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "reports" / "business_legal_latest.json"
DEFAULT_REPORT = ROOT / "docs" / "BUSINESS_LEGAL_RAG_EVALUATION.md"

ALLOWED_DOMAINS = {"electronic_finance", "digital_business", "intellectual_property"}
ALLOWED_CATEGORIES = {
    "direct_statute_retrieval",
    "lay_to_legal_mapping",
    "similar_provision_disambiguation",
    "multi_requirement",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_cases(rows: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    article_keys = {(str(row["law_id"]), str(row["article_no"])) for row in corpus}
    ids: set[str] = set()
    if len(rows) != 12:
        errors.append(f"dataset must contain 12 cases, got {len(rows)}")
    for index, row in enumerate(rows):
        case_id = str(row.get("case_id", f"row-{index}"))
        if case_id in ids:
            errors.append(f"{case_id}: duplicate case_id")
        ids.add(case_id)
        if not case_id.startswith("business-"):
            errors.append(f"{case_id}: case_id must start with business-")
        if row.get("domain") not in ALLOWED_DOMAINS:
            errors.append(f"{case_id}: unsupported domain {row.get('domain')}")
        if row.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"{case_id}: unsupported category {row.get('category')}")
        if row.get("difficulty") not in {"easy", "medium", "hard"}:
            errors.append(f"{case_id}: unsupported difficulty {row.get('difficulty')}")
        if row.get("expected_abstain"):
            errors.append(f"{case_id}: this focused dataset requires answerable cases")
        law_id = str(row.get("expected_law_id") or "")
        articles = list(row.get("expected_article_nos") or [])
        if not law_id or not articles:
            errors.append(f"{case_id}: gold law and articles are required")
        for article in articles:
            if (law_id, str(article)) not in article_keys:
                errors.append(f"{case_id}: missing corpus article {law_id}:{article}")
        if not row.get("expected_answer_points"):
            errors.append(f"{case_id}: expected_answer_points must not be empty")
        if not str(row.get("annotation_note") or "").strip():
            errors.append(f"{case_id}: annotation_note must not be empty")
    return errors


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def render_markdown(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    now = current["summary"]
    before = baseline["summary"]
    error_rows = "\n".join(
        f"| `{key}` | {value}건 |" for key, value in now.get("error_type_counts", {}).items()
    ) or "| 없음 | 0건 |"
    case_rows = []
    for row in current["cases"]:
        gold = ", ".join(f"{row['expected_law_id']}:{article}" for article in row["expected_article_nos"])
        errors = ", ".join(row["error_types"]) or "없음"
        case_rows.append(
            f"| `{row['case_id']}` | {'PASS' if row['passed'] else 'FAIL'} | "
            f"{'Y' if row['top1_hit'] else 'N'} | {'Y' if row['hit_at_k'] else 'N'} | {gold} | {errors} |"
        )
    return f"""# 기업 법무 질문 RAG 검색 평가

## 평가 목적

결제·전자금융, 개인정보, 기술·지식재산 질문 12건이 실제 하이브리드
검색 파이프라인에서 사전에 지정한 법률·조문을 회수하는지 평가한다.
법령용어–일상용어의 명시적 매핑을 확인하는 KB 폐쇄형 평가와 달리,
이 평가는 질의 계획, 도메인 확장, 검색·재정렬·유보 판단을 포함한다.

## 전후 결과

| 지표 | 규칙 보강 전 | 보강 후 |
|---|---:|---:|
| 통과 | {before['passed_cases']}/{before['total_cases']} | {now['passed_cases']}/{now['total_cases']} |
| Pass rate | {_pct(before['pass_rate'])} | {_pct(now['pass_rate'])} |
| Top-1 Accuracy | {_pct(before['top1_accuracy'])} | {_pct(now['top1_accuracy'])} |
| Hit@5 | {_pct(before['hit_at_k'])} | {_pct(now['hit_at_k'])} |
| Recall@5 | {_pct(before['mean_recall_at_k'])} | {_pct(now['mean_recall_at_k'])} |
| MRR | {before['mean_reciprocal_rank']:.4f} | {now['mean_reciprocal_rank']:.4f} |
| 유보 판단 정확도 | {_pct(before['abstention_accuracy'])} | {_pct(now['abstention_accuracy'])} |

초기 기준선에서는 처리위탁·유출 통지, 전자금융사고 책임, 업무상 프로그램
저작자 질문에서 검색 누락 또는 과도한 유보가 발생했다. 법령 정답을 검색
결과에 직접 고정하지 않고, 각 도메인의 동의어와 쟁점별 질의 확장 규칙을
보강했다. 또한 특허출원 전 공개 질문은 신규성 원칙인 제29조뿐 아니라
공지예외인 제30조도 함께 검토해야 한다는 법적 검수 결과를 반영해 gold
조문을 보정했다. 따라서 전후 차이는 검색 규칙 개선과 평가 정답 보정이
함께 반영된 결과다.

## 문항별 결과

| case_id | 통과 | Top-1 | Hit@5 | 정답 근거 | 진단 |
|---|---:|---:|---:|---|---|
{chr(10).join(case_rows)}

## 진단 항목

| 유형 | 현재 건수 |
|---|---:|
{error_rows}

`over_retrieval`은 정답 조문을 모두 찾았더라도 Top-K에 정답 외 후보가 함께
포함된 경우를 기록하는 진단 항목이다. 이 데이터셋은 실무 검토에서 관련
후보를 함께 살피는 검색 환경을 가정해 Top-K를 5로 유지했으므로, 이를
답변 오류나 평가 실패와 동일하게 해석하지 않는다.

## 재현 명령

```bash
python tools/evaluate_business_legal_cases.py
```

## 해석상 한계

- 12문항은 공개 법령을 사용한 내부 설계 평가이며 독립된 제3자 블라인드 평가가 아니다.
- Hit@5 100%는 정답 조문이 상위 5개 안에 포함됐다는 뜻이며, 생성형 답변의 법적 정확도를 뜻하지 않는다.
- 계약 협상, 소송 수행, 특허출원·권리관리 실무 능력을 직접 평가하지 않는다.
- 구체적인 출원 가능성, 책임 성립과 권리귀속은 추가 사실관계와 전문가 검토가 필요하다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate business legal RAG retrieval cases")
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
    report["evaluation_name"] = "business_legal_rag_retrieval_v1"
    report["dataset"] = str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset)
    report["limitations"] = [
        "설계된 12문항의 검색 평가이며 독립된 제3자 블라인드 벤치마크가 아니다.",
        "검색 지표는 생성형 답변의 법적 정확도를 측정하지 않는다.",
        "over_retrieval은 진단 항목이며 답변 실패와 동일하지 않다.",
    ]
    write_report(report, args.output)
    args.report.write_text(render_markdown(report, load_json(args.baseline)), encoding="utf-8")
    summary = report["summary"]
    print(
        f"OK: {summary['passed_cases']}/{summary['total_cases']} passed; "
        f"top1={summary['top1_accuracy']:.4f}; hit@5={summary['hit_at_k']:.4f}; "
        f"mrr={summary['mean_reciprocal_rank']:.4f}"
    )
    return 0 if float(summary["pass_rate"]) >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
