from rag.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []


def test_short_text_returns_single_chunk():
    assert chunk_text("Hello world.", chunk_size=800) == ["Hello world."]


def test_long_text_is_split_into_multiple_chunks():
    text = ("This is a sentence. " * 200).strip()
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 550 for c in chunks)  # allow small overlap slack


def test_no_content_lost_across_chunks():
    text = "Paragraph one.\n\n" + ("word " * 300)
    chunks = chunk_text(text, chunk_size=400, overlap=40)
    rejoined_word_count = sum(c.count("word") for c in chunks)
    assert rejoined_word_count >= 300  # overlap may double-count some, never lose
