"""NF row → Policy matching by `numero_apolice`.

Strict number-based match: each NF must carry the apolice number in the
spreadsheet, and the policy must have the same number populated from
HubSpot. NFs without a number — or pointing at an apolice we don't have —
fall through as UNMATCHED with a specific reason.
"""
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
    """
    if s is None:
        return ""
    return str(s).strip().strip("'\"").upper()


def build_policy_index(policies):
    """Build O(1) lookup index by apolice number.

    Returns: dict[apolice_number_normalized] -> list[Policy]
    Each list is sorted by closed_date DESC so callers can pick the most
    recent policy whose vigência window covers a given NF date.

    Policies missing numero_apolice are skipped (cannot be matched by this
    strategy). The list-of-Policies value (rather than single Policy) is
    kept to match the legacy interface; in practice apolice numbers are
    unique so each list has size 1.
    """
    index = defaultdict(list)
    for p in policies:
        number = normalize_apolice_number(getattr(p, 'numero_apolice', None))
        if not number:
            continue
        index[number].append(p)
    for key in index:
        index[key].sort(key=lambda p: p.closed_date or date.min, reverse=True)
    return dict(index)
