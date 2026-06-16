"""Pure CN commission calculation — no DB access.

Regra de Ouro (spec §2.1):
  pct_sao   = sao_realizado / sao_meta          (uncapped)
  pct_vidas = min(vidas_realizado / vidas_meta, 1.5)
  score     = pct_sao * 0.70 + pct_vidas * 0.30
  mult      = regua(score)
  commission = CN_BASE[nivel] * mult
"""
from decimal import Decimal

CN_BASES: dict[str, Decimal] = {
    "CN1": Decimal("2000"),
    "CN2": Decimal("2500"),
    "CN3": Decimal("3000"),
}

VIDAS_META_FACTORS: dict[str, Decimal] = {
    "M": Decimal("375"),
    "G+": Decimal("2000"),
}

_ZERO = Decimal("0")
_SCALE4 = Decimal("0.0001")
_SCALE2 = Decimal("0.01")


def _regua(score: Decimal) -> Decimal:
    """Régua de pagamento: score → multiplier."""
    if score < Decimal("0.20"):
        return _ZERO
    if score < Decimal("0.40"):
        return Decimal("0.20")
    if score < Decimal("1.00"):
        return score
    if score < Decimal("1.10"):
        return Decimal("1.20")
    if score < Decimal("1.40"):
        return Decimal("1.80")
    return Decimal("2.10")


def _regua_rampagem(score: Decimal) -> Decimal:
    """Régua da rampagem — limites superiores INCLUSIVOS (tabela do print).

    Diverge de _regua (cálculo normal): aqui 100% → em linha (o próprio
    score) e 110% → 120%. Ver docs/superpowers/specs/2026-06-16-cn-rampagem-design.md.
    """
    if score <= Decimal("0.20"):
        return _ZERO
    if score <= Decimal("0.40"):
        return Decimal("0.20")
    if score <= Decimal("1.00"):
        return score
    if score <= Decimal("1.10"):
        return Decimal("1.20")
    if score < Decimal("1.40"):
        return Decimal("1.80")
    return Decimal("2.10")


def vidas_meta_from_sao(sao_meta: Decimal, porte: str | None) -> Decimal:
    """Monthly lives target derived from SAO target and CN company-size profile."""
    factor = VIDAS_META_FACTORS.get(porte or "")
    if sao_meta <= _ZERO or factor is None:
        return _ZERO
    return (sao_meta * factor).quantize(_SCALE2)


def simulate_cn(
    nivel: str,
    sao_meta: Decimal,
    sao_realizado: Decimal,
    vidas_meta: Decimal,
    vidas_realizado: Decimal,
) -> dict:
    """Compute CN commission breakdown. Returns serialisable dict (all values str).

    If sao_meta is zero the period is undefined — return zero commission.
    """
    if sao_meta <= _ZERO:
        return {
            "pct_sao": "0.0000",
            "pct_vidas": "0.0000",
            "score_final": "0.0000",
            "multiplicador": "0",
            "commission_amount": "0.00",
        }
    pct_sao = sao_realizado / sao_meta
    pct_vidas = (
        min(vidas_realizado / vidas_meta, Decimal("1.5"))
        if vidas_meta > _ZERO
        else _ZERO
    )
    score = (pct_sao * Decimal("0.70") + pct_vidas * Decimal("0.30")).quantize(_SCALE4)
    multiplicador = _regua(score)
    base = CN_BASES.get(nivel, _ZERO)
    commission = (base * multiplicador).quantize(_SCALE2)

    return {
        "pct_sao": str(pct_sao.quantize(_SCALE4)),
        "pct_vidas": str(pct_vidas.quantize(_SCALE4)),
        "score_final": str(score),
        "multiplicador": str(multiplicador),
        "commission_amount": str(commission),
    }


def _capped(num: Decimal, den: Decimal) -> Decimal:
    """ratio capped at 1.0 (KPI de atividade)."""
    if den <= _ZERO:
        return _ZERO
    return min(num / den, Decimal("1"))


def _uncapped(num: Decimal, den: Decimal) -> Decimal:
    """ratio without cap (KPI de resultado / SAO)."""
    if den <= _ZERO:
        return _ZERO
    return num / den


def _rampagem_result(calc_mode, atingimento, base, bonus_total):
    gatilho = _regua_rampagem(atingimento)
    comissao = (base * gatilho + bonus_total).quantize(_SCALE2)
    at4 = atingimento.quantize(_SCALE4)
    g2 = gatilho.quantize(_SCALE2)
    return {
        "calc_mode": calc_mode,
        "atingimento": str(at4),
        "gatilho": str(g2),
        "bonus_sao_amount": str(bonus_total.quantize(_SCALE2)),
        "commission_amount": str(comissao),
        # compat aliases so existing serializer / régua-pipeline keep working
        "pct_sao": "0.0000",
        "pct_vidas": "0.0000",
        "score_final": str(at4),
        "multiplicador": str(g2),
    }


def simulate_cn_rampagem_sem_sao(
    nivel: str,
    neg_meta: Decimal, neg_real: Decimal,
    emails_meta: Decimal, emails_real: Decimal,
    sao_fora_da_meta: int,
    bonus_sao: Decimal,
) -> dict:
    """Rampagem sem meta de SAO: dois KPIs de atividade (ambos com teto)."""
    atingimento = (
        Decimal("0.5") * _capped(neg_real, neg_meta)
        + Decimal("0.5") * _capped(emails_real, emails_meta)
    )
    base = CN_BASES.get(nivel, _ZERO)
    bonus_total = (bonus_sao * Decimal(str(sao_fora_da_meta)))
    return _rampagem_result("RAMPAGEM_SEM_SAO", atingimento, base, bonus_total)


def simulate_cn_rampagem_com_sao(
    nivel: str,
    sao_meta: Decimal, sao_real: Decimal,
    qualis_meta: Decimal, qualis_real: Decimal,
) -> dict:
    """Rampagem com meta de SAO: SAO sem teto + Qualis com teto. Sem bônus."""
    atingimento = (
        Decimal("0.5") * _uncapped(sao_real, sao_meta)
        + Decimal("0.5") * _capped(qualis_real, qualis_meta)
    )
    base = CN_BASES.get(nivel, _ZERO)
    return _rampagem_result("RAMPAGEM_COM_SAO", atingimento, base, _ZERO)


def simulate_cn_auto(
    em_rampagem: bool,
    nivel: str,
    sao_meta: Decimal,
    *,
    sao_realizado: Decimal = _ZERO,
    vidas_meta: Decimal = _ZERO,
    vidas_realizado: Decimal = _ZERO,
    neg_meta: Decimal = _ZERO,
    neg_real: Decimal = _ZERO,
    emails_meta: Decimal = _ZERO,
    emails_real: Decimal = _ZERO,
    qualis_meta: Decimal = _ZERO,
    qualis_real: Decimal = _ZERO,
    sao_fora_da_meta: int = 0,
    bonus_sao: Decimal = Decimal("300"),
) -> dict:
    """Pick the calc mode: NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO."""
    if not em_rampagem:
        result = simulate_cn(
            nivel=nivel, sao_meta=sao_meta, sao_realizado=sao_realizado,
            vidas_meta=vidas_meta, vidas_realizado=vidas_realizado,
        )
        result["calc_mode"] = "NORMAL"
        result["atingimento"] = result["score_final"]
        result["gatilho"] = result["multiplicador"]
        result["bonus_sao_amount"] = "0.00"
        return result
    if sao_meta > _ZERO:
        return simulate_cn_rampagem_com_sao(
            nivel=nivel, sao_meta=sao_meta, sao_real=sao_realizado,
            qualis_meta=qualis_meta, qualis_real=qualis_real,
        )
    return simulate_cn_rampagem_sem_sao(
        nivel=nivel, neg_meta=neg_meta, neg_real=neg_real,
        emails_meta=emails_meta, emails_real=emails_real,
        sao_fora_da_meta=sao_fora_da_meta, bonus_sao=bonus_sao,
    )
