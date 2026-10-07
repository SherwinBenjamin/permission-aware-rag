import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker, init_db
from app.ingest import ingest_document
from app.models import Document, Role, User
from app.providers import make_embedder, make_llm
from app.rag import answer_question
from app.retrieval import search
from app.security import hash_password
from app.storage import make_storage

DEMO_ROLES = ["all-staff", "engineering", "hr"]
DEMO_USERS = [
    ("admin@example.com", True, DEMO_ROLES),
    ("alice@example.com", False, ["all-staff", "engineering"]),
    ("hannah@example.com", False, ["all-staff", "hr"]),
    ("newbie@example.com", False, []),
]


def sample_docs_dir() -> Path:
    for candidate in (os.environ.get("SAMPLE_DOCS_DIR"), "sample_docs", "../sample_docs"):
        if candidate and Path(candidate, "manifest.json").exists():
            return Path(candidate)
    sys.exit("sample_docs/manifest.json not found; set SAMPLE_DOCS_DIR")


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def find_user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None:
        sys.exit(f"no user {email}")
    return user


def upsert_user(db: Session, email: str, password: str, is_admin: bool, roles: list[str]) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None:
        user = User(email=email.lower(), password_hash=hash_password(password))
        db.add(user)
    user.is_admin = is_admin
    user.roles = [get_or_create_role(db, r) for r in roles]
    return user


def ingest_file(db: Session, path: Path, title: str, role_names: list[str]) -> Document:
    settings = get_settings()
    doc = ingest_document(
        db,
        title=title,
        filename=path.name,
        data=path.read_bytes(),
        roles=[get_or_create_role(db, r) for r in role_names],
        uploaded_by=None,
        embedder=make_embedder(settings),
        storage=make_storage(settings),
        settings=settings,
    )
    print(f"ingested {title!r}: {len(doc.chunks)} chunks, roles={role_names}")
    return doc


def cmd_create_admin(db: Session, args: argparse.Namespace) -> None:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 8:
        sys.exit("password must be at least 8 characters")
    upsert_user(db, args.email, password, True, args.roles)
    db.commit()
    print(f"admin {args.email} ready")


def cmd_ingest(db: Session, args: argparse.Namespace) -> None:
    path = Path(args.path)
    ingest_file(db, path, args.title or path.stem, args.roles)


def cmd_seed_demo(db: Session, args: argparse.Namespace) -> None:
    if db.scalar(select(func.count()).select_from(User)):
        print("database already has users; skipping demo seed")
        return
    for role in DEMO_ROLES:
        get_or_create_role(db, role)
    for email, is_admin, roles in DEMO_USERS:
        upsert_user(db, email, args.password, is_admin, roles)
    db.commit()
    directory = sample_docs_dir()
    for entry in json.loads((directory / "manifest.json").read_text()):
        ingest_file(db, directory / entry["file"], entry["title"], entry["roles"])
    print("demo users:", ", ".join(email for email, *_ in DEMO_USERS))


def cmd_ask(db: Session, args: argparse.Namespace) -> None:
    settings = get_settings()
    result = answer_question(
        db,
        find_user(db, args.user),
        args.question,
        embedder=make_embedder(settings),
        llm=make_llm(settings),
        settings=settings,
    )
    print(result.answer)
    for s in result.sources:
        print(f"  [{s.id}] {s.title} (chunk {s.chunk_index}, similarity {s.similarity:.3f})")


def cmd_eval(db: Session, args: argparse.Namespace) -> None:
    """Report retrieval hit rates, and the similarity gap the refusal threshold must sit in.

    Cases with "expected": null are off-topic and should be refused.
    """
    settings = get_settings()
    embedder = make_embedder(settings)
    user = find_user(db, args.user)
    cases = json.loads(Path(args.file).read_text())
    answerable = [c for c in cases if c["expected"]]
    top1 = hits = 0
    relevant_best, off_topic_best = [], []
    for case in cases:
        [embedding] = embedder.embed([case["question"]])
        results = search(db, user.id, embedding, settings.top_k)
        titles = [c.title for c in results]
        best = results[0].similarity if results else 0.0
        if case["expected"] is None:
            off_topic_best.append(best)
            hit = best < settings.threshold
        else:
            relevant_best.append(best)
            hit = case["expected"] in titles
            hits += hit
            top1 += bool(titles) and titles[0] == case["expected"]
        if args.verbose or not hit:
            mark = "ok  " if hit else "MISS"
            print(f"{mark} {best:.3f} {case['question']!r} -> {titles[:3]}")
    n = len(answerable)
    print(
        f"hit@1: {top1}/{n}  hit@{settings.top_k}: {hits}/{n}  "
        f"chunk_size={settings.chunk_size} overlap={settings.chunk_overlap} "
        f"embedder={settings.embedding_provider}"
    )
    if relevant_best and off_topic_best:
        print(
            f"lowest relevant best-match: {min(relevant_best):.3f}  "
            f"highest off-topic best-match: {max(off_topic_best):.3f}  "
            f"threshold: {settings.threshold:.3f}"
        )


def roles_arg(value: str) -> list[str]:
    return [r.strip() for r in value.split(",") if r.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    p = sub.add_parser("create-admin", help="password from $ADMIN_PASSWORD or prompt")
    p.add_argument("email")
    p.add_argument("--roles", type=roles_arg, default=[])
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("ingest")
    p.add_argument("path")
    p.add_argument("--roles", type=roles_arg, required=True, help="comma-separated role names")
    p.add_argument("--title")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("seed-demo", help="demo roles, users and sample documents")
    p.add_argument("--password", default=os.environ.get("DEMO_PASSWORD", "demo-password"))
    p.set_defaults(func=cmd_seed_demo)

    p = sub.add_parser("ask")
    p.add_argument("question")
    p.add_argument("--user", required=True, help="answer with this user's permissions")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("eval")
    p.add_argument("--user", default="admin@example.com")
    p.add_argument("--file", default="eval/questions.json")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    init_db()
    if args.command == "init-db":
        print("database ready")
        return
    with get_sessionmaker()() as db:
        args.func(db, args)


if __name__ == "__main__":
    main()
