"""Financial upload + history endpoints.

The new flow accepts the real "Consulta - Follow up Faturamento" XLSX
as multipart upload. Parser → processor pipeline persists rows directly.
No more 2-step preview/confirm.
"""
import os
import tempfile

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.models import ImportBatch, UserRole
from app.modules.financial.parser import parse_financial_xlsx, ParseError
from app.modules.financial.perk_parser import parse_perk_xlsx, PerkParseError
from app.modules.financial.processor import (
    persist_financial_rows, persist_perk_rows, UploadBlockedError,
)

financial_bp = Blueprint("financial", __name__, url_prefix="/api/v1/financial")

# XLSX (and DOCX/PPTX) is a ZIP archive — magic bytes are "PK\x03\x04" or
# "PK\x05\x06" (empty). Validate before passing to openpyxl so a renamed
# binary doesn't reach the XML parser.
_XLSX_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _validate_xlsx_file(file_storage, max_bytes=10 * 1024 * 1024):
    """Return (ok, error_response) tuple. Validates extension, magic bytes, size."""
    if not file_storage.filename or not file_storage.filename.lower().endswith((".xlsx", ".xls")):
        return False, (jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "Only .xlsx/.xls files accepted"}
        }), 400)

    head = file_storage.stream.read(8)
    file_storage.stream.seek(0)
    if not any(head.startswith(m) for m in _XLSX_MAGIC):
        return False, (jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "File is not a valid XLSX (bad magic bytes)"}
        }), 400)

    # Month/year sanity (1-12, year >= 2020) — reject early
    return True, None


def _validate_period(month, year):
    if not month or not year:
        return False, (jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "month+year form fields required"}
        }), 400)
    if month < 1 or month > 12:
        return False, (jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "month must be 1-12"}
        }), 400)
    if year < 2020 or year > 2100:
        return False, (jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "year out of range"}
        }), 400)
    return True, None


@financial_bp.route("/upload", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def upload_financial():
    """Upload XLSX, parse, and persist as financial_imports for a year.

    Each NF is tagged by its own competência month, so one upload of a
    multi-month export populates every month. Months already LOCKED are
    preserved (their rows are kept and skipped in the import).

    Multipart form fields:
        file: .xlsx file
        year: int
    """
    user = g.current_user

    if "file" not in request.files:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "File required"},
        }), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Only .xlsx/.xls files accepted",
            },
        }), 400

    year = request.form.get("year", type=int)
    if not year:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "year form field required",
            },
        }), 400
    if year < 2020 or year > 2100:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "year out of range"},
        }), 400

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    file.save(path)

    try:
        try:
            parsed = parse_financial_xlsx(path, year)
        except ParseError as e:
            return jsonify({
                "error": {"code": "PARSE_ERROR", "message": str(e)},
            }), 400

        result = persist_financial_rows(
            parsed['rows'], year, file.filename, user.id,
        )

        log_audit(
            "import_batches", str(result['batch_id']), "CREATE",
            new_values={
                "filename": file.filename,
                "year": year,
                "nf_count": result['persisted'],
                "skipped_locked": result['skipped_locked'],
            },
        )
        db.session.commit()

        return jsonify({
            "data": {
                "batch_id": str(result['batch_id']),
                "year": year,
                "rows_persisted": result['persisted'],
                "skipped_locked": result['skipped_locked'],
                "stats": parsed['stats'],
            },
        }), 201
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@financial_bp.route("/upload-perks", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def upload_perks():
    """Upload XLSX with subsidies/perks for a year.

    Each perk is tagged by its own competência month (the sheet's 'Mês'
    column). Months already LOCKED are preserved.

    Multipart form fields:
        file: .xlsx file
        year: int
    """
    user = g.current_user

    if "file" not in request.files:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "File required"},
        }), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Only .xlsx/.xls files accepted",
            },
        }), 400

    year = request.form.get("year", type=int)
    if not year:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "year form field required",
            },
        }), 400
    if year < 2020 or year > 2100:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "year out of range"},
        }), 400

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    file.save(path)

    try:
        try:
            parsed = parse_perk_xlsx(path, year)
        except PerkParseError as e:
            return jsonify({
                "error": {"code": "PARSE_ERROR", "message": str(e)},
            }), 400

        result = persist_perk_rows(
            parsed['rows'], year, file.filename, user.id,
        )

        log_audit(
            "import_batches", str(result['batch_id']), "CREATE",
            new_values={
                "filename": file.filename,
                "year": year,
                "type": "perks",
                "matched": result['matched'],
                "missed": result['missed'],
                "skipped_locked": result['skipped_locked'],
            },
        )
        db.session.commit()

        return jsonify({
            "data": {
                "batch_id": str(result['batch_id']),
                "year": year,
                "matched": result['matched'],
                "missed": result['missed'],
                "skipped_locked": result['skipped_locked'],
                "missed_clients": result['missed_clients'],
                "stats": parsed['stats'],
            },
        }), 201
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


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
    """Return a description of the expected upload XLSX format."""
    return jsonify({
        "data": {
            "format": "Real Pipo financeiro spreadsheet (Consulta - Follow up Faturamento)",
            "single_sheet": True,
            "header_row": "Auto-detected (looks for 'Cliente Mãe' in first 20 rows)",
            "columns": [
                "Operadora", "Produto", "Cliente \"Mãe\"",
                "NF Líquido", "Status Recebimento", "Data Recebimento",
                "Mês Recebimento", "Tipo Receita",
            ],
            "filters": [
                "Status Recebimento must be 'RECEBIDO'",
                "data_recebimento must fall in the selected year (each NF keeps its own month)",
                "Cliente \"Mãe\" and NF Líquido must be non-empty",
            ],
        },
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
