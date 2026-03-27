from decimal import Decimal
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.models import CommissionPctTable
from app.extensions import db


def _seed_pct_table(session):
    """Seed version 1 of commission pct table: 3 segments x 3 faixas."""
    rows = [
        # PP
        ("PP", "0.0000", "0.4999", "0.05"),
        ("PP", "0.5000", "0.9999", "0.08"),
        ("PP", "1.0000", "9.9999", "0.12"),
        # P
        ("P", "0.0000", "0.4999", "0.06"),
        ("P", "0.5000", "0.9999", "0.10"),
        ("P", "1.0000", "9.9999", "0.15"),
        # M
        ("M", "0.0000", "0.4999", "0.04"),
        ("M", "0.5000", "0.9999", "0.07"),
        ("M", "1.0000", "9.9999", "0.10"),
    ]
    for segment, amin, amax, pct in rows:
        row = CommissionPctTable(
            version=1,
            segment=segment,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        )
        session.add(row)
    session.flush()


def test_lookup_p_segment_medium_achievement(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("P", Decimal("0.75"))
    assert pct == Decimal("0.10")
    assert version == 1


def test_lookup_pp_segment_high_achievement(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("PP", Decimal("1.20"))
    assert pct == Decimal("0.12")
    assert version == 1


def test_lookup_returns_none_for_unknown_segment(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("G", Decimal("0.75"))
    assert pct is None
    assert version == 1
