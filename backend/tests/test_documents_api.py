"""Documents API tests: upload/list/get with mocked DB + mocked pipeline."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.main import app
from backend.app.models.document import Document, DocumentStatus
from backend.app.models.user import User, UserRole


def make_hr_user():
    u = User(email="hr@company.com", password_hash="x", full_name="HR",
             role=UserRole.hr_manager)
    u.id = uuid.uuid4()
    u.is_active = True
    return u


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, single=None, items=None):
        self._single = single
        self._items = items or []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return FakeScalars(self._items)


def make_session(single=None, items=None):
    session = AsyncMock()
    session.execute.return_value = FakeResult(single, items)
    session.add = MagicMock(return_value=None)
    session.commit.return_value = None
    session.refresh.return_value = None
    return session


def client_with(user, single=None, items=None):
    async def _db():
        yield make_session(single, items)

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_upload_rejects_bad_extension():
    c = client_with(make_hr_user(), items=[])
    r = c.post("/api/v1/documents/upload", files={"file": ("evil.exe", b"data")})
    assert r.status_code == 422


def test_upload_accepts_txt_and_queues_task():
    c = client_with(make_hr_user(), items=[])
    with patch("backend.app.api.v1.documents._run_ingestion") as _:
        r = c.post("/api/v1/documents/upload", files={"file": ("leave.txt", b"Annual leave 18 days.")})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "processing" and body["version"] == 1


def test_upload_increments_version():
    old = Document(file_name="leave.txt", file_type="txt", file_size=1, version=2,
                   status=DocumentStatus.ready)
    old.id = uuid.uuid4()
    c = client_with(make_hr_user(), items=[old])
    with patch("backend.app.api.v1.documents._run_ingestion"):
        r = c.post("/api/v1/documents/upload", files={"file": ("leave.txt", b"new text")})
    assert r.json()["version"] == 3


def test_list_documents():
    d = Document(file_name="a.pdf", file_type="pdf", file_size=1, version=1,
                 status=DocumentStatus.ready)
    d.id = uuid.uuid4()
    c = client_with(make_hr_user(), items=[d])
    r = c.get("/api/v1/documents")
    assert r.status_code == 200 and r.json()[0]["file_name"] == "a.pdf"


def test_get_document_404():
    c = client_with(make_hr_user(), single=None)
    r = c.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert r.status_code == 404
