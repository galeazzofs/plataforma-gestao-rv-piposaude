"""Tests for HubSpot → CN realized values sync (cn_realized).

Matching rule under test: a deal's `cn` property (a free-text CN name)
is normalized and looked up against active User.name (role=CN).
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
import uuid

from app.extensions import db
from app.models import User, UserRole, CnNivel, CnPorte
from app.modules.hubspot_sync.cn_realized import (
    fetch_cn_realized, fetch_cn_realized_with_meta, _month_bounds, _to_ms,
)


def _make_cn(name, email=None):
    suffix = uuid.uuid4().hex[:6]
    u = User(
        email=email or f"{name.lower().replace(' ', '.')}-{suffix}@piposaude.com",
        name=name, role=UserRole.CN, active=True,
        nivel=CnNivel.CN1, porte=CnPorte.M,
        salario_base=Decimal("3000"),
    )
    db.session.add(u)
    db.session.flush()
    return u


def _fake_deal(deal_id, cn_name, vidas=None, sao_date_iso="2026-04-15"):
    return {
        "id": str(deal_id),
        "properties": {
            "cn": cn_name,
            "numero_de_vidas_previstas": str(vidas) if vidas is not None else None,
            "hs_v2_date_entered_9102669": sao_date_iso,
            "pipeline": "default",
        },
    }


def test_month_bounds_normal_month():
    assert _month_bounds(4, 2026) == (date(2026, 4, 1), date(2026, 5, 1))


def test_month_bounds_december_rolls_over():
    assert _month_bounds(12, 2026) == (date(2026, 12, 1), date(2027, 1, 1))


def test_to_ms_is_utc_midnight():
    from datetime import datetime, timezone
    expected = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert _to_ms(date(2026, 4, 1)) == expected


def test_aggregates_count_and_vidas_per_cn(db_session):
    ana = _make_cn("Ana CN")
    bob = _make_cn("Bob CN")

    client = MagicMock()
    client.search_deals.return_value = {
        "results": [
            _fake_deal("d1", "Ana CN", vidas=10),
            _fake_deal("d2", "Ana CN", vidas=15),
            _fake_deal("d3", "Bob CN", vidas=8),
        ],
        "paging": {},
    }

    result, meta = fetch_cn_realized_with_meta(4, 2026, client=client)

    assert result[ana.id]["sao_realizado"] == Decimal("2")
    assert result[ana.id]["vidas_realizado"] == Decimal("25")
    assert result[bob.id]["sao_realizado"] == Decimal("1")
    assert result[bob.id]["vidas_realizado"] == Decimal("8")
    assert meta == {"deals_scanned": 3, "unresolved": 0}


def test_matches_case_and_accent_insensitive(db_session):
    """Domain expert types names freely in HubSpot — normalize before
    matching so 'ANA SOUZA' / 'ana souza' / 'Ana Sousa' all hit the same
    User('Ana Souza')."""
    ana = _make_cn("Ana Souza")

    client = MagicMock()
    client.search_deals.return_value = {
        "results": [
            _fake_deal("d1", "ANA SOUZA",  vidas=1),
            _fake_deal("d2", "ana souza",  vidas=2),
            _fake_deal("d3", "Ana Sóuza",  vidas=3),  # extra accent
        ],
        "paging": {},
    }

    result = fetch_cn_realized(4, 2026, client=client)
    assert result[ana.id]["sao_realizado"] == Decimal("3")
    assert result[ana.id]["vidas_realizado"] == Decimal("6")


def test_missing_vidas_property_treated_as_zero(db_session):
    vera = _make_cn("Vera CN")
    client = MagicMock()
    client.search_deals.return_value = {
        "results": [
            _fake_deal("d1", "Vera CN", vidas=None),
            _fake_deal("d2", "Vera CN", vidas=5),
        ],
        "paging": {},
    }
    result, meta = fetch_cn_realized_with_meta(4, 2026, client=client)
    assert result[vera.id]["sao_realizado"] == Decimal("2")
    assert result[vera.id]["vidas_realizado"] == Decimal("5")
    assert meta["unresolved"] == 0


def test_deals_with_unknown_or_empty_cn_counted_as_unresolved(db_session):
    carlos = _make_cn("Carlos CN")
    client = MagicMock()
    client.search_deals.return_value = {
        "results": [
            _fake_deal("d1", "Carlos CN",   vidas=10),
            _fake_deal("d2", "Quem É Esse", vidas=20),   # name not in DB
            _fake_deal("d3", None,          vidas=30),   # missing cn prop
            _fake_deal("d4", "",            vidas=40),   # empty cn prop
        ],
        "paging": {},
    }
    result, meta = fetch_cn_realized_with_meta(4, 2026, client=client)
    assert result == {carlos.id: {
        "sao_realizado": Decimal("1"),
        "vidas_realizado": Decimal("10"),
    }}
    assert meta["unresolved"] == 3
    assert meta["deals_scanned"] == 4


def test_empty_deals_returns_empty_dict_and_zero_meta(db_session):
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}
    result, meta = fetch_cn_realized_with_meta(4, 2026, client=client)
    assert result == {}
    assert meta == {"deals_scanned": 0, "unresolved": 0}


def test_pagination_followed(db_session):
    eva = _make_cn("Eva CN")
    client = MagicMock()
    client.search_deals.side_effect = [
        {"results": [_fake_deal("d1", "Eva CN", vidas=3)],
         "paging": {"next": {"after": "100"}}},
        {"results": [_fake_deal("d2", "Eva CN", vidas=4)],
         "paging": {}},
    ]
    result = fetch_cn_realized(4, 2026, client=client)
    assert result[eva.id]["sao_realizado"] == Decimal("2")
    assert result[eva.id]["vidas_realizado"] == Decimal("7")
    assert client.search_deals.call_count == 2


def test_inactive_cn_not_matched(db_session):
    suffix = uuid.uuid4().hex[:6]
    u = User(
        email=f"old-{suffix}@piposaude.com", name="Old CN",
        role=UserRole.CN, active=False,
        nivel=CnNivel.CN1, porte=CnPorte.M,
        salario_base=Decimal("3000"),
    )
    db.session.add(u)
    db.session.flush()

    client = MagicMock()
    client.search_deals.return_value = {
        "results": [_fake_deal("d1", "Old CN", vidas=99)],
        "paging": {},
    }
    result, meta = fetch_cn_realized_with_meta(4, 2026, client=client)
    assert result == {}
    assert meta["unresolved"] == 1
