from decimal import Decimal
from app.models import CommissionPctTable


def lookup_commission_pct(segment, achievement_pct, version=None):
    """Lookup commission percentage for segment and achievement.

    Returns (commission_pct, version) or (None, version) if not found.
    """
    if version is None:
        version = CommissionPctTable.current_version()

    if version == 0:
        return None, 0

    row = CommissionPctTable.lookup(segment, achievement_pct, version)
    if row is None:
        return None, version

    return row.commission_pct, version
