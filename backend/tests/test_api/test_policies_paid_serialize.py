"""The policies serializer exposes the EV-payable paid figures for the tiles."""
from datetime import date
from decimal import Decimal

from app.api.v1.policies import _serialize_policy
from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType, CommissionStatus,
    Commission,
)


def test_serialize_policy_exposes_ev_scale_paid(db_session):
    ev = User(email="ev-ser@piposaude.com", name="EV", role=UserRole.EV, active=True)
    db_session.add(ev)
    db_session.flush()
    client = Client(name="SerCo", name_normalized="serco", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    p = Policy(
        hubspot_apolice_id="SER-1", hubspot_ticket_id="SER-1",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"), closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.IN_PAYMENT, installments_paid=1,
        total_paid_comissao=Decimal("100.00"),
        total_paid_agenciamento=Decimal("30.00"),
    )
    db_session.add(p)
    db_session.flush()
    # Finalized apuracao paying R$160 to the EV, no NF -> all Comissao.
    db_session.add(Commission(
        policy_id=p.id, ev_id=ev.id, month=1, year=2026,
        total_actual=Decimal("160.00"), is_final=True,
    ))
    db_session.flush()

    data = _serialize_policy(p)

    assert data["comissao_paga"] == "260.00"       # 100 baseline + 160 apuracao
    assert data["agenciamento_pago"] == "30.00"    # 30 baseline + 0
    assert data["total_pago"] == "290.00"          # 260 + 30
