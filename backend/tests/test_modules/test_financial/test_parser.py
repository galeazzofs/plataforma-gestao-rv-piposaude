import os
import tempfile
from openpyxl import Workbook
from app.modules.financial.parser import parse_financial_xlsx


def _create_test_xlsx():
    """Create a minimal test XLSX with NFs and Perks tabs."""
    wb = Workbook()

    # NFs tab
    ws_nf = wb.active
    ws_nf.title = "NFs"
    ws_nf.append(["hubspot_ticket_id", "client_name", "nf_valor_liquido", "nf_mes_recebimento"])
    ws_nf.append(["TICKET-1", "Acme Corp", 5000.50, "2026-01"])
    ws_nf.append(["TICKET-2", "Beta Inc", 3000.00, "2026-02"])

    # Perks tab
    ws_perks = wb.create_sheet("Perks")
    ws_perks.append(["client_name", "quarter", "year", "amount"])
    ws_perks.append(["Acme Corp", 1, 2026, 500.00])

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


def test_parse_xlsx_returns_nfs_and_perks():
    path = _create_test_xlsx()
    try:
        result = parse_financial_xlsx(path)
        assert len(result["nfs"]) == 2
        assert result["nfs"][0]["hubspot_ticket_id"] == "TICKET-1"
        assert result["nfs"][0]["nf_valor_liquido"] == 5000.50
        assert len(result["perks"]) == 1
        assert result["perks"][0]["client_name"] == "Acme Corp"
        assert result["perks"][0]["amount"] == 500.00
    finally:
        os.unlink(path)
