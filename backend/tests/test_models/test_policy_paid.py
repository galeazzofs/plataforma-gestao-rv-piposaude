"""Comissao paga / Agenciamento pago / Total pago da apolice (EV payable scale).

Per CONTEXT.md: paid = manual pre-platform baseline (frozen) + the comissao/
agenciamento cut of every finalized apuracao (Commission.total_actual split by
NF weights). NF gross is never the paid value, only the split weight.
"""
from datetime import date
from decimal import Decimal

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType, CommissionStatus,
    Commission, FinancialImport, ImportBatch,
)


def _ev_client(session):
    ev = User(email="ev_paid@piposaude.com", name="EV Paid",
              role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()
    client = Client(name="PaidCo", name_normalized="paidco", ev_id=ev.id)
    session.add(client)
    session.flush()
    return ev, client


def _batch(session, ev):
    b = ImportBatch(filename="fin.xlsx", uploaded_by=ev.id)
    session.add(b)
    session.flush()
    return b


def _matched_nf(session, policy, batch, tipo, valor, month=1, year=2026):
    """A MATCHED financial-import row on the NF gross scale."""
    nf = FinancialImport(
        policy_id=policy.id, import_batch_id=batch.id,
        nf_valor_liquido=Decimal(str(valor)),
        nf_mes_recebimento=f"{year}-{month:02d}",
        month=month, year=year,
        tipo_receita=tipo, match_status="MATCHED",
    )
    session.add(nf)
    session.flush()
    return nf


def _policy(session, ev, client, **kwargs):
    defaults = dict(
        hubspot_apolice_id="P-1", hubspot_ticket_id="T-1",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"), closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.IN_PAYMENT,
        installments_paid=2,
    )
    defaults.update(kwargs)
    p = Policy(**defaults)
    session.add(p)
    session.flush()
    return p


class TestComissaoPaga:
    def test_comissao_paga_is_manual_baseline_without_apuracoes(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(
            db_session, ev, client,
            total_paid_comissao=Decimal("10004.00"),
            total_paid_agenciamento=Decimal("0"),
        )

        assert p.comissao_paga == Decimal("10004.00")

    def test_finalized_apuracao_adds_comissao_cut(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(db_session, ev, client, total_paid_comissao=Decimal("0"))
        # Finalized apuracao paying R$160 to the EV, no NF rows -> the whole
        # cut is treated as Comissao.
        db_session.add(Commission(
            policy_id=p.id, ev_id=ev.id, month=1, year=2026,
            total_actual=Decimal("160.00"), is_final=True,
        ))
        db_session.flush()

        assert p.comissao_paga == Decimal("160.00")

    def test_non_final_apuracao_ignored(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(db_session, ev, client, total_paid_comissao=Decimal("100.00"))
        db_session.add(Commission(
            policy_id=p.id, ev_id=ev.id, month=1, year=2026,
            total_actual=Decimal("160.00"), is_final=False,
        ))
        db_session.flush()

        # Only the frozen baseline counts; the open apuracao does not.
        assert p.comissao_paga == Decimal("100.00")

    def test_comissao_paga_splits_apuracao_by_nf_weights(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(db_session, ev, client, total_paid_comissao=Decimal("0"))
        batch = _batch(db_session, ev)
        # NF gross for the apuracao month: 1500 comissao + 500 agenciamento
        # -> comissao weight 0.75.
        _matched_nf(db_session, p, batch, "Comissão", Decimal("1500"))
        _matched_nf(db_session, p, batch, "Agenciamento", Decimal("500"))
        db_session.add(Commission(
            policy_id=p.id, ev_id=ev.id, month=1, year=2026,
            total_actual=Decimal("200.00"), is_final=True,
        ))
        db_session.flush()

        # EV cut R$200 split by weight: 200 * 0.75 = 150 to comissao.
        assert p.comissao_paga == Decimal("150.00")


class TestAgenciamentoPagoETotal:
    def test_agenciamento_pago_is_baseline_plus_split(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(db_session, ev, client,
                    total_paid_comissao=Decimal("0"),
                    total_paid_agenciamento=Decimal("30.00"))
        batch = _batch(db_session, ev)
        _matched_nf(db_session, p, batch, "Comissão", Decimal("1500"))
        _matched_nf(db_session, p, batch, "Agenciamento", Decimal("500"))
        db_session.add(Commission(
            policy_id=p.id, ev_id=ev.id, month=1, year=2026,
            total_actual=Decimal("200.00"), is_final=True,
        ))
        db_session.flush()

        # agenciamento cut 200*0.25 = 50, plus manual baseline 30 = 80
        assert p.agenciamento_pago == Decimal("80.00")

    def test_total_pago_is_comissao_plus_agenciamento(self, db_session):
        ev, client = _ev_client(db_session)
        p = _policy(db_session, ev, client,
                    total_paid_comissao=Decimal("10.00"),
                    total_paid_agenciamento=Decimal("30.00"))
        batch = _batch(db_session, ev)
        _matched_nf(db_session, p, batch, "Comissão", Decimal("1500"))
        _matched_nf(db_session, p, batch, "Agenciamento", Decimal("500"))
        db_session.add(Commission(
            policy_id=p.id, ev_id=ev.id, month=1, year=2026,
            total_actual=Decimal("200.00"), is_final=True,
        ))
        db_session.flush()

        # comissao 10+150=160 ; agenciamento 30+50=80 ; total 240
        assert p.comissao_paga == Decimal("160.00")
        assert p.agenciamento_pago == Decimal("80.00")
        assert p.total_pago == Decimal("240.00")
        assert p.total_pago == p.comissao_paga + p.agenciamento_pago
