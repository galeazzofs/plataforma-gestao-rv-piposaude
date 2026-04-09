from datetime import date
from decimal import Decimal

from app.models import Policy, CommissionStatus, Segment, BenefitType, Client
from app.modules.commissions.status import update_policy_statuses
from app.extensions import db


def _make_client(session, name="Acme Corp"):
    c = Client(name=name, name_normalized=name.strip().lower())
    session.add(c)
    session.flush()
    return c


def _make_policy(session, client, **overrides):
    defaults = dict(
        hubspot_ticket_id=f"T-{id(overrides)}",
        client_id=client.id,
        segment=Segment.P,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("5000"),
        commission_status=CommissionStatus.PROJECTED,
        closed_date=date(2026, 1, 15),
        installments_paid=0,
        first_payment_real=None,
    )
    defaults.update(overrides)
    p = Policy(**defaults)
    session.add(p)
    session.flush()
    return p


class TestUpdatePolicyStatuses:
    """Spec §3.3 — lifecycle: PROJECTED → IN_PAYMENT → SETTLED."""

    def test_projected_stays_when_no_payments(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(db_session, client, installments_paid=0)

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.PROJECTED

    def test_transitions_to_in_payment_when_first_payment_real_set(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            installments_paid=1,
            first_payment_real=date(2026, 4, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.IN_PAYMENT

    def test_transitions_to_settled_at_12_installments(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            installments_paid=12,
            first_payment_real=date(2026, 1, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.SETTLED

    def test_does_not_touch_cancelled(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            commission_status=CommissionStatus.CANCELLED,
            installments_paid=5,
            first_payment_real=date(2026, 1, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.CANCELLED

    def test_infers_first_payment_real_from_nf_dates(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(db_session, client, installments_paid=1)

        nf_dates = {p.id: date(2026, 3, 15)}
        update_policy_statuses([p], earliest_nf_dates=nf_dates)

        assert p.first_payment_real == date(2026, 3, 15)
        assert p.commission_status == CommissionStatus.IN_PAYMENT
