"""Tests for the legacy 'ticket de implantação' enrichment phase
(populates mrr_post_deploy + first_payment_prev from a separate
'implantação' ticket associated to the apolice's deal).

This phase was removed in commit caa4db1 (apolice-anchored sync rewrite)
and not re-introduced in the ticket-anchored + incremental rewrite. The
feature is tracked separately; these tests stay so the contract is visible
when the phase is brought back.
"""
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    CommissionStatus, PlatformSetting,
)
from app.modules.hubspot_sync.sync import run_sync
from app.extensions import db


pytestmark = pytest.mark.skip(
    reason="Implant ticket enrichment removed in apolice-anchored rewrite "
    "(caa4db1); will be re-added when needed."
)


_ev_counter = 0


def _seed_ev(session):
    global _ev_counter
    _ev_counter += 1
    email = f"vendedor_impl{_ev_counter}@piposaude.com"
    ev = User(email=email, name=f"Vendedor Impl {_ev_counter}",
              role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()
    return ev


class TestSyncImplantTicket:
    """Spec 3.5 -- enrich from ticket de implantacao via deal -> tickets."""

    @patch("app.modules.hubspot_sync.sync.HubSpotClient")
    def test_populates_mrr_post_deploy_and_first_payment_prev(self, MockClient, db_session):
        ev = _seed_ev(db_session)

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_client.get_all_owners.return_value = {
            "12345": {"email": ev.email, "name": ev.name},
        }

        ticket_id = "impl-test-999"

        # search_tickets returns one gongoed ticket
        mock_client.search_tickets.side_effect = [
            {
                "results": [{
                    "id": ticket_id,
                    "properties": {
                        "solicitante_demanda": "12345",
                        "cotar___segmentacao_pipo": "P (81-200)",
                        "mrr___receita_mensal": "5000",
                        "closed_date": "2026-01-15",
                        "apolice___beneficio": "Saude",
                        "cliente___nome_da_empresa": "TestCorp",
                    }
                }],
                "paging": {},
            },
        ]

        # Deal association from ticket
        # Then ticket association from deal
        mock_client.get_associations.side_effect = [
            # tickets/<ticket_id>/associations/deals
            {"results": [{"toObjectId": "D1"}]},
            # deals/D1/associations/tickets
            {"results": [
                {"toObjectId": ticket_id},   # cotacao (same ticket)
                {"toObjectId": "888"},        # implantacao (different)
            ]},
        ]

        mock_client.get_deal.return_value = {
            "properties": {
                "dealstage": "closedwon",
                "hs_v2_date_entered_8438574": "2026-02-01",
            }
        }

        mock_client.get_ticket.return_value = {
            "properties": {
                "previsao_primeiro_pagamento": "2026-03-15",
                "mrr_pos_implantacao": "4800",
            }
        }

        run_sync()

        policy = Policy.query.filter_by(hubspot_ticket_id=ticket_id).first()
        assert policy is not None
        assert policy.first_payment_prev == date(2026, 3, 15)
        assert policy.mrr_post_deploy == Decimal("4800")

    @patch("app.modules.hubspot_sync.sync.HubSpotClient")
    def test_no_implant_ticket_leaves_fields_none(self, MockClient, db_session):
        ev = _seed_ev(db_session)

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_client.get_all_owners.return_value = {
            "12345": {"email": ev.email, "name": ev.name},
        }

        ticket_id = "impl-test-no-implant-999"

        mock_client.search_tickets.side_effect = [
            {
                "results": [{
                    "id": ticket_id,
                    "properties": {
                        "solicitante_demanda": "12345",
                        "cotar___segmentacao_pipo": "P (81-200)",
                        "mrr___receita_mensal": "5000",
                        "closed_date": "2026-01-15",
                        "apolice___beneficio": "Saude",
                        "cliente___nome_da_empresa": "TestCorp",
                    }
                }],
                "paging": {},
            },
        ]

        # Deal association -- only the cotacao ticket associated
        mock_client.get_associations.side_effect = [
            {"results": [{"toObjectId": "D1"}]},
            {"results": [{"toObjectId": ticket_id}]},  # only self
        ]

        mock_client.get_deal.return_value = {
            "properties": {"dealstage": "closedwon", "hs_v2_date_entered_8438574": "2026-02-01"}
        }

        run_sync()

        policy = Policy.query.filter_by(hubspot_ticket_id=ticket_id).first()
        assert policy is not None
        assert policy.first_payment_prev is None
        assert policy.mrr_post_deploy is None
