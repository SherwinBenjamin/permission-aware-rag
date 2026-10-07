import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag_test"
)
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-bytes-long"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LLM_PROVIDER"] = "extractive"
os.environ["EMBEDDING_DIM"] = "768"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, make_url, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, get_sessionmaker, init_db  # noqa: E402
from app.deps import get_storage  # noqa: E402
from app.ingest import ingest_document  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Document, Role, User  # noqa: E402
from app.providers import HashEmbedder  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402
from app.storage import LocalStorage  # noqa: E402

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "sample_docs"
PASSWORD = "correct-horse-battery"


def ensure_database(url: str) -> None:
    target = make_url(url)
    engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        found = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        )
        if not found:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    ensure_database(os.environ["DATABASE_URL"])
    engine = get_engine()
    Base.metadata.drop_all(engine)
    init_db(engine)
    yield engine


@pytest.fixture(autouse=True)
def clean_tables(database):
    yield
    with database.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Session:
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def embedder(settings):
    return HashEmbedder(settings.embedding_dim)


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(str(tmp_path / "storage"))


@pytest.fixture
def client(storage):
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class Org:
    """The spec's example: three roles, three documents, an engineer and an HR user."""

    def __init__(self, db: Session, embedder, storage, settings):
        self.db = db
        self.roles = {name: Role(name=name) for name in ("all-staff", "engineering", "hr")}
        db.add_all(self.roles.values())
        self.engineer = self.user("eng@example.com", ["all-staff", "engineering"])
        self.hr = self.user("hr@example.com", ["all-staff", "hr"])
        self.nobody = self.user("nobody@example.com", [])
        self.admin = self.user("admin@example.com", [], is_admin=True)
        db.commit()

        def ingest(filename: str, title: str, roles: list[str]) -> Document:
            return ingest_document(
                db,
                title=title,
                filename=filename,
                data=(SAMPLE_DOCS / filename).read_bytes(),
                roles=[self.roles[r] for r in roles],
                uploaded_by=self.admin.id,
                embedder=embedder,
                storage=storage,
                settings=settings,
            )

        self.handbook = ingest(
            "employee_handbook.md", "Employee handbook", ["all-staff", "engineering", "hr"]
        )
        self.runbook = ingest("oncall_runbook.md", "On-call runbook", ["engineering"])
        self.salaries = ingest("salary_bands_2026.md", "Salary bands 2026", ["hr"])

    def user(self, email: str, roles: list[str], is_admin: bool = False) -> User:
        user = User(
            email=email,
            password_hash=hash_password(PASSWORD),
            is_admin=is_admin,
            roles=[self.roles[r] for r in roles],
        )
        self.db.add(user)
        return user


@pytest.fixture
def org(db, embedder, storage, settings) -> Org:
    return Org(db, embedder, storage, settings)


@pytest.fixture
def auth(settings):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}

    return headers
