from decimal import Decimal
import pytest
from app.modules.commissions.simulator import simulate_cn, _regua


class TestRegua:
    """Régua de pagamento — 6 boundary conditions."""

    def test_below_minimum_returns_zero(self):
        assert _regua(Decimal("0.19")) == Decimal("0")

    def test_at_20pct_returns_0_20(self):
        assert _regua(Decimal("0.20")) == Decimal("0.20")

    def test_at_39pct_returns_0_20(self):
        assert _regua(Decimal("0.39")) == Decimal("0.20")

    def test_linear_zone_returns_score(self):
        score = Decimal("0.65")
        assert _regua(score) == score

    def test_at_100pct_returns_1_20(self):
        assert _regua(Decimal("1.00")) == Decimal("1.20")

    def test_at_110pct_returns_1_80(self):
        assert _regua(Decimal("1.10")) == Decimal("1.80")

    def test_at_140pct_returns_2_10(self):
        assert _regua(Decimal("1.40")) == Decimal("2.10")

    def test_above_140pct_returns_2_10(self):
        assert _regua(Decimal("2.00")) == Decimal("2.10")


class TestSimulateCn:
    """simulate_cn — end-to-end formula verification."""

    def test_cn1_at_100pct_sao_100pct_vidas(self):
        # score = 0.70*1.0 + 0.30*1.0 = 1.00 → multiplicador = 1.20
        # commission = 2000 * 1.20 = 2400
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("50"),
        )
        assert result["score_final"] == "1.0000"
        assert result["multiplicador"] == "1.20"
        assert result["commission_amount"] == "2400.00"

    def test_cn2_below_minimum_pays_zero(self):
        # score = 0.70*0.10 + 0.30*0.10 = 0.10 → multiplicador = 0
        result = simulate_cn(
            nivel="CN2",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("10"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("5"),
        )
        assert result["commission_amount"] == "0.00"

    def test_cn3_vidas_capped_at_150pct(self):
        # pct_vidas = min(200/50, 1.5) = 1.5
        # pct_sao = 100/100 = 1.0
        # score = 0.70*1.0 + 0.30*1.5 = 1.15 → multiplicador = 1.80
        # commission = 3000 * 1.80 = 5400
        result = simulate_cn(
            nivel="CN3",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("200"),
        )
        assert result["pct_vidas"] == "1.5000"
        assert result["commission_amount"] == "5400.00"

    def test_cn1_excelencia_tier(self):
        # score ≥ 1.40 → multiplicador = 2.10, commission = 2000*2.10 = 4200
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("150"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("100"),
        )
        assert result["multiplicador"] == "2.10"
        assert result["commission_amount"] == "4200.00"

    def test_zero_sao_meta_returns_zero_commission(self):
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("0"),
            sao_realizado=Decimal("50"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("50"),
        )
        assert result["commission_amount"] == "0.00"


from app.modules.commissions.simulator import _regua_rampagem


class TestReguaRampagem:
    """Régua de rampagem — limites SUPERIORES inclusivos (diverge de _regua)."""

    def test_at_or_below_20pct_returns_zero(self):
        assert _regua_rampagem(Decimal("0.20")) == Decimal("0")
        assert _regua_rampagem(Decimal("0.10")) == Decimal("0")

    def test_21_to_40_returns_0_20(self):
        assert _regua_rampagem(Decimal("0.21")) == Decimal("0.20")
        assert _regua_rampagem(Decimal("0.40")) == Decimal("0.20")

    def test_em_linha_zone_returns_score_inclusive_of_100(self):
        assert _regua_rampagem(Decimal("0.65")) == Decimal("0.65")
        assert _regua_rampagem(Decimal("1.00")) == Decimal("1.00")  # 100% → em linha

    def test_101_to_110_returns_1_20(self):
        assert _regua_rampagem(Decimal("1.01")) == Decimal("1.20")
        assert _regua_rampagem(Decimal("1.10")) == Decimal("1.20")  # 110% → 120%

    def test_111_to_139_returns_1_80(self):
        assert _regua_rampagem(Decimal("1.11")) == Decimal("1.80")
        assert _regua_rampagem(Decimal("1.39")) == Decimal("1.80")

    def test_140_and_above_returns_2_10(self):
        assert _regua_rampagem(Decimal("1.40")) == Decimal("2.10")
        assert _regua_rampagem(Decimal("2.00")) == Decimal("2.10")
