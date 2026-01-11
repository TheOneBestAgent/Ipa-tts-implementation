from core.chunking import chunk_text


def test_chunk_text_splits_long_sentence():
    text = "word " * 50
    chunks = chunk_text(text.strip(), target_chars=40, max_chars=50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 50 for chunk in chunks)


def test_chunk_text_keeps_sentence_boundaries_when_possible():
    sentence_a = "This is sentence one with enough words."
    sentence_b = "This is sentence two with enough words."
    text = f"{sentence_a} {sentence_b}"
    chunks = chunk_text(text, target_chars=30, max_chars=45)
    assert chunks == [sentence_a, sentence_b]
