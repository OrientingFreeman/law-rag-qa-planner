from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data" / "amendment_case_candidates.json"
DEFAULT_KB = ROOT / "data" / "legal_knowledge_base.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_EVALUATION = ROOT / "evaluation" / "datasets" / "official_core_cases.json"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_candidates(
    payload: dict[str, Any],
    kb: dict[str, Any],
    corpus: list[dict[str, Any]],
    evaluation: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    candidates = payload.get("candidates") or []
    concept_index = {row.get("concept_id"): row for row in kb.get("concepts", [])}
    case_index = {row.get("case_id"): row for row in evaluation}
    corpus_articles = {(str(row.get("law_id")), str(row.get("article_no"))) for row in corpus}
    corpus_texts = {
        str(row.get("text") or "").strip()
        for row in corpus
        if str(row.get("text") or "").strip()
    }

    ids: set[str] = set()
    selected = 0
    for row in candidates:
        case_id = str(row.get("case_id") or "<missing-case-id>")
        if case_id in ids:
            errors.append(f"{case_id}: duplicate case_id")
        ids.add(case_id)
        if row.get("status") == "selected":
            selected += 1

        try:
            promulgated = date.fromisoformat(str(row.get("promulgated_at")))
            effective = date.fromisoformat(str(row.get("effective_from")))
            if effective < promulgated:
                errors.append(f"{case_id}: effective date precedes promulgation")
        except ValueError:
            errors.append(f"{case_id}: invalid promulgation/effective date")

        law_article = (str(row.get("law_id")), str(row.get("article_no")))
        if law_article not in corpus_articles:
            errors.append(f"{case_id}: changed article not found in current corpus")

        for concept_id in row.get("impacted_concept_ids") or []:
            concept = concept_index.get(concept_id)
            if not concept:
                errors.append(f"{case_id}: unknown concept_id {concept_id}")
            elif str(concept.get("law_id")) != law_article[0] or law_article[1] not in concept.get("article_refs", []):
                errors.append(f"{case_id}: concept {concept_id} is not linked to changed article")

        for evaluation_id in row.get("impacted_evaluation_case_ids") or []:
            evaluation_case = case_index.get(evaluation_id)
            if not evaluation_case:
                errors.append(f"{case_id}: unknown evaluation case {evaluation_id}")
            elif str(evaluation_case.get("expected_law_id")) != law_article[0] or law_article[1] not in (evaluation_case.get("expected_article_nos") or []):
                errors.append(f"{case_id}: evaluation case {evaluation_id} is not linked to changed article")

        sources = row.get("official_sources") or {}
        for source_name in ("before_text_url", "after_text_url", "amendment_document_url"):
            url = str(sources.get(source_name) or "")
            if not url.startswith("https://www.law.go.kr/"):
                errors.append(f"{case_id}: {source_name} is not an official law.go.kr URL")

        after_text = str((row.get("after") or {}).get("text") or "").strip()
        if after_text and after_text not in corpus_texts:
            errors.append(f"{case_id}: after text does not exactly match current corpus")
        if row.get("verification", {}).get("status") != "pass":
            errors.append(f"{case_id}: selected evidence has not passed verification")

    if selected != 1:
        errors.append(f"expected exactly one selected K4 case, found {selected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate official K4 amendment case candidates")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    args = parser.parse_args()
    payload = load_json(args.candidates)
    errors = validate_candidates(payload, load_json(args.kb), load_json(args.corpus), load_json(args.evaluation))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    selected = next(row for row in payload["candidates"] if row["status"] == "selected")
    print(
        "OK: "
        f"{len(payload['candidates'])} candidate; selected={selected['case_id']}; "
        f"concepts={len(selected['impacted_concept_ids'])}; "
        f"evaluation_cases={len(selected['impacted_evaluation_case_ids'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
