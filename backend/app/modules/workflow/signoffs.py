"""Conferência (sign-off) por EV da Apuração mensal.

RevOps revisa cada EV dentro do CALCULATING e marca DONE um a um; a
liberação CALCULATING → VALIDATING é bloqueada enquanto houver EV do escopo
sem conferência. Uma linha DONE guarda o fingerprint dos valores do EV;
recálculos só invalidam linhas cujo fingerprint mudou, então o trabalho de
conferência sobrevive à recalculação. O recálculo é sempre global — perks
são deduzidos no nível do cliente e rateados entre apólices que podem ser
de EVs diferentes, então um recálculo escopado deixaria o outro EV
obsoleto (spec 2026-07-07).
"""
import hashlib
import json
from decimal import Decimal

from app.extensions import db
from app.models import (
    AppraisalStatus, Commission, EvSignoff, SignoffStatus, User, UserRole,
)


def signoff_scope_ev_ids(month, year):
    """EVs que precisam de conferência em (month, year): todo EV ativo não
    desligado (um mês sem movimento ainda ganha conferência explícita) mais
    qualquer EV com Commission no mês (pega desligados que ainda geraram)."""
    active = {
        u.id for u in User.query.filter_by(
            role=UserRole.EV, active=True, left_company=False,
        ).all()
    }
    with_commission = {
        ev_id for (ev_id,) in db.session.query(Commission.ev_id)
        .filter(
            Commission.month == month,
            Commission.year == year,
            Commission.ev_id.isnot(None),
        )
        .distinct()
        .all()
    }
    return active | with_commission


# Quanta das colunas NUMERIC (total_actual 12,2; pcts 8,4). O hash tem que
# sair idêntico quer as linhas venham do banco (Decimal na escala da coluna,
# ex. 0.0800) quer tenham acabado de ser atribuídas em memória pelo
# calculator (0.08) — str(Decimal) distingue as duas escalas, então
# normalizamos com quantize antes de serializar.
_Q_MONEY = Decimal("0.01")
_Q_PCT = Decimal("0.0001")


def _canon(value, quantum):
    return str((value if value is not None else Decimal(0)).quantize(quantum))


def compute_ev_fingerprint(ev_id, month, year):
    """sha256 dos valores de comissão do EV no mês. Decimals normalizados
    para a escala da coluna e serializados como str — float tornaria o
    hash instável entre runs idênticos."""
    rows = Commission.query.filter_by(
        ev_id=ev_id, month=month, year=year,
    ).all()
    payload = sorted(
        [
            str(c.policy_id),
            _canon(c.total_actual, _Q_MONEY),
            _canon(c.commission_pct, _Q_PCT),
            _canon(c.achievement_pct, _Q_PCT),
        ]
        for c in rows
    )
    canonical = json.dumps(payload, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_signoffs(appraisal):
    """Cria as linhas PENDING que faltam para o escopo atual. Retorna
    quantas criou. Linhas de EVs que saíram do escopo ficam como histórico
    e são ignoradas pelo gate."""
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    existing = {
        s.ev_id for s in EvSignoff.query
        .filter_by(appraisal_id=appraisal.id).all()
    }
    created = 0
    for ev_id in scope - existing:
        db.session.add(EvSignoff(
            appraisal_id=appraisal.id,
            ev_id=ev_id,
            status=SignoffStatus.PENDING,
        ))
        created += 1
    if created:
        db.session.flush()
    return created


def refresh_signoffs_after_recalc(appraisal):
    """Re-hasheia cada linha DONE do escopo após um recálculo; volta para
    PENDING as que mudaram (values_changed=True). Retorna
    {"invalidated": [nomes ordenados], "kept": n} para o toast do frontend."""
    ensure_signoffs(appraisal)
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    invalidated, kept = [], 0
    rows = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, status=SignoffStatus.DONE,
    ).all()
    for row in rows:
        # Linha DONE de EV fora do escopo é história congelada: não
        # re-hasheia nem invalida (o gate e os totais já a ignoram).
        if row.ev_id not in scope:
            continue
        new_fp = compute_ev_fingerprint(
            row.ev_id, appraisal.month, appraisal.year,
        )
        if new_fp == row.fingerprint:
            kept += 1
            continue
        row.status = SignoffStatus.PENDING
        row.values_changed = True
        row.fingerprint = None
        row.signed_off_by = None
        row.signed_off_at = None
        ev = db.session.get(User, row.ev_id)
        invalidated.append(ev.name if ev else str(row.ev_id))
    if invalidated:
        db.session.flush()
    return {"invalidated": sorted(invalidated), "kept": kept}


def pending_signoff_evs(appraisal):
    """EVs do escopo ainda sem conferência DONE — os que bloqueiam a
    liberação para VALIDATING. Retorna [(ev_id, nome)] ordenado por nome."""
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    done = {
        s.ev_id for s in EvSignoff.query.filter_by(
            appraisal_id=appraisal.id, status=SignoffStatus.DONE,
        ).all()
    }
    pending_ids = scope - done
    if not pending_ids:
        return []
    names = {
        u.id: u.name
        for u in User.query.filter(User.id.in_(list(pending_ids))).all()
    }
    return sorted(
        [(ev_id, names.get(ev_id, str(ev_id))) for ev_id in pending_ids],
        key=lambda t: t[1],
    )


def signoff_totals(appraisal):
    """{"total", "done", "all_done"} para a banda de progresso.

    Em CALCULATING os totais vêm do escopo recomputado (EVs novos entram na
    conta). Fora de CALCULATING vêm das linhas gravadas: são história, e o
    escopo recomputado de hoje reescreveria os números de uma apuração
    antiga a cada mudança no time (mesmo racional do `expected` congelado
    do cycle_aggregator em ciclos LOCKED)."""
    if appraisal.status != AppraisalStatus.CALCULATING:
        rows = EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
        done = sum(1 for r in rows if r.status == SignoffStatus.DONE)
        return {
            "total": len(rows),
            "done": done,
            "all_done": done == len(rows),
        }
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    done_ids = {
        s.ev_id for s in EvSignoff.query.filter_by(
            appraisal_id=appraisal.id, status=SignoffStatus.DONE,
        ).all()
    }
    done = len(scope & done_ids)
    return {
        "total": len(scope),
        "done": done,
        "all_done": done == len(scope),
    }
