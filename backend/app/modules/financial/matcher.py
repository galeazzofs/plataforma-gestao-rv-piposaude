"""NF row → Policy matching by `numero_apolice`.

Strict number-based match: each NF must carry the apolice number in the
spreadsheet, and the policy must have the same number populated from
HubSpot. NFs without a number — or pointing at an apolice we don't have —
fall through as UNMATCHED with a specific reason.
"""
import re
import unicodedata
from collections import defaultdict
from datetime import date


def normalize(s):
    """Lowercase + strip accents + trim spaces. Empty string for None.

    Kept on this module's surface because the calculator still uses it
    for product → benefit mapping ('saude' / 'odonto' / 'vida') and may
    be used by future tooling. Not used by the apolice-number matcher
    itself — apolice numbers are compared after a simpler string strip.
    """
    if not s:
        return ""
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def normalize_apolice_number(s):
    """Trim + uppercase the apolice number for consistent matching.

    HubSpot tends to store these with surrounding whitespace; spreadsheets
    sometimes pad with a leading apostrophe or quotes. We strip both ends
    and uppercase so 'AB-123 ' and 'ab-123' index the same key.

    Excel numeric cells read as text produce a trailing '.0' (e.g. 9797 →
    '9797.0'). Strip it so NF numbers match policy numbers.
    """
    if s is None:
        return ""
    result = str(s).strip().strip("'\"")
    # Strip Excel float suffix: "9797.0" → "9797" (only when purely numeric)
    if result.endswith(".0") and result[:-2].isdigit():
        result = result[:-2]
    return result.upper()


# Regex: common prefixes like "Apólice(s):", "Apolice:", "Nº:", etc.
_PREFIX_RE = re.compile(
    r"^(?:ap[oó]lices?\s*(?:\(s\))?\s*:?\s*|n[ºo°]?\s*:?\s*)",
    re.IGNORECASE,
)
# Regex: split on commas, semicolons, pipes, newlines, or the word "e"/"and"
# as a standalone separator (word boundaries prevent splitting "verde").
_SPLIT_RE = re.compile(
    r"[,;\|\n]+|\s+\be\b\s+|\s+\band\b\s+",
    re.IGNORECASE,
)


def parse_apolice_numbers(raw):
    """Extract individual apolice numbers from a possibly multi-valued string.

    HubSpot's numero_apolice field is free-text and operators sometimes enter
    multiple numbers in one field with unpredictable formatting, e.g.:

        "Apólice(s): 798140003, 798140143 e 798140151"
        "798140003; 798140143; 798140151"
        "798140003 e 798140143"
        "AP-100, AP-200"

    Returns a list of normalized individual apolice numbers (deduplicated,
    order-preserved). Returns empty list for None/blank input.
    """
    if not raw:
        return []
    text = str(raw).strip()
    # Strip known prefixes
    text = _PREFIX_RE.sub("", text).strip()
    # Split on separators
    parts = _SPLIT_RE.split(text)
    # Second pass: split on "/" when both sides are purely numeric
    # (e.g. "1034957/1034958" → two numbers, but "277.615/2024" stays one)
    expanded = []
    for part in parts:
        stripped = part.strip()
        if "/" in stripped:
            pieces = stripped.split("/")
            if all(p.strip().isdigit() for p in pieces if p.strip()):
                expanded.extend(pieces)
            else:
                expanded.append(stripped)
        else:
            expanded.append(stripped)
    seen = set()
    result = []
    for part in expanded:
        normalized = normalize_apolice_number(part)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def fallback_match_key(client_name_normalized, benefit, operadora):
    """Composite key for the (Cliente Mãe, Benefício, Operadora) fallback.

    Used to match an NF to a policy when the policy's numero_apolice is
    missing or corrupted in the HubSpot sync (e.g. stored as scientific
    notation '1,10E+16', a free-text note, or blank) so the apolice-number
    match can never land.

    `client_name_normalized` must ALREADY be normalized with
    normalize_client_name (so the NF side and the policy side — which stores
    Client.name_normalized — produce identical keys). `benefit` is the
    canonical SAUDE/ODONTO/VIDA. `operadora` is normalized here, accent/case/
    space-insensitive, on both sides.
    """
    return (
        (client_name_normalized or "").strip(),
        (benefit or "").strip().upper(),
        normalize(operadora or ""),
    )


def build_policy_index(policies):
    """Build O(1) lookup index by apolice number.

    Returns: dict[apolice_number_normalized] -> list[Policy]
    Each list is sorted by closed_date DESC so callers can pick the most
    recent policy whose vigência window covers a given NF date.

    Handles multi-valued numero_apolice fields — a single Policy with
    "798140003, 798140143 e 798140151" gets indexed under all three keys.

    Policies missing numero_apolice are skipped (cannot be matched by this
    strategy). The list-of-Policies value (rather than single Policy) is
    kept to match the legacy interface; in practice apolice numbers are
    unique so each list has size 1.
    """
    index = defaultdict(list)
    for p in policies:
        numbers = parse_apolice_numbers(getattr(p, 'numero_apolice', None))
        for number in numbers:
            index[number].append(p)
    for key in index:
        index[key].sort(key=lambda p: p.closed_date or date.min, reverse=True)
    return dict(index)
