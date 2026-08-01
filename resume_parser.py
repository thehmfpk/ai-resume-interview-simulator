"""
resume_parser.py
-----------------
Extracts and cleans raw text from an uploaded resume (PDF). Uses pdfplumber
as the primary engine (better layout handling) and falls back to PyPDF2 if
pdfplumber fails on an unusual PDF.
"""

import re
import io

import pdfplumber
from PyPDF2 import PdfReader

ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_with_pdfplumber(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _extract_with_pypdf2(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(text_parts)


def extract_resume_text(file_bytes: bytes) -> str:
    """Returns cleaned resume text, or raises ValueError if nothing could
    be extracted (e.g. a purely scanned/image-based PDF)."""
    text = ""
    try:
        text = _extract_with_pdfplumber(file_bytes)
    except Exception:
        text = ""

    if not text or len(text.strip()) < 30:
        try:
            text = _extract_with_pypdf2(file_bytes)
        except Exception:
            text = ""

    text = _clean_text(text)

    if len(text) < 30:
        raise ValueError(
            "Could not extract readable text from this PDF. "
            "Please upload a text-based resume (not a scanned image)."
        )
    return text
