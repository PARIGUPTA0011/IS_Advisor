"""Reading a specification out of a file, whatever the file happens to be.

Plain text passes through unchanged. PDFs go through `pdfplumber`, which is the
same library the deferred scope-text work will need, so this adds no new
dependency family.
"""
from __future__ import annotations

from pathlib import Path

# A text-bearing page yields far more than this. Below it, the page is almost
# certainly a scan, and silently searching an empty string would look like a
# tender with no line items rather than a file we cannot read.
MIN_CHARS_PER_PAGE = 40


class ScannedPdfError(RuntimeError):
    """Raised when a PDF carries images rather than extractable text."""


def read_document(path: Path) -> str:
    """Return the text of a specification file."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    return path.read_text(encoding="utf-8", errors="replace")


def read_pdf(path: Path) -> str:
    """Extract text page by page.

    One extraction path per page, deliberately. Running `extract_text` and
    `extract_tables` together fed the same schedule of quantities into the
    splitter twice, so every table row was searched, ranked and reported twice.
    `extract_text` already returns table rows intact, one row per line, which is
    what the line splitter wants.
    """
    try:
        import pdfplumber
    except ImportError as error:                       # pragma: no cover
        raise RuntimeError(
            "reading PDFs needs pdfplumber: pip install pdfplumber"
        ) from error

    pages: list[str] = []
    total_chars = 0
    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            total_chars += len(page_text.strip())
            pages.append(page_text)

    if page_count and total_chars < MIN_CHARS_PER_PAGE * page_count:
        raise ScannedPdfError(
            f"{path.name} yielded {total_chars} characters across {page_count} page(s), "
            "which means it is a scan rather than a text PDF. Optical character "
            "recognition is out of scope; supply the specification as text."
        )
    return "\n".join(pages)
