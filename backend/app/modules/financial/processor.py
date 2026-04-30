"""Persist parsed financial rows into financial_imports.

The new flow has no PENDING/preview state — once parsed, rows are
committed immediately. Re-uploads delete the period's rows and mark
old batches as SUPERSEDED.
"""
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import FinancialImport, ImportBatch, Appraisal, AppraisalStatus, Perk, Client


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


def _normalize(s):
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def persist_perk_rows(rows, quarter, year, filename, uploaded_by):
    """Persist perk/subsidy rows for a given (quarter, year).

    Replaces existing perks for that period. Matches client_name to Client
    records by normalized name (exact then partial). The caller MUST wrap
    this in try/except and rollback on exception (the route handler does so).

    Returns dict with batch_id, matched, missed, missed_clients, partial_matches.
    """
    from app.models import AuditLog  # local import to avoid circular dependency

    appraisal = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if appraisal and appraisal.status == AppraisalStatus.LOCKED:
        raise UploadBlockedError(
            f"Apuração de Q{quarter}/{year} já está LOCKED. Upload de perks não permitido."
        )

    # Delete existing perks for this period
    Perk.query.filter_by(quarter=quarter, year=year).delete()
    db.session.flush()

    batch = ImportBatch(
        filename=filename,
        uploaded_by=uploaded_by,
        nf_count=0,
        perk_count=len(rows),
        status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()

    # Build normalized client lookup ONCE — avoid O(N*M) re-normalizing
    all_clients = Client.query.all()
    norm_map = {_normalize(c.name): c for c in all_clients}

    matched = 0
    missed = 0
    missed_clients = set()
    partial_matches = []

    for row in rows:
        norm_name = _normalize(row['client_name'])

        # Exact match (single dict lookup)
        client = norm_map.get(norm_name)

        # Partial match fallback — scan precomputed normalized names
        if client is None:
            candidates = [
                c for norm_c, c in norm_map.items()
                if norm_c and (norm_name in norm_c or norm_c in norm_name)
            ]
            if len(candidates) == 1:
                client = candidates[0]
                partial_matches.append({
                    "csv_name": row['client_name'],
                    "matched_to": client.name,
                })

        if client is None:
            missed += 1
            missed_clients.add(row['client_name'])
            continue

        perk = Perk(
            client_id=client.id,
            quarter=quarter,
            year=year,
            amount=Decimal(str(row['amount'])),
            import_batch_id=batch.id,
        )
        db.session.add(perk)
        matched += 1

    # Audit any partial matches so finance can review later
    if partial_matches:
        db.session.add(AuditLog(
            table_name="perks",
            record_id=batch.id,
            action="PARTIAL_MATCH",
            user_id=uploaded_by,
            new_values={
                "quarter": quarter,
                "year": year,
                "matches": partial_matches,
            },
        ))

    db.session.flush()
    return {
        'batch_id': batch.id,
        'matched': matched,
        'missed': missed,
        'missed_clients': sorted(missed_clients),
        'partial_matches': partial_matches,
    }
