"""
Format dispatcher for document ingestion — one entrypoint, strategy per
format, same pattern as tools/registry.py. Adding a new format means adding
one function and one dict entry here, nothing else changes.
"""

from __future__ import annotations

from utils.errors import IngestionError


def _parse_pdf(path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _parse_docx(path: str) -> str:
    import docx
    document = docx.Document(path)
    return "\n\n".join(p.text for p in document.paragraphs if p.text)


def _parse_xlsx(path: str) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        rows = [", ".join(str(c) for c in row if c is not None) for row in sheet.iter_rows(values_only=True)]
        parts.append(f"Sheet: {sheet.title}\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _parse_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


_PARSERS = {
    "application/pdf": _parse_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _parse_docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _parse_xlsx,
    "text/plain": _parse_txt,
}

_EXTENSION_FALLBACK = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".txt": "text/plain"}


def parse_document(path: str, content_type: str, filename: str) -> str:
    parser = _PARSERS.get(content_type)
    if parser is None:
        import os
        ext = os.path.splitext(filename)[1].lower()
        content_type = _EXTENSION_FALLBACK.get(ext, "")
        parser = _PARSERS.get(content_type)
    if parser is None:
        raise IngestionError(
            f"Unsupported document type: {content_type or filename}",
            user_message="That file type isn't supported yet (PDF, DOCX, XLSX, and TXT are).",
        )
    text = parser(path)
    if not text.strip():
        raise IngestionError(
            f"No extractable text in {filename}",
            user_message="I couldn't find any text in that file — if it's a scanned/image PDF, OCR support isn't wired in yet.",
        )
    return text
