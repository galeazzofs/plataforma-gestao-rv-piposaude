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
