"""Tests for perk_parser + persist_perk_rows + /upload-perks endpoint."""
import io
import uuid
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.extensions import db
from app.models import (
    User, UserRole, Client, Perk, ImportBatch,
    Appraisal, AppraisalStatus,
)
from app.modules.financial.perk_parser import parse_perk_xlsx, PerkParseError
from app.modules.financial.processor import (
    persist_perk_rows, UploadBlockedError,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_user():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"perk-admin-{suffix}@piposaude.com",
        name="Perk Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    db.session.add(u)
    db.session.flush()
    db.session.commit()
    yield u
    Perk.query.delete()
    ImportBatch.query.delete()
    Appraisal.query.delete()
    Client.query.delete()
    db.session.delete(u)
    db.session.commit()


def _make_xlsx(rows, headers=None):
    """Build an in-memory XLSX with the given rows. Returns a temp file path."""
    import tempfile, os
    headers = headers or ["Cliente", "Valor", "Mes", "Ano"]
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


# ── parse_perk_xlsx ──────────────────────────────────────────────────────────


class TestParsePerkXlsx:
    def test_parses_basic_rows(self, admin_user):
        path = _make_xlsx([
            ["Acme", 1500.00, 1, 2026],
            ["Zup", 2500.00, 2, 2026],
        ])
        out = parse_perk_xlsx(path, target_quarter=1, target_year=2026)
        assert len(out['rows']) == 2
        assert out['stats']['persistidas'] == 2
        assert out['rows'][0]['amount'] == Decimal('1500')

    def test_drops_rows_outside_target_period(self, admin_user):
        path = _make_xlsx([
            ["Acme", 1000, 1, 2026],   # Q1/2026 — keep
            ["Zup",  1000, 4, 2026],   # Q2 — drop
            ["BBB",  1000, 1, 2025],   # wrong year — drop
        ])
        out = parse_perk_xlsx(path, target_quarter=1, target_year=2026)
        assert len(out['rows']) == 1
        assert out['stats']['descartadas_periodo'] == 2

    def test_handles_brazilian_negative_format(self, admin_user):
        path = _make_xlsx([
            ["Acme", "(3.500,00)", 1, 2026],  # negative-in-parens BR format
        ])
        out = parse_perk_xlsx(path, target_quarter=1, target_year=2026)
        assert len(out['rows']) == 1
        assert out['rows'][0]['amount'] == Decimal('3500')

    def test_drops_zero_and_invalid_amounts(self, admin_user):
        path = _make_xlsx([
            ["Acme", 0, 1, 2026],
            ["Zup",  "abc", 1, 2026],
            ["BBB",  100, 1, 2026],
        ])
        out = parse_perk_xlsx(path, target_quarter=1, target_year=2026)
        assert len(out['rows']) == 1
        assert out['stats']['descartadas_vazias'] == 2

    def test_missing_cliente_column_raises(self, admin_user):
        path = _make_xlsx(
            [["foo", 100, 1, 2026]],
            headers=["Other", "Valor", "Mes", "Ano"],
        )
        with pytest.raises(PerkParseError):
            parse_perk_xlsx(path, target_quarter=1, target_year=2026)


# ── persist_perk_rows ────────────────────────────────────────────────────────


class TestPersistPerkRows:
    def _client(self, name="Acme Corp"):
        c = Client(name=name, name_normalized=name.lower())
        db.session.add(c)
        db.session.flush()
        return c

    def test_creates_perks_with_exact_match(self, admin_user):
        c = self._client("Acme Corp")
        rows = [{
            'client_name': 'Acme Corp',
            'amount': Decimal('1000'),
            'month': 1, 'quarter': 1, 'year': 2026,
        }]
        out = persist_perk_rows(rows, 1, 2026, "t.xlsx", admin_user.id)
        db.session.commit()

        perks = Perk.query.filter_by(quarter=1, year=2026).all()
        assert len(perks) == 1
        assert perks[0].client_id == c.id
        assert perks[0].amount == Decimal('1000')
        assert out['matched'] == 1
        assert out['missed'] == 0
        assert out['partial_matches'] == []

    def test_partial_match_logs_audit(self, admin_user):
        c = self._client("Zup IT Services")
        rows = [{
            'client_name': 'Zup',
            'amount': Decimal('500'),
            'month': 1, 'quarter': 1, 'year': 2026,
        }]
        out = persist_perk_rows(rows, 1, 2026, "t.xlsx", admin_user.id)
        db.session.commit()

        assert out['matched'] == 1
        assert len(out['partial_matches']) == 1
        assert out['partial_matches'][0]['matched_to'] == "Zup IT Services"

    def test_missed_clients_deduplicated(self, admin_user):
        rows = [
            {'client_name': 'Unknown',  'amount': Decimal('100'),
             'month': 1, 'quarter': 1, 'year': 2026},
            {'client_name': 'Unknown',  'amount': Decimal('200'),
             'month': 2, 'quarter': 1, 'year': 2026},
            {'client_name': 'Other',    'amount': Decimal('300'),
             'month': 3, 'quarter': 1, 'year': 2026},
        ]
        out = persist_perk_rows(rows, 1, 2026, "t.xlsx", admin_user.id)
        assert out['missed'] == 3
        assert out['missed_clients'] == ['Other', 'Unknown']  # sorted, deduped

    def test_replaces_existing_perks_for_period(self, admin_user):
        c = self._client("Acme Corp")
        # First upload
        persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('100'),
              'month': 1, 'quarter': 1, 'year': 2026}],
            1, 2026, "first.xlsx", admin_user.id,
        )
        db.session.commit()
        # Second upload — different amount
        persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('999'),
              'month': 1, 'quarter': 1, 'year': 2026}],
            1, 2026, "second.xlsx", admin_user.id,
        )
        db.session.commit()

        perks = Perk.query.filter_by(quarter=1, year=2026).all()
        assert len(perks) == 1
        assert perks[0].amount == Decimal('999')

    def test_blocks_when_appraisal_locked(self, admin_user):
        ap = Appraisal(
            quarter=1, year=2026,
            status=AppraisalStatus.LOCKED,
            created_by=admin_user.id,
        )
        db.session.add(ap)
        db.session.commit()

        with pytest.raises(UploadBlockedError):
            persist_perk_rows(
                [{'client_name': 'Acme', 'amount': Decimal('100'),
                  'month': 1, 'quarter': 1, 'year': 2026}],
                1, 2026, "t.xlsx", admin_user.id,
            )