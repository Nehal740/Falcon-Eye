"""Shared test setup.

The environment is configured *before* the app is imported, so tests use an
in-memory SQLite database and never touch your real data.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["LLM_API_KEY"] = ""  # tests never call a real AI service
os.environ["LOGIN_MAX_ATTEMPTS"] = "5"

import pytest  # noqa: E402


@pytest.fixture()
def client():
    """A fresh app + empty database for every test (needs FastAPI installed)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    from database import Base, engine
    from migrations import init_db
    from rate_limiter import limiter

    Base.metadata.drop_all(bind=engine)
    limiter.clear()
    init_db()
    from main import app

    with TestClient(app) as test_client:
        yield test_client


class Session:
    """A signed-in user, with helpers for readable tests."""

    def __init__(self, client, email, password, data):
        self.client = client
        self.email = email
        self.password = password
        self.token = data["access_token"]
        self.user = data["user"]
        self.workspace_id = data["workspaces"][0]["id"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post(path, json=json, headers=self.headers, **kw)

    def patch(self, path, json=None):
        return self.client.patch(path, json=json, headers=self.headers)

    def put(self, path, json=None):
        return self.client.put(path, json=json, headers=self.headers)

    def delete(self, path):
        return self.client.delete(path, headers=self.headers)

    def ws(self, suffix=""):
        return f"/workspaces/{self.workspace_id}{suffix}"


@pytest.fixture()
def make_user(client):
    def _make(email="alice@example.com", name="Alice Example", password="Sup3rSecret!"):
        # TestClient keeps cookies; use a fresh client per user is unnecessary
        # because every request here authenticates with a Bearer token.
        r = client.post("/auth/register",
                        json={"full_name": name, "email": email, "password": password})
        assert r.status_code == 201, r.text
        client.cookies.clear()
        return Session(client, email, password, r.json())
    return _make


@pytest.fixture()
def alice(make_user):
    return make_user()


@pytest.fixture()
def bob(make_user):
    return make_user("bob@example.com", "Bob Example")


@pytest.fixture()
def agent(alice):
    """An agent in Alice's workspace with an active key, and a starter policy."""
    r = alice.post(alice.ws("/agents"), {"name": "Support bot", "description": "test"})
    assert r.status_code == 201, r.text
    data = r.json()
    alice.post(alice.ws("/policies/from-template"), {"template_id": "recommended"})
    return {"id": data["agent"]["id"], "public_id": data["agent"]["agent_id"],
            "key": data["api_key"], "headers": {"Authorization": f"Bearer {data['api_key']}"}}
