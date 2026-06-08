"""Tests for perk_parser + persist_perk_rows (per-year / per-competência)."""
import uuid
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.extensions import db
from app.models import (
    User, UserRole, Client, Perk, ImportBatch,
    Appraisal, AppraisalStatus, AuditLog,
)
from app.modules.financial.perk_parser import parse_perk_xlsx, PerkParseError
from app.modules.financial.processor import persist_perk_rows


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
    AuditLog.query.filter_by(user_id=u.id).delete()
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
            ["Zup", 2500.00, 1, 2026],
        ])
        out = parse_perk_xlsx(path, 2026)
        assert len(out['rows']) == 2
        assert out['stats']['persistidas'] == 2
        assert out['rows'][0]['amount'] == Decimal('1500')

    def test_keeps_all_months_drops_other_years(self, admin_user):
        path = _make_xlsx([
            ["Acme", 1000, 1, 2026],   # month 1/2026 — keep
            ["Zup",  1000, 4, 2026],   # month 4/2026 — keep (month no longer filters)
            ["BBB",  1000, 1, 2025],   # wrong year — drop
        ])
        out = parse_perk_xlsx(path, 2026)
        assert len(out['rows']) == 2
        assert {r['month'] for r in out['rows']} == {1, 4}
        assert out['stats']['descartadas_periodo'] == 1

    def test_handles_brazilian_negative_format(self, admin_user):
        path = _make_xlsx([
            ["Acme", "(3.500,00)", 1, 2026],  # negative-in-parens BR format
        ])
        out = parse_perk_xlsx(path, 2026)
        assert len(out['rows']) == 1
        assert out['rows'][0]['amount'] == Decimal('3500')

    def test_drops_zero_and_invalid_amounts(self, admin_user):
        path = _make_xlsx([
            ["Acme", 0, 1, 2026],
            ["Zup",  "abc", 1, 2026],
            ["BBB",  100, 1, 2026],
        ])
        out = parse_perk_xlsx(path, 2026)
        assert len(out['rows']) == 1
        assert out['stats']['descartadas_vazias'] == 2

    def test_missing_cliente_column_raises(self, admin_user):
        path = _make_xlsx(
            [["foo", 100, 1, 2026]],
            headers=["Other", "Valor", "Mes", "Ano"],
        )
        with pytest.raises(PerkParseError):
            parse_perk_xlsx(path, 2026)


# ── persist_perk_rows ────────────────────────────────────────────────────────


class TestPersistPerkRows:
    def _client(self, name="Acme Corp"):
        c = Client(name=name, name_normalized=name.lower())
        db.session.add(c)
        db.session.flush()
        return c

    def test_creates_perks_with_per_row_month(self, admin_user):
        c = self._client("Acme Corp")
        rows = [
            {'client_name': 'Acme Corp', 'amount': Decimal('1000'),
             'month': 1, 'year': 2026},
            {'client_name': 'Acme Corp', 'amount': Decimal('500'),
             'month': 5, 'year': 2026},
        ]
        out = persist_perk_rows(rows, 2026, "t.xlsx", admin_user.id)
        db.session.commit()

        assert out['matched'] == 2
        assert out['missed'] == 0
        assert Perk.query.filter_by(month=1, year=2026).count() == 1
        assert Perk.query.filter_by(month=5, year=2026).count() == 1
        assert all(p.client_id == c.id for p in Perk.query.all())

    def test_partial_match_logs_audit(self, admin_user):
        self._client("Zup IT Services")
        rows = [{
            'client_name': 'Zup',
            'amount': Decimal('500'),
            'month': 1, 'year': 2026,
        }]
        out = persist_perk_rows(rows, 2026, "t.xlsx", admin_user.id)
        db.session.commit()

        assert out['matched'] == 1
        assert len(out['partial_matches']) == 1
        assert out['partial_matches'][0]['matched_to'] == "Zup IT Services"

    def test_missed_clients_deduplicated(self, admin_user):
        rows = [
            {'client_name': 'Unknown',  'amount': Decimal('100'),
             'month': 1, 'year': 2026},
            {'client_name': 'Unknown',  'amount': Decimal('200'),
             'month': 2, 'year': 2026},
            {'client_name': 'Other',    'amount': Decimal('300'),
             'month': 3, 'year': 2026},
        ]
        out = persist_perk_rows(rows, 2026, "t.xlsx", admin_user.id)
        assert out['missed'] == 3
        assert out['missed_clients'] == ['Other', 'Unknown']  # sorted, deduped

    def test_replaces_only_months_present(self, admin_user):
        self._client("Acme Corp")
        # First upload — month 1.
        persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('100'),
              'month': 1, 'year': 2026}],
            2026, "first.xlsx", admin_user.id,
        )
        db.session.commit()
        # Second upload — month 1 again, different amount → replaces month 1.
        persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('999'),
              'month': 1, 'year': 2026}],
            2026, "second.xlsx", admin_user.id,
        )
        db.session.commit()

        perks = Perk.query.filter_by(month=1, year=2026).all()
        assert len(perks) == 1
        assert perks[0].amount == Decimal('999')

    def test_skips_and_preserves_locked_months(self, admin_user):
        self._client("Acme Corp")
        # Load month 1 while open.
        persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('100'),
              'month': 1, 'year': 2026}],
            2026, "first.xlsx", admin_user.id,
        )
        db.session.commit()
        db.session.add(Appraisal(
            month=1, year=2026, status=AppraisalStatus.LOCKED,
            created_by=admin_user.id,
        ))
        db.session.commit()

        out = persist_perk_rows(
            [{'client_name': 'Acme Corp', 'amount': Decimal('999'),
              'month': 1, 'year': 2026}],
            2026, "second.xlsx", admin_user.id,
        )
        db.session.commit()

        assert out['skipped_locked'] == 1
        assert out['matched'] == 0
        perks = Perk.query.filter_by(month=1, year=2026).all()
        assert len(perks) == 1
        assert perks[0].amount == Decimal('100')  # original preserved
