from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.models import Chunk, Document
from tests.conftest import PASSWORD, SAMPLE_DOCS

SALARY_QUESTION = "What are the salary bands for senior engineers?"

ADMIN_ENDPOINTS = [
    ("post", "/documents", {"files": {"file": ("a.md", b"hello")}}),
    ("patch", "/documents/1/roles", {"json": {"role_ids": []}}),
    ("delete", "/documents/1", {}),
    ("put", "/users/1/roles", {"json": {"role_ids": []}}),
    ("get", "/users", {}),
    ("get", "/roles", {}),
    ("post", "/roles", {"json": {"name": "x"}}),
    ("get", "/admin/logs", {}),
]


def login(client, email, password=PASSWORD):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_register_login_me(client):
    resp = client.post("/auth/register", json={"email": "New@Example.com", "password": PASSWORD})
    assert resp.status_code == 201
    assert resp.json()["roles"] == []
    assert "password" not in resp.text

    me = client.get("/me", headers=login(client, "new@example.com")).json()
    assert me["email"] == "new@example.com"
    assert me["roles"] == [] and me["is_admin"] is False


def test_register_rejects_duplicates_and_short_passwords(client):
    body = {"email": "a@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409
    short = {"email": "b@example.com", "password": "short"}
    assert client.post("/auth/register", json=short).status_code == 422


def test_login_rejects_bad_credentials(client, org):
    for email, password in [("hr@example.com", "wrong-password"), ("ghost@example.com", PASSWORD)]:
        resp = client.post("/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 401


def test_password_is_hashed(org):
    assert org.hr.password_hash.startswith("$argon2")
    assert PASSWORD not in org.hr.password_hash


@pytest.mark.parametrize(("method", "path", "kwargs"), ADMIN_ENDPOINTS)
def test_non_admin_gets_403_on_admin_endpoints(client, org, auth, method, path, kwargs):
    resp = getattr(client, method)(path, headers=auth(org.hr), **kwargs)
    assert resp.status_code == 403


@pytest.mark.parametrize(("method", "path", "kwargs"), ADMIN_ENDPOINTS)
def test_unauthenticated_gets_401_on_admin_endpoints(client, method, path, kwargs):
    assert getattr(client, method)(path, **kwargs).status_code == 401


def make_token(settings, sub, *, minutes=5, secret=None):
    now = datetime.now(UTC)
    payload = {"sub": str(sub), "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm="HS256")


@pytest.mark.parametrize("case", ["missing", "malformed", "expired", "tampered", "wrong_key"])
def test_bad_tokens_get_401(client, org, settings, case):
    good = make_token(settings, org.hr.id)
    header, payload, signature = good.split(".")
    tokens = {
        "missing": None,
        "malformed": "not-a-jwt",
        "expired": make_token(settings, org.hr.id, minutes=-1),
        "tampered": f"{header}.{make_token(settings, org.admin.id).split('.')[1]}.{signature}",
        "wrong_key": make_token(
            settings, org.hr.id, secret="attacker-secret-key-0123456789-abcdef"
        ),
    }
    headers = {"Authorization": f"Bearer {tokens[case]}"} if tokens[case] else {}
    for method, path in [("GET", "/me"), ("POST", "/ask"), ("GET", "/documents")]:
        resp = client.request(method, path, headers=headers, json={"question": "hi"})
        assert resp.status_code == 401, (case, path)


def test_token_for_deleted_user_gets_401(client, org, db, auth):
    headers = auth(org.engineer)
    db.delete(org.engineer)
    db.commit()
    assert client.get("/me", headers=headers).status_code == 401


def test_documents_list_only_visible(client, org, auth):
    titles = {d["title"] for d in client.get("/documents", headers=auth(org.engineer)).json()}
    assert titles == {"Employee handbook", "On-call runbook"}
    admin_titles = {d["title"] for d in client.get("/documents", headers=auth(org.admin)).json()}
    assert "Salary bands 2026" in admin_titles


def test_invisible_document_returns_404(client, org, auth):
    assert (
        client.get(f"/documents/{org.salaries.id}", headers=auth(org.engineer)).status_code == 404
    )
    assert client.get("/documents/9999", headers=auth(org.engineer)).status_code == 404
    assert client.get(f"/documents/{org.salaries.id}", headers=auth(org.hr)).status_code == 200


def test_ask_returns_answer_with_sources(client, org, auth):
    body = client.post("/ask", json={"question": SALARY_QUESTION}, headers=auth(org.hr)).json()
    assert body["refused"] is False
    assert body["sources"][0]["title"] == "Salary bands 2026"
    assert {"id", "document_id", "chunk_index", "similarity"} <= body["sources"][0].keys()


def test_roles_in_request_body_are_ignored(client, org, auth):
    body = client.post(
        "/ask",
        json={"question": SALARY_QUESTION, "roles": ["hr"], "role_ids": [3]},
        headers=auth(org.engineer),
    ).json()
    assert "Salary bands 2026" not in {s["title"] for s in body["sources"]}


def test_revoking_user_role_via_api_applies_on_next_question(client, org, auth):
    ask = lambda: client.post("/ask", json={"question": SALARY_QUESTION}, headers=auth(org.hr))  # noqa: E731
    assert "Salary bands 2026" in {s["title"] for s in ask().json()["sources"]}

    keep = [org.roles["all-staff"].id]
    resp = client.put(f"/users/{org.hr.id}/roles", json={"role_ids": keep}, headers=auth(org.admin))
    assert resp.status_code == 200

    assert "Salary bands 2026" not in {s["title"] for s in ask().json()["sources"]}


def test_revoking_document_role_via_api(client, org, auth):
    resp = client.patch(
        f"/documents/{org.salaries.id}/roles", json={"role_ids": []}, headers=auth(org.admin)
    )
    assert resp.status_code == 200 and resp.json()["roles"] == []
    body = client.post("/ask", json={"question": SALARY_QUESTION}, headers=auth(org.hr)).json()
    assert "Salary bands 2026" not in {s["title"] for s in body["sources"]}


def test_unknown_role_ids_are_rejected(client, org, auth):
    resp = client.put(
        f"/users/{org.hr.id}/roles", json={"role_ids": [999]}, headers=auth(org.admin)
    )
    assert resp.status_code == 400


def test_admin_upload_and_ask(client, org, auth, storage):
    data = (SAMPLE_DOCS / "expense_policy.md").read_bytes()
    resp = client.post(
        "/documents",
        files={"file": ("expense_policy.md", data, "text/markdown")},
        data={"title": "Expense policy", "role_ids": [str(org.roles["all-staff"].id)]},
        headers=auth(org.admin),
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert [r["name"] for r in doc["roles"]] == ["all-staff"]

    body = client.post(
        "/ask",
        json={"question": "What is the hotel cap per night in Tokyo?"},
        headers=auth(org.engineer),
    ).json()
    assert body["sources"][0]["title"] == "Expense policy"


def test_upload_rejects_wrong_type_and_large_files(client, org, auth, settings):
    headers = auth(org.admin)
    resp = client.post("/documents", files={"file": ("x.exe", b"MZ")}, headers=headers)
    assert resp.status_code == 415
    big = b"a " * (settings.max_upload_bytes // 2 + 1)
    resp = client.post("/documents", files={"file": ("big.txt", big)}, headers=headers)
    assert resp.status_code == 413
    resp = client.post("/documents", files={"file": ("empty.txt", b"   ")}, headers=headers)
    assert resp.status_code == 400


def test_delete_removes_document_chunks_and_file(client, org, auth, db, storage):
    doc_id, key = org.runbook.id, org.runbook.s3_key
    assert storage.get(key)
    resp = client.delete(f"/documents/{doc_id}", headers=auth(org.admin))
    assert resp.status_code == 204
    db.expire_all()
    assert db.get(Document, doc_id) is None
    assert db.query(Chunk).filter_by(document_id=doc_id).count() == 0
    with pytest.raises(FileNotFoundError):
        storage.get(key)


def test_audit_log(client, org, auth):
    client.post("/ask", json={"question": SALARY_QUESTION}, headers=auth(org.hr))
    client.post("/ask", json={"question": SALARY_QUESTION}, headers=auth(org.nobody))

    page = client.get("/admin/logs", headers=auth(org.admin)).json()
    assert page["total"] == 2
    newest, oldest = page["items"]
    assert newest["user_email"] == "nobody@example.com" and newest["refused"] is True
    assert oldest["user_email"] == "hr@example.com"
    assert "Salary bands 2026" in oldest["retrieved_titles"]

    only_hr = client.get(f"/admin/logs?user_id={org.hr.id}", headers=auth(org.admin)).json()
    assert only_hr["total"] == 1


def test_admin_creates_role(client, org, auth):
    resp = client.post("/roles", json={"name": "finance"}, headers=auth(org.admin))
    assert resp.status_code == 201
    assert (
        client.post("/roles", json={"name": "finance"}, headers=auth(org.admin)).status_code == 409
    )
    names = [r["name"] for r in client.get("/roles", headers=auth(org.admin)).json()]
    assert "finance" in names
