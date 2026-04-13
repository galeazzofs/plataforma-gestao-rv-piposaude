"""Tests for migrate_legacy_policies.py"""
import pytest
from datetime import date

from app.extensions import db
from app.models import Client, Policy, BenefitType, Segment


CSV_WITH_DATE = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,25/04/2026,11\n"
)
CSV_NO_DATE = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,,3\n"
)
CSV_ZERO_MESES = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,,0\n"
)


def _make_csv(tmp_path, content):
    f = tmp_path / "test.csv"
    f.write_text(content, encoding="utf-8")
    return str(f)


@pytest.fixture
def policy(db_session):
    client = Client.find_or_create("Celcoin")
    db.session.flush()
    p = Policy(
        hubspot_ticket_id="T-CELCOIN",
        client_id=client.id,
        benefit_type=BenefitType.SAUDE,
        partner_operator="Sulamérica",
        segment=Segment.M,
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_updates_policy_with_date(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_WITH_DATE), dry_run=False)
    assert policy.initial_installments_paid == 11
    assert policy.first_payment_real == date(2026, 4, 25)


def test_infers_date_from_last_appraisal(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_NO_DATE), dry_run=False)
    # _LAST_APPRAISAL=Dec 2025, Meses_Pagos=3 → Dec - 2 months = Oct 2025
    assert policy.initial_installments_paid == 3
    assert policy.first_payment_real == date(2025, 10, 1)


def test_skips_zero_meses_no_date(policy, tmp_path):
    from migrate_legacy_policies import run
    _, skipped, _ = run(_make_csv(tmp_path, CSV_ZERO_MESES), dry_run=False)
    assert skipped == 1
    assert policy.initial_installments_paid == 0
    assert policy.first_payment_real is None


def test_dry_run_does_not_write(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_WITH_DATE), dry_run=True)
    assert policy.initial_installments_paid == 0
    assert policy.first_payment_real is None


def test_unknown_client_returns_miss(tmp_path):
    from migrate_legacy_policies import run
    csv = (
        "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
        "ClienteInexistente,Alguem,Bradesco,Saúde,25/04/2026,5\n"
    )
    updated, _, missed = run(_make_csv(tmp_path, csv), dry_run=False)
    assert updated == 0
    assert missed == 1


def test_skips_locked_policy(tmp_path, db_session):
    from migrate_legacy_policies import run
    client = Client.find_or_create("LockedCo")
    db.session.flush()
    p = Policy(
        hubspot_ticket_id="T-LOCKED",
        client_id=client.id,
        benefit_type=BenefitType.SAUDE,
        partner_operator="Bradesco",
        segment=Segment.M,
        is_locked=True,
    )
    db.session.add(p)
    db.session.flush()

    csv = (
        "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
        "LockedCo,Alguem,Bradesco,Saúde,25/04/2026,5\n"
    )
    updated, skipped, _ = run(_make_csv(tmp_path, csv), dry_run=False)
    assert updated == 0
    assert skipped == 1
    assert p.initial_installments_paid == 0  # unchanged
