from openpyxl import load_workbook


REQUIRED_NF_COLUMNS = ["hubspot_ticket_id", "client_name", "nf_valor_liquido", "nf_mes_recebimento"]
REQUIRED_PERK_COLUMNS = ["client_name", "quarter", "year", "amount"]


class ParseError(Exception):
    pass


def parse_financial_xlsx(filepath):
    """Parse financial XLSX file with NFs and Perks tabs.

    Returns: {"nfs": [...], "perks": [...]}
    """
    wb = load_workbook(filepath, read_only=True, data_only=True)

    nfs = _parse_sheet(wb, "NFs", REQUIRED_NF_COLUMNS)
    perks = _parse_sheet(wb, "Perks", REQUIRED_PERK_COLUMNS)

    wb.close()
    return {"nfs": nfs, "perks": perks}


def _parse_sheet(wb, sheet_name, required_columns):
    """Parse a single sheet into list of dicts."""
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    rows = list(ws.rows)
    if len(rows) < 2:
        return []

    # Header row
    headers = [cell.value.strip().lower() if cell.value else "" for cell in rows[0]]

    # Validate required columns
    for col in required_columns:
        if col not in headers:
            raise ParseError(f"Missing required column '{col}' in sheet '{sheet_name}'")

    # Parse data rows
    records = []
    for row_idx, row in enumerate(rows[1:], start=2):
        values = [cell.value for cell in row]
        record = dict(zip(headers, values))

        # Skip completely empty rows
        if all(v is None for v in values):
            continue

        record["_row"] = row_idx
        records.append(record)

    return records
