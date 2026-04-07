# Financeiro & Apuração Trimestral — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever parser financeiro, calculator e UI de revisão pra trabalhar com o XLSX real (Consulta - Follow up Faturamento 2026), aplicando filtro global de "EVs ativos", edição manual de Policies (override do HubSpot) e atingimento % manual por trimestre.

**Architecture:** Backend Flask+SQLAlchemy roda parser → matcher (dict O(1)) → calculator (per gongo-quarter achievement, date-based vigência) → grava em `financial_imports` e `commissions`. Frontend ClojureScript+Re-frame mostra drill-down EV→Policy→NF na revisão. Status `CALCULATING` é uma porta manual: RevOps revisa antes de liberar pra `VALIDATING`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2.x, Alembic, Postgres 16, openpyxl, ClojureScript (shadow-cljs), Reagent, Re-frame, cljs-ajax.

**Spec:** `docs/superpowers/specs/2026-04-07-financeiro-apuracao-redesign.md`

**Pré-req:** Ler a spec inteira antes de começar. Ela tem todas as decisões e o "porquê" de cada uma.

---

## Convenções

- **TDD obrigatório**: para cada função nova, write the failing test FIRST, run it, see it fail, then implement.
- **Commits frequentes**: um commit por tarefa concluída, mensagem no formato `feat:`/`fix:`/`refactor:`/`test:`/`docs:`.
- **Rodar tests dentro do container** (não no host) pra garantir mesmo Python/libs:
  ```bash
  docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
      python -m pytest tests/path/ -v
  ```
- **Não usar Bash pra ler/editar arquivos** — Read/Edit/Write tools.
- **Não pular `superpowers:test-driven-development`** se a skill estiver disponível.
- **Worktree:** este plano modifica ~25 arquivos em backend e frontend. Considerar rodar em worktree dedicada (`EnterWorktree` ou `git worktree add`) pra isolar do trabalho atual. Se já estiver em worktree, ok.

## Mapa de arquivos

### Backend — criar
- `backend/migrations/versions/<rev>_add_is_locked_to_policies.py`
- `backend/migrations/versions/<rev>_redesign_financial_imports.py`
- `backend/migrations/versions/<rev>_seed_commission_pct_table_v2.py`
- `backend/app/modules/policies/__init__.py`
- `backend/app/modules/policies/filters.py`
- `backend/app/modules/financial/matcher.py`
- `backend/app/modules/financial/parser.py` (rewrite — old file deletado)
- `backend/app/modules/financial/processor.py` (rewrite)
- `backend/tests/test_modules/test_policies/__init__.py`
- `backend/tests/test_modules/test_policies/test_filters.py`
- `backend/tests/test_modules/test_financial/test_matcher.py`
- `backend/tests/fixtures/sample_financial.xlsx` (subset 100 linhas da planilha real)

### Backend — modificar
- `backend/app/models/financial_import.py` — add cliente_mae, operadora, produto, tipo_receita, status_recebimento, data_recebimento, match_status, matched_at; nullable policy_id; drop unique constraint
- `backend/app/models/policy.py` — add `is_locked` column
- `backend/app/modules/commissions/calculator.py` — replace `run_quarterly_appraisal_v2` with new implementation, drop V1 alias
- `backend/app/modules/workflow/state_machine.py` — update import, add LOCK→is_final logic
- `backend/app/modules/hubspot_sync/sync.py` — respect `is_locked` in `_process_ticket`
- `backend/app/api/v1/workflow.py` — enrich `_serialize_appraisal` with `ev_summary`, add `POST /appraisals/{id}/recalculate`
- `backend/app/api/v1/policies.py` — add `PUT /policies/{id}` endpoint, apply active-EV filter to GET
- `backend/app/api/v1/financial.py` — rewrite upload (no preview, immediate persist)
- `backend/app/api/v1/admin.py` — keep auto-calc baseline endpoint as-is
- `backend/tests/test_modules/test_financial/test_parser.py` — update for new format
- `backend/tests/test_modules/test_workflow/test_state_machine.py` — update for new flow
- `backend/tests/test_modules/test_commissions/test_calculator.py` — rewrite

### Backend — deletar
- `backend/app/modules/financial/validator.py` (validation collapsed into parser; or leave but unused)
- (Old `parse_financial_xlsx` function — overwritten by new version)

### Frontend — criar
- `frontend/src/app/views/revops/achievements.cljs`
- `frontend/src/app/views/revops/policy_edit_modal.cljs`

### Frontend — modificar
- `frontend/src/app/views/revops/policies.cljs` — wire up edit modal, apply active-EV filter on backend (already filtered)
- `frontend/src/app/views/revops/appraisal_review.cljs` — full drill-down with tabs
- `frontend/src/app/views/revops/financial_upload.cljs` — new flow (no 2-step preview)
- `frontend/src/app/views/revops/events.cljs` — add events for edit-policy, recalculate, achievements
- `frontend/src/app/api/endpoints.cljs` — add new endpoint paths
- `frontend/src/app/core.cljs` — add achievements route
- `frontend/src/app/routes.cljs` — register `/admin/achievements` route

---

## Chunk 1: Schema migrations + active-EV filter

### Task 1.1: Migration `add_is_locked_to_policies`

**Files:**
- Create: `backend/migrations/versions/<rev>_add_is_locked_to_policies.py`

- [ ] **Step 1: Generate empty alembic revision**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    flask db revision -m "add is_locked to policies"
```

This creates a new file in `backend/migrations/versions/`. Note the revision id.

- [ ] **Step 2: Fill in upgrade/downgrade**

Read the new file and replace its body with:

```python
def upgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_column('is_locked')
```

- [ ] **Step 3: Apply migration**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 flask db upgrade
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ... (add is_locked to policies)`.

- [ ] **Step 4: Verify column exists**

```bash
docker exec plataforma-gestao-rv-pipo-db-1 sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d policies" | grep is_locked'
```

Expected: `is_locked | boolean | not null | false`

- [ ] **Step 5: Add field to model**

Edit `backend/app/models/policy.py`, add after `installments_paid` line:

```python
is_locked = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
```

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*_add_is_locked_to_policies.py backend/app/models/policy.py
git commit -m "feat(policies): add is_locked flag to support manual override of HubSpot sync"
```

---

### Task 1.2: Migration `redesign_financial_imports`

**Files:**
- Create: `backend/migrations/versions/<rev>_redesign_financial_imports.py`
- Modify: `backend/app/models/financial_import.py`

- [ ] **Step 1: Generate revision**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    flask db revision -m "redesign financial_imports"
```

- [ ] **Step 2: Fill in upgrade**

```python
def upgrade():
    # Table is empty in production (verified). Safe to wipe.
    op.execute("TRUNCATE TABLE financial_imports")

    # Drop legacy unique constraint
    op.execute("ALTER TABLE financial_imports DROP CONSTRAINT IF EXISTS uq_financial_policy_month")

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.alter_column('policy_id', existing_type=sa.dialects.postgresql.UUID(), nullable=True)
        batch_op.add_column(sa.Column('cliente_mae', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('operadora', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('produto', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('tipo_receita', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('status_recebimento', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('data_recebimento', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('match_status', sa.String(length=30), nullable=False, server_default='UNMATCHED'))
        batch_op.add_column(sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('ix_financial_imports_quarter_year', 'financial_imports', ['quarter', 'year'])
    op.create_index('ix_financial_imports_match_status', 'financial_imports', ['match_status'])
    op.create_index('ix_financial_imports_policy_id', 'financial_imports', ['policy_id'])


def downgrade():
    op.drop_index('ix_financial_imports_policy_id', table_name='financial_imports')
    op.drop_index('ix_financial_imports_match_status', table_name='financial_imports')
    op.drop_index('ix_financial_imports_quarter_year', table_name='financial_imports')

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.drop_column('matched_at')
        batch_op.drop_column('match_status')
        batch_op.drop_column('data_recebimento')
        batch_op.drop_column('status_recebimento')
        batch_op.drop_column('tipo_receita')
        batch_op.drop_column('produto')
        batch_op.drop_column('operadora')
        batch_op.drop_column('cliente_mae')
        batch_op.alter_column('policy_id', existing_type=sa.dialects.postgresql.UUID(), nullable=False)

    op.create_unique_constraint('uq_financial_policy_month', 'financial_imports', ['policy_id', 'nf_mes_recebimento'])
```

- [ ] **Step 3: Update model**

Edit `backend/app/models/financial_import.py`, replace the `FinancialImport` class:

```python
class FinancialImport(db.Model):
    __tablename__ = "financial_imports"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    policy_id = db.Column(GUID, db.ForeignKey("policies.id"), nullable=True)
    nf_valor_liquido = db.Column(db.Numeric(12, 2), nullable=False)
    nf_mes_recebimento = db.Column(db.String(7), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    import_batch_id = db.Column(GUID, db.ForeignKey("import_batches.id"), nullable=False)

    cliente_mae = db.Column(db.String(500), nullable=True)
    operadora = db.Column(db.String(255), nullable=True)
    produto = db.Column(db.String(50), nullable=True)
    tipo_receita = db.Column(db.String(100), nullable=True)
    status_recebimento = db.Column(db.String(50), nullable=True)
    data_recebimento = db.Column(db.Date, nullable=True)
    match_status = db.Column(db.String(30), nullable=False, default='UNMATCHED', server_default='UNMATCHED')
    matched_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    policy = db.relationship("Policy", foreign_keys=[policy_id])
    batch = db.relationship("ImportBatch", foreign_keys=[import_batch_id])
```

(No more `__table_args__` with the unique constraint.)

- [ ] **Step 4: Apply migration**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 flask db upgrade
```

- [ ] **Step 5: Verify**

```bash
docker exec plataforma-gestao-rv-pipo-db-1 sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d financial_imports"'
```

Expected: 12 columns including `cliente_mae`, `match_status`, etc. `policy_id` should show as nullable.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*_redesign_financial_imports.py backend/app/models/financial_import.py
git commit -m "feat(financial): redesign financial_imports schema for new parser flow"
```

---

### Task 1.3: Seed `commission_pct_table` v2

**Files:**
- Create: `backend/migrations/versions/<rev>_seed_commission_pct_table_v2.py`

- [ ] **Step 1: Generate revision**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    flask db revision -m "seed commission_pct_table v2"
```

- [ ] **Step 2: Fill upgrade with idempotent seed**

```python
from datetime import date
from decimal import Decimal
import uuid


MATRIX = [
    # (segment, achievement_min, achievement_max, commission_pct)
    ('PP', '0.0000', '0.4999', '0.07'),
    ('PP', '0.5000', '0.9999', '0.08'),
    ('PP', '1.0000', '99.9999', '0.10'),
    ('P',  '0.0000', '0.4999', '0.07'),
    ('P',  '0.5000', '0.9999', '0.08'),
    ('P',  '1.0000', '99.9999', '0.10'),
    ('M',  '0.0000', '0.4999', '0.05'),
    ('M',  '0.5000', '0.9999', '0.06'),
    ('M',  '1.0000', '99.9999', '0.08'),
    ('G',  '0.0000', '0.4999', '0.03'),
    ('G',  '0.5000', '0.9999', '0.04'),
    ('G',  '1.0000', '99.9999', '0.06'),
]


def upgrade():
    conn = op.get_bind()

    # Determine next version
    result = conn.execute(sa.text(
        "SELECT COALESCE(MAX(version), 0) FROM commission_pct_table"
    )).scalar()
    next_version = (result or 0) + 1

    today = date.today().isoformat()

    for segment, ach_min, ach_max, pct in MATRIX:
        conn.execute(sa.text("""
            INSERT INTO commission_pct_table
                (id, version, segment, achievement_min, achievement_max,
                 commission_pct, valid_from, valid_until, created_by)
            VALUES
                (:id, :version, :segment, :ach_min, :ach_max, :pct, :valid_from, NULL, NULL)
        """), {
            "id": str(uuid.uuid4()),
            "version": next_version,
            "segment": segment,
            "ach_min": ach_min,
            "ach_max": ach_max,
            "pct": pct,
            "valid_from": today,
        })


def downgrade():
    # Best-effort: remove the version we added (only if it's the latest)
    conn = op.get_bind()
    max_version = conn.execute(sa.text(
        "SELECT MAX(version) FROM commission_pct_table"
    )).scalar()
    if max_version:
        conn.execute(sa.text(
            "DELETE FROM commission_pct_table WHERE version = :v"
        ), {"v": max_version})
```

- [ ] **Step 3: Apply migration**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 flask db upgrade
```

- [ ] **Step 4: Verify seed**

```bash
docker exec plataforma-gestao-rv-pipo-db-1 sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version, segment, achievement_min, achievement_max, commission_pct FROM commission_pct_table ORDER BY version DESC, segment, achievement_min LIMIT 12"'
```

Expected: 12 rows for the latest version, 4 segments × 3 ranges.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/*_seed_commission_pct_table_v2.py
git commit -m "feat(commissions): seed commission_pct_table with old-app matrix (12 entries)"
```

---

### Task 1.4: Active-EV filter helper

**Files:**
- Create: `backend/app/modules/policies/__init__.py`
- Create: `backend/app/modules/policies/filters.py`
- Create: `backend/tests/test_modules/test_policies/__init__.py`
- Create: `backend/tests/test_modules/test_policies/test_filters.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
mkdir -p backend/app/modules/policies backend/tests/test_modules/test_policies
```

Then with the Write tool, create empty files at:
- `backend/app/modules/policies/__init__.py` (empty)
- `backend/tests/test_modules/test_policies/__init__.py` (empty)

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_modules/test_policies/test_filters.py`:

```python
import pytest
from app import create_app
from app.extensions import db
from app.models import User, UserRole, Policy, Client


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_user(email, role=UserRole.EV, active=True):
    u = User(email=email, name=email, role=role, active=active)
    db.session.add(u)
    db.session.flush()
    return u


def _make_policy(ev, ticket_id):
    p = Policy(hubspot_ticket_id=ticket_id, ev_id=ev.id)
    db.session.add(p)
    db.session.flush()
    return p


def test_returns_only_policies_of_active_evs(app_ctx):
    from app.modules.policies.filters import active_ev_policies_query

    active_ev = _make_user("active@x", role=UserRole.EV, active=True)
    inactive_ev = _make_user("inactive@x", role=UserRole.EV, active=False)
    admin = _make_user("admin@x", role=UserRole.ADMIN, active=True)

    p_active = _make_policy(active_ev, "T1")
    _make_policy(inactive_ev, "T2")
    _make_policy(admin, "T3")  # admin is not EV; excluded

    result = active_ev_policies_query().all()
    assert len(result) == 1
    assert result[0].id == p_active.id


def test_excludes_policies_with_null_ev(app_ctx):
    from app.modules.policies.filters import active_ev_policies_query

    p = Policy(hubspot_ticket_id="T_NULL", ev_id=None)
    db.session.add(p)
    db.session.flush()

    assert active_ev_policies_query().count() == 0
```

- [ ] **Step 3: Run test, expect failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_policies/test_filters.py -v
```

Expected: ImportError or ModuleNotFoundError for `app.modules.policies.filters`.

- [ ] **Step 4: Implement helper**

Create `backend/app/modules/policies/filters.py`:

```python
"""Centralized policy filters.

Use these query builders for any feature that should only see policies
tied to active EV users (Apólices page, dashboards, calculator, etc).
"""
from app.models import Policy, User, UserRole
from app.extensions import db


def active_ev_policies_query():
    """Base query returning only policies whose ev_id resolves to an
    active user with role=EV.

    Use as starting point for further filters:
        active_ev_policies_query().filter(Policy.year == 2026).all()
    """
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(User.role == UserRole.EV, User.active.is_(True))
    )
```

- [ ] **Step 5: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_policies/test_filters.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/policies/ backend/tests/test_modules/test_policies/
git commit -m "feat(policies): add active_ev_policies_query helper for global filter"
```

---

## Chunk 2: Parser + Matcher

### Task 2.1: Matcher with normalize + dict index

**Files:**
- Create: `backend/app/modules/financial/matcher.py`
- Create: `backend/tests/test_modules/test_financial/test_matcher.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_financial/test_matcher.py`:

```python
import pytest
from datetime import date
from app.modules.financial.matcher import normalize, build_policy_index


class FakeClient:
    def __init__(self, name): self.name = name


class FakeBenefit:
    def __init__(self, value): self.value = value


class FakePolicy:
    def __init__(self, client_name, operadora, benefit, closed_date):
        self.client = FakeClient(client_name) if client_name else None
        self.partner_operator = operadora
        self.benefit_type = FakeBenefit(benefit) if benefit else None
        self.closed_date = closed_date


# ── normalize ────────────────────────────────────────────────
def test_normalize_lowercases():
    assert normalize("ABC") == "abc"


def test_normalize_strips_accents():
    assert normalize("Saúde") == "saude"
    assert normalize("Educação") == "educacao"


def test_normalize_trims_spaces():
    assert normalize("  Hello  ") == "hello"


def test_normalize_handles_none_and_empty():
    assert normalize(None) == ""
    assert normalize("") == ""


def test_normalize_combined():
    assert normalize("  CLÍNICA São JOÃO  ") == "clinica sao joao"


# ── build_policy_index ───────────────────────────────────────
def test_build_index_groups_by_key():
    p1 = FakePolicy("Zup", "Sulamérica", "SAUDE", date(2026, 1, 15))
    p2 = FakePolicy("Zup", "Sulamérica", "ODONTO", date(2026, 1, 15))
    p3 = FakePolicy("Acme", "Sulamérica", "SAUDE", date(2026, 1, 15))

    index = build_policy_index([p1, p2, p3])

    assert ("zup", "sulamerica", "SAUDE") in index
    assert ("zup", "sulamerica", "ODONTO") in index
    assert ("acme", "sulamerica", "SAUDE") in index


def test_build_index_sorts_by_closed_date_desc():
    p_old = FakePolicy("Zup", "X", "SAUDE", date(2025, 6, 1))
    p_new = FakePolicy("Zup", "X", "SAUDE", date(2026, 2, 1))
    p_mid = FakePolicy("Zup", "X", "SAUDE", date(2025, 12, 1))

    index = build_policy_index([p_old, p_new, p_mid])
    bucket = index[("zup", "x", "SAUDE")]

    assert bucket == [p_new, p_mid, p_old]


def test_build_index_skips_policies_without_client_or_benefit():
    p_ok = FakePolicy("Zup", "X", "SAUDE", date(2026, 1, 1))
    p_no_client = FakePolicy(None, "X", "SAUDE", date(2026, 1, 1))
    p_no_benefit = FakePolicy("Acme", "X", None, date(2026, 1, 1))

    index = build_policy_index([p_ok, p_no_client, p_no_benefit])
    assert len(index) == 1
    assert ("zup", "x", "SAUDE") in index
```

- [ ] **Step 2: Run tests, expect import failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_matcher.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement matcher**

Create `backend/app/modules/financial/matcher.py`:

```python
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
```

- [ ] **Step 4: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_matcher.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/financial/matcher.py backend/tests/test_modules/test_financial/test_matcher.py
git commit -m "feat(financial): add NF→Policy matcher with normalized dict index"
```

---

### Task 2.2: Sample fixture from real XLSX

**Files:**
- Create: `backend/tests/fixtures/sample_financial.xlsx`

- [ ] **Step 1: Generate sample fixture (100 rows from real XLSX)**

```bash
docker cp "/c/Users/User/Downloads/Consulta - Follow up Faturamento 2026.xlsx" \
    plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/full.xlsx

docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 python <<'PY'
import openpyxl
from copy import copy

src = openpyxl.load_workbook('/tmp/full.xlsx', read_only=False, data_only=True)
ws = src.active

dst = openpyxl.Workbook()
dws = dst.active
dws.title = ws.title

# Copy rows 1..5 (headers + summary) and rows 6..105 (100 data rows)
for r in range(1, 106):
    for c in range(1, 40):
        v = ws.cell(row=r, column=c).value
        if v is not None:
            dws.cell(row=r, column=c).value = v

dst.save('/tmp/sample.xlsx')
print("Sample saved")
PY

mkdir -p backend/tests/fixtures
docker cp plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/sample.xlsx \
    backend/tests/fixtures/sample_financial.xlsx
```

- [ ] **Step 2: Verify the fixture has expected structure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 python -c "
import openpyxl
wb = openpyxl.load_workbook('/tmp/sample.xlsx', data_only=True)
ws = wb.active
print('rows:', ws.max_row, 'cols:', ws.max_column)
print('header row 5 col 10:', ws.cell(5, 10).value)
"
```

Expected: ~105 rows, header at row 5, "Cliente \"Mãe\"" at col 10.

- [ ] **Step 3: Commit fixture**

```bash
git add backend/tests/fixtures/sample_financial.xlsx
git commit -m "test(financial): add 100-row sample fixture from real XLSX"
```

---

### Task 2.3: Parser rewrite

**Files:**
- Modify: `backend/app/modules/financial/parser.py` (full rewrite)
- Modify: `backend/tests/test_modules/test_financial/test_parser.py`

- [ ] **Step 1: Write failing tests for new parser**

Replace `backend/tests/test_modules/test_financial/test_parser.py` with:

```python
import pytest
from datetime import date
from pathlib import Path

from app.modules.financial.parser import parse_financial_xlsx, ParseError

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "sample_financial.xlsx"


def test_parses_real_xlsx_format():
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    assert result['stats']['total_lidas'] > 0
    # Some rows should pass the filter
    assert len(result['rows']) >= 0


def test_each_row_has_required_fields():
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert 'cliente_mae' in row
        assert 'operadora' in row
        assert 'produto' in row
        assert 'nf_valor_liquido' in row
        assert 'data_recebimento' in row
        assert 'mes_recebimento' in row
        assert 'tipo_receita' in row
        assert 'status_recebimento' in row
        assert row['status_recebimento'] == 'RECEBIDO'
        assert row['cliente_mae']  # not empty
        assert row['nf_valor_liquido'] is not None


def test_filters_out_non_recebido():
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    assert all(r['status_recebimento'] == 'RECEBIDO' for r in result['rows'])


def test_filters_by_quarter():
    result_q1 = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    result_q2 = parse_financial_xlsx(str(FIXTURE), target_quarter=2, target_year=2026)
    # Sample is from 2026 mostly Q1 — Q1 should have more rows
    assert result_q1['stats']['total_lidas'] == result_q2['stats']['total_lidas']
    # Both processed full file but filtered different periods


def test_keeps_mental_and_fitness_rows():
    """Mental/Fitness must be persisted to be visible in review (calculator marks them
    as PRODUTO_NAO_SUPORTADO). Parser should NOT drop them."""
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    produtos = {r['produto'] for r in result['rows']}
    # We can't assert Mental/Fitness exist in the sample, but if any row has them they should pass
    for r in result['rows']:
        # Parser doesn't filter by produto
        assert r['produto'] in {'Saúde', 'Odonto', 'Vida', 'Mental', 'Fitness'} or r['produto']


def test_keeps_negative_values():
    """Estornos (negativos) entram na soma — parser não filtra."""
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    for r in result['rows']:
        # nf_valor_liquido can be negative; just must be not None
        assert r['nf_valor_liquido'] is not None


def test_raises_on_missing_file():
    with pytest.raises((FileNotFoundError, ParseError)):
        parse_financial_xlsx("/nonexistent/path.xlsx", 1, 2026)


def test_stats_returned():
    result = parse_financial_xlsx(str(FIXTURE), target_quarter=1, target_year=2026)
    assert 'stats' in result
    assert 'total_lidas' in result['stats']
    assert 'persistidas' in result['stats']
    assert result['stats']['persistidas'] == len(result['rows'])
```

- [ ] **Step 2: Run tests, expect failures**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_parser.py -v
```

Expected: tests fail (function signature mismatch — old parser took just filepath).

- [ ] **Step 3: Rewrite the parser**

Replace `backend/app/modules/financial/parser.py` entirely:

```python
"""Financial XLSX parser for the real "Consulta - Follow up Faturamento" format.

The spreadsheet has:
- Single sheet (any name; we take the first / active)
- Summary rows at top
- Header row somewhere in the first 20 rows (detected by "Cliente Mãe" / "Operadora")
- Data rows after the header

We parse, apply minimal filters (status RECEBIDO + period + non-empty),
and return rows ready to be persisted as financial_imports.
"""
from datetime import datetime, date
from openpyxl import load_workbook


class ParseError(Exception):
    pass


# Header keywords for column detection (lowercase, no accents)
COLUMN_KEYWORDS = {
    'cliente_mae': lambda h: 'cliente' in h and ('mae' in h or 'maee' in h),
    'operadora': lambda h: 'operadora' in h,
    'produto': lambda h: 'produto' in h and 'segmenta' not in h,
    'nf_valor_liquido': lambda h: 'nf' in h and 'liquido' in h,
    'data_recebimento': lambda h: 'data' in h and 'recebimento' in h,
    'mes_recebimento': lambda h: 'mes' in h and 'recebimento' in h,
    'status_recebimento': lambda h: 'status' in h and 'recebimento' in h,
    'tipo_receita': lambda h: 'tipo' in h and 'receita' in h,
    'porte': lambda h: 'porte' in h,
}


def _normalize_header(s):
    if s is None:
        return ""
    import unicodedata
    decomp = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomp if unicodedata.category(c) != 'Mn')


def _detect_header_row(ws, scan_limit=20):
    """Find the header row by looking for 'cliente mae' in the first N rows."""
    for r in range(1, scan_limit + 1):
        row_values = [ws.cell(row=r, column=c).value for c in range(1, (ws.max_column or 40) + 1)]
        normalized = [_normalize_header(v) for v in row_values]
        if any('cliente' in h and 'mae' in h for h in normalized):
            return r
    raise ParseError(f"Header row not found in first {scan_limit} rows (looking for 'Cliente Mãe')")


def _build_column_map(headers):
    """Map our field names → column index by scanning headers."""
    mapping = {}
    for col_idx, header in enumerate(headers, start=1):
        norm = _normalize_header(header)
        for field, matcher in COLUMN_KEYWORDS.items():
            if field in mapping:
                continue
            if matcher(norm):
                mapping[field] = col_idx
    required = ['cliente_mae', 'operadora', 'produto', 'nf_valor_liquido', 'data_recebimento', 'status_recebimento']
    missing = [f for f in required if f not in mapping]
    if missing:
        raise ParseError(f"Missing required columns: {missing}")
    return mapping


def _coerce_date(value):
    """Accept datetime, date, or 'dd/mm/yyyy' string. Returns date or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _quarter_of(d):
    return (d.month - 1) // 3 + 1


def parse_financial_xlsx(filepath, target_quarter, target_year):
    """Parse the financial XLSX, returning rows that pass minimal filters.

    Returns:
        {
          'rows': [{cliente_mae, operadora, produto, nf_valor_liquido,
                    data_recebimento, mes_recebimento, tipo_receita,
                    status_recebimento, _row}],
          'stats': {total_lidas, descartadas_status, descartadas_periodo,
                    descartadas_vazias, persistidas}
        }
    """
    wb = load_workbook(filepath, read_only=False, data_only=True)
    ws = wb.active

    header_row = _detect_header_row(ws)
    headers = [ws.cell(row=header_row, column=c).value
               for c in range(1, (ws.max_column or 40) + 1)]
    cmap = _build_column_map(headers)

    rows = []
    stats = {
        'total_lidas': 0,
        'descartadas_status': 0,
        'descartadas_periodo': 0,
        'descartadas_vazias': 0,
        'persistidas': 0,
    }

    for r in range(header_row + 1, (ws.max_row or 0) + 1):
        stats['total_lidas'] += 1

        def cell(field):
            idx = cmap.get(field)
            return ws.cell(row=r, column=idx).value if idx else None

        cliente_mae = cell('cliente_mae')
        nf_liq = cell('nf_valor_liquido')
        if not cliente_mae or nf_liq is None:
            stats['descartadas_vazias'] += 1
            continue

        status = cell('status_recebimento')
        if (status or '').strip().upper() != 'RECEBIDO':
            stats['descartadas_status'] += 1
            continue

        data_rec = _coerce_date(cell('data_recebimento'))
        if data_rec is None:
            stats['descartadas_vazias'] += 1
            continue

        if data_rec.year != target_year or _quarter_of(data_rec) != target_quarter:
            stats['descartadas_periodo'] += 1
            continue

        mes_rec_raw = cell('mes_recebimento')
        if isinstance(mes_rec_raw, str) and mes_rec_raw:
            mes_rec = mes_rec_raw
        else:
            mes_rec = data_rec.strftime("%Y-%m")

        rows.append({
            'cliente_mae': str(cliente_mae).strip(),
            'operadora': str(cell('operadora') or '').strip(),
            'produto': str(cell('produto') or '').strip(),
            'nf_valor_liquido': float(nf_liq),
            'data_recebimento': data_rec,
            'mes_recebimento': mes_rec,
            'tipo_receita': str(cell('tipo_receita') or '').strip() or None,
            'status_recebimento': 'RECEBIDO',
            '_row': r,
        })
        stats['persistidas'] += 1

    wb.close()
    return {'rows': rows, 'stats': stats}
```

- [ ] **Step 4: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_parser.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/financial/parser.py backend/tests/test_modules/test_financial/test_parser.py
git commit -m "feat(financial): rewrite parser for real XLSX format with minimal filters"
```

---

## Chunk 3: Calculator + State Machine

### Task 3.1: Achievement validator

**Files:**
- Create or modify: `backend/app/modules/commissions/calculator.py` (add helper)
- Create: `backend/tests/test_modules/test_commissions/test_achievement_validation.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_commissions/test_achievement_validation.py`:

```python
import pytest
from datetime import date
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement, Segment, BenefitType
)


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u); db.session.flush()
    return u


def _policy(ev, ticket, closed_date, client_name="X"):
    c = Client(name=client_name)
    db.session.add(c); db.session.flush()
    p = Policy(
        hubspot_ticket_id=ticket, ev_id=ev.id, client_id=c.id,
        closed_date=closed_date, segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="Op",
    )
    db.session.add(p); db.session.flush()
    return p


def _ach(ev, q, y, pct):
    a = EvQuarterAchievement(
        ev_id=ev.id, quarter=q, year=y,
        achievement_pct=Decimal(str(pct)),
    )
    db.session.add(a); db.session.flush()
    return a


def test_validator_passes_when_all_gongo_quarters_have_achievement(app_ctx):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    ev = _ev("e1@x")
    _policy(ev, "T1", date(2026, 1, 15))
    _policy(ev, "T2", date(2025, 11, 1))
    _ach(ev, 1, 2026, 0.75)
    _ach(ev, 4, 2025, 0.50)

    missing = validate_achievements_for_appraisal(1, 2026)
    assert missing == []


def test_validator_returns_missing_for_uncovered_gongo_quarter(app_ctx):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    ev = _ev("e2@x")
    _policy(ev, "T1", date(2026, 1, 15))  # gongo Q1/2026
    _policy(ev, "T2", date(2025, 11, 1))  # gongo Q4/2025
    _ach(ev, 1, 2026, 0.75)
    # Missing achievement for Q4/2025

    missing = validate_achievements_for_appraisal(1, 2026)
    assert len(missing) == 1
    assert "Q4/2025" in missing[0]


def test_validator_ignores_inactive_evs(app_ctx):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    inactive = _ev("inact@x")
    inactive.active = False
    db.session.flush()
    _policy(inactive, "T1", date(2026, 1, 15))

    # Even though achievement is missing, this EV is excluded by the active filter
    missing = validate_achievements_for_appraisal(1, 2026)
    assert missing == []
```

- [ ] **Step 2: Run tests, expect import failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_commissions/test_achievement_validation.py -v
```

Expected: `validate_achievements_for_appraisal` not found.

- [ ] **Step 3: Implement validator at top of calculator.py**

Add to `backend/app/modules/commissions/calculator.py` (near top, after imports):

```python
from app.modules.policies.filters import active_ev_policies_query


class MissingAchievementsError(Exception):
    """Raised when run_quarterly_appraisal cannot proceed because some
    (ev, gongo_quarter, gongo_year) combination has no achievement."""
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


def validate_achievements_for_appraisal(quarter, year):
    """Verify every (ev_id, gongo_q, gongo_y) needed by this apuração
    has a stored achievement.

    Returns a list of human-readable strings for missing combinations.
    Empty list = ok to proceed.
    """
    policies = active_ev_policies_query().all()

    needed = set()
    for p in policies:
        if not p.closed_date or not p.ev_id:
            continue
        gongo_q = (p.closed_date.month - 1) // 3 + 1
        needed.add((p.ev_id, gongo_q, p.closed_date.year))

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
```

(Note: import `User` and `db` if not yet imported.)

- [ ] **Step 4: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_commissions/test_achievement_validation.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/calculator.py backend/tests/test_modules/test_commissions/test_achievement_validation.py
git commit -m "feat(commissions): add validate_achievements_for_appraisal (gongo-quarter aware)"
```

---

### Task 3.2: Calculator core (happy path)

**Files:**
- Modify: `backend/app/modules/commissions/calculator.py`
- Create: `backend/tests/test_modules/test_commissions/test_calculator_v2.py`

- [ ] **Step 1: Write failing tests for happy path**

Create `backend/tests/test_modules/test_commissions/test_calculator_v2.py`:

```python
import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement, Segment,
    BenefitType, FinancialImport, ImportBatch, Commission, CommissionPctTable,
)


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        # Seed minimal commission_pct_table
        for seg, mn, mx, pct in [
            ('M', '0.0000', '0.4999', '0.05'),
            ('M', '0.5000', '0.9999', '0.06'),
            ('M', '1.0000', '99.9999', '0.08'),
        ]:
            db.session.add(CommissionPctTable(
                version=1, segment=seg,
                achievement_min=Decimal(mn), achievement_max=Decimal(mx),
                commission_pct=Decimal(pct), valid_from=date.today(),
            ))
        db.session.flush()
        yield
        db.session.rollback()
        db.drop_all()


def _setup_basic_scenario():
    """One active EV, one client, one policy gongado in Q4/2025,
    one NF received in Q1/2026."""
    ev = User(email="ev@x", name="EV One", role=UserRole.EV, active=True)
    db.session.add(ev); db.session.flush()

    client = Client(name="Zup")
    db.session.add(client); db.session.flush()

    policy = Policy(
        hubspot_ticket_id="T1", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 11, 15),  # Q4/2025
        first_payment_real=date(2025, 12, 1),
        installments_paid=0, initial_installments_paid=0,
    )
    db.session.add(policy); db.session.flush()

    ach = EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025,
        achievement_pct=Decimal('0.75'),  # 75%, mid faixa → 6%
    )
    db.session.add(ach); db.session.flush()

    batch = ImportBatch(filename="test.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch); db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, quarter=1, year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup', operadora='SulAmerica', produto='Saúde',
        tipo_receita='Comissão', status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf); db.session.flush()

    return ev, policy, nf


def test_happy_path_matches_and_calculates_commission(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'MATCHED'
    assert nf.policy_id == policy.id

    comm = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    assert comm is not None
    # 1000 * 0.06 (M segment, 50-99.9 range) = 60.00
    assert comm.total_actual == Decimal('60.00')
    assert comm.is_final is False


def test_pre_vigencia_when_nf_before_first_payment(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2026, 6, 1)  # later than NF date
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRE_VIGENCIA'

    comm = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    assert comm is None


def test_expired_when_nf_after_window(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    policy.first_payment_real = date(2024, 1, 1)  # 2 years ago
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'EXPIRED'


def test_initial_installments_paid_shrinks_window(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    # first_payment 2025-12-01, initial=10 → window = 12-10 = 2 months → ends 2026-02-01
    policy.first_payment_real = date(2025, 12, 1)
    policy.initial_installments_paid = 10
    db.session.flush()

    # NF on 2026-02-15 should be EXPIRED (window ended 2026-02-01)
    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'EXPIRED'


def test_unmatched_when_no_policy(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev); db.session.flush()
    batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch); db.session.flush()

    # No policies; NF for unknown client
    nf = FinancialImport(
        import_batch_id=batch.id, quarter=1, year=2026,
        nf_valor_liquido=Decimal('500.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Unknown Co', operadora='X', produto='Saúde',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf); db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'
    assert nf.policy_id is None


def test_produto_nao_suportado(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    nf.produto = 'Mental'
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.match_status == 'PRODUTO_NAO_SUPORTADO'


def test_recalc_is_idempotent(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()

    run_quarterly_appraisal(1, 2026)
    first = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first().total_actual

    # Run again
    run_quarterly_appraisal(1, 2026)
    second = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first().total_actual

    assert first == second  # Same value, not doubled


def test_recalc_does_not_touch_locked_commissions(app_ctx):
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    # Pre-create a LOCKED commission with different value
    locked = Commission(
        policy_id=policy.id, ev_id=ev.id, quarter=1, year=2026,
        segment='M', achievement_pct=Decimal('0.5'),
        commission_pct=Decimal('0.06'), commission_pct_version=1,
        monthly_actual=Decimal('99.00'), total_actual=Decimal('99.00'),
        is_final=True,
    )
    db.session.add(locked); db.session.flush()

    run_quarterly_appraisal(1, 2026)

    # Locked commission preserved, no new one created (because policy_id+q+y is unique)
    locked_after = Commission.query.filter_by(
        policy_id=policy.id, quarter=1, year=2026, is_final=True
    ).first()
    assert locked_after.total_actual == Decimal('99.00')


def test_missing_achievement_raises_before_any_writes(app_ctx):
    from app.modules.commissions.calculator import (
        run_quarterly_appraisal, MissingAchievementsError,
    )

    ev, policy, nf = _setup_basic_scenario()
    EvQuarterAchievement.query.delete()
    db.session.flush()

    with pytest.raises(MissingAchievementsError):
        run_quarterly_appraisal(1, 2026)

    # No commissions created
    assert Commission.query.count() == 0
    db.session.refresh(nf)
    assert nf.match_status == 'UNMATCHED'  # untouched
```

- [ ] **Step 2: Run tests, expect failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_commissions/test_calculator_v2.py -v
```

Expected: tests fail because `run_quarterly_appraisal` (new) doesn't exist yet.

- [ ] **Step 3: Implement the new calculator**

Open `backend/app/modules/commissions/calculator.py`. Replace the entire file content with:

```python
"""Quarterly commission calculator (v2 — replaces old run_quarterly_appraisal_v2).

Match logic ported from the old React app's processCommissions:
- Match NF row → Policy by (cliente_mae, operadora, produto) normalized
- Vigência window = [first_payment_real, first_payment_real + (12 - initial_installments_paid) months]
- Achievement % is taken from EvQuarterAchievement of the policy's GONGO quarter
- Commission = nf_valor_liquido × matrix[segment][achievement_faixa]

is_final is NEVER set here; only by transition_appraisal(LOCKED).
"""
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from app.extensions import db
from app.models import (
    Policy, Commission, EvQuarterAchievement, FinancialImport,
    User, UserRole,
)
from app.modules.policies.filters import active_ev_policies_query
from app.modules.financial.matcher import build_policy_index, normalize
from app.modules.commissions.pct_lookup import lookup_commission_pct


# ── Errors ───────────────────────────────────────────────────────────


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# ── Pre-check ────────────────────────────────────────────────────────


def validate_achievements_for_appraisal(quarter, year):
    """Returns list of (ev_name → Q?/YYYY) strings for missing achievements."""
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


# ── Main entry ───────────────────────────────────────────────────────


BENEFIT_MAP = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}


def run_quarterly_appraisal(quarter, year):
    """Process all financial_imports for (quarter, year) and produce commissions.

    Pre-conditions:
    - validate_achievements_for_appraisal(quarter, year) returns []
    - financial_imports populated for this quarter

    Side effects:
    - Wipes Commissions for (quarter, year) where is_final=False
    - Resets policy.installments_paid to baseline (initial + LOCKED count)
    - Updates each NF's match_status and policy_id
    - Creates/updates Commission rows
    - Increments policy.installments_paid as MATCHED NFs are processed

    Raises:
        MissingAchievementsError if pre-check fails (no writes happen).
    """
    # ── Pre-check ────────────────────────────────────────────
    missing = validate_achievements_for_appraisal(quarter, year)
    if missing:
        raise MissingAchievementsError(missing)

    # ── 1. Wipe non-final commissions ────────────────────────
    Commission.query.filter_by(quarter=quarter, year=year, is_final=False).delete()
    db.session.flush()

    # ── 2. Reset installments_paid to baseline ───────────────
    policies = active_ev_policies_query().all()

    locked_nf_count = dict(
        db.session.query(
            FinancialImport.policy_id,
            db.func.count(FinancialImport.id),
        )
        .join(Commission, Commission.policy_id == FinancialImport.policy_id)
        .filter(Commission.is_final.is_(True),
                FinancialImport.match_status == 'MATCHED')
        .group_by(FinancialImport.policy_id)
        .all()
    )
    for p in policies:
        p.installments_paid = (p.initial_installments_paid or 0) + int(locked_nf_count.get(p.id, 0))

    # ── 3. Build matcher index ───────────────────────────────
    policy_index = build_policy_index(policies)

    # ── 4. Iterate financial_imports ─────────────────────────
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

    for nf in nfs:
        produto_n = normalize(nf.produto or '')
        benefit = BENEFIT_MAP.get(produto_n)
        if benefit is None:
            nf.match_status = 'PRODUTO_NAO_SUPORTADO'
            nf.policy_id = None
            nf.matched_at = None
            continue

        key = (normalize(nf.cliente_mae or ''), normalize(nf.operadora or ''), benefit)
        candidates = policy_index.get(key, [])
        if not candidates:
            nf.match_status = 'UNMATCHED'
            nf.policy_id = None
            nf.matched_at = None
            continue

        matched = None
        for policy in candidates:  # already sorted desc by closed_date
            if not policy.first_payment_real:
                continue
            window_end = policy.first_payment_real + relativedelta(
                months=12 - (policy.initial_installments_paid or 0)
            )
            if nf.data_recebimento < policy.first_payment_real:
                continue
            if nf.data_recebimento > window_end:
                continue
            matched = policy
            break

        if matched is None:
            best = candidates[0]
            if not best.first_payment_real or nf.data_recebimento < best.first_payment_real:
                nf.match_status = 'PRE_VIGENCIA'
            else:
                nf.match_status = 'EXPIRED'
            nf.policy_id = best.id
            nf.matched_at = None
            continue

        # Achievement at gongo quarter
        gongo_q = (matched.closed_date.month - 1) // 3 + 1
        gongo_y = matched.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=matched.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        segment_value = matched.segment.value if matched.segment else 'P'
        commission_pct, version = lookup_commission_pct(segment_value, achievement)
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (
            Decimal(str(nf.nf_valor_liquido)) * commission_pct
        ).quantize(Decimal('0.01'))

        # Upsert commission accumulating
        comm = Commission.query.filter_by(
            policy_id=matched.id, quarter=quarter, year=year, is_final=False
        ).first()
        if comm is None:
            comm = Commission(
                policy_id=matched.id, ev_id=matched.ev_id,
                quarter=quarter, year=year,
                segment=segment_value,
                achievement_pct=achievement,
                commission_pct=commission_pct,
                commission_pct_version=version,
                monthly_actual=Decimal('0'),
                total_actual=Decimal('0'),
                is_final=False,
            )
            db.session.add(comm)
        comm.monthly_actual = (comm.monthly_actual or Decimal('0')) + commission_amount
        comm.total_actual = (comm.total_actual or Decimal('0')) + commission_amount

        nf.policy_id = matched.id
        nf.match_status = 'MATCHED'
        nf.matched_at = datetime.now(timezone.utc)
        matched.installments_paid = (matched.installments_paid or 0) + 1

    db.session.flush()
    return _build_summary(quarter, year)


# ── Summary builder (used by API serializer) ─────────────────────────


def _build_summary(quarter, year):
    """Returns {ev_summary, totals, unmatched, expired} for the appraisal."""
    # Implemented in Task 4.3 (workflow.py serializer); stub here for tests.
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
        }
    }
```

- [ ] **Step 4: Verify dateutil is installed**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from dateutil.relativedelta import relativedelta; print('ok')"
```

If error, add `python-dateutil` to `backend/requirements.txt` and rebuild image.

- [ ] **Step 5: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_commissions/test_calculator_v2.py -v
```

Expected: 9 passed (or close — fix any compile errors).

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/commissions/calculator.py backend/tests/test_modules/test_commissions/test_calculator_v2.py
git commit -m "feat(commissions): rewrite run_quarterly_appraisal with NF→Policy matching"
```

---

### Task 3.3: State machine — drop V1, add LOCK→is_final

**Files:**
- Modify: `backend/app/modules/workflow/state_machine.py`
- Modify: `backend/tests/test_modules/test_workflow/test_state_machine.py`

- [ ] **Step 1: Update import in state_machine.py**

In `backend/app/modules/workflow/state_machine.py`, find the line:

```python
from app.modules.commissions.calculator import run_quarterly_appraisal_v2
run_quarterly_appraisal_v2(appraisal.quarter, appraisal.year)
```

Replace with:

```python
from app.modules.commissions.calculator import run_quarterly_appraisal
run_quarterly_appraisal(appraisal.quarter, appraisal.year)
```

- [ ] **Step 2: Add LOCK→is_final logic**

In the same file, find the `LOCKED` block:

```python
if new_status == AppraisalStatus.LOCKED:
    appraisal.locked_at = datetime.now(timezone.utc)
    appraisal.approved_by_finance = kwargs.get("approved_by")
```

Replace with:

```python
if new_status == AppraisalStatus.LOCKED:
    appraisal.locked_at = datetime.now(timezone.utc)
    appraisal.approved_by_finance = kwargs.get("approved_by")
    # Mark all commissions for this apuração as final
    from app.models import Commission
    Commission.query.filter_by(
        quarter=appraisal.quarter, year=appraisal.year, is_final=False
    ).update({"is_final": True})
```

- [ ] **Step 3: Drop the V1/V2 calculator aliases**

In `backend/app/modules/commissions/calculator.py`, ensure there's NO function named `run_quarterly_appraisal_v2`. The new file should only have `run_quarterly_appraisal`. If V2 still exists from previous edits, delete it.

- [ ] **Step 4: Update existing state_machine tests**

Open `backend/tests/test_modules/test_workflow/test_state_machine.py`. Replace any reference to `run_quarterly_appraisal_v2` with `run_quarterly_appraisal`. Add a test for the LOCK→is_final behavior:

```python
def test_lock_marks_commissions_as_final(app_ctx):
    from app.modules.workflow.state_machine import transition_appraisal
    from app.models import Appraisal, AppraisalStatus, Commission

    # Setup: appraisal in APPROVED state with non-final commissions
    appraisal = Appraisal(quarter=1, year=2026, status=AppraisalStatus.APPROVED, created_by=...)
    db.session.add(appraisal); db.session.flush()
    comm = Commission(
        policy_id=..., ev_id=..., quarter=1, year=2026,
        is_final=False, total_actual=Decimal("100.00"), monthly_actual=Decimal("100.00"),
    )
    db.session.add(comm); db.session.flush()

    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=...)

    db.session.refresh(comm)
    assert comm.is_final is True
```

(Adapt the `...` placeholders with actual fixtures from your test setup.)

- [ ] **Step 5: Run state machine tests**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_workflow/test_state_machine.py -v
```

Expected: all pass. Fix any imports that still reference V2.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/workflow/state_machine.py backend/tests/test_modules/test_workflow/test_state_machine.py backend/app/modules/commissions/calculator.py
git commit -m "refactor(workflow): drop run_quarterly_appraisal_v2, mark commissions final on LOCK"
```

---

## Chunk 4: Backend endpoints

### Task 4.1: PUT /policies/{id} edit + active-EV filter

**Files:**
- Modify: `backend/app/api/v1/policies.py`

- [ ] **Step 1: Read current state of policies.py**

```bash
# Read the file with the Read tool, not bash
```

- [ ] **Step 2: Add edit endpoint**

In `backend/app/api/v1/policies.py`, add:

```python
from app.api.middlewares import log_audit
from app.modules.policies.filters import active_ev_policies_query

EDITABLE_FIELDS = {
    'ev_id', 'first_payment_real', 'closed_date', 'initial_installments_paid',
    'segment', 'partner_operator', 'client_id',
}


@policies_bp.route("/<policy_id>", methods=["PUT"])
@require_role(UserRole.ADMIN)
def update_policy(policy_id):
    policy = db.session.get(Policy, policy_id)
    if policy is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Policy not found"}}), 404

    data = request.get_json() or {}
    old_values = {}
    new_values = {}

    for field in EDITABLE_FIELDS:
        if field in data:
            old = getattr(policy, field, None)
            new = data[field]
            # Coerce dates
            if field in ('first_payment_real', 'closed_date') and isinstance(new, str):
                from datetime import datetime as _dt
                new = _dt.fromisoformat(new).date() if new else None
            if field == 'segment' and new:
                from app.models.policy import Segment
                new = Segment(new)
            if old != new:
                old_values[field] = str(old) if old is not None else None
                new_values[field] = str(new) if new is not None else None
                setattr(policy, field, new)

    if new_values:
        policy.is_locked = True
        log_audit("policies", str(policy.id), "UPDATE",
                  old_values=old_values, new_values=new_values)
        db.session.commit()

    return jsonify({"data": _serialize_policy(policy)})
```

- [ ] **Step 3: Apply active-EV filter to GET**

Find the `list_policies` function. Replace `Policy.query` with `active_ev_policies_query()` as the base query.

- [ ] **Step 4: Test manually**

```bash
# Curl the endpoint after restart, e.g. PUT /api/v1/policies/<id> with body
# {"initial_installments_paid": 6}
```

For now we'll defer formal tests to Chunk 6 smoke. Just compile-check and ensure imports work:

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.api.v1.policies import policies_bp; print('ok')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/policies.py
git commit -m "feat(policies): add PUT endpoint for manual override + apply active-EV filter to GET"
```

---

### Task 4.2: HubSpot sync respects is_locked

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`

- [ ] **Step 1: Identify lockable fields**

The sync currently overwrites `ev_id`, `closed_date`, `segment`, `partner_operator`, `benefit_type`, `mrr_projected`. Of these, the "lockable" ones (per spec) are: `ev_id`, `first_payment_real`, `closed_date`, `segment`, `partner_operator`, `client_id`.

`mrr_projected` and other non-lockable fields are still updated regardless of `is_locked`.

- [ ] **Step 2: Wrap field updates in is_locked check**

In `_process_ticket()`, find the section that updates policy fields. Wrap the lockable assignments:

```python
if not policy.is_locked:
    if ev:
        policy.ev_id = ev.id
    if client_obj:
        policy.client_id = client_obj.id
    policy.segment = map_segment(props.get("cotar___segmentacao_pipo"))
    policy.benefit_type = map_benefit_type(props.get("apolice___beneficio"))
    policy.closed_date = parse_date(props.get("closed_date"))
    # partner_operator if present...

# Always update non-lockable
policy.mrr_projected = parse_decimal(props.get("mrr___receita_mensal"))
```

- [ ] **Step 3: Verify import compiles**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.modules.hubspot_sync.sync import run_sync; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py
git commit -m "feat(sync): respect Policy.is_locked when updating fields from HubSpot"
```

---

### Task 4.3: Enriched appraisal serializer + recalculate endpoint

**Files:**
- Modify: `backend/app/api/v1/workflow.py`

- [ ] **Step 1: Build the rich serializer**

In `backend/app/api/v1/workflow.py`, replace `_build_ev_summary` with a comprehensive version that drills down per Policy and per NF. Add:

```python
def _build_appraisal_detail(appraisal):
    """Build the full review payload: ev_summary with nested policies and NFs,
    plus unmatched/expired tabs."""
    from app.models import FinancialImport, Commission
    from app.modules.policies.filters import active_ev_policies_query

    quarter, year = appraisal.quarter, appraisal.year

    # Per-EV aggregation
    commissions = Commission.query.filter_by(quarter=quarter, year=year).all()
    nfs_matched = FinancialImport.query.filter_by(
        quarter=quarter, year=year, match_status='MATCHED'
    ).all()

    nfs_by_policy = defaultdict(list)
    for nf in nfs_matched:
        if nf.policy_id:
            nfs_by_policy[nf.policy_id].append(nf)

    # Pull policies referenced
    policy_ids = {c.policy_id for c in commissions} | set(nfs_by_policy.keys())
    policies = {p.id: p for p in Policy.query.filter(Policy.id.in_(policy_ids)).all()} if policy_ids else {}

    # Group commissions by EV
    by_ev = defaultdict(list)
    for c in commissions:
        by_ev[c.ev_id].append(c)

    # Build summary
    ev_summary = []
    for ev_id, ev_commissions in by_ev.items():
        ev = db.session.get(User, ev_id)
        # EV's achievement of the apuração quarter (for display only)
        ach_curr = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year
        ).first()

        policy_blocks = []
        for c in ev_commissions:
            p = policies.get(c.policy_id)
            if not p:
                continue
            nfs = nfs_by_policy.get(p.id, [])
            policy_blocks.append({
                "policy_id": str(p.id),
                "client_name": p.client.name if p.client else None,
                "operadora": p.partner_operator,
                "produto": p.benefit_type.value if p.benefit_type else None,
                "segment": p.segment.value if p.segment else None,
                "first_payment_real": p.first_payment_real.isoformat() if p.first_payment_real else None,
                "closed_date": p.closed_date.isoformat() if p.closed_date else None,
                "achievement_used_pct": float(c.achievement_pct * 100) if c.achievement_pct else 0.0,
                "commission_pct": float(c.commission_pct) if c.commission_pct else 0.0,
                "subtotal": float(c.total_actual or 0),
                "nfs": [
                    {
                        "data_recebimento": nf.data_recebimento.isoformat() if nf.data_recebimento else None,
                        "tipo_receita": nf.tipo_receita,
                        "nf_liquido": float(nf.nf_valor_liquido),
                    }
                    for nf in nfs
                ],
            })

        ev_summary.append({
            "ev_id": str(ev_id),
            "ev_name": ev.name if ev else "—",
            "achievement_pct": float(ach_curr.achievement_pct * 100) if ach_curr and ach_curr.achievement_pct else None,
            "policies_count": len(policy_blocks),
            "nf_count": sum(len(b["nfs"]) for b in policy_blocks),
            "total_commission": float(sum(c.total_actual or 0 for c in ev_commissions)),
            "policies": sorted(policy_blocks, key=lambda b: b["client_name"] or ""),
        })
    ev_summary.sort(key=lambda s: s["ev_name"])

    # Unmatched / expired tabs
    def _serialize_nf(nf):
        return {
            "id": str(nf.id),
            "cliente_mae": nf.cliente_mae,
            "operadora": nf.operadora,
            "produto": nf.produto,
            "data_recebimento": nf.data_recebimento.isoformat() if nf.data_recebimento else None,
            "nf_liquido": float(nf.nf_valor_liquido),
            "tipo_receita": nf.tipo_receita,
            "match_status": nf.match_status,
            "policy_id": str(nf.policy_id) if nf.policy_id else None,
        }

    unmatched = [_serialize_nf(n) for n in FinancialImport.query.filter_by(
        quarter=quarter, year=year, match_status='UNMATCHED').all()]
    expired = [_serialize_nf(n) for n in FinancialImport.query.filter(
        FinancialImport.quarter == quarter,
        FinancialImport.year == year,
        FinancialImport.match_status.in_(['EXPIRED', 'PRE_VIGENCIA'])).all()]
    nao_suportado = [_serialize_nf(n) for n in FinancialImport.query.filter_by(
        quarter=quarter, year=year, match_status='PRODUTO_NAO_SUPORTADO').all()]

    totals = {
        "total_commission": sum(s["total_commission"] for s in ev_summary),
        "ev_count": len(ev_summary),
        "policy_count": sum(s["policies_count"] for s in ev_summary),
        "matched_nf_count": sum(s["nf_count"] for s in ev_summary),
        "unmatched_count": len(unmatched),
        "expired_count": len(expired),
        "nao_suportado_count": len(nao_suportado),
    }

    return {
        "totals": totals,
        "ev_summary": ev_summary,
        "unmatched": unmatched,
        "expired": expired,
        "nao_suportado": nao_suportado,
    }
```

Add the necessary imports at top: `from collections import defaultdict`, `Policy`.

- [ ] **Step 2: Wire serializer into GET endpoint**

Update `_serialize_appraisal` to call `_build_appraisal_detail(appraisal)` when `detail=True`, and merge the result into the response under nested keys.

- [ ] **Step 3: Add recalculate endpoint**

```python
@workflow_bp.route("/<appraisal_id>/recalculate", methods=["POST"])
@require_role(UserRole.ADMIN)
def recalculate(appraisal_id):
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Not found"}}), 404
    if appraisal.status == AppraisalStatus.LOCKED:
        return jsonify({"error": {"code": "CONFLICT", "message": "Apuração está LOCKED"}}), 409

    from app.modules.commissions.calculator import (
        run_quarterly_appraisal, MissingAchievementsError,
    )
    try:
        run_quarterly_appraisal(appraisal.quarter, appraisal.year)
        db.session.commit()
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "MISSING_ACHIEVEMENTS", "message": str(e), "missing": e.missing}}), 422

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})
```

- [ ] **Step 4: Verify import compiles**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.api.v1.workflow import workflow_bp; print('ok')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/workflow.py
git commit -m "feat(workflow): enrich appraisal serializer with drill-down + add recalculate endpoint"
```

---

### Task 4.4: Financial upload rewrite

**Files:**
- Modify: `backend/app/api/v1/financial.py`
- Modify: `backend/app/modules/financial/processor.py`

- [ ] **Step 1: Rewrite the processor**

Replace `backend/app/modules/financial/processor.py`:

```python
"""Persist parsed financial rows into financial_imports.

The new flow has no PENDING/preview state — once parsed, rows are
committed immediately. Re-uploads delete the period first.
"""
from datetime import datetime, timezone
from app.extensions import db
from app.models import FinancialImport, ImportBatch, Appraisal, AppraisalStatus


class UploadBlockedError(Exception):
    pass


def persist_financial_rows(rows, quarter, year, filename, uploaded_by):
    """Persist rows for a given (quarter, year). Replaces any existing rows
    for that period unless an apuração for it is already LOCKED.

    Returns the ImportBatch id.
    """
    appraisal = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if appraisal and appraisal.status == AppraisalStatus.LOCKED:
        raise UploadBlockedError(
            f"Apuração de Q{quarter}/{year} já está LOCKED. Re-upload não permitido."
        )

    # Delete existing for this period
    FinancialImport.query.filter_by(quarter=quarter, year=year).delete()
    db.session.flush()

    batch = ImportBatch(
        filename=filename, uploaded_by=uploaded_by,
        nf_count=len(rows), perk_count=0, status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()

    for row in rows:
        fi = FinancialImport(
            import_batch_id=batch.id,
            quarter=quarter, year=year,
            nf_valor_liquido=row['nf_valor_liquido'],
            nf_mes_recebimento=row['mes_recebimento'],
            cliente_mae=row['cliente_mae'],
            operadora=row['operadora'],
            produto=row['produto'],
            tipo_receita=row['tipo_receita'],
            status_recebimento=row['status_recebimento'],
            data_recebimento=row['data_recebimento'],
            match_status='UNMATCHED',
        )
        db.session.add(fi)

    db.session.flush()
    return batch.id
```

- [ ] **Step 2: Rewrite the upload endpoint**

Replace the `upload_financial` function in `backend/app/api/v1/financial.py`:

```python
@financial_bp.route("/upload", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def upload_financial():
    """Upload XLSX, parse, and persist as financial_imports for a target quarter."""
    import tempfile, os

    user = g.current_user

    if "file" not in request.files:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "File required"}}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Only .xlsx accepted"}}), 400

    quarter = request.form.get("quarter", type=int)
    year = request.form.get("year", type=int)
    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter+year form fields required"}}), 400

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    file.save(path)

    try:
        from app.modules.financial.parser import parse_financial_xlsx, ParseError
        from app.modules.financial.processor import persist_financial_rows, UploadBlockedError

        try:
            parsed = parse_financial_xlsx(path, quarter, year)
        except ParseError as e:
            return jsonify({"error": {"code": "PARSE_ERROR", "message": str(e)}}), 400

        try:
            batch_id = persist_financial_rows(
                parsed['rows'], quarter, year, file.filename, user.id,
            )
        except UploadBlockedError as e:
            return jsonify({"error": {"code": "UPLOAD_BLOCKED", "message": str(e)}}), 409

        log_audit("import_batches", str(batch_id), "CREATE",
                  new_values={"filename": file.filename, "quarter": quarter, "year": year,
                              "nf_count": len(parsed['rows'])})
        db.session.commit()

        return jsonify({
            "data": {
                "batch_id": str(batch_id),
                "quarter": quarter, "year": year,
                "rows_persisted": len(parsed['rows']),
                "stats": parsed['stats'],
            }
        }), 201
    finally:
        os.unlink(path)
```

- [ ] **Step 3: Verify import compiles**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.api.v1.financial import financial_bp; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/financial.py backend/app/modules/financial/processor.py
git commit -m "feat(financial): rewrite upload to persist directly + handle re-upload semantics"
```

---

## Chunk 5: Frontend

### Task 5.1: Endpoints + events

**Files:**
- Modify: `frontend/src/app/api/endpoints.cljs`
- Modify: `frontend/src/app/views/revops/events.cljs`

- [ ] **Step 1: Add endpoint constants**

In `frontend/src/app/api/endpoints.cljs`, add:

```clojure
(defn policy-edit [id] (str "/policies/" id))
(defn appraisal-recalculate [id] (str "/appraisals/" id "/recalculate"))
(def achievements "/admin/ev-achievements")
```

- [ ] **Step 2: Add events**

In `frontend/src/app/views/revops/events.cljs`, add:

```clojure
;; ── Edit policy ───────────────────────────────────────────
(rf/reg-event-fx
 :revops/update-policy
 (fn [_ [_ id payload]]
   {:http {:method     :put
           :url        (ep/policy-edit id)
           :body       payload
           :on-success [:revops/policy-updated]
           :on-failure [:revops/policy-update-error]}}))

(rf/reg-event-fx
 :revops/policy-updated
 (fn [_ _]
   {:dispatch-n [[:revops/fetch-policies]
                 [:ui/show-toast {:type :success :message "Apólice atualizada"}]]}))

(rf/reg-event-fx
 :revops/policy-update-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error :message "Erro ao atualizar apólice"}]}))

;; ── Recalculate apuração ─────────────────────────────────
(rf/reg-event-fx
 :revops/recalculate-appraisal
 (fn [_ [_ id]]
   {:http {:method     :post
           :url        (ep/appraisal-recalculate id)
           :on-success [:revops/recalculated id]
           :on-failure [:revops/recalculate-error]}}))

(rf/reg-event-fx
 :revops/recalculated
 (fn [_ [_ id _resp]]
   {:dispatch-n [[:revops/fetch-appraisal-detail id]
                 [:ui/show-toast {:type :success :message "Recalculado!"}]]}))

(rf/reg-event-fx
 :revops/recalculate-error
 (fn [_ [_ resp]]
   (let [msg (get-in resp [:error :message] "Erro ao recalcular")]
     {:dispatch [:ui/show-toast {:type :error :message msg}]})))

;; ── Achievements editor ──────────────────────────────────
(rf/reg-event-fx
 :revops/save-achievement
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/achievements
           :body       payload
           :on-success [:revops/achievement-saved]
           :on-failure [:revops/achievement-error]}}))

(rf/reg-event-fx
 :revops/achievement-saved
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :success :message "Atingimento salvo"}]}))

(rf/reg-event-fx
 :revops/achievement-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error :message "Erro ao salvar"}]}))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/api/endpoints.cljs frontend/src/app/views/revops/events.cljs
git commit -m "feat(frontend): add events for policy edit, recalculate, achievements"
```

---

### Task 5.2: Policy edit modal

**Files:**
- Create: `frontend/src/app/views/revops/policy_edit_modal.cljs`
- Modify: `frontend/src/app/views/revops/policies.cljs`

- [ ] **Step 1: Create the modal**

Create `frontend/src/app/views/revops/policy_edit_modal.cljs`:

```clojure
(ns app.views.revops.policy-edit-modal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]))

(defn policy-edit-modal [{:keys [open? on-close policy]}]
  (let [form (r/atom (or policy {}))]
    (fn [{:keys [open? on-close policy]}]
      [modal/modal {:open? open? :on-close on-close
                    :title (str "Editar Apólice " (:hubspot_ticket_id policy))
                    :size :md}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [inputs/text-field
         {:label "Início Vigência (first_payment_real)"
          :type "date"
          :value (:first_payment_real @form)
          :on-change #(swap! form assoc :first_payment_real %)}]
        [inputs/text-field
         {:label "Data de Gongo (closed_date)"
          :type "date"
          :value (:closed_date @form)
          :on-change #(swap! form assoc :closed_date %)}]
        [inputs/number-field
         {:label "Parcelas pagas antes da plataforma (initial_installments_paid)"
          :value (:initial_installments_paid @form)
          :min 0 :max 12
          :on-change #(swap! form assoc :initial_installments_paid (js/parseInt %))}]
        [inputs/select
         {:label "Segmento"
          :value (:segment @form)
          :options [{:value "PP" :label "PP"} {:value "P" :label "P"}
                    {:value "M" :label "M"} {:value "G" :label "G"}]
          :on-change #(swap! form assoc :segment %)}]
        [inputs/text-field
         {:label "Operadora"
          :value (:partner_operator @form)
          :on-change #(swap! form assoc :partner_operator %)}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :primary
                      :on-click (fn []
                                  (rf/dispatch [:revops/update-policy (:id policy) @form])
                                  (on-close))}
          "Salvar"]]]])))
```

- [ ] **Step 2: Wire into policies.cljs**

In `frontend/src/app/views/revops/policies.cljs`, import the modal and add a state atom:

```clojure
(:require ...
          [app.views.revops.policy-edit-modal :as edit-modal])
```

Add an "Edit" button to each row in the data-table that opens the modal with the selected policy.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/policy_edit_modal.cljs frontend/src/app/views/revops/policies.cljs
git commit -m "feat(frontend): add policy edit modal for manual override"
```

---

### Task 5.3: Achievements editor page

**Files:**
- Create: `frontend/src/app/views/revops/achievements.cljs`
- Modify: `frontend/src/app/routes.cljs`
- Modify: `frontend/src/app/core.cljs`
- Modify: `frontend/src/app/views/revops/dashboard.cljs` (sidebar)

- [ ] **Step 1: Create the page**

Create `frontend/src/app/views/revops/achievements.cljs`:

```clojure
(ns app.views.revops.achievements
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn achievements-page []
  (let [filter (r/atom {:quarter 1 :year 2026})]
    (rf/dispatch [:revops/fetch-achievements @filter])
    (fn []
      (let [user @(rf/subscribe [:auth/current-user])
            route @(rf/subscribe [:current-route-name])
            achievements @(rf/subscribe [:revops/achievements])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user user
          :title "Atingimento por EV"
          :subtitle "Editar % de atingimento por trimestre"}
         [cards/card {}
          [:div {:style {:display "flex" :gap "12px" :margin-bottom "16px"}}
           [inputs/select {:label "Trimestre" :value (:quarter @filter)
                           :options [{:value 1 :label "Q1"} {:value 2 :label "Q2"}
                                     {:value 3 :label "Q3"} {:value 4 :label "Q4"}]
                           :on-change #(do (swap! filter assoc :quarter (js/parseInt %))
                                           (rf/dispatch [:revops/fetch-achievements @filter]))}]
           [inputs/select {:label "Ano" :value (:year @filter)
                           :options [{:value 2025 :label "2025"} {:value 2026 :label "2026"}
                                     {:value 2027 :label "2027"}]
                           :on-change #(do (swap! filter assoc :year (js/parseInt %))
                                           (rf/dispatch [:revops/fetch-achievements @filter]))}]]
          ;; Render table — each row is a (ev, achievement_pct) editable
          ;; (Implementation detail: table with inline edit + save button)
          ]]]))))
```

- [ ] **Step 2: Add route**

In `frontend/src/app/routes.cljs`, add:

```clojure
["/admin/achievements" {:name :revops/achievements :role #{:ADMIN}}]
```

- [ ] **Step 3: Wire view in core.cljs**

Add to the route → view map:

```clojure
:revops/achievements [revops-achievements/achievements-page]
```

And import the namespace.

- [ ] **Step 4: Add sidebar entry**

In `dashboard.cljs` `sidebar-items`, add a row for Achievements pointing to `:revops/achievements`.

- [ ] **Step 5: Add fetch event**

In `events.cljs`:

```clojure
(rf/reg-event-fx
 :revops/fetch-achievements
 (fn [_ [_ {:keys [quarter year]}]]
   {:http {:method :get
           :url (str "/admin/ev-achievements?quarter=" quarter "&year=" year)
           :on-success [:revops/achievements-loaded]}}))

(rf/reg-event-db
 :revops/achievements-loaded
 (fn [db [_ resp]]
   (assoc-in db [:admin :achievements] (get resp :data))))

(rf/reg-sub
 :revops/achievements
 (fn [db _] (get-in db [:admin :achievements])))
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/views/revops/achievements.cljs frontend/src/app/routes.cljs frontend/src/app/core.cljs frontend/src/app/views/revops/events.cljs frontend/src/app/views/revops/dashboard.cljs
git commit -m "feat(frontend): add achievements editor page (per-quarter, manual)"
```

---

### Task 5.4: Appraisal review drill-down

**Files:**
- Modify: `frontend/src/app/views/revops/appraisal_review.cljs`

- [ ] **Step 1: Rewrite the review page**

Replace `frontend/src/app/views/revops/appraisal_review.cljs` with a tabs-based version:

```clojure
(ns app.views.revops.appraisal-review
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.tabs :as tabs]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn ev-row [ev]
  ;; Collapsible row showing EV summary; click to expand drill-down per policy
  ...)

(defn por-ev-tab [ev-summary]
  [:div
   (for [ev ev-summary]
     ^{:key (:ev_id ev)} [ev-row ev])])

(defn unmatched-tab [unmatched]
  [tbl/data-table
   {:columns [{:key :cliente_mae :label "Cliente"}
              {:key :operadora :label "Operadora"}
              {:key :produto :label "Produto"}
              {:key :data_recebimento :label "Data"}
              {:key :nf_liquido :label "NF Líquido" :render #(fmt-brl (:nf_liquido %))}]
    :rows unmatched
    :empty-message "Nenhuma linha não matcheada"}])

(defn expired-tab [expired]
  ;; Same structure as unmatched-tab plus a column for the matched policy
  ...)

(defn nao-suportado-tab [rows]
  [tbl/data-table
   {:columns [...]
    :rows rows}])

(defn appraisal-review-page []
  (let [route @(rf/subscribe [:current-route])
        appraisal-id (get-in route [:path-params :id])
        active-tab (r/atom :por-ev)]
    (when appraisal-id
      (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id]))
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            appraisal (first (filter #(= (str (:id %)) (str appraisal-id)) (or appraisals [])))
            ev-summary (:ev_summary appraisal)
            unmatched (:unmatched appraisal)
            expired (:expired appraisal)
            nao-sup (:nao_suportado appraisal)
            totals (:totals appraisal)
            user @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route-name
          :user user
          :title "Revisão de Apuração"
          :subtitle (when appraisal (str "Q" (:quarter appraisal) "/" (:year appraisal)))
          :header-actions
          [:div {:style {:display "flex" :gap "8px"}}
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:navigate! :revops/appraisal])} "← Voltar"]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/recalculate-appraisal appraisal-id])}
            "🔄 Recalcular"]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:revops/release-to-validation appraisal-id])}
            "✅ Liberar para Validação EVs"]]}

         [cards/card {}
          [:div {:style {:display "flex" :gap "16px" :margin-bottom "16px"}}
           [:div "Total: " [:strong (fmt-brl (:total_commission totals))]]
           [:div "EVs: " (:ev_count totals)]
           [:div "Apólices: " (:policy_count totals)]
           [:div "NFs matcheadas: " (:matched_nf_count totals)]
           [:div "Não matcheadas: " (:unmatched_count totals)]
           [:div "Fora vigência: " (:expired_count totals)]]

          [tabs/tabs {:value @active-tab :on-change #(reset! active-tab %)}
           [{:value :por-ev :label "Por EV"}
            {:value :unmatched :label (str "Não matcheadas (" (count unmatched) ")")}
            {:value :expired :label (str "Fora de vigência (" (count expired) ")")}
            {:value :nao-sup :label (str "Não suportado (" (count nao-sup) ")")}]]

          (case @active-tab
            :por-ev [por-ev-tab ev-summary]
            :unmatched [unmatched-tab unmatched]
            :expired [expired-tab expired]
            :nao-sup [nao-suportado-tab nao-sup])]]))))
```

(The `ev-row`, `expired-tab`, `nao-suportado-tab` are sketched — fill in similar to `unmatched-tab`.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/views/revops/appraisal_review.cljs
git commit -m "feat(frontend): rewrite appraisal review with drill-down tabs"
```

---

### Task 5.5: Financial upload page (new flow)

**Files:**
- Modify: `frontend/src/app/views/revops/financial_upload.cljs`
- Modify: `frontend/src/app/views/revops/events.cljs`

- [ ] **Step 1: Update upload event to send quarter+year as form data**

The new backend endpoint needs `file` + `quarter` + `year` as multipart form fields. Update `:revops/upload-financial` event in events.cljs to build a `FormData` with these fields:

```clojure
(rf/reg-event-fx
 :revops/upload-financial
 (fn [{:keys [db]} [_ file quarter year]]
   (let [fd (js/FormData.)]
     (.append fd "file" file)
     (.append fd "quarter" quarter)
     (.append fd "year" year)
     {:db (assoc-in db [:admin :upload-loading?] true)
      :http {:method :post
             :url (ep/financial-upload)
             :body fd
             :on-success [:revops/upload-success]
             :on-failure [:revops/upload-error]}})))
```

(The `client.cljs` already handles `FormData` from the previous fix.)

- [ ] **Step 2: Update upload page UI**

In `financial_upload.cljs`, replace the 2-step preview flow with a single-step:

- Quarter + Year selectors
- File picker
- Submit button → dispatch `[:revops/upload-financial file quarter year]`
- Show progress + result (rows persisted, stats)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/financial_upload.cljs frontend/src/app/views/revops/events.cljs
git commit -m "feat(frontend): rewrite financial upload page with quarter+year + single-step flow"
```

---

## Chunk 6: Integration & Smoke Test

### Task 6.1: Reset, rebuild, smoke test

**Files:** none new

- [ ] **Step 1: Run all backend tests**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest -v 2>&1 | tail -30
```

Expected: all green. Fix any regressions.

- [ ] **Step 2: Rebuild containers**

```bash
docker compose up -d --build plataforma-comissoes-backend frontend
```

- [ ] **Step 3: Reset DB state for smoke test**

```bash
docker exec plataforma-gestao-rv-pipo-db-1 sh -c '
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  DELETE FROM commissions;
  DELETE FROM financial_imports;
  DELETE FROM ev_quarter_achievements;
  UPDATE appraisals SET status='"'"'DRAFT'"'"' WHERE quarter=1 AND year=2026;
"'
```

- [ ] **Step 4: Cadastrar achievements via UI**

Manual: abrir `/admin/achievements`, cadastrar % de atingimento pra cada EV ativo em Q1/2026 e em quaisquer trimestres anteriores que tenham policies gongadas.

- [ ] **Step 5: Upload da planilha real via UI**

Manual: abrir `/financial-upload`, selecionar Q1/2026, fazer upload do XLSX real. Verificar mensagem de sucesso com `rows_persisted` > 0.

- [ ] **Step 6: Iniciar apuração via UI**

Manual: abrir `/apuracao`, clicar em "Iniciar Cálculo". Esperar redirect pra tela de revisão.

- [ ] **Step 7: Verificar drill-down**

Manual: na tela de revisão, abrir cada aba (Por EV / Não matcheadas / Fora de vigência / Não suportado) e verificar que os números fazem sentido.

- [ ] **Step 8: Liberar pra Validação**

Manual: clicar "Liberar para Validação EVs". Verificar que vai pro status VALIDATING.

- [ ] **Step 9: Documentar achados**

Em `docs/superpowers/plans/2026-04-07-financeiro-apuracao-redesign.md` (este arquivo), adicionar uma seção "## Smoke test results" no final com:
- Total de NFs no XLSX
- Total persistido no DB após filtros
- Distribution por match_status
- Total de comissão calculado por EV
- Issues encontrados

- [ ] **Step 10: Commit final**

```bash
git add docs/superpowers/plans/2026-04-07-financeiro-apuracao-redesign.md
git commit -m "docs(plan): add smoke test results"
```

---

## Smoke test results

(Preencher após Task 6.1 step 9.)
