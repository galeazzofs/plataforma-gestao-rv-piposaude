import logging
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import (
    AppraisalStatus, UserRole, CnMonthlyGoal, CnMonthlyAppraisal,
    CnQuarterBonus, User,
)
from app.extensions import db
from app.modules.commissions.simulator import simulate_cn, vidas_meta_from_sao
from app.modules.commissions.cn_calculator import (
    run_cn_monthly_appraisal_with_inputs,
    validate_cn_goals,
    MissingGoalsError,
)
from app.modules.commissions.cn_bonus_calculator import run_cn_quarterly_bonus
from app.modules.workflow.state_machine import (
    transition_cn_monthly_appraisal,
    InvalidTransitionError,
)

_log = logging.getLogger(__name__)

cn_commissions_bp = Blueprint(
    "cn_commissions", __name__, url_prefix="/api/v1/commissions/cn"
)


# ── Goals ──────────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/goals")
@require_auth
def list_cn_goals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    # Admin sees one row per active CN (with merged goal data when present)
    # so the UI can seed targets without a separate "create" affordance.
    if user.role == UserRole.ADMIN:
        cns = User.query.filter_by(role=UserRole.CN, active=True).order_by(User.name).all()
    else:
        cns = [user]

    goal_map = {}
    if month and year:
        goal_q = CnMonthlyGoal.query.filter_by(month=month, year=year)
        if user.role == UserRole.CN:
            goal_q = goal_q.filter_by(cn_id=user.id)
        goal_map = {gl.cn_id: gl for gl in goal_q.all()}

    data = [_serialize_cn_row(cn, goal_map.get(cn.id), month, year) for cn in cns]
    return jsonify({"data": data})


@cn_commissions_bp.route("/goals", methods=["PUT"])
@require_auth
def upsert_cn_goals():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    if not body:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400
    try:
        month = int(body["month"])
        year = int(body["year"])
        items = body["items"]
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400

    try:
        for item in items:
            goal = CnMonthlyGoal.query.filter_by(
                cn_id=item["cn_id"], month=month, year=year
            ).first()
            if goal is None:
                goal = CnMonthlyGoal(cn_id=item["cn_id"], month=month, year=year)
                db.session.add(goal)
            sao_target = _decimal_or_zero(item.get("sao_target"))
            goal.sao_target = sao_target
            # Derive the lives target from the CN porte (SAO × factor) — the
            # same rule the simulator uses — so it is never hand-typed.
            cn = db.session.get(User, item["cn_id"])
            porte = (cn.porte.value if (cn and hasattr(cn.porte, "value"))
                     else (cn.porte if cn else None))
            auto = vidas_meta_from_sao(sao_target, porte) if porte else None
            goal.vidas_target = (
                auto if (auto and auto > 0)
                else _decimal_or_zero(item.get("vidas_target"))
            )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500
    return jsonify({"data": {"updated": len(items)}}), 200


# ── Apuração ───────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/appraisal", methods=["POST"])
@require_auth
def run_cn_appraisal():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    if not body:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400
    try:
        month = int(body["month"])
        year = int(body["year"])
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400
    inputs = body.get("inputs", [])

    try:
        result = run_cn_monthly_appraisal_with_inputs(month, year, inputs)
        db.session.commit()
        return jsonify({"data": result})
    except MissingGoalsError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "MISSING_GOALS", "missing": e.missing}}), 422
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500


@cn_commissions_bp.route("/appraisal")
@require_auth
def list_cn_appraisals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    query = CnMonthlyAppraisal.query
    if month:
        query = query.filter_by(month=month)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.CN:
        query = query.filter_by(cn_id=user.id)

    items = query.order_by(CnMonthlyAppraisal.year.desc(),
                           CnMonthlyAppraisal.month.desc()).all()
    return jsonify({"data": [_serialize_appraisal(a) for a in items]})


@cn_commissions_bp.route("/appraisal/<appraisal_id>/finalize", methods=["POST"])
@require_auth
def finalize_cn_appraisal(appraisal_id):
    """Drive the CN monthly appraisal straight to LOCKED.

    Kept for backwards compatibility with existing UI; new code should
    prefer the explicit transition endpoint.
    """
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.status == AppraisalStatus.LOCKED:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    # Walk through the state machine to LOCKED. This preserves the
    # invariants enforced by transition_cn_monthly_appraisal. Rows
    # already inside the chain get only their remaining forward steps —
    # walking the full chain would attempt a backward transition.
    chain = [
        AppraisalStatus.VALIDATING,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LOCKED,
    ]
    start = chain.index(appraisal.status) + 1 if appraisal.status in chain else 0
    try:
        for s in chain[start:]:
            transition_cn_monthly_appraisal(appraisal, s)
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    db.session.commit()
    return jsonify({"data": _serialize_appraisal(appraisal)})


@cn_commissions_bp.route("/appraisal/<appraisal_id>/contest", methods=["POST"])
@require_auth
def contest_cn_appraisal(appraisal_id):
    """CN opens a contestation on their own monthly appraisal in
    VALIDATING — routes to REVOPS_REVIEW with a flag, just like the
    quarterly Appraisal in #36.
    """
    user = g.current_user
    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    if user.role == UserRole.CN and str(appraisal.cn_id) != str(user.id):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403
    if user.role not in (UserRole.CN, UserRole.ADMIN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    if appraisal.status != AppraisalStatus.VALIDATING:
        return jsonify({
            "error": {"code": "INVALID_STATE",
                      "message": (f"Contestation only allowed in VALIDATING "
                                   f"(current: {appraisal.status.value})")},
        }), 409

    body = request.get_json() or {}
    note = (body.get("note") or "").strip()
    if not note:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "note is required"},
        }), 400

    appraisal.has_contestation = True
    appraisal.contestation_note = note
    appraisal.resolution_note = None
    appraisal.status = AppraisalStatus.REVOPS_REVIEW
    db.session.commit()
    return jsonify({"data": _serialize_appraisal(appraisal)})


@cn_commissions_bp.route(
    "/appraisal/<appraisal_id>/resolve-contestation", methods=["POST"],
)
@require_auth
def resolve_cn_contestation(appraisal_id):
    """RevOps resolves a CN contestation. Requires resolution_note."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if not appraisal.has_contestation:
        return jsonify({
            "error": {"code": "INVALID_STATE",
                      "message": "no open contestation on this appraisal"},
        }), 409

    body = request.get_json() or {}
    resolution = (body.get("resolution_note") or "").strip()
    if not resolution:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "resolution_note is required"},
        }), 400

    appraisal.has_contestation = False
    appraisal.resolution_note = resolution
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()
    return jsonify({"data": _serialize_appraisal(appraisal)})


@cn_commissions_bp.route("/appraisal/<appraisal_id>/transition", methods=["POST"])
@require_auth
def transition_cn_appraisal_endpoint(appraisal_id):
    """Move a CN monthly appraisal to a new status.

    Body: {"to": "VALIDATING" | "LIDER_REVIEW" | ...}
    Role check: ADMIN can drive any transition. CNs can only move their
    own appraisal from VALIDATING → LIDER_REVIEW (auto-approve their data).
    Líder de Vendas can drive LIDER_REVIEW → REVOPS_REVIEW.
    """
    user = g.current_user
    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    body = request.get_json() or {}
    to_status_str = body.get("to")
    if not to_status_str:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "'to' field required"},
        }), 400

    try:
        new_status = AppraisalStatus(to_status_str)
    except ValueError:
        valid = [s.value for s in AppraisalStatus]
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": f"Invalid status. Valid: {valid}"},
        }), 400

    # Coarse role gate. Finer per-state rules can land in a follow-up.
    if user.role == UserRole.ADMIN:
        pass
    elif user.role == UserRole.CN:
        if str(appraisal.cn_id) != str(user.id):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403
        if not (appraisal.status == AppraisalStatus.VALIDATING
                and new_status == AppraisalStatus.LIDER_REVIEW):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403
    elif user.role == UserRole.LIDER_VENDAS:
        if not (appraisal.status == AppraisalStatus.LIDER_REVIEW
                and new_status == AppraisalStatus.REVOPS_REVIEW):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403
    else:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    try:
        transition_cn_monthly_appraisal(appraisal, new_status)
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    return jsonify({"data": _serialize_appraisal(appraisal)})


@cn_commissions_bp.route("/appraisal/transition-month", methods=["POST"])
@require_auth
def transition_cn_month():
    """Bulk-advance every CN monthly appraisal of (month, year).

    Rows already in the target status are ignored; rows with an open
    contestation or an invalid source state are skipped and reported —
    they never block the rest. ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        month = int(body["month"])
        year = int(body["year"])
        new_status = AppraisalStatus(body["to"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month, year and to (valid status) required"},
        }), 400

    rows = CnMonthlyAppraisal.query.filter_by(month=month, year=year).all()
    if not rows:
        return jsonify({
            "error": {"code": "NOT_FOUND",
                      "message": f"No CN appraisals for {month:02d}/{year}"},
        }), 404

    advanced, skipped = 0, []
    for row in rows:
        if row.status == new_status:
            continue
        if row.has_contestation:
            skipped.append({"cn_id": str(row.cn_id),
                            "reason": "contestação aberta"})
            continue
        try:
            transition_cn_monthly_appraisal(row, new_status)
            advanced += 1
        except InvalidTransitionError as e:
            skipped.append({"cn_id": str(row.cn_id), "reason": str(e)})
    db.session.commit()
    return jsonify({"data": {"advanced": advanced, "skipped": skipped,
                             "to": new_status.value}})


@cn_commissions_bp.route("/appraisal/finalize-month", methods=["POST"])
@require_auth
def finalize_cn_month():
    """Bulk-finalize: walk every non-LOCKED CN appraisal of (month, year)
    through the state machine to LOCKED. Contested rows are skipped.
    The last LOCK re-evaluates the month's cycle (inside the state
    machine). ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        month = int(body["month"])
        year = int(body["year"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month and year required (integers)"},
        }), 400

    rows = CnMonthlyAppraisal.query.filter_by(month=month, year=year).all()
    if not rows:
        return jsonify({
            "error": {"code": "NOT_FOUND",
                      "message": f"No CN appraisals for {month:02d}/{year}"},
        }), 404

    chain = [
        AppraisalStatus.VALIDATING,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LOCKED,
    ]
    advanced, skipped = 0, []
    for row in rows:
        if row.status == AppraisalStatus.LOCKED:
            continue
        if row.has_contestation:
            skipped.append({"cn_id": str(row.cn_id),
                            "reason": "contestação aberta"})
            continue
        try:
            # Only apply steps that come after the row's current status.
            start = chain.index(row.status) + 1 if row.status in chain else 0
            for s in chain[start:]:
                transition_cn_monthly_appraisal(row, s)
            advanced += 1
        except InvalidTransitionError as e:
            skipped.append({"cn_id": str(row.cn_id), "reason": str(e)})
    db.session.commit()
    return jsonify({"data": {"advanced": advanced, "skipped": skipped}})


# ── Simulator ──────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/simulate", methods=["POST"])
@require_auth
def simulate_cn_endpoint():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    if not body:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    # CN can only simulate with their own nivel
    if user.role == UserRole.CN:
        nivel = user.nivel.value if hasattr(user.nivel, "value") else (user.nivel or "CN1")
        porte = user.porte.value if hasattr(user.porte, "value") else user.porte
    else:
        nivel = body.get("nivel", "CN1")
        porte = body.get("porte")

    try:
        sao_meta = Decimal(str(body["sao_meta"]))
        vidas_meta = (
            Decimal(str(body["vidas_meta"]))
            if body.get("vidas_meta") not in (None, "")
            else vidas_meta_from_sao(sao_meta, porte)
        )
        result = simulate_cn(
            nivel=nivel,
            sao_meta=sao_meta,
            sao_realizado=Decimal(str(body["sao_realizado"])),
            vidas_meta=vidas_meta,
            vidas_realizado=Decimal(str(body["vidas_realizado"])),
        )
        result.update({
            "nivel": nivel,
            "porte": porte,
            "vidas_meta": str(vidas_meta),
        })
    except (KeyError, TypeError, ValueError, InvalidOperation) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400
    return jsonify({"data": result})


# ── Serialisers ────────────────────────────────────────────────────────────

def _decimal_or_zero(v):
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v))


def _serialize_cn_row(cn, goal, month, year):
    porte = cn.porte.value if hasattr(cn.porte, "value") else cn.porte
    nivel = cn.nivel.value if hasattr(cn.nivel, "value") else cn.nivel
    sao_target = goal.sao_target if goal else None
    # Lives target is derived from porte (SAO × factor), like the simulator,
    # so the UI shows it read-only instead of asking RevOps to type it.
    vidas_auto = (
        vidas_meta_from_sao(Decimal(str(sao_target)), porte)
        if (sao_target is not None and porte) else None
    )
    if vidas_auto is not None and vidas_auto > 0:
        vidas_target = str(vidas_auto)
    elif goal:
        vidas_target = str(goal.vidas_target)
    else:
        vidas_target = None
    return {
        "id": str(goal.id) if goal else None,
        "cn_id": str(cn.id),
        "cn_name": cn.name,
        "nivel": nivel,
        "porte": porte,
        "month": month,
        "year": year,
        "sao_target": str(sao_target) if sao_target is not None else None,
        "vidas_target": vidas_target,
    }


# ── Quarterly Bonus (issue #33) ────────────────────────────────────────────


def _serialize_quarter_bonus(b):
    return {
        "id": str(b.id),
        "cn_id": str(b.cn_id),
        "cn_name": b.cn.name if b.cn else None,
        "quarter": b.quarter,
        "year": b.year,
        "sao_trim_realizado": str(b.sao_trim_realizado),
        "sao_trim_meta": str(b.sao_trim_meta),
        "pct_sao_trim": str(b.pct_sao_trim),
        "multiplicador": str(b.multiplicador),
        "bonus_amount": str(b.bonus_amount),
        "salario_base_snapshot": (
            str(b.salario_base_snapshot)
            if b.salario_base_snapshot is not None else None
        ),
        "is_final": b.is_final,
    }


@cn_commissions_bp.route("/quarterly-bonus", methods=["POST"])
@require_auth
def run_cn_quarterly_bonus_endpoint():
    """Run the trimestral CN bonus calculator for (quarter, year). ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        quarter = int(body.get("quarter"))
        year = int(body.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter and year required (integers)"},
        }), 400

    try:
        result = run_cn_quarterly_bonus(quarter, year)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500

    return jsonify({"data": result})


@cn_commissions_bp.route("/quarterly-bonus")
@require_auth
def list_cn_quarterly_bonus():
    """List CN trimestral bonuses, optionally filtered by quarter/year."""
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)

    query = CnQuarterBonus.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.CN:
        query = query.filter_by(cn_id=user.id)

    items = query.order_by(
        CnQuarterBonus.year.desc(), CnQuarterBonus.quarter.desc(),
    ).all()
    return jsonify({"data": [_serialize_quarter_bonus(b) for b in items]})


@cn_commissions_bp.route("/quarterly-bonus/finalize", methods=["POST"])
@require_auth
def finalize_cn_quarterly_bonus():
    """Lock all non-final CN bonuses for (quarter, year). ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        quarter = int(body.get("quarter"))
        year = int(body.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter and year required (integers)"},
        }), 400

    rows = CnQuarterBonus.query.filter_by(
        quarter=quarter, year=year, is_final=False,
    ).all()
    for row in rows:
        row.is_final = True
    db.session.commit()

    # Issue #37b: locking the last bonus row for a quarter may complete
    # the quarter-end month's cycle. Re-evaluate.
    from app.modules.workflow.state_machine import _maybe_lock_attached_cycle
    try:
        _maybe_lock_attached_cycle(quarter * 3, year)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _log.exception("cycle re-evaluation after CN bonus finalize failed")

    return jsonify({"data": {"finalized": len(rows)}})


def _serialize_appraisal(a):
    return {
        "id": str(a.id),
        "cn_id": str(a.cn_id),
        "cn_name": a.cn.name if a.cn else None,
        "month": a.month,
        "year": a.year,
        "sao_realizado": str(a.sao_realizado),
        "vidas_realizado": str(a.vidas_realizado),
        "pct_sao": str(a.pct_sao),
        "pct_vidas": str(a.pct_vidas),
        "score_final": str(a.score_final),
        "multiplicador": str(a.multiplicador),
        "commission_amount": str(a.commission_amount),
        "status": a.status.value if a.status else None,
        "is_final": a.is_final,
        "has_contestation": bool(a.has_contestation),
        "contestation_note": a.contestation_note,
        "resolution_note": a.resolution_note,
    }
