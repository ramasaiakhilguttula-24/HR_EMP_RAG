"""Chunk text: recursive character splitting, 512 tokens / 64 overlap.

Token→char approximation: ~4 chars per token (standard for English).
So CHUNK_SIZE=512 → 2048 chars, CHUNK_OVERLAP=64 → 256 chars.
Phase 2 adds semantic + parent-child variants; this stays the default.
"""
import re
from dataclasses import dataclass

from backend.app.core.config import get_settings
from backend.app.services.ingestion.parser import ParsedPage

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page_number: int
    section_heading: str | None = None


def _split_recursive(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text on the first separator that keeps pieces small, merging small pieces."""
    sep = next((s for s in _SEPARATORS if s == "" or s in text), "")
    parts = text.split(sep) if sep else list(text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        piece = part if not sep else part + sep
        if len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            if current.strip():
                chunks.append(current.strip())
            # overlap: carry tail of previous chunk
            current = (current[-overlap:] if overlap and current else "") + piece
            while len(current) > chunk_size:
                chunks.append(current[:chunk_size].strip())
                current = current[chunk_size - overlap :]
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def chunk_pages(
    pages: list[ParsedPage],
    chunk_size_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[TextChunk]:
    """Chunk parsed pages, preserving page_number and tracking md headings per chunk."""
    settings = get_settings()
    size = (chunk_size_tokens or settings.CHUNK_SIZE) * 4
    overlap = (overlap_tokens or settings.CHUNK_OVERLAP) * 4
    chunks: list[TextChunk] = []
    for page in pages:
        for piece in _split_recursive(page.text, size, overlap):
            heading = page.section_heading
            if heading is None:
                m = re.search(r"^#{1,6}\s+(.+)$", piece, re.MULTILINE)
                heading = m.group(1).strip() if m else None
            chunks.append(
                TextChunk(
                    text=piece,
                    chunk_index=len(chunks),
                    page_number=page.page_number,
                    section_heading=heading,
                )
            )
    return chunks
