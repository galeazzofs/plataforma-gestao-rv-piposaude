# Fix 5 Critical Spec Violations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 critical discrepancies between the spec v2.2 and the current app — commission formula, perks deduction, status transitions, HubSpot sync of ticket implantação, and projection layer.

**Architecture:** All fixes are in the Python backend. Tasks 1-2 rewrite `calculator.py` to aggregate NFs at the empresa level, subtract perks, and auto-transition `commission_status`. Task 3 extends the HubSpot sync to navigate deal → ticket implantação. Task 4 rewrites the commission summary/projection endpoints to compute live estimates from Policy data using the middle-tier commission %.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, pytest, unittest.mock

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/modules/commissions/status.py` | **Create** | commission_status transition logic + first_payment_real inference |
| `backend/app/modules/commissions/calculator.py` | **Modify** | Rewrite apuração to aggregate by empresa, subtract perks, call status helper |
| `backend/app/modules/commissions/projection.py` | **Create** | Live projection helpers (estimated balance, monthly projection) |
| `backend/app/modules/hubspot_sync/sync.py` | **Modify** | Add ticket implantação fetch via deal → tickets navigation |
| `backend/app/api/v1/commissions.py` | **Modify** | Rewrite summary + projection endpoints to use new projection helpers |
| `backend/tests/test_modules/__init__.py` | **Create** | Package init |
| `backend/tests/test_modules/test_status.py` | **Create** | Tests for commission_status transitions |
| `backend/tests/test_modules/test_calculator.py` | **Create** | Tests for per-empresa formula + perks |
| `backend/tests/test_modules/test_projection.py` | **Create** | Tests for projection helpers |
| `backend/tests/test_modules/test_sync_implant.py` | **Create** | Tests for ticket implantação sync |

---

### Task 1: commission_status auto-transitions

**Files:**
- Create: `backend/app/modules/commissions/status.py`
- Create: `backend/tests/test_modules/__init__.py`
- Create: `backend/tests/test_modules/test_status.py`

- [ ] **Step 1: Create test package init**

```python
# backend/tests/test_modules/__init__.py
# (empty file)
```

- [ ] **Step 2: Write failing tests for status transitions**

```python
# backend/tests/test_modules/test_status.py
from datetime import date
from decimal import Decimal

from app.models import Policy, CommissionStatus, Segment, BenefitType, Client
from app.modules.commissions.status import update_policy_statuses
from app.extensions import db


def _make_client(session, name="Acme Corp"):
    c = Client(name=name, name_normalized=name.strip().lower())
    session.add(c)
    session.flush()
    return c


def _make_policy(session, client, **overrides):
    defaults = dict(
        hubspot_ticket_id=f"T-{id(overrides)}",
        client_id=client.id,
        segment=Segment.P,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("5000"),
        commission_status=CommissionStatus.PROJECTED,
        closed_date=date(2026, 1, 15),
        installments_paid=0,
        first_payment_real=None,
    )
    defaults.update(overrides)
    p = Policy(**defaults)
    session.add(p)
    session.flush()
    return p


class TestUpdatePolicyStatuses:
    """Spec §3.3 — lifecycle: PROJECTED → IN_PAYMENT → SETTLED."""

    def test_projected_stays_when_no_payments(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(db_session, client, installments_paid=0)

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.PROJECTED

    def test_transitions_to_in_payment_when_first_payment_real_set(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            installments_paid=1,
            first_payment_real=date(2026, 4, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.IN_PAYMENT

    def test_transitions_to_settled_at_12_installments(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            installments_paid=12,
            first_payment_real=date(2026, 1, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.SETTLED

    def test_does_not_touch_cancelled(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(
            db_session, client,
            commission_status=CommissionStatus.CANCELLED,
            installments_paid=5,
            first_payment_real=date(2026, 1, 1),
        )

        update_policy_statuses([p])

        assert p.commission_status == CommissionStatus.CANCELLED

    def test_infers_first_payment_real_from_nf_dates(self, db_session):
        client = _make_client(db_session)
        p = _make_policy(db_session, client, installments_paid=1)

        nf_dates = {p.id: date(2026, 3, 15)}
        update_policy_statuses([p], earliest_nf_dates=nf_dates)

        assert p.first_payment_real == date(2026, 3, 15)
        assert p.commission_status == CommissionStatus.IN_PAYMENT
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_modules/test_status.py -v`
Expected: ImportError — `cannot import name 'update_policy_statuses'`

- [ ] **Step 4: Implement status transition module**

```python
# backend/app/modules/commissions/status.py
"""commission_status auto-transitions per spec §3.3.

PROJECTED  → first payment received → IN_PAYMENT
IN_PAYMENT → 12 installments paid   → SETTLED
CANCELLED  → never touched
"""
from app.models import CommissionStatus


def update_policy_statuses(policies, earliest_nf_dates=None):
    """Update commission_status for each policy based on payment state.

    Args:
        policies: iterable of Policy objects (will be mutated in-place).
        earliest_nf_dates: optional dict {policy_id: date} — earliest
            data_recebimento among matched NFs. Used to infer
            first_payment_real when it is None.
    """
    earliest_nf_dates = earliest_nf_dates or {}

    for policy in policies:
        if policy.commission_status == CommissionStatus.CANCELLED:
            continue

        # Infer first_payment_real from matched NF dates if missing
        if policy.first_payment_real is None and policy.id in earliest_nf_dates:
            policy.first_payment_real = earliest_nf_dates[policy.id]

        # Transition logic
        if policy.installments_paid >= 12:
            policy.commission_status = CommissionStatus.SETTLED
        elif policy.first_payment_real is not None and policy.installments_paid > 0:
            policy.commission_status = CommissionStatus.IN_PAYMENT
        # else: stays PROJECTED
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_modules/test_status.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/commissions/status.py backend/tests/test_modules/__init__.py backend/tests/test_modules/test_status.py
git commit -m "feat: add commission_status auto-transition logic (spec §3.3)"
```

---

### Task 2: Rewrite calculator — per-empresa formula with perks deduction

**Files:**
- Modify: `backend/app/modules/commissions/calculator.py`
- Create: `backend/tests/test_modules/test_calculator.py`

- [ ] **Step 1: Write failing tests for the new formula**

```python
# backend/tests/test_modules/test_calculator.py
from datetime import date
from decimal import Decimal

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType,
    CommissionStatus, Commission, FinancialImport, ImportBatch,
    Perk, EvQuarterAchievement, CommissionPctTable,
)
from app.modules.commissions.calculator import run_quarterly_appraisal
from app.extensions import db


def _seed_pct_table(session):
    """Seed commission % table v1 — P segment, 3 tiers."""
    rows = [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "9.9999", "0.10"),
    ]
    for seg, amin, amax, pct in rows:
        session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))
    session.flush()


def _base_setup(session):
    """Create EV, client, policy, achievement, NFs for Q1/2026."""
    ev = User(email="ev1@piposaude.com", name="EV Um", role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()

    client = Client(name="Acme Corp", name_normalized="acme corp", ev_id=ev.id)
    session.add(client)
    session.flush()

    policy = Policy(
        hubspot_ticket_id="TICKET-100",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.PROJECTED,
        first_payment_real=date(2026, 2, 1),
        installments_paid=0,
        initial_installments_paid=0,
        partner_operator="Bradesco",
    )
    session.add(policy)
    session.flush()

    # Achievement for Q1/2026: 80% → falls in 50-99.9% tier → 8%
    ach = EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2026,
        total_mrr=Decimal("40000"), mrr_target=Decimal("50000"),
        achievement_pct=Decimal("0.8000"),
    )
    session.add(ach)
    session.flush()

    _seed_pct_table(session)

    batch = ImportBatch(filename="test.xlsx", uploaded_by=ev.id, nf_count=2, status="CONFIRMED")
    session.add(batch)
    session.flush()

    return ev, client, policy, batch


class TestPerEmpresaFormula:
    """Spec §4.3 — Comissão real = (Total líquido empresa – Perks) × %."""

    def test_single_policy_no_perks(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        # Two NFs totaling R$ 20,000
        for i, val in enumerate([Decimal("12000"), Decimal("8000")]):
            db_session.add(FinancialImport(
                nf_valor_liquido=val,
                nf_mes_recebimento=f"2026-0{i+2}",
                quarter=1, year=2026,
                import_batch_id=batch.id,
                cliente_mae="Acme Corp",
                operadora="Bradesco",
                produto="Saude",
                status_recebimento="RECEBIDO",
                data_recebimento=date(2026, 2 + i, 15),
            ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
        ).first()
        assert comm is not None
        # (12000 + 8000 - 0 perks) × 8% = 20000 × 0.08 = 1600
        assert comm.total_actual == Decimal("1600.00")

    def test_perks_subtracted_at_empresa_level(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("20000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))

        # Perk of R$ 5,000 for this client in Q1
        db_session.add(Perk(
            client_id=client.id,
            quarter=1, year=2026,
            amount=Decimal("5000"),
            import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
        ).first()
        assert comm is not None
        # (20000 - 5000) × 0.08 = 15000 × 0.08 = 1200
        assert comm.total_actual == Decimal("1200.00")

    def test_two_policies_same_client_proportional_share(self, db_session):
        ev, client, policy_saude, batch = _base_setup(db_session)

        policy_odonto = Policy(
            hubspot_ticket_id="TICKET-101",
            ev_id=ev.id,
            client_id=client.id,
            segment=Segment.P,
            benefit_type=BenefitType.ODONTO,
            mrr_projected=Decimal("3000"),
            closed_date=date(2026, 1, 20),
            commission_status=CommissionStatus.PROJECTED,
            first_payment_real=date(2026, 2, 1),
            installments_paid=0,
            initial_installments_paid=0,
            partner_operator="Bradesco",
        )
        db_session.add(policy_odonto)
        db_session.flush()

        # NF for saude: R$ 10,000
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("10000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        # NF for odonto: R$ 5,000
        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("5000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Odonto",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))

        # Perk R$ 3,000
        db_session.add(Perk(
            client_id=client.id, quarter=1, year=2026,
            amount=Decimal("3000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm_saude = Commission.query.filter_by(
            policy_id=policy_saude.id, quarter=1, year=2026, is_final=False
        ).first()
        comm_odonto = Commission.query.filter_by(
            policy_id=policy_odonto.id, quarter=1, year=2026, is_final=False
        ).first()

        # Client total NF = 15000, perks = 3000, net = 12000
        # Saude share = 10000/15000 = 2/3, Odonto share = 5000/15000 = 1/3
        # Saude commission = 12000 × (2/3) × 0.08 = 640
        # Odonto commission = 12000 × (1/3) × 0.08 = 320
        assert comm_saude is not None
        assert comm_odonto is not None
        assert comm_saude.total_actual == Decimal("640.00")
        assert comm_odonto.total_actual == Decimal("320.00")

    def test_perks_greater_than_nf_yields_zero_commission(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("1000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        db_session.add(Perk(
            client_id=client.id, quarter=1, year=2026,
            amount=Decimal("5000"), import_batch_id=batch.id,
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        comm = Commission.query.filter_by(
            policy_id=policy.id, quarter=1, year=2026, is_final=False
        ).first()
        # net = max(0, 1000 - 5000) = 0 → commission = 0
        assert comm is not None
        assert comm.total_actual == Decimal("0.00")

    def test_status_transitions_after_appraisal(self, db_session):
        ev, client, policy, batch = _base_setup(db_session)

        db_session.add(FinancialImport(
            nf_valor_liquido=Decimal("5000"),
            nf_mes_recebimento="2026-02",
            quarter=1, year=2026,
            import_batch_id=batch.id,
            cliente_mae="Acme Corp",
            operadora="Bradesco",
            produto="Saude",
            status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 2, 15),
        ))
        db_session.flush()

        run_quarterly_appraisal(1, 2026)

        db_session.refresh(policy)
        assert policy.commission_status == CommissionStatus.IN_PAYMENT
        assert policy.installments_paid >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_modules/test_calculator.py -v`
Expected: Failures — tests expect per-empresa aggregation + perks, but current code does per-NF without perks.

- [ ] **Step 3: Rewrite the calculator**

Replace the full contents of `backend/app/modules/commissions/calculator.py`:

```python
"""Quarterly commission calculator (v4 — per-empresa formula with perks).

Spec §4.3:
  Comissão real = (Total líquido empresa − Perks empresa) × % comissão

Algorithm:
1. Match NF rows → policies by (cliente_mae, operadora, produto) normalised
2. Aggregate matched NFs by client (empresa level)
3. Subtract perks at the client level
4. Distribute net amount proportionally across policies
5. Apply commission % per policy (from gongo quarter achievement snapshot)
6. Update commission_status via status helper
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.extensions import db
from app.models import (
    Policy,
    Commission,
    EvQuarterAchievement,
    FinancialImport,
    Perk,
    User,
)
from app.modules.policies.filters import active_ev_policies_query
from app.modules.financial.matcher import build_policy_index, normalize
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.modules.commissions.status import update_policy_statuses


# ── Errors ───────────────────────────────────────────────────────────


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# ── Pre-check ────────────────────────────────────────────────────────


def validate_achievements_for_appraisal(quarter, year):
    """Verify every (ev_id, gongo_q, gongo_y) needed by this apuração
    has a stored achievement.

    Returns list of human-readable strings for missing combinations.
    Empty list = ok to proceed.
    """
    policies = active_ev_policies_query().all()

    needed = set()
    for p in policies:
        if not p.closed_date or not p.ev_id:
            continue
        gq = (p.closed_date.month - 1) // 3 + 1
        needed.add((p.ev_id, gq, p.closed_date.year))

    missing = []
    for ev_id, gq, gy in sorted(needed, key=lambda t: (str(t[0]), t[2], t[1])):
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=gq, year=gy
        ).first()
        if ach is None or ach.achievement_pct is None:
            user = db.session.get(User, ev_id)
            label = user.name if user else str(ev_id)
            missing.append(f"{label} → Q{gq}/{gy}")
    return missing


# ── Benefit normalisation ────────────────────────────────────────────

BENEFIT_MAP = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}


# ── Main entry ───────────────────────────────────────────────────────


def run_quarterly_appraisal(quarter, year):
    """Process all financial_imports for (quarter, year) and produce commissions.

    Implements spec §4.3:
      Comissão real = (Total líquido empresa − Perks empresa) × % comissão
    """
    # ── Pre-check ────────────────────────────────────────────
    missing = validate_achievements_for_appraisal(quarter, year)
    if missing:
        raise MissingAchievementsError(missing)

    # ── 1. Wipe non-final commissions ────────────────────────
    Commission.query.filter_by(
        quarter=quarter, year=year, is_final=False
    ).delete()
    db.session.flush()

    # ── 2. Reset installments_paid to baseline ───────────────
    locked_policy_ids = {
        pid for (pid,) in db.session.query(Commission.policy_id)
        .filter(
            Commission.quarter == quarter,
            Commission.year == year,
            Commission.is_final.is_(True),
        )
        .all()
    }
    policies = [
        p for p in active_ev_policies_query().all()
        if p.id not in locked_policy_ids
    ]

    locked_nf_count_rows = (
        db.session.query(
            FinancialImport.policy_id,
            db.func.count(FinancialImport.id),
        )
        .join(Commission, Commission.policy_id == FinancialImport.policy_id)
        .filter(
            Commission.is_final.is_(True),
            FinancialImport.match_status == 'MATCHED',
        )
        .group_by(FinancialImport.policy_id)
        .all()
    )
    locked_nf_count = {pid: int(cnt) for pid, cnt in locked_nf_count_rows}

    for p in policies:
        p.installments_paid = (
            (p.initial_installments_paid or 0) + locked_nf_count.get(p.id, 0)
        )

    # ── 3. Build matcher index ───────────────────────────────
    policy_index = build_policy_index(policies)

    # ── 4. Pass 1 — Match NFs to policies ────────────────────
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

    # Accumulators
    policy_nf_subtotals = defaultdict(Decimal)   # policy_id → sum NF values
    client_nf_totals = defaultdict(Decimal)       # client_id → sum NF values
    matched_policies = {}                          # policy_id → Policy
    earliest_nf_dates = {}                         # policy_id → earliest date

    for nf in nfs:
        produto_n = normalize(nf.produto or '')
        benefit = BENEFIT_MAP.get(produto_n)
        if benefit is None:
            nf.match_status = 'PRODUTO_NAO_SUPORTADO'
            nf.policy_id = None
            nf.matched_at = None
            continue

        key = (
            normalize(nf.cliente_mae or ''),
            normalize(nf.operadora or ''),
            benefit,
        )
        candidates = policy_index.get(key, [])
        if not candidates:
            nf.match_status = 'UNMATCHED'
            nf.policy_id = None
            nf.matched_at = None
            continue

        matched = None
        for policy in candidates:
            if not policy.first_payment_real:
                continue
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

        if matched is None:
            best = candidates[0]
            if (not best.first_payment_real
                    or (nf.data_recebimento
                        and nf.data_recebimento < best.first_payment_real)):
                nf.match_status = 'PRE_VIGENCIA'
            else:
                nf.match_status = 'EXPIRED'
            nf.policy_id = best.id
            nf.matched_at = None
            continue

        # Record the match
        amount = Decimal(str(nf.nf_valor_liquido))
        nf.policy_id = matched.id
        nf.match_status = 'MATCHED'
        nf.matched_at = datetime.now(timezone.utc)

        policy_nf_subtotals[matched.id] += amount
        client_nf_totals[matched.client_id] += amount
        matched_policies[matched.id] = matched
        matched.installments_paid = (matched.installments_paid or 0) + 1

        # Track earliest NF date per policy (for first_payment_real inference)
        if nf.data_recebimento:
            prev = earliest_nf_dates.get(matched.id)
            if prev is None or nf.data_recebimento < prev:
                earliest_nf_dates[matched.id] = nf.data_recebimento

    # ── 5. Load perks per client ─────────────────────────────
    perks_by_client = defaultdict(Decimal)
    perk_rows = Perk.query.filter_by(quarter=quarter, year=year).all()
    for perk in perk_rows:
        perks_by_client[perk.client_id] += perk.amount

    # ── 6. Pass 2 — Compute commissions per policy ──────────
    for policy_id, nf_subtotal in policy_nf_subtotals.items():
        policy = matched_policies[policy_id]
        client_id = policy.client_id

        # Empresa-level aggregation (spec §4.3)
        client_total = client_nf_totals[client_id]
        client_perks = perks_by_client.get(client_id, Decimal('0'))
        net_client = max(Decimal('0'), client_total - client_perks)

        # Proportional share for this policy
        if client_total > 0:
            share = nf_subtotal / client_total
        else:
            share = Decimal('0')
        net_policy = (net_client * share).quantize(Decimal('0.01'))

        # Achievement snapshot from gongo quarter
        gongo_q = (policy.closed_date.month - 1) // 3 + 1
        gongo_y = policy.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=policy.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        segment_value = policy.segment.value if policy.segment else 'P'
        commission_pct, version = lookup_commission_pct(segment_value, achievement)
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (net_policy * commission_pct).quantize(Decimal('0.01'))

        comm = Commission(
            policy_id=policy_id,
            ev_id=policy.ev_id,
            quarter=quarter,
            year=year,
            segment=segment_value,
            achievement_pct=achievement,
            commission_pct=commission_pct,
            commission_pct_version=version,
            monthly_actual=commission_amount,
            total_actual=commission_amount,
            is_final=False,
        )
        db.session.add(comm)

    # ── 7. Update commission_status ──────────────────────────
    update_policy_statuses(matched_policies.values(), earliest_nf_dates)

    db.session.flush()
    return _build_summary(quarter, year)


# ── Summary ──────────────────────────────────────────────────────────


def _build_summary(quarter, year):
    return {
        "totals": {
            "matched_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='MATCHED'
            ).count(),
            "unmatched_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='UNMATCHED'
            ).count(),
            "expired_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='EXPIRED'
            ).count(),
            "pre_vigencia_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='PRE_VIGENCIA'
            ).count(),
            "produto_nao_suportado_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='PRODUTO_NAO_SUPORTADO'
            ).count(),
        }
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_modules/test_calculator.py -v`
Expected: 5 passed

- [ ] **Step 5: Run existing tests to check for regressions**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass (existing tests should still work since the calculator API is the same)

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/commissions/calculator.py backend/tests/test_modules/test_calculator.py
git commit -m "fix: rewrite calculator with per-empresa formula + perks deduction (spec §4.3)"
```

---

### Task 3: HubSpot sync — fetch ticket de implantação

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Create: `backend/tests/test_modules/test_sync_implant.py`

- [ ] **Step 1: Write failing tests for implant ticket fetch**

```python
# backend/tests/test_modules/test_sync_implant.py
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    CommissionStatus, PlatformSetting,
)
from app.modules.hubspot_sync.sync import run_sync
from app.extensions import db


def _seed_ev(session):
    ev = User(email="vendedor1@piposaude.com", name="Vendedor Um",
              role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()
    return ev


class TestSyncImplantTicket:
    """Spec §3.5 — enrich from ticket de implantação via deal → tickets."""

    @patch("app.modules.hubspot_sync.sync.HubSpotClient")
    def test_populates_mrr_post_deploy_and_first_payment_prev(self, MockClient, db_session):
        ev = _seed_ev(db_session)

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_client.get_all_owners.return_value = {
            "12345": "vendedor1@piposaude.com"
        }

        # search_tickets returns one gongoed ticket
        mock_client.search_tickets.side_effect = [
            {
                "results": [{
                    "id": "999",
                    "properties": {
                        "solicitante_demanda": "12345",
                        "cotar___segmentacao_pipo": "P (81-200)",
                        "mrr___receita_mensal": "5000",
                        "closed_date": "2026-01-15",
                        "apolice___beneficio": "Saúde",
                        "cliente___nome_da_empresa": "TestCorp",
                    }
                }],
                "paging": {},
            },
        ]

        # Deal association
        mock_client.get_associations.side_effect = [
            # tickets/999/associations/deals
            {"results": [{"toObjectId": "D1"}]},
            # deals/D1/associations/tickets
            {"results": [
                {"toObjectId": "999"},   # cotação (same ticket)
                {"toObjectId": "888"},   # implantação (different)
            ]},
        ]

        mock_client.get_deal.return_value = {
            "properties": {
                "dealstage": "closedwon",
                "hs_v2_date_entered_8438574": "2026-02-01",
            }
        }

        mock_client.get_ticket.return_value = {
            "properties": {
                "previsao_primeiro_pagamento": "2026-03-15",
                "mrr_pos_implantacao": "4800",
            }
        }

        run_sync()

        policy = Policy.query.filter_by(hubspot_ticket_id="999").first()
        assert policy is not None
        assert policy.first_payment_prev == date(2026, 3, 15)
        assert policy.mrr_post_deploy == Decimal("4800")

    @patch("app.modules.hubspot_sync.sync.HubSpotClient")
    def test_no_implant_ticket_leaves_fields_none(self, MockClient, db_session):
        ev = _seed_ev(db_session)

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        mock_client.get_all_owners.return_value = {
            "12345": "vendedor1@piposaude.com"
        }

        mock_client.search_tickets.side_effect = [
            {
                "results": [{
                    "id": "999",
                    "properties": {
                        "solicitante_demanda": "12345",
                        "cotar___segmentacao_pipo": "P (81-200)",
                        "mrr___receita_mensal": "5000",
                        "closed_date": "2026-01-15",
                        "apolice___beneficio": "Saúde",
                        "cliente___nome_da_empresa": "TestCorp",
                    }
                }],
                "paging": {},
            },
        ]

        # Deal association — only the cotação ticket associated
        mock_client.get_associations.side_effect = [
            {"results": [{"toObjectId": "D1"}]},
            {"results": [{"toObjectId": "999"}]},  # only self
        ]

        mock_client.get_deal.return_value = {
            "properties": {"dealstage": "closedwon", "hs_v2_date_entered_8438574": "2026-02-01"}
        }

        run_sync()

        policy = Policy.query.filter_by(hubspot_ticket_id="999").first()
        assert policy is not None
        assert policy.first_payment_prev is None
        assert policy.mrr_post_deploy is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_modules/test_sync_implant.py -v`
Expected: Assertion failures — `first_payment_prev` and `mrr_post_deploy` are None because sync doesn't fetch implant ticket.

- [ ] **Step 3: Modify sync.py to fetch implant ticket data**

Edit `backend/app/modules/hubspot_sync/sync.py` — add implant ticket navigation inside `_process_ticket`, after the deal association block:

```python
# In _process_ticket, replace the deal association block with:
    # Fetch deal associations (non-lockable — always refresh)
    try:
        assoc = hs_client.get_associations("tickets", ticket_id, "deals")
        deal_ids = [r["toObjectId"] for r in assoc.get("results", [])]
        if deal_ids:
            policy.deal_id = str(deal_ids[0])
            deal = hs_client.get_deal(deal_ids[0], DEAL_PROPERTIES)
            deal_props = deal.get("properties", {})
            policy.deal_stage = deal_props.get("dealstage")
            if not locked:
                policy.deploy_date = parse_date(deal_props.get("hs_v2_date_entered_8438574"))

            # Navigate deal → tickets to find implantation ticket (spec §3.5)
            try:
                ticket_assocs = hs_client.get_associations(
                    "deals", deal_ids[0], "tickets"
                )
                assoc_ticket_ids = [
                    str(r["toObjectId"])
                    for r in ticket_assocs.get("results", [])
                ]
                implant_ids = [
                    tid for tid in assoc_ticket_ids if tid != str(ticket_id)
                ]
                if implant_ids and not locked:
                    implant = hs_client.get_ticket(
                        implant_ids[0], TICKET_IMPLANT_PROPERTIES
                    )
                    impl_props = implant.get("properties", {})
                    policy.first_payment_prev = parse_date(
                        impl_props.get("previsao_primeiro_pagamento")
                    )
                    policy.mrr_post_deploy = parse_decimal(
                        impl_props.get("mrr_pos_implantacao")
                    )
            except Exception as e:
                logger.warning(
                    f"Implant ticket fetch failed for ticket {ticket_id}: {e}"
                )
    except Exception as e:
        logger.warning(f"Deal association fetch failed for ticket {ticket_id}: {e}")
```

The full replacement for `_process_ticket` (to make the edit precise): find the existing `# Fetch deal associations` block (lines ~204-217 of the current file) and replace it entirely with the code above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_modules/test_sync_implant.py -v`
Expected: 2 passed

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_sync_implant.py
git commit -m "fix: sync ticket de implantação data (mrr_post_deploy, first_payment_prev) — spec §3.5"
```

---

### Task 4: Live projection from Policy data (estimated balance + monthly projection)

**Files:**
- Create: `backend/app/modules/commissions/projection.py`
- Modify: `backend/app/api/v1/commissions.py`
- Create: `backend/tests/test_modules/test_projection.py`

- [ ] **Step 1: Write failing tests for projection helpers**

```python
# backend/tests/test_modules/test_projection.py
from datetime import date
from decimal import Decimal

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType,
    CommissionStatus, CommissionPctTable, Goal,
)
from app.modules.commissions.projection import (
    compute_ev_balance,
    compute_ev_projection,
)
from app.extensions import db


def _seed_pct_table(session):
    """Seed P segment with 3 tiers. Middle tier (50-99.9%) = 8%."""
    rows = [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "9.9999", "0.10"),
    ]
    for seg, amin, amax, pct in rows:
        session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))
    session.flush()


def _setup(session):
    ev = User(email="ev@piposaude.com", name="EV Test", role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()

    client = Client(name="TestCo", name_normalized="testco", ev_id=ev.id)
    session.add(client)
    session.flush()

    _seed_pct_table(session)
    return ev, client


class TestComputeEvBalance:
    """Spec §9 — Projeção: MRR comissão × faixa média (50-99.9%)."""

    def test_balance_for_projected_policy(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_ticket_id="T-1", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            installments_paid=0,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # 10000 × 0.08 (middle tier) × 12 remaining = 9600
        assert balance == Decimal("9600.00")

    def test_balance_reduces_with_installments_paid(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_ticket_id="T-2", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=4,
            first_payment_real=date(2026, 1, 1),
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # 10000 × 0.08 × (12-4) = 800 × 8 = 6400
        assert balance == Decimal("6400.00")

    def test_settled_policy_excluded(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_ticket_id="T-3", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.SETTLED,
            installments_paid=12,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)
        assert balance == Decimal("0")

    def test_uses_mrr_for_commission_cascade(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_ticket_id="T-4", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            mrr_post_deploy=Decimal("8000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            installments_paid=0,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # mrr_for_commission = mrr_post_deploy = 8000
        # 8000 × 0.08 × 12 = 7680
        assert balance == Decimal("7680.00")


class TestComputeEvProjection:
    """Spec §7 — Projeção mensal, 12 meses."""

    def test_projection_distributes_across_months(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_ticket_id="T-5", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=6,
            first_payment_real=date(2026, 1, 1),
        ))
        db_session.flush()

        months = compute_ev_projection(ev.id, ref_date=date(2026, 4, 1))

        assert len(months) == 12
        # 6 remaining installments of R$ 800 (10000 × 0.08)
        non_zero = [m for m in months if m["projected"] > Decimal("0")]
        assert len(non_zero) == 6
        assert all(m["projected"] == Decimal("800.00") for m in non_zero)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_modules/test_projection.py -v`
Expected: ImportError — `cannot import name 'compute_ev_balance'`

- [ ] **Step 3: Implement projection module**

```python
# backend/app/modules/commissions/projection.py
"""Live projection helpers — compute estimated balance and monthly projection
from Policy data using the middle-tier commission % (spec §9).

These never touch Commission records. They read Policy fields directly
and compute on-the-fly so projections stay current after each sync.
"""
from datetime import date
from decimal import Decimal

from app.models import Policy, CommissionStatus
from app.modules.commissions.pct_lookup import lookup_commission_pct

# Middle-tier achievement value — any value in [0.50, 0.999) works.
# We use 0.50 (the floor) to hit the 50-99.9% tier in the pct table.
_MIDDLE_TIER_ACH = Decimal("0.5000")


def _estimated_monthly(policy):
    """Estimated monthly commission for a single policy using middle tier %."""
    mrr = policy.mrr_for_commission or Decimal("0")
    if mrr <= 0:
        return Decimal("0")
    segment = policy.segment.value if policy.segment else "P"
    pct, _ = lookup_commission_pct(segment, _MIDDLE_TIER_ACH)
    if pct is None:
        return Decimal("0")
    return (mrr * pct).quantize(Decimal("0.01"))


def _active_policies(ev_id):
    """Non-settled, non-cancelled policies for an EV."""
    return Policy.query.filter(
        Policy.ev_id == ev_id,
        Policy.commission_status.notin_([
            CommissionStatus.SETTLED,
            CommissionStatus.CANCELLED,
        ]),
    ).all()


def compute_ev_balance(ev_id):
    """Total estimated saldo a receber for an EV (spec §3.7 saldo_devedor_estimado).

    balance = SUM( monthly_est × remaining_months ) across active policies.
    """
    policies = _active_policies(ev_id)
    balance = Decimal("0")
    for p in policies:
        monthly = _estimated_monthly(p)
        remaining = max(0, 12 - (p.installments_paid or 0))
        balance += monthly * remaining
    return balance.quantize(Decimal("0.01"))


def compute_ev_projection(ev_id, ref_date=None):
    """12-month projection of estimated receivables (spec §7).

    Returns list of 12 dicts: [{"month": "YYYY-MM", "projected": Decimal}, ...]
    """
    ref_date = ref_date or date.today()
    policies = _active_policies(ev_id)

    # Build 12-month bucket list
    buckets = []
    for i in range(12):
        m = ref_date.month + i
        y = ref_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        buckets.append({"month": f"{y}-{m:02d}", "projected": Decimal("0")})

    for p in policies:
        monthly = _estimated_monthly(p)
        if monthly <= 0:
            continue

        remaining = max(0, 12 - (p.installments_paid or 0))
        if remaining == 0:
            continue

        # Determine payment start: real > prev > ref_date
        start = p.first_payment_real or p.first_payment_prev or ref_date

        distributed = 0
        for bucket in buckets:
            if distributed >= remaining:
                break
            bucket_y, bucket_m = map(int, bucket["month"].split("-"))
            if (bucket_y, bucket_m) >= (start.year, start.month):
                bucket["projected"] += monthly
                distributed += 1

    # Quantize all values
    for b in buckets:
        b["projected"] = b["projected"].quantize(Decimal("0.01"))

    return buckets
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_modules/test_projection.py -v`
Expected: 5 passed

- [ ] **Step 5: Rewrite the commission summary and projection endpoints**

In `backend/app/api/v1/commissions.py`, replace `commission_summary` and `commission_projection`:

```python
# Replace the commission_summary function (lines ~48-104) with:
@commissions_bp.route("/summary")
@require_auth
def commission_summary():
    """Summary: saldo a receber, atingimento, projeção (spec §7 + §9)."""
    from app.modules.commissions.projection import compute_ev_balance

    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    # Live estimated balance from Policy data (spec §9 projection layer)
    balance = compute_ev_balance(ev_id)

    # Current quarter achievement
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1
    current_year = today.year

    goal = Goal.query.filter_by(
        ev_id=ev_id, quarter=current_quarter, year=current_year
    ).first()

    quarter_start_month = (current_quarter - 1) * 3 + 1
    quarter_end_month = current_quarter * 3
    start_date = date(current_year, quarter_start_month, 1)
    if quarter_end_month == 12:
        end_date = date(current_year + 1, 1, 1)
    else:
        end_date = date(current_year, quarter_end_month + 1, 1)

    quarter_mrr = db.session.query(
        func.coalesce(func.sum(Policy.mrr_projected), 0)
    ).filter(
        Policy.ev_id == ev_id,
        Policy.closed_date >= start_date,
        Policy.closed_date < end_date,
    ).scalar()

    target = goal.mrr_target if goal else Decimal("0")
    achievement = (Decimal(str(quarter_mrr)) / target * 100) if target > 0 else Decimal("0")

    return jsonify({
        "data": {
            "balance_estimated": str(balance),
            "current_quarter": current_quarter,
            "current_year": current_year,
            "mrr_sold": str(quarter_mrr),
            "mrr_target": str(target),
            "achievement_pct": str(achievement.quantize(Decimal("0.01"))),
        }
    })


# Replace the commission_projection function (lines ~107-138) with:
@commissions_bp.route("/projection")
@require_auth
def commission_projection():
    """12-month projection of estimated receivables (spec §7)."""
    from app.modules.commissions.projection import compute_ev_projection

    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    months = compute_ev_projection(ev_id)

    return jsonify({
        "data": [
            {"month": m["month"], "projected": str(m["projected"])}
            for m in months
        ]
    })
```

- [ ] **Step 6: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/commissions/projection.py backend/app/api/v1/commissions.py backend/tests/test_modules/test_projection.py
git commit -m "fix: live projection from Policy data using middle-tier % (spec §7, §9)"
```

---

## Post-Implementation Notes

After these 4 tasks, the following critical issues from the spec audit are resolved:

| # | Issue | Fixed by |
|---|-------|----------|
| 1 | Commission formula per-NF, not per-empresa | Task 2 — calculator rewrite |
| 2 | Perks never subtracted | Task 2 — calculator rewrite |
| 3 | monthly_estimated/total_estimated always NULL | Task 4 — live projection |
| 4 | Ticket implantação not synced | Task 3 — sync.py |
| 5 | commission_status never transitions | Task 1 + Task 2 |

**Remaining significant issues** (not in this plan, prioritize next):
- Finance dashboard backend incomplete (saldo by year, cash flow series, orçado vs realizado)
- MRR > 0 filter missing in sync
- soma_nf_valor_liquido not exposed
- data_fim_estimada not calculated
- EV table missing commission % column
- Export only CSV (no XLSX/PDF)
