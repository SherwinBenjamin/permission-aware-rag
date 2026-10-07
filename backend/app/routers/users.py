from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, AdminUser
from app.models import Role, User
from app.roles import load_roles
from app.schemas import RoleIdsIn, RoleIn, RoleOut, UserOut

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DB) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)))


@router.put("/users/{user_id}/roles", response_model=UserOut)
def set_user_roles(user_id: int, body: RoleIdsIn, _: AdminUser, db: DB) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.roles = load_roles(db, body.role_ids)
    db.commit()
    return user


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: AdminUser, db: DB) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)))


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleIn, _: AdminUser, db: DB) -> Role:
    role = Role(name=body.name)
    db.add(role)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Role already exists") from None
    return role
