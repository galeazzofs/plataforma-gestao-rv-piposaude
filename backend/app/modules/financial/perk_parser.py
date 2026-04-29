"""Perk/subsidy XLSX parser.

Parses spreadsheets with columns like:
  - Cliente Pipo / Cliente
  - Valor
  - Mês (Competência)
  - Ano

Returns rows ready to be persisted as Perk records.
"""
import unicodedata
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook


class PerkParseError(Exception):
    pass


COLUMN_KEYWORDS = {
    'cliente': lambda h: 'cliente' in h,
    'valor': lambda h: h == 'valor' or ('valor' in h and 'liquido' not in h),
    'mes': lambda h: 'mes' in h or 'competencia' in h,
    'ano': lambda h: h == 'ano',
}


def _normalize_header(s):
    if s is None:
        return ""
    decomp = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomp if unicodedata.category(c) != 'Mn')


def _detect_header_row(ws, scan_limit=20):
    """Return the row index of the header. A real header row has BOTH a
    'cliente' cell and a 'valor' cell — title rows that only mention
    'Cliente' shouldn't be picked up.
    """
    max_cols = min(ws.max_column or 40, 40)
    for r in range(1, scan_limit + 1):
        row_norms = []
        for c in range(1, max_cols + 1):
            v = ws.cell(row=r, column=c).value
            if v is not None:
                row_norms.append(_normalize_header(v))
        has_cliente = any('cliente' in n for n in row_norms)
        has_valor = any(
            n == 'valor' or ('valor' in n and 'liquido' not in n)
            for n in row_norms
        )
        if has_cliente and has_valor:
            return r
    raise PerkParseError(
        "Header row not found — expected a row with both 'Cliente' and "
        "'Valor' columns in the first 20 rows."
    )


def _build_column_map(headers):
    cmap = {}
    for col_idx, raw in enumerate(headers, start=1):
        norm = _normalize_header(raw)
        if not norm:
            continue
        for field, matcher in COLUMN_KEYWORDS.items():
            if field not in cmap and matcher(norm):
                cmap[field] = col_idx
    if 'cliente' not in cmap:
        raise PerkParseError("Column 'Cliente' not found in header row.")
    if 'valor' not in cmap:
        raise PerkParseError("Column 'Valor' not found in header row.")
    return cmap


def _parse_month(raw):
    """Extract month number from values like '01 - Janeiro', '3', 'Março', etc."""
    if raw is None:
        return None
    s = str(raw).strip()
    # "01 - Janeiro" → take first part
    if '-' in s:
        s = s.split('-')[0].strip()
    try:
        return int(s)
    except ValueError:
        return None


def _quarter_of(month):
    return (month - 1) // 3 + 1


def parse_perk_xlsx(filepath, target_quarter, target_year):
    """Parse perk XLSX and return rows for the target quarter/year.

    Returns:
        {
          'rows': [{client_name, amount, month, quarter, year}],
          'stats': {total_lidas, descartadas_periodo, descartadas_vazias, persistidas}
        }
    """
    # read_only=True streams cells (lower memory + safer XML parser surface).
    wb = load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    header_row = _detect_header_row(ws)
    max_cols = min(ws.max_column or 40, 40)
    headers = [ws.cell(row=header_row, column=c).value
               for c in range(1, max_cols + 1)]
    cmap = _build_column_map(headers)

    rows = []
    stats = {
        'total_lidas': 0,
        'descartadas_periodo': 0,
        'descartadas_vazias': 0,
        'persistidas': 0,
    }

    def cell(r, field):
        idx = cmap.get(field)
        return ws.cell(row=r, column=idx).value if idx else None

    for r in range(header_row + 1, (ws.max_row or 0) + 1):
        cliente = cell(r, 'cliente')
        valor_raw = cell(r, 'valor')

        if cliente is None and valor_raw is None:
            continue
        stats['total_lidas'] += 1

        if not cliente or valor_raw is None:
            stats['descartadas_vazias'] += 1
            continue

        # Parse valor — handle negative values in parentheses like (3.500,00)
        try:
            valor_str = str(valor_raw).strip()
            # Remove parentheses and make negative
            negate = False
            if valor_str.startswith('(') and valor_str.endswith(')'):
                valor_str = valor_str[1:-1]
                negate = True
            # Normalize BR number format: 1.234,56 → 1234.56
            if ',' in valor_str:
                valor_str = valor_str.replace('.', '').replace(',', '.')
            amount = abs(Decimal(valor_str))
            if negate or amount == 0:
                pass  # keep positive absolute value for perks
        except (InvalidOperation, ValueError):
            stats['descartadas_vazias'] += 1
            continue

        if amount <= 0:
            stats['descartadas_vazias'] += 1
            continue

        # Parse period
        ano_raw = cell(r, 'ano')
        mes_raw = cell(r, 'mes')

        try:
            year = int(ano_raw) if ano_raw else target_year
        except (ValueError, TypeError):
            year = target_year

        month = _parse_month(mes_raw)
        if month is None or month < 1 or month > 12:
            stats['descartadas_vazias'] += 1
            continue

        q = _quarter_of(month)
        if year != target_year or q != target_quarter:
            stats['descartadas_periodo'] += 1
            continue

        rows.append({
            'client_name': str(cliente).strip(),
            'amount': amount,
            'month': month,
            'quarter': q,
            'year': year,
            '_row': r,
        })
        stats['persistidas'] += 1

    wb.close()
    return {'rows': rows, 'stats': stats}
