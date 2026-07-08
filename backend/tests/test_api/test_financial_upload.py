"""End-to-end test for the financial upload endpoint (per-year ingestion)."""
import io
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, FinancialImport, ImportBatch, AuditLog, Client, Perk,
)
from app.auth.jwt_manager import create_access_token

FIXTURES = Path(__file__).parent.parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic_financial.xlsx"


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()


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
    Perk.query.delete()
    FinancialImport.query.delete()
    ImportBatch.query.delete()
    Client.query.delete()
    AuditLog.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()


def test_upload_synthetic_xlsx_persists_rows_by_month(client, admin):
    """End-to-end: POST the synthetic fixture for the year and verify the 4
    RECEBIDO rows persist, each tagged by its own competência month
    (3 in 02/2026, 1 in 04/2026)."""
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

    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["data"]
    assert body["rows_persisted"] == 4
    assert body["year"] == 2026
    assert body["skipped_locked"] == 0
    assert FinancialImport.query.filter_by(year=2026).count() == 4
    assert FinancialImport.query.filter_by(month=2, year=2026).count() == 3
    assert FinancialImport.query.filter_by(month=4, year=2026).count() == 1


def test_upload_missing_file_returns_400(client, admin):
    resp = client.post(
        "/api/v1/financial/upload",
        data={"year": "2026"},
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_upload_missing_year_returns_400(client, admin):
    with open(SYNTHETIC, "rb") as f:
        file_bytes = f.read()
    resp = client.post(
        "/api/v1/financial/upload",
        data={
            "file": (io.BytesIO(file_bytes), "synthetic.xlsx"),
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
            "year": "2026",
        },
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_upload_perks_csv_us_format_persists_intact_amounts(client, admin):
    """End-to-end: a US-format Omie CSV is accepted by /upload-perks, parsed,
    matched to a Client by name, and persisted WITHOUT the BR-format ~1000x
    shrink — both OLX rows land at their real magnitudes."""
    c = Client(name="OLX", name_normalized="olx")
    db.session.add(c)
    db.session.commit()

    csv_bytes = (
        "Cliente Pipo,Tipo Subsídio,Fornecedor,Ano,Mês (Competência),Valor,OBS\n"
        'OLX,Academia,FOO,2026,01 - Janeiro,"(22,771.59)",GYMPASS\n'
        'OLX,Cesta Natal,FOO,2026,01 - Janeiro,"(16,666.67)",BRINDES\n'
    ).encode("utf-8")

    resp = client.post(
        "/api/v1/financial/upload-perks",
        data={"file": (io.BytesIO(csv_bytes), "Omie Output.csv"), "year": "2026"},
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["data"]
    assert body["matched"] == 2
    assert body["missed"] == 0
    perks = Perk.query.filter_by(client_id=c.id, month=1, year=2026).all()
    assert {p.amount for p in perks} == {Decimal("22771.59"), Decimal("16666.67")}


def test_upload_perks_rejects_unsupported_extension(client, admin):
    resp = client.post(
        "/api/v1/financial/upload-perks",
        data={"file": (io.BytesIO(b"hello"), "notes.txt"), "year": "2026"},
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_upload_perks_returns_unique_matched_client_count(client, admin):
    """matched conta linhas persistidas; matched_clients conta CLIENTES
    distintos — duas linhas do mesmo cliente devem reportar 1 cliente."""
    db.session.add(Client(name="Acme Corp", name_normalized="acme corp"))
    db.session.commit()
    file_bytes = _xlsx_bytes(
        ["Cliente Pipo", "Valor", "Mês (Competência)", "Ano"],
        [
            ["Acme Corp", -1000, "01 - Janeiro", 2026],
            ["Acme Corp", -500, "02 - Fevereiro", 2026],
        ],
    )

    resp = client.post(
        "/api/v1/financial/upload-perks",
        data={
            "file": (io.BytesIO(file_bytes), "perks.xlsx"),
            "year": "2026",
        },
        content_type="multipart/form-data",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["data"]
    assert body["matched"] == 2
    assert body["matched_clients"] == 1
    assert body["missed"] == 0
    assert Perk.query.filter_by(year=2026).count() == 2
