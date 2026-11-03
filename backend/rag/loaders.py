"""Local loaders for PDF, DOCX, text, Markdown, and source-code files."""

from pathlib import Path

from backend.rag.models import DocumentSegment, LoadedDocument

SUPPORTED_SUFFIXES = {
    ".pdf", ".docx", ".txt", ".md", ".markdown", ".rst", ".py", ".rb", ".js", ".ts", ".tsx",
    ".jsx", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".sql", ".sh", ".ps1",
    ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".swift", ".kt", ".xml", ".csv",
}


class DocumentLoadError(ValueError):
    """Raised when a supported document cannot be parsed safely."""


def _load_text(path: Path) -> LoadedDocument:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        raise DocumentLoadError("Text document must be readable UTF-8") from exc
    if "\x00" in text:
        raise DocumentLoadError("Binary-looking input is not a supported text document")
    return LoadedDocument(path.name, [DocumentSegment(text=text)])


def _load_pdf(path: Path) -> LoadedDocument:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise DocumentLoadError("Encrypted PDFs are not supported") from exc
        segments = [
            DocumentSegment(text=page.extract_text() or "", page_number=index, location_unit="line", start_line=1)
            for index, page in enumerate(reader.pages, start=1)
        ]
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError("PDF parsing failed") from exc
    return LoadedDocument(path.name, segments)


def _load_docx(path: Path) -> LoadedDocument:
    try:
        from docx import Document

        document = Document(str(path))
        groups: list[DocumentSegment] = []
        section_name: str | None = None
        paragraphs: list[str] = []
        paragraph_start = 1
        for number, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text.strip()
            style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
            if style_name.casefold().startswith("heading") and paragraphs:
                groups.append(DocumentSegment("\n".join(paragraphs), location_unit="paragraph", section=section_name,
                                              start_line=paragraph_start))
                paragraphs = []
                paragraph_start = number
            if style_name.casefold().startswith("heading"):
                section_name = text
            paragraphs.append(text)
        if paragraphs:
            groups.append(DocumentSegment("\n".join(paragraphs), location_unit="paragraph", section=section_name,
                                          start_line=paragraph_start))
        for table_number, table in enumerate(document.tables, start=1):
            rows = []
            for row_number, row in enumerate(table.rows, start=1):
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                groups.append(DocumentSegment(
                    "\n".join(rows), location_unit="table_row", section=f"Table {table_number}", start_line=1,
                ))
        # Paragraph and table row ordinals are retained for source citations.
        return LoadedDocument(path.name, groups)
    except Exception as exc:
        if isinstance(exc, DocumentLoadError):
            raise
        raise DocumentLoadError("DOCX parsing failed") from exc


def load_document(path: Path) -> LoadedDocument:
    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentLoadError(f"Unsupported document format: {suffix or '(no extension)'}")
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".docx":
        return _load_docx(path)
    return _load_text(path)
