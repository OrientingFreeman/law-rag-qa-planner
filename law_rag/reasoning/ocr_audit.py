from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


OCR_MANIFEST_SCHEMA_VERSION = "0.1.0"
OCR_AUDIT_SCHEMA_VERSION = "0.2.0"
PAGE_DECISIONS_SCHEMA_VERSION = "0.1.0"
WARNING_DECISIONS_SCHEMA_VERSION = "0.1.0"
ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]*$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
COMPATIBILITY_IDEOGRAPH_RE = re.compile(r"[\uf900-\ufaff]")
SUSPECT_ARTICLE_RE = re.compile(r"제\s*\d+(?:의\s*\d+)?\s*(?:죠|조우|조l|조I)")
SUSPECT_NEGATION_RE = re.compile(r"아니\s*(?:뇐다|됀다|되ㄴ다)")
SUSPECT_NEGATION_SPACING_RE = re.compile(r"아니\s+된\s+다")


class OcrAuditValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OcrSourceManifest:
    document_id: str
    title: str
    edition: str
    source_type: str
    rights_status: str
    page_start: int
    page_end: int
    private_source_ref: str | None = None
    expected_chapters: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = OCR_MANIFEST_SCHEMA_VERSION

    def validate(self) -> None:
        errors: list[str] = []
        if self.schema_version != OCR_MANIFEST_SCHEMA_VERSION:
            errors.append(f"unsupported schema_version: {self.schema_version}")
        if not ID_RE.fullmatch(self.document_id):
            errors.append(f"invalid document_id: {self.document_id}")
        if not self.title.strip() or not self.edition.strip():
            errors.append("title and edition are required")
        if self.source_type not in {"ocr", "born_digital", "public_statute", "authored_fixture"}:
            errors.append(f"unsupported source_type: {self.source_type}")
        if self.rights_status not in {"private_research", "licensed", "public_domain", "public_law", "authored"}:
            errors.append(f"unsupported rights_status: {self.rights_status}")
        if self.page_start < 1 or self.page_end < self.page_start:
            errors.append("invalid page range")
        if errors:
            raise OcrAuditValidationError("; ".join(errors))

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "OcrSourceManifest":
        payload = dict(row)
        payload["expected_chapters"] = tuple(payload.get("expected_chapters", []))
        manifest = cls(**payload)
        manifest.validate()
        return manifest

    def to_dict(self, *, public: bool = False) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        if public:
            payload.pop("private_source_ref", None)
            payload["metadata"] = {
                key: value for key, value in payload["metadata"].items()
                if key.startswith("public_")
            }
        return payload


@dataclass(frozen=True, slots=True)
class OcrPageInput:
    page_number: int
    text: str
    printed_page_label: str | None = None
    chapter: str | None = None
    section: str | None = None
    footnote_boundary_char: int | None = None

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "OcrPageInput":
        return cls(**row)


@dataclass(frozen=True, slots=True)
class OcrSegmentProvenance:
    segment_id: str
    document_id: str
    edition: str
    page_number: int
    paragraph_number: int
    char_start: int
    char_end: int
    text_sha256: str
    printed_page_label: str | None = None
    chapter: str | None = None
    section: str | None = None
    review_status: str = "draft"
    zone_hint: str = "unknown"


@dataclass(frozen=True, slots=True)
class NonTextPageDecision:
    page_number: int
    classification: str
    reason: str
    review_status: str
    reviewer: str
    reviewed_at: str

    def validate(self) -> None:
        if self.page_number < 1:
            raise OcrAuditValidationError("page decision page_number must be positive")
        if self.classification not in {"blank", "divider", "image_only_nonsemantic", "other_non_text"}:
            raise OcrAuditValidationError(f"unsupported non-text classification: {self.classification}")
        if self.review_status not in {"draft", "approved", "rejected"}:
            raise OcrAuditValidationError(f"unsupported page decision review_status: {self.review_status}")
        if not all(value.strip() for value in (self.reason, self.reviewer, self.reviewed_at)):
            raise OcrAuditValidationError("reason, reviewer, and reviewed_at are required")


def load_non_text_page_decisions(path: str | Path) -> list[NonTextPageDecision]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != PAGE_DECISIONS_SCHEMA_VERSION or not isinstance(payload.get("decisions"), list):
        raise OcrAuditValidationError("invalid page decisions envelope")
    decisions = [NonTextPageDecision(**row) for row in payload["decisions"]]
    for decision in decisions:
        decision.validate()
    if len({item.page_number for item in decisions}) != len(decisions):
        raise OcrAuditValidationError("duplicate page decision")
    return decisions


@dataclass(frozen=True, slots=True)
class OcrWarningDecision:
    warning_id: str
    action: str
    reason: str
    review_status: str
    reviewer: str
    reviewed_at: str

    def validate(self) -> None:
        if not self.warning_id.startswith("warn."):
            raise OcrAuditValidationError("invalid warning_id")
        if self.action not in {"accepted_as_is", "verified_label_absent", "corrected_source"}:
            raise OcrAuditValidationError(f"unsupported warning decision action: {self.action}")
        if self.review_status not in {"draft", "approved", "rejected"}:
            raise OcrAuditValidationError(f"unsupported warning decision review_status: {self.review_status}")
        if not all(value.strip() for value in (self.reason, self.reviewer, self.reviewed_at)):
            raise OcrAuditValidationError("reason, reviewer, and reviewed_at are required")


def load_ocr_warning_decisions(path: str | Path) -> list[OcrWarningDecision]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != WARNING_DECISIONS_SCHEMA_VERSION or not isinstance(payload.get("decisions"), list):
        raise OcrAuditValidationError("invalid warning decisions envelope")
    decisions = [OcrWarningDecision(**row) for row in payload["decisions"]]
    for decision in decisions:
        decision.validate()
    if len({item.warning_id for item in decisions}) != len(decisions):
        raise OcrAuditValidationError("duplicate warning decision")
    return decisions


FOOTNOTE_MARKER_RE = re.compile(r"(?m)^\s*(?:\d{1,3}[.)]|[①-⑳])\s*\S")


def detect_footnote_boundary(text: str) -> int | None:
    """Return a conservative character boundary; it never removes or rewrites text."""
    if len(text) < 80:
        return None
    matches = list(FOOTNOTE_MARKER_RE.finditer(text))
    for index, match in enumerate(matches):
        ratio = match.start() / len(text)
        later = matches[index + 1:]
        if 0.20 <= ratio <= 0.90 and later and later[0].start() - match.start() <= max(800, len(text) // 2):
            return match.start()
    return None


@dataclass(frozen=True, slots=True)
class OcrAuditWarning:
    warning_id: str
    code: str
    severity: str
    message: str
    page_number: int | None = None
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class OcrAuditReport:
    schema_version: str
    document: dict[str, Any]
    page_count: int
    segment_count: int
    page_numbers: tuple[int, ...]
    content_sha256: str
    segments: tuple[OcrSegmentProvenance, ...]
    warnings: tuple[OcrAuditWarning, ...]
    quality_gate: str
    summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent) + "\n"


def load_ocr_import(path: str | Path) -> tuple[OcrSourceManifest, list[OcrPageInput]]:
    """Load a private OCR import envelope without retaining its path in reports."""
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise OcrAuditValidationError("OCR import must be a JSON object")
    manifest = OcrSourceManifest.from_dict(dict(row.get("manifest") or {}))
    raw_pages = row.get("pages")
    if not isinstance(raw_pages, list):
        raise OcrAuditValidationError("pages must be a list")
    pages = [OcrPageInput.from_dict(item) for item in raw_pages if isinstance(item, dict)]
    if len(pages) != len(raw_pages):
        raise OcrAuditValidationError("every page must be an object")
    return manifest, pages


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, flags=re.DOTALL):
        spans.append((match.start(), match.end()))
    return spans


def _warning(
    code: str,
    severity: str,
    message: str,
    *,
    page_number: int | None = None,
    segment_id: str | None = None,
) -> OcrAuditWarning:
    location = f"{page_number or 0}:{segment_id or '-'}"
    digest = hashlib.sha256(f"{code}:{location}".encode()).hexdigest()[:12]
    return OcrAuditWarning(f"warn.{digest}", code, severity, message, page_number, segment_id)


def ocr_content_sha256(pages: Iterable[OcrPageInput]) -> str:
    digest = hashlib.sha256()
    for page in pages:
        digest.update(f"{page.page_number}:".encode())
        digest.update(page.text.encode("utf-8"))
    return digest.hexdigest()


def audit_ocr_source(
    manifest: OcrSourceManifest,
    pages: Iterable[OcrPageInput],
    *,
    page_decisions: Iterable[NonTextPageDecision] = (),
    warning_decisions: Iterable[OcrWarningDecision] = (),
    verified_absent_printed_pages: Iterable[int] = (),
    infer_footnotes: bool = False,
) -> OcrAuditReport:
    """Audit OCR structure and risky tokens without returning source text."""
    manifest.validate()
    rows = list(pages)
    warnings: list[OcrAuditWarning] = []
    segments: list[OcrSegmentProvenance] = []
    decisions = list(page_decisions)
    for decision in decisions:
        decision.validate()
    if len({item.page_number for item in decisions}) != len(decisions):
        raise OcrAuditValidationError("duplicate page decision")
    decision_by_page = {item.page_number: item for item in decisions}
    for number in decision_by_page:
        if not manifest.page_start <= number <= manifest.page_end:
            raise OcrAuditValidationError(f"page decision out of range: {number}")
    reviewed = list(warning_decisions)
    for decision in reviewed:
        decision.validate()
    if len({item.warning_id for item in reviewed}) != len(reviewed):
        raise OcrAuditValidationError("duplicate warning decision")
    reviewed_by_id = {item.warning_id: item for item in reviewed if item.review_status == "approved"}
    verified_absent_labels = set(verified_absent_printed_pages)
    if any(number < manifest.page_start or number > manifest.page_end for number in verified_absent_labels):
        raise OcrAuditValidationError("verified absent printed page out of range")

    page_numbers = [page.page_number for page in rows]
    if len(set(page_numbers)) != len(page_numbers):
        warnings.append(_warning("duplicate_page_number", "error", "중복된 페이지 번호가 있습니다."))
    expected = set(range(manifest.page_start, manifest.page_end + 1))
    actual = set(page_numbers)
    for number in sorted(expected - actual):
        warnings.append(_warning("missing_page", "error", "manifest 범위의 페이지가 누락되었습니다.", page_number=number))
    for number in sorted(actual - expected):
        warnings.append(_warning("page_out_of_range", "error", "manifest 범위를 벗어난 페이지입니다.", page_number=number))
    if page_numbers != sorted(page_numbers):
        warnings.append(_warning("page_order", "error", "페이지 입력 순서가 증가 순서가 아닙니다."))

    found_chapters: set[str] = set()
    for page in rows:
        if page.chapter:
            found_chapters.add(page.chapter)
        decision = decision_by_page.get(page.page_number)
        if not page.text.strip() and decision and decision.review_status == "approved":
            warnings.append(_warning("expected_non_text_page", "info", "승인된 비본문 페이지입니다.", page_number=page.page_number))
        elif not page.text.strip():
            warnings.append(_warning("empty_page", "error", "OCR 텍스트가 비어 있습니다.", page_number=page.page_number))
        elif len(page.text.strip()) < 20:
            warnings.append(_warning("short_page", "warning", "OCR 텍스트가 비정상적으로 짧습니다.", page_number=page.page_number))
        if page.printed_page_label is None and page.page_number not in verified_absent_labels and not (not page.text.strip() and decision and decision.review_status == "approved"):
            warnings.append(_warning("missing_printed_page_label", "warning", "인쇄 페이지 표지가 없습니다.", page_number=page.page_number))
        elif page.printed_page_label is None and page.page_number in verified_absent_labels:
            warnings.append(_warning("verified_printed_label_absent", "info", "인쇄면수가 없는 페이지로 검토 승인되었습니다.", page_number=page.page_number))
        if "\ufffd" in page.text or "□" in page.text:
            warnings.append(_warning("replacement_glyph", "error", "대체 문자 또는 판독 불가 문자가 있습니다.", page_number=page.page_number))
        if CONTROL_RE.search(page.text):
            warnings.append(_warning("control_character", "error", "허용되지 않는 제어 문자가 있습니다.", page_number=page.page_number))
        if COMPATIBILITY_IDEOGRAPH_RE.search(page.text):
            warnings.append(_warning("compatibility_ideograph", "warning", "OCR 검수가 필요한 호환 한자가 있습니다.", page_number=page.page_number))
        if SUSPECT_ARTICLE_RE.search(page.text):
            warnings.append(_warning("suspect_article_number", "error", "조문 번호 OCR 오류 가능성이 있습니다.", page_number=page.page_number))
        if SUSPECT_NEGATION_RE.search(page.text):
            warnings.append(_warning("suspect_negation", "error", "법률 의미를 바꿀 수 있는 부정 표현 OCR 오류 가능성이 있습니다.", page_number=page.page_number))
        if SUSPECT_NEGATION_SPACING_RE.search(page.text):
            warnings.append(_warning("suspect_negation_spacing", "warning", "부정 표현의 비정상 띄어쓰기를 검토해야 합니다.", page_number=page.page_number))

        boundary = page.footnote_boundary_char
        if boundary is None and infer_footnotes:
            boundary = detect_footnote_boundary(page.text)
        if boundary is not None and not 0 <= boundary <= len(page.text):
            raise OcrAuditValidationError(f"invalid footnote boundary on page {page.page_number}")
        for paragraph_number, (start, end) in enumerate(_paragraph_spans(page.text), start=1):
            text_hash = hashlib.sha256(page.text[start:end].encode("utf-8")).hexdigest()
            segment_id = f"segment.{manifest.document_id}.p{page.page_number}.para{paragraph_number}"
            segments.append(OcrSegmentProvenance(
                segment_id=segment_id,
                document_id=manifest.document_id,
                edition=manifest.edition,
                page_number=page.page_number,
                paragraph_number=paragraph_number,
                char_start=start,
                char_end=end,
                text_sha256=text_hash,
                printed_page_label=page.printed_page_label,
                chapter=page.chapter,
                section=page.section,
                zone_hint="footnote_candidate" if boundary is not None and start >= boundary else ("body_candidate" if boundary is not None else "unknown"),
            ))

    for chapter in manifest.expected_chapters:
        if chapter not in found_chapters:
            warnings.append(_warning("missing_chapter", "warning", f"예상 장 식별자가 없습니다: {chapter}"))

    unknown_warning_ids = set(reviewed_by_id) - {item.warning_id for item in warnings}
    if unknown_warning_ids:
        raise OcrAuditValidationError(f"warning decision does not match current audit: {sorted(unknown_warning_ids)[0]}")
    warnings = [
        OcrAuditWarning(item.warning_id, item.code, "info", f"검토 완료: {item.message}", item.page_number, item.segment_id)
        if item.warning_id in reviewed_by_id and item.severity == "warning" else item
        for item in warnings
    ]

    counts = {"error": 0, "warning": 0, "info": 0}
    for item in warnings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    quality_gate = "blocked" if counts["error"] else ("review_required" if counts["warning"] else "passed")
    return OcrAuditReport(
        schema_version=OCR_AUDIT_SCHEMA_VERSION,
        document=manifest.to_dict(public=True),
        page_count=len(rows),
        segment_count=len(segments),
        page_numbers=tuple(page_numbers),
        content_sha256=ocr_content_sha256(rows),
        segments=tuple(segments),
        warnings=tuple(warnings),
        quality_gate=quality_gate,
        summary={
            **counts,
            "missing_page_count": len(expected - actual),
            "expected_non_text_count": sum(1 for item in warnings if item.code == "expected_non_text_page"),
            "footnote_candidate_page_count": len({item.page_number for item in segments if item.zone_hint == "footnote_candidate"}),
            "missing_printed_page_label_count": sum(1 for item in warnings if item.code == "missing_printed_page_label"),
            "reviewed_warning_count": sum(1 for item in warnings if item.severity == "info" and item.warning_id in reviewed_by_id),
            "verified_printed_label_absent_count": sum(1 for item in warnings if item.code == "verified_printed_label_absent"),
        },
    )


def save_ocr_audit_report(report: OcrAuditReport, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_json(), encoding="utf-8")
    return output
