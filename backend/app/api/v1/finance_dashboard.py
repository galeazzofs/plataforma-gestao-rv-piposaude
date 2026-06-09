"""Finance dashboard endpoint — three editorial rows.

Row 1 (KPIs):  Comissão Potencial · Comissão Paga · Saldo Devedor Total
Row 2:         Comissão x Agenciamento (split + monthly series)
Row 3:         Fluxo de Caixa Projetado (30/60/90 horizons + chart)

Optional filters: ?year=YYYY&quarter=1..4. Both default to all-time.

Data sources, in priority order:
- Policy.commission_potential (model property, MRR × 12 × commission_pct).
- Policy.total_paid_comissao / total_paid_agenciamento (recomputed when
  an Appraisal transitions to LOCKED, see policy_paid_totals.py).
- Commission.total_actual (per-quarter EV commission once the apuração
  is finalised; is_final=True) — fallback before any apuração has locked.
- FinancialImport (NF-level revenue with tipo_receita = comissao/agenciamento).

Freshness: bound to the HubSpot sync cycle — metrics are computed live on
each request from the data the sync left in the database.
"""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from flask import Blueprint, jsonify, request, Response
from sqlalchemy import func, or_

from app.auth.decorators import require_role
from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    Commission,
    FinancialImport,
    Policy,
    User,
    UserRole,
)
from app.modules.financial.monthly_engine import (
    A_APURAR,
    PROJETADO,
    REALIZADO,
)
from app.modules.financial.finance_read_model import build_monthly_finance_view

finance_dashboard_bp = Blueprint(
    "finance_dashboard", __name__, url_prefix="/api/v1/finance"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PT_MONTHS = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def _short_pt_month(ym: str) -> str:
    """'2026-05' → 'mai/26' for axis labels."""
    try:
        y, m = ym.split("-")
        return f"{_PT_MONTHS[int(m) - 1]}/{y[2:]}"
    except (ValueError, IndexError):
        return ym


def _is_comissao(tipo: str | None) -> bool:
    return "comiss" in (tipo or "").strip().lower()


def _is_agenciamento(tipo: str | None) -> bool:
    return "agenc" in (tipo or "").strip().lower()


def _filter_policies_by_period(
    query, year: int | None, quarter: int | None, year_floor: int | None = None
):
    """Filter a Policy query by closed_date (gongo) quarter and/or year."""
    if year_floor is not None:
        query = query.filter(Policy.closed_date >= date(year_floor, 1, 1))
    elif year is not None:
        query = query.filter(func.extract("year", Policy.closed_date) == year)
    if quarter is not None:
        start_month = (quarter - 1) * 3 + 1
        query = query.filter(
            func.extract("month", Policy.closed_date) >= start_month,
            func.extract("month", Policy.closed_date) <= start_month + 2,
        )
    return query


def _filter_fi_by_period(
    query, year: int | None, quarter: int | None, year_floor: int | None = None
):
    """Filter a FinancialImport query by its month+year columns.

    The dashboard period selector is still a calendar quarter; map it to the
    three financial months it spans (FinancialImport is keyed by month now)."""
    if year_floor is not None:
        query = query.filter(FinancialImport.year >= year_floor)
    elif year is not None:
        query = query.filter(FinancialImport.year == year)
    if quarter is not None:
        start_month = (quarter - 1) * 3 + 1
        query = query.filter(
            FinancialImport.month >= start_month,
            FinancialImport.month <= start_month + 2,
        )
    return query


def _parse_year_filter(raw: str | None) -> tuple[int | None, int | None, str | None]:
    """Return (exact_year, future_floor, normalized_bucket)."""
    if not raw:
        return None, None, None
    if raw.endswith("_plus"):
        try:
            floor = int(raw.replace("_plus", ""))
            return None, floor, raw
        except ValueError:
            return None, None, None
    try:
        return int(raw), None, None
    except ValueError:
        return None, None, None


def _month_matches_period(
    ym: str, year: int | None, quarter: int | None, year_floor: int | None
) -> bool:
    try:
        y, m = (int(part) for part in ym.split("-"))
    except ValueError:
        return False

    if year_floor is not None and y < year_floor:
        return False
    if year is not None and y != year:
        return False
    if quarter is not None:
        start_month = (quarter - 1) * 3 + 1
        if m < start_month or m > start_month + 2:
            return False
    return True


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@finance_dashboard_bp.route("/dashboard")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def dashboard():
    today = date.today()
    year_raw = request.args.get("year")
    quarter_raw = request.args.get("quarter")
    if year_raw and not (
        year_raw.isdigit()
        or (year_raw.endswith("_plus") and year_raw.replace("_plus", "").isdigit())
    ):
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "year must be YYYY or YYYY_plus",
            }
        }), 400
    if quarter_raw and not quarter_raw.isdigit():
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "quarter must be between 1 and 4",
            }
        }), 400
    year_param, year_floor, year_bucket = _parse_year_filter(year_raw)
    quarter_param = int(quarter_raw) if quarter_raw else None
    if quarter_param is not None and quarter_param not in (1, 2, 3, 4):
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "quarter must be between 1 and 4",
            }
        }), 400
    has_period = bool(year_param or year_floor or quarter_param)

    # Build the monthly Finance view up front. Period filters in Finance answer
    # "what belongs to this monthly competency window?".
    finance_engine, finance_by_month = build_monthly_finance_view(today)
    realizado_by_month = {
        ym: values[REALIZADO]
        for ym, values in finance_by_month.items()
        if values[REALIZADO] != 0
    }
    a_apurar_by_month = {
        ym: values[A_APURAR]
        for ym, values in finance_by_month.items()
        if values[A_APURAR] != 0
    }
    projected_by_month = {
        ym: values[PROJETADO]
        for ym, values in finance_by_month.items()
        if values[PROJETADO] != 0
    }
    apolices_by_month = {
        ym: values["apolices"]
        for ym, values in finance_by_month.items()
    }

    visible_realizado_calendar = Decimal("0")
    visible_a_apurar_calendar = Decimal("0")
    visible_projetado_calendar = Decimal("0")
    if has_period:
        visible_realizado_calendar = sum(
            total
            for ym, total in realizado_by_month.items()
            if _month_matches_period(ym, year_param, quarter_param, year_floor)
        )
        visible_a_apurar_calendar = sum(
            total
            for ym, total in a_apurar_by_month.items()
            if _month_matches_period(ym, year_param, quarter_param, year_floor)
        )
        visible_projetado_calendar = sum(
            total
            for ym, total in projected_by_month.items()
            if _month_matches_period(ym, year_param, quarter_param, year_floor)
        )

    # ---- Row 1: KPIs ----------------------------------------------------

    # Potencial a pagar: future/pending obligation only. Keep
    # `comissao_potencial` as a response alias until the UI slice renames it.
    if has_period:
        potencial_a_pagar = visible_a_apurar_calendar + visible_projetado_calendar
    else:
        potencial_a_pagar = finance_engine.payable_potential
    comissao_potencial = potencial_a_pagar

    # Comissão Paga: when a period is selected, slice by FinancialImport
    # receipts in that quarter+year. Otherwise prefer Policy.total_paid_*
    # (with Commission.total_actual as fallback) for the all-time figure.
    if has_period:
        paga_q = _filter_fi_by_period(
            db.session.query(
                func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0)
            ).filter(
                FinancialImport.match_status == "MATCHED",
                or_(
                    FinancialImport.tipo_receita.ilike("%comiss%"),
                    FinancialImport.tipo_receita.ilike("%agenc%"),
                ),
            ),
            year_param,
            quarter_param,
            year_floor,
        )
        comissao_paga = paga_q.scalar() or Decimal("0")
    else:
        cols = db.session.query(
            func.coalesce(func.sum(Policy.total_paid_comissao), 0),
            func.coalesce(func.sum(Policy.total_paid_agenciamento), 0),
        ).first()
        paid_comissao_total = cols[0] or Decimal("0")
        paid_agenciamento_total = cols[1] or Decimal("0")
        explicit = paid_comissao_total + paid_agenciamento_total
        if explicit > 0:
            comissao_paga = explicit
        else:
            # Fallback when total_paid_* columns are still 0 across the board.
            comissao_paga = (
                db.session.query(
                    func.coalesce(func.sum(Commission.total_actual), 0)
                )
                .filter(Commission.is_final.is_(True))
                .scalar()
                or Decimal("0")
            )

    # Compatibility alias for Potencial a pagar.
    saldo_devedor = potencial_a_pagar

    # Obrigação aberta: only confirmed-but-unpaid competencies (a_apurar),
    # no projections. With a period filter, sliced to that window; otherwise
    # the engine's pending_total covers all active policies.
    if has_period:
        obrigacao_aberta = visible_a_apurar_calendar
    else:
        obrigacao_aberta = finance_engine.pending_total

    # ---- Row 2: Comissão x Agenciamento ---------------------------------

    # Totals: prefer Policy.total_paid_* (all-time, no filter); else slice
    # FinancialImport for the period. The "total" view is the authoritative
    # split between the two revenue streams.
    if has_period:
        com_total = (
            _filter_fi_by_period(
                db.session.query(
                    func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0)
                ).filter(
                    FinancialImport.match_status == "MATCHED",
                    FinancialImport.tipo_receita.ilike("%comiss%"),
                ),
                year_param,
                quarter_param,
                year_floor,
            ).scalar()
            or Decimal("0")
        )
        ag_total = (
            _filter_fi_by_period(
                db.session.query(
                    func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0)
                ).filter(
                    FinancialImport.match_status == "MATCHED",
                    FinancialImport.tipo_receita.ilike("%agenc%"),
                ),
                year_param,
                quarter_param,
                year_floor,
            ).scalar()
            or Decimal("0")
        )
    else:
        com_total = paid_comissao_total
        ag_total = paid_agenciamento_total
        # If the columns are empty, fall back to FinancialImport totals.
        if com_total == 0 and ag_total == 0:
            com_total = (
                db.session.query(
                    func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0)
                )
                .filter(
                    FinancialImport.match_status == "MATCHED",
                    FinancialImport.tipo_receita.ilike("%comiss%"),
                )
                .scalar()
                or Decimal("0")
            )
            ag_total = (
                db.session.query(
                    func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0)
                )
                .filter(
                    FinancialImport.match_status == "MATCHED",
                    FinancialImport.tipo_receita.ilike("%agenc%"),
                )
                .scalar()
                or Decimal("0")
            )

    # Series: bucketed by FinancialImport.nf_mes_recebimento (YYYY-MM).
    # Spec called for "month apuração closed". Without a per-row link from
    # commission rows to appraisal.locked_at, NF receipt month is the closest
    # signal we can derive from existing data — apuração close happens in the
    # same monthly cycle as NF processing. Re-derive from Appraisal.locked_at
    # once that attribution is wired.
    series_q = (
        db.session.query(
            FinancialImport.nf_mes_recebimento,
            FinancialImport.tipo_receita,
            func.coalesce(func.sum(FinancialImport.nf_valor_liquido), 0),
        )
        .filter(FinancialImport.match_status == "MATCHED")
    )
    series_q = _filter_fi_by_period(series_q, year_param, quarter_param, year_floor)
    series_rows = (
        series_q.group_by(
            FinancialImport.nf_mes_recebimento, FinancialImport.tipo_receita
        )
        .order_by(FinancialImport.nf_mes_recebimento)
        .all()
    )

    by_month: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"comissao": Decimal("0"), "agenciamento": Decimal("0")}
    )
    for ym, tipo, total in series_rows:
        if not ym:
            continue
        amount = total or Decimal("0")
        if _is_comissao(tipo):
            by_month[ym]["comissao"] += amount
        elif _is_agenciamento(tipo):
            by_month[ym]["agenciamento"] += amount

    months_sorted = sorted(by_month.keys())
    # Trim to last 12 months when no period filter is active, for chart legibility.
    if not has_period and len(months_sorted) > 12:
        months_sorted = months_sorted[-12:]

    comm_ag_series = [
        {
            "label": _short_pt_month(ym),
            "comissao": str(by_month[ym]["comissao"]),
            "agenciamento": str(by_month[ym]["agenciamento"]),
        }
        for ym in months_sorted
    ]

    if has_period:
        period_label = (
            f"Q{quarter_param}" if quarter_param else "Todos os trimestres"
        )
        if year_floor is not None:
            period_label += f" · {year_floor}+"
        elif year_param is not None:
            period_label += f" · {year_param}"
        else:
            period_label += " · Todos os anos"
    else:
        period_label = "Liberado · todo o histórico"

    # ---- Row 3: Fluxo de Caixa Mensal -----------------------------------

    future_months = 24

    today_ym = today.strftime("%Y-%m")
    chart_months = {
        (today + relativedelta(months=i)).strftime("%Y-%m")
        for i in range(-6, future_months + 1)
    }
    chart_months.update(finance_by_month.keys())

    fluxo_series_all = []
    for ym in sorted(chart_months):
        realized = realizado_by_month.get(ym)
        a_apurar = a_apurar_by_month.get(ym)
        projected = projected_by_month.get(ym)
        total = (realized or Decimal("0")) + (a_apurar or Decimal("0")) + (
            projected or Decimal("0")
        )
        states = []
        if realized:
            states.append(REALIZADO)
        if a_apurar:
            states.append(A_APURAR)
        if projected:
            states.append(PROJETADO)
        estado = None
        if a_apurar:
            estado = A_APURAR
        elif projected:
            estado = PROJETADO
        elif realized:
            estado = REALIZADO
        fluxo_series_all.append(
            {
                "ym": ym,
                "label": _short_pt_month(ym),
                "realizado": str(realized) if realized is not None else None,
                "a_apurar": str(a_apurar) if a_apurar is not None else None,
                "projetado": str(projected) if projected is not None else None,
                "total": str(total) if total != 0 else None,
                "estado": estado,
                "states": states,
                "is_current_month": ym == today_ym,
            }
        )

    fluxo_series = [
        point
        for point in fluxo_series_all
        if _month_matches_period(point["ym"], year_param, quarter_param, year_floor)
    ]

    visible_realizado = Decimal("0")
    visible_a_apurar = Decimal("0")
    visible_projetado = Decimal("0")
    visible_apolices: set = set()
    for point in fluxo_series:
        ym = point["ym"]
        if point["realizado"] is not None:
            visible_realizado += Decimal(point["realizado"])
        if point["a_apurar"] is not None:
            visible_a_apurar += Decimal(point["a_apurar"])
            visible_apolices.update(apolices_by_month.get(ym, set()))
        if point["projetado"] is not None:
            visible_projetado += Decimal(point["projetado"])
            visible_apolices.update(apolices_by_month.get(ym, set()))

    # Horizon strip: cumulative 30/60/90 days, snapped to whole months
    # (1 / 2 / 3 calendar months from today). Apólices = distinct policies
    # contributing to that window.
    def _cumulative(months_count: int) -> tuple[Decimal, set]:
        total = Decimal("0")
        apolices: set = set()
        for i in range(months_count):
            ym = (today + relativedelta(months=i)).strftime("%Y-%m")
            total += a_apurar_by_month.get(ym, Decimal("0"))
            total += projected_by_month.get(ym, Decimal("0"))
            apolices.update(apolices_by_month.get(ym, set()))
        return total, apolices

    next_30, ap_30 = _cumulative(1)
    next_60, ap_60 = _cumulative(2)
    next_90, ap_90 = _cumulative(3)

    # ---- Available years for the period selector -----------------------

    fi_year_rows = (
        db.session.query(func.distinct(FinancialImport.year))
        .order_by(FinancialImport.year.asc())
        .all()
    )
    policy_year_rows = (
        db.session.query(func.distinct(func.extract("year", Policy.closed_date)))
        .filter(Policy.closed_date.isnot(None))
        .all()
    )
    available_years = [int(y) for (y,) in fi_year_rows if y]
    available_years.extend(int(y) for (y,) in policy_year_rows if y)
    if not available_years:
        available_years = [today.year]
    if today.year not in available_years:
        available_years.append(today.year)
    available_years = sorted(set(available_years))

    future_year_floor = today.year + 1
    has_future_projection = any(
        int(ym.split("-")[0]) >= future_year_floor
        for ym in projected_by_month.keys()
    )

    return jsonify(
        {
            "data": {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "available_years": available_years,
                "future_year_floor": future_year_floor if has_future_projection else None,
                "period": {
                    "year": year_bucket or year_param,
                    "quarter": quarter_param,
                },
                "potencial_a_pagar": str(potencial_a_pagar),
                "comissao_potencial": str(comissao_potencial),
                "comissao_paga": str(comissao_paga),
                "saldo_devedor_total": str(saldo_devedor),
                "obrigacao_aberta": str(obrigacao_aberta),
                "comissao_agenciamento": {
                    "comissao": str(com_total),
                    "agenciamento": str(ag_total),
                    "series": comm_ag_series,
                    "period": period_label,
                },
                "fluxo_caixa": {
                    "horizon": {
                        "next_30": str(next_30),
                        "next_60": str(next_60),
                        "next_90": str(next_90),
                        "next_30_apolices": len(ap_30),
                        "next_60_apolices": len(ap_60),
                        "next_90_apolices": len(ap_90),
                    },
                    "period_summary": {
                        "realizado": str(visible_realizado),
                        "a_apurar": str(visible_a_apurar),
                        "projetado": str(visible_projetado),
                        "potencial_a_pagar": str(visible_a_apurar + visible_projetado),
                        "apolices": len(visible_apolices),
                    },
                    "period_label": period_label,
                    "series": fluxo_series,
                },
            }
        }
    )


@finance_dashboard_bp.route("/approval")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def list_approval():
    """Return appraisals in REVOPS_REVIEW, pending finance release."""
    from app.api.middlewares import paginate_query
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Appraisal.query.filter_by(
        status=AppraisalStatus.REVOPS_REVIEW
    ).order_by(Appraisal.year.desc(), Appraisal.month.desc())

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": {
            "items": [_serialize_approval_item(a) for a in items],
            "meta": meta,
        }
    })


def _serialize_approval_item(appraisal: Appraisal):
    commissions = Commission.query.filter_by(
        month=appraisal.month,
        year=appraisal.year,
    ).all()

    commission_total = sum(
        (
            Decimal(str(c.total_actual or c.monthly_actual or 0))
            for c in commissions
        ),
        Decimal("0"),
    )
    policy_ids = {c.policy_id for c in commissions if c.policy_id}
    ev_ids = {c.ev_id for c in commissions if c.ev_id}
    evs = User.query.filter(User.id.in_(ev_ids)).all() if ev_ids else []
    ev_name = None
    ev_id = None
    if len(evs) == 1:
        ev_name = evs[0].name
        ev_id = str(evs[0].id)
    elif evs:
        ev_name = f"{len(evs)} EVs"

    achievement_values = [
        Decimal(str(c.achievement_pct)) * Decimal("100")
        for c in commissions
        if c.achievement_pct is not None
    ]
    achievement_pct = None
    if achievement_values:
        achievement_pct = str(
            (sum(achievement_values, Decimal("0")) / len(achievement_values))
            .quantize(Decimal("0.01"))
        )

    return {
        "id": str(appraisal.id),
        "appraisal_id": str(appraisal.id),
        "month": appraisal.month,
        "year": appraisal.year,
        "status": appraisal.status.value,
        "validation_deadline": (
            appraisal.validation_deadline.isoformat()
            if appraisal.validation_deadline else None
        ),
        "created_at": (
            appraisal.created_at.isoformat() if appraisal.created_at else None
        ),
        "locked_at": (
            appraisal.locked_at.isoformat() if appraisal.locked_at else None
        ),
        "commission_total": str(commission_total),
        "policies_count": len(policy_ids),
        "ev_count": len(ev_ids),
        "ev_id": ev_id,
        "ev_name": ev_name or "Sem EV apurado",
        "achievement_pct": achievement_pct,
    }


@finance_dashboard_bp.route("/export")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def export_commissions():
    """Export commissions to CSV for a period — a single month, or a calendar
    quarter (mapped to its three months) for the Finance views."""
    month = request.args.get("month", type=int)
    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)

    if not year or (not month and not quarter):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "year and (month or quarter) required"}}), 400

    query = Commission.query.filter_by(year=year)
    if month:
        query = query.filter(Commission.month == month)
        period_label = f"{month:02d}"
    else:
        start_month = (quarter - 1) * 3 + 1
        query = query.filter(
            Commission.month >= start_month,
            Commission.month <= start_month + 2,
        )
        period_label = f"Q{quarter}"
    commissions = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "commission_id", "ev_id", "ev_name", "policy_id", "month", "year",
        "segment", "achievement_pct", "commission_pct",
        "monthly_estimated", "total_estimated",
        "monthly_actual", "total_actual", "is_final",
    ])

    for c in commissions:
        ev_name = c.ev.name if c.ev else ""
        writer.writerow([
            str(c.id), str(c.ev_id), ev_name, str(c.policy_id),
            c.month, c.year, c.segment,
            str(c.achievement_pct) if c.achievement_pct else "",
            str(c.commission_pct) if c.commission_pct else "",
            str(c.monthly_estimated) if c.monthly_estimated else "",
            str(c.total_estimated) if c.total_estimated else "",
            str(c.monthly_actual) if c.monthly_actual else "",
            str(c.total_actual) if c.total_actual else "",
            str(c.is_final),
        ])

    csv_data = output.getvalue()
    filename = f"commissions_{period_label}_{year}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
