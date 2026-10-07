import re

WORD = re.compile(r"\S+")


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into windows of `size` words, each sharing `overlap` words with the previous.

    Slices the original text so line breaks and tables survive.
    """
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    spans = [m.span() for m in WORD.finditer(text)]
    if not spans:
        return []
    chunks = []
    step = size - overlap
    for start in range(0, len(spans), step):
        window = spans[start : start + size]
        chunks.append(text[window[0][0] : window[-1][1]])
        if start + size >= len(spans):
            break
    return chunks
