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
