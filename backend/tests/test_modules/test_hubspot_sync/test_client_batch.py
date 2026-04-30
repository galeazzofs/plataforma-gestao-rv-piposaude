"""Tests for new HubSpotClient batch helpers."""
from unittest.mock import patch, MagicMock
from app.modules.hubspot_sync.client import HubSpotClient


def _client():
    with patch("app.modules.hubspot_sync.client.current_app") as mock_app:
        mock_app.config = {"HUBSPOT_TOKEN": "test-token"}
        return HubSpotClient()


def test_search_deals_calls_correct_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": [], "paging": {}}
        c.search_deals(
            filters=[{"propertyName": "hs_pipeline", "operator": "EQ", "value": "X"}],
            properties=["foo", "bar"],
            limit=50,
        )
        mock_req.assert_called_once()
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v3/objects/deals/search"
        body = mock_req.call_args[1]["json"]
        assert body["filterGroups"] == [{"filters": [{"propertyName": "hs_pipeline", "operator": "EQ", "value": "X"}]}]
        assert body["properties"] == ["foo", "bar"]
        assert body["limit"] == 50
        assert "after" not in body


def test_search_deals_passes_pagination_cursor():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": [], "paging": {}}
        c.search_deals(filters=[], properties=[], after="cursor-123")
        body = mock_req.call_args[1]["json"]
        assert body["after"] == "cursor-123"


def test_batch_read_associations_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": []}
        c.batch_read_associations("deals", "tickets", ["123", "456"])
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v4/associations/deals/tickets/batch/read"
        body = mock_req.call_args[1]["json"]
        assert body == {"inputs": [{"id": "123"}, {"id": "456"}]}


def test_batch_read_associations_parses_response():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {
            "results": [
                {"from": {"id": "123"}, "to": [{"toObjectId": "T1"}, {"toObjectId": "T2"}]},
                {"from": {"id": "456"}, "to": [{"toObjectId": "T3"}]},
            ]
        }
        result = c.batch_read_associations("deals", "tickets", ["123", "456"])
        assert result == {"123": ["T1", "T2"], "456": ["T3"]}


def test_batch_read_associations_empty_input_returns_empty_dict():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        result = c.batch_read_associations("deals", "tickets", [])
        assert result == {}
        mock_req.assert_not_called()
