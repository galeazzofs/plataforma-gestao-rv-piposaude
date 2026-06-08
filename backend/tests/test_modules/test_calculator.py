from datetime import date
from decimal import Decimal

import pytest

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType,
    CommissionStatus, Commission, FinancialImport, ImportBatch,
    Perk, EvQuarterAchievement, CommissionPctTable, PlatformSetting,
)
from app.modules.commissions.calculator import run_monthly_appraisal
from app.extensions import db


def _seed_pct_table(session):
    """Seed commission % table v1 -- P segment, 3 tiers."""
    rows = [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "9.9999", "0.10"),
    ]
    for seg, amin, amax, pct in rows:
        session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))
    session.flush()


def _base_setup(session):
    """Create EV, client, policy, achievement, NFs for Q1/2026."""
    ev = User(email="ev1@piposaude.com", name="EV Um", role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()

    client = Client(name="Acme Corp", name_normalized="acme corp", ev_id=ev.id)
    session.add(client)
    session.flush()

    policy = Policy(
        hubspot_apolice_id="A-TICKET-100",
        hubspot_ticket_id="TICKET-100",
        numero_apolice="AP-100",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.PROJECTED,
        first_payment_real=date(2026, 2, 1),
        installments_paid=0,
        initial_installments_paid=0,
        partner_operator="Bradesco",
    )
    session.add(policy)
    session.flush()

    # Achievement for Q1/2026: 80% -> falls in 50-99.9% tier -> 8%
    ach = EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2026,
        total_mrr=Decimal("40000"), mrr_target=Decimal("50000"),
        achievement_pct=Decimal("0.8000"),
    )
    session.add(ach)
    session.flush()

    _seed_pct_table(session)

    batch = ImportBatch(filename="test.xlsx", uploaded_by=ev.id, nf_count=2, status="CONFIRMED")
    session.add(batch)
    session.flush()

    return ev, client, policy, batch


def test_legacy_clock_baseline_preserved_with_no_locked_apuracao(db_session):
    """Reset invariant: the monthly switch bakes a policy's 12-month clock into
    initial_installments_paid (migration f1e2d3c4b5a6). With no LOCKED apuração
    yet, run_monthly_appraisal must rebuild installments_paid from that baseline
    — never zero it — so 'já pago' months survive the reset."""
    _seed_pct_table(db_session)
    ev = User(email="evclock@piposaude.com", name="EV Clock",
              role=UserRole.EV, active=True)
    db_session.add(ev)
    db_session.flush()
    client = Client(name="Beta Ltda", name_normalized="beta ltda", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    policy = Policy(
        hubspot_ticket_id="TICKET-CLOCK",
        numero_apolice="AP-CLOCK",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.IN_PAYMENT,
        first_payment_real=date(2025, 8, 1),
        installments_paid=5,
        initial_installments_paid=5,  # legacy baseline baked in by the reset
    )
    db_session.add(policy)
    # Gongo-quarter achievement so the apuração's pre-check passes.
    db_session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2026,
        total_mrr=Decimal("40000"), mrr_target=Decimal("50000"),
        achievement_pct=Decimal("0.8000"),
    ))
    db_session.flush()

    # No FinancialImport for this month and no LOCKED apuração anywhere.
    run_monthly_appraisal(6, 2026)

    db_session.refresh(policy)
    assert policy.installments_paid == 5  # preserved, not reset to 0


class TestPerEmpresaFormula:
    """Spec 4.3 -- Comissao real = (Total liquido empresa - Perks) x %."""

    def test_single_policy_no_perks(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        # Two NFs totaling R$ 20,000
        for i, val in enumerate([Decimal("12000"), Decimal("8000")]):
            db_session.add(FinancialImport(
                nf_valor_liquido=val,
                nf_mes_recebimento=f"2026-0{i+2}",
                month=1, year=2026,
                import_batch_id=batch.id,
                cliente_mae="Acme Corp",
                operadora="Bradesco",
                produto="Saude",
                numero_apolice="AP-100",
                tipo_receita="Comissão",
                status_recebimento="RECEBIDO",
                data_recebimento=date(2026, 2 + i, 15),
            ))
        db_session.flush()

        run_monthly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, month=1, year=2026, is_final=False
        ).first()
        assert comm is not None
        # (12000 + 8000 - 0 perks) x 8% = 20000 x 0.08 = 1600
        assert comm.total_actual == Decimal("1600.00")

    def test_perks_subtracted_at_empresa_level(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("20000"),
            nf_mes_recebimento="2026-02",
            month=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            numero_apolice="AP-100",
            tipo_receita="Comissão",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))

        # Perk of R$ 5,000 for this client in Q1
        db_session.add(Perk(
            client_id=client.id,
            month=1, year=2026,
            amount=Decimal("5000"),
            import_batch_id=batch.id,
        ))
        db_session.flush()

        run_monthly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, month=1, year=2026, is_final=False
        ).first()
        assert comm is not None
        # (20000 - 5000) x 0.08 = 15000 x 0.08 = 1200
        assert comm.total_actual == Decimal("1200.00")

    def test_two_policies_same_client_proportional_share(self, db_session):
        ev, client, policy_saude, batch = _base_setup(db_session)

        policy_odonto = Policy(
            hubspot_apolice_id="A-TICKET-101",
            hubspot_ticket_id="TICKET-101",
            numero_apolice="AP-101",
            ev_id=ev.id,
            client_id=client.id,
            segment=Segment.P,
            benefit_type=BenefitType.ODONTO,
            mrr_projected=Decimal("3000"),
            closed_date=date(2026, 1, 20),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=date(2026, 2, 1),
            installments_paid=0,
            initial_installments_paid=0,
            partner_operator="Bradesco",
        )
        db_session.add(policy_odonto)
        db_session.flush()

        # NF for saude: R$ 10,000
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("10000"),
            nf_mes_recebimento="2026-02",
            month=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            numero_apolice="AP-100",
            tipo_receita="Comissão",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        # NF for odonto: R$ 5,000
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("5000"),
            nf_mes_recebimento="2026-02",
            month=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Odonto",
            numero_apolice="AP-101",
            tipo_receita="Comissão",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))

        # Perk R$ 3,000
        db_session.add(Perk(
            client_id=client.id, month=1, year=2026,
            amount=Decimal("3000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_monthly_appraisal(1, 2026)

        comm_saude = Commission.query.filter_by(
            policy_id=policy_saude.id, month=1, year=2026, is_final=False
        ).first()
        comm_odonto = Commission.query.filter_by(
            policy_id=policy_odonto.id, month=1, year=2026, is_final=False
        ).first()

        # Client total NF = 15000, perks = 3000, net = 12000
        # Saude share = 10000/15000 = 2/3, Odonto share = 5000/15000 = 1/3
        # Saude commission = 12000 x (2/3) x 0.08 = 640
        # Odonto commission = 12000 x (1/3) x 0.08 = 320
        assert comm_saude is not None
        assert comm_odonto is not None
        assert comm_saude.total_actual == Decimal("640.00")
        assert comm_odonto.total_actual == Decimal("320.00")

    def test_perks_greater_than_nf_yields_zero_commission(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("1000"),
            nf_mes_recebimento="2026-02",
            month=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            numero_apolice="AP-100",
            tipo_receita="Comissão",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        db_session.add(Perk(
            client_id=client.id, month=1, year=2026,
            amount=Decimal("5000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_monthly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, month=1, year=2026, is_final=False
        ).first()
        # net = max(0, 1000 - 5000) = 0 -> commission = 0
        assert comm is not None
        assert comm.total_actual == Decimal("0.00")

    def test_status_transitions_after_appraisal(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("5000"),
            nf_mes_recebimento="2026-02",
            month=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            numero_apolice="AP-100",
            tipo_receita="Comissão",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        db_session.flush()

        run_monthly_appraisal(1, 2026)

        db_session.refresh(policy)
        assert policy.commission_status == CommissionStatus.IN_PAYMENT
        assert policy.installments_paid >= 1


@pytest.mark.parametrize(
    "active,left_company",
    [
        (True, False),    # normal active EV
        (False, True),    # left the company, still commissionable
        (True, True),     # active + flagged left
        (False, False),   # deactivated / soft-deleted, NOT flagged left_company
    ],
)
def test_apuracao_includes_ev_regardless_of_account_state(
    db_session, active, left_company
):
    """Regression: an EV whose account is deactivated (active=False) but who
    was never flagged left_company — the soft-delete state produced by
    DELETE /admin/users/<id> — used to have every policy dropped by the
    policy filter, so the apuração produced zero commissions and the EV
    vanished from the review (the "todas da Bianca Kurban" report).

    Commissionability must not depend on the EV's account flags, so all four
    flag combinations must produce a commission for an eligible policy."""
    _seed_pct_table(db_session)
    ev = User(
        email="bianca@piposaude.com", name="EV Bianca",
        role=UserRole.EV, active=active, left_company=left_company,
    )
    db_session.add(ev)
    db_session.flush()
    client = Client(name="Kurban Co", name_normalized="kurban co", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    policy = Policy(
        hubspot_ticket_id="TICKET-BIANCA",
        numero_apolice="AP-BIANCA",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.PROJECTED,
        first_payment_real=date(2026, 5, 1),
        installments_paid=0, initial_installments_paid=0,
        partner_operator="Bradesco",
    )
    db_session.add(policy)
    db_session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=2, year=2026,
        total_mrr=Decimal("40000"), mrr_target=Decimal("50000"),
        achievement_pct=Decimal("0.8000"),
    ))
    batch = ImportBatch(
        filename="t.xlsx", uploaded_by=ev.id, nf_count=1, status="CONFIRMED",
    )
    db_session.add(batch)
    db_session.flush()

    db_session.add(FinancialImport(
        nf_valor_liquido=Decimal("20000"),
        nf_mes_recebimento="2026-05",
        month=5, year=2026,
        import_batch_id=batch.id,
        cliente_mae="Kurban Co", operadora="Bradesco", produto="Saude",
        numero_apolice="AP-BIANCA", tipo_receita="Comissão",
        status_recebimento="RECEBIDO", data_recebimento=date(2026, 5, 15),
    ))
    db_session.flush()

    run_monthly_appraisal(5, 2026, validate_achievements=False)

    comm = Commission.query.filter_by(
        policy_id=policy.id, month=5, year=2026,
    ).first()
    assert comm is not None, (
        f"EV apuração missing for active={active}, "
        f"left_company={left_company}"
    )


class TestApoliceFallbackMatch:
    """When a policy's numero_apolice is wrong/blank in the sync, the NF still
    matches by (Cliente Mãe, Benefício, Operadora). Real-data motivation:
    Bianca Kurban's only live policy carried a sci-notation-corrupted apólice
    ('1,10E+16'), so the apolice-number match could never land."""

    def _ev_client_policy(self, session, *, numero_apolice, ticket,
                          client_name="Kurban Co", operadora="Bradesco",
                          benefit=BenefitType.SAUDE, email="bianca@x"):
        ev = User(email=email, name="EV Bianca", role=UserRole.EV, active=True)
        session.add(ev)
        session.flush()
        client = Client(
            name=client_name,
            name_normalized=client_name.strip().lower(),
            ev_id=ev.id,
        )
        session.add(client)
        session.flush()
        policy = Policy(
            hubspot_ticket_id=ticket, numero_apolice=numero_apolice,
            ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=benefit,
            mrr_projected=Decimal("10000"), closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=None, installments_paid=0,
            initial_installments_paid=0, partner_operator=operadora,
        )
        session.add(policy)
        session.flush()
        return ev, client, policy

    def _nf(self, session, *, ev_id, numero_apolice, cliente_mae="Kurban Co",
            operadora="Bradesco", produto="Saude", val=Decimal("20000")):
        batch = ImportBatch(filename="t.xlsx", uploaded_by=ev_id,
                            nf_count=1, status="CONFIRMED")
        session.add(batch)
        session.flush()
        session.add(FinancialImport(
            nf_valor_liquido=val, nf_mes_recebimento="2026-05",
            month=5, year=2026, import_batch_id=batch.id,
            cliente_mae=cliente_mae, operadora=operadora, produto=produto,
            numero_apolice=numero_apolice, tipo_receita="Comissão",
            status_recebimento="RECEBIDO", data_recebimento=date(2026, 5, 15),
        ))
        session.flush()

    def test_fallback_recovers_corrupted_apolice_policy(self, db_session):
        _seed_pct_table(db_session)
        ev, client, policy = self._ev_client_policy(
            db_session, numero_apolice="1,10E+16", ticket="T-CORRUPT")
        # NF's apolice is the *real* operadora number, which the policy lost.
        self._nf(db_session, ev_id=ev.id, numero_apolice="999777555")

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        comm = Commission.query.filter_by(policy_id=policy.id).first()
        assert comm is not None, "fallback should match by client+benefit+operadora"

    def test_fallback_recovers_blank_apolice_policy(self, db_session):
        _seed_pct_table(db_session)
        ev, client, policy = self._ev_client_policy(
            db_session, numero_apolice=None, ticket="T-BLANK")
        self._nf(db_session, ev_id=ev.id, numero_apolice="123456")

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        assert Commission.query.filter_by(policy_id=policy.id).first() is not None

    def test_ambiguous_fallback_left_unmatched(self, db_session):
        """Two policies share (client, benefit, operadora); a fallback there
        would misattribute, so the NF must stay UNMATCHED — nobody is paid."""
        _seed_pct_table(db_session)
        ev, client, p1 = self._ev_client_policy(
            db_session, numero_apolice=None, ticket="T-AMB-1", email="a@x")
        # Second policy: same client/benefit/operadora, also blank apólice.
        p2 = Policy(
            hubspot_ticket_id="T-AMB-2", numero_apolice=None,
            ev_id=ev.id, client_id=client.id, segment=Segment.P,
            benefit_type=BenefitType.SAUDE, mrr_projected=Decimal("5000"),
            closed_date=date(2026, 1, 20),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=None, installments_paid=0,
            initial_installments_paid=0, partner_operator="Bradesco",
        )
        db_session.add(p2)
        db_session.flush()
        self._nf(db_session, ev_id=ev.id, numero_apolice="111")

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        assert Commission.query.filter_by(policy_id=p1.id).first() is None
        assert Commission.query.filter_by(policy_id=p2.id).first() is None
        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "UNMATCHED"

    def test_apolice_match_takes_precedence(self, db_session):
        """A correct apólice match must win; the fallback only fills gaps."""
        _seed_pct_table(db_session)
        ev, client, good = self._ev_client_policy(
            db_session, numero_apolice="AP-GOOD", ticket="T-GOOD", email="g@x")
        # Same client/benefit/operadora, blank apólice → fallback candidate.
        blank = Policy(
            hubspot_ticket_id="T-OTHER", numero_apolice=None,
            ev_id=ev.id, client_id=client.id, segment=Segment.P,
            benefit_type=BenefitType.SAUDE, mrr_projected=Decimal("5000"),
            closed_date=date(2026, 1, 20),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=None, installments_paid=0,
            initial_installments_paid=0, partner_operator="Bradesco",
        )
        db_session.add(blank)
        db_session.flush()
        self._nf(db_session, ev_id=ev.id, numero_apolice="AP-GOOD")

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        assert Commission.query.filter_by(policy_id=good.id).first() is not None
        assert Commission.query.filter_by(policy_id=blank.id).first() is None

    def test_partial_client_fallback_recovers_yamaha_group_name(self, db_session):
        """Real-data shape: NF says "Yamaha", HubSpot policy says
        "GRUPO YAMAHA BRASIL", and the synced apolice field is unusable text.
        The fallback can safely match because benefit+operadora leave one
        candidate only."""
        _seed_pct_table(db_session)
        ev, client, policy = self._ev_client_policy(
            db_session,
            numero_apolice="Aguardando avaliacao do time de Seguranca",
            ticket="T-YAMAHA-SUL",
            client_name="GRUPO YAMAHA BRASIL",
            operadora="Sulamerica",
        )
        self._nf(
            db_session,
            ev_id=ev.id,
            numero_apolice="67059",
            cliente_mae="Yamaha",
            operadora="Sulamerica",
            produto="Saude",
        )

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "MATCHED"
        assert nf.policy_id == policy.id
        assert Commission.query.filter_by(policy_id=policy.id).first() is not None

    def test_client_alias_setting_recovers_non_partial_name(self, db_session):
        _seed_pct_table(db_session)
        PlatformSetting.set(
            "financial_client_aliases",
            {"YMH": ["GRUPO YAMAHA BRASIL"]},
        )
        ev, client, policy = self._ev_client_policy(
            db_session,
            numero_apolice="Aguardando apolice",
            ticket="T-YAMAHA-ALIAS",
            client_name="GRUPO YAMAHA BRASIL",
            operadora="Sulamerica",
        )
        self._nf(
            db_session,
            ev_id=ev.id,
            numero_apolice="67059",
            cliente_mae="YMH",
            operadora="Sulamerica",
            produto="Saude",
        )

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "MATCHED"
        assert nf.policy_id == policy.id

    def test_partial_client_fallback_requires_unique_candidate(self, db_session):
        _seed_pct_table(db_session)
        ev, client, p1 = self._ev_client_policy(
            db_session,
            numero_apolice="Aguardando apolice",
            ticket="T-YAMAHA-1",
            client_name="GRUPO YAMAHA BRASIL",
            operadora="Sulamerica",
        )
        p2 = Policy(
            hubspot_ticket_id="T-YAMAHA-2", numero_apolice="Nao possuimos",
            ev_id=ev.id, client_id=client.id, segment=Segment.P,
            benefit_type=BenefitType.SAUDE, mrr_projected=Decimal("5000"),
            closed_date=date(2026, 1, 20),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=None, installments_paid=0,
            initial_installments_paid=0, partner_operator="Sulamerica",
        )
        db_session.add(p2)
        db_session.flush()
        self._nf(
            db_session,
            ev_id=ev.id,
            numero_apolice="67059",
            cliente_mae="Yamaha",
            operadora="Sulamerica",
            produto="Saude",
        )

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "UNMATCHED"
        assert Commission.query.filter_by(policy_id=p1.id).first() is None
        assert Commission.query.filter_by(policy_id=p2.id).first() is None


class TestCountBasedClock:
    """The 12-month clock is count-based: a policy keeps earning until it has
    12 paid Comissão months, regardless of calendar time since first payment.
    Motivation: ARVO (7/12, first payment 2025-06) was billed only from
    2026-02, but a first_payment_real + (12 − legadas) calendar window closed
    in 2025-11 and EXPIRED every real NF."""

    def _legacy_policy(self, session, *, initial_paid, fpr, apolice="AP-X",
                       ticket="T-CLK", email="clk@x"):
        ev = User(email=email, name="EV Clk", role=UserRole.EV, active=True)
        session.add(ev)
        session.flush()
        client = Client(name="Clk Co", name_normalized="clk co", ev_id=ev.id)
        session.add(client)
        session.flush()
        policy = Policy(
            hubspot_ticket_id=ticket, numero_apolice=apolice,
            ev_id=ev.id, client_id=client.id, segment=Segment.P,
            benefit_type=BenefitType.SAUDE, mrr_projected=Decimal("10000"),
            closed_date=date(2025, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            first_payment_real=fpr, installments_paid=initial_paid,
            initial_installments_paid=initial_paid, partner_operator="Bradesco",
        )
        session.add(policy)
        session.flush()
        batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id,
                            nf_count=1, status="CONFIRMED")
        session.add(batch)
        session.flush()
        return ev, client, policy, batch

    def test_legacy_policy_pays_after_old_calendar_window(self, db_session):
        _seed_pct_table(db_session)
        # 7/12, first payment 2025-06 → old window closed 2025-11. NF in 2026-05.
        ev, client, policy, batch = self._legacy_policy(
            db_session, initial_paid=7, fpr=date(2025, 6, 1), apolice="AP-ARVO")
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("10000"), nf_mes_recebimento="2026-05",
            month=5, year=2026, import_batch_id=batch.id,
            cliente_mae="Clk Co", operadora="Bradesco", produto="Saude",
            numero_apolice="AP-ARVO", tipo_receita="Comissão",
            status_recebimento="RECEBIDO", data_recebimento=date(2026, 5, 15),
        ))
        db_session.flush()

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        comm = Commission.query.filter_by(policy_id=policy.id).first()
        assert comm is not None, "legacy policy NF must not be expired by calendar"
        db_session.refresh(policy)
        assert policy.installments_paid == 8  # advanced 7 → 8, not capped/expired
        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "MATCHED"

    def test_count_cap_still_finalizes_at_twelve(self, db_session):
        """Removing the calendar window must NOT let a 12/12 policy keep
        earning — the count cap is now the sole gate."""
        _seed_pct_table(db_session)
        ev, client, policy, batch = self._legacy_policy(
            db_session, initial_paid=12, fpr=date(2025, 1, 1),
            apolice="AP-FULL", ticket="T-FULL", email="full@x")
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("10000"), nf_mes_recebimento="2026-05",
            month=5, year=2026, import_batch_id=batch.id,
            cliente_mae="Clk Co", operadora="Bradesco", produto="Saude",
            numero_apolice="AP-FULL", tipo_receita="Comissão",
            status_recebimento="RECEBIDO", data_recebimento=date(2026, 5, 15),
        ))
        db_session.flush()

        run_monthly_appraisal(5, 2026, validate_achievements=False)

        assert Commission.query.filter_by(policy_id=policy.id).first() is None
        nf = FinancialImport.query.filter_by(month=5, year=2026).first()
        assert nf.match_status == "APOLICE_FINALIZADA"
