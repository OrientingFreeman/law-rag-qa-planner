from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = ROOT / "data" / "legal_knowledge_base.json"
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
ALLOWED_RELATIONS = {"exact_synonym", "contextual_mapping", "broader_term", "narrower_term", "related_not_synonym"}
ALLOWED_STATUSES = {"draft", "reviewed", "rejected"}
CONCEPT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ARTICLE_RE = re.compile(r"^제[0-9]+조(?:의[0-9]+)?$")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_knowledge_base(kb: dict[str, Any], corpus: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    concepts = kb.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        return ["concepts must be a non-empty list"]
    corpus_articles = {(str(r.get("law_id")), str(r.get("law_name")), str(r.get("article_no"))) for r in corpus}
    corpus_documents = {str(r.get("document_id")) for r in corpus if r.get("document_id")}
    seen_ids: set[str] = set()
    seen_terms: set[tuple[str, str]] = set()
    required = {"concept_id", "legal_term", "lay_terms", "relation_type", "scope_note", "law_id", "law_name", "article_refs", "effective_from", "effective_to", "source_document_ids", "annotation_status", "annotation_note"}
    for index, concept in enumerate(concepts):
        label = f"concepts[{index}]"
        if not isinstance(concept, dict):
            errors.append(f"{label}: must be an object")
            continue
        missing = sorted(required - concept.keys())
        if missing:
            errors.append(f"{label}: missing fields: {', '.join(missing)}")
            continue
        concept_id = concept["concept_id"]
        if not isinstance(concept_id, str) or not CONCEPT_ID_RE.fullmatch(concept_id):
            errors.append(f"{label}: invalid concept_id")
        elif concept_id in seen_ids:
            errors.append(f"{label}: duplicate concept_id {concept_id}")
        else:
            seen_ids.add(concept_id)
        term_key = (str(concept["law_id"]), str(concept["legal_term"]).strip())
        if term_key in seen_terms:
            errors.append(f"{label}: duplicate legal term within law: {term_key[1]}")
        seen_terms.add(term_key)
        if concept["relation_type"] not in ALLOWED_RELATIONS:
            errors.append(f"{label}: unsupported relation_type")
        if concept["annotation_status"] not in ALLOWED_STATUSES:
            errors.append(f"{label}: unsupported annotation_status")
        if not isinstance(concept["lay_terms"], list) or not concept["lay_terms"]:
            errors.append(f"{label}: lay_terms must be non-empty")
        elif len(concept["lay_terms"]) != len(set(concept["lay_terms"])):
            errors.append(f"{label}: duplicate lay_terms")
        try:
            start = date.fromisoformat(concept["effective_from"])
            end = date.fromisoformat(concept["effective_to"]) if concept["effective_to"] else None
            if end and end < start:
                errors.append(f"{label}: effective_to precedes effective_from")
        except (TypeError, ValueError):
            errors.append(f"{label}: invalid effective date")
        for article in concept["article_refs"]:
            if not isinstance(article, str) or not ARTICLE_RE.fullmatch(article):
                errors.append(f"{label}: invalid article ref {article!r}")
            elif (str(concept["law_id"]), str(concept["law_name"]), article) not in corpus_articles:
                errors.append(f"{label}: corpus article not found: {concept['law_name']} {article}")
        for document_id in concept["source_document_ids"]:
            if document_id not in corpus_documents:
                errors.append(f"{label}: source document not found: {document_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate legal terminology KB and corpus references")
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    kb, corpus = load_json(args.kb), load_json(args.corpus)
    errors = validate_knowledge_base(kb, corpus)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {len(kb['concepts'])} concepts; metadata and all corpus article/document references validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
