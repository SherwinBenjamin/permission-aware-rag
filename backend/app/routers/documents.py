from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.deps import DB, AdminUser, AppSettings, CurrentUser, get_embedder, get_storage
from app.extract import ALLOWED_EXTENSIONS, UnsupportedFile, extension
from app.ingest import ingest_document
from app.models import Document, User, document_roles, user_roles
from app.providers import Embedder
from app.roles import load_roles
from app.schemas import DocumentOut, RoleIdsIn
from app.storage import Storage

router = APIRouter(prefix="/documents", tags=["documents"])


def visible_to(user: User):
    return exists(
        select(1)
        .select_from(
            document_roles.join(user_roles, user_roles.c.role_id == document_roles.c.role_id)
        )
        .where(document_roles.c.document_id == Document.id, user_roles.c.user_id == user.id)
    )


def get_visible_document(db: Session, user: User, document_id: int) -> Document:
    query = select(Document).where(Document.id == document_id)
    if not user.is_admin:
        query = query.where(visible_to(user))
    doc = db.scalar(query)
    # 404 rather than 403 so users cannot probe which documents exist.
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(user: CurrentUser, db: DB) -> list[Document]:
    query = select(Document).order_by(Document.created_at.desc())
    if not user.is_admin:
        query = query.where(visible_to(user))
    return list(db.scalars(query))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, user: CurrentUser, db: DB) -> Document:
    return get_visible_document(db, user, document_id)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    admin: AdminUser,
    db: DB,
    settings: AppSettings,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    storage: Annotated[Storage, Depends(get_storage)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=255)] = None,
    role_ids: Annotated[list[int] | None, Form()] = None,
) -> Document:
    filename = file.filename or "upload"
    if extension(filename) not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    roles = load_roles(db, role_ids or [])
    try:
        return ingest_document(
            db,
            title=(title or "").strip() or filename,
            filename=filename,
            data=data,
            roles=roles,
            uploaded_by=admin.id,
            embedder=embedder,
            storage=storage,
            settings=settings,
        )
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@router.patch("/{document_id}/roles", response_model=DocumentOut)
def set_document_roles(document_id: int, body: RoleIdsIn, _: AdminUser, db: DB) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    doc.roles = load_roles(db, body.role_ids)
    db.commit()
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    _: AdminUser,
    db: DB,
    storage: Annotated[Storage, Depends(get_storage)],
) -> Response:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    key = doc.s3_key
    db.delete(doc)
    db.commit()
    storage.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
