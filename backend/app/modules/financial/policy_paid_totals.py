"""Recompute Policy.total_paid_comissao / total_paid_agenciamento.

Triggered when an Appraisal transitions to LOCKED. The columns are derived
from FinancialImport rows:
- total_paid_comissao       = Σ NF amounts where tipo_receita matches "comiss"
- total_paid_agenciamento   = Σ NF amounts where tipo_receita matches "agenc"

Only matched FIs whose (month, year) corresponds to a LOCKED Appraisal
contribute. Recomputed from scratch each time so the operation is idempotent
— locking the same apuração twice (or recomputing after a fix) produces
identical totals, never doubled.

Scope: only policies whose FIs touch the apuração being locked are
recomputed; other policies' totals are left untouched.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, tuple_

from app.extensions import db
from app.models import Appraisal, AppraisalStatus, FinancialImport, Policy


def recompute_policy_paid_totals_for_apuracao(month: int, year: int) -> int:
    """Recompute total_paid_* on every policy with a matched NF in (month, year).

    Returns the number of policies updated. The caller is responsible for the
    enclosing transaction — we flush but do not commit.
    """
    # 1. Find which policies were touched by this apuração.
    impacted_rows = (
        db.session.query(FinancialImport.policy_id)
        .filter(
            FinancialImport.month == month,
            FinancialImport.year == year,
            FinancialImport.match_status == "MATCHED",
            FinancialImport.policy_id.isnot(None),
        )
        .distinct()
        .all()
    )
    impacted_policy_ids = [pid for (pid,) in impacted_rows]
    if not impacted_policy_ids:
        return 0

    # 2. Collect the (month, year) pairs of every LOCKED appraisal — those
    # are the periods whose FIs count toward the running totals.
    locked_pairs = (
        db.session.query(Appraisal.month, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    )
    if not locked_pairs:
        # If we're transitioning the first apuração ever to LOCKED, the row
        # hasn't been flushed yet by the caller. Include the current pair
        # explicitly so the recompute reflects the in-flight transition.
        locked_pairs = [(month, year)]
    elif (month, year) not in locked_pairs:
        locked_pairs.append((month, year))
    locked_pairs = list(set(locked_pairs))

    # 3. One grouped query: per-policy totals, split by tipo_receita.
    rows = (
        db.session.query(
            FinancialImport.policy_id,
            FinancialImport.tipo_receita,
            func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0),
        )
        .filter(
            FinancialImport.policy_id.in_(impacted_policy_ids),
            FinancialImport.match_status == "MATCHED",
            tuple_(FinancialImport.month, FinancialImport.year).in_(locked_pairs),
        )
        .group_by(FinancialImport.policy_id, FinancialImport.tipo_receita)
        .all()
    )

    totals: dict = defaultdict(
        lambda: {"comissao": Decimal("0"), "agenciamento": Decimal("0")}
    )
    for policy_id, tipo, total in rows:
        normalized = (tipo or "").strip().lower()
        amount = total or Decimal("0")
        if "comiss" in normalized:
            totals[policy_id]["comissao"] += amount
        elif "agenc" in normalized:
            totals[policy_id]["agenciamento"] += amount

    # 4. Persist. Each impacted policy gets exactly one update — including
    # those with no contribution this time (totals stay at 0 if their only
    # FIs are non-comissão / non-agenciamento). We DO touch policies whose
    # totals are unchanged; SQLAlchemy will no-op those.
    updated = 0
    for pid in impacted_policy_ids:
        policy = db.session.get(Policy, pid)
        if policy is None:
            continue
        policy.total_paid_comissao = totals[pid]["comissao"]
        policy.total_paid_agenciamento = totals[pid]["agenciamento"]
        updated += 1

    db.session.flush()
    return updated
