from decimal import Decimal
from app.models import PlatformSetting
from app.modules.commissions.cn_calculator import get_rampagem_bonus_sao


def test_default_is_300_when_unset(db_session):
    assert get_rampagem_bonus_sao() == Decimal("300")


def test_reads_value_from_platform_setting(db_session):
    PlatformSetting.set("cn_rampagem_bonus_sao", "450")
    db_session.flush()
    assert get_rampagem_bonus_sao() == Decimal("450")
