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


def _locked_months(year):
    """Months (1-12) of `year` whose Appraisal is already LOCKED — their NFs
    and perks must be preserved across a re-upload."""
    return {
        m for (m,) in db.session.query(Appraisal.month)
        .filter(Appraisal.year == year, Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }


def persist_financial_rows(rows, year, filename, uploaded_by):
    """Persist financial rows for a year, tagging each NF with its OWN
    competência month (from mes_recebimento, 'YYYY-MM'). A single upload of a
    multi-month export therefore populates every month.

    Re-uploading a year refreshes its OPEN months and PRESERVES months whose
    apuração is already LOCKED: those rows stay untouched and any file rows that
    land on a locked month are skipped (counted in skipped_locked).

    Args:
        rows: list of dicts from parse_financial_xlsx.
        year: int — the competência year being (re)loaded.
        filename: original upload filename (audit only).
        uploaded_by: User ID.

    Returns {batch_id, persisted, skipped_locked}.
    """
    locked = _locked_months(year)
    # Replace only the (non-locked) months actually present in this file, so
    # both an incremental upload (one month) and a full re-upload work without
    # wiping months the file doesn't carry.
    months_in_file = {int(r['mes_recebimento'][5:7]) for r in rows}
    months_to_replace = months_in_file - locked

    if months_to_replace:
        sup_q = db.session.query(FinancialImport.import_batch_id).filter(
            FinancialImport.year == year,
            FinancialImport.month.in_(months_to_replace),
        )
        superseded_batch_ids = {bid for (bid,) in sup_q.distinct().all()}
        if superseded_batch_ids:
            ImportBatch.query.filter(
                ImportBatch.id.in_(superseded_batch_ids)
            ).update({"status": "SUPERSEDED"}, synchronize_session=False)
        FinancialImport.query.filter(
            FinancialImport.year == year,
            FinancialImport.month.in_(months_to_replace),
        ).delete(synchronize_session=False)
        db.session.flush()

    batch = ImportBatch(
        filename=filename,
        uploaded_by=uploaded_by,
        nf_count=0,
        perk_count=0,
        status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()

    persisted = 0
    skipped_locked = 0
    for row in rows:
        mes = row['mes_recebimento']  # 'YYYY-MM'
        month = int(mes[5:7])
        if month in locked:
            skipped_locked += 1
            continue
        db.session.add(FinancialImport(
            import_batch_id=batch.id,
            month=month,
            year=year,
            nf_valor_liquido=row['nf_valor_liquido'],
            nf_mes_recebimento=mes,
            cliente_mae=row['cliente_mae'],
            operadora=row['operadora'],
            produto=row['produto'],
            numero_apolice=row.get('numero_apolice'),
            tipo_receita=row.get('tipo_receita'),
            status_recebimento=row['status_recebimento'],
            data_recebimento=row['data_recebimento'],
            match_status='UNMATCHED',
        ))
        persisted += 1

    batch.nf_count = persisted
    db.session.flush()
    return {"batch_id": batch.id, "persisted": persisted, "skipped_locked": skipped_locked}


def _normalize(s):
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def persist_perk_rows(rows, year, filename, uploaded_by):
    """Persist perk rows for a year, tagging each by its OWN competência month
    (from the sheet's 'Mês' column). Refreshes OPEN months and PRESERVES LOCKED
    months (their perks stay; file rows on locked months are skipped).

    Matches client_name to Client records by normalized name (exact then
    partial). The caller MUST wrap this in try/except and rollback on exception
    (the route handler does so).

    Returns dict with batch_id, matched, missed, skipped_locked, missed_clients,
    partial_matches.
    """
    from app.models import AuditLog  # local import to avoid circular dependency

    locked = _locked_months(year)
    # Replace only the (non-locked) months present in this file.
    months_in_file = {r['month'] for r in rows}
    months_to_replace = months_in_file - locked
    if months_to_replace:
        Perk.query.filter(
            Perk.year == year,
            Perk.month.in_(months_to_replace),
        ).delete(synchronize_session=False)
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
    skipped_locked = 0
    matched_client_ids = set()
    missed_clients = set()
    partial_matches = []

    for row in rows:
        month = row['month']
        if month in locked:
            skipped_locked += 1
            continue
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
            month=month,
            year=year,
            amount=Decimal(str(row['amount'])),
            import_batch_id=batch.id,
        )
        db.session.add(perk)
        matched += 1
        matched_client_ids.add(client.id)

    # Audit any partial matches so finance can review later
    if partial_matches:
        db.session.add(AuditLog(
            table_name="perks",
            record_id=batch.id,
            action="PARTIAL_MATCH",
            user_id=uploaded_by,
            new_values={
                "year": year,
                "matches": partial_matches,
            },
        ))

    batch.perk_count = matched
    db.session.flush()
    return {
        'batch_id': batch.id,
        'matched': matched,
        'matched_clients': len(matched_client_ids),
        'missed': missed,
        'skipped_locked': skipped_locked,
        'missed_clients': sorted(missed_clients),
        'partial_matches': partial_matches,
    }
