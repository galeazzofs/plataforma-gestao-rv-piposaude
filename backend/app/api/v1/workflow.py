from collections import defaultdict

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.models import (
    Appraisal, AppraisalStatus, UserRole,
    Commission, FinancialImport, User,
    EvValidation,
)
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    pending_required_lideres,
    InvalidTransitionError,
)
from app.modules.commissions.calculator import MissingAchievementsError
from app.modules.workflow.appraisal_review import build_period_detail

workflow_bp = Blueprint("workflow", __name__, url_prefix="/api/v1/appraisals")


@workflow_bp.route("")
@require_auth
def list_appraisals():
    """List appraisals."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Appraisal.query.order_by(Appraisal.year.desc(), Appraisal.month.desc())

    status = request.args.get("status")
    if status:
        query = query.filter(Appraisal.status == status)

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_appraisal(a) for a in items],
        "meta": meta,
    })


@workflow_bp.route("/<appraisal_id>")
@require_auth
def get_appraisal(appraisal_id):
    """Get a single appraisal."""
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.LIDER_VENDAS)
def create_appraisal():
    """Create a new appraisal in DRAFT status."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    month = data.get("month")
    year = data.get("year")

    if not month or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month and year required"}}), 400

    try:
        month = int(month)
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month and year must be integers"}}), 400

    if month < 1 or month > 12:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month must be 1..12"}}), 400

    user = g.current_user

    try:
        appraisal = start_appraisal(month=month, year=year, created_by=user.id)
        log_audit("appraisals", appraisal.id, "CREATE", new_values={"month": month, "year": year})
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "CONFLICT", "message": str(e)}}), 409

    return jsonify({"data": _serialize_appraisal(appraisal)}), 201


@workflow_bp.route("/<appraisal_id>/transition", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.LIDER_VENDAS, UserRole.FINANCE)
def transition(appraisal_id):
    """Transition an appraisal to a new status.

    Body: { "to": "CALCULATING" | "VALIDATING" | "LIDER_REVIEW" | "REVOPS_REVIEW" | "LOCKED", ... }
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    data = request.get_json() or {}
    to_status_str = data.get("to")
    if not to_status_str:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "'to' field required"}}), 400

    try:
        new_status = AppraisalStatus(to_status_str)
    except ValueError:
        valid = [s.value for s in AppraisalStatus]
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid status. Valid: {valid}"}}), 400

    user = g.current_user
    old_status = appraisal.status.value

    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.REVOPS_REVIEW
        and user.role != UserRole.ADMIN
    ):
        return jsonify({
            "error": {
                "code": "FORBIDDEN",
                "message": "Only RevOps can approve departed-EV appraisals.",
            },
        }), 403

    kwargs = {}
    if new_status == AppraisalStatus.VALIDATING:
        kwargs["validation_deadline"] = data.get("validation_deadline")
    if new_status == AppraisalStatus.LOCKED:
        kwargs["approved_by"] = user.id

    try:
        transition_appraisal(appraisal, new_status, **kwargs)
        log_audit(
            "appraisals", appraisal.id, "UPDATE",
            old_values={"status": old_status},
            new_values={"status": new_status.value},
        )
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "MISSING_ACHIEVEMENTS", "message": str(e), "missing": e.missing}}), 422

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def delete_appraisal(appraisal_id):
    """Delete an appraisal and its associated commissions / NF matches."""
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    month, year = appraisal.month, appraisal.year

    # Drop the EV validations first — they FK appraisal_id with no cascade, so
    # the appraisal can't be deleted while any exist (i.e. once released).
    EvValidation.query.filter_by(appraisal_id=appraisal.id).delete()

    # Delete ALL commissions for this month (including is_final when LOCKED)
    Commission.query.filter_by(month=month, year=year).delete()

    # Reset NF match status back to UNMATCHED
    FinancialImport.query.filter(
        FinancialImport.month == month,
        FinancialImport.year == year,
    ).update({
        FinancialImport.match_status: 'UNMATCHED',
        FinancialImport.policy_id: None,
        FinancialImport.matched_at: None,
    })

    log_audit("appraisals", appraisal.id, "DELETE",
              old_values={"month": month, "year": year, "status": appraisal.status.value})

    db.session.delete(appraisal)
    db.session.commit()

    return jsonify({"data": {"deleted": True}}), 200


@workflow_bp.route("/<appraisal_id>/contest", methods=["POST"])
@require_auth
def contest_appraisal(appraisal_id):
    """Open a contestation on an appraisal in VALIDATING.

    Requires a non-empty note. Sets has_contestation=True and routes the
    appraisal straight to REVOPS_REVIEW so the contestation skips the
    LIDER_REVIEW step.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    if appraisal.status != AppraisalStatus.VALIDATING:
        return jsonify({
            "error": {
                "code": "INVALID_STATE",
                "message": (
                    f"Contestation only allowed in VALIDATING "
                    f"(current: {appraisal.status.value})"
                ),
            },
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

    # Walk to REVOPS_REVIEW: VALIDATING → LIDER_REVIEW is normally blocked
    # by has_contestation, so route via that step explicitly with the
    # contestation-skip path. We bypass transition_appraisal's block by
    # going through LIDER_REVIEW first (with a contested flag) is not
    # desired; instead, set status directly. The state graph allows
    # LIDER_REVIEW → REVOPS_REVIEW, so we set LIDER_REVIEW → REVOPS_REVIEW
    # via the state machine after a forced jump from VALIDATING.
    # Simpler: set appraisal.status = REVOPS_REVIEW directly here, which
    # is the documented contestation route per issue #36.
    appraisal.status = AppraisalStatus.REVOPS_REVIEW

    log_audit(
        "appraisals", appraisal.id, "CONTEST",
        new_values={"has_contestation": True, "note": note},
    )
    db.session.commit()

    try:
        from app.modules.notifications.slack import notify_contestation_opened
        notify_contestation_opened(
            appraisal.month, appraisal.year, g.current_user.name,
        )
    except Exception as e:  # pragma: no cover — graceful failure
        import logging
        logging.getLogger(__name__).warning(
            f"Slack notify_contestation_opened failed: {e}"
        )

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>/resolve-contestation", methods=["POST"])
@require_role(UserRole.ADMIN)
def resolve_contestation(appraisal_id):
    """RevOps resolves a contestation. Requires a resolution note.

    Clears has_contestation and routes the appraisal back to VALIDATING
    so the contesting party can re-validate with the resolution context.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
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
    # Route back to VALIDATING so the contesting party can re-validate.
    appraisal.status = AppraisalStatus.VALIDATING

    log_audit(
        "appraisals", appraisal.id, "RESOLVE_CONTESTATION",
        new_values={"has_contestation": False, "resolution_note": resolution},
    )
    db.session.commit()

    # Best-effort: DM the contestant if we can identify them via the
    # latest CONTEST audit log entry.
    try:
        from app.modules.notifications.slack import notify_contestation_resolved
        from app.models import AuditLog
        contest_log = (
            AuditLog.query
            .filter_by(table_name="appraisals", row_id=appraisal.id, action="CONTEST")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        if contest_log and contest_log.user_id:
            contestant = db.session.get(User, contest_log.user_id)
            if contestant is not None:
                notify_contestation_resolved(
                    contestant, appraisal.month, appraisal.year,
                )
    except Exception as e:  # pragma: no cover — graceful failure
        import logging
        logging.getLogger(__name__).warning(
            f"Slack notify_contestation_resolved failed: {e}"
        )

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>/recalculate", methods=["POST"])
@require_role(UserRole.ADMIN)
def recalculate(appraisal_id):
    """Re-run the calculator for this appraisal's (month, year).

    Allowed when appraisal is in CALCULATING / VALIDATING / LIDER_REVIEW / REVOPS_REVIEW.
    Blocked when LOCKED. Returns the enriched detail payload.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({
            "error": {"code": "NOT_FOUND", "message": "Appraisal not found"},
        }), 404

    if appraisal.status == AppraisalStatus.LOCKED:
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": "Apuração está LOCKED — recalculate não permitido",
            },
        }), 409

    from app.modules.commissions.calculator import (
        run_monthly_appraisal, MissingAchievementsError,
    )
    try:
        # Missing achievements don't block — they fall back to 0% and surface
        # as a warning in the detail payload (same as the preview).
        run_monthly_appraisal(
            appraisal.month, appraisal.year, validate_achievements=False
        )
        db.session.commit()
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({
            "error": {
                "code": "MISSING_ACHIEVEMENTS",
                "message": str(e),
                "missing": e.missing,
            },
        }), 422

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/preview", methods=["POST"])
@require_role(UserRole.ADMIN)
def preview_appraisal():
    """Read-only monthly draft of the EV commission apuração.

    Runs the real monthly calculator against whatever financial data is
    currently uploaded for (month, year), builds the same review payload
    the CALCULATING screen renders, then rolls the whole transaction back.

    Nothing is persisted: no Commission rows, no Policy mutations
    (installments_paid / first_payment_real / commission_status), no NF
    match_status changes, and no Slack notifications fire. This lets RevOps
    sanity-check the apuração mid-month — e.g. as NFs land —
    without opening an appraisal or touching any state.

    Missing achievements do NOT block a draft (unlike the real apuração): the
    affected policies fall back to 0% achievement and the gaps come back in
    `missing_achievements` as a warning.

    Body: { "month": 1..12, "year": int }
    """
    data = request.get_json() or {}
    try:
        month = int(data.get("month"))
        year = int(data.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month and year required (integers)"},
        }), 400

    if month not in range(1, 13):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month must be 1..12"},
        }), 400

    from app.modules.commissions.calculator import (
        run_monthly_appraisal, validate_achievements_for_appraisal,
    )
    try:
        # Report (don't enforce) the achievement gaps, then run the real
        # calculator with the gate disabled so a draft is always produced.
        missing_achievements = validate_achievements_for_appraisal(month, year)
        run_monthly_appraisal(month, year, validate_achievements=False)
        detail = build_period_detail(month, year)
    finally:
        # A preview must never persist. Nothing here was committed, so a full
        # rollback discards everything the calculator flushed — commissions,
        # policy clock mutations and NF match statuses all evaporate. The
        # detail payload is already materialised into plain values above, so
        # it survives the rollback.
        db.session.rollback()

    return jsonify({"data": {
        "month": month, "year": year, "preview": True,
        "missing_achievements": missing_achievements, **detail,
    }})


# ── Serializer ───────────────────────────────────────────────────────


def _serialize_appraisal(appraisal, detail=False):
    data = {
        "id": str(appraisal.id),
        "month": appraisal.month,
        "year": appraisal.year,
        "status": appraisal.status.value,
        "validation_deadline": (
            appraisal.validation_deadline.isoformat()
            if appraisal.validation_deadline else None
        ),
        "created_by": str(appraisal.created_by),
        "created_at": (
            appraisal.created_at.isoformat() if appraisal.created_at else None
        ),
        "locked_at": (
            appraisal.locked_at.isoformat() if appraisal.locked_at else None
        ),
        "has_contestation": bool(appraisal.has_contestation),
        "contestation_note": appraisal.contestation_note,
        "resolution_note": appraisal.resolution_note,
    }
    if detail:
        data["approved_by_finance"] = (
            str(appraisal.approved_by_finance)
            if appraisal.approved_by_finance else None
        )
        data["validation_count"] = len(appraisal.validations)
        data.update(_build_appraisal_detail(appraisal))
    return data


def _build_appraisal_detail(appraisal):
    """Build the rich review payload for an appraisal, keyed on its period,
    then layer on the EV validation status (who approved / who is still
    pending / who contested) so the review screen can show approval progress.
    Only persisted appraisals carry this — the read-only preview, which calls
    build_period_detail directly, has no validations."""
    detail = build_period_detail(appraisal.month, appraisal.year)
    _attach_validation_status(appraisal, detail)
    _attach_lider_gate(appraisal, detail)
    return detail


def _attach_lider_gate(appraisal, detail):
    """Surface the leader gate: which required líderes still haven't validated
    own for the quarter and are therefore blocking the advance out of
    VALIDATING, even when every EV validation is already approved."""
    quarter = (appraisal.month - 1) // 3 + 1
    leaders = []
    for lider_id, own in pending_required_lideres(appraisal):
        u = db.session.get(User, lider_id)
        leaders.append({
            "id": str(lider_id),
            "name": u.name if u else "—",
            "has_appraisal": own is not None,
            "own_status": (
                own.status.value
                if own is not None and hasattr(own.status, "value") else None
            ),
        })
    detail["lider_gate"] = {
        "quarter": quarter,
        "year": appraisal.year,
        "blocked": len(leaders) > 0,
        "pending_leaders": leaders,
    }


def _validation_counts(validations):
    """Roll a list of EvValidation rows into a status breakdown."""
    counts = {
        "total": len(validations), "pending": 0, "approved": 0,
        "auto_approved": 0, "contested": 0, "resolved": 0,
    }
    for v in validations:
        key = v.status.value.lower()
        counts[key] = counts.get(key, 0) + 1
    done = counts["approved"] + counts["auto_approved"] + counts["resolved"]
    counts["done"] = done
    counts["all_done"] = counts["total"] > 0 and done == counts["total"]
    return counts


def _attach_validation_status(appraisal, detail):
    """Annotate each EV (and each apurada policy) in the detail payload with
    its validation status for this appraisal, plus a top-level summary."""
    validations = EvValidation.query.filter_by(appraisal_id=appraisal.id).all()
    by_ev = defaultdict(list)
    by_policy = {}
    for v in validations:
        by_ev[str(v.ev_id)].append(v)
        by_policy[(str(v.ev_id), str(v.policy_id))] = v.status.value

    for ev in detail.get("ev_summary", []):
        ev["validation_status"] = _validation_counts(by_ev.get(ev["ev_id"], []))
        for p in ev.get("policies", []):
            p["validation_status"] = by_policy.get((ev["ev_id"], p["policy_id"]))

    detail["validation_totals"] = _validation_counts(validations)


