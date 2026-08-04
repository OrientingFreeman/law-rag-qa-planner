from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.analyze_legal_kb_update import build_manifest, load_json


DEFAULT_BEFORE = ROOT / "evaluation" / "fixtures" / "pipa_article15_before_2025.json"
DEFAULT_AFTER = ROOT / "evaluation" / "fixtures" / "pipa_article15_after_2025.json"
DEFAULT_CASES = ROOT / "evaluation" / "datasets" / "amendment_temporal_cases.json"
DEFAULT_KB = ROOT / "data" / "legal_knowledge_base.json"
DEFAULT_EVALUATION = ROOT / "evaluation" / "datasets" / "official_core_cases.json"
DEFAULT_CURRENT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_CANDIDATES = ROOT / "data" / "amendment_case_candidates.json"
DEFAULT_OUTPUT = ROOT / "data" / "k4_amendment_impact_manifest.json"
DEFAULT_REPORT = ROOT / "docs" / "AMENDMENT_IMPACT_REPORT.md"


def _active_on(row: dict[str, Any], as_of: date) -> bool:
    start = date.fromisoformat(str(row["effective_from"]))
    end_raw = row.get("effective_to")
    end = date.fromisoformat(str(end_raw)) if end_raw else None
    return start <= as_of and (end is None or as_of <= end)


def evaluate_temporal_cases(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    versioned = before + after
    results: list[dict[str, Any]] = []
    for case in cases:
        as_of = date.fromisoformat(case["as_of_date"])
        active = {
            row["document_id"]: row
            for row in versioned
            if _active_on(row, as_of)
        }
        actual_present = case["target_document_id"] in active
        results.append({
            "case_id": case["case_id"],
            "as_of_date": case["as_of_date"],
            "target_document_id": case["target_document_id"],
            "expected_present": case["expected_present"],
            "actual_present": actual_present,
            "passed": actual_present is case["expected_present"],
            "selected_version_ids": sorted({str(row["version_id"]) for row in active.values()}),
        })
    return results


def validate_fixture_provenance(
    after: list[dict[str, Any]],
    current_corpus: list[dict[str, Any]],
    selected_case: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    current = {row["document_id"]: row for row in current_corpus}
    for row in after:
        corpus_row = current.get(row["document_id"])
        if not corpus_row:
            errors.append(f"missing current corpus document: {row['document_id']}")
        elif corpus_row.get("text") != row.get("text"):
            errors.append(f"official fixture text mismatch: {row['document_id']}")
    target = selected_case["after"]["text"]
    target_id = "011357:제15조:①:제7호"
    if not any(row["document_id"] == target_id and row["text"] == target for row in after):
        errors.append("selected amendment text is absent from after fixture")
    return errors


def build_k4_result(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    kb: dict[str, Any],
    official_cases: list[dict[str, Any]],
    temporal_cases: list[dict[str, Any]],
    candidates: dict[str, Any],
    current_corpus: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    selected = next(row for row in candidates["candidates"] if row["status"] == "selected")
    comparison = build_manifest(
        before,
        after,
        kb,
        official_cases,
        generated_at=generated_at,
        mode="verified_official_amendment_case",
    )
    temporal_results = evaluate_temporal_cases(before, after, temporal_cases)
    provenance_errors = validate_fixture_provenance(after, current_corpus, selected)
    substantive = [
        row for row in comparison["changes"]
        if row["change_type"] in {"added", "removed", "content_changed"}
    ]
    temporal_passed = sum(row["passed"] for row in temporal_results)
    expected_added_id = "011357:제15조:①:제7호"
    detected_expected_addition = any(
        row["change_type"] == "added" and row["document_id"] == expected_added_id
        for row in substantive
    )
    status = "pass"
    if comparison["status"] != "changes_detected" or provenance_errors or temporal_passed != len(temporal_results) or not detected_expected_addition:
        status = "fail"
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "case_id": selected["case_id"],
        "status": status,
        "official_amendment": {
            "law_id": selected["law_id"],
            "law_name": selected["law_name"],
            "promulgation_number": selected["promulgation_number"],
            "promulgated_at": selected["promulgated_at"],
            "effective_from": selected["effective_from"],
            "provision_ref": selected["provision_ref"],
            "official_sources": selected["official_sources"],
        },
        "comparison": comparison,
        "substantive_changes": substantive,
        "detected_expected_addition": detected_expected_addition,
        "temporal_evaluation": {
            "total": len(temporal_results),
            "passed": temporal_passed,
            "accuracy": temporal_passed / len(temporal_results) if temporal_results else 0.0,
            "results": temporal_results,
        },
        "fixture_provenance_errors": provenance_errors,
        "scope_note": "제15조제1항의 개정 전후만 분리한 검증 fixture이며 운영 검색 코퍼스에는 과거 버전을 혼합하지 않는다.",
    }


def render_report(result: dict[str, Any]) -> str:
    comparison = result["comparison"]
    temporal = result["temporal_evaluation"]
    amendment = result["official_amendment"]
    impacted_concepts = ", ".join(f"`{row['concept_id']}`" for row in comparison["impacted_concepts"])
    impacted_cases = ", ".join(f"`{row['case_id']}`" for row in comparison["impacted_evaluation_cases"])
    temporal_rows = "\n".join(
        f"| `{row['case_id']}` | {row['as_of_date']} | {str(row['expected_present']).lower()} | {str(row['actual_present']).lower()} | {'PASS' if row['passed'] else 'FAIL'} |"
        for row in temporal["results"]
    )
    sources = amendment["official_sources"]
    return f"""# 실제 법령 개정 영향 분석 보고서

## 1. 결론

개인정보 보호법 제15조제1항제7호 신설 사례를 개정 전후 공식 본문
fixture로 비교했다. 예상한 신설 조문을 탐지하고 기존 법령지식 항목과
평가 문항까지 추적했으며, 시행일 경계 평가 {temporal['passed']}/{temporal['total']}건이 통과했다.

| 항목 | 결과 |
|---|---|
| 전체 판정 | **{result['status'].upper()}** |
| 개정 법령 | {amendment['law_name']} ({amendment['promulgation_number']}) |
| 공포일 / 시행일 | {amendment['promulgated_at']} / {amendment['effective_from']} |
| 변경 조문 | {amendment['provision_ref']} |
| 비교 문서 | 개정 전 {comparison['summary']['baseline_documents']}개 / 개정 후 {comparison['summary']['candidate_documents']}개 |
| 탐지 변경 | {comparison['summary']['changed_documents']}개(공통 문서의 버전 메타데이터 변경 포함) |
| 실질 변경 | {len(result['substantive_changes'])}개 |
| 영향 지식 항목 | {impacted_concepts} |
| 영향 평가 문항 | {impacted_cases} |
| 시점 평가 | {temporal['passed']}/{temporal['total']} ({temporal['accuracy']:.0%}) |

## 2. 탐지된 실질 변경

`011357:제15조:①:제7호`가 `added`로 탐지됐다.

> 7. 공중위생 등 공공의 안전과 안녕을 위하여 긴급히 필요한 경우

나머지 공통 문서의 변경은 본문 변경이 아니라 시행일, 현행 여부,
버전 식별자와 공식 출처가 개정판으로 전환된 결과다. 이를 실질 조문
변경과 분리해 집계했다.

## 3. 영향 추적 결과

- 지식 항목: {impacted_concepts}
- 공식 평가 문항: {impacted_cases}
- 필요한 조치: 개인정보 수집·이용 근거 목록과 기준시점에 따른 정답
  포인트를 재검수한다.

## 4. 시행일 경계 평가

| case_id | 기준일 | 기대 존재 | 실제 존재 | 판정 |
|---|---:|---:|---:|---:|
{temporal_rows}

2025-10-01에는 신설 제7호를 제외하고, 시행일인 2025-10-02부터 이를
포함했다. 이는 단순히 시행일 메타데이터가 존재하는지를 보는 검사가
아니라, 개정 조문의 실제 존재 여부를 기준일 전후로 확인한 결과다.

## 5. 공식 출처

- [개정 전 본문]({sources['before_text_url']})
- [개정 후 본문]({sources['after_text_url']})
- [제정·개정문]({sources['amendment_document_url']})

## 6. 재현 명령

```bash
python tools/run_k4_amendment_case.py
python -m pytest tests/test_k4_amendment_case.py -q
```

## 7. 범위와 한계

- 제15조제1항만 포함한 집중 검증 fixture이며 해당 법률 전체의 버전
  코퍼스가 아니다.
- 운영 검색 코퍼스에는 개정 전 문서를 넣지 않아 현행 검색 순위에
  영향을 주지 않는다.
- 자동 비교 결과는 영향 후보를 제시한다. 법적 의미와 정답 수정의
  최종 승인은 공식 원문을 대조한 사람이 수행한다.
- 시점 평가 100%는 이 사례의 두 경계 문항에 한정되며 일반적인 과거
  법령 질의 성능을 뜻하지 않는다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the verified K4 official amendment case")
    parser.add_argument("--before", type=Path, default=DEFAULT_BEFORE)
    parser.add_argument("--after", type=Path, default=DEFAULT_AFTER)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--generated-at", default="2026-08-04T00:00:00Z")
    args = parser.parse_args()
    result = build_k4_result(
        load_json(args.before),
        load_json(args.after),
        load_json(DEFAULT_KB),
        load_json(DEFAULT_EVALUATION),
        load_json(args.cases),
        load_json(DEFAULT_CANDIDATES),
        load_json(DEFAULT_CURRENT_CORPUS),
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result), encoding="utf-8")
    print(
        f"OK: status={result['status']}; substantive_changes={len(result['substantive_changes'])}; "
        f"impacted_concepts={result['comparison']['summary']['impacted_concepts']}; "
        f"impacted_cases={result['comparison']['summary']['impacted_evaluation_cases']}; "
        f"temporal={result['temporal_evaluation']['passed']}/{result['temporal_evaluation']['total']}"
    )
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
