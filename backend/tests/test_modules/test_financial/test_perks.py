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
from app.modules.financial.perk_parser import (
    parse_perk_xlsx, parse_perk_csv, parse_perk_file, parse_money, PerkParseError,
)
from app.modules.financial.processor import persist_perk_rows


# ── parse_money (US / BR number-format autodetect) ──────────────────────────
#
# The Omie export is US-formatted ("3,934.02"); earlier perk sheets were BR
# ("3.500,00"). parse_money must read both. The rule: the RIGHTMOST separator is
# the decimal mark; a single separator followed by exactly two digits is also a
# decimal mark; everything else is thousands grouping. Parentheses mean negative.


class TestParseMoney:
    def test_us_thousands_and_decimal(self):
        assert parse_money("3,934.02") == Decimal("3934.02")
        assert parse_money("16,666.67") == Decimal("16666.67")
        assert parse_money("(3,934.02)") == Decimal("-3934.02")

    def test_br_thousands_and_decimal(self):
        # Existing perk sheets used BR format — must keep working.
        assert parse_money("3.500,00") == Decimal("3500.00")
        assert parse_money("(3.500,00)") == Decimal("-3500.00")

    def test_single_separator_two_decimals_is_decimal(self):
        assert parse_money("880.41") == Decimal("880.41")
        assert parse_money("(39.00)") == Decimal("-39.00")
        assert parse_money("12,50") == Decimal("12.50")

    def test_separator_not_two_trailing_digits_is_grouping(self):
        # Comma/dot with 3 trailing digits and no second separator = thousands.
        assert parse_money("21,038") == Decimal("21038")
        assert parse_money("1,234,567.89") == Decimal("1234567.89")

    def test_numeric_inputs_pass_through(self):
        assert parse_money(1500) == Decimal("1500")
        assert parse_money(1500.5) == Decimal("1500.5")

    def test_blank_or_unparseable_returns_none(self):
        assert parse_money(None) is None
        assert parse_money("") is None
        assert parse_money("   ") is None
        assert parse_money("abc") is None


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


def _make_csv(text):
    """Write `text` to a temp .csv (UTF-8). Returns the path."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
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

    def test_parses_us_format_string_values(self, admin_user):
        # The Omie export carries values as parenthesized US-format strings.
        path = _make_xlsx([
            ["Acme", "(3,934.02)", "01 - Janeiro", 2026],
            ["Zup", "16,666.67", "02 - Fevereiro", 2026],
        ])
        out = parse_perk_xlsx(path, 2026)
        by_month = {r["month"]: r["amount"] for r in out["rows"]}
        assert by_month == {1: Decimal("3934.02"), 2: Decimal("16666.67")}


# ── parse_perk_csv / parse_perk_file ─────────────────────────────────────────


class TestParsePerkCsv:
    def test_parses_omie_csv_us_values_and_competencia_months(self, admin_user):
        path = _make_csv(
            "Cliente Pipo,Tipo Subsídio,Fornecedor,Ano,Mês (Competência),Valor,OBS\n"
            'OLX,Academia,FOO LTDA,2026,01 - Janeiro,"(22,771.59)",GYMPASS\n'
            'OLX,Cesta Natal,FOO LTDA,2026,01 - Janeiro,"(16,666.67)",BRINDES\n'
            "NUVEMSHOP,Reembolso Copay,BAR LTDA,2026,01 - Janeiro,(372.26),COPAY\n"
        )
        out = parse_perk_csv(path, 2026)
        totals = {}
        for r in out["rows"]:
            totals[r["client_name"]] = totals.get(r["client_name"], Decimal("0")) + r["amount"]
        # Both OLX rows summed, big values NOT shrunk by the BR-format bug.
        assert totals["OLX"] == Decimal("39438.26")
        assert totals["NUVEMSHOP"] == Decimal("372.26")
        assert all(r["month"] == 1 for r in out["rows"])

    def test_csv_drops_other_years(self, admin_user):
        path = _make_csv(
            "Cliente,Valor,Mês,Ano\n"
            'Acme,"(1,000.00)",01 - Janeiro,2026\n'
            'Zup,"(2,000.00)",12 - Dezembro,2025\n'
        )
        out = parse_perk_csv(path, 2026)
        assert len(out["rows"]) == 1
        assert out["rows"][0]["client_name"] == "Acme"
        assert out["stats"]["descartadas_periodo"] == 1

    def test_parse_perk_file_dispatches_by_extension(self, admin_user):
        csv_path = _make_csv("Cliente,Valor,Mês,Ano\nAcme,(50.00),01 - Janeiro,2026\n")
        xlsx_path = _make_xlsx([["Acme", "(3,934.02)", 1, 2026]])
        # A temp path may not carry the real suffix — original_filename wins.
        out_csv = parse_perk_file(csv_path, 2026, original_filename="Omie.csv")
        out_xlsx = parse_perk_file(xlsx_path, 2026, original_filename="sheet.xlsx")
        assert out_csv["rows"][0]["amount"] == Decimal("50.00")
        assert out_xlsx["rows"][0]["amount"] == Decimal("3934.02")


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
