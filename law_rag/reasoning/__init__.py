from law_rag.reasoning.law_graph import GraphEdge, LawGraph, ReasoningChainBuilder
from law_rag.reasoning.legal_logic import (
    LegalLogicTree,
    LogicEdge,
    LogicNode,
    build_answer_skeleton,
    build_counter_reasoning,
    build_decision_trace,
    build_rule_competition,
    resolve_rule_conflicts,
    derive_reasoning_path_from_logic_tree,
    build_legal_logic_tree,
    validate_legal_logic_tree,
)

__all__ = [
    "GraphEdge",
    "LawGraph",
    "ReasoningChainBuilder",
    "LegalLogicTree",
    "LogicEdge",
    "LogicNode",
    "build_answer_skeleton",
    "build_counter_reasoning",
    "build_decision_trace",
    "build_rule_competition",
    "resolve_rule_conflicts",
    "derive_reasoning_path_from_logic_tree",
    "build_legal_logic_tree",
    "validate_legal_logic_tree",
]
from law_rag.reasoning.legal_schema import (
    ExternalReference,
    FactStatus,
    LegalReasoningSchema,
    NodeType,
    ReasoningNode,
    ReasoningRelation,
    ReviewStatus,
    SCHEMA_VERSION,
    SchemaValidationError,
    SourceProvenance,
)

__all__ += [
    "ExternalReference",
    "FactStatus",
    "LegalReasoningSchema",
    "NodeType",
    "ReasoningNode",
    "ReasoningRelation",
    "ReviewStatus",
    "SCHEMA_VERSION",
    "SchemaValidationError",
    "SourceProvenance",
]

from law_rag.reasoning.ocr_audit import (
    OCR_AUDIT_SCHEMA_VERSION,
    OCR_MANIFEST_SCHEMA_VERSION,
    OcrAuditReport,
    OcrAuditValidationError,
    OcrAuditWarning,
    OcrPageInput,
    NonTextPageDecision,
    OcrWarningDecision,
    OcrSegmentProvenance,
    OcrSourceManifest,
    audit_ocr_source,
    detect_footnote_boundary,
    load_non_text_page_decisions,
    load_ocr_warning_decisions,
    load_ocr_import,
    ocr_content_sha256,
    save_ocr_audit_report,
)

__all__ += [
    "OCR_AUDIT_SCHEMA_VERSION",
    "OCR_MANIFEST_SCHEMA_VERSION",
    "OcrAuditReport",
    "OcrAuditValidationError",
    "OcrAuditWarning",
    "OcrPageInput",
    "NonTextPageDecision",
    "OcrWarningDecision",
    "OcrSegmentProvenance",
    "OcrSourceManifest",
    "audit_ocr_source",
    "detect_footnote_boundary",
    "load_non_text_page_decisions",
    "load_ocr_warning_decisions",
    "load_ocr_import",
    "ocr_content_sha256",
    "save_ocr_audit_report",
]

from law_rag.reasoning.pdf_import import (
    PDF_IMPORT_SCHEMA_VERSION,
    PdfImportDiagnostics,
    SearchablePdfImport,
    SearchablePdfImportError,
    detect_printed_page_label,
    detect_structure,
    import_searchable_pdf,
    save_private_pdf_import,
)

__all__ += [
    "PDF_IMPORT_SCHEMA_VERSION",
    "PdfImportDiagnostics",
    "SearchablePdfImport",
    "SearchablePdfImportError",
    "detect_printed_page_label",
    "detect_structure",
    "import_searchable_pdf",
    "save_private_pdf_import",
]

from law_rag.reasoning.ocr_corrections import (
    OCR_TEXT_CORRECTIONS_SCHEMA_VERSION,
    OcrTextCorrection,
    apply_ocr_text_corrections,
    load_ocr_text_corrections,
)

__all__ += [
    "OCR_TEXT_CORRECTIONS_SCHEMA_VERSION",
    "OcrTextCorrection",
    "apply_ocr_text_corrections",
    "load_ocr_text_corrections",
]

from law_rag.reasoning.printed_page_decisions import (
    PRINTED_PAGE_DECISIONS_SCHEMA_VERSION,
    PrintedPageDecision,
    apply_printed_page_decisions,
    decisions_from_review_queue,
    load_printed_page_decisions,
)

__all__ += [
    "PRINTED_PAGE_DECISIONS_SCHEMA_VERSION",
    "PrintedPageDecision",
    "apply_printed_page_decisions",
    "decisions_from_review_queue",
    "load_printed_page_decisions",
]
