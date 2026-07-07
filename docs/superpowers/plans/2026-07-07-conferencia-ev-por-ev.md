# Conferência EV por EV — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RevOps confere a Apuração EV mensal EV por EV dentro do CALCULATING; a liberação para VALIDATING é bloqueada até 100% conferido; recálculos só invalidam conferências de EVs cujos valores realmente mudaram (fingerprint).

**Architecture:** Camada aditiva sobre o state machine existente — tabela nova `ev_signoffs` (1 linha por apuração×EV), serviço `signoffs.py` (escopo/fingerprint/ensure/refresh), gate no chokepoint `transition_appraisal`, 2 endpoints REST, payload do detail enriquecido (incl. EVs sem movimento), e a aba "Por EV" da revisão ganha banda de progresso + badges + botões. Spec: `docs/superpowers/specs/2026-07-07-conferencia-ev-por-ev-design.md`.

**Tech Stack:** Flask + SQLAlchemy + Alembic + pytest (Postgres `comissoes_test`, isolamento por savepoint) · ClojureScript + re-frame + shadow-cljs + karma.

**Convenções do repo que você precisa saber:**
- Testes backend rodam de `backend/`: `python -m pytest tests/... -v`. O conftest envolve cada teste numa transação externa com savepoints — `db.session.commit()` dentro do teste é seguro e **não precisa de teardown manual**.
- `GUID` (app/models/compat.py) devolve `uuid.UUID` nas leituras e aceita `str` ou `UUID` no bind. Comparações entre valores vindos do banco e strings de URL exigem normalização (`str(x)`).
- Testes frontend: de `frontend/`, `npm test` (compila o build `:test` e roda karma headless). Funções puras testáveis devem ser `defn` público.
- Commits pequenos por task, mensagem em `feat(...)/test(...)` como no histórico.

---

## Task 1: Modelo `EvSignoff` + migration

**Files:**
- Create: `backend/app/models/ev_signoff.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/a7c3e5f1b2d4_create_ev_signoffs.py`
- Test: `backend/tests/test_models/test_ev_signoff.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models/test_ev_signoff.py`:

```python
"""EvSignoff model: shape + unique constraint."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appraisal, AppraisalStatus, EvSignoff, SignoffStatus, User, UserRole


def _mk_appraisal_and_ev(suffix):
    admin = User(email=f"sig-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"sig-ev-{suffix}@x", name="EV Sig",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()
    appraisal = Appraisal(month=9, year=2026,
                          status=AppraisalStatus.CALCULATING,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()
    return appraisal, ev


def test_ev_signoff_defaults(db_session):
    appraisal, ev = _mk_appraisal_and_ev(uuid.uuid4().hex[:8])
    row = EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id)
    db.session.add(row)
    db.session.flush()

    assert row.status == SignoffStatus.PENDING
    assert row.values_changed is False
    assert row.fingerprint is None
    assert row.signed_off_by is None
    assert row.signed_off_at is None


def test_ev_signoff_unique_per_appraisal_ev(db_session):
    appraisal, ev = _mk_appraisal_and_ev(uuid.uuid4().hex[:8])
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id))
    db.session.flush()
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_models/test_ev_signoff.py -v`
Expected: FAIL — `ImportError: cannot import name 'EvSignoff' from 'app.models'`

- [ ] **Step 3: Create the model**

Create `backend/app/models/ev_signoff.py`:

```python
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class SignoffStatus(str, enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"


class EvSignoff(db.Model):
    """Conferência do RevOps por EV numa Apuração mensal.

    Uma linha por (apuração, EV do escopo). Uma linha DONE carrega o
    fingerprint dos valores do EV no momento da conferência; um recálculo
    que muda os valores volta a linha para PENDING com values_changed=True
    (spec docs/superpowers/specs/2026-07-07-conferencia-ev-por-ev-design.md).
    """
    __tablename__ = "ev_signoffs"
    __table_args__ = (
        db.UniqueConstraint(
            "appraisal_id", "ev_id", name="uq_ev_signoff_appraisal_ev",
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    appraisal_id = db.Column(
        GUID, db.ForeignKey("appraisals.id"), nullable=False,
    )
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(
        db.Enum(SignoffStatus, name="signoff_status"),
        default=SignoffStatus.PENDING,
        nullable=False,
    )
    fingerprint = db.Column(db.String(64), nullable=True)
    values_changed = db.Column(db.Boolean, default=False, nullable=False)
    signed_off_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    signed_off_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    appraisal = db.relationship("Appraisal", foreign_keys=[appraisal_id])
    ev = db.relationship("User", foreign_keys=[ev_id])
    signer = db.relationship("User", foreign_keys=[signed_off_by])
```

In `backend/app/models/__init__.py`, add the import after the `ev_validation` line and the two names to `__all__`:

```python
from app.models.ev_signoff import EvSignoff, SignoffStatus
```

```python
    "EvSignoff", "SignoffStatus",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; python -m pytest tests/test_models/test_ev_signoff.py -v`
Expected: 2 passed (o conftest cria as tabelas com `db.create_all()` a partir dos models — a migration não é necessária para os testes).

- [ ] **Step 5: Write the migration**

Create `backend/migrations/versions/a7c3e5f1b2d4_create_ev_signoffs.py`:

```python
"""Create ev_signoffs

Conferência do RevOps por EV na apuração mensal: status + fingerprint,
para o recálculo invalidar só os EVs cujos valores realmente mudaram.

Revision ID: a7c3e5f1b2d4
Revises: e1f2a3b4c5d6
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from app.models.compat import GUID


revision = "a7c3e5f1b2d4"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ev_signoffs",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("appraisal_id", GUID(length=36), nullable=False),
        sa.Column("ev_id", GUID(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "DONE", name="signoff_status"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "values_changed", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("signed_off_by", GUID(length=36), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["appraisal_id"], ["appraisals.id"]),
        sa.ForeignKeyConstraint(["ev_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signed_off_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "appraisal_id", "ev_id", name="uq_ev_signoff_appraisal_ev",
        ),
    )


def downgrade():
    op.drop_table("ev_signoffs")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE signoff_status")
```

- [ ] **Step 6: Apply the migration to the dev DB**

Run: `cd backend; python -m flask db upgrade`
Expected: `Running upgrade e1f2a3b4c5d6 -> a7c3e5f1b2d4, Create ev_signoffs` (sem erro; `FLASK_APP` já vem do `.env`/`wsgi.py`).

- [ ] **Step 7: Commit**

```powershell
git add backend/app/models/ev_signoff.py backend/app/models/__init__.py backend/migrations/versions/a7c3e5f1b2d4_create_ev_signoffs.py backend/tests/test_models/test_ev_signoff.py
git commit -m "feat(models): EvSignoff - conferencia por EV da apuracao mensal"
```

---

## Task 2: Serviço de sign-off (escopo, fingerprint, ensure, refresh, pendências, totais)

**Files:**
- Create: `backend/app/modules/workflow/signoffs.py`
- Test: `backend/tests/test_modules/test_workflow/test_signoffs.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_modules/test_workflow/test_signoffs.py`:

```python
"""Signoff service: scope, fingerprint, ensure, refresh, pending, totals."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, Commission,
    EvSignoff, Policy, Segment, SignoffStatus, User, UserRole,
)
from app.modules.workflow.signoffs import (
    compute_ev_fingerprint,
    ensure_signoffs,
    pending_signoff_evs,
    refresh_signoffs_after_recalc,
    signoff_scope_ev_ids,
    signoff_totals,
)


def _mk_users(suffix):
    admin = User(email=f"sos-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev_active = User(email=f"sos-ev1-{suffix}@x", name=f"Ativa {suffix}",
                     role=UserRole.EV, active=True)
    ev_inactive = User(email=f"sos-ev2-{suffix}@x", name=f"Inativa {suffix}",
                       role=UserRole.EV, active=False, left_company=True)
    db.session.add_all([admin, ev_active, ev_inactive])
    db.session.flush()
    return admin, ev_active, ev_inactive


def _mk_commission(ev, suffix, total="80.00", month=9, year=2026):
    client = Client.find_or_create(f"SosClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"SOS-{suffix}",
        numero_apolice=f"AP-SOS-{suffix}",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Amil", closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.flush()
    comm = Commission(
        policy_id=policy.id, ev_id=ev.id, month=month, year=year,
        segment="P", achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.08"),
        monthly_actual=Decimal(total), total_actual=Decimal(total),
        is_final=False,
    )
    db.session.add(comm)
    db.session.flush()
    return policy, comm


def _mk_appraisal(admin, month=9, year=2026,
                  status=AppraisalStatus.CALCULATING):
    appraisal = Appraisal(month=month, year=year, status=status,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()
    return appraisal


def test_scope_active_in_inactive_out_departed_with_commission_in(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev_active, ev_departed = _mk_users(suffix)

    scope = signoff_scope_ev_ids(9, 2026)
    assert ev_active.id in scope
    assert ev_departed.id not in scope          # inativa e sem comissão
    assert admin.id not in scope                # ADMIN nunca entra

    _mk_commission(ev_departed, suffix)         # desligada COM comissão
    scope = signoff_scope_ev_ids(9, 2026)
    assert ev_departed.id in scope


def test_fingerprint_stable_and_sensitive(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)

    empty = compute_ev_fingerprint(ev.id, 9, 2026)
    assert empty == compute_ev_fingerprint(ev.id, 9, 2026)  # estável

    _, comm = _mk_commission(ev, suffix)
    with_comm = compute_ev_fingerprint(ev.id, 9, 2026)
    assert with_comm != empty

    comm.total_actual = Decimal("81.00")
    db.session.flush()
    assert compute_ev_fingerprint(ev.id, 9, 2026) != with_comm


def test_ensure_signoffs_idempotent(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin)

    assert ensure_signoffs(appraisal) == 1      # só a EV ativa
    assert ensure_signoffs(appraisal) == 0      # segunda chamada não duplica
    rows = EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
    assert len(rows) == 1
    assert rows[0].status == SignoffStatus.PENDING


def test_refresh_keeps_unchanged_and_invalidates_changed(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    _, comm = _mk_commission(ev, suffix)
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    row.signed_off_by = admin.id
    row.signed_off_at = datetime.now(timezone.utc)
    db.session.flush()

    # Sem mudança → mantém
    result = refresh_signoffs_after_recalc(appraisal)
    assert result == {"invalidated": [], "kept": 1}
    assert row.status == SignoffStatus.DONE

    # Valor mudou → invalida com aviso
    comm.total_actual = Decimal("99.99")
    db.session.flush()
    result = refresh_signoffs_after_recalc(appraisal)
    assert result["invalidated"] == [ev.name]
    assert result["kept"] == 0
    assert row.status == SignoffStatus.PENDING
    assert row.values_changed is True
    assert row.fingerprint is None
    assert row.signed_off_by is None
    assert row.signed_off_at is None


def test_pending_and_totals(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    ev2 = User(email=f"sos-ev3-{suffix}@x", name=f"Zeta {suffix}",
               role=UserRole.EV, active=True)
    db.session.add(ev2)
    db.session.flush()
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    pending = pending_signoff_evs(appraisal)
    assert [name for _, name in pending] == sorted([ev.name, ev2.name])
    assert signoff_totals(appraisal) == {
        "total": 2, "done": 0, "all_done": False,
    }

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    db.session.flush()

    assert [eid for eid, _ in pending_signoff_evs(appraisal)] == [ev2.id]
    assert signoff_totals(appraisal) == {
        "total": 2, "done": 1, "all_done": False,
    }

    # Linha órfã (EV saiu do escopo) não bloqueia o gate nem conta no total:
    ev2.active = False
    db.session.flush()
    assert pending_signoff_evs(appraisal) == []
    assert signoff_totals(appraisal) == {
        "total": 1, "done": 1, "all_done": True,
    }


def test_totals_frozen_from_rows_when_not_calculating(db_session):
    """Fora de CALCULATING os totais vêm das linhas gravadas (histórico),
    não do escopo recomputado — mudanças na tabela de usuários não podem
    reescrever a história de uma apuração liberada/travada."""
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin, status=AppraisalStatus.VALIDATING)
    db.session.add(EvSignoff(
        appraisal_id=appraisal.id, ev_id=ev.id,
        status=SignoffStatus.DONE, fingerprint="x",
    ))
    db.session.flush()

    # A EV nova (ativa) NÃO entra nos totais de uma apuração já liberada.
    ev_new = User(email=f"sos-ev4-{suffix}@x", name="Nova",
                  role=UserRole.EV, active=True)
    db.session.add(ev_new)
    db.session.flush()

    assert signoff_totals(appraisal) == {
        "total": 1, "done": 1, "all_done": True,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.workflow.signoffs'`

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/workflow/signoffs.py`:

```python
"""Conferência (sign-off) por EV da Apuração mensal.

RevOps revisa cada EV dentro do CALCULATING e marca DONE um a um; a
liberação CALCULATING → VALIDATING é bloqueada enquanto houver EV do escopo
sem conferência. Uma linha DONE guarda o fingerprint dos valores do EV;
recálculos só invalidam linhas cujo fingerprint mudou, então o trabalho de
conferência sobrevive à recalculação. O recálculo é sempre global — perks
são deduzidos no nível do cliente e rateados entre apólices que podem ser
de EVs diferentes, então um recálculo escopado deixaria o outro EV
obsoleto (spec 2026-07-07).
"""
import hashlib
import json

from app.extensions import db
from app.models import (
    AppraisalStatus, Commission, EvSignoff, SignoffStatus, User, UserRole,
)


def signoff_scope_ev_ids(month, year):
    """EVs que precisam de conferência em (month, year): todo EV ativo não
    desligado (um mês sem movimento ainda ganha conferência explícita) mais
    qualquer EV com Commission no mês (pega desligados que ainda geraram)."""
    active = {
        u.id for u in User.query.filter_by(
            role=UserRole.EV, active=True, left_company=False,
        ).all()
    }
    with_commission = {
        ev_id for (ev_id,) in db.session.query(Commission.ev_id)
        .filter(
            Commission.month == month,
            Commission.year == year,
            Commission.ev_id.isnot(None),
        )
        .distinct()
        .all()
    }
    return active | with_commission


def compute_ev_fingerprint(ev_id, month, year):
    """sha256 dos valores de comissão do EV no mês. Decimals serializados
    como str — float tornaria o hash instável entre runs idênticos."""
    rows = Commission.query.filter_by(
        ev_id=ev_id, month=month, year=year,
    ).all()
    payload = sorted(
        [
            str(c.policy_id),
            str(c.total_actual or 0),
            str(c.commission_pct or 0),
            str(c.achievement_pct or 0),
        ]
        for c in rows
    )
    canonical = json.dumps(payload, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_signoffs(appraisal):
    """Cria as linhas PENDING que faltam para o escopo atual. Retorna
    quantas criou. Linhas de EVs que saíram do escopo ficam como histórico
    e são ignoradas pelo gate."""
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    existing = {
        s.ev_id for s in EvSignoff.query
        .filter_by(appraisal_id=appraisal.id).all()
    }
    created = 0
    for ev_id in scope - existing:
        db.session.add(EvSignoff(
            appraisal_id=appraisal.id,
            ev_id=ev_id,
            status=SignoffStatus.PENDING,
        ))
        created += 1
    if created:
        db.session.flush()
    return created


def refresh_signoffs_after_recalc(appraisal):
    """Re-hasheia cada linha DONE após um recálculo; volta para PENDING as
    que mudaram (values_changed=True). Retorna
    {"invalidated": [nomes ordenados], "kept": n} para o toast do frontend."""
    ensure_signoffs(appraisal)
    invalidated, kept = [], 0
    rows = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, status=SignoffStatus.DONE,
    ).all()
    for row in rows:
        new_fp = compute_ev_fingerprint(
            row.ev_id, appraisal.month, appraisal.year,
        )
        if new_fp == row.fingerprint:
            kept += 1
            continue
        row.status = SignoffStatus.PENDING
        row.values_changed = True
        row.fingerprint = None
        row.signed_off_by = None
        row.signed_off_at = None
        ev = db.session.get(User, row.ev_id)
        invalidated.append(ev.name if ev else str(row.ev_id))
    if invalidated:
        db.session.flush()
    return {"invalidated": sorted(invalidated), "kept": kept}


def pending_signoff_evs(appraisal):
    """EVs do escopo ainda sem conferência DONE — os que bloqueiam a
    liberação para VALIDATING. Retorna [(ev_id, nome)] ordenado por nome."""
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    done = {
        s.ev_id for s in EvSignoff.query.filter_by(
            appraisal_id=appraisal.id, status=SignoffStatus.DONE,
        ).all()
    }
    pending_ids = scope - done
    if not pending_ids:
        return []
    names = {
        u.id: u.name
        for u in User.query.filter(User.id.in_(list(pending_ids))).all()
    }
    return sorted(
        [(ev_id, names.get(ev_id, str(ev_id))) for ev_id in pending_ids],
        key=lambda t: t[1],
    )


def signoff_totals(appraisal):
    """{"total", "done", "all_done"} para a banda de progresso.

    Em CALCULATING os totais vêm do escopo recomputado (EVs novos entram na
    conta). Fora de CALCULATING vêm das linhas gravadas: são história, e o
    escopo recomputado de hoje reescreveria os números de uma apuração
    antiga a cada mudança no time (mesmo racional do `expected` congelado
    do cycle_aggregator em ciclos LOCKED)."""
    if appraisal.status != AppraisalStatus.CALCULATING:
        rows = EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
        done = sum(1 for r in rows if r.status == SignoffStatus.DONE)
        return {
            "total": len(rows),
            "done": done,
            "all_done": done == len(rows),
        }
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    done_ids = {
        s.ev_id for s in EvSignoff.query.filter_by(
            appraisal_id=appraisal.id, status=SignoffStatus.DONE,
        ).all()
    }
    done = len(scope & done_ids)
    return {
        "total": len(scope),
        "done": done,
        "all_done": done == len(scope),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```powershell
git add backend/app/modules/workflow/signoffs.py backend/tests/test_modules/test_workflow/test_signoffs.py
git commit -m "feat(signoffs): servico de conferencia por EV (escopo, fingerprint, refresh)"
```

---

## Task 3: Gate no state machine + hook no CALCULATING

**Files:**
- Modify: `backend/app/modules/workflow/state_machine.py` (função `transition_appraisal`, ~linhas 65–160)
- Test: `backend/tests/test_modules/test_workflow/test_signoffs.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_modules/test_workflow/test_signoffs.py`:

```python
# ── Gate no state machine ─────────────────────────────────────────────


def test_release_blocked_until_all_signed_off(db_session):
    import pytest as _pytest
    from app.models import EvValidation
    from app.modules.workflow.state_machine import (
        InvalidTransitionError, transition_appraisal,
    )

    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    _mk_commission(ev, suffix)
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    with _pytest.raises(InvalidTransitionError) as exc:
        transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    assert "sem conferência" in str(exc.value)
    assert appraisal.status == AppraisalStatus.CALCULATING

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    db.session.flush()

    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    assert appraisal.status == AppraisalStatus.VALIDATING
    # comportamento existente preservado: a liberação cria as EvValidations
    assert EvValidation.query.filter_by(appraisal_id=appraisal.id).count() == 1


def test_calculating_transition_creates_signoff_rows(db_session):
    """DRAFT → CALCULATING roda o calculator e em seguida garante as linhas
    de sign-off do escopo (hook refresh_signoffs_after_recalc)."""
    from app.modules.workflow.state_machine import transition_appraisal

    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin, month=10, status=AppraisalStatus.DRAFT)

    transition_appraisal(appraisal, AppraisalStatus.CALCULATING)

    rows = EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
    assert {r.ev_id for r in rows} == {ev.id}
    assert rows[0].status == SignoffStatus.PENDING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v -k "release_blocked or creates_signoff_rows"`
Expected: FAIL — o primeiro teste falha porque a transição VALIDATING **passa** (gate ainda não existe: `DID NOT RAISE`); o segundo porque nenhuma linha é criada (`assert set() == {...}`).

- [ ] **Step 3: Implement gate + hook**

In `backend/app/modules/workflow/state_machine.py`:

(a) Add this function right after `_assert_no_open_contestation` (after line 28):

```python
def _assert_signoffs_complete(appraisal, new_status):
    """A liberação CALCULATING → VALIDATING exige a conferência de todos os
    EVs do escopo (spec 2026-07-07). Outros caminhos que escrevem VALIDATING
    direto (resolução de contestação) pulam o gate de propósito — a
    conferência daquele ciclo já aconteceu."""
    if new_status != AppraisalStatus.VALIDATING:
        return
    if appraisal.status != AppraisalStatus.CALCULATING:
        return
    from app.modules.workflow.signoffs import pending_signoff_evs
    pending = pending_signoff_evs(appraisal)
    if pending:
        names = ", ".join(name for _, name in pending[:5])
        more = f" (+{len(pending) - 5})" if len(pending) > 5 else ""
        raise InvalidTransitionError(
            f"{len(pending)} EV(s) sem conferência: {names}{more}. "
            "Confira todos os EVs antes de liberar para validação."
        )
```

(b) In `transition_appraisal`, call it right after the existing
`_assert_no_open_contestation(appraisal, new_status)` line:

```python
    _assert_no_open_contestation(appraisal, new_status)
    _assert_signoffs_complete(appraisal, new_status)
```

(c) In the `if new_status == AppraisalStatus.CALCULATING:` side-effect block,
add the refresh hook right after the `run_monthly_appraisal(...)` call:

```python
    if new_status == AppraisalStatus.CALCULATING:
        # Run the synchronous calculator. Status stays in CALCULATING —
        # RevOps reviews and releases manually via "Liberar para Validação".
        # Missing achievements do NOT block the apuração: affected policies fall
        # back to 0% and the gaps surface as a warning in the review payload, so
        # RevOps can fill them and recalculate before locking.
        from app.modules.commissions.calculator import run_monthly_appraisal
        run_monthly_appraisal(
            appraisal.month, appraisal.year, validate_achievements=False
        )
        # Conferência por EV: garante as linhas do escopo e re-valida os
        # fingerprints — voltas LIDER_REVIEW/REVOPS_REVIEW → CALCULATING
        # re-armam o gate preservando as conferências de quem não mudou.
        from app.modules.workflow.signoffs import refresh_signoffs_after_recalc
        refresh_signoffs_after_recalc(appraisal)
```

- [ ] **Step 4: Run the whole signoff test file**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v`
Expected: 8 passed

- [ ] **Step 5: Run the existing workflow/appraisal suites (regressão do gate)**

Run: `cd backend; python -m pytest tests/test_api/test_appraisal_review.py tests/test_modules/test_workflow -v`
Expected: os testes existentes que fazem CALCULATING → VALIDATING podem falhar com o novo gate **se criarem EVs ativos sem sign-off**. Se algum falhar com "sem conferência": ajuste o teste adicionando, antes da transição, a conferência dos EVs do escopo:

```python
from app.modules.workflow.signoffs import (
    compute_ev_fingerprint, ensure_signoffs,
)
from app.models import EvSignoff, SignoffStatus

ensure_signoffs(appraisal)
for row in EvSignoff.query.filter_by(appraisal_id=appraisal.id).all():
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(
        row.ev_id, appraisal.month, appraisal.year,
    )
db.session.flush()
```

Expected após ajustes: all passed.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/modules/workflow/state_machine.py backend/tests/
git commit -m "feat(workflow): gate de conferencia na liberacao CALCULATING->VALIDATING"
```

---

## Task 4: Endpoints de conferência (marcar / reabrir)

**Files:**
- Modify: `backend/app/api/v1/workflow.py` (imports no topo; rotas novas após `resolve_contestation`, ~linha 347)
- Test: `backend/tests/test_api/test_ev_signoffs.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api/test_ev_signoffs.py`:

```python
"""API da conferência por EV: marcar, reabrir, authz, estados, gate, payload."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, Commission,
    EvSignoff, Policy, Segment, SignoffStatus, User, UserRole,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def signoff_setup():
    """Admin + 2 EVs ativos; EV1 tem apólice + Commission na apuração
    09/2026 em CALCULATING; EV2 é ativo sem movimento."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"soa-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev1 = User(email=f"soa-ev1-{suffix}@x", name=f"Alice {suffix}",
               role=UserRole.EV, active=True)
    ev2 = User(email=f"soa-ev2-{suffix}@x", name=f"Bruno {suffix}",
               role=UserRole.EV, active=True)
    db.session.add_all([admin, ev1, ev2])
    db.session.flush()

    client_obj = Client.find_or_create(f"SoaClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"SOA-{suffix}",
        numero_apolice=f"AP-SOA-{suffix}",
        ev_id=ev1.id, client_id=client_obj.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Amil", closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(month=9, year=2026,
                          status=AppraisalStatus.CALCULATING,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()

    comm = Commission(
        policy_id=policy.id, ev_id=ev1.id, month=9, year=2026,
        segment="P", achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.08"),
        monthly_actual=Decimal("80.00"), total_actual=Decimal("80.00"),
        is_final=False,
    )
    db.session.add(comm)
    db.session.commit()
    return admin, ev1, ev2, policy, appraisal, comm


def test_signoff_and_reopen_roundtrip(client, signoff_setup):
    from app.models import AuditLog

    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["ev_id"] == str(ev1.id)
    assert data["signoff"]["status"] == "DONE"
    assert data["signoff"]["signed_off_by_name"] == admin.name
    assert data["signoff"]["values_changed"] is False
    assert data["signoff_totals"] == {"total": 2, "done": 1,
                                      "all_done": False}
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 1

    # idempotente
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["signoff_totals"]["done"] == 1

    # reabrir
    resp = client.delete(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["signoff"]["status"] == "PENDING"
    assert data["signoff_totals"]["done"] == 0


def test_signoff_requires_admin(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}"

    resp = client.post(url, headers=_auth_header(ev1))
    assert resp.status_code == 403
    resp = client.delete(url, headers=_auth_header(ev1))
    assert resp.status_code == 403


def test_signoff_only_in_calculating(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "INVALID_STATE"


def test_signoff_out_of_scope_and_not_found(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{admin.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400          # ADMIN não é EV do escopo

    resp = client.post(
        f"/api/v1/appraisals/{uuid.uuid4()}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/nao-e-uuid",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_release_gate_via_api(client, signoff_setup):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/transition"

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 422
    assert "sem conferência" in resp.get_json()["error"]["message"]

    for ev in (ev1, ev2):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "VALIDATING"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py -v`
Expected: FAIL — os 4 primeiros testes com 404 (rota não existe); `test_release_gate_via_api` falha no sign-off (404).

- [ ] **Step 3: Implement the endpoints**

In `backend/app/api/v1/workflow.py`:

(a) Top of file — add to the imports:

```python
import uuid as uuid_lib
from datetime import datetime, timezone
```

and extend the `from app.models import (...)` list with `EvSignoff, SignoffStatus`.

(b) Add after the `resolve_contestation` route (before `recalculate`):

```python
# ── Conferência por EV (sign-off) — spec 2026-07-07 ──────────────────


def _serialize_signoff(row):
    if row is None:
        return None
    return {
        "status": row.status.value,
        "values_changed": bool(row.values_changed),
        "signed_off_by_name": row.signer.name if row.signer else None,
        "signed_off_at": (
            row.signed_off_at.isoformat() if row.signed_off_at else None
        ),
    }


def _signoff_request_guard(appraisal_id, ev_id):
    """Shared validation for the sign-off routes. Returns
    (appraisal, ev_uuid, error_response); error_response is None when ok."""
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return None, None, (jsonify({"error": {
            "code": "NOT_FOUND", "message": "Appraisal not found",
        }}), 404)
    if appraisal.status != AppraisalStatus.CALCULATING:
        return None, None, (jsonify({"error": {
            "code": "INVALID_STATE",
            "message": (
                "Conferência só é permitida em CALCULATING "
                f"(atual: {appraisal.status.value})"
            ),
        }}), 409)
    try:
        ev_uuid = uuid_lib.UUID(str(ev_id))
    except ValueError:
        return None, None, (jsonify({"error": {
            "code": "VALIDATION_ERROR", "message": "ev_id inválido",
        }}), 400)

    from app.modules.workflow.signoffs import signoff_scope_ev_ids
    scope = signoff_scope_ev_ids(appraisal.month, appraisal.year)
    if ev_uuid not in scope:
        return None, None, (jsonify({"error": {
            "code": "VALIDATION_ERROR",
            "message": "EV fora do escopo da conferência deste mês",
        }}), 400)
    return appraisal, ev_uuid, None


@workflow_bp.route("/<appraisal_id>/signoffs/<ev_id>", methods=["POST"])
@require_role(UserRole.ADMIN)
def signoff_ev(appraisal_id, ev_id):
    """RevOps marca a conferência de um EV como DONE. Idempotente."""
    appraisal, ev_uuid, error = _signoff_request_guard(appraisal_id, ev_id)
    if error:
        return error

    from app.modules.workflow.signoffs import (
        compute_ev_fingerprint, ensure_signoffs, signoff_totals,
    )
    ensure_signoffs(appraisal)
    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev_uuid,
    ).first()

    if row.status != SignoffStatus.DONE:
        row.status = SignoffStatus.DONE
        row.fingerprint = compute_ev_fingerprint(
            ev_uuid, appraisal.month, appraisal.year,
        )
        row.values_changed = False
        row.signed_off_by = g.current_user.id
        row.signed_off_at = datetime.now(timezone.utc)
        log_audit(
            "ev_signoffs", row.id, "UPDATE",
            old_values={"status": SignoffStatus.PENDING.value},
            new_values={"status": SignoffStatus.DONE.value,
                        "ev_id": str(ev_uuid)},
        )
        db.session.commit()

    return jsonify({"data": {
        "ev_id": str(ev_uuid),
        "signoff": _serialize_signoff(row),
        "signoff_totals": signoff_totals(appraisal),
    }})


@workflow_bp.route("/<appraisal_id>/signoffs/<ev_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def reopen_signoff(appraisal_id, ev_id):
    """RevOps reabre a conferência de um EV (DONE → PENDING). Idempotente."""
    appraisal, ev_uuid, error = _signoff_request_guard(appraisal_id, ev_id)
    if error:
        return error

    from app.modules.workflow.signoffs import ensure_signoffs, signoff_totals
    ensure_signoffs(appraisal)
    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev_uuid,
    ).first()

    if row.status == SignoffStatus.DONE:
        row.status = SignoffStatus.PENDING
        row.fingerprint = None
        row.values_changed = False
        row.signed_off_by = None
        row.signed_off_at = None
        log_audit(
            "ev_signoffs", row.id, "UPDATE",
            old_values={"status": SignoffStatus.DONE.value},
            new_values={"status": SignoffStatus.PENDING.value,
                        "ev_id": str(ev_uuid)},
        )
        db.session.commit()

    return jsonify({"data": {
        "ev_id": str(ev_uuid),
        "signoff": _serialize_signoff(row),
        "signoff_totals": signoff_totals(appraisal),
    }})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/workflow.py backend/tests/test_api/test_ev_signoffs.py
git commit -m "feat(api): endpoints de conferencia por EV (marcar/reabrir) com gate"
```

---

## Task 5: Payload do detail — signoff por EV, EVs sem movimento, totais, visão do líder

**Files:**
- Modify: `backend/app/api/v1/workflow.py` (`_build_appraisal_detail` ~linha 550, `_scope_detail_payload` ~linha 472)
- Test: `backend/tests/test_api/test_ev_signoffs.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api/test_ev_signoffs.py`:

```python
def test_detail_payload_includes_signoffs_and_zero_movement(
    client, signoff_setup,
):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )

    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["signoff_totals"] == {"total": 2, "done": 1,
                                      "all_done": False}

    by_id = {s["ev_id"]: s for s in data["ev_summary"]}
    # EV1 (com comissão): conferida
    assert by_id[str(ev1.id)]["signoff"]["status"] == "DONE"
    assert by_id[str(ev1.id)].get("no_movement") is None
    # EV2 (sem movimento): entra zerada na lista, pendente
    zero = by_id[str(ev2.id)]
    assert zero["no_movement"] is True
    assert zero["total_commission"] == 0.0
    assert zero["policies"] == []
    assert zero["signoff"]["status"] == "PENDING"
    # lista continua ordenada por nome
    names = [s["ev_name"] for s in data["ev_summary"]]
    assert names == sorted(names)


def test_lider_scoped_view_recomputes_signoff_totals(client, signoff_setup):
    from app.models import Team

    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    suffix = uuid.uuid4().hex[:8]
    lider = User(email=f"soa-lider-{suffix}@x", name="Líder",
                 role=UserRole.LIDER_VENDAS, active=True)
    db.session.add(lider)
    db.session.flush()
    team = Team(name=f"Time-{suffix}", leader_id=lider.id)
    db.session.add(team)
    db.session.flush()
    lider.team_id = team.id
    ev1.team_id = team.id           # só a EV1 é do time do líder
    db.session.commit()

    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(lider))
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert [s["ev_id"] for s in data["ev_summary"]] == [str(ev1.id)]
    assert data["signoff_totals"] == {"total": 1, "done": 0,
                                      "all_done": False}


def test_preview_has_no_signoff_fields(client, signoff_setup):
    """O preview roda _build_period_detail direto — sem conferência (spec)."""
    admin, *_ = signoff_setup
    resp = client.post("/api/v1/appraisals/preview",
                       json={"month": 9, "year": 2026},
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "signoff_totals" not in data
    assert all("signoff" not in s for s in data["ev_summary"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py -v -k "detail_payload or lider_scoped"`
Expected: FAIL — `KeyError: 'signoff_totals'` (payload ainda não carrega os campos).

- [ ] **Step 3: Implement the payload changes**

In `backend/app/api/v1/workflow.py`:

(a) In `_build_appraisal_detail`, add the sign-off attach after
`_attach_validation_status(appraisal, detail)`:

```python
def _build_appraisal_detail(appraisal):
    detail = _build_period_detail(appraisal.month, appraisal.year)
    _attach_validation_status(appraisal, detail)
    _attach_signoffs(appraisal, detail)
    _attach_lider_gate(appraisal, detail)
    return detail
```

(b) Add the new function right after `_attach_validation_status`:

```python
def _attach_signoffs(appraisal, detail):
    """Anota cada bloco de EV com sua conferência e injeta os EVs ativos sem
    movimento (escopo − quem tem comissão) como blocos zerados, para a lista
    da conferência cobrir o escopo inteiro. Só o detail da apuração — o
    preview (que chama _build_period_detail direto) não tem conferência."""
    from app.modules.workflow.signoffs import (
        signoff_scope_ev_ids, signoff_totals,
    )
    rows = {
        str(s.ev_id): s
        for s in EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
    }
    present = {s["ev_id"] for s in detail["ev_summary"]}
    scope = {
        str(x) for x in signoff_scope_ev_ids(appraisal.month, appraisal.year)
    }

    missing_ids = scope - present
    if missing_ids:
        quarter = (appraisal.month - 1) // 3 + 1
        users = User.query.filter(User.id.in_(list(missing_ids))).all()
        for u in users:
            ach = EvQuarterAchievement.query.filter_by(
                ev_id=u.id, quarter=quarter, year=appraisal.year,
            ).first()
            detail["ev_summary"].append({
                "ev_id": str(u.id),
                "ev_name": u.name,
                "ev_left_company": bool(u.left_company),
                "no_movement": True,
                "achievement_pct": (
                    float(ach.achievement_pct * 100)
                    if ach and ach.achievement_pct is not None else None
                ),
                "policies_count": 0,
                "nao_apuradas_count": 0,
                "nf_count": 0,
                "nf_liquido_total": 0.0,
                "subsidio_aplicado_total": 0.0,
                "base_comissionavel_total": 0.0,
                "total_commission": 0.0,
                "policies": [],
                "validation_status": _validation_counts([]),
            })
        detail["ev_summary"].sort(key=lambda s: s["ev_name"] or "")

    for ev in detail["ev_summary"]:
        ev["signoff"] = _serialize_signoff(rows.get(ev["ev_id"]))

    detail["signoff_totals"] = signoff_totals(appraisal)
```

(c) In `_scope_detail_payload`, after the `validation_totals` block (before
`return data`), add:

```python
    if "signoff_totals" in data:
        done = sum(
            1 for s in ev_summary
            if (s.get("signoff") or {}).get("status") == "DONE"
        )
        total = len(ev_summary)
        data["signoff_totals"] = {
            "total": total,
            "done": done,
            "all_done": done == total,
        }
```

- [ ] **Step 4: Run the file's tests**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py tests/test_api/test_appraisal_review.py -v`
Expected: all passed (o test_appraisal_review pode falhar se algum teste asserta o conjunto exato de EVs em `ev_summary` — nesse caso o teste deve filtrar `no_movement` antes da asserção; ajuste apontando o motivo no commit).

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/workflow.py backend/tests/test_api/
git commit -m "feat(api): detail carrega signoff por EV, EVs sem movimento e totais"
```

---

## Task 6: Recalculate integra o refresh + delete limpa signoffs + invalidação cliente-compartilhado

**Files:**
- Modify: `backend/app/api/v1/workflow.py` (rota `recalculate` ~linha 349; rota `delete_appraisal` ~linha 172)
- Test: `backend/tests/test_api/test_ev_signoffs.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api/test_ev_signoffs.py`:

```python
def test_recalculate_invalidates_changed_signoffs(client, signoff_setup):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    for ev in (ev1, ev2):
        client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )

    # O recálculo real apaga a Commission da EV1 (não há NF que a recrie),
    # então o fingerprint dela muda; a EV2 segue vazia (mantida).
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["signoffs"]["invalidated"] == [ev1.name]
    assert body["signoffs"]["kept"] == 1

    by_id = {s["ev_id"]: s for s in body["data"]["ev_summary"]}
    assert by_id[str(ev1.id)]["signoff"]["status"] == "PENDING"
    assert by_id[str(ev1.id)]["signoff"]["values_changed"] is True
    assert by_id[str(ev2.id)]["signoff"]["status"] == "DONE"

    # Re-conferir limpa o aviso de "valores mudaram" (spec, teste 3d).
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    signoff = resp.get_json()["data"]["signoff"]
    assert signoff["status"] == "DONE"
    assert signoff["values_changed"] is False


def test_shared_client_recalc_invalidates_both_evs(client, db_session):
    """Duas EVs, duas apólices do MESMO cliente. Um Perk novo no cliente
    muda a base das duas no recálculo → as duas conferências caem. É o
    cenário que justifica o recálculo global (spec: 'Por que recálculo
    global e não escopado por EV')."""
    from app.models import (
        CommissionPctTable, EvQuarterAchievement, FinancialImport,
        ImportBatch, Perk,
    )

    suffix = uuid.uuid4().hex[:8]
    for seg, mn, mx, pct in [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "99.9999", "0.10"),
    ]:
        db.session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(mn), achievement_max=Decimal(mx),
            commission_pct=Decimal(pct), valid_from=date.today(),
        ))
    admin = User(email=f"shc-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    eva = User(email=f"shc-eva-{suffix}@x", name=f"Ana {suffix}",
               role=UserRole.EV, active=True)
    evb = User(email=f"shc-evb-{suffix}@x", name=f"Bia {suffix}",
               role=UserRole.EV, active=True)
    db.session.add_all([admin, eva, evb])
    db.session.flush()

    shared_client = Client.find_or_create(f"SharedCo-{suffix}")
    db.session.flush()
    for ev, tag, produto in ((eva, "A", BenefitType.SAUDE),
                             (evb, "B", BenefitType.ODONTO)):
        db.session.add(Policy(
            hubspot_ticket_id=f"SHC-{tag}-{suffix}",
            numero_apolice=f"AP-SHC-{tag}-{suffix}",
            ev_id=ev.id, client_id=shared_client.id,
            segment=Segment.P, benefit_type=produto,
            partner_operator="Amil", closed_date=date(2026, 7, 1),
        ))
        db.session.add(EvQuarterAchievement(
            ev_id=ev.id, quarter=3, year=2026,
            achievement_pct=Decimal("0.75"),
        ))
    db.session.flush()

    batch = ImportBatch(filename="shc.xlsx", uploaded_by=admin.id,
                        status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    for tag, produto in (("A", "Saúde"), ("B", "Odonto")):
        db.session.add(FinancialImport(
            import_batch_id=batch.id, month=9, year=2026,
            nf_valor_liquido=Decimal("1000.00"),
            nf_mes_recebimento="2026-09",
            cliente_mae=shared_client.name,
            operadora="Amil", produto=produto,
            numero_apolice=f"AP-SHC-{tag}-{suffix}",
            tipo_receita="Comissão", status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 9, 10),
            match_status="UNMATCHED",
        ))
    db.session.commit()

    # DRAFT → CALCULATING roda o calculator de verdade e cria os signoffs
    resp = client.post("/api/v1/appraisals", json={"month": 9, "year": 2026},
                       headers=_auth_header(admin))
    assert resp.status_code == 201
    appraisal_id = resp.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/appraisals/{appraisal_id}/transition",
                       json={"to": "CALCULATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 200

    for ev in (eva, evb):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal_id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    # Perk novo no cliente compartilhado → recálculo muda a base das DUAS
    db.session.add(Perk(client_id=shared_client.id, month=9, year=2026,
                        amount=Decimal("500.00"),
                        import_batch_id=batch.id))
    db.session.commit()

    resp = client.post(f"/api/v1/appraisals/{appraisal_id}/recalculate",
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    invalidated = resp.get_json()["signoffs"]["invalidated"]
    assert sorted(invalidated) == sorted([eva.name, evb.name])


def test_delete_appraisal_removes_signoffs(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert EvSignoff.query.filter_by(appraisal_id=appraisal.id).count() > 0

    resp = client.delete(f"/api/v1/appraisals/{appraisal.id}",
                         headers=_auth_header(admin))
    assert resp.status_code == 200
    assert EvSignoff.query.filter_by(appraisal_id=appraisal.id).count() == 0
```

> Nota: `Perk.import_batch_id` é NOT NULL (ver `app/models/perk.py`) — por
> isso o teste reaproveita o `batch` criado acima.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py -v -k "recalculate or shared_client or delete_appraisal"`
Expected: FAIL — `KeyError: 'signoffs'` nos dois primeiros (resposta do recalculate não tem o campo); o delete falha na asserção de contagem 0 (FK impede ou linhas sobram).

- [ ] **Step 3: Implement**

In `backend/app/api/v1/workflow.py`:

(a) In the `recalculate` route, integrate the refresh and the response field:

```python
    from app.modules.commissions.calculator import (
        run_monthly_appraisal, MissingAchievementsError,
    )
    from app.modules.workflow.signoffs import refresh_signoffs_after_recalc
    try:
        # Missing achievements don't block — they fall back to 0% and surface
        # as a warning in the detail payload (same as the preview).
        run_monthly_appraisal(
            appraisal.month, appraisal.year, validate_achievements=False
        )
        signoffs_result = refresh_signoffs_after_recalc(appraisal)
        db.session.commit()
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({
            "error": {
                "code": "MISSING_ACHIEVEMENTS",
                "message": str(e),
                "missing": e.missing,
            },
        }), 422

    return jsonify({
        "data": _serialize_appraisal(appraisal, detail=True),
        "signoffs": signoffs_result,
    })
```

(b) In `delete_appraisal`, add next to the `EvValidation` cleanup:

```python
    # Drop the EV validations first — they FK appraisal_id with no cascade, so
    # the appraisal can't be deleted while any exist (i.e. once released).
    EvValidation.query.filter_by(appraisal_id=appraisal.id).delete()
    EvSignoff.query.filter_by(appraisal_id=appraisal.id).delete()
```

- [ ] **Step 4: Run the whole API test file**

Run: `cd backend; python -m pytest tests/test_api/test_ev_signoffs.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/workflow.py backend/tests/test_api/test_ev_signoffs.py
git commit -m "feat(api): recalculate reporta conferencias invalidadas; delete limpa signoffs"
```

---

## Task 7: Contadores de conferência no agregador do ciclo

**Files:**
- Modify: `backend/app/modules/workflow/cycle_aggregator.py` (`_ev_apuracao_status`, linhas 49–74)
- Test: `backend/tests/test_modules/test_workflow/test_signoffs.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_modules/test_workflow/test_signoffs.py`:

```python
def test_cycle_aggregator_exposes_signoff_counters_in_calculating(db_session):
    from app.modules.workflow.cycle_aggregator import _ev_apuracao_status

    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin, month=11)
    ensure_signoffs(appraisal)

    status = _ev_apuracao_status(11, 2026)
    assert status["status"] == "CALCULATING"
    assert status["signoffs_total"] == 1
    assert status["signoffs_done"] == 0

    # Fora de CALCULATING os contadores somem (histórico não recomputado).
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.flush()
    status = _ev_apuracao_status(11, 2026)
    assert "signoffs_total" not in status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v -k cycle_aggregator`
Expected: FAIL — `KeyError: 'signoffs_total'`

- [ ] **Step 3: Implement**

In `backend/app/modules/workflow/cycle_aggregator.py`, change the return of
`_ev_apuracao_status` (the non-None branch):

```python
    payload = {
        "status": appraisal.status.value,
        "appraisal_id": str(appraisal.id),
        "validations_total": len(validations),
        "validations_done": done,
        "has_contestation": bool(getattr(appraisal, "has_contestation", False)),
    }
    if appraisal.status == AppraisalStatus.CALCULATING:
        # Progresso da conferência por EV — só faz sentido enquanto o
        # RevOps está conferindo; depois o escopo recomputado viraria
        # história reescrita (mesmo racional do expected em ciclos LOCKED).
        from app.modules.workflow.signoffs import signoff_totals
        totals = signoff_totals(appraisal)
        payload["signoffs_total"] = totals["total"]
        payload["signoffs_done"] = totals["done"]
    return payload
```

- [ ] **Step 4: Run tests**

Run: `cd backend; python -m pytest tests/test_modules/test_workflow/test_signoffs.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```powershell
git add backend/app/modules/workflow/cycle_aggregator.py backend/tests/test_modules/test_workflow/test_signoffs.py
git commit -m "feat(cycle): trilho expoe progresso da conferencia no CALCULATING"
```

---

## Task 8: Frontend — endpoint + eventos re-frame

**Files:**
- Modify: `frontend/src/app/api/endpoints.cljs` (bloco "Appraisals", ~linha 24)
- Modify: `frontend/src/app/views/revops/events.cljs` (`:revops/recalculated` ~linha 365; `:revops/release-to-validation` ~linha 371; eventos novos ao lado)

- [ ] **Step 1: Add the endpoint helper**

In `frontend/src/app/api/endpoints.cljs`, add after `appraisal-recalculate`:

```clojure
(def appraisal-signoff
  (fn [id ev-id] (str "/appraisals/" id "/signoffs/" ev-id)))
```

- [ ] **Step 2: Add sign-off events + upgrade the recalculated toast**

In `frontend/src/app/views/revops/events.cljs`:

(a) Replace the `:revops/recalculated` handler (keeps refetch, adds the
invalidated-signoffs message):

```clojure
(rf/reg-event-fx
 :revops/recalculated
 (fn [_ [_ id resp]]
   (let [invalidated (get-in resp [:signoffs :invalidated])
         msg (if (seq invalidated)
               (str "Recalculado. Conferências invalidadas: "
                    (clojure.string/join ", " invalidated))
               "Recalculado!")]
     {:dispatch-n [[:revops/fetch-appraisal-detail id]
                   [:ui/show-toast {:type :success :message msg}]]})))
```

(b) Replace `:revops/release-to-validation`'s `:on-failure` so the 422 do
gate appears as a toast (today it fails silently into
`:revops/appraisals-error`):

```clojure
(rf/reg-event-fx
 :revops/release-to-validation
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (str "/appraisals/" id "/transition")
           :body       {:to "VALIDATING"}
           :on-success [:revops/validation-released]
           :on-failure [:revops/release-blocked]}}))

(rf/reg-event-fx
 :revops/release-blocked
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Não foi possível liberar para validação.")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))
```

(c) Add the sign-off events right after the `:revops/release-blocked` block:

```clojure
;; ---- Conferência por EV (sign-off) ----

(rf/reg-event-fx
 :revops/signoff-ev
 (fn [_ [_ appraisal-id ev-id]]
   {:http {:method     :post
           :url        (ep/appraisal-signoff appraisal-id ev-id)
           :on-success [:revops/signoff-updated appraisal-id]
           :on-failure [:revops/signoff-error]}}))

(rf/reg-event-fx
 :revops/reopen-signoff
 (fn [_ [_ appraisal-id ev-id]]
   {:http {:method     :delete
           :url        (ep/appraisal-signoff appraisal-id ev-id)
           :on-success [:revops/signoff-updated appraisal-id]
           :on-failure [:revops/signoff-error]}}))

(rf/reg-event-db
 :revops/signoff-updated
 ;; Merge do delta (signoff do EV + totais) no item da lista — sem refetch
 ;; do detail inteiro a cada clique da esteira de conferência.
 (fn [db [_ appraisal-id response]]
   (let [{:keys [ev_id signoff signoff_totals]} (:data response)]
     (update-in db [:appraisal :list]
                (fn [items]
                  (map (fn [a]
                         (if (= (:id a) appraisal-id)
                           (-> a
                               (assoc :signoff_totals signoff_totals)
                               (update :ev_summary
                                       (fn [evs]
                                         (mapv #(if (= (:ev_id %) ev_id)
                                                  (assoc % :signoff signoff)
                                                  %)
                                               (or evs [])))))
                           a))
                       (or items [])))))))

(rf/reg-event-fx
 :revops/signoff-error
 (fn [_ [_ resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao atualizar a conferência.")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))
```

- [ ] **Step 3: Lint check**

Run: `cd frontend; npx clj-kondo --lint src/`
Expected: sem erros novos (warnings pré-existentes podem aparecer; compare com `git stash` se em dúvida).

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/app/api/endpoints.cljs frontend/src/app/views/revops/events.cljs
git commit -m "feat(frontend): eventos de conferencia por EV + toast do gate"
```

---

## Task 9: Frontend — funções puras da conferência (TDD com karma)

**Files:**
- Modify: `frontend/src/app/views/revops/appraisal_review.cljs` (funções novas, públicas, logo após `validation-ev-badge`, ~linha 123)
- Test: `frontend/test/app/views/revops/appraisal_review_test.cljs` (create)

- [ ] **Step 1: Write the failing tests**

Create `frontend/test/app/views/revops/appraisal_review_test.cljs`:

```clojure
(ns app.views.revops.appraisal-review-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.appraisal-review :as ar]))

(deftest signoff-status-test
  (testing "nil quando o EV não tem bloco de signoff (apuração antiga)"
    (is (nil? (ar/signoff-status {}))))
  (testing "done / changed / pending"
    (is (= :done (ar/signoff-status {:signoff {:status "DONE"}})))
    (is (= :changed (ar/signoff-status
                     {:signoff {:status "PENDING" :values_changed true}})))
    (is (= :pending (ar/signoff-status
                     {:signoff {:status "PENDING" :values_changed false}})))))

(deftest signoff-progress-test
  (is (= {:total 3 :done 1 :all-done? false}
         (ar/signoff-progress
          {:signoff_totals {:total 3 :done 1 :all_done false}})))
  (is (= {:total 0 :done 0 :all-done? false}
         (ar/signoff-progress {}))))

(deftest conference-active?-test
  (testing "ativa só em CALCULATING com totais presentes"
    (is (ar/conference-active?
         {:status "CALCULATING" :signoff_totals {:total 2 :done 0}}))
    (is (not (ar/conference-active?
              {:status "VALIDATING" :signoff_totals {:total 2 :done 2}})))
    (is (not (ar/conference-active? {:status "CALCULATING"})))))

(deftest sort-evs-for-conference-test
  (testing "pendentes (incl. valores-mudaram) primeiro, alfabético dentro"
    (is (= ["Bia" "Caio" "Ana"]
           (map :ev_name
                (ar/sort-evs-for-conference
                 [{:ev_name "Ana" :signoff {:status "DONE"}}
                  {:ev_name "Caio" :signoff {:status "PENDING"
                                             :values_changed true}}
                  {:ev_name "Bia" :signoff {:status "PENDING"}}]))))))

(deftest filter-evs-by-signoff-test
  (let [evs [{:ev_name "Ana" :signoff {:status "DONE"}}
             {:ev_name "Bia" :signoff {:status "PENDING"}}]]
    (is (= ["Bia"] (map :ev_name (ar/filter-evs-by-signoff evs :pendentes))))
    (is (= ["Ana"] (map :ev_name (ar/filter-evs-by-signoff evs :conferidos))))
    (is (= ["Ana" "Bia"] (map :ev_name (ar/filter-evs-by-signoff evs :todos))))))

(deftest release-blocked?-test
  (testing "bloqueia em CALCULATING com pendências"
    (is (ar/release-blocked?
         {:status "CALCULATING" :signoff_totals {:total 3 :done 1}})))
  (testing "libera com 100% ou fora do CALCULATING ou sem dados"
    (is (not (ar/release-blocked?
              {:status "CALCULATING" :signoff_totals {:total 3 :done 3}})))
    (is (not (ar/release-blocked?
              {:status "REVOPS_REVIEW" :signoff_totals {:total 3 :done 1}})))
    (is (not (ar/release-blocked? {:status "CALCULATING"})))))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npm test`
Expected: FAIL na compilação — `var: app.views.revops.appraisal-review/signoff-status is not defined` (e as demais).

- [ ] **Step 3: Implement the pure helpers**

In `frontend/src/app/views/revops/appraisal_review.cljs`, add after
`validation-ev-badge` (before `lider-gate-callout`). **Públicas (`defn`), são
a superfície testada:**

```clojure
;; ── Conferência por EV (sign-off) — helpers puros ─────────

(defn signoff-status
  "Estado efetivo da conferência de um bloco de EV:
   :done / :changed / :pending / nil (payload sem conferência)."
  [ev]
  (let [s (:signoff ev)]
    (cond
      (nil? s)                nil
      (= "DONE" (:status s))  :done
      (:values_changed s)     :changed
      :else                   :pending)))

(defn signoff-progress
  "{:total n :done m :all-done? bool} a partir do signoff_totals."
  [appraisal]
  (let [{:keys [total done all_done]} (:signoff_totals appraisal)]
    {:total (or total 0) :done (or done 0) :all-done? (boolean all_done)}))

(defn conference-active?
  "A esteira de conferência só aparece durante o CALCULATING (depois vira
   histórico read-only nos badges)."
  [appraisal]
  (and (= "CALCULATING" (:status appraisal))
       (some? (:signoff_totals appraisal))))

(defn sort-evs-for-conference
  "Pendentes (incl. ⚠ valores mudaram) primeiro; alfabético dentro do grupo."
  [evs]
  (sort-by (fn [ev] [(if (= :done (signoff-status ev)) 1 0)
                     (or (:ev_name ev) "")])
           evs))

(defn filter-evs-by-signoff [evs filter-k]
  (case filter-k
    :pendentes  (remove #(= :done (signoff-status %)) evs)
    :conferidos (filter #(= :done (signoff-status %)) evs)
    evs))

(defn release-blocked?
  "true quando o Liberar para EVs deve ficar desabilitado: CALCULATING com
   conferências pendentes. O servidor também bloqueia (defesa em camadas)."
  [appraisal]
  (let [{:keys [total done]} (signoff-progress appraisal)]
    (and (= "CALCULATING" (:status appraisal))
         (pos? total)
         (< done total))))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npm test`
Expected: `Executed N of N SUCCESS` (todos os testes existentes + os 6 novos).

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/app/views/revops/appraisal_review.cljs frontend/test/app/views/revops/appraisal_review_test.cljs
git commit -m "feat(frontend): helpers puros da conferencia por EV + testes karma"
```

---

## Task 10: Frontend — UI da esteira de conferência

**Files:**
- Modify: `frontend/src/app/views/revops/appraisal_review.cljs` (banda, badge, ev-row ~linha 317, por-ev-tab ~linha 381, header da página ~linha 574)
- Modify: `frontend/src/app/views/revops/monthly_cycle.cljs` (`step-summary`, ~linha 300)
- Modify: `frontend/resources/public/css/pipo-design.css` (classes novas no fim do arquivo)

- [ ] **Step 1: Badge + banda de progresso**

In `appraisal_review.cljs`, add after the pure helpers from Task 9:

```clojure
(defn- signoff-badge [ev]
  (let [s (:signoff ev)]
    (case (signoff-status ev)
      :done    [:span.badge.badge-approved
                (str "✓ conferido"
                     (when-let [n (:signed_off_by_name s)]
                       (str " · " n)))]
      :changed [:span.badge.badge-review "⚠ valores mudaram"]
      :pending [:span.badge.badge-pending "⏳ conferência pendente"]
      nil)))

(defn- signoff-band
  "Progresso da conferência + filtro Pendentes/Conferidos/Todos."
  [appraisal signoff-filter]
  (let [{:keys [total done]} (signoff-progress appraisal)
        pct (if (pos? total) (js/Math.round (* 100 (/ done total))) 0)]
    [:div.card.appraisal-signoff-band
     [:div.appraisal-signoff-head
      [:div
       [:strong "Conferência EV por EV"]
       [:div.card-sub
        "Confira e feche cada EV; a liberação para validação abre com 100%."]]
      [:span.appraisal-signoff-count
       (str done " de " total " EVs conferidos")]]
     [:div.appraisal-signoff-progress
      [:div.appraisal-signoff-progress-fill {:style {:width (str pct "%")}}]]
     [:div.filter-row {:role "group" :aria-label "Filtro de conferência"}
      (for [[k label] [[:pendentes "Pendentes"]
                       [:conferidos "Conferidos"]
                       [:todos "Todos"]]]
        ^{:key k}
        [:button {:type "button"
                  :class (str "chip" (when (= k @signoff-filter) " active"))
                  :aria-pressed (str (= k @signoff-filter))
                  :on-click #(reset! signoff-filter k)}
         label])]]))
```

- [ ] **Step 2: ev-row ganha badge, botões e estado sem-movimento**

In `appraisal_review.cljs`, `ev-row` (form-2 component, ~linha 317):

(a) Change the inner fn signature from
`(fn [ev tipo-filter operadora-filter]` to
`(fn [ev tipo-filter operadora-filter {:keys [appraisal-id conference? admin?]}]`.

(b) In the header `[:div.name (:ev_name ev) ...]`, add `[signoff-badge ev]`
right after `[validation-ev-badge (:validation_status ev)]`.

(c) Replace the meta line so zero-movement EVs read clearly. Change:

```clojure
           [:div.appraisal-ev-meta
            (str (:policies_count ev) " apuradas · "
                 (when (pos? nao-count) (str nao-count " não apuradas · "))
                 (:nf_count ev) " NFs · atingimento "
                 (or (fmt-pct (:achievement_pct ev)) "·") "%")]
```

to:

```clojure
           [:div.appraisal-ev-meta
            (if (:no_movement ev)
              "sem movimento no mês"
              (str (:policies_count ev) " apuradas · "
                   (when (pos? nao-count) (str nao-count " não apuradas · "))
                   (:nf_count ev) " NFs · atingimento "
                   (or (fmt-pct (:achievement_pct ev)) "·") "%"))]
```

(d) At the top of the expanded panel (`(when @open? [:div.appraisal-ev-detail ...`),
insert the action bar before the filter chips:

```clojure
            (when (and conference? admin?)
              [:div.appraisal-signoff-actions
               (if (= :done (signoff-status ev))
                 [:button.btn.btn-secondary.btn-sm
                  {:on-click #(rf/dispatch [:revops/reopen-signoff
                                            appraisal-id (:ev_id ev)])}
                  "Reabrir conferência"]
                 [:button.btn.btn-primary.btn-sm
                  {:on-click #(rf/dispatch [:revops/signoff-ev
                                            appraisal-id (:ev_id ev)])}
                  "Marcar como conferido"])
               [:button.btn.btn-secondary.btn-sm
                {:on-click #(rf/dispatch [:revops/recalculate-appraisal
                                          appraisal-id])}
                [layout/icon "refresh" {:width 12 :height 12}]
                " Recalcular"]])
```

(e) Still in the expanded panel, wrap the chips+policies in a no-movement
check. Replace the block from `[:div.filter-row.appraisal-subfilter-row ...`
through the policies `(for ...)` with:

```clojure
            (if (:no_movement ev)
              [:div.appraisal-empty-panel
               "Sem movimento no mês — nenhuma NF e nenhuma comissão para este EV."]
              [:<>
               [:div.filter-row.appraisal-subfilter-row
                {:role "group" :aria-label "Filtro de apuração"}
                (for [[k label cnt] [[:apuradas "Apuradas" (count apuradas)]
                                     [:nao-apuradas "Não apuradas" (count nao-apuradas)]
                                     [:todas "Todas" (count base)]]]
                  ^{:key k}
                  [:button {:type "button"
                            :class (str "chip" (when (= k @apurada-filter) " active"))
                            :aria-pressed (str (= k @apurada-filter))
                            :on-click #(reset! apurada-filter k)}
                   (str label " (" cnt ")")])]
               (if (empty? visible)
                 [:div.appraisal-empty-panel
                  "Nenhuma apólice neste filtro"]
                 (for [p visible]
                   ^{:key (:policy_id p)} [policy-block p]))])
```

- [ ] **Step 3: por-ev-tab orquestra a esteira**

Replace the whole `por-ev-tab` component with:

```clojure
(defn por-ev-tab []
  (let [tipo-filter    (r/atom "Todos")
        op-filter      (r/atom "Todas")
        signoff-filter (r/atom :todos)]
    (fn [appraisal ev-summary user]
      (let [conference? (conference-active? appraisal)
            admin?      (= "ADMIN" (:role user))
            evs         (cond->> ev-summary
                          conference? sort-evs-for-conference
                          conference? (#(filter-evs-by-signoff
                                         % @signoff-filter)))
            all-ops (->> ev-summary
                         (mapcat :policies)
                         (map :operadora)
                         (remove nil?)
                         distinct sort)]
        [:div
         (when conference?
           [signoff-band appraisal signoff-filter])
         [:div.appraisal-filter-band
          [:div.appraisal-filter-group
           [:div.appraisal-filter-label "receita"]
           [:div.filter-row.appraisal-filter-row
            {:role "group" :aria-label "Filtro por tipo de receita"}
            (for [t ["Todos" "Comissão" "Fee por Vida" "Premiação" "Patrocínio - Eventos" "Agenciamento"]]
              ^{:key t}
              [:button {:type "button"
                        :class (str "chip" (when (= t @tipo-filter) " active"))
                        :aria-pressed (str (= t @tipo-filter))
                        :on-click #(reset! tipo-filter t)}
               t])]]
          [:div.appraisal-filter-group.-wide
           [:div.appraisal-filter-label "operadora"]
           [:div.filter-row.appraisal-filter-row
            {:role "group" :aria-label "Filtro por operadora"}
            [:button {:type "button"
                      :class (str "chip" (when (= "Todas" @op-filter) " active"))
                      :aria-pressed (str (= "Todas" @op-filter))
                      :on-click #(reset! op-filter "Todas")} "Todas"]
            (for [o all-ops]
              ^{:key o}
              [:button {:type "button"
                        :class (str "chip" (when (= o @op-filter) " active"))
                        :aria-pressed (str (= o @op-filter))
                        :on-click #(reset! op-filter o)}
               o])]]]
         (if (empty? evs)
           [:div.appraisal-empty-panel.-large
            (if conference?
              "Nenhum EV neste filtro de conferência"
              "Nenhum EV com comissão calculada")]
           [:div.appraisal-ev-list
            (for [ev evs]
              ^{:key (:ev_id ev)}
              [ev-row ev @tipo-filter @op-filter
               {:appraisal-id (:id appraisal)
                :conference?  conference?
                :admin?       admin?}])])]))))
```

And update the call site in `appraisal-review-page` from
`:por-ev [por-ev-tab ev-summary]` to:

```clojure
             :por-ev    [por-ev-tab appraisal ev-summary user]
```

- [ ] **Step 4: Gate no botão "Liberar para EVs"**

In `appraisal-review-page`'s `:header-actions`, replace the
`(= st "CALCULATING")` branch:

```clojure
              (= st "CALCULATING")
              (conj (let [{:keys [total done]} (signoff-progress appraisal)
                          blocked? (release-blocked? appraisal)]
                      [:button.btn.btn-primary
                       {:disabled blocked?
                        :title (when blocked?
                                 (str "Faltam " (- total done)
                                      " conferência(s) para liberar."))
                        :on-click #(when-not blocked?
                                     (rf/dispatch
                                      [:revops/release-to-validation
                                       appraisal-id]))}
                       [layout/icon "check" {:width 14 :height 14}]
                       (if blocked?
                         (str "Liberar para EVs (faltam " (- total done) ")")
                         "Liberar para EVs")]))
```

- [ ] **Step 5: Trilho do ciclo mostra o progresso da conferência**

In `frontend/src/app/views/revops/monthly_cycle.cljs`, `step-summary` —
duas edições pontuais, o resto da função fica como está:

(a) Replace the destructuring line

```clojure
  (let [{:keys [validations_total validations_done rows final expected
                month has_contestation]} component
```

with

```clojure
  (let [{:keys [validations_total validations_done rows final expected
                month has_contestation signoffs_total signoffs_done]} component
```

(b) Insert a new first branch in the `cond`, immediately before the existing
`(and validations_total (pos? validations_total))` branch:

```clojure
        text (cond
               (and signoffs_total (pos? signoffs_total))
               (str signoffs_done " / " signoffs_total " EVs conferidos")

               (and validations_total (pos? validations_total))
```

(o backend só manda `signoffs_total` durante o CALCULATING, então o branch
novo nunca esconde o contador de validações — eles existem em estados
diferentes).

- [ ] **Step 6: CSS**

Append to `frontend/resources/public/css/pipo-design.css`:

```css
/* ── Conferência EV por EV (sign-off band) ───────────────── */
.appraisal-signoff-band {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 20px;
  margin-bottom: 14px;
}
.appraisal-signoff-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.appraisal-signoff-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-3);
  white-space: nowrap;
}
.appraisal-signoff-progress {
  height: 6px;
  border-radius: 3px;
  background: var(--bg-3, #222);
  overflow: hidden;
}
.appraisal-signoff-progress-fill {
  height: 100%;
  background: var(--accent, #4f7cff);
  transition: width 0.2s ease;
}
.appraisal-signoff-actions {
  display: flex;
  gap: 8px;
  margin: 2px 0 10px;
}
```

- [ ] **Step 7: Compile + tests + lint**

Run: `cd frontend; npm test; npx clj-kondo --lint src/`
Expected: karma SUCCESS; sem erros novos de lint (unused-binding etc.).

- [ ] **Step 8: Verificação manual no preview (obrigatória — mudança visual)**

Suba o stack de dev (Flask :5000 + shadow :8080, ver skill/launch config do
repo) e verifique na página de revisão de uma apuração em CALCULATING:
banda de progresso aparece; marcar/reabrir atualiza badge + contador sem
reload; EV sem movimento listado zerado; botão "Liberar para EVs"
desabilitado com contador; recalcular mostra o toast (com invalidadas quando
houver); em VALIDATING+ os badges ficam read-only e a banda some.

- [ ] **Step 9: Commit**

```powershell
git add frontend/src/app/views/revops/appraisal_review.cljs frontend/src/app/views/revops/monthly_cycle.cljs frontend/resources/public/css/pipo-design.css
git commit -m "feat(frontend): esteira de conferencia EV por EV na revisao da apuracao"
```

---

## Task 11: Suites completas + regressões

**Files:** nenhum novo — rodada final.

- [ ] **Step 1: Backend completo**

Run: `cd backend; python -m pytest tests -v`
Expected: all passed. Atenção especial a `test_api/test_appraisal_review.py`,
`test_api/test_validations*`, `test_modules/test_workflow/*` e qualquer teste
de monthly cycle que faça transição CALCULATING → VALIDATING (ajuste com o
snippet de sign-off do Task 3 Step 5 se necessário).

- [ ] **Step 2: Frontend completo**

Run: `cd frontend; npm test`
Expected: `Executed N of N SUCCESS`.

- [ ] **Step 3: Commit final (se houve ajustes de regressão)**

```powershell
git add -A backend/tests frontend/test
git commit -m "test: regressoes da conferencia por EV nas suites existentes"
```

---

## Notas de execução

- **Ordem importa**: Tasks 1→7 (backend) antes de 8→10 (frontend); Task 11 fecha.
- **Working tree sujo**: o repositório tem mudanças não relacionadas em
  `financial.py`, `perk_parser.py`, `financial_upload.cljs` etc. — **não**
  inclua esses arquivos nos commits desta feature (`git add` sempre com
  caminhos explícitos, nunca `git add -A` fora do Task 11 restrito a tests).
- **Fora de escopo** (spec): validações dos EVs, Slack, preview, recálculo
  escopado, página nova. Não toque.
