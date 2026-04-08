"""Persist parsed financial rows into financial_imports.

The new flow has no PENDING/preview state — once parsed, rows are
committed immediately. Re-uploads delete the period's rows and mark
old batches as SUPERSEDED.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models import FinancialImport, ImportBatch, Appraisal, AppraisalStatus


class UploadBlockedError(Exception):
    """Raised when an upload is rejected because the apuração is LOCKED."""


def persist_financial_rows(rows, quarter, year, filename, uploaded_by):
    """Persist rows for a given (quarter, year). Replaces any existing rows
    for that period unless an apuração for it is already LOCKED.

    Old batches that previously held rows for this period get their status
    set to SUPERSEDED (preserving audit history without confusion).

    Args:
        rows: list of dicts from parse_financial_xlsx (cliente_mae, operadora,
              produto, nf_valor_liquido, data_recebimento, mes_recebimento,
              tipo_receita, status_recebimento, ...)
        quarter: int 1-4
        year: int
        filename: original upload filename (audit only)
        uploaded_by: User ID

    Returns the new ImportBatch id.

    Raises:
        UploadBlockedError if there's a LOCKED apuração for (quarter, year).
    """
    appraisal = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if appraisal and appraisal.status == AppraisalStatus.LOCKED:
        raise UploadBlockedError(
            f"Apuração de Q{quarter}/{year} já está LOCKED. Re-upload não permitido."
        )

    # Find batches whose rows are about to be deleted, mark them SUPERSEDED
    superseded_batch_ids = {
        bid for (bid,) in db.session.query(FinancialImport.import_batch_id)
        .filter(FinancialImport.quarter == quarter,
                FinancialImport.year == year)
        .distinct()
        .all()
    }
    if superseded_batch_ids:
        ImportBatch.query.filter(
            ImportBatch.id.in_(superseded_batch_ids)
        ).update({"status": "SUPERSEDED"}, synchronize_session=False)

    # Delete existing rows for this period
    FinancialImport.query.filter_by(quarter=quarter, year=year).delete()
    db.session.flush()

    batch = ImportBatch(
        filename=filename,
        uploaded_by=uploaded_by,
        nf_count=len(rows),
        perk_count=0,
        status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()

    for row in rows:
        fi = FinancialImport(
            import_batch_id=batch.id,
            quarter=quarter,
            year=year,
            nf_valor_liquido=row['nf_valor_liquido'],
            nf_mes_recebimento=row['mes_recebimento'],
            cliente_mae=row['cliente_mae'],
            operadora=row['operadora'],
            produto=row['produto'],
            tipo_receita=row.get('tipo_receita'),
            status_recebimento=row['status_recebimento'],
            data_recebimento=row['data_recebimento'],
            match_status='UNMATCHED',
        )
        db.session.add(fi)

    db.session.flush()
    return batch.id
