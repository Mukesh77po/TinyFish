"""Bid document text: PDF -> text (PyMuPDF) and cleanup of bilingual GeM documents.

    python -m api.documents bid.pdf      # print the cleaned text of a local PDF
"""
import re
import sys
from pathlib import Path

import pymupdf

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def pdf_to_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def clean_text(text: str) -> str:
    """Drop the Hindi half of bilingual labels ("ईएमड रािश/EMD Amount" -> "EMD Amount").

    GeM PDFs embed Devanagari with broken glyph maps, so it extracts as noise that costs tokens
    and confuses clause matching. English segments, numbers and bid numbers (GEM/2026/B/...) survive.
    """
    text = text.replace("\x00", "")  # Postgres TEXT rejects NUL bytes
    out = []
    for line in text.splitlines():
        if _DEVANAGARI.search(line):
            line = "/".join(p for p in line.split("/") if not _DEVANAGARI.search(p))
        line = re.sub(r"[ \t ]+", " ", line).strip()
        if line:
            out.append(line)
    return "\n".join(out)


def to_text(raw: str | bytes) -> str:
    """Whatever the fetcher handed us (text, or PDF bytes) -> cleaned text."""
    if isinstance(raw, bytes):
        raw = pdf_to_text(raw) if raw[:5] == b"%PDF-" else raw.decode("utf-8", "replace")
    return clean_text(raw)



def locate_clause(doc: str, clause: str) -> tuple[int, int] | None:
    """(start, end) of `clause` in `doc`, ignoring case and whitespace differences. None if absent."""
    if not doc or not clause:
        return None
    chars, index, prev_space = [], [], True
    for i, ch in enumerate(doc):
        if ch.isspace():
            if prev_space:
                continue
            chars.append(" ")
            prev_space = True
        else:
            chars.append(ch.lower())
            prev_space = False
        index.append(i)
    norm = "".join(chars)
    target = " ".join(clause.lower().split())
    for probe in (target, target[:60]):  # the model sometimes trims or joins the clause's tail
        j = norm.find(probe) if len(probe) >= 8 else -1
        if j >= 0:
            return index[j], index[j + len(probe) - 1] + 1
    return None


def excerpt(doc: str, clause: str, context: int = 280) -> dict | None:
    """Text around a clause, with the clause's offsets inside it, for highlighting in the UI."""
    span = locate_clause(doc, clause)
    if not span:
        return None
    a, b = max(0, span[0] - context), min(len(doc), span[1] + context)
    return {"text": doc[a:b], "highlight_start": span[0] - a, "highlight_end": span[1] - a,
            "prefix_truncated": a > 0, "suffix_truncated": b < len(doc)}


if __name__ == "__main__":
    print(to_text(Path(sys.argv[1]).read_bytes()))
