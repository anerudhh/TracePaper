"""Credential-free parser subprocess: files in, extracted pages out."""

import json
import resource
import sys
import zipfile
from pathlib import Path
import fitz
from docx import Document


def extract(path, kind, ocr=False):
    pages = []
    if kind == "pdf":
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise ValueError(
                    "Password-protected PDFs are not supported. Upload an unlocked copy."
                )
            if len(doc) > 2000:
                raise ValueError(
                    "Limit is 2,000 pages per document. Split this document first."
                )
            for page in doc:
                text = page.get_text(sort=True)
                if len(text.strip()) < 30 and ocr:
                    text = page.get_text(textpage=page.get_textpage_ocr(language="eng"))
                pages.append(text)
    else:
        # A DOCX has no reliable page layout. Preserve paragraph sections instead.
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 150 * 1024 * 1024:
                raise ValueError("Expanded DOCX exceeds the 150 MB safety limit.")
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        paragraphs.extend(
            " | ".join(cell.text for cell in r.cells)
            for t in doc.tables
            for r in t.rows
        )
        section = ""
        for p in paragraphs:
            if len(section) + len(p) > 2500 and section:
                pages.append(section)
                section = ""
            section += p + "\n"
        if section:
            pages.append(section)
    if sum(len(t) for t in pages) > 20_000_000:
        raise ValueError(
            "Extracted text exceeds the 20-million-character processing limit."
        )
    if not any(len(t.strip()) >= 30 for t in pages):
        raise ValueError(
            "No readable text found. For scanned PDFs enable TRACEPAPER_OCR=1 with Tesseract installed."
        )
    return pages


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    try:
        result = {"pages": extract(Path(sys.argv[1]), sys.argv[3], sys.argv[4] == "1")}
    except Exception as error:
        result = {"error": str(error)[:400]}
    Path(sys.argv[2]).write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
