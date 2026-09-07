from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from law_rag.reasoning.ocr_audit import (
    audit_ocr_source,
    load_non_text_page_decisions,
    load_ocr_import,
    load_ocr_warning_decisions,
    ocr_content_sha256,
    save_ocr_audit_report,
)
from law_rag.reasoning.pdf_import import detect_printed_page_label
from law_rag.reasoning.ocr_review import build_private_ocr_review_queue, save_private_ocr_review_queue
from law_rag.reasoning.ocr_corrections import apply_ocr_text_corrections, load_ocr_text_corrections
from law_rag.reasoning.printed_page_decisions import apply_printed_page_decisions, load_printed_page_decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit private OCR provenance and structural quality")
    parser.add_argument("input", help="Private OCR import JSON envelope")
    parser.add_argument("--output", default="evaluation/ocr/ocr_audit_report.json")
    parser.add_argument("--page-decisions", help="Reviewed non-text page decisions JSON")
    parser.add_argument("--infer-footnotes", action="store_true", help="Add conservative body/footnote candidate hints")
    parser.add_argument("--repair-printed-labels", action="store_true", help="Re-detect labels from existing extracted text")
    parser.add_argument("--warning-decisions", help="Reviewed warning decisions JSON")
    parser.add_argument("--review-queue-output", help="Private warning queue with limited source snippets")
    parser.add_argument("--text-corrections", help="Approved private OCR text correction overlay JSON")
    parser.add_argument("--printed-page-decisions", help="Approved private printed-page decisions JSON")
    args = parser.parse_args(argv)

    manifest, pages = load_ocr_import(args.input)
    original_content_sha256 = ocr_content_sha256(pages)
    corrections = load_ocr_text_corrections(args.text_corrections) if args.text_corrections else []
    pages, correction_audit = apply_ocr_text_corrections(pages, corrections)
    if args.repair_printed_labels:
        pages = [replace(page, printed_page_label=page.printed_page_label or detect_printed_page_label(page.text)) for page in pages]
    printed_decisions = load_printed_page_decisions(args.printed_page_decisions) if args.printed_page_decisions else []
    pages, verified_absent_labels, printed_mapping_audit = apply_printed_page_decisions(pages, printed_decisions)
    decisions = load_non_text_page_decisions(args.page_decisions) if args.page_decisions else []
    warning_decisions = load_ocr_warning_decisions(args.warning_decisions) if args.warning_decisions else []
    report = audit_ocr_source(
        manifest,
        pages,
        page_decisions=decisions,
        warning_decisions=warning_decisions,
        verified_absent_printed_pages=verified_absent_labels,
        infer_footnotes=args.infer_footnotes,
    )
    if args.printed_page_decisions:
        decision_envelope = json.loads(Path(args.printed_page_decisions).read_text(encoding="utf-8"))
        expected_hash = decision_envelope.get("source_content_sha256")
        if expected_hash and expected_hash != original_content_sha256:
            raise ValueError("printed-page decisions do not match current OCR content hash")
    output = save_ocr_audit_report(report, args.output)
    queue_output = None
    if args.review_queue_output:
        queue = build_private_ocr_review_queue(
            report,
            pages,
            page_decisions=decisions,
            correction_audit=[*correction_audit, {"printed_page_mapping_audit": printed_mapping_audit}],
        )
        queue_output = save_private_ocr_review_queue(queue, args.review_queue_output)
    print(json.dumps({
        "output": str(output),
        "review_queue_output": str(queue_output) if queue_output else None,
        "document_id": manifest.document_id,
        "page_count": report.page_count,
        "segment_count": report.segment_count,
        "applied_correction_count": len(correction_audit),
        "applied_printed_page_decision_count": len(printed_mapping_audit),
        "quality_gate": report.quality_gate,
        "summary": report.summary,
    }, ensure_ascii=False, indent=2))
    return 2 if report.quality_gate == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
