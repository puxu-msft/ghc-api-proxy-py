from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_approval_gate
from app.pipeline.approval import ApprovalGate
from app.server import create_app


def test_approval_pending_and_missing_detail_routes() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=1)
    app = create_app(AppSettings())
    app.dependency_overrides[get_approval_gate] = lambda: gate
    with TestClient(app) as client:
        pending = client.get("/api/approval/pending")
        missing = client.get("/api/approval/missing")
    assert pending.status_code == 200
    assert pending.json() == []
    assert missing.status_code == 404
