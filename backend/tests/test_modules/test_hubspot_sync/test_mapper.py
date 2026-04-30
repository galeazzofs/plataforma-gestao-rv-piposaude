"""Tests for mapper helpers."""
from app.modules.hubspot_sync.mapper import map_benefit_type


def test_map_saude():
    assert map_benefit_type("Saúde") == "SAUDE"
    assert map_benefit_type("saude") == "SAUDE"


def test_map_odonto():
    assert map_benefit_type("Odonto") == "ODONTO"


def test_map_vida():
    assert map_benefit_type("Vida") == "VIDA"


def test_map_saude_odonto_with_accent():
    assert map_benefit_type("Saúde e Odonto") == "SAUDE_ODONTO"


def test_map_saude_odonto_without_accent():
    assert map_benefit_type("Saude e Odonto") == "SAUDE_ODONTO"


def test_map_unknown_returns_none():
    assert map_benefit_type("Outra Coisa") is None


def test_map_none_returns_none():
    assert map_benefit_type(None) is None
    assert map_benefit_type("") is None
