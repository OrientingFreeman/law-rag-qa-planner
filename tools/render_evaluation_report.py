"""Render the reproducible Markdown retrieval evaluation report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CATEGORY_LABELS = {
    "direct_statute_retrieval": "직접 조문 검색",
    "lay_to_legal_mapping": "일상어→법률용어",
    "similar_provision_disambiguation": "유사 조문 구별",
    "multi_requirement": "복합 요건",
    "ambiguous_question": "모호 질문",
    "abstention": "범위 밖 유보",
    "temporal_revision": "시점·개정",
    "false_premise": "잘못된 전제",
}
DIFFICULTY_LABELS = {"easy": "쉬움", "medium": "보통", "hard": "어려움"}


def pct(value: Any) -> str:
    return "N/A" if value is None else f"{float(value) * 100:.2f}%"


def metric_row(label: str, metrics: dict[str, Any]) -> str:
    mrr = metrics["mean_reciprocal_rank"]
    mrr_text = "N/A" if mrr is None else f"{float(mrr):.4f}"
    return (
        f"| {label} | {metrics['total_cases']} | {pct(metrics['pass_rate'])} | "
        f"{pct(metrics['top1_accuracy'])} | {pct(metrics['hit_at_k'])} | "
        f"{mrr_text} | {pct(metrics['abstention_accuracy'])} |"
    )


def render(report: dict[str, Any], evaluated_on: str) -> str:
    summary = report["summary"]
    cases = report["cases"]
    successes = [row for row in cases if row["passed"] and row["top1_hit"]][:3]
    failures = [row for row in cases if not row["passed"]][:5]

    lines = [
        "# 공식 평가 보고서",
        "",
        f"> 평가일: {evaluated_on} · 평가 엔진: {report['version']} · 데이터셋: `evaluation/datasets/official_core_cases.json`",
        "",
        "## 1. 평가 범위와 해석 원칙",
        "",
        "이 보고서는 저장소의 공개 법령 corpus를 대상으로 한 **검색·유보 평가**다. `LAW_RAG_LLM_PROVIDER=deterministic` 모드에서 실행했으며 외부 생성형 LLM을 호출하지 않았다. 따라서 인용 정확도와 `expected_answer_points` 기반 생성 답변 완결성은 이번 결과에 포함하지 않으며, 검색 지표를 생성 품질로 표현하지 않는다.",
        "",
        "평가셋은 49개 문항, 8개 유형, 3개 난이도로 구성된다. 각 문항의 gold 법률 ID와 조문은 로컬 corpus 존재 검증을 통과했다.",
        "",
        "## 2. 전체 결과",
        "",
        "| 지표 | 결과 | 해석 |",
        "| --- | ---: | --- |",
        f"| 통과 문항 | {summary['passed_cases']}/{summary['total_cases']} ({pct(summary['pass_rate'])}) | gold 검색·유보·시점·인용 조건을 결합한 기존 pass 기준 |",
        f"| Top-1 Accuracy | {pct(summary['top1_accuracy'])} | gold 조문이 첫 번째 검색 결과인 비율 |",
        f"| Hit@5 | {pct(summary['hit_at_k'])} | 상위 5개 안에 gold 조문이 하나 이상 있는 비율 |",
        f"| Recall@5 | {pct(summary['mean_recall_at_k'])} | gold 조문 집합 중 상위 5개가 회수한 평균 비율 |",
        f"| MRR | {float(summary['mean_reciprocal_rank']):.4f} | 첫 gold 조문의 평균 역순위 |",
        f"| 답변 유보 정확도 | {pct(summary['abstention_accuracy'])} | 기대 유보와 실제 유보의 일치율 |",
        f"| 시행일 정확도 | {pct(summary['temporal_accuracy'])} | 시점 유형 결과에 만료·미시행 조문이 포함되지 않은 비율 |",
        "| 인용 정확도 | N/A | 이번 49개 공식 실행은 검색 전용이며 생성 답변을 평가하지 않음 |",
        f"| 평균 지연 | {float(summary['average_latency_ms']):.1f} ms | 로컬 환경의 문항당 평균 검색 시간 |",
        "",
        "시행일 정확도 100%는 과거 법령 버전의 내용 정답률을 의미하지 않는다. 현재 구현이 기준일 이후 시행 조문을 결과에 포함하지 않았는지만 측정한 제한적 지표다.",
        "",
        "## 3. 유형별 결과",
        "",
        "| 유형 | 문항 | Pass | Top-1 | Hit@5 | MRR | 유보 정확도 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, metrics in report["metrics_by_category"].items():
        lines.append(metric_row(CATEGORY_LABELS.get(key, key), metrics))
    lines += [
        "",
        "유사 조문 구별은 Hit@5 20.00%, Pass 0%로 가장 취약했다. 일상어→법률용어는 Hit@5 81.82%로 상대적으로 강했으나, 정답을 첫 순위에 놓는 비율은 54.55%였다. 복합 요건은 Hit@5 66.67%에 비해 Pass가 33.33%여서 검색 후 유보 판정과 순위 품질을 함께 개선할 필요가 있다.",
        "",
        "## 4. 난이도별 결과",
        "",
        "| 난이도 | 문항 | Pass | Top-1 | Hit@5 | MRR | 유보 정확도 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, metrics in report["metrics_by_difficulty"].items():
        lines.append(metric_row(DIFFICULTY_LABELS.get(key, key), metrics))
    lines += [
        "",
        "보통 난이도의 Top-1이 18.18%로 가장 낮았다. 현재 난이도 표본은 유형 분포가 동일하지 않으므로, 이를 난이도 자체의 인과효과로 해석하지 않고 취약 문항군을 찾는 진단값으로 사용한다.",
        "",
        "## 5. 오류 유형",
        "",
        "| 오류 유형 | 건수 | 판정 기준 |",
        "| --- | ---: | --- |",
    ]
    descriptions = {
        "retrieval_miss": "상위 K에 gold 근거가 없음",
        "wrong_top1": "gold가 상위 K에는 있으나 1위가 아님",
        "over_retrieval": "모든 gold를 찾았지만 gold 이외 후보도 반환한 진단 플래그",
        "under_retrieval": "여러 gold 중 일부만 회수",
        "incorrect_abstention": "기대 유보와 실제 유보가 불일치",
        "unsupported_citation": "생성 답변이 검색 근거 밖 인용을 사용",
        "incomplete_answer": "생성 답변이 기대 정답 포인트를 모두 포괄하지 못함",
        "temporal_mismatch": "질문 기준일에 유효하지 않은 근거가 포함됨",
    }
    for key, count in summary.get("error_type_counts", {}).items():
        lines.append(f"| `{key}` | {count} | {descriptions[key]} |")
    lines += [
        "",
        "`over_retrieval`은 legacy pass와 독립적인 품질 진단 플래그이므로 통과 문항에도 붙을 수 있다. 검색 전용 실행에서는 `unsupported_citation`과 `incomplete_answer`가 산출되지 않는 것이 정상이다. 이번 데이터의 gold가 대부분 단일 조문이므로 `under_retrieval`도 발생하지 않았다.",
        "",
        "## 6. 대표 성공 사례",
        "",
        "| case_id | 질문 | Top-1 | 관찰 |",
        "| --- | --- | --- | --- |",
    ]
    for row in successes:
        lines.append(f"| `{row['case_id']}` | {row['question']} | `{row['retrieved_articles'][0]}` | gold를 1위로 회수 |")
    lines += [
        "",
        "## 7. 대표 실패 사례와 원인",
        "",
        "| case_id | 기대 조문 | 실제 상위 후보 | 오류 | 원인 가설 |",
        "| --- | --- | --- | --- | --- |",
    ]
    hypotheses = {
        "pipa-third-party-provision": "수집·이용 표현이 강하게 작동해 제15조가 제17조보다 우선됨",
        "pipa-destruction": "파기 질문의 핵심어가 최소수집·민감정보 후보로 분산되고 저신뢰 유보 발생",
        "pipa-consent-method": "동의 관련 다수 조문 사이에서 ‘동의를 받는 방법’ 의도가 충분히 고정되지 않음",
        "pipa-child-consent": "아동·법정대리인 개념보다 일반 수집 동의 확장이 우선됨",
        "pipa-breach": "유출 통지·신고의 복합 의도가 일반 보호 의무 후보로 분산됨",
    }
    for row in failures:
        expected = ", ".join(row["expected_article_nos"]) or "유보"
        actual = ", ".join(row["retrieved_articles"][:2]) or "없음"
        errors = ", ".join(row["error_types"])
        lines.append(f"| `{row['case_id']}` | {expected} | {actual} | `{errors}` | {hypotheses.get(row['case_id'], '검색 어휘·온톨로지 제약과 유보 임계값을 문항별로 재검토해야 함')} |")
    lines += [
        "",
        "실패 원인은 결과에 근거한 진단 가설이며 원인 확정이 아니다. 이후 ablation 또는 랭킹 로그 비교로 검증해야 한다.",
        "",
        "## 8. 개선 전후 비교",
        "",
        "기존 8개 공식 문항 결과와 이번 49개 결과는 문항 구성과 난이도가 달라 직접적인 성능 전후 비교로 사용하지 않는다. 이번 결과를 확장 평가셋의 최초 기준선(baseline)으로 고정하고, 이후 동일한 49개 데이터와 동일한 corpus에서 검색기 변경 전후를 비교한다.",
        "",
        "우선 개선 대상은 다음과 같다.",
        "",
        "1. 유사 조문 구별을 위한 법적 행위·목적 기반 ontology constraint 강화",
        "2. 제3자 제공/수집·이용, 해고예고/서면통지 같은 hard negative 쌍 보강",
        "3. 유보 임계값을 검색 점수 하나가 아니라 의도 일치도·gold 후보 간 격차와 결합",
        "4. 시점 평가를 위해 과거 버전 corpus와 개정 전후 gold 문항 추가",
        "5. 생성 평가 문항을 별도 실행해 인용 정확도와 정답 포인트 완결성 측정",
        "",
        "## 9. 재현 방법",
        "",
        "```bash",
        "python tools/validate_evaluation_dataset.py",
        "",
        "LAW_RAG_LLM_PROVIDER=deterministic python -m law_rag.benchmark \\",
        "  --dataset evaluation/datasets/official_core_cases.json \\",
        "  --output evaluation/reports/official_49_baseline.json \\",
        "  --fail-under 0 \\",
        "  --no-log-failures --json",
        "",
        "python tools/render_evaluation_report.py \\",
        "  --input evaluation/reports/official_49_baseline.json \\",
        "  --output docs/EVALUATION_REPORT.md \\",
        f"  --evaluated-on {evaluated_on}",
        "```",
        "",
        "실제 외부 LLM 생성 평가를 수행할 때에는 provider·model·prompt version·temperature와 실행 시점을 별도로 기록하고 검색 평가 결과와 분리한다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluated-on", required=True)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(report, args.evaluated_on), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
