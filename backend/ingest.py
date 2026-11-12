"""Isolated document parser. Invoked only by the ingestion coordinator."""

import resource
import sys
import zipfile
from pathlib import Path

import fitz
from docx import Document
from backend import main


def index_document(pid, ocr=False):
    try:
        with main.db() as c:
            row = c.execute("SELECT * FROM papers WHERE id=?", (pid,)).fetchone()
            if not row:
                return
            c.execute(
                "UPDATE papers SET status='indexing', error=NULL WHERE id=?", (pid,)
            )
        pages = []
        if row["kind"] == "pdf":
            with fitz.open(main.paper_path(pid, "pdf")) as doc:
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
                        text = page.get_text(
                            textpage=page.get_textpage_ocr(language="eng")
                        )
                    pages.append(text)
        else:
            # A DOCX has no reliable page layout. Preserve paragraph sections instead.
            with zipfile.ZipFile(main.paper_path(pid, "docx")) as archive:
                if (
                    sum(item.file_size for item in archive.infolist())
                    > 150 * 1024 * 1024
                ):
                    raise ValueError("Expanded DOCX exceeds the 150 MB safety limit.")
            doc = Document(main.paper_path(pid, "docx"))
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
        with main.db() as c:
            if not c.execute("SELECT id FROM papers WHERE id=?", (pid,)).fetchone():
                return
            c.execute("DELETE FROM chunks WHERE paper_id=?", (pid,))
            for number, text in enumerate(pages, 1):
                words = text.split()
                for start in range(0, len(words), 180):
                    passage = " ".join(words[start : start + 230])
                    if len(passage) >= 30:
                        c.execute(
                            "INSERT INTO chunks(paper_id,page,text) VALUES(?,?,?)",
                            (pid, number, passage),
                        )
            c.execute(
                "UPDATE papers SET status='ready',pages=? WHERE id=?", (len(pages), pid)
            )
    except Exception as e:
        with main.db() as c:
            c.execute(
                "UPDATE papers SET status='failed',error=? WHERE id=?",
                (str(e)[:400], pid),
            )


if __name__ == "__main__":
    # Native parsers and OCR receive no network credentials and bounded resources.
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    main.DATA = Path(sys.argv[2])
    index_document(sys.argv[1], sys.argv[3] == "1")
