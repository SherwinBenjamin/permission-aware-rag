import re
import uuid

from sqlalchemy.orm import Session

from app.chunking import chunk_text
from app.config import Settings
from app.extract import UnsupportedFile, extract_text
from app.models import Chunk, Document, Role
from app.providers import Embedder
from app.storage import Storage

EMBED_BATCH = 64


def safe_filename(filename: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    return name.strip("._") or "file"


def ingest_document(
    session: Session,
    *,
    title: str,
    filename: str,
    data: bytes,
    roles: list[Role],
    uploaded_by: int | None,
    embedder: Embedder,
    storage: Storage,
    settings: Settings,
) -> Document:
    text = extract_text(filename, data)
    pieces = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not pieces:
        raise UnsupportedFile("no extractable text")

    embeddings: list[list[float]] = []
    for i in range(0, len(pieces), EMBED_BATCH):
        embeddings.extend(embedder.embed(pieces[i : i + EMBED_BATCH]))

    key = f"documents/{uuid.uuid4().hex}/{safe_filename(filename)}"
    storage.put(key, data)
    try:
        doc = Document(
            title=title,
            filename=filename,
            s3_key=key,
            uploaded_by=uploaded_by,
            roles=list(roles),
            chunks=[
                Chunk(chunk_index=i, content=piece, embedding=emb)
                for i, (piece, emb) in enumerate(zip(pieces, embeddings, strict=True))
            ],
        )
        session.add(doc)
        session.commit()
    except Exception:
        session.rollback()
        storage.delete(key)
        raise
    return doc
