from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import Settings

_hasher = PasswordHasher()
# Verified when the email is unknown so login timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        valid = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return valid and password_hash is not None


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    """Return the user id, raising jwt.InvalidTokenError on a bad signature or expiry."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "iat"]},
    )
    try:
        return int(payload["sub"])
    except ValueError as exc:
        raise jwt.InvalidTokenError("invalid subject") from exc
