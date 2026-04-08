"""Tests for NF→Policy matcher: normalize + build_policy_index."""
from datetime import date
from app.modules.financial.matcher import normalize, build_policy_index


class FakeClient:
    def __init__(self, name):
        self.name = name


class FakeBenefit:
    def __init__(self, value):
        self.value = value


class FakePolicy:
    def __init__(self, client_name, operadora, benefit, closed_date):
        self.client = FakeClient(client_name) if client_name else None
        self.partner_operator = operadora
        self.benefit_type = FakeBenefit(benefit) if benefit else None
        self.closed_date = closed_date


# ── normalize ────────────────────────────────────────────────


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


# ── build_policy_index ───────────────────────────────────────


def test_build_index_groups_by_key():
    p1 = FakePolicy("Zup", "Sulamérica", "SAUDE", date(2026, 1, 15))
    p2 = FakePolicy("Zup", "Sulamérica", "ODONTO", date(2026, 1, 15))
    p3 = FakePolicy("Acme", "Sulamérica", "SAUDE", date(2026, 1, 15))

    index = build_policy_index([p1, p2, p3])

    assert ("zup", "sulamerica", "SAUDE") in index
    assert ("zup", "sulamerica", "ODONTO") in index
    assert ("acme", "sulamerica", "SAUDE") in index


def test_build_index_sorts_by_closed_date_desc():
    p_old = FakePolicy("Zup", "X", "SAUDE", date(2025, 6, 1))
    p_new = FakePolicy("Zup", "X", "SAUDE", date(2026, 2, 1))
    p_mid = FakePolicy("Zup", "X", "SAUDE", date(2025, 12, 1))

    index = build_policy_index([p_old, p_new, p_mid])
    bucket = index[("zup", "x", "SAUDE")]

    assert bucket == [p_new, p_mid, p_old]


def test_build_index_skips_policies_without_client_or_benefit():
    p_ok = FakePolicy("Zup", "X", "SAUDE", date(2026, 1, 1))
    p_no_client = FakePolicy(None, "X", "SAUDE", date(2026, 1, 1))
    p_no_benefit = FakePolicy("Acme", "X", None, date(2026, 1, 1))

    index = build_policy_index([p_ok, p_no_client, p_no_benefit])
    assert len(index) == 1
    assert ("zup", "x", "SAUDE") in index
