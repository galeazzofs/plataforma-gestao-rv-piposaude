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


from app.modules.commissions.simulator import (
    simulate_cn_rampagem_sem_sao,
    simulate_cn_rampagem_com_sao,
    simulate_cn_auto,
)


class TestRampagemSemSao:
    def test_print_example_gives_3300(self):
        # neg 103/60 → min(1.7167,1)=1 ; emails 1133/400 → min(2.83,1)=1
        # atingimento = 0.5*1 + 0.5*1 = 1.00 → gatilho 1.00 (em linha)
        # comissão = 3000*1.00 + 300*1 = 3300
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN3",
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=1, bonus_sao=Decimal("300"),
        )
        assert r["calc_mode"] == "RAMPAGEM_SEM_SAO"
        assert r["atingimento"] == "1.0000"
        assert r["gatilho"] == "1.00"
        assert r["bonus_sao_amount"] == "300.00"
        assert r["commission_amount"] == "3300.00"
        assert r["score_final"] == "1.0000"
        assert r["multiplicador"] == "1.00"

    def test_no_bonus_when_zero_sao_fora(self):
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN3",
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=0, bonus_sao=Decimal("300"),
        )
        assert r["commission_amount"] == "3000.00"

    def test_zero_meta_is_safe(self):
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN1",
            neg_meta=Decimal("0"), neg_real=Decimal("0"),
            emails_meta=Decimal("0"), emails_real=Decimal("0"),
            sao_fora_da_meta=0, bonus_sao=Decimal("300"),
        )
        assert r["atingimento"] == "0.0000"
        assert r["commission_amount"] == "0.00"


class TestRampagemComSao:
    def test_sao_uncapped_pushes_above_100(self):
        # SAO 5/3 = 1.6667 (sem teto); Qualis 10/10 = min(1,1)=1
        # atingimento = 0.5*1.6667 + 0.5*1 = 1.3333 → faixa 111-139 → 1.80
        # comissão = 3000 * 1.80 = 5400 ; sem bônus de SAO
        r = simulate_cn_rampagem_com_sao(
            nivel="CN3",
            sao_meta=Decimal("3"), sao_real=Decimal("5"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("10"),
        )
        assert r["calc_mode"] == "RAMPAGEM_COM_SAO"
        assert r["atingimento"] == "1.3333"
        assert r["gatilho"] == "1.80"
        assert r["commission_amount"] == "5400.00"
        assert r["bonus_sao_amount"] == "0.00"

    def test_qualis_is_capped_at_100(self):
        # SAO 3/3 = 1.0 ; Qualis 50/10 = min(5,1)=1 → atingimento 1.00 → 1.00
        r = simulate_cn_rampagem_com_sao(
            nivel="CN3",
            sao_meta=Decimal("3"), sao_real=Decimal("3"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("50"),
        )
        assert r["atingimento"] == "1.0000"
        assert r["commission_amount"] == "3000.00"

    def test_raw_atingimento_rounds_before_regua(self):
        # SAO 100008/100000 = 1.00008 (uncapped); Qualis 10/10 = 1.0
        # raw atingimento = 0.5*1.00008 + 0.5*1 = 1.00004 → quantize 4dp = 1.0000
        # régua deve usar 1.0000 (em linha) → gatilho 1.00, NÃO 1.20.
        r = simulate_cn_rampagem_com_sao(
            nivel="CN3",
            sao_meta=Decimal("100000"), sao_real=Decimal("100008"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("10"),
        )
        assert r["atingimento"] == "1.0000"
        assert r["gatilho"] == "1.00"
        assert r["commission_amount"] == "3000.00"


class TestSimulateCnAuto:
    def test_normal_when_not_rampagem(self):
        r = simulate_cn_auto(
            em_rampagem=False, nivel="CN1",
            sao_meta=Decimal("100"), sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"), vidas_realizado=Decimal("50"),
        )
        assert r["calc_mode"] == "NORMAL"
        assert r["commission_amount"] == "2400.00"

    def test_dispatches_sem_sao_when_sao_meta_zero(self):
        r = simulate_cn_auto(
            em_rampagem=True, nivel="CN3", sao_meta=Decimal("0"),
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=1, bonus_sao=Decimal("300"),
        )
        assert r["calc_mode"] == "RAMPAGEM_SEM_SAO"
        assert r["commission_amount"] == "3300.00"

    def test_dispatches_com_sao_when_sao_meta_positive(self):
        r = simulate_cn_auto(
            em_rampagem=True, nivel="CN3",
            sao_meta=Decimal("3"), sao_realizado=Decimal("5"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("10"),
        )
        assert r["calc_mode"] == "RAMPAGEM_COM_SAO"
        assert r["commission_amount"] == "5400.00"
