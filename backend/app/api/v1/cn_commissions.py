from decimal import Decimal
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, CnMonthlyGoal, CnMonthlyAppraisal, User
from app.extensions import db
from app.modules.commissions.simulator import simulate_cn
from app.modules.commissions.cn_calculator import (
    run_cn_monthly_appraisal_with_inputs,
    validate_cn_goals,
    MissingGoalsError,
)

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
            goal.sao_target = _decimal_or_zero(item.get("sao_target"))
            goal.vidas_target = _decimal_or_zero(item.get("vidas_target"))
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
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.is_final:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    appraisal.is_final = True
    db.session.commit()
    return jsonify({"data": _serialize_appraisal(appraisal)})


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
        nivel = user.nivel.value if user.nivel else "CN1"
    else:
        nivel = body.get("nivel", "CN1")

    try:
        result = simulate_cn(
            nivel=nivel,
            sao_meta=Decimal(str(body["sao_meta"])),
            sao_realizado=Decimal(str(body["sao_realizado"])),
            vidas_meta=Decimal(str(body["vidas_meta"])),
            vidas_realizado=Decimal(str(body["vidas_realizado"])),
        )
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400
    return jsonify({"data": result})


# ── Serialisers ────────────────────────────────────────────────────────────

def _decimal_or_zero(v):
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v))


def _serialize_cn_row(cn, goal, month, year):
    return {
        "id": str(goal.id) if goal else None,
        "cn_id": str(cn.id),
        "cn_name": cn.name,
        "month": month,
        "year": year,
        "sao_target": str(goal.sao_target) if goal else None,
        "vidas_target": str(goal.vidas_target) if goal else None,
    }


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
        "is_final": a.is_final,
    }
