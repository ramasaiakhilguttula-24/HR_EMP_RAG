"""Chunker tests: sizes, overlap continuity, metadata preservation."""
from backend.app.services.ingestion.chunker import chunk_pages
from backend.app.services.ingestion.parser import ParsedPage


def test_short_text_single_chunk():
    chunks = chunk_pages([ParsedPage(page_number=1, text="Hello world")])
    assert len(chunks) == 1 and chunks[0].text == "Hello world"
    assert chunks[0].chunk_index == 0 and chunks[0].page_number == 1


def test_long_text_splits_with_overlap():
    text = ("Annual leave policy. " * 300).strip()
    chunks = chunk_pages([ParsedPage(page_number=2, text=text)])
    assert len(chunks) > 1
    # overlap: end of chunk N shares text with start of chunk N+1
    assert chunks[0].text[-50:] in chunks[1].text
    assert all(c.page_number == 2 for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_no_content_loss():
    text = "\n\n".join(f"Paragraph {i} about leave benefits conduct." for i in range(50))
    chunks = chunk_pages([ParsedPage(page_number=1, text=text)])
    for i in range(50):
        assert any(f"Paragraph {i}" in c.text for c in chunks)


def test_markdown_heading_tracked():
    chunks = chunk_pages([ParsedPage(page_number=1, text="# Leave Policy\n\n18 days annual.")])
    assert chunks[0].section_heading == "Leave Policy"


def test_explicit_sizes_respected():
    text = "word " * 1000
    chunks = chunk_pages([ParsedPage(page_number=1, text=text)], chunk_size_tokens=100, overlap_tokens=10)
    assert all(len(c.text) <= 400 + 50 for c in chunks)  # 100 tokens ≈ 400 chars
