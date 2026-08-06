from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "legal_kb_verification.json"
DEFAULT_REPORT = ROOT / "docs" / "LEGAL_KB_VERIFICATION.md"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def collect_metrics(root: Path = ROOT) -> dict[str, Any]:
    corpus = load_json(root / "data" / "legal_corpus.json")
    kb = load_json(root / "data" / "legal_knowledge_base.json")
    kb_cases = load_json(root / "evaluation" / "datasets" / "legal_kb_cases.json")
    official_cases = load_json(root / "evaluation" / "datasets" / "official_core_cases.json")
    temporal_cases = load_json(root / "evaluation" / "datasets" / "amendment_temporal_cases.json")
    k4 = load_json(root / "data" / "k4_amendment_impact_manifest.json")
    k5 = load_json(root / "data" / "k5_amendment_review.json")
    return {
        "corpus_documents": len(corpus),
        "knowledge_concepts": len(kb.get("concepts", [])),
        "kb_evaluation_cases": len(kb_cases),
        "official_rag_evaluation_cases": len(official_cases),
        "verified_amendment_cases": 1 if k4.get("status") == "pass" else 0,
        "substantive_amendment_changes": len(k4.get("substantive_changes") or []),
        "impacted_concepts": k4.get("comparison", {}).get("summary", {}).get("impacted_concepts", 0),
        "impacted_evaluation_cases": k4.get("comparison", {}).get("summary", {}).get("impacted_evaluation_cases", 0),
        "temporal_boundary_cases": len(temporal_cases),
        "temporal_boundary_passed": k4.get("temporal_evaluation", {}).get("passed", 0),
        "k5_required_checks": k5.get("check_summary", {}).get("required", 0),
        "k5_passed_checks": k5.get("check_summary", {}).get("passed", 0),
        "k5_decision": k5.get("decision"),
        "review_model": k5.get("review_model"),
    }


def expected_claims(metrics: dict[str, Any]) -> dict[str, list[str]]:
    corpus = f"{metrics['corpus_documents']:,}개"
    concepts = f"{metrics['knowledge_concepts']}개"
    kb_cases = f"{metrics['kb_evaluation_cases']}문항"
    temporal = f"{metrics['temporal_boundary_passed']}/{metrics['temporal_boundary_cases']}"
    reviews = f"{metrics['k5_passed_checks']}/{metrics['k5_required_checks']}"
    return {
        "README.md": [
            corpus,
            concepts,
            kb_cases,
            "실제 개정 1건",
            temporal,
            f"{metrics['k5_required_checks']}개 필수 항목",
            "통합 검증 역시 9개 단계",
        ],
        "docs/LEGAL_DATA_QUALITY_PROJECT_SUMMARY.md": [corpus, concepts, kb_cases, temporal, reviews, "통합 검증 9/9"],
    }


def verify_document_claims(metrics: dict[str, Any], root: Path = ROOT) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for relative_path, tokens in expected_claims(metrics).items():
        text = (root / relative_path).read_text(encoding="utf-8")
        for token in tokens:
            checks.append({
                "path": relative_path,
                "expected_token": token,
                "passed": token in text,
            })
    return checks


def _compact_output(output: str, *, line_limit: int = 8) -> str:
    sanitized = output.replace(str(ROOT), "<PROJECT_ROOT>")
    lines = [line.rstrip() for line in sanitized.splitlines() if line.strip()]
    return "\n".join(lines[-line_limit:])


def run_step(
    name: str,
    arguments: list[str],
    *,
    root: Path = ROOT,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    completed = runner(
        [sys.executable, *arguments],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    passed_match = re.search(r"(\d+) passed", output)
    return {
        "name": name,
        "command": "python " + " ".join(arguments),
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "pytest_passed": int(passed_match.group(1)) if passed_match else None,
        "output_tail": _compact_output(output),
    }


def build_result(steps: list[dict[str, Any]], metrics: dict[str, Any], claim_checks: list[dict[str, Any]]) -> dict[str, Any]:
    invariant_checks = [
        {"check": "k4_actual_case_passed", "passed": metrics["verified_amendment_cases"] == 1},
        {"check": "k4_substantive_change_detected", "passed": metrics["substantive_amendment_changes"] == 1},
        {"check": "k4_temporal_boundary_passed", "passed": metrics["temporal_boundary_passed"] == metrics["temporal_boundary_cases"] == 2},
        {"check": "k5_gate_passed", "passed": metrics["k5_decision"] == "pass"},
        {"check": "k5_required_checks_passed", "passed": metrics["k5_passed_checks"] == metrics["k5_required_checks"] == 9},
    ]
    failed_steps = [row["name"] for row in steps if row["status"] != "pass"]
    failed_invariants = [row["check"] for row in invariant_checks if not row["passed"]]
    failed_claims = [f"{row['path']}:{row['expected_token']}" for row in claim_checks if not row["passed"]]
    status = "pass" if not (failed_steps or failed_invariants or failed_claims) else "fail"
    full_regression = next((row for row in steps if row["name"] == "full_regression"), None)
    return {
        "schema_version": "1.0.0",
        "verification_name": "legal_kb_final_verification",
        "status": status,
        "metrics": metrics,
        "steps": steps,
        "invariant_checks": invariant_checks,
        "documentation_claim_checks": claim_checks,
        "summary": {
            "steps_total": len(steps),
            "steps_passed": sum(row["status"] == "pass" for row in steps),
            "full_regression_tests_passed": full_regression.get("pytest_passed") if full_regression else None,
            "failed_steps": failed_steps,
            "failed_invariants": failed_invariants,
            "failed_documentation_claims": failed_claims,
        },
        "limitations": [
            f"KB {metrics['kb_evaluation_cases']}문항 결과는 등록 어휘 기반 폐쇄형 결정론 평가이며 자유 질의 의미검색 성능이 아니다.",
            "실제 개정 평가는 개인정보 보호법 제15조제1항의 단일 사례에 한정된다.",
            "검수 기록은 단계 분리 자기검수이며 독립된 제3자 검수가 아니다.",
            "외부 생성형 LLM의 답변 정확도는 이 통합 검증에 포함하지 않는다."
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    m = result["metrics"]
    s = result["summary"]
    step_rows = "\n".join(
        f"| `{row['name']}` | {row['status'].upper()} | `{row['command']}` |"
        for row in result["steps"]
    )
    claim_passed = sum(row["passed"] for row in result["documentation_claim_checks"])
    claim_total = len(result["documentation_claim_checks"])
    limitation_rows = "\n".join(f"- {text}" for text in result["limitations"])
    return f"""# 법령 지식베이스 최종 재현 검증 보고서

## 1. 최종 결과

| 항목 | 결과 |
|---|---:|
| 전체 판정 | **{result['status'].upper()}** |
| 검증 단계 | {s['steps_passed']}/{s['steps_total']} |
| 전체 pytest | {s['full_regression_tests_passed']} passed |
| 문서 수치 일치 | {claim_passed}/{claim_total} |

## 2. 실제 데이터에서 다시 계산한 수치

| 지표 | 결과 |
|---|---:|
| 법령 조·항·호 문서 | {m['corpus_documents']:,}개 |
| 법령 지식개념 | {m['knowledge_concepts']}개 |
| KB 폐쇄형 평가 | {m['kb_evaluation_cases']}문항 |
| 기존 RAG 공식 평가 | {m['official_rag_evaluation_cases']}문항 |
| 공식 개정 사례 | {m['verified_amendment_cases']}건 |
| 실질 변경 | {m['substantive_amendment_changes']}건 |
| 영향 개념 / 평가 문항 | {m['impacted_concepts']} / {m['impacted_evaluation_cases']} |
| 시행일 경계 평가 | {m['temporal_boundary_passed']}/{m['temporal_boundary_cases']} |
| 개정 검수 | {m['k5_passed_checks']}/{m['k5_required_checks']} ({m['k5_decision'].upper()}) |

## 3. 지식베이스·개정 관리 통합 실행 결과

| 단계 | 판정 | 재현 명령 |
|---|---:|---|
{step_rows}

## 4. 공개 문서 수치 검증

README와 `LEGAL_DATA_QUALITY_PROJECT_SUMMARY.md`에 표시된 코퍼스 문서 수,
개념 수, 평가 문항 수, 개정 사례, 시행일 평가와 검수 통과 수치를 실제
JSON 데이터에서 계산한 값과 비교했다. 불일치가 생기면 통합 검증의 전체 판정은
FAIL이 된다.

## 5. 재현 명령

```bash
python tools/run_legal_kb_verification.py
```

## 6. 해석상 한계

{limitation_rows}

이 보고서는 서로 다른 평가 범위의 수치를 합산하거나 일반화하지 않는다.
각 결과는 위에 명시한 데이터셋과 사례 범위 안에서만 해석한다.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the final legal knowledge-base verification")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    commands = [
        ("k1_knowledge_validation", ["tools/validate_legal_knowledge_base.py"]),
        ("k2_baseline_change_analysis", ["tools/analyze_legal_kb_update.py", "--output", "/tmp/law-rag-legal-kb-update.json"]),
        ("k3_closed_set_evaluation", ["tools/evaluate_legal_knowledge_base.py"]),
        ("k4_candidate_validation", ["tools/validate_amendment_case_candidates.py"]),
        ("k4_actual_amendment", ["tools/run_k4_amendment_case.py"]),
        ("k5_review_gate", ["tools/review_k5_amendment_update.py"]),
        ("official_dataset_validation", ["tools/validate_evaluation_dataset.py"]),
        ("targeted_tests", ["-m", "pytest", "tests/test_legal_knowledge_base.py", "tests/test_legal_kb_update.py", "tests/test_legal_kb_evaluation.py", "tests/test_amendment_case_candidates.py", "tests/test_k4_amendment_case.py", "tests/test_k5_amendment_review.py", "tests/test_legal_kb_verification.py", "-q"]),
        ("full_regression", ["-m", "pytest", "-q"]),
    ]
    steps = [run_step(name, command) for name, command in commands]
    metrics = collect_metrics()
    claims = verify_document_claims(metrics)
    result = build_result(steps, metrics, claims)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result), encoding="utf-8")
    print(
        f"OK: status={result['status']}; steps={result['summary']['steps_passed']}/{result['summary']['steps_total']}; "
        f"full_regression={result['summary']['full_regression_tests_passed']}; claims={sum(row['passed'] for row in claims)}/{len(claims)}"
    )
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
