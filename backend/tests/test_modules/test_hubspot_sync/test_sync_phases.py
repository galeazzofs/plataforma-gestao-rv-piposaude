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
