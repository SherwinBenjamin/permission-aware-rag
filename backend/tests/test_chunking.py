import pytest

from app.chunking import chunk_text


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_chunk_sizes_and_overlap():
    chunks = chunk_text(words(100), size=30, overlap=10)
    sizes = [len(c.split()) for c in chunks]
    assert sizes == [30, 30, 30, 30, 20]
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert prev.split()[-10:] == nxt.split()[:10]
    assert chunks[0].split()[0] == "w0"
    assert chunks[-1].split()[-1] == "w99"


def test_every_word_is_covered():
    text = words(257)
    covered = {w for c in chunk_text(text, size=40, overlap=8) for w in c.split()}
    assert covered == set(text.split())


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t"])
def test_empty_input_gives_no_chunks(text):
    assert chunk_text(text, size=10, overlap=2) == []


def test_short_input_gives_single_chunk():
    assert chunk_text("just three words", size=50, overlap=10) == ["just three words"]


def test_exact_size_gives_single_chunk():
    assert len(chunk_text(words(30), size=30, overlap=10)) == 1


def test_preserves_original_formatting():
    text = "| a | b |\n| --- | --- |\n| 1 | 2 |"
    assert chunk_text(text, size=100, overlap=0) == [text]


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_rejects_invalid_parameters(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", size=size, overlap=overlap)
