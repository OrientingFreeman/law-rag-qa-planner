from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from law_rag.domain.models import LegalProvision
from law_rag.ingestion.json_source import JsonLegalDocumentSource


def merge_corpus(path: str, incoming: Iterable[LegalProvision], *, replace_version: bool = True) -> dict:
    target = Path(path)
    existing = JsonLegalDocumentSource().load(target) if target.exists() else []
    incoming_list = list(incoming)
    index = {(p.document_id, p.version_id): p for p in existing}
    inserted = 0
    updated = 0
    for provision in incoming_list:
        key = (provision.document_id, provision.version_id)
        if key in index:
            if replace_version:
                index[key] = provision
                updated += 1
        else:
            index[key] = provision
            inserted += 1
    records = [p.to_dict() for p in sorted(index.values(), key=lambda p: (p.law_name, p.article_no, p.paragraph_no or "", p.item_no or "", p.subitem_no or "", p.version_id))]
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    return {"inserted": inserted, "updated": updated, "total": len(records), "path": str(target)}


def replace_corpus(path: str, incoming: Iterable[LegalProvision]) -> dict:
    """Atomically replace a corpus with the supplied normalized snapshot."""
    target = Path(path)
    incoming_list = list(incoming)
    records = [
        p.to_dict()
        for p in sorted(
            incoming_list,
            key=lambda p: (
                p.law_name, p.article_no, p.paragraph_no or "",
                p.item_no or "", p.subitem_no or "", p.version_id,
            ),
        )
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    return {"inserted": len(records), "updated": 0, "total": len(records), "path": str(target), "mode": "replace"}
