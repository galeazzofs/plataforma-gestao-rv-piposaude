"""Tests for individual phases of the apolice-anchored sync."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.hubspot_sync.sync import (
    _fetch_apolices,
    APOLICE_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    APOLICE_PROPERTIES,
)


def test_fetch_apolices_builds_correct_search_filters():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}

    _fetch_apolices(client)

    client.search_deals.assert_called_once()
    call_kwargs = client.search_deals.call_args.kwargs
    filters = call_kwargs["filters"]
    # 2 filters AND-ed: pipeline + benefit IN list
    pipeline_filter = next(f for f in filters if f["propertyName"] == "hs_pipeline")
    assert pipeline_filter["operator"] == "EQ"
    assert pipeline_filter["value"] == APOLICE_PIPELINE_ID

    benefit_filter = next(f for f in filters if f["propertyName"] == "apolice___beneficio")
    assert benefit_filter["operator"] == "IN"
    assert set(benefit_filter["values"]) == set(VALID_BENEFITS_HUBSPOT)

    assert set(call_kwargs["properties"]) == set(APOLICE_PROPERTIES)


def test_fetch_apolices_paginates_until_exhausted():
    client = MagicMock()
    client.search_deals.side_effect = [
        {"results": [{"id": "A1"}, {"id": "A2"}], "paging": {"next": {"after": "cursor"}}},
        {"results": [{"id": "A3"}], "paging": {}},
    ]
    apolices = _fetch_apolices(client)
    assert [a["id"] for a in apolices] == ["A1", "A2", "A3"]
    assert client.search_deals.call_count == 2
    # Second call passes the cursor
    assert client.search_deals.call_args_list[1].kwargs["after"] == "cursor"


def test_fetch_apolices_empty_first_page_returns_empty():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}
    assert _fetch_apolices(client) == []


# Task 8: _fetch_apolice_tickets
from app.modules.hubspot_sync.sync import _fetch_apolice_tickets


def test_fetch_apolice_tickets_returns_first_ticket_per_apolice():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "A1": ["T1"],
        "A2": ["T2", "T2-extra"],  # multiple tickets — take first, log warn
    }
    summary = {"skipped": {"no_ticket": 0}}
    apolices = [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]

    result = _fetch_apolice_tickets(client, apolices, summary)

    assert result == {"A1": "T1", "A2": "T2"}
    # A3 had no associations
    assert summary["skipped"]["no_ticket"] == 1
    client.batch_read_associations.assert_called_once_with("deals", "tickets", ["A1", "A2", "A3"])


def test_fetch_apolice_tickets_empty_input():
    client = MagicMock()
    summary = {"skipped": {"no_ticket": 0}}
    result = _fetch_apolice_tickets(client, [], summary)
    assert result == {}
    assert summary["skipped"]["no_ticket"] == 0


# Task 9: _fetch_and_validate_tickets
from app.modules.hubspot_sync.sync import _fetch_and_validate_tickets


def _ticket_props(pipeline=None, stage=None, closed_date=None):
    """Helper: build ticket properties with defaults for valid-ticket fields."""
    return {
        "hs_pipeline": pipeline if pipeline is not None else "651307",
        "hs_pipeline_stage": stage if stage is not None else "11947921",
        "closed_date": closed_date if closed_date is not None else "2025-06-01T00:00:00Z",
        "mrr___receita_mensal": "1000",
        "solicitante_demanda": "ev@x",
        "cliente___nome_da_empresa": "ClientCo",
        "cotar___segmentacao_pipo": "M",
    }


def _new_summary():
    return {"skipped": {"no_ticket": 0, "wrong_pipeline": 0,
                        "not_gongo": 0, "too_old": 0, "no_default_deal": 0}}


def test_validate_tickets_keeps_valid():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(),
        "T2": _ticket_props(),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1", "T2"], summary)
    assert set(result.keys()) == {"T1", "T2"}
    # batch_read_objects was called with TICKET_PROPERTIES
    call = client.batch_read_objects.call_args
    assert call.args[0] == "tickets"
    assert set(call.args[1]) == {"T1", "T2"}
    from app.modules.hubspot_sync.sync import TICKET_PROPERTIES
    assert call.args[2] == TICKET_PROPERTIES


def test_validate_tickets_drops_wrong_pipeline():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(pipeline="999999"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["wrong_pipeline"] == 1


def test_validate_tickets_drops_wrong_stage():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(stage="555"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["not_gongo"] == 1


def test_validate_tickets_drops_too_old():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date="2024-01-15T00:00:00Z"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_drops_missing_closed_date():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date=""),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, [], summary)
    assert result == {}
    client.batch_read_objects.assert_not_called()


# Task 10: _filter_tickets_with_default_deal
from app.modules.hubspot_sync.sync import _filter_tickets_with_default_deal


def test_filter_tickets_keeps_those_with_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
        "T2": ["D2", "D3"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "default"},
        "D2": {"hs_pipeline": "999999"},  # not default
        "D3": {"hs_pipeline": "default"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1", "T2"], summary)
    assert result == {"T1", "T2"}  # T2 has at least one default deal
    assert summary["skipped"]["no_default_deal"] == 0


def test_filter_tickets_drops_those_without_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "999999"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_drops_those_without_any_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {}  # T1 has no deals
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, [], summary)
    assert result == set()
    client.batch_read_associations.assert_not_called()
