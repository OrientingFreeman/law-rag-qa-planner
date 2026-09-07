from __future__ import annotations

import argparse
import json

from law_rag.reasoning.ocr_audit import audit_ocr_source, save_ocr_audit_report
from law_rag.reasoning.pdf_import import import_searchable_pdf, save_private_pdf_import


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a searchable OCR PDF into a private page-level envelope")
    parser.add_argument("pdf", help="Searchable OCR PDF path")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--edition", required=True)
    parser.add_argument("--rights-status", default="private_research")
    parser.add_argument("--output", required=True, help="Private JSON output outside any Git worktree")
    parser.add_argument("--audit-output", help="Optional public-safe audit report path")
    args = parser.parse_args(argv)

    result = import_searchable_pdf(
        args.pdf,
        document_id=args.document_id,
        title=args.title,
        edition=args.edition,
        rights_status=args.rights_status,
    )
    output = save_private_pdf_import(result, args.output)
    audit_output = None
    quality_gate = None
    if args.audit_output:
        report = audit_ocr_source(result.manifest, result.pages)
        audit_output = save_ocr_audit_report(report, args.audit_output)
        quality_gate = report.quality_gate
    print(json.dumps({
        "output": str(output),
        "audit_output": str(audit_output) if audit_output else None,
        "document_id": result.manifest.document_id,
        "page_count": result.diagnostics.page_count,
        "text_layer_page_count": result.diagnostics.text_layer_page_count,
        "missing_text_layer_pages": list(result.diagnostics.missing_text_layer_pages),
        "printed_page_label_count": result.diagnostics.printed_page_label_count,
        "quality_gate": quality_gate,
    }, ensure_ascii=False, indent=2))
    return 2 if result.diagnostics.missing_text_layer_pages else 0


if __name__ == "__main__":
    raise SystemExit(main())
