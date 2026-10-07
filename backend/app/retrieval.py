from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.config import get_settings

# Permission check and similarity search in one statement: chunks from documents the user
# shares no role with are never read, so they cannot reach the LLM.
SEARCH_SQL = text(
    """
    SELECT c.document_id, d.title, c.chunk_index, c.content,
           c.embedding <=> :embedding AS distance
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE EXISTS (
        SELECT 1
        FROM document_roles dr
        JOIN user_roles ur ON ur.role_id = dr.role_id
        WHERE dr.document_id = c.document_id
          AND ur.user_id = :user_id
    )
    ORDER BY distance
    LIMIT :k
    """
).bindparams(bindparam("embedding", type_=Vector(get_settings().embedding_dim)))


@dataclass
class RetrievedChunk:
    document_id: int
    title: str
    chunk_index: int
    content: str
    similarity: float


def search(session: Session, user_id: int, embedding: list[float], k: int) -> list[RetrievedChunk]:
    # HNSW applies the WHERE clause after the index scan; without iterative scans a user who
    # can see few documents may get fewer than k rows, or none.
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    rows = session.execute(SEARCH_SQL, {"embedding": embedding, "user_id": user_id, "k": k})
    return [
        RetrievedChunk(
            document_id=r.document_id,
            title=r.title,
            chunk_index=r.chunk_index,
            content=r.content,
            similarity=1.0 - float(r.distance),
        )
        for r in rows
    ]
