from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = ROOT / "data" / "legal_knowledge_base.json"
DEFAULT_CASES = ROOT / "evaluation" / "datasets" / "legal_kb_cases.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_JSON_REPORT = ROOT / "evaluation" / "reports" / "legal_kb_latest.json"
DEFAULT_MD_REPORT = ROOT / "docs" / "LEGAL_KB_QUALITY_REPORT.md"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


def _active_on(concept: dict[str, Any], reference_date: str) -> bool:
    target = date.fromisoformat(reference_date)
    start = date.fromisoformat(concept["effective_from"])
    end = date.fromisoformat(concept["effective_to"]) if concept.get("effective_to") else None
    return start <= target and (end is None or target <= end)


def predict(query: str, reference_date: str, kb: dict[str, Any]) -> dict[str, Any]:
    normalized_query = normalize(query)
    candidates = []
    for concept in kb["concepts"]:
        if not _active_on(concept, reference_date):
            continue
        terms = [(concept["legal_term"], "legal_term")] + [(term, "lay_term") for term in concept["lay_terms"]]
        matches = []
        for term, source in terms:
            normalized_term = normalize(term)
            if normalized_term and normalized_term in normalized_query:
                weight = 1.05 if source == "legal_term" else 1.0
                matches.append((round(len(normalized_term) * weight, 4), term, source))
        if matches:
            score, term, source = max(matches, key=lambda row: (row[0], len(row[1]), row[1]))
            candidates.append((score, concept, term, source))
    candidates.sort(key=lambda row: (-row[0], row[1]["concept_id"]))
    if not candidates:
        return {"abstained": True, "concept_id": None, "law_id": None, "article_refs": [], "matched_term": None, "match_source": None, "score": 0.0, "reason": "no_active_explicit_mapping"}
    top_score = candidates[0][0]
    tied = [row for row in candidates if row[0] == top_score]
    if len(tied) > 1:
        return {"abstained": True, "concept_id": None, "law_id": None, "article_refs": [], "matched_term": None, "match_source": None, "score": top_score, "reason": "ambiguous_top_mapping"}
    score, concept, term, source = candidates[0]
    return {"abstained": False, "concept_id": concept["concept_id"], "law_id": concept["law_id"], "article_refs": concept["article_refs"], "matched_term": term, "match_source": source, "score": score, "reason": "explicit_mapping_match"}


def validate_cases(cases: list[dict[str, Any]], kb: dict[str, Any], corpus: list[dict[str, Any]]) -> list[str]:
    errors = []
    concept_ids = {row["concept_id"] for row in kb["concepts"]}
    corpus_articles = {(row["law_id"], row["article_no"]) for row in corpus}
    seen = set()
    for case in cases:
        case_id = case.get("case_id", "<missing>")
        if case_id in seen:
            errors.append(f"{case_id}: duplicate case_id")
        seen.add(case_id)
        expected = set(case.get("expected_concept_ids") or [])
        missing = expected - concept_ids
        if missing:
            errors.append(f"{case_id}: unknown concepts {sorted(missing)}")
        if case.get("expected_abstain") and (expected or case.get("expected_law_id") or case.get("expected_article_refs")):
            errors.append(f"{case_id}: abstention case must not contain gold references")
        if not case.get("expected_abstain") and not expected:
            errors.append(f"{case_id}: answerable case needs expected_concept_ids")
        for article in case.get("expected_article_refs") or []:
            if (case.get("expected_law_id"), article) not in corpus_articles:
                errors.append(f"{case_id}: corpus article not found {case.get('expected_law_id')} {article}")
        try:
            date.fromisoformat(case["reference_date"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{case_id}: invalid reference_date")
    return errors


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def evaluate(cases: list[dict[str, Any]], kb: dict[str, Any], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    validation_errors = validate_cases(cases, kb, corpus)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))
    details = []
    answerable = top1_correct = abstention_correct = 0
    predicted_articles = gold_articles = article_true_positive = 0
    temporal_total = temporal_correct = overall_correct = 0
    groups: dict[str, dict[str, list[bool]]] = {"category": defaultdict(list), "difficulty": defaultdict(list)}
    for case in cases:
        prediction = predict(case["query"], case["reference_date"], kb)
        expected_abstain = case["expected_abstain"]
        abstain_ok = prediction["abstained"] == expected_abstain
        if expected_abstain:
            concept_ok = prediction["abstained"]
            article_ok = prediction["abstained"]
            abstention_correct += int(abstain_ok)
        else:
            answerable += 1
            concept_ok = not prediction["abstained"] and prediction["concept_id"] in case["expected_concept_ids"]
            top1_correct += int(concept_ok)
            predicted = set(prediction["article_refs"])
            gold = set(case["expected_article_refs"])
            article_true_positive += len(predicted & gold)
            predicted_articles += len(predicted)
            gold_articles += len(gold)
            article_ok = predicted == gold and prediction["law_id"] == case["expected_law_id"]
        exact = abstain_ok and concept_ok and article_ok
        overall_correct += int(exact)
        if case["category"] == "temporal":
            temporal_total += 1
            temporal_correct += int(exact)
        groups["category"][case["category"]].append(exact)
        groups["difficulty"][case["difficulty"]].append(exact)
        errors = []
        if not abstain_ok:
            errors.append("incorrect_abstention")
        if not expected_abstain and not concept_ok:
            errors.append("wrong_concept_top1")
        if not expected_abstain and not article_ok:
            errors.append("incorrect_article_link")
        details.append({
            "case_id": case["case_id"], "category": case["category"], "difficulty": case["difficulty"],
            "expected_abstain": expected_abstain, "expected_concept_ids": case["expected_concept_ids"],
            "expected_law_id": case["expected_law_id"], "expected_article_refs": case["expected_article_refs"],
            "prediction": prediction, "exact_match": exact, "errors": errors,
        })
    abstention_cases = sum(1 for case in cases if case["expected_abstain"])
    metrics = {
        "case_count": len(cases), "answerable_case_count": answerable, "abstention_case_count": abstention_cases,
        "overall_exact_match": _safe_ratio(overall_correct, len(cases)),
        "concept_top1_accuracy": _safe_ratio(top1_correct, answerable),
        "article_precision": _safe_ratio(article_true_positive, predicted_articles),
        "article_recall": _safe_ratio(article_true_positive, gold_articles),
        "abstention_accuracy": _safe_ratio(abstention_correct, abstention_cases),
        "temporal_accuracy": _safe_ratio(temporal_correct, temporal_total),
    }
    breakdown = {
        dimension: {key: {"cases": len(values), "exact_match": _safe_ratio(sum(values), len(values))} for key, values in sorted(rows.items())}
        for dimension, rows in groups.items()
    }
    return {
        "evaluation_name": "legal_kb_closed_set_v1", "evaluation_mode": "deterministic_explicit_vocabulary_lookup",
        "limitations": [
            "This is a closed-set terminology and reference-link integrity evaluation, not semantic retrieval or LLM generation evaluation.",
            "A correct match shows that an explicitly registered legal or lay term is linked to the expected concept and article.",
            "Temporal accuracy only tests whether mappings outside their recorded effective period are withheld.",
        ],
        "metrics": metrics, "breakdown": breakdown, "details": details,
    }


def render_markdown(report: dict[str, Any]) -> str:
    m = report["metrics"]
    pct = lambda value: "N/A" if value is None else f"{value * 100:.2f}%"
    lines = [
        "# 법령정보지식베이스 품질 평가 보고서", "",
        "## 평가 범위", "",
        "이 보고서는 법령용어–일상용어 매핑과 근거 조문 연결의 구조적 품질을 평가한다. "
        "명시적으로 등록된 어휘만 사용하는 폐쇄형 결정론 평가이며, RAG 의미검색이나 생성형 LLM 답변 성능을 측정하지 않는다.", "",
        f"- 평가 문항: {m['case_count']}개", f"- 답변 대상: {m['answerable_case_count']}개", f"- 유보 대상: {m['abstention_case_count']}개",
        "- 지식베이스 개념: 41개", "- 대상 법령: 개인정보 보호법·시행령, 전자금융거래법, 근로기준법, 민법", "",
        "## 전체 결과", "",
        "| 지표 | 결과 | 해석 |", "|---|---:|---|",
        f"| 전체 Exact Match | {pct(m['overall_exact_match'])} | 개념·법령·조문 또는 기대 유보가 모두 일치 |",
        f"| 개념 Top-1 Accuracy | {pct(m['concept_top1_accuracy'])} | 답변 대상에서 첫 개념 일치 |",
        f"| 조문 연결 Precision | {pct(m['article_precision'])} | 예측 조문 중 정답 조문 비율 |",
        f"| 조문 연결 Recall | {pct(m['article_recall'])} | 정답 조문 중 회수된 비율 |",
        f"| 유보 정확도 | {pct(m['abstention_accuracy'])} | 모호·범위 밖·미등록 표현의 유보 |",
        f"| 제한적 시점 정확도 | {pct(m['temporal_accuracy'])} | 기록된 유효기간 밖 매핑의 차단 |", "",
    ]
    for dimension, title in (("category", "유형별 결과"), ("difficulty", "난이도별 결과")):
        lines += [f"## {title}", "", "| 구분 | 문항 수 | Exact Match |", "|---|---:|---:|"]
        for key, row in report["breakdown"][dimension].items():
            lines.append(f"| `{key}` | {row['cases']} | {pct(row['exact_match'])} |")
        lines.append("")
    failures = [row for row in report["details"] if not row["exact_match"]]
    lines += ["## 실패 및 유보 사례", ""]
    if failures:
        lines += ["| case_id | 오류 유형 |", "|---|---|"] + [f"| `{row['case_id']}` | {', '.join(row['errors'])} |" for row in failures]
    else:
        lines.append("등록 어휘 기반의 이번 폐쇄형 평가에서는 실패가 없었다. 이는 자유로운 한국어 표현을 모두 처리한다는 뜻이 아니다. 미등록 표현인 `정보 과다 수집`, 포괄적인 `손해배상`, 범위 밖 조세 질문, 보유 버전 이전 시점 질문은 의도대로 유보됐다.")
    lines += [
        "", "## 재현 명령", "", "```bash", "python tools/evaluate_legal_knowledge_base.py", "python -m pytest tests/test_legal_kb_evaluation.py -q", "```", "",
        "## 한계와 다음 단계", "",
        "- 현재 평가는 명시적 문자열 포함 여부를 사용하므로 바꿔 말하기와 형태소 변형에 대한 일반화 성능은 측정하지 않는다.",
        "- 이 30문항 평가는 현행 기준선의 용어·조문 연결 결과다. 실제 개정 전후 비교와 시행일 경계 평가는 K4 보고서에서 별도로 수행한다.",
        "- 향후에는 독립 주석자가 작성한 비정형 표현, 다중 개념 질문, 구버전 법령 원문을 추가해 블라인드 평가해야 한다.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate legal terminology KB mappings")
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD_REPORT)
    args = parser.parse_args()
    report = evaluate(load_json(args.cases), load_json(args.kb), load_json(args.corpus))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    m = report["metrics"]
    print(f"OK: {m['case_count']} cases; exact={m['overall_exact_match']:.4f}; concept_top1={m['concept_top1_accuracy']:.4f}; abstention={m['abstention_accuracy']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
