"""NF row → Policy matching.

Uses an in-memory dict index for O(1) lookup keyed by
(normalized_cliente, normalized_operadora, benefit_type).
"""
import unicodedata
from collections import defaultdict
from datetime import date


def normalize(s):
    """Lowercase + strip accents + trim spaces. Empty string for None."""
    if not s:
        return ""
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def build_policy_index(policies):
    """Build O(1) lookup index over an iterable of Policy objects.

    Returns: dict[(cliente_norm, operadora_norm, benefit_value)] -> list[Policy]
    Each list is sorted by closed_date DESC so callers can pick the most
    recent policy whose vigência window covers a given NF date.

    Policies missing client or benefit_type are skipped.
    """
    index = defaultdict(list)
    for p in policies:
        if not getattr(p, 'client', None) or not getattr(p, 'benefit_type', None):
            continue
        key = (
            normalize(p.client.name),
            normalize(p.partner_operator or ''),
            p.benefit_type.value,
        )
        index[key].append(p)
    for key in index:
        index[key].sort(key=lambda p: p.closed_date or date.min, reverse=True)
    return dict(index)
