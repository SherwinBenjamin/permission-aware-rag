import io
from pathlib import PurePath

from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


class UnsupportedFile(ValueError):
    pass


def extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def extract_text(filename: str, data: bytes) -> str:
    ext = extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFile(f"unsupported file type: {ext or 'none'}")
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise UnsupportedFile("could not read PDF") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFile("text files must be UTF-8") from exc
