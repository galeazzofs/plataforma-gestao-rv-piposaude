"""Quarterly commission calculator (v4 --- per-empresa formula with perks).

Spec 4.3:
  Comissao real = (Total liquido empresa - Perks empresa) x % comissao

Algorithm:
1. Match NF rows -> policies by `numero_apolice` (after normalising whitespace
   and case). Product is still validated against the saude/odonto/vida
   benefit map so non-policy revenue is rejected explicitly. NFs without
   `numero_apolice` populated are dropped as UNMATCHED — the spreadsheet
   must carry the apolice number for the row to match.
2. Aggregate matched NFs by client (empresa level)
3. Subtract perks at the client level
4. Distribute net amount proportionally across policies
5. Apply commission % per policy (from gongo quarter achievement snapshot)
6. Update commission_status via status helper
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import tuple_

from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    Policy,
    Commission,
    CommissionStatus,
    EvQuarterAchievement,
    FinancialImport,
    Perk,
    PlatformSetting,
    User,
)
from app.models.client import normalize_client_name
from app.modules.policies.filters import ev_policies_query
from app.modules.financial.matcher import (
    build_policy_index,
    client_names_compatible,
    fallback_match_key,
    is_unreliable_apolice_number,
    normalize_apolice_number,
)
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.modules.financial.monthly_engine import (
    COMISSAO,
    classify_revenue_type,
)


# -- Errors -------------------------------------------------------------------


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# -- Pre-check ----------------------------------------------------------------


def validate_achievements_for_appraisal(month, year):
    """Verify every (ev_id, gongo_quarter, gongo_year) tuple needed by this
    apuracao has a stored achievement.

    Each policy uses the achievement_pct from the EV's GONGO quarter (when
    the sale closed) as a snapshot — not the appraisal quarter. So we need
    one achievement per (ev_id, gongo_q, gongo_y) combination across all
    active policies.

    Returns list of human-readable strings for missing combinations.
    Empty list = ok to proceed.
    """
    policies = ev_policies_query().filter(
        Policy.commission_status.notin_([
            CommissionStatus.CANCELLED,
            CommissionStatus.SETTLED,
        ])
    ).all()

    needed = set()
    for p in policies:
        if not p.closed_date or not p.ev_id:
            continue
        gq = (p.closed_date.month - 1) // 3 + 1
        needed.add((p.ev_id, gq, p.closed_date.year))

    missing = []
    for ev_id, gq, gy in sorted(needed, key=lambda t: (str(t[0]), t[2], t[1])):
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=gq, year=gy
        ).first()
        if ach is None or ach.achievement_pct is None:
            user = db.session.get(User, ev_id)
            label = user.name if user else str(ev_id)
            missing.append(f"{label} \u2192 Q{gq}/{gy}")
    return missing


# -- Benefit normalisation ----------------------------------------------------

BENEFIT_MAP = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}


APOLICE_FINALIZADA = "APOLICE_FINALIZADA"
RECEITA_NAO_COMISSIONAVEL = "RECEITA_NAO_COMISSIONAVEL"
FINANCIAL_CLIENT_ALIASES_SETTING = "financial_client_aliases"


def _normalize_client_label(value):
    if value is None:
        return ""
    return normalize_client_name(str(value))


def _financial_client_aliases():
    """Configured aliases for financial imports.

    Expected setting shape:
      {"Yamaha": ["GRUPO YAMAHA BRASIL"]}

    The map is treated bidirectionally so admins can write either the imported
    name or the HubSpot client name as the key.
    """
    raw = PlatformSetting.get(FINANCIAL_CLIENT_ALIASES_SETTING, {})
    if not isinstance(raw, dict):
        return {}

    aliases = defaultdict(set)
    for source, targets in raw.items():
        source_normalized = _normalize_client_label(source)
        if not source_normalized:
            continue
        if isinstance(targets, str):
            target_values = [targets]
        elif isinstance(targets, list):
            target_values = targets
        else:
            continue

        for target in target_values:
            target_normalized = _normalize_client_label(target)
            if not target_normalized or target_normalized == source_normalized:
                continue
            aliases[source_normalized].add(target_normalized)
            aliases[target_normalized].add(source_normalized)

    return aliases


def _unique_unlocked_policies(policies, locked_policy_ids):
    seen = set()
    result = []
    for policy in policies:
        if policy.id in locked_policy_ids or policy.id in seen:
            continue
        seen.add(policy.id)
        result.append(policy)
    return result


def _fallback_index_candidates(
    fallback_index,
    client_names,
    benefit,
    operadora,
    locked_policy_ids,
):
    candidates = []
    for client_name in client_names:
        if not client_name:
            continue
        candidates.extend(
            fallback_index.get(
                fallback_match_key(client_name, benefit, operadora),
                [],
            )
        )
    return _unique_unlocked_policies(candidates, locked_policy_ids)


def _same_fallback_dimensions(policy, benefit, operadora):
    if policy.benefit_type is None:
        return False
    policy_key = fallback_match_key(
        "", policy.benefit_type.value, policy.partner_operator,
    )
    nf_key = fallback_match_key("", benefit, operadora)
    return policy_key[1:] == nf_key[1:]


def _partial_client_fallback_candidates(
    policies,
    nf_client_name,
    benefit,
    operadora,
    locked_policy_ids,
):
    candidates = []
    for policy in policies:
        client = policy.client
        if (
            policy.id in locked_policy_ids
            or client is None
            or not is_unreliable_apolice_number(policy.numero_apolice)
            or not _same_fallback_dimensions(policy, benefit, operadora)
        ):
            continue

        policy_client_name = (
            client.name_normalized or _normalize_client_label(client.name)
        )
        if client_names_compatible(nf_client_name, policy_client_name):
            candidates.append(policy)

    return _unique_unlocked_policies(candidates, locked_policy_ids)


def _locked_period_pairs():
    appraisal_pairs = {
        (m, y) for m, y in db.session.query(Appraisal.month, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }
    commission_pairs = {
        (m, y) for m, y in db.session.query(Commission.month, Commission.year)
        .filter(Commission.is_final.is_(True))
        .all()
    }
    return appraisal_pairs | commission_pairs


def _locked_positive_comissao_month_counts():
    pairs = _locked_period_pairs()
    if not pairs:
        return {}

    rows = (
        db.session.query(
            FinancialImport.policy_id,
            FinancialImport.nf_mes_recebimento,
            FinancialImport.tipo_receita,
            db.func.coalesce(db.func.sum(FinancialImport.nf_valor_liquido), 0),
        )
        .filter(
            FinancialImport.match_status == "MATCHED",
            FinancialImport.policy_id.isnot(None),
            tuple_(FinancialImport.month, FinancialImport.year).in_(pairs),
        )
        .group_by(
            FinancialImport.policy_id,
            FinancialImport.nf_mes_recebimento,
            FinancialImport.tipo_receita,
        )
        .all()
    )

    monthly = defaultdict(lambda: defaultdict(Decimal))
    for policy_id, ym, tipo, total in rows:
        if classify_revenue_type(tipo) == COMISSAO:
            monthly[policy_id][ym] += total or Decimal("0")

    return {
        policy_id: sum(1 for total in months.values() if total > 0)
        for policy_id, months in monthly.items()
    }


def _set_nf_status(nf, status, policy_id=None, matched=False):
    nf.match_status = status
    nf.policy_id = policy_id
    nf.matched_at = datetime.now(timezone.utc) if matched else None


def _sync_policy_status(policy):
    if policy.commission_status == CommissionStatus.CANCELLED:
        return
    # Count-based only: the 12-month clock alone decides status.
    # first_payment_real (Início vigência) is unreliable and must NOT gate the
    # transition — a policy with paid months but a missing/future vigência
    # still derives its status from installments_paid.
    if policy.installments_paid >= 12:
        policy.commission_status = CommissionStatus.SETTLED
    elif policy.installments_paid > 0:
        policy.commission_status = CommissionStatus.IN_PAYMENT


# -- Main entry ---------------------------------------------------------------


def run_monthly_appraisal(month, year, *, validate_achievements=True):
    """Process all financial_imports for (month, year) and produce commissions.

    Implements spec 4.3:
      Comissao real = (Total liquido empresa - Perks empresa) x % comissao

    The real apuração refuses to run with missing achievements. A read-only
    preview passes validate_achievements=False so a draft can still be
    produced — missing (ev, gongo-quarter) combos fall back to 0% achievement
    — and the caller surfaces the gaps as a warning instead of a hard error.
    """
    # -- Pre-check ----------------------------------------------------
    if validate_achievements:
        missing = validate_achievements_for_appraisal(month, year)
        if missing:
            raise MissingAchievementsError(missing)

    # -- 1. Wipe non-final commissions --------------------------------
    Commission.query.filter_by(
        month=month, year=year, is_final=False
    ).delete()
    db.session.flush()

    # -- 2. Reset installments_paid to baseline -----------------------
    locked_policy_ids = {
        pid for (pid,) in db.session.query(Commission.policy_id)
        .filter(
            Commission.month == month,
            Commission.year == year,
            Commission.is_final.is_(True),
        )
        .all()
    }
    policies_for_index = ev_policies_query().filter(
        Policy.commission_status != CommissionStatus.CANCELLED
    ).all()
    policies = [p for p in policies_for_index if p.id not in locked_policy_ids]

    locked_comissao_count = _locked_positive_comissao_month_counts()
    for p in policies_for_index:
        if p.commission_status == CommissionStatus.CANCELLED:
            continue
        p.installments_paid = min(
            12,
            (p.initial_installments_paid or 0) + locked_comissao_count.get(p.id, 0),
        )

    # -- 3. Build matcher indexes -------------------------------------
    policy_index = build_policy_index(policies_for_index)
    # Fallback index for policies whose numero_apolice is missing/corrupted
    # in the sync: keyed on (Cliente Mãe, Benefício, Operadora). Only tuples
    # that resolve to exactly ONE policy are usable — see Pass 1.
    fallback_index = defaultdict(list)
    for p in policies_for_index:
        client = p.client
        if client is None or p.benefit_type is None:
            continue
        fallback_index[fallback_match_key(
            client.name_normalized, p.benefit_type.value, p.partner_operator,
        )].append(p)
    client_aliases = _financial_client_aliases()

    # -- 4. Pass 1 --- Find candidate policies ------------------------
    nfs = FinancialImport.query.filter_by(
        month=month, year=year, status_recebimento='RECEBIDO'
    ).all()

    # Accumulators
    policy_nf_subtotals = defaultdict(Decimal)    # policy_id -> sum NF values
    client_nf_totals = defaultdict(Decimal)        # client_id -> sum NF values
    matched_policies = {}                           # policy_id -> Policy
    candidate_rows = defaultdict(list)              # policy_id -> [FinancialImport]

    def _demote_unmatched(nf):
        """UNMATCHED — unless the row is already attached to a locked policy.
        That attachment is the record the locked (is_final) commission was
        built on; wiping policy_id would corrupt the 12-month clock and the
        paid-totals recompute, which both read match_status == MATCHED."""
        if (
            nf.policy_id in locked_policy_ids
            and nf.match_status in ('MATCHED', APOLICE_FINALIZADA)
        ):
            return
        _set_nf_status(nf, 'UNMATCHED')

    for nf in nfs:
        revenue_type = classify_revenue_type(nf.tipo_receita)
        if revenue_type is None:
            _set_nf_status(nf, RECEITA_NAO_COMISSIONAVEL)
            continue

        # Apolice-number-anchored matching: every match is keyed on the
        # apolice number stamped on the NF row + on the policy. Product
        # is still validated so non-saude/odonto/vida revenue is rejected
        # explicitly rather than appearing as "no policy found".
        from app.modules.financial.matcher import normalize as _normalize_text
        produto_n = _normalize_text(nf.produto or '')
        benefit = BENEFIT_MAP.get(produto_n)
        if benefit is None:
            _set_nf_status(nf, 'PRODUTO_NAO_SUPORTADO')
            continue

        apolice_key = normalize_apolice_number(nf.numero_apolice)
        candidates = policy_index.get(apolice_key, []) if apolice_key else []

        if not candidates:
            # Fallbacks run strongest to loosest. Each must resolve to exactly
            # one live policy before it can credit an EV.
            nf_client_name = normalize_client_name(nf.cliente_mae or '')
            fb_candidates = _fallback_index_candidates(
                fallback_index,
                [nf_client_name],
                benefit,
                nf.operadora,
                locked_policy_ids,
            )
            if len(fb_candidates) == 1:
                candidates = fb_candidates
            elif len(fb_candidates) > 1:
                _demote_unmatched(nf)
                continue
            else:
                alias_candidates = _fallback_index_candidates(
                    fallback_index,
                    client_aliases.get(nf_client_name, set()),
                    benefit,
                    nf.operadora,
                    locked_policy_ids,
                )
                if len(alias_candidates) == 1:
                    candidates = alias_candidates
                elif len(alias_candidates) > 1:
                    _demote_unmatched(nf)
                    continue
                else:
                    partial_candidates = _partial_client_fallback_candidates(
                        policies_for_index,
                        nf_client_name,
                        benefit,
                        nf.operadora,
                        locked_policy_ids,
                    )
                    if len(partial_candidates) == 1:
                        candidates = partial_candidates
                    elif len(partial_candidates) > 1:
                        _demote_unmatched(nf)
                        continue

        if not candidates:
            _demote_unmatched(nf)
            continue

        # The 12-month clock is COUNT-based ONLY (see Pass 2): a policy earns
        # until it has 12 paid Comissão months, then APOLICE_FINALIZADA. The
        # vigência DATE (first_payment_real) does NOT gate a match — NFs are
        # never dropped as PRE_VIGENCIA/EXPIRED by calendar date. Only the count
        # of paid months out of 12 decides whether an NF still earns. Match to
        # the first non-locked candidate.
        matched = next(
            (p for p in candidates if p.id not in locked_policy_ids), None
        )

        if matched is None:
            # Every matching policy already has a final (locked) commission for
            # this month — nothing to recompute for this NF this run; an
            # existing attachment to one of them is preserved.
            _demote_unmatched(nf)
            continue

        matched_policies[matched.id] = matched
        candidate_rows[matched.id].append(nf)

    # -- 4b. Pass 2 --- Process each policy chronologically by financial month
    for policy_id, rows in candidate_rows.items():
        policy = matched_policies[policy_id]
        by_month = defaultdict(list)
        for nf in rows:
            by_month[nf.nf_mes_recebimento].append(nf)

        for ym in sorted(by_month):
            month_rows = by_month[ym]
            # Finalizada is COUNT-based and keyed SOLELY on installments_paid,
            # which step 2 reset to the baseline derived from LOCKED history
            # (initial_installments_paid + locked Comissão months). Do NOT also
            # gate on commission_status == SETTLED: that flag is mutable and
            # _sync_policy_status rewrites it at the end of every run, so it goes
            # stale at the 11/12 edge — a prior run reaches 12/12 → SETTLED, this
            # run resets installments to 11, and trusting the flag would finalize
            # the 12th parcela that should still be PAID (the result would then
            # oscillate MATCHED↔FINALIZADA across re-runs). The 12th parcela's
            # month must show the commission; the policy only turns finalizada
            # for months AFTER that parcela is paid in a LOCKED apuração.
            if (policy.installments_paid or 0) >= 12:
                for nf in month_rows:
                    _set_nf_status(nf, APOLICE_FINALIZADA, policy.id)
                policy.commission_status = CommissionStatus.SETTLED
                continue

            # The 12-month commission clock is COUNT-based (CONTEXT.md:
            # "Relogio de 12 meses da apolice" = count of paid Comissão
            # months). The 12/12 cap above is the SOLE "fully paid" gate — we
            # do not expire NFs by a calendar window. A policy with legacy
            # parcelas at e.g. 7/12 still has 5 months to earn, no matter how
            # much calendar time passed since first_payment_real; previously a
            # first_payment_real + (12 − legadas) window closed early and
            # dropped legitimate later NFs (e.g. ARVO, billed 2026 but window
            # closed 2025).
            eligible_rows = month_rows

            comissao_net = Decimal("0")
            first_comissao_date = None
            for nf in eligible_rows:
                revenue_type = classify_revenue_type(nf.tipo_receita)
                amount = Decimal(str(nf.nf_valor_liquido))
                _set_nf_status(nf, 'MATCHED', policy.id, matched=True)

                policy_nf_subtotals[policy.id] += amount
                client_nf_totals[policy.client_id] += amount
                if revenue_type == COMISSAO:
                    comissao_net += amount
                    if nf.data_recebimento is not None:
                        if first_comissao_date is None or nf.data_recebimento < first_comissao_date:
                            first_comissao_date = nf.data_recebimento

            if policy.first_payment_real is None and comissao_net > 0:
                policy.first_payment_real = first_comissao_date

            if comissao_net > 0:
                policy.installments_paid = min(12, (policy.installments_paid or 0) + 1)

            _sync_policy_status(policy)

    # -- 5. Load perks per client -------------------------------------
    perks_by_client = defaultdict(Decimal)
    perk_rows = Perk.query.filter_by(month=month, year=year).all()
    for perk in perk_rows:
        perks_by_client[perk.client_id] += perk.amount

    # -- 6. Pass 2 --- Compute commissions per policy -----------------
    for policy_id, nf_subtotal in policy_nf_subtotals.items():
        policy = matched_policies[policy_id]
        client_id = policy.client_id

        # Empresa-level aggregation (spec 4.3)
        client_total = client_nf_totals[client_id]
        client_perks = perks_by_client.get(client_id, Decimal('0'))
        net_client = max(Decimal('0'), client_total - client_perks)

        # Proportional share for this policy
        if client_total > 0:
            share = nf_subtotal / client_total
        else:
            share = Decimal('0')
        net_policy = (net_client * share).quantize(Decimal('0.01'))

        # Achievement snapshot from gongo quarter
        gongo_q = (policy.closed_date.month - 1) // 3 + 1
        gongo_y = policy.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=policy.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        segment_value = policy.segment.value if policy.segment else 'P'
        commission_pct, version = lookup_commission_pct(segment_value, achievement)
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (net_policy * commission_pct).quantize(Decimal('0.01'))

        comm = Commission(
            policy_id=policy_id,
            ev_id=policy.ev_id,
            month=month,
            year=year,
            segment=segment_value,
            achievement_pct=achievement,
            commission_pct=commission_pct,
            commission_pct_version=version,
            monthly_actual=commission_amount,
            total_actual=commission_amount,
            is_final=False,
        )
        db.session.add(comm)

    # -- 7. Update commission_status ----------------------------------
    for policy in matched_policies.values():
        _sync_policy_status(policy)

    db.session.flush()
    return _build_summary(month, year)


# -- Summary ------------------------------------------------------------------


def _build_summary(month, year):
    return {
        "totals": {
            "matched_count": FinancialImport.query.filter_by(
                month=month, year=year, match_status='MATCHED'
            ).count(),
            "unmatched_count": FinancialImport.query.filter_by(
                month=month, year=year, match_status='UNMATCHED'
            ).count(),
            "produto_nao_suportado_count": FinancialImport.query.filter_by(
                month=month, year=year, match_status='PRODUTO_NAO_SUPORTADO'
            ).count(),
            "receita_nao_comissionavel_count": FinancialImport.query.filter_by(
                month=month, year=year, match_status=RECEITA_NAO_COMISSIONAVEL
            ).count(),
            "apolice_finalizada_count": FinancialImport.query.filter_by(
                month=month, year=year, match_status=APOLICE_FINALIZADA
            ).count(),
        }
    }
