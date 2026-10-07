from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text

from app.models import Chunk, Document, QueryLog, Role, User
from app.providers import ExtractiveLLM
from app.rag import answer_question
from app.retrieval import SEARCH_SQL, search

SALARY_QUESTION = "What are the salary bands for senior engineers?"
LEAVE_QUESTION = "How many days of annual leave do I get?"


def ask(db, user, question, embedder, settings):
    return answer_question(
        db, user, question, embedder=embedder, llm=ExtractiveLLM(), settings=settings
    )


def retrieve_all(db, user, question, embedder, k=100):
    [embedding] = embedder.embed([question])
    return search(db, user.id, embedding, k)


def test_non_hr_user_never_retrieves_hr_document(db, org, embedder, settings):
    chunks = retrieve_all(db, org.engineer, SALARY_QUESTION, embedder)
    assert chunks, "engineer should still see their own documents"
    assert org.salaries.id not in {c.document_id for c in chunks}

    result = ask(db, org.engineer, SALARY_QUESTION, embedder, settings)
    assert org.salaries.id not in {s.document_id for s in result.sources}
    assert "8,000,000" not in result.answer


def test_hr_user_retrieves_salary_document(db, org, embedder, settings):
    result = ask(db, org.hr, SALARY_QUESTION, embedder, settings)
    assert not result.refused
    assert result.sources[0].title == "Salary bands 2026"
    assert "8,000,000" in result.answer


def test_both_roles_can_ask_about_leave(db, org, embedder, settings):
    for user in (org.engineer, org.hr):
        result = ask(db, user, LEAVE_QUESTION, embedder, settings)
        assert not result.refused
        assert {s.title for s in result.sources} == {"Employee handbook"}


def test_removing_role_from_user_blocks_next_question(db, org, embedder, settings):
    assert not ask(db, org.hr, SALARY_QUESTION, embedder, settings).refused

    org.hr.roles = [r for r in org.hr.roles if r.name != "hr"]
    db.commit()

    result = ask(db, org.hr, SALARY_QUESTION, embedder, settings)
    assert org.salaries.id not in {s.document_id for s in result.sources}
    assert org.salaries.id not in {
        c.document_id for c in retrieve_all(db, org.hr, SALARY_QUESTION, embedder)
    }


def test_removing_role_from_document_blocks_next_question(db, org, embedder, settings):
    org.salaries.roles = []
    db.commit()

    result = ask(db, org.hr, SALARY_QUESTION, embedder, settings)
    assert org.salaries.id not in {s.document_id for s in result.sources}


def test_user_with_no_roles_retrieves_nothing(db, org, embedder, settings):
    for question in (SALARY_QUESTION, LEAVE_QUESTION, "on-call rotation"):
        assert retrieve_all(db, org.nobody, question, embedder) == []
    assert ask(db, org.nobody, LEAVE_QUESTION, embedder, settings).refused


def test_admin_flag_does_not_grant_document_access(db, org, embedder):
    assert retrieve_all(db, org.admin, SALARY_QUESTION, embedder) == []


def test_question_is_logged_with_retrieved_documents(db, org, embedder, settings):
    ask(db, org.hr, SALARY_QUESTION, embedder, settings)
    log = db.query(QueryLog).one()
    assert log.user_id == org.hr.id
    assert log.question == SALARY_QUESTION
    assert org.salaries.id in log.retrieved_document_ids


def _crowded_index(db, embedder):
    """A big document most users can't see, plus a small one only `lonely` can see."""
    crowd, lonely_role = Role(name="crowd"), Role(name="lonely")
    lonely = User(email="lonely@example.com", password_hash="x", roles=[lonely_role])
    texts = [f"database failover replica promote lag runbook step {i}" for i in range(400)]
    big = Document(title="Big", filename="big.md", s3_key="k1", roles=[crowd])
    big.chunks = [
        Chunk(chunk_index=i, content=t, embedding=e)
        for i, (t, e) in enumerate(zip(texts, embedder.embed(texts), strict=True))
    ]
    small_texts = ["notes on database ownership", "who owns the database budget"]
    small = Document(title="Small", filename="small.md", s3_key="k2", roles=[lonely_role])
    small.chunks = [
        Chunk(chunk_index=i, content=t, embedding=e)
        for i, (t, e) in enumerate(zip(small_texts, embedder.embed(small_texts), strict=True))
    ]
    db.add_all([lonely, big, small])
    db.commit()
    db.execute(text("ANALYZE chunks"))
    return lonely, small


def force_index_scan(db):
    # The planner prefers filter-then-sort on tables this small; production-sized tables
    # pick the HNSW scan, so force it to reproduce that plan.
    db.execute(text("SET LOCAL enable_seqscan = off"))
    db.execute(text("SET LOCAL enable_sort = off"))


def test_filtered_hnsw_search_still_finds_permitted_chunks(db, embedder):
    lonely, small = _crowded_index(db, embedder)
    [embedding] = embedder.embed(["database failover replica promote"])

    force_index_scan(db)
    explain = text("EXPLAIN " + SEARCH_SQL.text).bindparams(
        bindparam("embedding", type_=Vector(len(embedding)))
    )
    plan = db.execute(explain, {"embedding": embedding, "user_id": lonely.id, "k": 5}).scalars()
    assert "ix_chunks_embedding_hnsw" in "\n".join(plan), "test must exercise the HNSW index"

    results = search(db, lonely.id, embedding, 5)
    assert {c.document_id for c in results} == {small.id}
    assert len(results) == 2


def test_without_iterative_scan_filtered_hnsw_loses_rows(db, embedder):
    """Documents the problem the iterative scan setting in search() fixes."""
    lonely, _ = _crowded_index(db, embedder)
    [embedding] = embedder.embed(["database failover replica promote"])

    force_index_scan(db)
    db.execute(text("SET LOCAL hnsw.iterative_scan = off"))
    rows = db.execute(SEARCH_SQL, {"embedding": embedding, "user_id": lonely.id, "k": 5}).all()
    assert len(rows) < 2
