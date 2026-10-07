from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, AppSettings, CurrentUser
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DB) -> User:
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: DB, settings: AppSettings) -> TokenOut:
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenOut(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
