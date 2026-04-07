# Financeiro & Apuração Trimestral — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever parser financeiro, calculator e UI de revisão pra trabalhar com o XLSX real (Consulta - Follow up Faturamento 2026), aplicando filtro global de "EVs ativos", edição manual de Policies (override do HubSpot) e atingimento % manual por trimestre.

**Architecture:** Backend Flask+SQLAlchemy roda parser → matcher (dict O(1)) → calculator (per gongo-quarter achievement, date-based vigência) → grava em `financial_imports` e `commissions`. Frontend ClojureScript+Re-frame mostra drill-down EV→Policy→NF na revisão. Status `CALCULATING` é uma porta manual: RevOps revisa antes de liberar pra `VALIDATING`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2.x, Alembic, Postgres 16, openpyxl, ClojureScript (shadow-cljs), Reagent, Re-frame, cljs-ajax.

**Spec:** `docs/superpowers/specs/2026-04-07-financeiro-apuracao-redesign.md`

**Pré-req:** Ler a spec inteira antes de começar. Ela tem todas as decisões e o "porquê" de cada uma.

---

## Convenções

- **TDD obrigatório no backend**: para cada função nova, write the failing test FIRST, run it, see it fail, then implement.
- **Frontend NÃO tem TDD nesse repo** — não existe infraestrutura de `cljs.test` configurada e o padrão estabelecido é validar UI via smoke test manual (Chunk 6). NÃO criar `cljs.test` files; seguir o padrão existente. Se quiser adicionar testes de evento re-frame mais à frente, é uma melhoria à parte.
- **Commits frequentes**: um commit por tarefa concluída, mensagem no formato `feat:`/`fix:`/`refactor:`/`test:`/`docs:`.
- **Rodar tests dentro do container** (não no host) pra garantir mesmo Python/libs:
  ```bash
  docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
      python -m pytest tests/path/ -v
  ```
- **Não usar Bash pra ler/editar arquivos** — Read/Edit/Write tools.
- **Não pular `superpowers:test-driven-development`** se a skill estiver disponível.
- **Worktree:** este plano modifica ~25 arquivos em backend e frontend. Considerar rodar em worktree dedicada (`EnterWorktree` ou `git worktree add`) pra isolar do trabalho atual. Se já estiver em worktree, ok.
- **Verificar campos NOT NULL antes de criar fixtures de teste**: o `Policy` model tem vários campos obrigatórios (ev_id pode ser nullable, mas confirmar antes). Sempre rodar o teste com setup mínimo pra ver se SQLAlchemy aceita; ajustar fixture conforme necessário.

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

### Task 2.2: Sample fixtures (real XLSX subset + synthetic mini)

**Files:**
- Create: `backend/tests/fixtures/sample_financial.xlsx` (subset da planilha real, ~100 linhas)
- Create: `backend/tests/fixtures/synthetic_financial.xlsx` (gerado em Python, controle total dos valores)

Vamos ter dois fixtures:
1. **`sample_financial.xlsx`** — subset da planilha real pra smoke testing (formato exato, nomes reais)
2. **`synthetic_financial.xlsx`** — XLSX criado por código com valores conhecidos pra testes precisos (100% determinístico)

- [ ] **Step 1: Pre-copiar a planilha real pro container** (uma vez só)

```bash
# Copia a planilha pro container — caminho dentro do container fica fixo
docker cp "C:/Users/User/Downloads/Consulta - Follow up Faturamento 2026.xlsx" \
    plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/full.xlsx
```

Verificar:
```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    ls -la /tmp/full.xlsx
```

- [ ] **Step 2: Gerar `sample_financial.xlsx` (subset 100 linhas reais)**

Criar `backend/tests/fixtures/__make_sample.py` (script auxiliar, pode deletar depois):

```python
"""Run inside the backend container to generate sample_financial.xlsx
from /tmp/full.xlsx (the real spreadsheet pre-copied)."""
import openpyxl

src = openpyxl.load_workbook('/tmp/full.xlsx', data_only=True)
ws = src.active

dst = openpyxl.Workbook()
dws = dst.active
dws.title = ws.title

# Copy rows 1..5 (summary + headers) and rows 6..105 (100 data rows)
for r in range(1, 106):
    for c in range(1, 40):
        v = ws.cell(row=r, column=c).value
        if v is not None:
            dws.cell(row=r, column=c).value = v

dst.save('/tmp/sample.xlsx')
print("OK", dws.max_row, "rows")
```

Rodar:
```bash
docker cp backend/tests/fixtures/__make_sample.py \
    plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/__make_sample.py
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python /tmp/__make_sample.py
mkdir -p backend/tests/fixtures
docker cp plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/sample.xlsx \
    backend/tests/fixtures/sample_financial.xlsx
```

Apagar o helper depois:
```bash
rm backend/tests/fixtures/__make_sample.py
```

- [ ] **Step 3: Gerar `synthetic_financial.xlsx` (controle total)**

Criar `backend/tests/fixtures/__make_synthetic.py`:

```python
"""Generate a tiny XLSX with known values for parser unit tests."""
from datetime import datetime
import openpyxl

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Consulta receita 2026"

# Summary section (rows 1-3)
ws.cell(row=1, column=15).value = "Total Base Comissão"  # ignored

# Header row at row 5 (mimic real format)
headers = {
    2: "Operadora", 7: "Produto", 10: "Cliente \"Mãe\"",
    11: "Porte do Cliente", 14: "% Comissão", 20: "NF Líquido",
    23: "Status Recebimento", 25: "Data Recebimento",
    32: "Mês Recebimento", 5: "Tipo Receita",
}
for col, label in headers.items():
    ws.cell(row=5, column=col).value = label

# Data rows starting at row 6
def add_row(r, op, prod, cliente, porte, status, dt, nf_liq, tipo):
    ws.cell(row=r, column=2).value = op
    ws.cell(row=r, column=7).value = prod
    ws.cell(row=r, column=10).value = cliente
    ws.cell(row=r, column=11).value = porte
    ws.cell(row=r, column=20).value = nf_liq
    ws.cell(row=r, column=23).value = status
    ws.cell(row=r, column=25).value = dt
    ws.cell(row=r, column=5).value = tipo

# Q1/2026 RECEBIDO Saúde — should pass
add_row(6, "SulAmerica", "Saúde", "Zup", "G (>=600)", "RECEBIDO",
        datetime(2026, 2, 15), 1000.00, "Comissão")
# Q1/2026 RECEBIDO Saúde negative (estorno) — should pass
add_row(7, "SulAmerica", "Saúde", "Zup", "G (>=600)", "RECEBIDO",
        datetime(2026, 3, 1), -200.00, "Comissão")
# Q1/2026 A RECEBER — should be filtered out by status
add_row(8, "Bradesco", "Saúde", "Acme", "M (201-599)", "A RECEBER",
        datetime(2026, 1, 20), 500.00, "Comissão")
# Q2/2026 RECEBIDO — should be filtered out by period when target=Q1
add_row(9, "Hapvida", "Saúde", "Beta", "P (81-200)", "RECEBIDO",
        datetime(2026, 4, 5), 300.00, "Comissão")
# Q1/2026 RECEBIDO Mental — should pass parser, marked PRODUTO_NAO_SUPORTADO by calc
add_row(10, "Zenklub", "Mental", "Zup", "G (>=600)", "RECEBIDO",
        datetime(2026, 2, 20), 150.00, "Fee por Vida")
# Empty cliente — should be filtered out as garbage
add_row(11, "X", "Saúde", None, "M (201-599)", "RECEBIDO",
        datetime(2026, 2, 20), 100.00, "Comissão")

wb.save('/tmp/synthetic.xlsx')
print("OK")
```

Rodar:
```bash
docker cp backend/tests/fixtures/__make_synthetic.py \
    plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/__make_synthetic.py
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python /tmp/__make_synthetic.py
docker cp plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1:/tmp/synthetic.xlsx \
    backend/tests/fixtures/synthetic_financial.xlsx
rm backend/tests/fixtures/__make_synthetic.py
```

- [ ] **Step 4: Verificar fixtures**

```bash
ls -la backend/tests/fixtures/
```

Esperado: `sample_financial.xlsx` (~30KB) + `synthetic_financial.xlsx` (~6KB).

- [ ] **Step 5: Commit fixtures**

```bash
git add backend/tests/fixtures/sample_financial.xlsx backend/tests/fixtures/synthetic_financial.xlsx
git commit -m "test(financial): add sample (real subset) + synthetic XLSX fixtures"
```

---

### Task 2.3: Parser rewrite

**Files:**
- Modify: `backend/app/modules/financial/parser.py` (full rewrite)
- Modify: `backend/tests/test_modules/test_financial/test_parser.py`

- [ ] **Step 1: Write failing tests for new parser**

Estes testes usam o `synthetic_financial.xlsx` (controle total) pra asserções precisas, e o `sample_financial.xlsx` (planilha real) só pra smoke do formato. Replace `backend/tests/test_modules/test_financial/test_parser.py` with:

```python
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.modules.financial.parser import parse_financial_xlsx, ParseError

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic_financial.xlsx"
SAMPLE = FIXTURES / "sample_financial.xlsx"


# ── Synthetic XLSX (controlled values) ────────────────────────

def test_synthetic_parses_3_valid_rows_for_q1_2026():
    """Synthetic has 6 rows total: 3 should pass for Q1/2026
    (1 RECEBIDO Saúde positive, 1 RECEBIDO Saúde negative, 1 RECEBIDO Mental).
    Filtered out: 1 A RECEBER, 1 Q2/2026, 1 sem cliente."""
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    assert result['stats']['total_lidas'] == 6
    assert result['stats']['descartadas_status'] == 1  # A RECEBER
    assert result['stats']['descartadas_periodo'] == 1  # Q2/2026
    assert result['stats']['descartadas_vazias'] == 1   # sem cliente
    assert result['stats']['persistidas'] == 3
    assert len(result['rows']) == 3


def test_synthetic_keeps_negative_values():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    nfs = [r['nf_valor_liquido'] for r in result['rows']]
    assert -200.00 in nfs
    assert 1000.00 in nfs


def test_synthetic_keeps_mental_product():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    produtos = [r['produto'] for r in result['rows']]
    assert 'Mental' in produtos


def test_synthetic_filters_by_quarter():
    """Q2/2026 should give different result than Q1/2026."""
    result_q1 = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    result_q2 = parse_financial_xlsx(str(SYNTHETIC), target_quarter=2, target_year=2026)
    assert result_q1['stats']['persistidas'] == 3
    assert result_q2['stats']['persistidas'] == 1  # the Q2 row
    # The Q2 row should be the Hapvida one
    assert result_q2['rows'][0]['operadora'] == 'Hapvida'


def test_synthetic_parses_dates_as_date_objects():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert isinstance(row['data_recebimento'], date)
        assert row['data_recebimento'].year == 2026


def test_synthetic_status_only_recebido():
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    assert all(r['status_recebimento'] == 'RECEBIDO' for r in result['rows'])


def test_synthetic_extracts_mes_recebimento():
    """mes_recebimento is YYYY-MM format derived from data_recebimento."""
    result = parse_financial_xlsx(str(SYNTHETIC), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert len(row['mes_recebimento']) == 7
        assert row['mes_recebimento'].startswith('2026-')


# ── Real XLSX format smoke test ───────────────────────────────

def test_real_xlsx_format_parses_without_error():
    """Smoke test against the real spreadsheet subset — verifies header
    detection and column mapping work for the actual format."""
    result = parse_financial_xlsx(str(SAMPLE), target_quarter=1, target_year=2026)
    assert 'rows' in result
    assert 'stats' in result
    assert result['stats']['total_lidas'] > 0


def test_real_xlsx_extracts_known_fields():
    """Every persisted row should have all required fields populated."""
    result = parse_financial_xlsx(str(SAMPLE), target_quarter=1, target_year=2026)
    for row in result['rows']:
        assert row['cliente_mae']
        assert row['nf_valor_liquido'] is not None
        assert isinstance(row['data_recebimento'], date)
        assert row['status_recebimento'] == 'RECEBIDO'


# ── Error handling ────────────────────────────────────────────

def test_raises_on_missing_file():
    with pytest.raises((FileNotFoundError, ParseError)):
        parse_financial_xlsx("/nonexistent/path.xlsx", 1, 2026)
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
- Create new file: `backend/app/modules/commissions/calculator.py` (REPLACING existing — old file gets fully deleted)
- Create: `backend/tests/test_modules/test_commissions/test_achievement_validation.py`

**IMPORTANTE — Estratégia de substituição do calculator.py:**

Tasks 3.1 e 3.2 juntas reescrevem o `calculator.py` inteiro. Pra evitar confusão:

1. **Task 3.1** adiciona o `validate_achievements_for_appraisal` no INÍCIO do novo arquivo, junto com a classe `MissingAchievementsError`. Mas mantém o `run_quarterly_appraisal_v2` antigo coexistindo (comentado como TODO REMOVE).
2. **Task 3.2** substitui o resto, deletando o V2 antigo e implementando o `run_quarterly_appraisal` novo.

Ao final da Task 3.2 o arquivo está completamente novo e limpo.

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


def test_negative_nf_subtracts_from_commission(app_ctx):
    """Estornos: NF negativo gera comissão negativa que reduz o total."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()
    # Add a second NF with a negative value for the same policy
    second_nf = FinancialImport(
        import_batch_id=nf.import_batch_id, quarter=1, year=2026,
        nf_valor_liquido=Decimal('-300.00'),
        nf_mes_recebimento='2026-03',
        cliente_mae='Zup', operadora='SulAmerica', produto='Saúde',
        tipo_receita='Comissão', status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 3, 10),
        match_status='UNMATCHED',
    )
    db.session.add(second_nf); db.session.flush()

    run_quarterly_appraisal(1, 2026)

    # 1000 * 0.06 = 60.00 (positive NF)
    # -300 * 0.06 = -18.00 (negative NF)
    # Total: 60 - 18 = 42.00
    comm = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    assert comm.total_actual == Decimal('42.00')


def test_snapshot_uses_gongo_quarter_not_apuracao_quarter(app_ctx):
    """Achievement % must come from the quarter the policy was gongado, not the
    apuração quarter. Policy gongado in Q4/2025 used in Q1/2026 apuração → Q4/2025 ach."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev, policy, nf = _setup_basic_scenario()

    # Set Q4/2025 achievement to 30% (faixa <50, → 5%)
    EvQuarterAchievement.query.filter_by(ev_id=ev.id).delete()
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025,
        achievement_pct=Decimal('0.30'),
    ))
    # Add a Q1/2026 achievement with a DIFFERENT value (should NOT be used)
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=1, year=2026,
        achievement_pct=Decimal('1.50'),  # 150% — would give 8% if used
    ))
    db.session.flush()

    run_quarterly_appraisal(1, 2026)

    # Should use Q4/2025 (30%) → segment M, faixa <50 → 5%
    # 1000 * 0.05 = 50.00 (NOT 80.00 from 1.50/Q1 lookup)
    comm = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    assert comm.total_actual == Decimal('50.00')
    assert comm.achievement_pct == Decimal('0.30')


def test_multi_policy_picks_most_recent_within_window(app_ctx):
    """Two policies with same (cliente, operadora, produto). The NF should match
    the more recent one whose vigência still covers the NF date."""
    from app.modules.commissions.calculator import run_quarterly_appraisal

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev); db.session.flush()
    client = Client(name="Zup")
    db.session.add(client); db.session.flush()

    # Old policy: gongado mar/2025, vigência 2025-04-01 → 2026-04-01
    p_old = Policy(
        hubspot_ticket_id="OLD", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 3, 1),
        first_payment_real=date(2025, 4, 1),
    )
    # New policy: gongado dez/2025, vigência 2026-01-01 → 2027-01-01
    p_new = Policy(
        hubspot_ticket_id="NEW", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 12, 1),
        first_payment_real=date(2026, 1, 1),
    )
    db.session.add_all([p_old, p_new]); db.session.flush()

    # Achievements for both gongo quarters
    db.session.add(EvQuarterAchievement(ev_id=ev.id, quarter=1, year=2025, achievement_pct=Decimal('0.30')))
    db.session.add(EvQuarterAchievement(ev_id=ev.id, quarter=4, year=2025, achievement_pct=Decimal('0.80')))
    db.session.flush()

    batch = ImportBatch(filename="t.xlsx", uploaded_by=ev.id, status="CONFIRMED")
    db.session.add(batch); db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, quarter=1, year=2026,
        nf_valor_liquido=Decimal('1000.00'),
        nf_mes_recebimento='2026-02',
        cliente_mae='Zup', operadora='SulAmerica', produto='Saúde',
        status_recebimento='RECEBIDO',
        data_recebimento=date(2026, 2, 15),
        match_status='UNMATCHED',
    )
    db.session.add(nf); db.session.flush()

    run_quarterly_appraisal(1, 2026)

    db.session.refresh(nf)
    assert nf.policy_id == p_new.id  # picked the more recent

    # Should use Q4/2025 achievement (80%) → faixa 50-99.9 → 6%
    # 1000 * 0.06 = 60.00
    comm = Commission.query.filter_by(policy_id=p_new.id, quarter=1, year=2026).first()
    assert comm.total_actual == Decimal('60.00')
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

- [ ] **Step 1: Write the failing LOCK→is_final test FIRST**

Add to `backend/tests/test_modules/test_workflow/test_state_machine.py`:

```python
def test_lock_marks_all_quarter_commissions_as_final(app_ctx):
    from datetime import date
    from decimal import Decimal
    from app.extensions import db
    from app.modules.workflow.state_machine import transition_appraisal
    from app.models import (
        Appraisal, AppraisalStatus, Commission, User, UserRole,
        Policy, Client, Segment, BenefitType,
    )

    # Setup: minimal user+policy
    admin = User(email="adm@x", name="Admin", role=UserRole.ADMIN, active=True)
    db.session.add(admin); db.session.flush()

    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev); db.session.flush()

    client = Client(name="Zup")
    db.session.add(client); db.session.flush()

    policy = Policy(
        hubspot_ticket_id="T1", ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 12, 1),
        first_payment_real=date(2026, 1, 1),
    )
    db.session.add(policy); db.session.flush()

    # Apuração in APPROVED state (next legal transition is LOCKED)
    appraisal = Appraisal(
        quarter=1, year=2026, status=AppraisalStatus.APPROVED,
        created_by=admin.id,
    )
    db.session.add(appraisal); db.session.flush()

    # Two non-final commissions for this apuração
    c1 = Commission(
        policy_id=policy.id, ev_id=ev.id, quarter=1, year=2026,
        segment="M", achievement_pct=Decimal("0.5"),
        commission_pct=Decimal("0.06"), commission_pct_version=1,
        monthly_actual=Decimal("100.00"), total_actual=Decimal("100.00"),
        is_final=False,
    )
    db.session.add(c1); db.session.flush()

    # Transition APPROVED → LOCKED
    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=admin.id)
    db.session.flush()

    db.session.refresh(c1)
    assert c1.is_final is True
    assert appraisal.status == AppraisalStatus.LOCKED
    assert appraisal.locked_at is not None


def test_calculator_called_when_transitioning_to_calculating(app_ctx):
    """Smoke: ensure the import path of run_quarterly_appraisal still resolves."""
    from app.modules.commissions.calculator import run_quarterly_appraisal
    assert callable(run_quarterly_appraisal)
```

- [ ] **Step 2: Run new tests, expect failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_workflow/test_state_machine.py::test_lock_marks_all_quarter_commissions_as_final -v
```

Expected: FAIL because the LOCK block doesn't yet update commissions, and possibly the import is still `run_quarterly_appraisal_v2`.

- [ ] **Step 3: Update import in state_machine.py**

In `backend/app/modules/workflow/state_machine.py`, find the line importing the calculator and replace:

```python
from app.modules.commissions.calculator import run_quarterly_appraisal_v2
run_quarterly_appraisal_v2(appraisal.quarter, appraisal.year)
```

with:

```python
from app.modules.commissions.calculator import run_quarterly_appraisal
run_quarterly_appraisal(appraisal.quarter, appraisal.year)
```

- [ ] **Step 4: Add LOCK→is_final logic**

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
    ).update({"is_final": True}, synchronize_session=False)
```

- [ ] **Step 5: Drop the V1/V2 calculator aliases (sanity check)**

Run:
```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    grep -n "run_quarterly_appraisal_v2" /app/app/modules/commissions/calculator.py
```

Esperado: no output (V2 não existe mais — Task 3.2 já apagou).

- [ ] **Step 6: Update any leftover V2 references in tests**

```bash
grep -rn "run_quarterly_appraisal_v2" backend/tests/
```

Replace any hits with `run_quarterly_appraisal`.

- [ ] **Step 7: Run all state machine tests**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_workflow/ -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/workflow/state_machine.py backend/tests/test_modules/test_workflow/test_state_machine.py
git commit -m "feat(workflow): mark commissions as final on LOCK + drop V2 calculator alias"
```

---

## Chunk 4: Backend endpoints

### Task 4.1: PUT /policies/{id} edit + active-EV filter

**Files:**
- Modify: `backend/app/api/v1/policies.py`
- Create: `backend/tests/test_api/test_policies_edit.py`

- [ ] **Step 1: Read current state of policies.py**

Use the Read tool to read `backend/app/api/v1/policies.py` and understand current GET endpoint shape and imports.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_api/test_policies_edit.py`:

```python
import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType, AuditLog,
)


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _admin_token(app_ctx):
    """Mint a JWT for an admin user. Adjust to match auth helper in your tests."""
    from app.auth.tokens import create_access_token  # adjust path if different
    admin = User(email="adm@x", name="Admin", role=UserRole.ADMIN, active=True)
    db.session.add(admin); db.session.flush()
    return create_access_token(admin), admin


def _make_policy():
    c = Client(name="Zup")
    db.session.add(c); db.session.flush()
    p = Policy(
        hubspot_ticket_id="T1", client_id=c.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 12, 1),
    )
    db.session.add(p); db.session.flush()
    return p


def test_put_policy_updates_initial_installments_paid(client, app_ctx):
    token, admin = _admin_token(app_ctx)
    p = _make_policy()

    resp = client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db.session.refresh(p)
    assert p.initial_installments_paid == 6
    assert p.is_locked is True


def test_put_policy_creates_audit_log_entry(client, app_ctx):
    token, admin = _admin_token(app_ctx)
    p = _make_policy()

    client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers={"Authorization": f"Bearer {token}"},
    )

    log = AuditLog.query.filter_by(table_name="policies", record_id=p.id).first()
    assert log is not None
    assert log.action == "UPDATE"
    assert "initial_installments_paid" in log.new_values


def test_put_policy_returns_404_if_not_found(client, app_ctx):
    token, _ = _admin_token(app_ctx)
    resp = client.put(
        "/api/v1/policies/00000000-0000-0000-0000-000000000000",
        json={"initial_installments_paid": 6},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_put_policy_requires_admin(client, app_ctx):
    ev = User(email="ev@x", name="EV", role=UserRole.EV, active=True)
    db.session.add(ev); db.session.flush()
    from app.auth.tokens import create_access_token
    token = create_access_token(ev)

    p = _make_policy()
    resp = client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (401, 403)
```

**Nota:** o helper `create_access_token` pode ter outro nome no projeto. Antes de rodar, dar `grep -rn "def create_access_token\|jwt.encode" backend/app/auth/` pra encontrar o helper certo e ajustar o import.

- [ ] **Step 3: Run tests, expect failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_api/test_policies_edit.py -v
```

Expected: 404 ou erro de import — endpoint não existe ainda.

- [ ] **Step 4: Add edit endpoint**

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

- [ ] **Step 5: Apply active-EV filter to GET**

Open the file. Find `list_policies` function. The current implementation likely starts with `query = Policy.query.order_by(...)`. Replace with:

```python
from app.modules.policies.filters import active_ev_policies_query
# ...
query = active_ev_policies_query().order_by(Policy.created_at.desc())
```

Preserve any additional `.filter(...)` chains that come after.

- [ ] **Step 6: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_api/test_policies_edit.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Compile-check the blueprint**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.api.v1.policies import policies_bp; print('ok')"
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/policies.py backend/tests/test_api/test_policies_edit.py
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

- [ ] **Step 1: Write failing tests for processor**

Create `backend/tests/test_modules/test_financial/test_processor.py`:

```python
import pytest
from datetime import date
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models import (
    FinancialImport, ImportBatch, Appraisal, AppraisalStatus,
    User, UserRole,
)
from app.modules.financial.processor import (
    persist_financial_rows, UploadBlockedError,
)


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _admin():
    u = User(email="adm@x", name="Admin", role=UserRole.ADMIN, active=True)
    db.session.add(u); db.session.flush()
    return u


def _row(**kw):
    base = {
        'cliente_mae': 'Zup', 'operadora': 'SulAmerica', 'produto': 'Saúde',
        'nf_valor_liquido': 1000.00, 'mes_recebimento': '2026-02',
        'data_recebimento': date(2026, 2, 15), 'tipo_receita': 'Comissão',
        'status_recebimento': 'RECEBIDO',
    }
    base.update(kw)
    return base


def test_persist_creates_rows(app_ctx):
    admin = _admin()
    batch_id = persist_financial_rows(
        [_row(), _row(cliente_mae='Acme')],
        quarter=1, year=2026, filename="t.xlsx", uploaded_by=admin.id,
    )
    assert FinancialImport.query.count() == 2
    assert ImportBatch.query.get(batch_id).nf_count == 2


def test_persist_replaces_existing_for_same_period(app_ctx):
    admin = _admin()
    persist_financial_rows([_row()], 1, 2026, "first.xlsx", admin.id)
    persist_financial_rows([_row(), _row(cliente_mae='X')], 1, 2026, "second.xlsx", admin.id)

    # Only the second batch's rows remain
    assert FinancialImport.query.count() == 2
    # Old batch is marked SUPERSEDED
    superseded = ImportBatch.query.filter_by(status='SUPERSEDED').count()
    assert superseded == 1


def test_persist_blocks_when_appraisal_locked(app_ctx):
    admin = _admin()
    appraisal = Appraisal(
        quarter=1, year=2026, status=AppraisalStatus.LOCKED, created_by=admin.id,
    )
    db.session.add(appraisal); db.session.flush()

    with pytest.raises(UploadBlockedError):
        persist_financial_rows([_row()], 1, 2026, "t.xlsx", admin.id)

    # Nothing was persisted
    assert FinancialImport.query.count() == 0


def test_persist_does_not_touch_other_periods(app_ctx):
    admin = _admin()
    persist_financial_rows([_row()], 1, 2026, "q1.xlsx", admin.id)
    persist_financial_rows(
        [_row(data_recebimento=date(2026, 5, 1), mes_recebimento='2026-05')],
        2, 2026, "q2.xlsx", admin.id,
    )

    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 1
    assert FinancialImport.query.filter_by(quarter=2, year=2026).count() == 1
```

- [ ] **Step 2: Run tests, expect failure**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_processor.py -v
```

Expected: ImportError (processor doesn't have `persist_financial_rows` yet).

- [ ] **Step 3: Rewrite the processor**

Replace `backend/app/modules/financial/processor.py`:

```python
"""Persist parsed financial rows into financial_imports.

The new flow has no PENDING/preview state — once parsed, rows are
committed immediately. Re-uploads delete the period's rows and mark
old batches as SUPERSEDED.
"""
from datetime import datetime, timezone
from app.extensions import db
from app.models import FinancialImport, ImportBatch, Appraisal, AppraisalStatus


class UploadBlockedError(Exception):
    pass


def persist_financial_rows(rows, quarter, year, filename, uploaded_by):
    """Persist rows for a given (quarter, year). Replaces any existing rows
    for that period unless an apuração for it is already LOCKED.

    Old batches that previously held rows for this period get their status
    set to SUPERSEDED (so the audit trail is preserved without confusion).

    Returns the new ImportBatch id.
    """
    appraisal = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if appraisal and appraisal.status == AppraisalStatus.LOCKED:
        raise UploadBlockedError(
            f"Apuração de Q{quarter}/{year} já está LOCKED. Re-upload não permitido."
        )

    # Find batches whose rows are about to be deleted, mark them SUPERSEDED
    superseded_batch_ids = {
        bid for (bid,) in db.session.query(FinancialImport.import_batch_id)
        .filter(FinancialImport.quarter == quarter,
                FinancialImport.year == year)
        .distinct()
        .all()
    }
    if superseded_batch_ids:
        ImportBatch.query.filter(
            ImportBatch.id.in_(superseded_batch_ids)
        ).update({"status": "SUPERSEDED"}, synchronize_session=False)

    # Delete existing rows for this period
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

- [ ] **Step 4: Run tests, expect pass**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_modules/test_financial/test_processor.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Rewrite the upload endpoint**

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

- [ ] **Step 6: Verify import compiles**

```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -c "from app.api.v1.financial import financial_bp; print('ok')"
```

- [ ] **Step 7: Smoke test the upload endpoint via test client**

Add to `backend/tests/test_api/test_financial_upload.py`:

```python
import pytest
from pathlib import Path
from app import create_app
from app.extensions import db
from app.models import User, UserRole, FinancialImport

FIXTURE = Path(__file__).parent.parent / "fixtures" / "synthetic_financial.xlsx"


@pytest.fixture
def app_ctx():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


def test_upload_synthetic_xlsx_persists_3_rows(app_ctx):
    """End-to-end: POST the synthetic fixture and verify rows persisted."""
    from app.auth.tokens import create_access_token

    admin = User(email="adm@x", name="Admin", role=UserRole.ADMIN, active=True)
    db.session.add(admin); db.session.commit()
    token = create_access_token(admin)

    client = app_ctx.test_client()
    with open(FIXTURE, "rb") as f:
        resp = client.post(
            "/api/v1/financial/upload",
            data={
                "file": (f, "synthetic.xlsx"),
                "quarter": "1",
                "year": "2026",
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["data"]["rows_persisted"] == 3
    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 3
```

Run:
```bash
docker exec plataforma-gestao-rv-pipo-plataforma-comissoes-backend-1 \
    python -m pytest tests/test_api/test_financial_upload.py -v
```

Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/financial.py backend/app/modules/financial/processor.py backend/tests/test_modules/test_financial/test_processor.py backend/tests/test_api/test_financial_upload.py
git commit -m "feat(financial): rewrite upload to persist directly + handle re-upload + tests"
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

Read `frontend/src/app/views/revops/policies.cljs` first. Then:

a) Add to `:require`:
```clojure
[reagent.core :as r]
[app.views.revops.policy-edit-modal :as edit-modal]
```

b) Inside the page component, add state:
```clojure
(let [selected-policy (r/atom nil)
      modal-open? (r/atom false)]
  (fn []
    ...
```

c) Add a new column to the data-table `:columns` vector (right after the existing "Ações" or last column):
```clojure
{:key :edit :label "" :width "80px"
 :render
 (fn [row]
   [btn/button
    {:variant :secondary :size :sm
     :on-click #(do (reset! selected-policy row)
                    (reset! modal-open? true))}
    "✏️ Editar"])}
```

d) Render the modal at the bottom of the page component (sibling of the table card):
```clojure
[edit-modal/policy-edit-modal
 {:open? @modal-open?
  :policy @selected-policy
  :on-close #(reset! modal-open? false)}]
```

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

- [ ] **Step 1: Create the page (full implementation)**

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
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn achievements-page []
  (let [filter-state (r/atom {:quarter 1 :year 2026})
        edits (r/atom {})] ; ev_id → new pct value
    (rf/dispatch [:revops/fetch-achievements @filter-state])
    (fn []
      (let [user @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])
            achievements (or @(rf/subscribe [:revops/achievements]) [])
            on-filter-change
            (fn [k v]
              (swap! filter-state assoc k v)
              (reset! edits {})
              (rf/dispatch [:revops/fetch-achievements @filter-state]))]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route-name
          :user user
          :title "Atingimento por EV"
          :subtitle "Editar % de atingimento manual por trimestre"
          :header-actions
          [btn/button
           {:variant :secondary
            :on-click #(rf/dispatch
                        [:revops/auto-calc-achievements @filter-state])}
           "🤖 Auto-calcular baseline"]}
         [cards/card {}
          [:div {:style {:display "flex" :gap "12px" :margin-bottom "16px"}}
           [inputs/select
            {:label "Trimestre"
             :value (str (:quarter @filter-state))
             :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                       {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
             :on-change #(on-filter-change :quarter (js/parseInt %))}]
           [inputs/select
            {:label "Ano"
             :value (str (:year @filter-state))
             :options [{:value "2025" :label "2025"} {:value "2026" :label "2026"}
                       {:value "2027" :label "2027"}]
             :on-change #(on-filter-change :year (js/parseInt %))}]]

          [tbl/data-table
           {:columns
            [{:key :ev_name :label "EV"}
             {:key :total_mrr :label "MRR Total"
              :render #(when (:total_mrr %)
                         (str "R$ " (.toLocaleString (:total_mrr %) "pt-BR")))}
             {:key :mrr_target :label "Meta MRR"
              :render #(when (:mrr_target %)
                         (str "R$ " (.toLocaleString (:mrr_target %) "pt-BR")))}
             {:key :achievement_pct :label "% Atingimento (editável)"
              :render
              (fn [row]
                (let [ev-id (:ev_id row)
                      stored (or (* 100 (or (:achievement_pct row) 0)) 0)
                      current (get @edits ev-id stored)]
                  [:input
                   {:type "number" :step "0.01" :min "0" :max "9999"
                    :value current
                    :style {:width "100px"}
                    :on-change #(swap! edits assoc ev-id
                                       (js/parseFloat (.. % -target -value)))}]))}
             {:key :is_final :label "Final"
              :render #(if (:is_final %) "✅" "—")}
             {:key :actions :label "" :width "100px"
              :render
              (fn [row]
                (let [ev-id (:ev_id row)
                      pct (get @edits ev-id)]
                  (when pct
                    [btn/button
                     {:variant :primary :size :sm
                      :on-click
                      #(do
                         (rf/dispatch
                          [:revops/save-achievement
                           {:ev_id ev-id
                            :quarter (:quarter @filter-state)
                            :year (:year @filter-state)
                            :achievement_pct (/ pct 100.0)}]) ; convert back to fraction
                         (swap! edits dissoc ev-id))}
                     "Salvar"])))}]
            :rows achievements
            :empty-message "Nenhum EV. Cadastre EVs primeiro."}]]]))))
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

- [ ] **Step 5: Add fetch + auto-calc events + sub**

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

(rf/reg-event-fx
 :revops/auto-calc-achievements
 (fn [_ [_ {:keys [quarter year]}]]
   {:http {:method :post
           :url "/admin/ev-achievements/calculate"
           :body {:quarter quarter :year year}
           :on-success [:revops/auto-calc-done quarter year]
           :on-failure [:revops/achievement-error]}}))

(rf/reg-event-fx
 :revops/auto-calc-done
 (fn [_ [_ quarter year _]]
   {:dispatch-n [[:revops/fetch-achievements {:quarter quarter :year year}]
                 [:ui/show-toast {:type :success :message "Baseline calculado"}]]}))
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

- [ ] **Step 1: Rewrite the review page (full implementation, no stubs)**

Replace `frontend/src/app/views/revops/appraisal_review.cljs` with:

```clojure
(ns app.views.revops.appraisal-review
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.tabs :as tabs]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when (some? v)
    (str "R$ " (.toLocaleString (js/Number. v) "pt-BR"
                                #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn fmt-pct [v]
  (when (some? v)
    (str (.toFixed (js/Number. v) 1) "%")))

;; ── Drill-down: NF list inside a Policy block ─────────────
(defn nf-list-table [nfs]
  [tbl/data-table
   {:columns
    [{:key :data_recebimento :label "Data" :width "100px"}
     {:key :tipo_receita :label "Tipo" :width "140px"}
     {:key :nf_liquido :label "NF Líquido" :align "right"
      :render (fn [r] (fmt-brl (:nf_liquido r)))}]
    :rows nfs
    :empty-message "—"}])

;; ── Policy block (one per Policy under an EV) ─────────────
(defn policy-block [policy]
  (let [open? (r/atom false)]
    (fn [policy]
      [:div {:style {:border (str "1px solid " t/border-default)
                     :border-radius (:md t/border-radius)
                     :padding "12px" :margin-bottom "8px"}}
       [:div {:style {:display "flex" :justify-content "space-between"
                      :align-items "center" :cursor "pointer"}
              :on-click #(swap! open? not)}
        [:div
         [:strong (:client_name policy)]
         [:span {:style {:color t/text-secondary :margin-left "8px"}}
          (str (:operadora policy) " · " (:produto policy) " · " (:segment policy))]]
        [:div {:style {:font-weight (:semibold t/font-weights)}}
         (fmt-brl (:subtotal policy))]]
       (when @open?
         [:div {:style {:margin-top "12px" :padding-top "12px"
                        :border-top (str "1px solid " t/border-default)}}
          [:div {:style {:display "flex" :gap "16px" :margin-bottom "8px"
                         :font-size (:sm t/font-sizes) :color t/text-secondary}}
           [:div "Início vigência: " (or (:first_payment_real policy) "—")]
           [:div "Gongo: " (or (:closed_date policy) "—")]
           [:div "Atingimento usado: " (fmt-pct (:achievement_used_pct policy))]
           [:div "% Comissão: " (fmt-pct (* 100 (or (:commission_pct policy) 0)))]]
          [nf-list-table (:nfs policy)]])])))

;; ── EV row (one per EV in Por EV tab) ─────────────────────
(defn ev-row [ev tipo-filter operadora-filter]
  (let [open? (r/atom false)]
    (fn [ev tipo-filter operadora-filter]
      (let [filter-nfs (fn [nfs]
                         (cond->> nfs
                           (and tipo-filter (not= tipo-filter "Todos"))
                           (filter #(= (:tipo_receita %) tipo-filter))))
            filtered-policies (->> (:policies ev)
                                   (filter (fn [p]
                                             (or (= operadora-filter "Todas")
                                                 (nil? operadora-filter)
                                                 (= (:operadora p) operadora-filter))))
                                   (map (fn [p] (update p :nfs filter-nfs))))]
        [:div {:style {:border (str "1px solid " t/border-default)
                       :border-radius (:md t/border-radius)
                       :margin-bottom "12px" :background t/bg-card}}
         [:div {:style {:padding "16px" :cursor "pointer"
                        :display "flex" :justify-content "space-between"}
                :on-click #(swap! open? not)}
          [:div
           [:div {:style {:font-weight (:semibold t/font-weights)
                          :font-size (:lg t/font-sizes)}} (:ev_name ev)]
           [:div {:style {:color t/text-secondary :font-size (:sm t/font-sizes)}}
            (str (:policies_count ev) " apólices · "
                 (:nf_count ev) " NFs · "
                 "Atingimento: " (fmt-pct (:achievement_pct ev)))]]
          [:div {:style {:font-size (:xl t/font-sizes)
                         :font-weight (:bold t/font-weights)
                         :color t/color-primary}}
           (fmt-brl (:total_commission ev))]]
         (when @open?
           [:div {:style {:padding "0 16px 16px 16px"}}
            (for [p filtered-policies]
              ^{:key (:policy_id p)} [policy-block p])])]))))

;; ── Por EV tab ────────────────────────────────────────────
(defn por-ev-tab [ev-summary]
  (let [tipo-filter (r/atom "Todos")
        operadora-filter (r/atom "Todas")]
    (fn [ev-summary]
      (let [all-operadoras (->> ev-summary
                                (mapcat :policies)
                                (map :operadora)
                                distinct
                                sort)]
        [:div
         [:div {:style {:display "flex" :gap "12px" :margin-bottom "16px"}}
          [inputs/select
           {:label "Tipo Receita" :value @tipo-filter
            :options [{:value "Todos" :label "Todos"}
                      {:value "Comissão" :label "Comissão"}
                      {:value "Fee por Vida" :label "Fee por Vida"}
                      {:value "Premiação" :label "Premiação"}
                      {:value "Patrocínio - Eventos" :label "Patrocínio"}
                      {:value "Agenciamento" :label "Agenciamento"}]
            :on-change #(reset! tipo-filter %)}]
          [inputs/select
           {:label "Operadora" :value @operadora-filter
            :options (cons {:value "Todas" :label "Todas"}
                           (map (fn [o] {:value o :label o}) all-operadoras))
            :on-change #(reset! operadora-filter %)}]]
         (for [ev ev-summary]
           ^{:key (:ev_id ev)} [ev-row ev @tipo-filter @operadora-filter])]))))

;; ── Generic NF table for unmatched/expired/nao-suportado ──
(defn nf-table [rows show-policy?]
  [tbl/data-table
   {:columns
    (cond-> [{:key :cliente_mae :label "Cliente"}
             {:key :operadora :label "Operadora"}
             {:key :produto :label "Produto"}
             {:key :data_recebimento :label "Data" :width "110px"}
             {:key :tipo_receita :label "Tipo"}
             {:key :nf_liquido :label "NF Líquido" :align "right"
              :render #(fmt-brl (:nf_liquido %))}]
      show-policy?
      (conj {:key :match_status :label "Status"
             :render #(do [badge/badge {:variant :warning} (:match_status %)])}))
    :rows rows
    :empty-message "Nenhuma linha"}])

(defn export-csv-button [rows filename]
  [btn/button
   {:variant :secondary :size :sm
    :on-click
    (fn []
      (let [headers ["cliente_mae" "operadora" "produto" "data_recebimento"
                     "tipo_receita" "nf_liquido" "match_status"]
            csv-rows (cons (str/join "," headers)
                           (map (fn [r]
                                  (str/join ","
                                            (map #(str "\"" (or (get r (keyword %)) "") "\"")
                                                 headers)))
                                rows))
            content (str/join "\n" csv-rows)
            blob (js/Blob. #js [content] #js {:type "text/csv"})
            url (.createObjectURL js/URL blob)
            a (.createElement js/document "a")]
        (set! (.-href a) url)
        (set! (.-download a) filename)
        (.click a)
        (.revokeObjectURL js/URL url)))}
   "📥 Exportar CSV"])

(defn unmatched-tab [rows]
  [:div
   [:div {:style {:margin-bottom "12px"}} [export-csv-button rows "nao-matcheadas.csv"]]
   [nf-table rows false]])

(defn expired-tab [rows]
  [:div
   [:div {:style {:margin-bottom "12px"}} [export-csv-button rows "fora-vigencia.csv"]]
   [nf-table rows true]])

(defn nao-suportado-tab [rows]
  [:div
   [:p {:style {:color t/text-secondary :font-size (:sm t/font-sizes)}}
    "Linhas com produto não suportado pelo modelo (Mental, Fitness)."]
   [nf-table rows false]])

;; ── Page ──────────────────────────────────────────────────
(defn appraisal-review-page []
  (let [route @(rf/subscribe [:current-route])
        appraisal-id (get-in route [:path-params :id])
        active-tab (r/atom :por-ev)]
    (when appraisal-id
      (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id]))
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            appraisal (first (filter #(= (str (:id %)) (str appraisal-id))
                                     (or appraisals [])))
            ev-summary (or (:ev_summary appraisal) [])
            unmatched (or (:unmatched appraisal) [])
            expired (or (:expired appraisal) [])
            nao-sup (or (:nao_suportado appraisal) [])
            totals (or (:totals appraisal) {})
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
          [:div {:style {:display "flex" :gap "24px" :margin-bottom "16px"
                         :padding "12px" :background t/bg-main
                         :border-radius (:md t/border-radius)}}
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "TOTAL"]
            [:div {:style {:font-size (:xl t/font-sizes) :font-weight (:bold t/font-weights)}}
             (fmt-brl (:total_commission totals))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "EVs"]
            [:div (str (:ev_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Apólices"]
            [:div (str (:policy_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "NFs OK"]
            [:div (str (:matched_nf_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Não match"]
            [:div (str (:unmatched_count totals 0))]]
           [:div [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Fora vig"]
            [:div (str (:expired_count totals 0))]]]

          [tabs/tabs
           {:value @active-tab :on-change #(reset! active-tab %)
            :tabs [{:value :por-ev :label "Por EV"}
                   {:value :unmatched :label (str "Não matcheadas (" (count unmatched) ")")}
                   {:value :expired :label (str "Fora de vigência (" (count expired) ")")}
                   {:value :nao-sup :label (str "Não suportado (" (count nao-sup) ")")}]}]

          (case @active-tab
            :por-ev [por-ev-tab ev-summary]
            :unmatched [unmatched-tab unmatched]
            :expired [expired-tab expired]
            :nao-sup [nao-suportado-tab nao-sup])]]))))
```

**Notas pra implementação:**
- A API exata de `app.ds.tabs/tabs` pode ser ligeiramente diferente do que está aqui. Antes de usar, ler `frontend/src/app/ds/tabs.cljs` e ajustar o map de props.
- `app.ds.inputs/select` já é usado no codebase — manter mesmo padrão.
- Se `app.ds.tabs` não existir, criar usando o padrão dos outros componentes do design system (~50 linhas, similar a `card`).

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
