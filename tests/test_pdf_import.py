from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from law_rag.reasoning.ocr_audit import audit_ocr_source
from law_rag.reasoning.pdf_import import (
    SearchablePdfImportError,
    detect_printed_page_label,
    detect_structure,
    import_searchable_pdf,
    save_private_pdf_import,
)


def _make_searchable_pdf(path: Path, pages: list[list[str]]) -> None:
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=(595, 842))
    for lines in pages:
        y = 790
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 24
        pdf.showPage()
    pdf.save()


def test_import_preserves_physical_pages_and_printed_labels(tmp_path: Path) -> None:
    source = tmp_path / "searchable.pdf"
    _make_searchable_pdf(source, [
        ["Searchable authored page one.", "1"],
        ["Searchable authored page two.", "2"],
    ])
    result = import_searchable_pdf(
        source,
        document_id="fixture.searchable_pdf",
        title="Authored searchable PDF",
        edition="test-1",
        rights_status="authored",
    )
    assert [page.page_number for page in result.pages] == [1, 2]
    assert [page.printed_page_label for page in result.pages] == ["1", "2"]
    assert result.diagnostics.page_count == 2
    assert result.diagnostics.text_layer_page_count == 2
    assert result.diagnostics.missing_text_layer_pages == ()
    assert result.manifest.private_source_ref == str(source.resolve())


def test_blank_pdf_page_is_reported_without_silent_ocr(tmp_path: Path) -> None:
    source = tmp_path / "partly-searchable.pdf"
    _make_searchable_pdf(source, [["Searchable authored text.", "1"], []])
    result = import_searchable_pdf(
        source,
        document_id="fixture.partial_pdf",
        title="Partial searchable PDF",
        edition="test-1",
        rights_status="authored",
    )
    assert result.diagnostics.missing_text_layer_pages == (2,)
    audit = audit_ocr_source(result.manifest, result.pages)
    assert audit.quality_gate == "blocked"
    assert any(item.code == "empty_page" and item.page_number == 2 for item in audit.warnings)


def test_private_envelope_and_public_audit_have_separate_content_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_searchable_pdf(source, [["Private extracted authored text.", "7"]])
    result = import_searchable_pdf(
        source,
        document_id="fixture.private_boundary",
        title="Private boundary fixture",
        edition="test-1",
        rights_status="authored",
    )
    output = save_private_pdf_import(result, tmp_path / "private" / "import.json")
    private_payload = output.read_text(encoding="utf-8")
    public_payload = audit_ocr_source(result.manifest, result.pages).to_json()
    assert "Private extracted authored text" in private_payload
    assert str(source.resolve()) in private_payload
    assert "Private extracted authored text" not in public_payload
    assert str(source.resolve()) not in public_payload
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_output_inside_git_worktree_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_searchable_pdf(source, [["Searchable authored text."]])
    result = import_searchable_pdf(
        source,
        document_id="fixture.git_guard",
        title="Git guard fixture",
        edition="test-1",
        rights_status="authored",
    )
    with pytest.raises(SearchablePdfImportError, match="Git worktree"):
        save_private_pdf_import(result, Path.cwd() / "evaluation" / "ocr" / "private-import.json")


def test_heading_and_page_label_detection_is_conservative() -> None:
    assert detect_printed_page_label("본문\n\n- 123 -") == "123"
    assert detect_printed_page_label("2026년 8월 22일") is None
    assert detect_printed_page_label("123 요건사실과 주장책임") == "123"
    assert detect_printed_page_label("요건사실과 주장책임 124") == "124"
    assert detect_structure("제1장 대여금\n제2절 반환기\n본문") == ("제1장 대여금", "제2절 반환기")
    assert detect_structure("장래의 반환에 관한 일반 문장") == (None, None)


def test_non_pdf_and_missing_pdf_are_rejected(tmp_path: Path) -> None:
    text = tmp_path / "not-pdf.txt"
    text.write_text("not a pdf", encoding="utf-8")
    kwargs = {
        "document_id": "fixture.invalid",
        "title": "Invalid fixture",
        "edition": "test-1",
        "rights_status": "authored",
    }
    with pytest.raises(SearchablePdfImportError, match="input must be a PDF"):
        import_searchable_pdf(text, **kwargs)
    with pytest.raises(SearchablePdfImportError, match="PDF not found"):
        import_searchable_pdf(tmp_path / "missing.pdf", **kwargs)


def test_private_envelope_remains_compatible_with_v427_loader(tmp_path: Path) -> None:
    from law_rag.reasoning.ocr_audit import load_ocr_import

    source = tmp_path / "compatible.pdf"
    _make_searchable_pdf(source, [["Compatible authored text.", "1"]])
    result = import_searchable_pdf(
        source,
        document_id="fixture.compatible",
        title="Compatible fixture",
        edition="test-1",
        rights_status="authored",
    )
    output = save_private_pdf_import(result, tmp_path / "compatible.json")
    manifest, pages = load_ocr_import(output)
    assert manifest.document_id == "fixture.compatible"
    assert pages[0].page_number == 1
    assert "Compatible authored text" in pages[0].text


def test_serialization_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "deterministic.pdf"
    _make_searchable_pdf(source, [["Deterministic authored text.", "1"]])
    result = import_searchable_pdf(
        source,
        document_id="fixture.deterministic",
        title="Deterministic fixture",
        edition="test-1",
        rights_status="authored",
    )
    assert json.loads(result.to_json()) == result.to_dict()
    assert result.to_json() == result.to_json()
