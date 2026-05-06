from datetime import date
from decimal import Decimal

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType,
    CommissionStatus, Commission, FinancialImport, ImportBatch,
    Perk, EvQuarterAchievement, CommissionPctTable,
)
from app.modules.commissions.calculator import run_quarterly_appraisal
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


class TestPerEmpresaFormula:
    """Spec 4.3 -- Comissao real = (Total liquido empresa - Perks) x %."""

    def test_single_policy_no_perks(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        # Two NFs totaling R$ 20,000
        for i, val in enumerate([Decimal("12000"), Decimal("8000")]):
            db_session.add(FinancialImport(
                nf_valor_liquido=val,
                nf_mes_recebimento=f"2026-0{i+2}",
                quarter=1, year=2026,
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

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
        ).first()
        assert comm is not None
        # (12000 + 8000 - 0 perks) x 8% = 20000 x 0.08 = 1600
        assert comm.total_actual == Decimal("1600.00")

    def test_perks_subtracted_at_empresa_level(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("20000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
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
            quarter=1, year=2026,
            amount=Decimal("5000"),
            import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
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
            quarter=1, year=2026,
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
            quarter=1, year=2026,
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
            client_id=client.id, quarter=1, year=2026,
            amount=Decimal("3000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm_saude = Commission.query.filter_by(
            policy_id=policy_saude.id, quarter=1, year=2026, is_final=False
        ).first()
        comm_odonto = Commission.query.filter_by(
            policy_id=policy_odonto.id, quarter=1, year=2026, is_final=False
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
            quarter=1, year=2026,
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
            client_id=client.id, quarter=1, year=2026,
            amount=Decimal("5000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
        ).first()
        # net = max(0, 1000 - 5000) = 0 -> commission = 0
        assert comm is not None
        assert comm.total_actual == Decimal("0.00")

    def test_status_transitions_after_appraisal(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("5000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
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

        run_quarterly_appraisal(1, 2026)

        db_session.refresh(policy)
        assert policy.commission_status == CommissionStatus.IN_PAYMENT
        assert policy.installments_paid >= 1
