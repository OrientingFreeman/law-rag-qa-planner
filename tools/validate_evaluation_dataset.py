"""Validate evaluation metadata and expected articles against the local corpus."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REQUIRED_CATEGORIES = {
    "direct_statute_retrieval",
    "lay_to_legal_mapping",
    "similar_provision_disambiguation",
    "multi_requirement",
    "ambiguous_question",
    "abstention",
    "temporal_revision",
    "false_premise",
    "safety_false_premise",
    "safety_temporal_uncertainty",
    "safety_out_of_domain",
    "safety_scope_boundary",
    "safety_answerable_control",
}
DIFFICULTIES = {"easy", "medium", "hard"}


def validate(dataset_path: Path, corpus_path: Path) -> list[str]:
    rows = json.loads(dataset_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    article_keys = {(str(row["law_id"]), str(row["article_no"])) for row in corpus}
    errors: list[str] = []
    ids: set[str] = set()
    categories: Counter[str] = Counter()

    if not 40 <= len(rows) <= 64:
        errors.append(f"dataset size must be 40..64, got {len(rows)}")
    for index, row in enumerate(rows):
        prefix = f"row {index}"
        for field in (
            "case_id", "question", "category", "difficulty", "expected_law_id",
            "expected_article_nos", "expected_answer_points",
            "expected_abstain", "annotation_note",
        ):
            if field not in row:
                errors.append(f"{prefix}: missing {field}")
        case_id = str(row.get("case_id", ""))
        if case_id in ids:
            errors.append(f"{prefix}: duplicate case_id {case_id}")
        ids.add(case_id)
        category = str(row.get("category", ""))
        categories[category] += 1
        if category not in REQUIRED_CATEGORIES:
            errors.append(f"{case_id}: unsupported category {category}")
        if row.get("difficulty") not in DIFFICULTIES:
            errors.append(f"{case_id}: unsupported difficulty {row.get('difficulty')}")
        if not row.get("expected_answer_points"):
            errors.append(f"{case_id}: expected_answer_points must not be empty")
        if not str(row.get("annotation_note", "")).strip():
            errors.append(f"{case_id}: annotation_note must not be empty")
        law_id = row.get("expected_law_id")
        articles = row.get("expected_article_nos", [])
        if bool(law_id) != bool(articles):
            errors.append(f"{case_id}: law_id and article numbers must be set together")
        for article in articles:
            if (str(law_id), str(article)) not in article_keys:
                errors.append(f"{case_id}: missing corpus article {law_id}:{article}")
        if row.get("expected_abstain") and (law_id or articles):
            errors.append(f"{case_id}: abstention case must not declare a gold article")
        outcome = row.get("expected_outcome")
        if outcome not in {None, "answer", "abstain", "request_more_facts"}:
            errors.append(f"{case_id}: unsupported expected_outcome {outcome}")
        if outcome == "request_more_facts" and not row.get("required_facts"):
            errors.append(f"{case_id}: request_more_facts requires required_facts")
    missing_categories = REQUIRED_CATEGORIES.difference(categories)
    if missing_categories:
        errors.append(f"missing categories: {sorted(missing_categories)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/datasets/official_core_cases.json"))
    parser.add_argument("--corpus", type=Path, default=Path("data/legal_corpus.json"))
    args = parser.parse_args()
    errors = validate(args.dataset, args.corpus)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    rows = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(f"OK: {len(rows)} cases; metadata and corpus article references validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
