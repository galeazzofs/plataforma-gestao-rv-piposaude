from decimal import Decimal
from app.extensions import db
from app.models import (
    FinancialImport, ImportBatch, Perk, Policy, Client, CommissionStatus,
)
from app.models.client import normalize_client_name


def process_financial_import(batch_id, valid_nfs, valid_perks):
    """Process validated financial data: insert NFs, perks, update policies.

    Args:
        batch_id: UUID of the ImportBatch
        valid_nfs: List of validated NF dicts
        valid_perks: List of validated perk dicts

    Returns summary dict.
    """
    nfs_created = 0
    perks_created = 0

    # Process NFs
    for nf in valid_nfs:
        mes = nf["nf_mes_recebimento"]
        month = int(mes.split("-")[1])
        year_val = int(mes.split("-")[0])
        quarter = (month - 1) // 3 + 1

        fi = FinancialImport(
            policy_id=nf["policy_id"],
            nf_valor_liquido=nf["nf_valor_liquido"],
            nf_mes_recebimento=mes,
            quarter=quarter,
            year=year_val,
            import_batch_id=batch_id,
        )
        db.session.add(fi)
        nfs_created += 1

        # Update policy
        policy = Policy.query.get(nf["policy_id"])
        if policy:
            policy.installments_paid = (policy.installments_paid or 0) + 1

            # First payment?
            if policy.first_payment_real is None:
                from datetime import date
                policy.first_payment_real = date(year_val, month, 1)

            # Status transition
            if policy.commission_status == CommissionStatus.PROJECTED:
                policy.commission_status = CommissionStatus.IN_PAYMENT

            if policy.installments_paid >= 12:
                policy.commission_status = CommissionStatus.SETTLED

    # Process Perks
    for perk_data in valid_perks:
        client = Client.query.filter_by(
            name_normalized=normalize_client_name(perk_data["client_name"])
        ).first()

        if client:
            perk = Perk(
                client_id=client.id,
                quarter=perk_data["quarter"],
                year=perk_data["year"],
                amount=perk_data["amount"],
                import_batch_id=batch_id,
            )
            db.session.add(perk)
            perks_created += 1

    db.session.flush()

    # Update batch
    batch = ImportBatch.query.get(batch_id)
    if batch:
        batch.nf_count = nfs_created
        batch.perk_count = perks_created
        batch.status = "CONFIRMED"

    return {
        "nfs_created": nfs_created,
        "perks_created": perks_created,
    }
