from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "k5_amendment_review_input.json"
DEFAULT_MANIFEST = ROOT / "data" / "k4_amendment_impact_manifest.json"
DEFAULT_OUTPUT = ROOT / "data" / "k5_amendment_review.json"
DEFAULT_REPORT = ROOT / "docs" / "AMENDMENT_REVIEW_REPORT.md"

REQUIRED_STAGES = ["collection", "annotation", "legal_review", "release_gate"]
REQUIRED_CHECKS = {
    "official_sources",
    "before_after_text",
    "effective_date",
    "change_classification",
    "knowledge_impact",
    "evaluation_impact",
    "temporal_boundary",
    "targeted_tests",
    "full_regression",
}
CRITICAL_CHECKS = {"official_sources", "before_after_text", "effective_date"}
VALID_CHECK_STATUSES = {"pass", "revise", "reject", "pending"}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_stage_order(stages: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    names = [str(row.get("stage")) for row in stages]
    if names != REQUIRED_STAGES:
        errors.append("review stages must appear in collection→annotation→legal_review→release_gate order")
        return errors
    if [row.get("sequence") for row in stages] != [1, 2, 3, 4]:
        errors.append("review stage sequence must be 1→2→3→4")
    try:
        for row in stages:
            date.fromisoformat(str(row["completed_on"]))
    except (KeyError, ValueError):
        errors.append("invalid or missing review stage date")
    for row in stages:
        if not row.get("actor_role") or not row.get("actor_label"):
            errors.append(f"{row.get('stage', '<missing-stage>')}: missing actor role or label")
    return errors


def evaluate_review(review: dict[str, Any], manifest: dict[str, Any], actual_hash: str) -> dict[str, Any]:
    reject_reasons: list[str] = []
    revise_reasons: list[str] = []
    evidence_errors: list[str] = []

    if review.get("input_manifest_sha256") != actual_hash:
        reject_reasons.append("input_manifest_hash_mismatch")
    if review.get("case_id") != manifest.get("case_id"):
        reject_reasons.append("case_id_mismatch")
    if manifest.get("status") != "pass":
        reject_reasons.append("k4_manifest_not_passed")
    if manifest.get("fixture_provenance_errors"):
        reject_reasons.append("fixture_provenance_error")
    if manifest.get("comparison", {}).get("temporal_errors"):
        reject_reasons.append("temporal_consistency_error")
    if not manifest.get("detected_expected_addition"):
        reject_reasons.append("expected_substantive_change_not_detected")

    sources = manifest.get("official_amendment", {}).get("official_sources", {})
    if set(sources) != {"before_text_url", "after_text_url", "amendment_document_url"}:
        reject_reasons.append("official_source_set_incomplete")
    elif any(not str(url).startswith("https://www.law.go.kr/") for url in sources.values()):
        reject_reasons.append("non_official_source")

    stage_errors = _validate_stage_order(review.get("stages") or [])
    revise_reasons.extend(stage_errors)

    checklist = review.get("checklist") or []
    indexed: dict[str, dict[str, Any]] = {}
    for row in checklist:
        check_id = str(row.get("check_id") or "")
        if not check_id or check_id in indexed:
            evidence_errors.append(f"duplicate or missing check_id: {check_id or '<empty>'}")
            continue
        indexed[check_id] = row
        status = row.get("status")
        if status not in VALID_CHECK_STATUSES:
            evidence_errors.append(f"{check_id}: invalid status {status}")
        if not str(row.get("evidence") or "").strip():
            evidence_errors.append(f"{check_id}: missing evidence")

    missing = sorted(REQUIRED_CHECKS - set(indexed))
    if missing:
        revise_reasons.append("missing_checks:" + ",".join(missing))
    for check_id, row in indexed.items():
        status = row.get("status")
        if status == "reject" and check_id in CRITICAL_CHECKS:
            reject_reasons.append(f"critical_check_rejected:{check_id}")
        elif status in {"reject", "revise", "pending"}:
            revise_reasons.append(f"check_not_passed:{check_id}:{status}")
    revise_reasons.extend(evidence_errors)

    decision = "reject" if reject_reasons else ("revise" if revise_reasons else "pass")
    requested = review.get("requested_decision")
    decision_matches_request = requested == decision
    if requested == "pass" and decision != "pass":
        evidence_errors.append("requested pass cannot override gate decision")

    return {
        "schema_version": "1.0.0",
        "review_id": review.get("review_id"),
        "case_id": manifest.get("case_id"),
        "input_manifest_sha256": actual_hash,
        "decision": decision,
        "requested_decision": requested,
        "decision_matches_request": decision_matches_request,
        "baseline_promotion_allowed": decision == "pass",
        "review_model": review.get("review_model"),
        "review_limitation": review.get("review_limitation"),
        "stage_count": len(review.get("stages") or []),
        "check_summary": {
            "required": len(REQUIRED_CHECKS),
            "passed": sum(1 for key in REQUIRED_CHECKS if indexed.get(key, {}).get("status") == "pass"),
            "revise": sum(1 for key in REQUIRED_CHECKS if indexed.get(key, {}).get("status") in {"revise", "pending"}),
            "rejected": sum(1 for key in REQUIRED_CHECKS if indexed.get(key, {}).get("status") == "reject"),
        },
        "reject_reasons": sorted(set(reject_reasons)),
        "revise_reasons": sorted(set(revise_reasons)),
        "evidence_errors": sorted(set(evidence_errors)),
        "review_note": review.get("review_note"),
        "release_actions": [
            "preserve_historical_fixture_separately",
            "retain_current_operational_corpus",
            "record_review_audit",
            "rerun_regression_before_future_baseline_change",
        ] if decision == "pass" else ["do_not_promote_baseline", "resolve_review_findings", "rerun_k5_gate"],
    }


def render_report(result: dict[str, Any], review: dict[str, Any]) -> str:
    checks = result["check_summary"]
    stages = "\n".join(
        f"| {row['sequence']} | {row['stage']} | {row['actor_role']} | `{row['actor_label']}` | {row['completed_on']} |"
        for row in review["stages"]
    )
    checklist = "\n".join(
        f"| `{row['check_id']}` | {row['status'].upper()} | {row['evidence']} |"
        for row in review["checklist"]
    )
    return f"""# 법령 개정 검수·승인 보고서

## 1. 최종 판정

| 항목 | 결과 |
|---|---|
| 사례 | `{result['case_id']}` |
| 게이트 판정 | **{result['decision'].upper()}** |
| 기준선 반영 허용 | {str(result['baseline_promotion_allowed']).lower()} |
| 필수 검수 통과 | {checks['passed']}/{checks['required']} |
| 검수 방식 | `{result['review_model']}` |

K4 결과, 공식 출처, 시행일, 지식 항목·평가 문항 영향과 회귀검증 증거를
확인한 결과 게이트가 PASS를 산출했다. 이 사례에서 운영 코퍼스는 이미
현행 제7호를 포함하므로 파일을 다시 교체하지 않는다. 승인 대상은 K4
분석 결과와 과거 버전 fixture의 감사 기록이다.

## 2. 역할별 단계 기록

| 순서 | 단계 | 역할 | 기록 주체 | 완료일 |
|---:|---|---|---|---|
{stages}

`project_author_second_pass`는 작성과 검수를 시간상 분리한 자기검수 단계다.
독립된 제3자 검수가 아니라는 한계를 숨기지 않는다.

## 3. 검수 체크리스트

| 검사 | 판정 | 증거 |
|---|---|---|
{checklist}

## 4. 자동 게이트 규칙

- 공식 출처 누락·비공식 출처·manifest 해시 불일치·시점 모순은 `reject`
- 영향 항목 미검수·회귀검증 미완료·단계 기록 오류는 `revise`
- 모든 필수 검사가 통과해야만 `pass`
- 입력의 희망 판정은 자동 게이트 결과를 덮어쓸 수 없음

## 5. 재현 명령

```bash
python tools/review_k5_amendment_update.py
python -m pytest tests/test_k5_amendment_review.py -q
python -m pytest -q
```

## 6. 한계

{result['review_limitation']}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the K5 amendment review and release gate")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    review = load_json(args.input)
    manifest = load_json(args.manifest)
    result = evaluate_review(review, manifest, file_sha256(args.manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result, review), encoding="utf-8")
    print(
        f"OK: decision={result['decision']}; checks={result['check_summary']['passed']}/{result['check_summary']['required']}; "
        f"baseline_promotion_allowed={result['baseline_promotion_allowed']}"
    )
    return 0 if result["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
