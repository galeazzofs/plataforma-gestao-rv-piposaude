"""Tests for the new financial XLSX parser.

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


def test_synthetic_parses_3_valid_rows_for_q1_2026():
    """Synthetic has 6 data rows. For Q1/2026:
    - 2 RECEBIDO Saúde (positive + negative) → pass
    - 1 RECEBIDO Mental → pass (not filtered by produto)
    - 1 A RECEBER → filtered by status
    - 1 Q2/2026 RECEBIDO → filtered by period
    - 1 RECEBIDO without cliente → filtered as garbage
    Total passing: 3"""
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    assert result['stats']['total_lidas'] == 6
    assert result['stats']['descartadas_status'] == 1
    assert result['stats']['descartadas_periodo'] == 1
    assert result['stats']['descartadas_vazias'] == 1
    assert result['stats']['persistidas'] == 3
    assert len(result['rows']) == 3


def test_synthetic_keeps_negative_values():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    nfs = [r['nf_valor_liquido'] for r in result['rows']]
    assert -200.00 in nfs
    assert 1000.00 in nfs


def test_synthetic_keeps_mental_product():
    """Parser should NOT filter Mental/Fitness — calculator does it later."""
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    produtos = [r['produto'] for r in result['rows']]
    assert 'Mental' in produtos


def test_synthetic_filters_by_quarter():
    result_q1 = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    result_q2 = parse_financial_xlsx(str(SYNTHETIC), target_quarter=2, target_year=2026)
    assert result_q1['stats']['persistidas'] == 3
    assert result_q2['stats']['persistidas'] == 1
    assert result_q2['rows'][0]['operadora'] == 'Hapvida'


def test_synthetic_parses_dates_as_date_objects():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert isinstance(row['data_recebimento'], date)
        assert row['data_recebimento'].year == 2026


def test_synthetic_status_only_recebido():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    assert all(r['status_recebimento'] == 'RECEBIDO' for r in result['rows'])


def test_synthetic_extracts_mes_recebimento():
    """mes_recebimento is YYYY-MM format derived from data_recebimento."""
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert len(row['mes_recebimento']) == 7
        assert row['mes_recebimento'].startswith('2026-')


# ── Real XLSX format smoke test ───────────────────────────────


def test_real_xlsx_format_parses_without_error():
    """Smoke test against the real spreadsheet subset — verifies header
    detection and column mapping work for the actual format."""
    result = parse_financial_xlsx(str(SAMPLE), target_quarter=1, target_year=2026)
    assert 'rows' in result
    assert 'stats' in result
    assert result['stats']['total_lidas'] > 0


def test_real_xlsx_extracts_known_fields():
    """Every persisted row should have all required fields populated."""
    result = parse_financial_xlsx(str(SAMPLE), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert row['cliente_mae']
        assert row['nf_valor_liquido'] is not None
        assert isinstance(row['data_recebimento'], date)
        assert row['status_recebimento'] == 'RECEBIDO'


# ── Error handling ────────────────────────────────────────────


def test_raises_on_missing_file():
    with pytest.raises((FileNotFoundError, ParseError)):
        parse_financial_xlsx("/nonexistent/path.xlsx", 1, 2026)
