"""Create original demonstration notes, explicitly labeled as non-research."""

from pathlib import Path
import fitz

root = Path(__file__).resolve().parents[1]
doc = fitz.open()
pages = [
    (
        "Reading research papers",
        """These demonstration notes were written for the TracePaper sample library. They are not published research and should not be cited as scientific evidence.

A useful first reading pass separates a paper's central question, method, findings, and limitations. Record these elements independently before comparing papers.

Inspect whether reported findings support the stated conclusions. Identify the evaluation dataset, baselines, assumptions, and limitations. A passage containing a keyword may be relevant without answering the reader's question.

Keeping a page reference next to a note makes it easier to return to the original context and check whether a summary omits an important qualification.""",
    ),
    (
        "Keeping citations honest",
        """Citation validity and citation correctness are different checks. A valid reference points to an existing source. A correct supporting citation contains evidence for the specific claim it accompanies.

Citation coverage measures how many claims carry a reference. Coverage alone does not establish that the referenced passages support the claims. Evaluate support separately by reading each claim together with its cited passage.

When the source collection does not support an answer, an explicit statement of insufficient evidence is preferable to an unsupported conclusion. Absence from a small collection does not prove a claim false.

For PDF documents, use the physical page number in the uploaded file. For DOCX documents, use explicit section references because page layout can change between applications.""",
    ),
    (
        "Evaluating retrieval",
        """A retrieval evaluation needs representative questions and labeled relevant passages. Recall at k measures the proportion of known relevant passages found in the top k results. Reciprocal rank records how early the first relevant result appears.

BM25 is a lexical ranking method using query term frequency and collection statistics. Stemming can match inflected words. Lexical retrieval may miss a relevant passage that uses different terminology. Semantic retrieval can be evaluated separately.

Report evaluation dataset size and provenance with scores. Synthetic fixtures test implementation mechanics but do not establish performance on diverse research libraries.

Measure response latency separately from quality. Token cost estimates depend on the provider, model, and pricing. Indexing, OCR, and storage are separate expenses.""",
    ),
]
for title, text in pages:
    p = doc.new_page(width=595, height=842)
    p.insert_text((54, 60), "TRACEPAPER / ORIGINAL DEMONSTRATION NOTES", fontsize=9)
    p.insert_text((54, 112), title, fontsize=24, fontname="tiro")
    p.insert_textbox(
        fitz.Rect(54, 155, 541, 755), text, fontsize=12, fontname="tiro", lineheight=1.6
    )
    p.insert_text((54, 795), f"Not published research / Page {len(doc)}", fontsize=9)
doc.save(root / "examples" / "tracepaper-field-notes.pdf")

from docx import Document

word = Document()
word.add_heading("TracePaper demonstration notes", 0)
word.add_paragraph("Original demonstration material, not published research.")
for title, text in pages:
    word.add_heading(title, 1)
    for paragraph in text.split("\n\n"):
        word.add_paragraph(paragraph)
word.save(root / "examples" / "tracepaper-field-notes.docx")
