"""Validate the isolated precedent PoC and its links to the statute corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_PRECEDENT_FIELDS = {
    "precedent_id", "evidence_type", "court", "case_number", "decision_date",
    "case_name", "issues", "holding_summary", "reasoning_summary",
    "related_statutes", "source_url", "context_date", "legal_context_note",
}


def validate(precedent_path: Path, cases_path: Path, corpus_path: Path) -> list[str]:
    payload = json.loads(precedent_path.read_text(encoding="utf-8"))
    cases_payload = json.loads(cases_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    article_keys = {(str(row["law_id"]), str(row["article_no"])) for row in corpus}
    precedents = payload.get("precedents", [])
    errors: list[str] = []

    if not 1 <= len(precedents) <= 12:
        errors.append(f"precedent count must be 1..12, got {len(precedents)}")
    ids: set[str] = set()
    case_numbers: set[str] = set()
    for row in precedents:
        missing = REQUIRED_PRECEDENT_FIELDS.difference(row)
        if missing:
            errors.append(f"{row.get('precedent_id', '?')}: missing {sorted(missing)}")
        precedent_id = str(row.get("precedent_id", ""))
        if precedent_id in ids:
            errors.append(f"duplicate precedent_id: {precedent_id}")
        ids.add(precedent_id)
        case_number = str(row.get("case_number", ""))
        if case_number in case_numbers:
            errors.append(f"duplicate case_number: {case_number}")
        case_numbers.add(case_number)
        if row.get("evidence_type") != "precedent":
            errors.append(f"{precedent_id}: evidence_type must be precedent")
        if row.get("court") != "대법원":
            errors.append(f"{precedent_id}: only Supreme Court samples are allowed")
        if not str(row.get("source_url", "")).startswith("https://www.law.go.kr/"):
            errors.append(f"{precedent_id}: source_url must be official law.go.kr")
        for statute in row.get("related_statutes", []):
            key = (str(statute.get("law_id")), str(statute.get("article_no")))
            if key not in article_keys:
                errors.append(f"{precedent_id}: missing corpus statute {key[0]}:{key[1]}")

    evaluation_cases = cases_payload.get("cases", [])
    if not 2 <= len(evaluation_cases) <= 24:
        errors.append(f"evaluation case count must be 2..24, got {len(evaluation_cases)}")
    evaluation_ids: set[str] = set()
    for case in evaluation_cases:
        case_id = str(case.get("case_id", ""))
        if case_id in evaluation_ids:
            errors.append(f"duplicate evaluation case_id: {case_id}")
        evaluation_ids.add(case_id)
        expected_ids = set(map(str, case.get("expected_precedent_ids", [])))
        if not expected_ids or not expected_ids.issubset(ids):
            errors.append(f"{case_id}: unknown expected_precedent_ids {sorted(expected_ids - ids)}")
        expected_numbers = set(map(str, case.get("expected_case_numbers", [])))
        if not expected_numbers or not expected_numbers.issubset(case_numbers):
            errors.append(f"{case_id}: unknown expected_case_numbers {sorted(expected_numbers - case_numbers)}")
        law_id = str(case.get("expected_law_id", ""))
        for article_no in case.get("expected_article_nos", []):
            if (law_id, str(article_no)) not in article_keys:
                errors.append(f"{case_id}: missing corpus statute {law_id}:{article_no}")
        if not case.get("expected_answer_points"):
            errors.append(f"{case_id}: expected_answer_points must not be empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--precedents", type=Path, default=Path("data/precedent_poc.json"))
    parser.add_argument("--cases", type=Path, default=Path("evaluation/datasets/precedent_poc_cases.json"))
    parser.add_argument("--corpus", type=Path, default=Path("data/legal_corpus.json"))
    args = parser.parse_args()
    errors = validate(args.precedents, args.cases, args.corpus)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    payload = json.loads(args.precedents.read_text(encoding="utf-8"))
    cases_payload = json.loads(args.cases.read_text(encoding="utf-8"))
    print(
        f"OK: {len(payload['precedents'])} official precedents, "
        f"{len(cases_payload['cases'])} evaluation cases, and all statute links validated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
