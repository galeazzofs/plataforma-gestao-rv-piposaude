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


def test_batch_read_objects_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": []}
        c.batch_read_objects("tickets", ["T1", "T2"], ["foo", "bar"])
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v3/objects/tickets/batch/read"
        body = mock_req.call_args[1]["json"]
        assert body == {
            "properties": ["foo", "bar"],
            "inputs": [{"id": "T1"}, {"id": "T2"}],
        }


def test_batch_read_objects_parses_response():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {
            "results": [
                {"id": "T1", "properties": {"foo": "v1"}},
                {"id": "T2", "properties": {"foo": "v2"}},
            ]
        }
        result = c.batch_read_objects("tickets", ["T1", "T2"], ["foo"])
        assert result == {
            "T1": {"foo": "v1"},
            "T2": {"foo": "v2"},
        }


def test_batch_read_objects_empty_input_returns_empty_dict():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        result = c.batch_read_objects("tickets", [], ["foo"])
        assert result == {}
        mock_req.assert_not_called()


def test_batch_read_objects_chunks_above_100():
    c = _client()
    ids = [f"id-{i}" for i in range(250)]
    with patch.object(c, "_request") as mock_req:
        # Each call returns its inputs as identity dict
        def fake_req(method, path, json=None, **kwargs):
            return {
                "results": [
                    {"id": inp["id"], "properties": {"foo": inp["id"]}}
                    for inp in json["inputs"]
                ]
            }
        mock_req.side_effect = fake_req
        result = c.batch_read_objects("tickets", ids, ["foo"])
        # 250 ids → 100 + 100 + 50 = 3 calls
        assert mock_req.call_count == 3
        assert len(result) == 250
        assert result["id-0"]["foo"] == "id-0"
        assert result["id-249"]["foo"] == "id-249"


def test_get_all_owners_combines_active_and_archived_owners():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.side_effect = [
            {
                "results": [
                    {
                        "id": "1",
                        "email": "active@x",
                        "firstName": "Active",
                        "lastName": "Owner",
                        "archived": False,
                    }
                ],
                "paging": {},
            },
            {
                "results": [
                    {
                        "id": "2",
                        "email": "inactive@x",
                        "firstName": "Inactive",
                        "lastName": "Owner",
                        "archived": True,
                    }
                ],
                "paging": {},
            },
        ]

        result = c.get_all_owners()

    assert result == {
        "1": {"email": "active@x", "name": "Active Owner"},
        "2": {"email": "inactive@x", "name": "Inactive Owner"},
    }
    assert mock_req.call_args_list[0].kwargs["params"] == {"limit": 100}
    assert mock_req.call_args_list[1].kwargs["params"] == {
        "limit": 100,
        "archived": "true",
    }


def test_get_all_owners_paginates_archived_owners():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.side_effect = [
            {"results": [], "paging": {}},
            {
                "results": [
                    {
                        "id": "2",
                        "email": "inactive-1@x",
                        "firstName": "Inactive",
                        "lastName": "One",
                    }
                ],
                "paging": {"next": {"after": "archived-cursor"}},
            },
            {
                "results": [
                    {
                        "id": "3",
                        "email": "inactive-2@x",
                        "firstName": "Inactive",
                        "lastName": "Two",
                    }
                ],
                "paging": {},
            },
        ]

        result = c.get_all_owners()

    assert result["2"] == {"email": "inactive-1@x", "name": "Inactive One"}
    assert result["3"] == {"email": "inactive-2@x", "name": "Inactive Two"}
    assert mock_req.call_args_list[2].kwargs["params"] == {
        "limit": 100,
        "archived": "true",
        "after": "archived-cursor",
    }
