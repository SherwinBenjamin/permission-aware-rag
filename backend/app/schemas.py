from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleOut(ORM):
    id: int
    name: str


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")


class UserOut(ORM):
    id: int
    email: str
    is_admin: bool
    roles: list[RoleOut]


class RoleIdsIn(BaseModel):
    role_ids: list[int]


class DocumentOut(ORM):
    id: int
    title: str
    filename: str
    created_at: datetime
    roles: list[RoleOut]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SourceOut(BaseModel):
    id: int
    document_id: int
    title: str
    chunk_index: int
    similarity: float


class AskOut(BaseModel):
    answer: str
    refused: bool
    sources: list[SourceOut]


class LogOut(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None
    question: str
    retrieved_document_ids: list[int]
    retrieved_titles: list[str]
    refused: bool
    created_at: datetime


class LogPage(BaseModel):
    total: int
    items: list[LogOut]
