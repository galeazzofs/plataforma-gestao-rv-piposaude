"""End-to-end test for the financial upload endpoint."""
import io
import uuid
from pathlib import Path

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, FinancialImport, ImportBatch, AuditLog,
)
from app.auth.jwt_manager import create_access_token

FIXTURES = Path(__file__).parent.parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic_financial.xlsx"


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"upload-admin-{suffix}@x", name="Admin",
        role=UserRole.ADMIN, active=True,
    )
    db.session.add(u)
    db.session.commit()
    yield u
    FinancialImport.query.delete()
    ImportBatch.query.delete()
    AuditLog.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()


def test_upload_synthetic_xlsx_persists_3_rows(client, admin):
    """End-to-end: POST the synthetic fixture and verify 3 rows persisted
    (positive Saúde, negative Saúde estorno, Mental — for Q1/2026)."""
    with open(SYNTHETIC, "rb") as f:
        file_bytes = f.read()

    resp = client.post(
        "/api/v1/financial/upload",
        data={
            "file": (io.BytesIO(file_bytes), "synthetic.xlsx"),
            "quarter": "1",
            "year": "2026",
        },
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["data"]
    assert body["rows_persisted"] == 3
    assert body["quarter"] == 1
    assert body["year"] == 2026
    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 3


def test_upload_missing_file_returns_400(client, admin):
    resp = client.post(
        "/api/v1/financial/upload",
        data={"quarter": "1", "year": "2026"},
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_upload_missing_quarter_returns_400(client, admin):
    with open(SYNTHETIC, "rb") as f:
        file_bytes = f.read()
    resp = client.post(
        "/api/v1/financial/upload",
        data={
            "file": (io.BytesIO(file_bytes), "synthetic.xlsx"),
            "year": "2026",
        },
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_upload_rejects_non_xlsx(client, admin):
    resp = client.post(
        "/api/v1/financial/upload",
        data={
            "file": (io.BytesIO(b"hello"), "notes.txt"),
            "quarter": "1",
            "year": "2026",
        },
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400
