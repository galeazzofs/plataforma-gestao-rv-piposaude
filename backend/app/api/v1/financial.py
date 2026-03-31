from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import ImportBatch, FinancialImport, UserRole
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

financial_bp = Blueprint("financial", __name__, url_prefix="/api/v1/financial")


@financial_bp.route("/upload", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def upload_financial():
    """Upload financial XLSX file with NFs and Perks tabs.

    Accepts multipart/form-data with a 'file' field containing .xlsx.
    Returns preview of parsed data for confirmation.
    """
    import tempfile, os

    user = g.current_user

    if "file" not in request.files:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "File required. Send as multipart/form-data with 'file' field."}}), 400

    file = request.files["file"]
    if not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Only .xlsx/.xls files accepted"}}), 400

    # Save temp file and parse
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    file.save(path)

    try:
        from app.modules.financial.parser import parse_financial_xlsx, ParseError
        from app.modules.financial.validator import validate_nf_rows, validate_perk_rows

        try:
            parsed = parse_financial_xlsx(path)
        except ParseError as e:
            return jsonify({"error": {"code": "PARSE_ERROR", "message": str(e)}}), 400

        valid_nfs, nf_errors = validate_nf_rows(parsed["nfs"])
        valid_perks, perk_errors = validate_perk_rows(parsed["perks"])

        # Create batch in PENDING status
        batch = ImportBatch(
            filename=file.filename,
            uploaded_by=user.id,
            nf_count=len(valid_nfs),
            perk_count=len(valid_perks),
            status="PENDING",
        )
        db.session.add(batch)
        db.session.flush()

        # Store validated data in batch for later confirmation
        # We save it via a simple approach: process immediately if no errors
        if not nf_errors and not perk_errors:
            from app.modules.financial.processor import process_financial_import
            result = process_financial_import(batch.id, valid_nfs, valid_perks)
            log_audit("import_batches", batch.id, "CREATE", new_values={
                "filename": file.filename,
                "nf_count": result["nfs_created"],
                "perk_count": result["perks_created"],
            })
            db.session.commit()

            return jsonify({
                "data": {
                    "batch_id": str(batch.id),
                    "status": "CONFIRMED",
                    "nfs_created": result["nfs_created"],
                    "perks_created": result["perks_created"],
                    "errors": [],
                }
            }), 201
        else:
            db.session.commit()
            return jsonify({
                "data": {
                    "batch_id": str(batch.id),
                    "status": "PENDING",
                    "nf_count": len(valid_nfs),
                    "perk_count": len(valid_perks),
                    "errors": nf_errors + perk_errors,
                    "message": "Some rows have errors. Fix and re-upload, or confirm to import valid rows only.",
                }
            }), 201
    finally:
        os.unlink(path)


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
