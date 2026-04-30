from decimal import Decimal
from app.modules.financial.validator import validate_nf_rows, validate_perk_rows
from app.models import Policy, User, UserRole, Client
from app.extensions import db


def test_validate_nf_rows_valid(db_session):
    ev = User(email="ev@piposaude.com", name="EV", role=UserRole.EV)
    db_session.add(ev)
    db_session.flush()
    client = Client(name="Acme", name_normalized="acme", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    policy = Policy(hubspot_apolice_id="A-T-1", hubspot_ticket_id="T-1", ev_id=ev.id, client_id=client.id)
    db_session.add(policy)
    db_session.flush()

    rows = [{"hubspot_ticket_id": "T-1", "nf_valor_liquido": 5000, "nf_mes_recebimento": "2026-01", "_row": 2}]
    valid, errors = validate_nf_rows(rows)
    assert len(valid) == 1
    assert len(errors) == 0


def test_validate_nf_rows_unknown_ticket(db_session):
    rows = [{"hubspot_ticket_id": "UNKNOWN", "nf_valor_liquido": 5000, "nf_mes_recebimento": "2026-01", "_row": 2}]
    valid, errors = validate_nf_rows(rows)
    assert len(valid) == 0
    assert len(errors) == 1
    assert "not found" in errors[0]["message"].lower()
