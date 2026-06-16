def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_ready_returns_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json["status"] == "ready"


def test_ready_failure_does_not_leak_internals(client, monkeypatch):
    """A DB outage must yield a generic 503 — connection-string fragments or
    driver internals in the body would be exposed unauthenticated."""

    class _BrokenDb:
        class session:  # noqa: N801 — mimics db.session attribute access
            @staticmethod
            def execute(*args, **kwargs):
                raise Exception("postgresql://user:supersecret@db:5432/x")

        @staticmethod
        def text(query):
            return query

    monkeypatch.setattr("app.api.v1.health.db", _BrokenDb)

    response = client.get("/ready")
    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "supersecret" not in body
    assert response.json["status"] == "not_ready"
