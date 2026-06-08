"""Tests for run_monthly_appraisal (new implementation)."""
import pytest
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement, Segment,
    BenefitType, FinancialImport, ImportBatch, Commission, CommissionPctTable,
    CommissionStatus,
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
        numero_apolice="AP-001",
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
        month=1,
        year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup',
        operadora='SulAmerica',
        produto='Saúde',
        numero_apolice='AP-001',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    return ev, policy, nf


def _add_nf(policy, batch_id, *, amount, month, received_on, tipo="Comissão"):
    nf = FinancialImport(
        import_batch_id=batch_id,
        month=1,
        year=2026,
        nf_valor_liquido=Decimal(str(amount)),
        nf_mes_recebimento=month,
        cliente_mae=policy.client.name,
        operadora=policy.partner_operator,
        produto="Saúde",
        numero_apolice=policy.numero_apolice,
        tipo_receita=tipo,
        status_recebimento="RECEBIDO",
        data_recebimento=received_on,
        match_status="UNMATCHED",
    )
    db.session.add(nf)
    db.session.flush()
    return nf


# ── Happy path ────────────────────────────────────────────────


def test_happy_path_matches_and_calculates_commission(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'MATCHED'
    assert nf.policy_id == policy.id

    comm = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first()
    assert comm is not None
    # 1000 * 0.06 (M, 50-99.9% faixa) = 60.00
    assert comm.total_actual == Decimal('60.00')
    assert comm.is_final is False


# ── Vigência edge cases ───────────────────────────────────────


def test_pre_vigencia_when_nf_before_first_payment(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2026, 6, 1)  # later than NF
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRE_VIGENCIA'

    comm = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first()
    assert comm is None


def test_nf_long_after_first_payment_still_pays(db_session):
    """Count-based clock: a policy below 12/12 keeps earning no matter how
    long ago the first payment was. Previously a first_payment_real + 12
    calendar window expired anything later — which dropped legitimate NFs for
    policies billed long after their first payment."""
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2024, 1, 1)  # 2 years before the NF
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'MATCHED'
    comm = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first()
    assert comm is not None and comm.total_actual == Decimal('60.00')
    db.session.refresh(policy)
    assert policy.installments_paid == 1


def test_legacy_installments_do_not_close_window(db_session):
    """Count-based clock: legacy parcelas raise the starting count but never
    create a calendar deadline. A 10/12 policy still has 2 months to earn,
    whenever the NFs arrive. Previously initial=10 shrank the window to
    first_payment_real + 2 months and expired anything after."""
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2025, 12, 1)
    policy.initial_installments_paid = 10
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'MATCHED'
    db.session.refresh(policy)
    assert policy.installments_paid == 11  # 10 → 11, still below the 12 cap


# ── Unmatched / unsupported ───────────────────────────────────


def test_unmatched_when_no_policy(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()
    batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id,
        month=1,
        year=2026,
        nf_valor_liquido=Decimal('500.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Unknown Co',
        operadora='X',
        produto='Saúde',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'
    assert nf.policy_id is None


def test_produto_nao_suportado(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.produto = 'Mental'
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRODUTO_NAO_SUPORTADO'


# ── Idempotency / re-run ──────────────────────────────────────


def test_recalc_is_idempotent(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()

    run_monthly_appraisal(1, 2026)
    first = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first().total_actual

    run_monthly_appraisal(1, 2026)
    second = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first().total_actual

    assert first == second


def test_recalc_does_not_touch_locked_commissions(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    # Pre-create a LOCKED commission with a different value
    locked = Commission(
        policy_id=policy.id, ev_id=ev.id, month=1, year=2026,
        segment='M', achievement_pct=Decimal('0.5'),
        commission_pct=Decimal('0.06'), commission_pct_version=1,
        monthly_actual=Decimal('99.00'), total_actual=Decimal('99.00'),
        is_final=True,
    )
    db.session.add(locked)
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    locked_after = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026, is_final=True
    ).first()
    assert locked_after.total_actual == Decimal('99.00')


def test_missing_achievement_raises_before_any_writes(db_session):
    from app.modules.commissions.calculator import (
        run_monthly_appraisal, MissingAchievementsError,
    )

    ev, policy, nf = _setup_basic_scenario()
    EvQuarterAchievement.query.delete()
    db.session.flush()

    with pytest.raises(MissingAchievementsError):
        run_monthly_appraisal(1, 2026)

    assert Commission.query.count() == 0
    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'  # untouched


# ── Negative values (estornos) ────────────────────────────────


def test_negative_nf_subtracts_from_commission(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    second_nf = FinancialImport(
        import_batch_id=nf.import_batch_id,
        month=1,
        year=2026,
        nf_valor_liquido=Decimal('-300.00'),
        nf_mes_recebimento='2026-03',
        cliente_mae='Zup',
        operadora='SulAmerica',
        produto='Saúde',
        numero_apolice='AP-001',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 3, 10),
        match_status='UNMATCHED',
    )
    db.session.add(second_nf)
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    # 1000 * 0.06 = 60.00, -300 * 0.06 = -18.00, total = 42.00
    comm = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('42.00')


def test_agenciamento_alone_pays_but_does_not_start_commission_clock(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.tipo_receita = "Agenciamento"
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(policy)
    db.session.refresh(nf)
    comm = Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first()
    assert nf.match_status == "MATCHED"
    assert comm.total_actual == Decimal("60.00")
    assert policy.installments_paid == 0
    assert policy.commission_status == CommissionStatus.PROJECTED


def test_comissao_and_agenciamento_same_month_pay_both_and_count_one_month(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    _add_nf(
        policy,
        nf.import_batch_id,
        amount="200.00",
        month="2026-02",
        received_on=date(2026, 2, 20),
        tipo="Agenciamento",
    )

    run_monthly_appraisal(1, 2026)

    db.session.refresh(policy)
    comm = Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first()
    assert comm.total_actual == Decimal("72.00")
    assert policy.installments_paid == 1


def test_monthly_net_comissao_must_be_positive_to_count_clock(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.nf_valor_liquido = Decimal("100.00")
    _add_nf(
        policy,
        nf.import_batch_id,
        amount="-120.00",
        month="2026-02",
        received_on=date(2026, 2, 20),
        tipo="Comissão",
    )
    _add_nf(
        policy,
        nf.import_batch_id,
        amount="50.00",
        month="2026-02",
        received_on=date(2026, 2, 21),
        tipo="Agenciamento",
    )

    run_monthly_appraisal(1, 2026)

    db.session.refresh(policy)
    comm = Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first()
    assert comm.total_actual == Decimal("1.80")
    assert policy.installments_paid == 0


def test_non_commissionable_revenue_does_not_enter_appraisal(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.tipo_receita = "Patrocínio"
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == "RECEITA_NAO_COMISSIONAVEL"
    assert Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first() is None


def test_eleventh_month_april_closes_and_may_goes_to_finalized_bucket(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2026, 4, 1)
    policy.initial_installments_paid = 11
    policy.installments_paid = 11
    nf.nf_mes_recebimento = "2026-04"
    nf.data_recebimento = date(2026, 4, 15)
    may_nf = _add_nf(
        policy,
        nf.import_batch_id,
        amount="1000.00",
        month="2026-05",
        received_on=date(2026, 5, 15),
        tipo="Comissão",
    )
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(policy)
    db.session.refresh(nf)
    db.session.refresh(may_nf)
    comm = Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first()
    assert nf.match_status == "MATCHED"
    assert may_nf.match_status == "APOLICE_FINALIZADA"
    assert comm.total_actual == Decimal("60.00")
    assert policy.installments_paid == 12
    assert policy.commission_status == CommissionStatus.SETTLED


def test_twelfth_month_pays_agenciamento_in_same_month_before_settling(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2026, 4, 1)
    policy.initial_installments_paid = 11
    policy.installments_paid = 11
    nf.nf_mes_recebimento = "2026-04"
    nf.data_recebimento = date(2026, 4, 15)
    _add_nf(
        policy,
        nf.import_batch_id,
        amount="200.00",
        month="2026-04",
        received_on=date(2026, 4, 20),
        tipo="Agenciamento",
    )
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(policy)
    comm = Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first()
    assert comm.total_actual == Decimal("72.00")
    assert policy.commission_status == CommissionStatus.SETTLED


def test_policy_already_twelve_of_twelve_sends_all_rows_to_finalized_bucket(db_session):
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.initial_installments_paid = 12
    policy.installments_paid = 12
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == "APOLICE_FINALIZADA"
    assert Commission.query.filter_by(policy_id=policy.id, month=1, year=2026).first() is None


# ── Snapshot uses gongo quarter, not apuração quarter ─────────


def test_snapshot_uses_gongo_quarter_not_apuracao_quarter(db_session):
    """Policy gongado in Q4/2025 → apuração Q1/2026 must use Q4/2025 achievement."""
    from app.modules.commissions.calculator import run_monthly_appraisal

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

    run_monthly_appraisal(1, 2026)

    # Should use Q4/2025 (30%) → M faixa <50% → 5%
    # 1000 * 0.05 = 50.00 (NOT 80.00 that Q1/2026 150% would give)
    comm = Commission.query.filter_by(
        policy_id=policy.id, month=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('50.00')
    assert comm.achievement_pct == Decimal('0.3000')


# ── Multi-policy (same key, picks most recent in window) ──────


def test_multi_policy_picks_most_recent_within_window(db_session):
    """Two policies with same (cliente, operadora, produto). The NF
    should match the more recent one whose vigência covers the NF date."""
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()
    client = Client.find_or_create("Zup")
    db.session.flush()

    # Both policies share the same numero_apolice so the matcher returns
    # both as candidates and the calculator's vigência logic picks the
    # most recent one whose window covers the NF date.
    p_old = Policy(
        hubspot_apolice_id="A-OLD", hubspot_ticket_id="OLD", numero_apolice="AP-SHARED",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 3, 1),
        first_payment_real=date(2025, 4, 1),
    )
    p_new = Policy(
        hubspot_apolice_id="A-NEW", hubspot_ticket_id="NEW", numero_apolice="AP-SHARED",
        ev_id=ev.id, client_id=client.id,
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
        import_batch_id=batch.id, month=1, year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup', operadora='SulAmerica', produto='Saúde',
        numero_apolice='AP-SHARED',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf)
    db.session.flush()

    run_monthly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.policy_id == p_new.id

    # Q4/2025 achievement 80% → M faixa 50-99.9% → 6%
    # 1000 * 0.06 = 60.00
    comm = Commission.query.filter_by(
        policy_id=p_new.id, month=1, year=2026
    ).first()
    assert comm.total_actual == Decimal('60.00')


def test_auto_sets_first_payment_real_when_none(db_session):
    """Policy with no first_payment_real: first matched NF sets it and counts as month 1."""
    from app.modules.commissions.calculator import run_monthly_appraisal

    ev = User(email='ev@autodetect', name='EV AutoDetect', role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    client = Client.find_or_create('AutoDetect Co')
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id='A-AUTODETECT',
        hubspot_ticket_id='T-AUTODETECT',
        numero_apolice='AP-AUTODETECT',
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        partner_operator='TestOp',
        closed_date=date(2025, 11, 1),  # Q4/2025 gongo
        first_payment_real=None,        # ← no vigência set yet
        installments_paid=0,
        initial_installments_paid=0,
    )
    db.session.add(policy)
    db.session.flush()

    db.session.add(EvQuarterAchievement(
        ev_id=ev.id,
        quarter=4,
        year=2025,
        achievement_pct=Decimal('0.75'),
    ))
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id,
        quarter=1,
        year=2026,
        achievement_pct=Decimal('0.75'),
    ))

    batch = ImportBatch(filename='auto.xlsx', uploaded_by=ev.id, status='CONFIRMED')
    db.session.add(batch)
    db.session.flush()

    db.session.add(FinancialImport(
        import_batch_id=batch.id,
        month=1,
        year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-01',
        cliente_mae='AutoDetect Co',
        operadora='TestOp',
        produto='Saúde',
        numero_apolice='AP-AUTODETECT',
        tipo_receita='Comissão',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 1, 15),
        match_status='UNMATCHED',
    ))
    db.session.flush()

    run_monthly_appraisal(month=1, year=2026)

    db.session.refresh(policy)
    assert policy.first_payment_real == date(2026, 1, 15)
    assert policy.installments_paid == 1
    nf = db.session.query(FinancialImport).filter_by(cliente_mae='AutoDetect Co').first()
    assert nf.match_status == 'MATCHED'
