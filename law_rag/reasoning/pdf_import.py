from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from law_rag.reasoning.ocr_audit import OcrPageInput, OcrSourceManifest


PDF_IMPORT_SCHEMA_VERSION = "0.1.0"
PRINTED_PAGE_RE = re.compile(r"^(?:-\s*)?([0-9]{1,4}|[ivxlcdm]{1,10})(?:\s*-)?$", re.IGNORECASE)
EDGE_PRINTED_PAGE_RE = re.compile(r"^(?:(?:-\s*)?([0-9]{1,4}|[ivxlcdm]{1,10})(?:\s*-)?\s+\S.*|\S.*?\s+(?:-\s*)?([0-9]{1,4}|[ivxlcdm]{1,10})(?:\s*-)?$)", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^제\s*([0-9일이삼사오육칠팔구십백]+)\s*(장|편)\b")
SECTION_RE = re.compile(r"^제\s*([0-9일이삼사오육칠팔구십백]+)\s*절\b")


class SearchablePdfImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PdfImportDiagnostics:
    page_count: int
    text_layer_page_count: int
    missing_text_layer_pages: tuple[int, ...]
    printed_page_label_count: int
    chapter_heading_count: int
    section_heading_count: int


@dataclass(frozen=True, slots=True)
class SearchablePdfImport:
    schema_version: str
    manifest: OcrSourceManifest
    pages: tuple[OcrPageInput, ...]
    diagnostics: PdfImportDiagnostics

    def to_dict(self) -> dict[str, Any]:
        manifest = self.manifest.to_dict(public=False)
        manifest["expected_chapters"] = list(manifest.get("expected_chapters", []))
        diagnostics = asdict(self.diagnostics)
        diagnostics["missing_text_layer_pages"] = list(self.diagnostics.missing_text_layer_pages)
        return {
            "schema_version": self.schema_version,
            "manifest": manifest,
            "pages": [asdict(page) for page in self.pages],
            "diagnostics": diagnostics,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent) + "\n"


def _nonempty_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def detect_printed_page_label(text: str) -> str | None:
    lines = _nonempty_lines(text)
    for line in [*lines[:2], *lines[-2:]]:
        match = PRINTED_PAGE_RE.fullmatch(line)
        if match:
            return match.group(1)
        if len(line) <= 80:
            edge = EDGE_PRINTED_PAGE_RE.fullmatch(line)
            if edge:
                candidate = edge.group(1) or edge.group(2)
                if not (candidate.isdigit() and 1900 <= int(candidate) <= 2100):
                    return candidate
    return None


def detect_structure(text: str) -> tuple[str | None, str | None]:
    chapter: str | None = None
    section: str | None = None
    for line in _nonempty_lines(text):
        if len(line) > 80:
            continue
        if chapter is None and CHAPTER_RE.match(line):
            chapter = line
        if section is None and SECTION_RE.match(line):
            section = line
        if chapter is not None and section is not None:
            break
    return chapter, section


def import_searchable_pdf(
    pdf_path: str | Path,
    *,
    document_id: str,
    title: str,
    edition: str,
    rights_status: str = "private_research",
) -> SearchablePdfImport:
    """Extract a searchable PDF into the private v4.27.0 OCR import envelope."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise SearchablePdfImportError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise SearchablePdfImportError("input must be a PDF")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SearchablePdfImportError("pypdf is required; install with: pip install -e '.[pdf]'") from exc

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:
        raise SearchablePdfImportError(f"failed to open PDF: {exc}") from exc
    if reader.is_encrypted and not reader.decrypt(""):
        raise SearchablePdfImportError("encrypted PDF requires decryption before import")
    if not reader.pages:
        raise SearchablePdfImportError("PDF has no pages")

    pages: list[OcrPageInput] = []
    missing: list[int] = []
    printed_count = 0
    chapter_count = 0
    section_count = 0
    for physical_page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        except Exception as exc:
            raise SearchablePdfImportError(f"text extraction failed on physical page {physical_page_number}: {exc}") from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            missing.append(physical_page_number)
        printed_label = detect_printed_page_label(text)
        chapter, section = detect_structure(text)
        printed_count += int(printed_label is not None)
        chapter_count += int(chapter is not None)
        section_count += int(section is not None)
        pages.append(OcrPageInput(
            page_number=physical_page_number,
            text=text,
            printed_page_label=printed_label,
            chapter=chapter,
            section=section,
        ))

    manifest = OcrSourceManifest(
        document_id=document_id,
        title=title,
        edition=edition,
        source_type="ocr",
        rights_status=rights_status,
        page_start=1,
        page_end=len(pages),
        private_source_ref=str(path),
        metadata={
            "public_import_format": "searchable_pdf",
            "public_import_schema_version": PDF_IMPORT_SCHEMA_VERSION,
        },
    )
    manifest.validate()
    diagnostics = PdfImportDiagnostics(
        page_count=len(pages),
        text_layer_page_count=len(pages) - len(missing),
        missing_text_layer_pages=tuple(missing),
        printed_page_label_count=printed_count,
        chapter_heading_count=chapter_count,
        section_heading_count=section_count,
    )
    return SearchablePdfImport(PDF_IMPORT_SCHEMA_VERSION, manifest, tuple(pages), diagnostics)


def _active_git_worktree_root() -> Path | None:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def save_private_pdf_import(result: SearchablePdfImport, output_path: str | Path) -> Path:
    """Write raw extracted text only outside a Git worktree and restrict permissions."""
    output = Path(output_path).expanduser().resolve()
    worktree = _active_git_worktree_root()
    if worktree is not None and output.is_relative_to(worktree):
        raise SearchablePdfImportError(
            f"refusing to write OCR full text inside Git worktree: {worktree}; choose private storage outside the repository"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.to_json(), encoding="utf-8")
    output.chmod(0o600)
    return output
