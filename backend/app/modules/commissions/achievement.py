from decimal import Decimal
from datetime import date


def calculate_achievement(total_mrr_gongos, mrr_target):
    """Calculate EV achievement percentage.

    achievement = sum(MRR gongos no tri) / meta MRR do tri
    """
    if mrr_target is None or mrr_target == 0:
        return Decimal("0")
    return (total_mrr_gongos / mrr_target).quantize(Decimal("0.0001"))


def get_quarter_date_range(quarter, year):
    """Get start and end dates for a quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    start = date(year, start_month, 1)
    if end_month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, end_month + 1, 1)
    return start, end
