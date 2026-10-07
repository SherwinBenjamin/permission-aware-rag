from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, AdminUser
from app.models import Document, QueryLog
from app.schemas import LogOut, LogPage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/logs", response_model=LogPage)
def list_logs(
    _: AdminUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: int | None = None,
) -> LogPage:
    query = select(QueryLog)
    if user_id is not None:
        query = query.where(QueryLog.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    logs = list(
        db.scalars(
            query.options(selectinload(QueryLog.user))
            .order_by(QueryLog.created_at.desc(), QueryLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    doc_ids = {d for log in logs for d in log.retrieved_document_ids}
    rows = db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
    titles = {doc_id: title for doc_id, title in rows}
    return LogPage(
        total=total or 0,
        items=[
            LogOut(
                id=log.id,
                user_id=log.user_id,
                user_email=log.user.email if log.user else None,
                question=log.question,
                retrieved_document_ids=log.retrieved_document_ids,
                retrieved_titles=[
                    titles.get(d, f"(deleted #{d})") for d in log.retrieved_document_ids
                ],
                refused=log.refused,
                created_at=log.created_at,
            )
            for log in logs
        ],
    )
