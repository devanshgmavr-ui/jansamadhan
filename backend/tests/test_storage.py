"""Supabase Storage provider tests (Stage-11 storage blocker).

Transport is faked at urllib: no network, no credentials. Covers upload
success/failure, DB rollback with orphan cleanup, download, signed-URL
generation (5-minute expiry), delete, missing objects, invalid objects,
oversized files, and validation. Scratch DB only (conftest isolation).
"""

import io
import json
import re
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.core import gov_revocation, ratelimit
from app.core.config import settings
from app.main import app
from app.services import storage as storage_svc
from tests.conftest import (
    APPROVABLE_PROBLEM,
    make_official,
    make_user,
)

client = TestClient(app, raise_server_exceptions=False)

PDF = b"%PDF-1.4 fake attachment bytes"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100

NAMESPACE = storage_svc.NAMESPACE_PROBLEM_ATTACHMENTS


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeTransport:
    """In-memory Supabase Storage. Records every request for assertions."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple] = []
        self.fail_upload = False

    def __call__(self, req, timeout=None):
        url = req.full_url
        method = req.get_method()
        body = req.data or b""
        headers = dict(req.header_items())
        # Signed-URL fetches are bare GETs carrying the token in the URL
        # and need no key; every other call must authenticate.
        if not (method == "GET" and not headers):
            assert "apikey" in {k.lower() for k in headers}, \
                "key must be sent"
        self.calls.append((method, url, body))
        root = "https://xyz.supabase.co"
        if self.fail_upload and "/storage/v1/object/attachments/" in url \
                and method == "POST" and "/object/sign/" not in url:
            raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))
        if method == "POST" and "/object/sign/" in url:
            m = re.search(r"/object/sign/attachments/(.+)$", url)
            path = m.group(1)
            if path not in self.objects:
                # Real Supabase answers 400 + embedded NoSuchKey here.
                raise urllib.error.HTTPError(
                    url, 400, "bad request", {},
                    io.BytesIO(b'{"statusCode":"404","error":"not_found",'
                               b'"message":"Object not found",'
                               b'"code":"NoSuchKey"}'))
            payload = json.loads(body.decode())
            assert payload.get("expiresIn") == 300, payload
            return FakeResponse(json.dumps(
                {"signedURL": "/storage/v1/object/sign/attachments/"
                              f"{path}?token=t"}
            ).encode())
        if "/storage/v1/object/sign/" in url:
            m = re.search(r"/object/sign/attachments/(.+?)\?token=", url)
            path = m.group(1)
            if path not in self.objects:
                raise urllib.error.HTTPError(
                    url, 400, "bad request", {},
                    io.BytesIO(b'{"statusCode":"404","code":"NoSuchKey"}'))
            return FakeResponse(self.objects[path])
        if method == "POST" and "/storage/v1/object/attachments/" in url:
            path = url.split("/storage/v1/object/attachments/", 1)[1]
            self.objects[path] = body
            return FakeResponse(json.dumps({"Key": path}).encode())
        if method == "DELETE" and url.endswith("/storage/v1/object/attachments"):
            prefixes = json.loads(body.decode()).get("prefixes", [])
            for prefix in prefixes:
                self.objects.pop(prefix, None)
            return FakeResponse(b"[]")
        raise AssertionError(f"unexpected call {method} {url}")

    def upload_urls(self):
        return [u for m, u, _ in self.calls
                if m == "POST" and "/object/sign/" not in u
                and "/storage/v1/object/" in u]

    def delete_calls(self):
        return [(u, b) for m, u, b in self.calls if m == "DELETE"]


@pytest.fixture()
def supabase_env(monkeypatch):
    import app.services.supabase_storage as sup

    transport = FakeTransport()
    monkeypatch.setattr(sup.urllib.request, "urlopen", transport)
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "test-key")
    storage_svc.reset_providers()
    yield transport
    storage_svc.reset_providers()


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def owner_token(db, user):
    from app.core import security

    return security.create_access_token(user.id)


def upload(db, user, ticket, filename="report.pdf", content=PDF):
    return client.post(
        f"/api/v1/problems/{ticket}/attachments",
        files={"file": (filename, content, "application/pdf")},
        headers=authz(owner_token(db, user)),
    )


def make_pending_ticket(db):
    owner = make_user(db)
    r = client.post("/api/v1/problems", json=dict(APPROVABLE_PROBLEM),
                    headers=authz(owner_token(db, owner)))
    assert r.status_code == 201, r.text
    return owner, r.json()["ticket"]


# upload success ---------------------------------------------------------------
def test_supabase_upload_success_and_path_shape(db, supabase_env):
    owner, ticket = make_pending_ticket(db)
    r = upload(db, owner, ticket)
    assert r.status_code == 201, r.text
    urls = supabase_env.upload_urls()
    assert len(urls) == 1
    assert urls[0].startswith(
        "https://xyz.supabase.co/storage/v1/object/attachments/"
        f"problem-attachments/{ticket}/")
    stored = urls[0].rsplit("/", 1)[-1]
    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", stored), stored
    assert "report.pdf" not in urls[0]  # never original filenames
    body = r.json()
    assert body["size_bytes"] == len(PDF)
    assert body["mime_type"] == "application/pdf"


# upload failure -> database unchanged ------------------------------------------
def test_supabase_upload_failure_leaves_db_unchanged(db, supabase_env):
    from sqlalchemy import func, select

    from app.models.problem import ProblemAttachment

    supabase_env.fail_upload = True
    owner, ticket = make_pending_ticket(db)
    r = upload(db, owner, ticket)
    assert r.status_code == 502, r.status_code
    count = db.execute(
        select(func.count()).select_from(ProblemAttachment)).scalar_one()
    assert count == 0


# database rollback -> orphan object deleted --------------------------------------
def test_db_failure_deletes_uploaded_object(db, supabase_env, monkeypatch):
    from sqlalchemy.orm import Session

    owner, ticket = make_pending_ticket(db)
    real_commit = Session.commit

    def boom(self):
        raise RuntimeError("db down")

    monkeypatch.setattr(Session, "commit", boom)
    r = upload(db, owner, ticket)
    assert r.status_code == 500, (r.status_code, r.text)
    assert supabase_env.objects == {}, supabase_env.objects
    assert len(supabase_env.delete_calls()) == 1


# download ------------------------------------------------------------------------
def test_supabase_download_roundtrip(db, supabase_env):
    owner, ticket = make_pending_ticket(db)
    aid = upload(db, owner, ticket).json()["id"]
    r = client.get(
        f"/api/v1/problems/{ticket}/attachments/{aid}/download",
        headers=authz(owner_token(db, owner)))
    assert r.status_code == 200, r.status_code
    assert r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert "report.pdf" in r.headers.get("content-disposition", "")
    assert "sb_secret" not in r.text and "test-key" not in r.text


# delete ----------------------------------------------------------------------------
def test_supabase_delete_removes_object_and_row(db, supabase_env):
    from sqlalchemy import func, select

    from app.models.problem import ProblemAttachment

    owner, ticket = make_pending_ticket(db)
    aid = upload(db, owner, ticket).json()["id"]
    assert len(supabase_env.objects) == 1
    r = client.delete(f"/api/v1/problems/{ticket}/attachments/{aid}",
                      headers=authz(owner_token(db, owner)))
    assert r.status_code == 204, r.text
    assert supabase_env.objects == {}
    count = db.execute(
        select(func.count()).select_from(ProblemAttachment)).scalar_one()
    assert count == 0


# missing object -----------------------------------------------------------------------
def test_supabase_missing_object_is_404(db, supabase_env):
    owner, ticket = make_pending_ticket(db)
    aid = upload(db, owner, ticket).json()["id"]
    supabase_env.objects.clear()  # object lost remotely
    r = client.get(
        f"/api/v1/problems/{ticket}/attachments/{aid}/download",
        headers=authz(owner_token(db, owner)))
    assert r.status_code == 404, r.status_code


# invalid objects -------------------------------------------------------------------------
def test_supabase_rejects_invalid_uploads(db, supabase_env):
    owner, ticket = make_pending_ticket(db)
    h = authz(owner_token(db, owner))
    r = client.post(f"/api/v1/problems/{ticket}/attachments",
                    files={"file": ("evil.exe", b"MZ" + b"0" * 50,
                                     "application/octet-stream")},
                    headers=h)
    assert r.status_code == 422, r.status_code
    r = client.post(
        f"/api/v1/problems/{ticket}/attachments",
        files={"file": ("big.pdf", b"%PDF" + b"0" * (10 * 1024 * 1024 + 1),
                         "application/pdf")},
        headers=h)
    assert r.status_code == 413, r.status_code
    r = client.post(f"/api/v1/problems/{ticket}/attachments",
                    files={"file": ("fake.pdf", b"not a pdf at all",
                                     "application/pdf")},
                    headers=h)
    assert r.status_code == 422, r.status_code
    assert supabase_env.upload_urls() == []


# solution PDFs ride the same provider -------------------------------------------------------
def test_solution_pdf_supabase_roundtrip(db, supabase_env):
    from sqlalchemy import select as _select

    from app.models.problem import Problem
    from app.services import government_review_service as g

    owner = make_user(db)
    solver = make_user(db)
    r = client.post("/api/v1/problems", json=dict(APPROVABLE_PROBLEM),
                    headers=authz(owner_token(db, owner)))
    ticket = r.json()["ticket"]
    problem = db.execute(
        _select(Problem).where(Problem.ticket == ticket)).scalars().one()
    official = make_official(db)
    g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC",
                     actor_id=official.id)
    r = client.post(
        f"/api/v1/problems/{ticket}/solutions",
        data={"title": "Solar purifier pilot",
              "short_description": "Community RO plant for the ward.",
              "expected_impact": "Clean water for 300 families."},
        files={"file": ("plan.pdf", PDF, "application/pdf")},
        headers=authz(owner_token(db, solver)))
    assert r.status_code == 201, r.text
    urls = supabase_env.upload_urls()
    assert len(urls) == 1
    assert f"solution-pdfs/{r.json()['ticket']}/" in urls[0]
    dl = client.get(f"/api/v1/solutions/{r.json()['ticket']}/download",
                    headers=authz(owner_token(db, solver)))
    assert dl.status_code == 200, dl.status_code
    assert dl.content == PDF
