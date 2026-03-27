from decimal import Decimal, InvalidOperation
import re
from app.models import Policy, FinancialImport


def validate_nf_rows(rows):
    """Validate NF rows against database.

    Returns (valid_rows, errors).
    """
    valid = []
    errors = []

    for row in rows:
        row_num = row.get("_row", "?")
        ticket_id = row.get("hubspot_ticket_id")
        valor = row.get("nf_valor_liquido")
        mes = row.get("nf_mes_recebimento")

        # Required fields
        if not ticket_id:
            errors.append({"row": row_num, "message": "hubspot_ticket_id is required"})
            continue

        # Ticket exists?
        policy = Policy.query.filter_by(hubspot_ticket_id=str(ticket_id)).first()
        if policy is None:
            errors.append({"row": row_num, "message": f"Ticket '{ticket_id}' not found in database"})
            continue

        # Valor is numeric?
        try:
            valor = Decimal(str(valor))
            if valor <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError, TypeError):
            errors.append({"row": row_num, "message": f"Invalid nf_valor_liquido: {valor}"})
            continue

        # Mes format
        if not mes or not re.match(r"^\d{4}-\d{2}$", str(mes)):
            errors.append({"row": row_num, "message": f"Invalid nf_mes_recebimento format: {mes}. Expected YYYY-MM"})
            continue

        # Duplicate check
        existing = FinancialImport.query.filter_by(
            policy_id=policy.id, nf_mes_recebimento=str(mes)
        ).first()
        if existing:
            errors.append({"row": row_num, "message": f"NF already exists for ticket {ticket_id} month {mes}"})
            continue

        valid.append({
            "policy_id": policy.id,
            "hubspot_ticket_id": str(ticket_id),
            "nf_valor_liquido": valor,
            "nf_mes_recebimento": str(mes),
            "_row": row_num,
        })

    return valid, errors


def validate_perk_rows(rows):
    """Validate perk rows. Returns (valid_rows, errors)."""
    valid = []
    errors = []

    for row in rows:
        row_num = row.get("_row", "?")
        client_name = row.get("client_name")
        quarter = row.get("quarter")
        year = row.get("year")
        amount = row.get("amount")

        if not client_name:
            errors.append({"row": row_num, "message": "client_name is required"})
            continue

        try:
            quarter = int(quarter)
            year = int(year)
            amount = Decimal(str(amount))
            if quarter < 1 or quarter > 4:
                raise ValueError("quarter must be 1-4")
            if amount < 0:
                raise ValueError("amount must be >= 0")
        except (TypeError, ValueError) as e:
            errors.append({"row": row_num, "message": f"Invalid data: {e}"})
            continue

        valid.append({
            "client_name": str(client_name),
            "quarter": quarter,
            "year": year,
            "amount": amount,
            "_row": row_num,
        })

    return valid, errors
