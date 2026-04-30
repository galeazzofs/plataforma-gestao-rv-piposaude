from datetime import date

# HubSpot property → Policy field mapping
TICKET_COTACAO_MAP = {
    "solicitante_demanda": "ev_email",
    "cotar___segmentacao_pipo": "segment_raw",
    "mrr___receita_mensal": "mrr_projected",
    "closed_date": "closed_date",
    "apolice___beneficio": "benefit_type_raw",
    "cliente___nome_da_empresa": "client_name",
}

DEAL_MAP = {
    "dealstage": "deal_stage",
    "hs_v2_date_entered_8438574": "deploy_date",
}

TICKET_IMPLANT_MAP = {
    "previsao_primeiro_pagamento": "first_payment_prev",
    "mrr_pos_implantacao": "mrr_post_deploy",
}

# Segment mapping: HubSpot text → enum value
# HubSpot sends values like "Startup (1-80)", "P (81-200)", "M (201-500)", "G (501+)"
SEGMENT_MAP = {
    "pp": "PP",
    "p": "P",
    "m": "M",
    "g": "G",
    "startup": "PP",
    "enterprise": "G",
}

BENEFIT_MAP = {
    "saude": "SAUDE",
    "saúde": "SAUDE",
    "odonto": "ODONTO",
    "odontológico": "ODONTO",
    "odontologico": "ODONTO",
    "vida": "VIDA",
    "saúde e odonto": "SAUDE_ODONTO",
    "saude e odonto": "SAUDE_ODONTO",
}


def map_segment(raw):
    if not raw:
        return None
    # Extract prefix before parentheses: "P (81-200)" → "p"
    key = raw.strip().split("(")[0].strip().lower()
    return SEGMENT_MAP.get(key)


def map_benefit_type(raw):
    if not raw:
        return None
    return BENEFIT_MAP.get(raw.strip().lower())


def parse_date(raw):
    if not raw:
        return None
    try:
        if "T" in str(raw):
            return date.fromisoformat(str(raw).split("T")[0])
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def parse_decimal(raw):
    if not raw:
        return None
    try:
        from decimal import Decimal
        return Decimal(str(raw))
    except Exception:
        return None
