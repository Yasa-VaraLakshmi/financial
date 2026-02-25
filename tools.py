import os
from typing import List

from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()


def extract_pdf_text(path: str) -> str:
    """Extract and normalize text from a PDF path."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"PDF file not found: {path}")

    reader = PdfReader(path)
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = " ".join(text.split())
        if text:
            pages.append(text)

    if not pages:
        raise ValueError("The uploaded PDF has no extractable text.")

    return "\n".join(pages)


def build_document_excerpt(path: str, max_chars: int = 15000) -> str:
    """Return a bounded excerpt to keep token usage predictable."""
    text = extract_pdf_text(path)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[TRUNCATED]"
