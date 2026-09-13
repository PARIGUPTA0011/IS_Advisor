"""Write the small PDF fixtures the tests read.

The PDFs are assembled byte by byte rather than with a PDF writer, so the test
suite needs no library that the product itself does not use.

    python Semantic_Analysis/tests/make_fixtures.py
"""
from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

TENDER_LINES = [
    "SCHEDULE OF MATERIALS",
    "1. TMT reinforcement bars Fe 500D grade conforming to IS 1786",
    "2. Ordinary Portland Cement 43 grade in 50 kg bags",
    "3. Cast iron sluice valve DN 150 for the pumping main",
]


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(lines: list[str]) -> bytes:
    """A one-page PDF showing each line, using the base Helvetica font."""
    content = ["BT", "/F1 11 Tf", "14 TL", "40 760 Td"]
    for line in lines:
        content.append(f"({_escape(line)}) Tj")
        content.append("T*")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    return _assemble(objects)


def build_scanned_pdf() -> bytes:
    """A page with no text at all, standing in for a scan."""
    stream = b"0.9 g 40 600 500 180 re f"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    return _assemble(objects)


def _assemble(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written = [
        (FIXTURE_DIR / "tender.pdf", build_pdf(TENDER_LINES)),
        (FIXTURE_DIR / "scanned.pdf", build_scanned_pdf()),
    ]
    for path, data in written:
        path.write_bytes(data)
        print(f"wrote {path.relative_to(FIXTURE_DIR.parent)}  {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
