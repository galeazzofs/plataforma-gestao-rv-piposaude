"""Tests for the financial XLSX parser (per-year ingestion).

Uses two fixtures:
- synthetic_financial.xlsx — 6 known rows for precise assertions
- sample_financial.xlsx — real-format subset for smoke testing
"""
import pytest
from datetime import date
from pathlib import Path

from app.modules.financial.parser import parse_financial_xlsx, ParseError

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic_financial.xlsx"
SAMPLE = FIXTURES / "sample_financial.xlsx"


# ── Synthetic XLSX (controlled values) ────────────────────────


def test_synthetic_parses_valid_rows_for_2026():
    """Synthetic has 6 data rows. For year 2026, the parser keeps every
    RECEBIDO commissionable row regardless of month:
    - 3 RECEBIDO in 02/2026 (positive Saúde, negative Saúde, Mental)
    - 1 RECEBIDO in 04/2026 (Hapvida)
    - 1 A RECEBER → filtered by status
    - 1 RECEBIDO without cliente → filtered as garbage
    Total passing: 4 (the month no longer filters)."""
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    assert result['stats']['total_lidas'] == 6
    assert result['stats']['descartadas_status'] == 1
    assert result['stats']['descartadas_periodo'] == 0
    assert result['stats']['descartadas_vazias'] == 1
    assert result['stats']['persistidas'] == 4
    assert len(result['rows']) == 4


def test_synthetic_keeps_all_months_of_the_year():
    """A single parse pulls in every month — Feb AND April rows come through,
    each carrying its own competência month in mes_recebimento."""
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    meses = sorted({r['mes_recebimento'] for r in result['rows']})
    assert '2026-02' in meses
    assert '2026-04' in meses
    operadoras = {r['operadora'] for r in result['rows']}
    assert 'Hapvida' in operadoras  # the April row is included


def test_synthetic_keeps_negative_values():
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    nfs = [r['nf_valor_liquido'] for r in result['rows']]
    assert -200.00 in nfs
    assert 1000.00 in nfs


def test_synthetic_keeps_mental_product():
    """Parser should NOT filter Mental/Fitness — calculator does it later."""
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    produtos = [r['produto'] for r in result['rows']]
    assert 'Mental' in produtos


def test_synthetic_drops_other_years():
    """A different year keeps nothing from this 2026-only fixture."""
    result = parse_financial_xlsx(str(SYNTHETIC), 2025)
    assert result['stats']['persistidas'] == 0


def test_synthetic_parses_dates_as_date_objects():
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    for row in result['rows']:
        assert isinstance(row['data_recebimento'], date)
        assert row['data_recebimento'].year == 2026


def test_synthetic_status_only_recebido():
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    assert all(r['status_recebimento'] == 'RECEBIDO' for r in result['rows'])


def test_synthetic_extracts_mes_recebimento():
    """mes_recebimento is YYYY-MM format derived from data_recebimento."""
    result = parse_financial_xlsx(str(SYNTHETIC), 2026)
    for row in result['rows']:
        assert len(row['mes_recebimento']) == 7
        assert row['mes_recebimento'].startswith('2026-')


# ── Real XLSX format smoke test ───────────────────────────────


def test_real_xlsx_format_parses_without_error():
    """Smoke test against the real spreadsheet subset — verifies header
    detection and column mapping work for the actual format."""
    result = parse_financial_xlsx(str(SAMPLE), 2026)
    assert 'rows' in result
    assert 'stats' in result
    assert result['stats']['total_lidas'] > 0


def test_real_xlsx_extracts_known_fields():
    """Every persisted row should have all required fields populated."""
    result = parse_financial_xlsx(str(SAMPLE), 2026)
    for row in result['rows']:
        assert row['cliente_mae']
        assert row['nf_valor_liquido'] is not None
        assert isinstance(row['data_recebimento'], date)
        assert row['status_recebimento'] == 'RECEBIDO'


# ── Error handling ────────────────────────────────────────────


def test_raises_on_missing_file():
    with pytest.raises((FileNotFoundError, ParseError)):
        parse_financial_xlsx("/nonexistent/path.xlsx", 2026)
