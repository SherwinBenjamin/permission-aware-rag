from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role


def load_roles(db: Session, role_ids: list[int]) -> list[Role]:
    wanted = set(role_ids)
    roles = list(db.scalars(select(Role).where(Role.id.in_(wanted)))) if wanted else []
    missing = wanted - {r.id for r in roles}
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role ids: {sorted(missing)}")
    return roles
