from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.providers import LLM, Embedder, make_embedder, make_llm
from app.security import decode_access_token
from app.storage import Storage, make_storage

DB = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_embedder(settings: AppSettings) -> Embedder:
    return make_embedder(settings)


def get_llm(settings: AppSettings) -> LLM:
    return make_llm(settings)


def get_storage(settings: AppSettings) -> Storage:
    return make_storage(settings)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DB, settings: AppSettings, authorization: Annotated[str | None, Header()] = None
) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    try:
        user_id = decode_access_token(token, settings)
    except jwt.InvalidTokenError:
        raise _unauthorized() from None
    # Roles are always loaded from the database, never from the token or request.
    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
