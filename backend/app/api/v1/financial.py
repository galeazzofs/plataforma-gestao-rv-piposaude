from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import ImportBatch, FinancialImport, UserRole
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

financial_bp = Blueprint("financial", __name__, url_prefix="/api/v1/financial")


@financial_bp.route("/upload", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def upload_financial():
    """Upload financial data (NFs + Perks) for processing.

    Expects JSON body with:
      - nfs: list of NF dicts
      - perks: list of perk dicts
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    nfs = data.get("nfs", [])
    perks = data.get("perks", [])
    filename = data.get("filename", "upload.json")

    user = g.current_user

    from app.modules.financial.validator import validate_nf_rows, validate_perk_rows

    valid_nfs, nf_errors = validate_nf_rows(nfs)
    valid_perks, perk_errors = validate_perk_rows(perks)
    validation_errors = nf_errors + perk_errors

    if validation_errors:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Some rows failed validation",
                "details": validation_errors,
            }
        }), 422

    # Create batch record
    batch = ImportBatch(
        filename=filename,
        uploaded_by=user.id,
        nf_count=len(valid_nfs),
        perk_count=len(valid_perks),
        status="PENDING",
    )
    db.session.add(batch)
    db.session.flush()

    log_audit("import_batches", batch.id, "CREATE", new_values={"filename": filename, "nf_count": len(valid_nfs)})
    db.session.commit()

    return jsonify({
        "data": {
            "batch_id": str(batch.id),
            "nf_count": len(valid_nfs),
            "perk_count": len(valid_perks),
            "status": "PENDING",
            "message": "Upload accepted — confirm to apply",
        }
    }), 201


@financial_bp.route("/confirm/<batch_id>", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def confirm_financial(batch_id):
    """Confirm and apply a pending financial batch."""
    batch = db.session.get(ImportBatch, batch_id)
    if batch is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Batch not found"}}), 404

    if batch.status != "PENDING":
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": f"Batch already in status: {batch.status}",
            }
        }), 409

    # Check if batch already has imports
    existing_imports = FinancialImport.query.filter_by(import_batch_id=batch_id).count()
    if existing_imports > 0:
        return jsonify({
            "error": {"code": "CONFLICT", "message": "Batch already has imported records"}
        }), 409

    batch.status = "CONFIRMED"
    log_audit("import_batches", batch.id, "UPDATE", old_values={"status": "PENDING"}, new_values={"status": "CONFIRMED"})
    db.session.commit()

    return jsonify({
        "data": {
            "batch_id": str(batch.id),
            "status": "CONFIRMED",
        }
    })


@financial_bp.route("/history")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def financial_history():
    """List import batch history."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = ImportBatch.query.order_by(ImportBatch.created_at.desc())
    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_batch(b) for b in items],
        "meta": meta,
    })


@financial_bp.route("/template")
@require_auth
def financial_template():
    """Return the expected upload template schema."""
    return jsonify({
        "data": {
            "nfs": [
                {
                    "hubspot_ticket_id": "string (required)",
                    "nf_valor_liquido": "number (required)",
                    "nf_mes_recebimento": "YYYY-MM (required)",
                }
            ],
            "perks": [
                {
                    "client_name": "string (required)",
                    "perk_type": "string (required)",
                    "value": "number (required)",
                    "period": "YYYY-MM (required)",
                }
            ],
        }
    })


def _serialize_batch(batch):
    return {
        "id": str(batch.id),
        "filename": batch.filename,
        "uploaded_by": str(batch.uploaded_by),
        "nf_count": batch.nf_count,
        "perk_count": batch.perk_count,
        "status": batch.status,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }
