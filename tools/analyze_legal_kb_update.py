from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "data" / "legal_corpus.json"
DEFAULT_KB = ROOT / "data" / "legal_knowledge_base.json"
DEFAULT_EVALUATION = ROOT / "evaluation" / "datasets" / "official_core_cases.json"
DEFAULT_OUTPUT = ROOT / "data" / "kb_update_manifest.json"


@dataclass(frozen=True)
class DocumentChange:
    change_type: str
    document_id: str
    law_id: str
    law_name: str
    article_no: str
    changed_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "change_type": self.change_type,
            "document_id": self.document_id,
            "law_id": self.law_id,
            "law_name": self.law_name,
            "article_no": self.article_no,
            "changed_fields": list(self.changed_fields),
        }


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index(corpus: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in corpus:
        document_id = str(row.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("corpus row without document_id")
        if document_id in result:
            raise ValueError(f"duplicate document_id: {document_id}")
        result[document_id] = row
    return result


def compare_corpora(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> list[DocumentChange]:
    before, after = _index(baseline), _index(candidate)
    changes: list[DocumentChange] = []
    tracked = ("text", "article_title", "paragraph_no", "item_no", "subitem_no", "effective_from", "effective_to", "revision_date", "is_current", "version_id", "source_url")
    for document_id in sorted(before.keys() | after.keys()):
        old, new = before.get(document_id), after.get(document_id)
        row = new or old or {}
        common = dict(
            document_id=document_id,
            law_id=str(row.get("law_id") or ""),
            law_name=str(row.get("law_name") or ""),
            article_no=str(row.get("article_no") or ""),
        )
        if old is None:
            changes.append(DocumentChange("added", **common))
        elif new is None:
            changes.append(DocumentChange("removed", **common))
        else:
            changed = tuple(field for field in tracked if old.get(field) != new.get(field))
            if changed:
                if "text" in changed:
                    kind = "content_changed"
                elif {"effective_from", "effective_to", "is_current", "version_id"}.intersection(changed):
                    kind = "temporal_metadata_changed"
                else:
                    kind = "metadata_changed"
                changes.append(DocumentChange(kind, changed_fields=changed, **common))
    return changes


def validate_temporal_consistency(corpus: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for row in corpus:
        label = str(row.get("document_id") or "<missing-document-id>")
        try:
            start_raw, end_raw = row.get("effective_from"), row.get("effective_to")
            if not start_raw:
                errors.append(f"{label}: missing effective_from")
                continue
            start = date.fromisoformat(str(start_raw))
            end = date.fromisoformat(str(end_raw)) if end_raw else None
            if end and end < start:
                errors.append(f"{label}: effective_to precedes effective_from")
            if row.get("is_current") is True and end is not None:
                errors.append(f"{label}: current document has effective_to")
        except ValueError:
            errors.append(f"{label}: invalid effective date")
    return errors


def impacted_concepts(changes: list[DocumentChange], kb: dict[str, Any]) -> list[dict[str, Any]]:
    changed_docs = {c.document_id for c in changes}
    changed_articles = {(c.law_id, c.article_no) for c in changes}
    impacted = []
    for concept in kb.get("concepts", []):
        direct = changed_docs.intersection(concept.get("source_document_ids", []))
        article = {(str(concept.get("law_id")), str(a)) for a in concept.get("article_refs", [])}.intersection(changed_articles)
        if direct or article:
            impacted.append({
                "concept_id": concept["concept_id"],
                "law_id": concept["law_id"],
                "article_refs": concept["article_refs"],
                "reason": "source_document_changed" if direct else "linked_article_changed",
            })
    return sorted(impacted, key=lambda row: row["concept_id"])


def impacted_evaluation_cases(changes: list[DocumentChange], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed_articles = {(c.law_id, c.article_no) for c in changes}
    result = []
    for case in cases:
        law_id = case.get("expected_law_id")
        refs = case.get("expected_article_nos") or []
        matched = sorted(article for article in refs if (str(law_id), str(article)) in changed_articles)
        if matched:
            result.append({"case_id": case["case_id"], "law_id": law_id, "article_refs": matched})
    return sorted(result, key=lambda row: row["case_id"])


def build_manifest(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    kb: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
    mode: str = "comparison",
) -> dict[str, Any]:
    changes = compare_corpora(baseline, candidate)
    temporal_errors = validate_temporal_consistency(candidate)
    concepts = impacted_concepts(changes, kb)
    evaluations = impacted_evaluation_cases(changes, cases)
    status = "invalid" if temporal_errors else ("changes_detected" if changes else "no_changes")
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "status": status,
        "baseline_sha256": canonical_hash(baseline),
        "candidate_sha256": canonical_hash(candidate),
        "summary": {
            "baseline_documents": len(baseline),
            "candidate_documents": len(candidate),
            "changed_documents": len(changes),
            "impacted_concepts": len(concepts),
            "impacted_evaluation_cases": len(evaluations),
            "temporal_errors": len(temporal_errors),
        },
        "changes": [change.to_dict() for change in changes],
        "impacted_concepts": concepts,
        "impacted_evaluation_cases": evaluations,
        "temporal_errors": temporal_errors,
        "required_actions": _required_actions(status, changes, concepts, evaluations),
    }


def _required_actions(status: str, changes: list[DocumentChange], concepts: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> list[str]:
    if status == "invalid":
        return ["reject_candidate_corpus", "correct_temporal_metadata", "rerun_validation"]
    if not changes:
        return ["record_baseline_check"]
    actions = ["review_changed_official_sources"]
    if concepts:
        actions.append("review_and_version_impacted_concepts")
    if evaluations:
        actions.append("rerun_impacted_evaluation_cases")
    actions.extend(["validate_knowledge_base", "run_full_regression"])
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare statute corpora and trace legal-KB impact")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", default="baseline_integrity_check")
    args = parser.parse_args()
    manifest = build_manifest(load_json(args.baseline), load_json(args.candidate), load_json(args.kb), load_json(args.evaluation), mode=args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: status={manifest['status']}; changed={manifest['summary']['changed_documents']}; impacted_concepts={manifest['summary']['impacted_concepts']}; impacted_cases={manifest['summary']['impacted_evaluation_cases']}")
    return 1 if manifest["status"] == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
