# Legacy Policies Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill `initial_installments_paid` and `first_payment_real` on existing policies from a legacy CSV, and auto-detect vigência start for new policies on their first apuração match.

**Architecture:** A standalone one-time migration script (`backend/migrate_legacy_policies.py`) reads the CSV, normalizes names, and updates matching Policy records. A two-line change in the apuração calculator auto-sets `first_payment_real` when a policy has none and a NF matches it for the first time.

**Tech Stack:** Python 3, Flask-SQLAlchemy, `dateutil.relativedelta`, `csv` stdlib, `unicodedata` stdlib

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/tests/test_migrate_legacy.py` | Tests for migration script |
| Create | `backend/migrate_legacy_policies.py` | One-time migration script |
| Modify | `backend/tests/test_modules/test_commissions/test_calculator_v2.py` | Test for auto-detect behavior |
| Modify | `backend/app/modules/commissions/calculator.py` | Auto-set `first_payment_real` on first NF match |

---

### Task 1: Failing tests for migration script

**Files:**
- Create: `backend/tests/test_migrate_legacy.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_migrate_legacy.py` with this content:

```python
"""Tests for migrate_legacy_policies.py"""
import pytest
from datetime import date

from app.extensions import db
from app.models import Client, Policy, BenefitType, Segment


CSV_WITH_DATE = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,25/04/2026,11\n"
)
CSV_NO_DATE = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,,3\n"
)
CSV_ZERO_MESES = (
    "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
    "Celcoin,Karina Gomes,Sulamérica,Saúde,,0\n"
)


def _make_csv(tmp_path, content):
    f = tmp_path / "test.csv"
    f.write_text(content, encoding="utf-8")
    return str(f)


@pytest.fixture
def policy(db_session):
    client = Client.find_or_create("Celcoin")
    db.session.flush()
    p = Policy(
        hubspot_ticket_id="T-CELCOIN",
        client_id=client.id,
        benefit_type=BenefitType.SAUDE,
        partner_operator="Sulamérica",
        segment=Segment.M,
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_updates_policy_with_date(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_WITH_DATE), dry_run=False)
    assert policy.initial_installments_paid == 11
    assert policy.first_payment_real == date(2026, 4, 25)


def test_infers_date_from_last_appraisal(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_NO_DATE), dry_run=False)
    # _LAST_APPRAISAL=Dec 2025, Meses_Pagos=3 → Dec - 2 months = Oct 2025
    assert policy.initial_installments_paid == 3
    assert policy.first_payment_real == date(2025, 10, 1)


def test_skips_zero_meses_no_date(policy, tmp_path):
    from migrate_legacy_policies import run
    _, skipped, _ = run(_make_csv(tmp_path, CSV_ZERO_MESES), dry_run=False)
    assert skipped == 1
    assert policy.initial_installments_paid == 0
    assert policy.first_payment_real is None


def test_dry_run_does_not_write(policy, tmp_path):
    from migrate_legacy_policies import run
    run(_make_csv(tmp_path, CSV_WITH_DATE), dry_run=True)
    assert policy.initial_installments_paid == 0
    assert policy.first_payment_real is None


def test_unknown_client_returns_miss(tmp_path):
    from migrate_legacy_policies import run
    csv = (
        "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
        "ClienteInexistente,Alguem,Bradesco,Saúde,25/04/2026,5\n"
    )
    updated, _, missed = run(_make_csv(tmp_path, csv), dry_run=False)
    assert updated == 0
    assert missed == 1


def test_skips_locked_policy(tmp_path, db_session):
    from migrate_legacy_policies import run
    client = Client.find_or_create("LockedCo")
    db.session.flush()
    p = Policy(
        hubspot_ticket_id="T-LOCKED",
        client_id=client.id,
        benefit_type=BenefitType.SAUDE,
        partner_operator="Bradesco",
        segment=Segment.M,
        is_locked=True,
    )
    db.session.add(p)
    db.session.flush()

    csv = (
        "Cliente,Executivo_Vendas,Operadora,Produto,Inicio_Vigencia,Meses_Pagos\n"
        "LockedCo,Alguem,Bradesco,Saúde,25/04/2026,5\n"
    )
    updated, skipped, _ = run(_make_csv(tmp_path, csv), dry_run=False)
    assert updated == 0
    assert skipped == 1
    assert p.initial_installments_paid == 0  # unchanged
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && pytest tests/test_migrate_legacy.py -v
```

Expected: 6 failures with `ModuleNotFoundError: No module named 'migrate_legacy_policies'`

---

### Task 2: Implement migration script

**Files:**
- Create: `backend/migrate_legacy_policies.py`

- [ ] **Step 1: Create the script**

Create `backend/migrate_legacy_policies.py` with this content:

```python
"""One-time migration: seed initial_installments_paid and first_payment_real
from apolices_legado.csv into existing Policy records."""
import argparse
import csv
import unicodedata
from datetime import date

from dateutil.relativedelta import relativedelta

from app import create_app
from app.extensions import db
from app.models import Client, Policy, BenefitType

# Reference month: the last apuração before the platform launched
_LAST_APPRAISAL = date(2025, 12, 1)

_BENEFIT_MAP = {
    'saude': BenefitType.SAUDE,
    'odonto': BenefitType.ODONTO,
    'vida': BenefitType.VIDA,
}


def _normalize(s):
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def _parse_date(s):
    day, month, year = s.strip().split('/')
    return date(int(year), int(month), int(day))


def _infer_first_payment(meses_pagos):
    """Work backwards from Dec 2025: month 1 = Dec, month 2 = Nov, etc."""
    return _LAST_APPRAISAL - relativedelta(months=meses_pagos - 1)


def _map_benefit(produto):
    norm = _normalize(produto)
    for key, val in _BENEFIT_MAP.items():
        if key in norm:
            return val
    return None


def run(csv_path, dry_run=False):
    """Process CSV and update matching policies. Returns (updated, skipped, missed)."""
    updated = skipped = missed = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        cliente   = (row.get('Cliente')         or '').strip()
        operadora = (row.get('Operadora')        or '').strip()
        produto   = (row.get('Produto')          or '').strip()
        inicio_raw = (row.get('Inicio_Vigencia') or '').strip()
        meses_pagos = int((row.get('Meses_Pagos') or '0').strip() or '0')

        if meses_pagos == 0 and not inicio_raw:
            print(f'[SKIP]  {cliente} | {operadora} | {produto} → Meses_Pagos=0, sem data')
            skipped += 1
            continue

        first_payment = _parse_date(inicio_raw) if inicio_raw else _infer_first_payment(meses_pagos)

        benefit = _map_benefit(produto)
        if benefit is None:
            print(f'[MISS]  {cliente} | {operadora} | {produto} → produto não mapeado')
            missed += 1
            continue

        client = Client.query.filter_by(name_normalized=_normalize(cliente)).first()
        if client is None:
            print(f'[MISS]  {cliente} → cliente não encontrado no banco')
            missed += 1
            continue

        norm_op = _normalize(operadora)
        policy = None
        for p in Policy.query.filter_by(client_id=client.id, benefit_type=benefit).all():
            if not norm_op or norm_op in _normalize(p.partner_operator or ''):
                policy = p
                break

        if policy is None:
            print(f'[MISS]  {cliente} | {operadora} | {produto} → apólice não encontrada')
            missed += 1
            continue

        if policy.is_locked:
            print(f'[SKIP]  {cliente} | {operadora} | {produto} → policy is_locked=True')
            skipped += 1
            continue

        tag = '[INFER]' if not inicio_raw else '[MATCH]'
        print(f'{tag}  {cliente} | {operadora} | {produto} → '
              f'initial_installments_paid={meses_pagos}, first_payment_real={first_payment}')

        if not dry_run:
            policy.initial_installments_paid = meses_pagos
            policy.first_payment_real = first_payment

        updated += 1

    print(f'---\nSummary: {updated} updated, {skipped} skipped, {missed} not found')
    return updated, skipped, missed


def main():
    parser = argparse.ArgumentParser(description='Seed legacy policy baselines from CSV.')
    parser.add_argument('--dry-run', action='store_true', help='Print without saving.')
    parser.add_argument('--csv', default='apolices_legado.csv', help='Path to CSV file.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(args.csv, dry_run=args.dry_run)
        if not args.dry_run:
            db.session.commit()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
cd backend && pytest tests/test_migrate_legacy.py -v
```

Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
cd backend && git add migrate_legacy_policies.py tests/test_migrate_legacy.py
git commit -m "feat: add one-time migration script for legacy policy baselines"
```

---

### Task 3: Failing test for calculator auto-detect

**Files:**
- Modify: `backend/tests/test_modules/test_commissions/test_calculator_v2.py`

- [ ] **Step 1: Append the failing test to the file**

Open `backend/tests/test_modules/test_commissions/test_calculator_v2.py` and append this function at the end:

```python
def test_auto_sets_first_payment_real_when_none(db_session):
    """Policy with no first_payment_real: first matched NF sets it and counts as month 1."""
    ev = User(email='ev@autodetect', name='EV AutoDetect', role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    client = Client.find_or_create('AutoDetect Co')
    db.session.flush()

    policy = Policy(
        hubspot_ticket_id='T-AUTODETECT',
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        partner_operator='TestOp',
        closed_date=date(2025, 11, 1),  # Q4/2025 gongo
        first_payment_real=None,        # ← no vigência set yet
        installments_paid=0,
        initial_installments_paid=0,
    )
    db.session.add(policy)
    db.session.flush()

    db.session.add(EvQuarterAchievement(
        ev_id=ev.id,
        quarter=4,
        year=2025,
        achievement_pct=Decimal('0.75'),
    ))

    batch = ImportBatch(filename='auto.xlsx', quarter=1, year=2026, imported_by=ev.id)
    db.session.add(batch)
    db.session.flush()

    db.session.add(FinancialImport(
        batch_id=batch.id,
        cliente_mae='AutoDetect Co',
        operadora='TestOp',
        produto='Saude',
        data_recebimento=date(2026, 1, 15),
        nf_valor_liquido=Decimal('1000.00'),
        quarter=1,
        year=2026,
        status='RECEBIDO',
    ))
    db.session.flush()

    from app.modules.commissions.calculator import run_quarterly_appraisal
    run_quarterly_appraisal(quarter=1, year=2026)

    db.session.refresh(policy)
    assert policy.first_payment_real == date(2026, 1, 15)
    assert policy.installments_paid == 1
    nf = db.session.query(FinancialImport).filter_by(cliente_mae='AutoDetect Co').first()
    assert nf.match_status == 'MATCHED'
```

Also add `ImportBatch` to the existing imports at the top of the file (line 8) if not already present:

```python
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement, Segment,
    BenefitType, FinancialImport, ImportBatch, Commission, CommissionPctTable,
)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend && pytest tests/test_modules/test_commissions/test_calculator_v2.py::test_auto_sets_first_payment_real_when_none -v
```

Expected: FAIL — `assert policy.first_payment_real == date(2026, 1, 15)` fails because `policy.first_payment_real` is still `None`

---

### Task 4: Implement calculator auto-detect

**Files:**
- Modify: `backend/app/modules/commissions/calculator.py:170-171`

- [ ] **Step 1: Edit the vigência window check**

In `backend/app/modules/commissions/calculator.py`, lines 170-171 currently read:

```python
            if not policy.first_payment_real:
                continue
```

Replace with:

```python
            if not policy.first_payment_real:
                if nf.data_recebimento is None:
                    continue
                policy.first_payment_real = nf.data_recebimento
```

The full surrounding context after the edit (lines 168-183):

```python
        matched = None
        for policy in candidates:
            if not policy.first_payment_real:
                if nf.data_recebimento is None:
                    continue
                policy.first_payment_real = nf.data_recebimento
            window_end = policy.first_payment_real + relativedelta(
                months=12 - (policy.initial_installments_paid or 0)
            )
            if nf.data_recebimento is None:
                continue
            if nf.data_recebimento < policy.first_payment_real:
                continue
            if nf.data_recebimento > window_end:
                continue
            matched = policy
            break
```

- [ ] **Step 2: Run the new test to confirm it passes**

```bash
cd backend && pytest tests/test_modules/test_commissions/test_calculator_v2.py::test_auto_sets_first_payment_real_when_none -v
```

Expected: PASS

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
cd backend && pytest tests/ -v
```

Expected: all tests pass (including existing calculator tests)

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/modules/commissions/calculator.py tests/test_modules/test_commissions/test_calculator_v2.py
git commit -m "feat: auto-set first_payment_real on first NF match for policies without vigência"
```

---

## Running the migration (production)

Once both commits are deployed:

```bash
cd backend
# 1. Preview what would change:
python migrate_legacy_policies.py --dry-run --csv /path/to/apolices_legado.csv

# 2. Review the [MISS] lines and resolve manually if needed

# 3. Run for real:
python migrate_legacy_policies.py --csv /path/to/apolices_legado.csv
```
