"""Tests for NF→Policy matcher: normalize + normalize_apolice_number + build_policy_index."""
from datetime import date
from app.modules.financial.matcher import (
    normalize, normalize_apolice_number, build_policy_index,
)


class FakePolicy:
    def __init__(self, numero_apolice, closed_date):
        self.numero_apolice = numero_apolice
        self.closed_date = closed_date


# ── normalize (still exposed for product → benefit mapping) ─────────


def test_normalize_lowercases():
    assert normalize("ABC") == "abc"


def test_normalize_strips_accents():
    assert normalize("Saúde") == "saude"
    assert normalize("Educação") == "educacao"


def test_normalize_trims_spaces():
    assert normalize("  Hello  ") == "hello"


def test_normalize_handles_none_and_empty():
    assert normalize(None) == ""
    assert normalize("") == ""


def test_normalize_combined():
    assert normalize("  CLÍNICA São JOÃO  ") == "clinica sao joao"


# ── normalize_apolice_number ────────────────────────────────────────


def test_normalize_apolice_number_uppercases():
    assert normalize_apolice_number("ab-123") == "AB-123"


def test_normalize_apolice_number_strips_whitespace():
    assert normalize_apolice_number("  AB-123 ") == "AB-123"


def test_normalize_apolice_number_strips_quotes_and_apostrophes():
    """Spreadsheets occasionally export with leading apostrophe/quotes
    (Excel's text-coercion artefact). Treat both as cosmetic."""
    assert normalize_apolice_number("'AB-123") == "AB-123"
    assert normalize_apolice_number('"AB-123"') == "AB-123"


def test_normalize_apolice_number_handles_none_and_empty():
    assert normalize_apolice_number(None) == ""
    assert normalize_apolice_number("") == ""


def test_normalize_apolice_number_keeps_internal_chars():
    assert normalize_apolice_number("277.615/2024") == "277.615/2024"


# ── build_policy_index (now keyed on numero_apolice) ────────────────


def test_build_index_groups_by_apolice_number():
    p1 = FakePolicy("AP-100", date(2026, 1, 15))
    p2 = FakePolicy("AP-200", date(2026, 1, 15))
    p3 = FakePolicy("ap-300", date(2026, 1, 15))

    index = build_policy_index([p1, p2, p3])

    assert "AP-100" in index
    assert "AP-200" in index
    assert "AP-300" in index  # case-normalized


def test_build_index_normalizes_apolice_number_for_lookup():
    """Whitespace + casing differences must not cause a miss."""
    p = FakePolicy("  ab-99 ", date(2026, 1, 15))

    index = build_policy_index([p])

    assert "AB-99" in index


def test_build_index_sorts_by_closed_date_desc():
    """In the rare case two policies share a number (e.g. one renews
    another with the same number), most recent wins."""
    p_old = FakePolicy("AP-1", date(2025, 6, 1))
    p_new = FakePolicy("AP-1", date(2026, 2, 1))
    p_mid = FakePolicy("AP-1", date(2025, 12, 1))

    index = build_policy_index([p_old, p_new, p_mid])
    bucket = index["AP-1"]

    assert bucket == [p_new, p_mid, p_old]


def test_build_index_skips_policies_without_apolice_number():
    p_ok = FakePolicy("AP-OK", date(2026, 1, 1))
    p_no_num = FakePolicy(None, date(2026, 1, 1))
    p_blank = FakePolicy("   ", date(2026, 1, 1))

    index = build_policy_index([p_ok, p_no_num, p_blank])

    assert len(index) == 1
    assert "AP-OK" in index
