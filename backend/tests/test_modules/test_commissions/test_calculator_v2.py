"""Tests for run_quarterly_appraisal (new implementation)."""
import pytest
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement, Segment,
    BenefitType, FinancialImport, ImportBatch, Commission, CommissionPctTable,
)


@pytest.fixture(autouse=True)
def _seed_pct_table(db_session):
    """Seed minimal commission_pct_table for M segment before each test."""
    for seg, mn, mx, pct in [
        ('M', '0.0000', '0.4999', '0.05'),
        ('M', '0.5000', '0.9999', '0.06'),
        ('M', '1.0000', '99.9999', '0.08'),
    ]:
        db.session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(mn), achievement_max=Decimal(mx),
            commission_pct=Decimal(pct), valid_from=date.today(),
        ))
    db.session.flush()
    yield


def _setup_basic_scenario():
    """One active EV, one client, one policy gongado in Q4/2025,
    one NF received in Q1/2026."""
    ev = User(email="ev@x", name="EV One", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    client = Client.find_or_create("Zup")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-T1",
        hubspot_ticket_id="T1",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 11, 15),  # Q4/2025
        first_payment_real=date(2025, 12, 1),
        installments_paid=0,
        initial_installments_paid=0,
    )
    db.session.add(policy)
    db.session.flush()

    ach = EvQuarterAchievement(
        ev_id=ev.id,
        quarter=4,
        year=2025,
        achievement_pct=Decimal('0.75'),  # 75% → 0.06 for M
    )
    db.session.add(ach)
    db.session.flush()

    batch = ImportBatch(
        filename="test.xlsx", uploaded_by=ev.id, status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id,
        quarter=1,
        year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup',
        operadora='SulAmerica',
        produto='Saúde',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    return ev, policy, nf


# ── Happy path ────────────────────────────────────────────────


def test_happy_path_matches_and_calculates_commission(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'MATCHED'
    assert nf.policy_id == policy.id

    comm = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first()
    assert comm is not None
    # 1000 * 0.06 (M, 50-99.9% faixa) = 60.00
    assert comm.total_actual == Decimal('60.00')
    assert comm.is_final is False


# ── Vigência edge cases ───────────────────────────────────────


def test_pre_vigencia_when_nf_before_first_payment(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2026, 6, 1)  # later than NF
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRE_VIGENCIA'

    comm = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first()
    assert comm is None


def test_expired_when_nf_after_window(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2024, 1, 1)  # 2 years ago
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'EXPIRED'


def test_initial_installments_paid_shrinks_window(db_session):
    """initial=10 shrinks the window to 12-10=2 months from first_payment_real."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2025, 12, 1)
    policy.initial_installments_paid = 10
    db.session.flush()

    # NF 2026-02-15 > 2025-12-01 + 2 months (2026-02-01) → EXPIRED
    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'EXPIRED'


# ── Unmatched / unsupported ───────────────────────────────────


def test_unmatched_when_no_policy(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()
    batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id,
        quarter=1,
        year=2026,
        nf_valor_liquido=Decimal('500.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Unknown Co',
        operadora='X',
        produto='Saúde',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'
    assert nf.policy_id is None


def test_produto_nao_suportado(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.produto = 'Mental'
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRODUTO_NAO_SUPORTADO'


# ── Idempotency / re-run ──────────────────────────────────────


def test_recalc_is_idempotent(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()

    run_quarterly_appraisal(1, 2026)
    first = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first().total_actual

    run_quarterly_appraisal(1, 2026)
    second = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first().total_actual

    assert first == second


def test_recalc_does_not_touch_locked_commissions(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    # Pre-create a LOCKED commission with a different value
    locked = Commission(
        policy_id=policy.id, ev_id=ev.id, quarter=1, year=2026,
        segment='M', achievement_pct=Decimal('0.5'),
        commission_pct=Decimal('0.06'), commission_pct_version=1,
        monthly_actual=Decimal('99.00'), total_actual=Decimal('99.00'),
        is_final=True,
    )
    db.session.add(locked)
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    locked_after = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026, is_final=True
    ).first()
    assert locked_after.total_actual == Decimal('99.00')


def test_missing_achievement_raises_before_any_writes(db_session):
    from app.modules.commissions.calculator import (
        run_quarterly_appraisal, MissingAchievementsError,
    )

    ev, policy, nf = _setup_basic_scenario()
    EvQuarterAchievement.query.delete()
    db.session.flush()

    with pytest.raises(MissingAchievementsError):
        run_quarterly_appraisal(1, 2026)

    assert Commission.query.count() == 0
    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'  # untouched


# ── Negative values (estornos) ────────────────────────────────


def test_negative_nf_subtracts_from_commission(db_session):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    second_nf = FinancialImport(
        import_batch_id=nf.import_batch_id,
        quarter=1,
        year=2026,
        nf_valor_liquido=Decimal('-300.00'),
        nf_mes_recebimento='2026-03',
        cliente_mae='Zup',
        operadora='SulAmerica',
        produto='Saúde',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 3, 10),
        match_status='UNMATCHED',
    )
    db.session.add(second_nf)
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    # 1000 * 0.06 = 60.00, -300 * 0.06 = -18.00, total = 42.00
    comm = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('42.00')


# ── Snapshot uses gongo quarter, not apuração quarter ─────────


def test_snapshot_uses_gongo_quarter_not_apuracao_quarter(db_session):
    """Policy gongado in Q4/2025 → apuração Q1/2026 must use Q4/2025 achievement."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()

    # Rewrite achievements: Q4/2025 = 30% (should be used), Q1/2026 = 150% (must NOT be used)
    EvQuarterAchievement.query.filter_by(ev_id=ev.id).delete()
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025, achievement_pct=Decimal('0.30'),
    ))
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2026, achievement_pct=Decimal('1.50'),
    ))
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    # Should use Q4/2025 (30%) → M faixa <50% → 5%
    # 1000 * 0.05 = 50.00 (NOT 80.00 that Q1/2026 150% would give)
    comm = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('50.00')
    assert comm.achievement_pct == Decimal('0.3000')


# ── Multi-policy (same key, picks most recent in window) ──────


def test_multi_policy_picks_most_recent_within_window(db_session):
    """Two policies with same (cliente, operadora, produto). The NF
    should match the more recent one whose vigência covers the NF date."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()
    client = Client.find_or_create("Zup")
    db.session.flush()

    p_old = Policy(
        hubspot_apolice_id="A-OLD", hubspot_ticket_id="OLD", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 3, 1),
        first_payment_real=date(2025, 4, 1),
    )
    p_new = Policy(
        hubspot_apolice_id="A-NEW", hubspot_ticket_id="NEW", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 12, 1),
        first_payment_real=date(2026, 1, 1),
    )
    db.session.add_all([p_old, p_new])
    db.session.flush()

    # Achievements for both gongo quarters
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2025, achievement_pct=Decimal('0.30'),
    ))
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025, achievement_pct=Decimal('0.80'),
    ))
    db.session.flush()

    batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, quarter=1, year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup', operadora='SulAmerica', produto='Saúde',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.policy_id == p_new.id

    # Q4/2025 achievement 80% → M faixa 50-99.9% → 6%
    # 1000 * 0.06 = 60.00
    comm = Commission.query.filter_by(
        policy_id=p_new.id, quarter=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('60.00')
