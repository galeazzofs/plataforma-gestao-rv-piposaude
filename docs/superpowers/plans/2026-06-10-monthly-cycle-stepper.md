# Ciclo Mensal — Trilho Passo-a-Passo: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar a página do Ciclo Mensal num trilho vertical passo-a-passo com seletor de ciclo, faixa de próxima ação e ações de orquestração inline — sem agrupamento por time.

**Architecture:** O backend passa a servir um payload global por componente (`components: {...}` no lugar de `teams: [...]`) via `cycle_aggregator`, ganha 2 endpoints em lote para a Apuração CN e 1 finalize para o Bônus EV. O frontend reescreve `monthly_cycle.cljs` como trilho com uma função pura `next-action` (componente+status → ação), um evento genérico `:revops/cycle-action` (executa → refetch → toast) e seletor de mês persistido em app-db.

**Tech Stack:** Flask + SQLAlchemy + pytest (Postgres `comissoes_test`); ClojureScript + re-frame + reagent + shadow-cljs/karma.

**Spec:** `docs/superpowers/specs/2026-06-10-monthly-cycle-stepper-design.md`

**Desvios conscientes do spec (validar com o usuário se discordar):**
1. **`POST /commissions/ev/bonus/finalize` adicionado.** O spec dizia "Bônus EV já tem ações, sem mudanças", mas NÃO existe endpoint que sete `EvQuarterAchievement.is_final` (só edição manual por EV em admin.py). Sem ele o passo Bônus EV nunca chega a LOCKED e o ciclo nunca auto-fecha. Espelha o `quarterly-bonus/finalize` do CN.
2. **Endpoints em lote sem `log_audit`.** O spec pedia log_audit "como os endpoints existentes" — mas os endpoints existentes de cn_commissions NÃO usam log_audit. Mantida a consistência com o módulo (sem audit).
3. **Campo `expected` nos componentes.** Para preservar o invariante antigo ("CN sem linha bloqueia o lock", garantido antes pelo particionamento por time), os componentes cn/bônus/liderança comparam `rows` com a contagem de usuários ativos do papel; um conjunto todo-LOCKED porém incompleto rebaixa para `CALCULATING`.

**Comandos de teste:**
- Backend (rodar de `backend/`): `python -m pytest <arquivo> -v` (Postgres `comissoes_test` via .env)
- Frontend (rodar de `frontend/`): `npm test` (shadow-cljs compile test + karma)

---

## File Structure

| Arquivo | Mudança | Responsabilidade |
|---|---|---|
| `backend/app/modules/workflow/cycle_aggregator.py` | rewrite | Payload global por componente; lock inalterado |
| `backend/tests/test_modules/test_workflow/test_cycle_orchestration.py` | modify | Testes de payload global; lock tests preservados |
| `backend/tests/test_api/test_monthly_cycles.py` | modify | Asserções do GET /:id no novo shape |
| `backend/app/api/v1/cn_commissions.py` | add | `transition-month` + `finalize-month` (bulk) |
| `backend/tests/test_api/test_cn_bulk_actions.py` | create | Testes dos endpoints em lote |
| `backend/app/api/v1/ev_bonus.py` | add | `POST /bonus/finalize` |
| `backend/tests/test_api/test_ev_bonus_finalize.py` | create | Testes do finalize EV |
| `frontend/src/app/api/endpoints.cljs` | add | 3 novos endpoints |
| `frontend/src/app/views/revops/events.cljs` | add | `:revops/cycle-action` (+done/error), `:revops/select-cycle-month` |
| `frontend/src/app/views/revops/subs.cljs` | add | `:revops/monthly-cycle-selection` |
| `frontend/src/app/views/revops/monthly_cycle.cljs` | rewrite | Trilho + helpers puros (`next-action`, `progress`, …) |
| `frontend/test/app/views/revops/monthly_cycle_test.cljs` | modify | Testes dos helpers puros |
| `frontend/src/app/util/url.cljs` | create | `query-param` (deep links) |
| `frontend/src/app/routes.cljs` | modify | `:navigate!` aceita query params |
| `frontend/src/app/views/revops/{cn_appraisal,ev_bonus,cn_quarterly_bonus,leadership_appraisal}.cljs` | modify | Seed do filtro via query param |

---

### Task 1: Aggregator global (sem times)

**Files:**
- Modify: `backend/app/modules/workflow/cycle_aggregator.py`
- Test: `backend/tests/test_modules/test_workflow/test_cycle_orchestration.py`
- Test: `backend/tests/test_api/test_monthly_cycles.py`

- [ ] **Step 1: Reescrever os testes de payload no module test**

Em `backend/tests/test_modules/test_workflow/test_cycle_orchestration.py`:

1a. Substituir `test_payload_quarter_end_has_full_sequence` (linhas ~138-157) por:

```python
def test_payload_quarter_end_has_full_sequence(db_session, two_teams_setup):
    s = two_teams_setup
    payload = build_cycle_payload(s["cycle"])
    assert payload["month"] == 6
    assert payload["quarter"] == 2
    assert payload["is_quarter_end"] is True
    assert payload["sequence"] == [
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    ]
    assert "teams" not in payload
    assert set(payload["components"].keys()) == {
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    }
```

1b. Substituir `test_payload_mid_quarter_has_only_apuracoes` (linhas ~160-176) por:

```python
def test_payload_mid_quarter_has_only_apuracoes(db_session, two_teams_setup):
    s = two_teams_setup
    cycle = MonthlyCycle(
        month=5, year=s["year"],
        status=MonthlyCycleStatus.OPEN,
        created_by=s["admin"].id,
    )
    db.session.add(cycle)
    db.session.flush()

    payload = build_cycle_payload(cycle)
    assert payload["is_quarter_end"] is False
    assert payload["sequence"] == ["ev_apuracao", "cn_apuracao"]
    assert "teams" not in payload
    assert set(payload["components"].keys()) == {"ev_apuracao", "cn_apuracao"}
```

1c. Renomear `test_cycle_does_not_lock_when_team_b_is_behind` (linhas ~179-197) para o novo invariante global (corpo igual, asserção extra):

```python
def test_cycle_does_not_lock_while_any_cn_row_missing(db_session, two_teams_setup):
    """A LOCKED-only CN row set that misses an active CN must hold the
    component (and the cycle) open — the per-team payload guaranteed this
    via the missing team's PENDING; the global payload uses `expected`."""
    s = two_teams_setup
    # CN A: every component LOCKED; CN B: no rows at all.
    _lock_team_components(
        s["ev_a"], s["cn_a"], s["lider_a"], s["month"], s["year"],
    )
    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.LIDER_REVIEW,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    components = build_cycle_payload(s["cycle"])["components"]
    assert components["cn_apuracao"]["rows"] == 1
    assert components["cn_apuracao"]["expected"] == 2
    assert components["cn_apuracao"]["status"] == "CALCULATING"

    assert all_components_locked(s["cycle"]) is False
    assert maybe_lock_cycle(s["cycle"]) is False
    assert s["cycle"].status == MonthlyCycleStatus.OPEN
```

1d. Adicionar ao final do arquivo:

```python
def test_ev_apuracao_component_exposes_appraisal_id(db_session, two_teams_setup):
    s = two_teams_setup
    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.DRAFT,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["ev_apuracao"]
    assert comp["status"] == "DRAFT"
    assert comp["appraisal_id"] == str(appraisal.id)


def test_ev_apuracao_component_pending_without_appraisal(
    db_session, two_teams_setup,
):
    s = two_teams_setup
    comp = build_cycle_payload(s["cycle"])["components"]["ev_apuracao"]
    assert comp["status"] == "PENDING"
    assert comp["appraisal_id"] is None
    assert comp["validations_total"] == 0


def test_leadership_component_exposes_single_row_id(db_session, two_teams_setup):
    s = two_teams_setup
    row = LiderVendasQuarterAppraisal(
        lider_vendas_id=s["lider_a"].id, quarter=s["quarter"], year=s["year"],
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=AppraisalStatus.REVOPS_REVIEW,
    )
    db.session.add(row)
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["leadership_bonus"]
    assert comp["status"] == "REVOPS_REVIEW"
    assert comp["appraisal_id"] == str(row.id)
    assert comp["rows"] == 1
    assert comp["expected"] == 2  # fixture has 2 active LIDER_VENDAS


def test_bonus_component_incomplete_final_set_stays_calculating(
    db_session, two_teams_setup,
):
    """All-final bonus rows that miss an eligible user must not read LOCKED."""
    s = two_teams_setup
    db.session.add(EvQuarterAchievement(
        ev_id=s["ev_a"].id, quarter=s["quarter"], year=s["year"],
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=True,
    ))
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["ev_bonus"]
    assert comp["rows"] == 1
    assert comp["final"] == 1
    assert comp["expected"] == 2  # ev_a + ev_b
    assert comp["status"] == "CALCULATING"
```

- [ ] **Step 2: Atualizar as asserções do API test**

Em `backend/tests/test_api/test_monthly_cycles.py`, substituir o corpo dos dois testes de componentes:

`test_get_cycle_returns_base_sequence_components` — substituir as 4 linhas finais (`assert body["sequence"] ...` até o `for team ...`) por:

```python
    assert body["sequence"] == ["ev_apuracao", "cn_apuracao"]
    assert "teams" not in body
    assert set(body["components"].keys()) == {"ev_apuracao", "cn_apuracao"}
    assert body["components"]["ev_apuracao"]["status"] == "PENDING"
```

`test_get_quarter_end_cycle_returns_bonus_components` — substituir o bloco final (`for team in body["teams"]: ...`) por:

```python
    assert "teams" not in body
    assert set(body["components"].keys()) == {
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    }
```

- [ ] **Step 3: Rodar os testes para confirmar que falham**

```powershell
cd backend
python -m pytest tests/test_modules/test_workflow/test_cycle_orchestration.py tests/test_api/test_monthly_cycles.py -v
```

Expected: FAIL — `KeyError: 'components'` / asserções de `teams` nos testes novos.

- [ ] **Step 4: Reescrever o aggregator**

Substituir o conteúdo COMPLETO de `backend/app/modules/workflow/cycle_aggregator.py` por:

```python
"""Build the global component status for a MonthlyCycle.

The cycle is an orchestration shell over the monthly apuração sequence:

  1. Apuração EV        — monthly Appraisal (one per month)
  2. Apuração CN        — CnMonthlyAppraisal of the cycle month (per CN)

and, only on quarter-end months (3, 6, 9, 12), the quarterly bonuses:

  3. Bônus CN           — CnQuarterBonus (per CN)
  4. Bônus EV           — EvQuarterAchievement (per EV)
  5. Bônus Liderança    — LiderVendasQuarterAppraisal (per Líder)

Components are aggregated globally — there is no per-team partition.
Each component also reports `expected` (eligible-user count) where rows
are per-user: an all-LOCKED set that misses an eligible user must not
read LOCKED, otherwise the cycle could auto-close with work missing.
"""
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, EvValidation, LiderVendasQuarterAppraisal,
    MonthlyCycle, MonthlyCycleStatus, User, UserRole,
    ValidationStatus,
)


BASE_SEQUENCE = ["ev_apuracao", "cn_apuracao"]
QUARTER_END_SEQUENCE = BASE_SEQUENCE + ["cn_bonus", "ev_bonus", "leadership_bonus"]


def component_sequence(month: int) -> list:
    """Ordered component keys for a cycle month. Quarterly bonuses only
    exist on the last month of each quarter."""
    return QUARTER_END_SEQUENCE if month % 3 == 0 else BASE_SEQUENCE


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _active_count(role: UserRole, exclude_left: bool = False) -> int:
    q = User.query.filter_by(role=role, active=True)
    if exclude_left:
        q = q.filter_by(left_company=False)
    return q.count()


def _ev_apuracao_status(month: int, year: int) -> dict:
    """Status of the Apuração EV component: the month's Appraisal plus
    its global validation progress."""
    appraisal = Appraisal.query.filter_by(month=month, year=year).first()
    if appraisal is None:
        return {"status": "PENDING", "appraisal_id": None,
                "validations_total": 0, "validations_done": 0}

    validations = EvValidation.query.filter_by(
        appraisal_id=appraisal.id,
    ).all()
    done = sum(
        1 for v in validations
        if v.status in (
            ValidationStatus.APPROVED, ValidationStatus.AUTO_APPROVED,
            ValidationStatus.RESOLVED,
        )
    )
    return {
        "status": appraisal.status.value,
        "appraisal_id": str(appraisal.id),
        "validations_total": len(validations),
        "validations_done": done,
    }


def _summarize_status_set(statuses: list) -> str:
    """Reduce a list of component-row statuses into one status.

    Rules:
      - empty / no rows → PENDING
      - all LOCKED → LOCKED
      - any in REVOPS_REVIEW → REVOPS_REVIEW
      - any in LIDER_REVIEW → LIDER_REVIEW
      - any in VALIDATING → VALIDATING
      - any in CALCULATING → CALCULATING
      - else → DRAFT
    """
    if not statuses:
        return "PENDING"
    s = set(statuses)
    if s == {AppraisalStatus.LOCKED}:
        return "LOCKED"
    for level in (
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.VALIDATING,
        AppraisalStatus.CALCULATING,
    ):
        if level in s:
            return level.value
    return "DRAFT"


def _hold_open_if_incomplete(status: str, rows: int, expected: int) -> str:
    """An all-LOCKED row set that misses an eligible user is not done:
    someone's apuração was never created. Hold the component open."""
    if status == "LOCKED" and rows < expected:
        return "CALCULATING"
    return status


def _cn_apuracao_status(month: int, year: int) -> dict:
    expected = _active_count(UserRole.CN)
    rows = CnMonthlyAppraisal.query.filter_by(year=year, month=month).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "expected": expected,
                "month": month}
    status = _summarize_status_set([r.status for r in rows])
    return {
        "status": _hold_open_if_incomplete(status, len(rows), expected),
        "rows": len(rows),
        "expected": expected,
        "month": month,
    }


def _bonus_rows_status(rows: list, expected: int) -> dict:
    final = sum(1 for r in rows if r.is_final)
    if not rows:
        return {"status": "PENDING", "rows": 0, "final": 0,
                "expected": expected}
    status = "LOCKED" if all(r.is_final for r in rows) else "CALCULATING"
    return {
        "status": _hold_open_if_incomplete(status, len(rows), expected),
        "rows": len(rows),
        "final": final,
        "expected": expected,
    }


def _cn_bonus_status(quarter: int, year: int) -> dict:
    rows = CnQuarterBonus.query.filter_by(quarter=quarter, year=year).all()
    return _bonus_rows_status(rows, _active_count(UserRole.CN))


def _ev_bonus_status(quarter: int, year: int) -> dict:
    rows = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year,
    ).all()
    return _bonus_rows_status(
        rows, _active_count(UserRole.EV, exclude_left=True),
    )


def _leadership_status(quarter: int, year: int) -> dict:
    expected = _active_count(UserRole.LIDER_VENDAS)
    rows = LiderVendasQuarterAppraisal.query.filter_by(
        quarter=quarter, year=year,
    ).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "expected": expected,
                "appraisal_id": None, "has_contestation": False}
    status = _summarize_status_set([r.status for r in rows])
    return {
        "status": _hold_open_if_incomplete(status, len(rows), expected),
        "rows": len(rows),
        "expected": expected,
        # The inline transition buttons need a row id; with the single
        # Líder P/M there is exactly one. Ambiguous (2+) → None, the UI
        # falls back to the detail page.
        "appraisal_id": str(rows[0].id) if len(rows) == 1 else None,
        "has_contestation": any(r.has_contestation for r in rows),
    }


def _components(cycle: MonthlyCycle) -> dict:
    month, year = cycle.month, cycle.year
    quarter = _quarter_of(month)
    components = {
        "ev_apuracao": _ev_apuracao_status(month, year),
        "cn_apuracao": _cn_apuracao_status(month, year),
    }
    if month % 3 == 0:
        components["cn_bonus"] = _cn_bonus_status(quarter, year)
        components["ev_bonus"] = _ev_bonus_status(quarter, year)
        components["leadership_bonus"] = _leadership_status(quarter, year)
    return components


def build_cycle_payload(cycle: MonthlyCycle) -> dict:
    """Return the global per-component payload for a cycle."""
    return {
        "id": str(cycle.id),
        "month": cycle.month,
        "year": cycle.year,
        "quarter": cycle.quarter,
        "is_quarter_end": cycle.is_quarter_end,
        "sequence": component_sequence(cycle.month),
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
        "components": _components(cycle),
    }


def all_components_locked(cycle: MonthlyCycle) -> bool:
    """True iff every component in the cycle is LOCKED. PENDING counts as
    not-locked: a cycle with no work in a component must not auto-LOCK."""
    payload = build_cycle_payload(cycle)
    return all(
        comp.get("status") == "LOCKED"
        for comp in payload["components"].values()
    )


def maybe_lock_cycle(cycle: MonthlyCycle) -> bool:
    """Auto-LOCK the cycle if every component is LOCKED. Returns True
    when the cycle transitioned to LOCKED in this call."""
    from datetime import datetime, timezone
    if cycle.status == MonthlyCycleStatus.LOCKED:
        return False
    if not all_components_locked(cycle):
        return False
    cycle.status = MonthlyCycleStatus.LOCKED
    cycle.locked_at = datetime.now(timezone.utc)
    db.session.flush()
    return True
```

Nota: o import de `Team` saiu; `_month_appraisal` foi absorvida por `_ev_apuracao_status`.

- [ ] **Step 5: Rodar os testes do Task 1**

```powershell
cd backend
python -m pytest tests/test_modules/test_workflow/test_cycle_orchestration.py tests/test_api/test_monthly_cycles.py -v
```

Expected: PASS (todos — incluindo os lock tests intocados: `test_mid_quarter_cycle_locks_without_bonuses`, `test_quarter_end_cycle_locks_when_all_teams_complete`, `test_cycle_locks_from_cn_monthly_when_appraisal_already_locked`, `test_cycle_locks_from_leadership_lock`).

- [ ] **Step 6: Procurar outros consumidores do payload por time**

```powershell
cd backend
python -m pytest tests/ -x -q
```

Expected: PASS. Se algum teste fora dos dois arquivos quebrar com `KeyError: 'teams'`, corrigir o consumidor para ler `components` global (mesma informação, sem o nível de time).

- [ ] **Step 7: Commit**

```powershell
git add backend/app/modules/workflow/cycle_aggregator.py backend/tests/test_modules/test_workflow/test_cycle_orchestration.py backend/tests/test_api/test_monthly_cycles.py
git commit -m "refactor: global (team-less) MonthlyCycle component payload"
```

---

### Task 2: Endpoints em lote da Apuração CN

**Files:**
- Modify: `backend/app/api/v1/cn_commissions.py` (inserir após `transition_cn_appraisal_endpoint`, ~linha 320)
- Create: `backend/tests/test_api/test_cn_bulk_actions.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_api/test_cn_bulk_actions.py`:

```python
"""Tests for the month-level bulk CN appraisal actions
(POST /commissions/cn/appraisal/transition-month and /finalize-month)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal,
    MonthlyCycle, MonthlyCycleStatus, User, UserRole,
)
from app.auth.jwt_manager import create_access_token

MONTH, YEAR = 5, 2033


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_user(role, name):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower()}-{suffix}@x", name=name, role=role,
        active=True, salario_base=Decimal("8000"),
    )
    db.session.add(u)
    db.session.flush()
    return u


def _add_cn_row(cn_user, status, contested=False):
    row = CnMonthlyAppraisal(
        cn_id=cn_user.id, month=MONTH, year=YEAR,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"), status=status,
        has_contestation=contested,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def setup():
    admin = _make_user(UserRole.ADMIN, "BulkAdmin")
    cn_a = _make_user(UserRole.CN, "BulkCnA")
    cn_b = _make_user(UserRole.CN, "BulkCnB")
    return {"admin": admin, "cn_a": cn_a, "cn_b": cn_b}


def test_transition_month_advances_all_rows(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.CALCULATING)
    _add_cn_row(s["cn_b"], AppraisalStatus.CALCULATING)

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 2
    assert data["skipped"] == []
    statuses = {
        r.status for r in CnMonthlyAppraisal.query.filter_by(
            month=MONTH, year=YEAR,
        ).all()
    }
    assert statuses == {AppraisalStatus.VALIDATING}


def test_transition_month_is_idempotent(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.CALCULATING)

    for expected_advanced in (1, 0):
        resp = client.post(
            "/api/v1/commissions/cn/appraisal/transition-month",
            json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
            headers=_auth_header(s["admin"]),
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["advanced"] == expected_advanced


def test_transition_month_skips_contested_rows(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.VALIDATING)
    contested = _add_cn_row(
        s["cn_b"], AppraisalStatus.VALIDATING, contested=True,
    )

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "LIDER_REVIEW"},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 1
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["cn_id"] == str(s["cn_b"].id)
    db.session.refresh(contested)
    assert contested.status == AppraisalStatus.VALIDATING


def test_transition_month_404_without_rows(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": 11, "year": 2099, "to": "VALIDATING"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 404


def test_transition_month_validates_body(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "NOT_A_STATUS"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_transition_month_requires_admin(client, setup):
    cn = setup["cn_a"]
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
        headers=_auth_header(cn),
    )
    assert resp.status_code == 403


def test_finalize_month_locks_all_and_skips_contested(client, setup):
    s = setup
    clean = _add_cn_row(s["cn_a"], AppraisalStatus.REVOPS_REVIEW)
    contested = _add_cn_row(
        s["cn_b"], AppraisalStatus.REVOPS_REVIEW, contested=True,
    )

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 1
    assert len(data["skipped"]) == 1
    db.session.refresh(clean)
    db.session.refresh(contested)
    assert clean.status == AppraisalStatus.LOCKED
    assert contested.status == AppraisalStatus.REVOPS_REVIEW


def test_finalize_month_triggers_cycle_autolock(client, setup):
    """Locking the last CN row must re-evaluate the month's cycle."""
    s = setup
    cycle = MonthlyCycle(
        month=MONTH, year=YEAR,
        status=MonthlyCycleStatus.OPEN, created_by=s["admin"].id,
    )
    db.session.add(cycle)
    # Apuração EV already LOCKED — the CN rows are the last gate.
    db.session.add(Appraisal(
        month=MONTH, year=YEAR,
        status=AppraisalStatus.LOCKED, created_by=s["admin"].id,
    ))
    _add_cn_row(s["cn_a"], AppraisalStatus.REVOPS_REVIEW)
    _add_cn_row(s["cn_b"], AppraisalStatus.REVOPS_REVIEW)
    db.session.flush()

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(cycle)
    assert cycle.status == MonthlyCycleStatus.LOCKED


def test_finalize_month_requires_admin(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(setup["cn_a"]),
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Rodar para confirmar que falham**

```powershell
cd backend
python -m pytest tests/test_api/test_cn_bulk_actions.py -v
```

Expected: FAIL — 404 (rota não existe) nos testes que esperam 200/400/403.

- [ ] **Step 3: Implementar os endpoints**

Em `backend/app/api/v1/cn_commissions.py`, inserir imediatamente após a função `transition_cn_appraisal_endpoint` (após a linha `return jsonify({"data": _serialize_appraisal(appraisal)})`, ~linha 319):

```python
@cn_commissions_bp.route("/appraisal/transition-month", methods=["POST"])
@require_auth
def transition_cn_month():
    """Bulk-advance every CN monthly appraisal of (month, year).

    Rows already in the target status are ignored; rows with an open
    contestation or an invalid source state are skipped and reported —
    they never block the rest. ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        month = int(body["month"])
        year = int(body["year"])
        new_status = AppraisalStatus(body["to"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month, year and to (valid status) required"},
        }), 400

    rows = CnMonthlyAppraisal.query.filter_by(month=month, year=year).all()
    if not rows:
        return jsonify({
            "error": {"code": "NOT_FOUND",
                      "message": f"No CN appraisals for {month:02d}/{year}"},
        }), 404

    advanced, skipped = 0, []
    for row in rows:
        if row.status == new_status:
            continue
        if row.has_contestation:
            skipped.append({"cn_id": str(row.cn_id),
                            "reason": "contestação aberta"})
            continue
        try:
            transition_cn_monthly_appraisal(row, new_status)
            advanced += 1
        except InvalidTransitionError as e:
            skipped.append({"cn_id": str(row.cn_id), "reason": str(e)})
    db.session.commit()
    return jsonify({"data": {"advanced": advanced, "skipped": skipped,
                             "to": new_status.value}})


@cn_commissions_bp.route("/appraisal/finalize-month", methods=["POST"])
@require_auth
def finalize_cn_month():
    """Bulk-finalize: walk every non-LOCKED CN appraisal of (month, year)
    through the state machine to LOCKED. Contested rows are skipped.
    The last LOCK re-evaluates the month's cycle (inside the state
    machine). ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        month = int(body["month"])
        year = int(body["year"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month and year required (integers)"},
        }), 400

    rows = CnMonthlyAppraisal.query.filter_by(month=month, year=year).all()
    if not rows:
        return jsonify({
            "error": {"code": "NOT_FOUND",
                      "message": f"No CN appraisals for {month:02d}/{year}"},
        }), 404

    chain = [
        AppraisalStatus.VALIDATING,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LOCKED,
    ]
    advanced, skipped = 0, []
    for row in rows:
        if row.status == AppraisalStatus.LOCKED:
            continue
        if row.has_contestation:
            skipped.append({"cn_id": str(row.cn_id),
                            "reason": "contestação aberta"})
            continue
        try:
            for s in chain:
                if row.status == s:
                    continue
                transition_cn_monthly_appraisal(row, s)
            advanced += 1
        except InvalidTransitionError as e:
            skipped.append({"cn_id": str(row.cn_id), "reason": str(e)})
    db.session.commit()
    return jsonify({"data": {"advanced": advanced, "skipped": skipped}})
```

(Os imports necessários — `AppraisalStatus`, `CnMonthlyAppraisal`, `transition_cn_monthly_appraisal`, `InvalidTransitionError` — já existem no topo do arquivo.)

- [ ] **Step 4: Rodar os testes**

```powershell
cd backend
python -m pytest tests/test_api/test_cn_bulk_actions.py -v
```

Expected: PASS (9 testes).

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/cn_commissions.py backend/tests/test_api/test_cn_bulk_actions.py
git commit -m "feat: month-level bulk transition/finalize for CN appraisals"
```

---

### Task 3: Finalize do Bônus EV

**Files:**
- Modify: `backend/app/api/v1/ev_bonus.py`
- Create: `backend/tests/test_api/test_ev_bonus_finalize.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_api/test_ev_bonus_finalize.py`:

```python
"""Tests for POST /commissions/ev/bonus/finalize."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import EvQuarterAchievement, User, UserRole
from app.auth.jwt_manager import create_access_token

QUARTER, YEAR = 2, 2033


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_user(role, name):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower()}-{suffix}@x", name=name, role=role,
        active=True, salario_base=Decimal("8000"),
    )
    db.session.add(u)
    db.session.flush()
    return u


def _add_achievement(ev, is_final=False):
    row = EvQuarterAchievement(
        ev_id=ev.id, quarter=QUARTER, year=YEAR,
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=is_final,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def setup():
    return {
        "admin": _make_user(UserRole.ADMIN, "EvFinAdmin"),
        "ev_a": _make_user(UserRole.EV, "EvFinA"),
        "ev_b": _make_user(UserRole.EV, "EvFinB"),
    }


def test_finalize_locks_all_non_final_rows(client, setup):
    s = setup
    row_a = _add_achievement(s["ev_a"])
    row_b = _add_achievement(s["ev_b"], is_final=True)

    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": QUARTER, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["finalized"] == 1
    db.session.refresh(row_a)
    db.session.refresh(row_b)
    assert row_a.is_final is True
    assert row_b.is_final is True


def test_finalize_validates_body(client, setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": "x"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_finalize_requires_admin(client, setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": QUARTER, "year": YEAR},
        headers=_auth_header(setup["ev_a"]),
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Rodar para confirmar que falham**

```powershell
cd backend
python -m pytest tests/test_api/test_ev_bonus_finalize.py -v
```

Expected: FAIL — 404 (rota não existe).

- [ ] **Step 3: Implementar o endpoint**

Em `backend/app/api/v1/ev_bonus.py`:

3a. Apagar o comentário desatualizado das linhas 9-10:

```python
# NOTE: EV bonus finalization (locking is_final=True) is out of scope for this branch.
# The EvQuarterAchievement.is_final flag is set externally via the quarterly close flow.
```

3b. Adicionar ao final do arquivo (após `_serialize`):

```python
@ev_bonus_bp.route("/bonus/finalize", methods=["POST"])
@require_auth
def finalize_bonus():
    """Lock all non-final EV quarter achievements for (quarter, year).
    Mirrors the CN quarterly-bonus finalize; the last final row may
    complete the quarter-end month's cycle. ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        quarter = int(body.get("quarter"))
        year = int(body.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter and year required (integers)"},
        }), 400

    rows = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year, is_final=False,
    ).all()
    for row in rows:
        row.is_final = True
    db.session.commit()

    # Locking the last bonus row may complete the quarter-end cycle.
    from app.modules.workflow.state_machine import _maybe_lock_attached_cycle
    try:
        _maybe_lock_attached_cycle(quarter * 3, year)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({"data": {"finalized": len(rows)}})
```

- [ ] **Step 4: Rodar os testes**

```powershell
cd backend
python -m pytest tests/test_api/test_ev_bonus_finalize.py -v
```

Expected: PASS (3 testes).

- [ ] **Step 5: Rodar a suíte backend completa e commitar**

```powershell
cd backend
python -m pytest tests/ -q
```

Expected: PASS.

```powershell
git add backend/app/api/v1/ev_bonus.py backend/tests/test_api/test_ev_bonus_finalize.py
git commit -m "feat: quarter-level finalize endpoint for EV bonus"
```

---

### Task 4: Frontend — endpoints, eventos e sub

**Files:**
- Modify: `frontend/src/app/api/endpoints.cljs`
- Modify: `frontend/src/app/views/revops/events.cljs` (após o bloco "Monthly Cycles", ~linha 810)
- Modify: `frontend/src/app/views/revops/subs.cljs` (após `:revops/monthly-cycle-loading?`, ~linha 168)

- [ ] **Step 1: Adicionar endpoints**

Em `frontend/src/app/api/endpoints.cljs`, no bloco "CN commissions" (após a linha de `cn-appraisal-finalize`):

```clojure
(def cn-appraisal-transition-month "/commissions/cn/appraisal/transition-month")
(def cn-appraisal-finalize-month   "/commissions/cn/appraisal/finalize-month")
```

E no bloco "EV bonus" (após `ev-bonus`):

```clojure
(def ev-bonus-finalize  "/commissions/ev/bonus/finalize")
```

- [ ] **Step 2: Adicionar eventos**

Em `frontend/src/app/views/revops/events.cljs`, inserir após `:revops/monthly-cycle-delete-error` (linha ~810), antes do bloco "Appraisal contestation":

```clojure
;; ---- Monthly cycle: inline orchestration actions ----
;; One generic event powers every step button on the cycle rail:
;; run the request, then refetch the cycle payload (single source of
;; truth — no optimistic state) and toast the outcome.

(rf/reg-event-db
 :revops/select-cycle-month
 (fn [db [_ selection]]
   (assoc-in db [:appraisal :monthly-cycle-selection] selection)))

(rf/reg-event-fx
 :revops/cycle-action
 (fn [_ [_ {:keys [method url body success-msg cycle-id]}]]
   {:http {:method     (or method :post)
           :url        url
           :body       body
           :on-success [:revops/cycle-action-done cycle-id success-msg]
           :on-failure [:revops/cycle-action-error cycle-id]}}))

(rf/reg-event-fx
 :revops/cycle-action-done
 (fn [_ [_ cycle-id success-msg resp]]
   (let [skipped (get-in resp [:data :skipped])
         msg     (if (seq skipped)
                   (str success-msg " · " (count skipped)
                        " pulado(s) — ver detalhes")
                   success-msg)]
     {:dispatch-n [[:revops/fetch-monthly-cycle-detail cycle-id]
                   [:revops/fetch-monthly-cycles]
                   [:ui/show-toast {:type :success :message msg}]]})))

(rf/reg-event-fx
 :revops/cycle-action-error
 (fn [_ [_ cycle-id resp]]
   (let [msg (or (get-in resp [:error :message])
                 "Erro ao executar a ação")]
     {:dispatch-n [[:revops/fetch-monthly-cycle-detail cycle-id]
                   [:ui/show-toast {:type :error :message msg}]]})))
```

- [ ] **Step 3: Adicionar sub**

Em `frontend/src/app/views/revops/subs.cljs`, após `:revops/monthly-cycle-loading?`:

```clojure
(rf/reg-sub
 :revops/monthly-cycle-selection
 (fn [db _]
   (get-in db [:appraisal :monthly-cycle-selection])))
```

- [ ] **Step 4: Verificar compilação e commitar**

```powershell
cd frontend
npm test
```

Expected: compila e os testes existentes passam (nada novo testado ainda).

```powershell
git add frontend/src/app/api/endpoints.cljs frontend/src/app/views/revops/events.cljs frontend/src/app/views/revops/subs.cljs
git commit -m "feat: cycle inline-action events, selection state and endpoints"
```

---

### Task 5: Frontend — helpers puros do trilho (TDD)

**Files:**
- Modify: `frontend/src/app/views/revops/monthly_cycle.cljs` (adicionar helpers; a view é reescrita no Task 6)
- Test: `frontend/test/app/views/revops/monthly_cycle_test.cljs`

- [ ] **Step 1: Escrever os testes (falhando)**

Adicionar ao final de `frontend/test/app/views/revops/monthly_cycle_test.cljs` (manter os deftests existentes — `suggest-cycle-test` e `components-for-test` continuam valendo):

```clojure
(deftest component-of-test
  (testing "reads keyword and string keys from the payload"
    (is (= {:status "DRAFT"}
           (mc/component-of {:components {:ev_apuracao {:status "DRAFT"}}}
                            "ev_apuracao")))
    (is (= {:status "DRAFT"}
           (mc/component-of {:components {"ev_apuracao" {:status "DRAFT"}}}
                            "ev_apuracao")))))

(deftest current-step-key-test
  (let [cycle {:month 6 :is_quarter_end true
               :components {:ev_apuracao {:status "LOCKED"}
                            :cn_apuracao {:status "VALIDATING"}
                            :cn_bonus    {:status "PENDING"}
                            :ev_bonus    {:status "PENDING"}
                            :leadership_bonus {:status "PENDING"}}}]
    (testing "first non-LOCKED component in sequence order"
      (is (= "cn_apuracao" (mc/current-step-key cycle))))
    (testing "fully locked cycle has no current step"
      (is (nil? (mc/current-step-key
                 {:month 5 :is_quarter_end false
                  :components {:ev_apuracao {:status "LOCKED"}
                               :cn_apuracao {:status "LOCKED"}}}))))))

(deftest progress-test
  (is (= {:done 1 :total 5}
         (mc/progress {:month 6 :is_quarter_end true
                       :components {:ev_apuracao {:status "LOCKED"}
                                    :cn_apuracao {:status "DRAFT"}
                                    :cn_bonus    {:status "PENDING"}
                                    :ev_bonus    {:status "PENDING"}
                                    :leadership_bonus {:status "PENDING"}}})))
  (is (= {:done 0 :total 2}
         (mc/progress {:month 5 :is_quarter_end false :components {}}))))

(deftest month-navigation-test
  (is (= {:month 4 :year 2026} (mc/prev-month {:month 5 :year 2026})))
  (is (= {:month 12 :year 2025} (mc/prev-month {:month 1 :year 2026})))
  (is (= {:month 6 :year 2026}
         (:selected (let [c {:month 6 :year 2026 :id "x"}]
                      {:selected (select-keys
                                  (mc/cycle-for-month [c] {:month 6 :year 2026})
                                  [:month :year])}))))
  (is (nil? (mc/cycle-for-month [{:month 5 :year 2026}] {:month 6 :year 2026}))))

(deftest next-action-test
  (let [cycle {:id "cy1" :month 6 :year 2026 :quarter 2 :is_quarter_end true}]
    (testing "EV apuração PENDING → create"
      (let [a (mc/next-action "ev_apuracao" {:status "PENDING"} cycle)]
        (is (= :request (:kind a)))
        (is (= "/appraisals" (:url a)))
        (is (= {:month 6 :year 2026} (:body a)))))
    (testing "EV apuração DRAFT → run calc via transition"
      (let [a (mc/next-action "ev_apuracao"
                              {:status "DRAFT" :appraisal_id "ap1"} cycle)]
        (is (= "/appraisals/ap1/transition" (:url a)))
        (is (= {:to "CALCULATING"} (:body a)))))
    (testing "EV apuração VALIDATING → no admin action (EVs validate)"
      (is (nil? (mc/next-action "ev_apuracao"
                                {:status "VALIDATING" :appraisal_id "ap1"}
                                cycle))))
    (testing "EV apuração REVOPS_REVIEW → lock with confirm"
      (let [a (mc/next-action "ev_apuracao"
                              {:status "REVOPS_REVIEW" :appraisal_id "ap1"}
                              cycle)]
        (is (= {:to "LOCKED"} (:body a)))
        (is (true? (:confirm? a)))))
    (testing "CN apuração PENDING → navigate to the detail page (inputs live there)"
      (let [a (mc/next-action "cn_apuracao" {:status "PENDING"} cycle)]
        (is (= :navigate (:kind a)))
        (is (= :revops/cn-appraisal (:route a)))))
    (testing "CN apuração CALCULATING → bulk transition to VALIDATING"
      (let [a (mc/next-action "cn_apuracao" {:status "CALCULATING"} cycle)]
        (is (= "/commissions/cn/appraisal/transition-month" (:url a)))
        (is (= {:month 6 :year 2026 :to "VALIDATING"} (:body a)))))
    (testing "CN apuração REVOPS_REVIEW → bulk finalize"
      (let [a (mc/next-action "cn_apuracao" {:status "REVOPS_REVIEW"} cycle)]
        (is (= "/commissions/cn/appraisal/finalize-month" (:url a)))
        (is (= {:month 6 :year 2026} (:body a)))
        (is (true? (:confirm? a)))))
    (testing "Bônus CN PENDING → run; CALCULATING → finalize"
      (is (= "/commissions/cn/quarterly-bonus"
             (:url (mc/next-action "cn_bonus" {:status "PENDING"} cycle))))
      (is (= "/commissions/cn/quarterly-bonus/finalize"
             (:url (mc/next-action "cn_bonus" {:status "CALCULATING"} cycle)))))
    (testing "Bônus EV PENDING → run; CALCULATING → finalize"
      (is (= {:quarter 2 :year 2026}
             (:body (mc/next-action "ev_bonus" {:status "PENDING"} cycle))))
      (is (= "/commissions/ev/bonus/finalize"
             (:url (mc/next-action "ev_bonus" {:status "CALCULATING"} cycle)))))
    (testing "Liderança PENDING → navigate (inputs live there)"
      (is (= :navigate
             (:kind (mc/next-action "leadership_bonus" {:status "PENDING"} cycle)))))
    (testing "Liderança transitions need the row id"
      (is (nil? (mc/next-action "leadership_bonus"
                                {:status "LIDER_REVIEW" :appraisal_id nil}
                                cycle)))
      (is (= "/commissions/leadership/appraisal/ld1/transition"
             (:url (mc/next-action "leadership_bonus"
                                   {:status "LIDER_REVIEW" :appraisal_id "ld1"}
                                   cycle)))))
    (testing "LOCKED components have no action"
      (is (nil? (mc/next-action "ev_apuracao" {:status "LOCKED"} cycle)))
      (is (nil? (mc/next-action "cn_bonus" {:status "LOCKED"} cycle))))))
```

- [ ] **Step 2: Rodar para confirmar que falham**

```powershell
cd frontend
npm test
```

Expected: FAIL — `mc/component-of`, `mc/next-action` etc. não existem.

- [ ] **Step 3: Implementar os helpers**

Em `frontend/src/app/views/revops/monthly_cycle.cljs`:

3a. Atualizar o ns para:

```clojure
(ns app.views.revops.monthly-cycle
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))
```

3b. Adicionar os helpers puros após `cycle-label` (antes de `status->badge`):

```clojure
;; ── Pure rail helpers ───────────────────────────────────────────────

(defn component-of
  "Component map for key `k` — payload keys may arrive as keywords or
   strings depending on the JSON decoding path."
  [cycle k]
  (or (get-in cycle [:components (keyword k)])
      (get-in cycle [:components k])))

(defn current-step-key
  "First component in sequence order that is not LOCKED — the step the
   admin should be working on. nil when everything is locked."
  [cycle]
  (->> (components-for cycle)
       (map first)
       (remove #(= "LOCKED" (:status (component-of cycle %))))
       first))

(defn progress
  "{:done n :total m} counting LOCKED components."
  [cycle]
  (let [ks (map first (components-for cycle))]
    {:done  (count (filter #(= "LOCKED" (:status (component-of cycle %))) ks))
     :total (count ks)}))

(defn prev-month [{:keys [month year]}]
  (if (> month 1)
    {:month (dec month) :year year}
    {:month 12 :year (dec year)}))

(defn cycle-for-month [cycles {:keys [month year]}]
  (first (filter #(and (= (:month %) month) (= (:year %) year))
                 (or cycles []))))

(defn next-action
  "Primary inline action for component `k` in its current state.
   {:kind :request ...} actions run through :revops/cycle-action;
   {:kind :navigate :route ...} deep-link to the detail page (work that
   needs inputs). nil = nothing for the admin to click right now."
  [k component cycle]
  (let [{:keys [status appraisal_id rows expected]} component
        {:keys [month year quarter]} cycle]
    (case k
      "ev_apuracao"
      (case status
        "PENDING"
        {:kind :request :label "Criar apuração (DRAFT)"
         :method :post :url (ep/appraisals)
         :body {:month month :year year}
         :success-msg "Apuração criada em DRAFT."}
        "DRAFT"
        (when appraisal_id
          {:kind :request :label "Rodar cálculo"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "CALCULATING"}
           :success-msg "Cálculo concluído. Revise antes de liberar."})
        "CALCULATING"
        (when appraisal_id
          {:kind :request :label "Liberar para validação"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "VALIDATING"}
           :success-msg "Liberado para validação dos EVs."})
        "VALIDATING" nil
        "LIDER_REVIEW"
        (when appraisal_id
          {:kind :request :label "Avançar para revisão RevOps"
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "REVOPS_REVIEW"}
           :success-msg "Enviado para revisão RevOps."})
        "REVOPS_REVIEW"
        (when appraisal_id
          {:kind :request :label "Travar (LOCKED)" :confirm? true
           :method :post :url (str "/appraisals/" appraisal_id "/transition")
           :body {:to "LOCKED"}
           :success-msg "Apuração EV travada."})
        nil)

      "cn_apuracao"
      (case status
        "PENDING"
        {:kind :navigate :label "Preparar e rodar →"
         :route :revops/cn-appraisal}
        ("DRAFT" "CALCULATING")
        (if (and rows expected (< rows expected))
          ;; Incomplete row set (e.g. CN hired after the run): bulk
          ;; transitions would no-op — the remedy is re-running from the
          ;; detail page, which recreates non-LOCKED rows for all CNs.
          {:kind :navigate :label "Completar apuração →"
           :route :revops/cn-appraisal}
          {:kind :request :label "Liberar para validação"
           :method :post :url ep/cn-appraisal-transition-month
           :body {:month month :year year :to "VALIDATING"}
           :success-msg "CNs liberados para validação."})
        "VALIDATING"
        {:kind :request :label "Avançar para revisão do líder" :confirm? true
         :method :post :url ep/cn-appraisal-transition-month
         :body {:month month :year year :to "LIDER_REVIEW"}
         :success-msg "CNs avançados para revisão do líder."}
        "LIDER_REVIEW"
        {:kind :request :label "Avançar para revisão RevOps"
         :method :post :url ep/cn-appraisal-transition-month
         :body {:month month :year year :to "REVOPS_REVIEW"}
         :success-msg "CNs avançados para revisão RevOps."}
        "REVOPS_REVIEW"
        {:kind :request :label "Finalizar todos" :confirm? true
         :method :post :url ep/cn-appraisal-finalize-month
         :body {:month month :year year}
         :success-msg "Apurações CN finalizadas."}
        nil)

      "cn_bonus"
      (case status
        "PENDING"
        {:kind :request :label "Rodar Bônus CN"
         :method :post :url ep/cn-quarterly-bonus
         :body {:quarter quarter :year year}
         :success-msg "Bônus CN calculado."}
        "CALCULATING"
        {:kind :request :label "Finalizar Bônus CN" :confirm? true
         :method :post :url ep/cn-quarterly-bonus-finalize
         :body {:quarter quarter :year year}
         :success-msg "Bônus CN finalizado."}
        nil)

      "ev_bonus"
      (case status
        "PENDING"
        {:kind :request :label "Rodar Bônus EV"
         :method :post :url ep/ev-bonus
         :body {:quarter quarter :year year}
         :success-msg "Bônus EV calculado."}
        "CALCULATING"
        {:kind :request :label "Finalizar Bônus EV" :confirm? true
         :method :post :url ep/ev-bonus-finalize
         :body {:quarter quarter :year year}
         :success-msg "Bônus EV finalizado."}
        nil)

      "leadership_bonus"
      (case status
        "PENDING"
        {:kind :navigate :label "Preparar e rodar →"
         :route :revops/leadership}
        "CALCULATING"
        (when appraisal_id
          {:kind :request :label "Liberar para validação"
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "VALIDATING"}
           :success-msg "Liberado para validação do líder."})
        "VALIDATING" nil
        "LIDER_REVIEW"
        (when appraisal_id
          {:kind :request :label "Avançar para revisão RevOps"
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "REVOPS_REVIEW"}
           :success-msg "Enviado para revisão RevOps."})
        "REVOPS_REVIEW"
        (when appraisal_id
          {:kind :request :label "Travar (LOCKED)" :confirm? true
           :method :post :url (ep/leadership-transition appraisal_id)
           :body {:to "LOCKED"}
           :success-msg "Bônus Liderança travado."})
        nil)

      nil)))
```

Nota: `(ep/appraisals)` é função; os demais são `def`s — conferir em `endpoints.cljs` ao usar.

- [ ] **Step 4: Rodar os testes**

```powershell
cd frontend
npm test
```

Expected: PASS (testes novos + `suggest-cycle-test` + `components-for-test` intactos).

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/app/views/revops/monthly_cycle.cljs frontend/test/app/views/revops/monthly_cycle_test.cljs
git commit -m "feat: pure rail helpers (next-action, progress, month nav)"
```

---

### Task 6: Frontend — reescrever a view como trilho

**Files:**
- Modify: `frontend/src/app/views/revops/monthly_cycle.cljs`

- [ ] **Step 1: Substituir as partes de view do arquivo**

Manter no arquivo: o ns (Task 5), `steps`→renomeado, vocabulários, `base-sequence`/`quarter-end-sequence`/`components-for`, `component-routes`, `month-names`, `cycle-label`, helpers puros do Task 5, `next-month`, `current-cycle-suggestion`, `suggest-cycle`, `pick-cycle`, `status->badge`, `delete-cycle-btn`.

Remover: `header-banner`, `component-card-for-team`, o antigo `stepper` de status global e o antigo `page`.

O arquivo final completo (referência de montagem — vocabulários e helpers já descritos acima ficam como estão):

```clojure
(ns app.views.revops.monthly-cycle
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Unified MonthlyCycle page — a vertical step rail fed from
;; GET /api/v1/monthly-cycles/:id (global component aggregator).
;;
;; Sequence: Apuração EV → Apuração CN → (quarter-end months only)
;; Bônus CN, Bônus EV e Bônus Liderança. The rail guides, never blocks.

(def ^:private full-steps
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])

(def ^:private full-step-labels
  {"DRAFT"         "Draft"
   "CALCULATING"   "Calculating"
   "VALIDATING"    "Validating"
   "LIDER_REVIEW"  "Líder Review"
   "REVOPS_REVIEW" "RevOps Review"
   "LOCKED"        "Locked"})

(def ^:private bonus-steps ["PENDING" "CALCULATING" "LOCKED"])

(def ^:private bonus-step-labels
  {"PENDING" "Pendente" "CALCULATING" "Calculando" "LOCKED" "Final"})

(def ^:private base-sequence
  [["ev_apuracao" "Apuração EV"]
   ["cn_apuracao" "Apuração CN"]])

(def ^:private quarter-end-sequence
  [["cn_bonus" "Bônus CN"]
   ["ev_bonus" "Bônus EV"]
   ["leadership_bonus" "Bônus Liderança"]])

(defn components-for
  "Ordered [key label] sequence for a cycle. The quarterly bonuses only
   appear on the last month of each quarter."
  [cycle]
  (if (:is_quarter_end cycle)
    (into base-sequence quarter-end-sequence)
    base-sequence))

(def ^:private component-routes
  {"ev_apuracao"      :revops/appraisal
   "cn_apuracao"      :revops/cn-appraisal
   "cn_bonus"         :revops/cn-quarterly-bonus
   "ev_bonus"         :revops/ev-bonus
   "leadership_bonus" :revops/leadership})

(def ^:private month-names
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn cycle-label [{:keys [month year]}]
  (str (nth month-names (dec month) month) "/" year))

;; ── Pure rail helpers ───────────────────────────────────────────────
;; AQUI entra, byte a byte, o bloco inserido no Task 5 Step 3b:
;; component-of, current-step-key, progress, prev-month,
;; cycle-for-month e next-action. Não reescrever — copiar do Task 5.

(defn- next-month [{:keys [month year]}]
  (if (< month 12)
    {:month (inc month) :year year}
    {:month 1 :year (inc year)}))

(defn current-cycle-suggestion
  ([] (current-cycle-suggestion (js/Date.)))
  ([date]
   {:month (inc (.getMonth date))
    :year (.getFullYear date)}))

(defn suggest-cycle
  "Suggest the cycle that should be opened next.
   With no existing cycles, default to the current month. If the most recent
   cycle is LOCKED and there's no cycle yet for the following month, suggest
   that following month."
  ([cycles last-cycle]
   (suggest-cycle cycles last-cycle (js/Date.)))
  ([cycles last-cycle today]
   (cond
     (empty? (or cycles []))
     (current-cycle-suggestion today)

     (and last-cycle (= "LOCKED" (:status last-cycle)))
     (let [{:keys [month year] :as nm} (next-month last-cycle)
           already? (some #(and (= (:month %) month)
                                 (= (:year %) year))
                          cycles)]
       (when-not already? nm)))))

(defn- pick-cycle
  "Default to the most-recent OPEN cycle, falling back to the latest row."
  [cycles]
  (let [sorted (->> (or cycles [])
                    (sort-by (juxt :year :month) #(compare %2 %1)))]
    (or (first (filter #(= "OPEN" (:status %)) sorted))
        (first sorted))))

;; ── View pieces ─────────────────────────────────────────────────────

(defn- status->badge [status]
  (case status
    "PENDING"       [:span.badge.badge-locked "Pendente"]
    "DRAFT"         [:span.badge.badge-draft "Draft"]
    "CALCULATING"   [:span.badge.badge-calc "Calculating"]
    "VALIDATING"    [:span.badge.badge-validating "Validating"]
    "LIDER_REVIEW"  [:span.badge.badge-review "Líder Review"]
    "REVOPS_REVIEW" [:span.badge.badge-review "RevOps Review"]
    "LOCKED"        [:span.badge.badge-paid "Locked"]
    [:span.badge.badge-locked (or status "·")]))

(defn- mini-stepper
  "Per-component state mini-stepper. Bonus components use the short
   vocabulary; apurações/liderança use the full state machine."
  [k current-status]
  (let [bonus? (#{"cn_bonus" "ev_bonus"} k)
        sts    (if bonus? bonus-steps full-steps)
        labels (if bonus? bonus-step-labels full-step-labels)
        idx    (max 0 (.indexOf (clj->js sts) (or current-status (first sts))))]
    [:div.stepper
     (for [[i s] (map-indexed vector sts)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot (str (inc i))]]
         [:div.step-label (labels s)]]
        (when (< i (dec (count sts)))
          [:div.step-line])])]))

(defn- step-summary
  "One line with the numbers that matter for a component."
  [k component]
  (let [{:keys [validations_total validations_done rows final expected
                month has_contestation]} component
        text (cond
               (and validations_total (pos? validations_total))
               (str validations_done " / " validations_total
                    " validações concluídas")

               (= k "cn_apuracao")
               (if (and rows (pos? rows))
                 (str rows " de " (or expected rows) " CNs apurados"
                      (when month (str " · mês " month)))
                 "—")

               (and rows (pos? rows))
               (str (or final 0) " / " rows " finais"
                    (when expected (str " · " rows " de " expected)))

               :else "—")]
    [:<>
     [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
      text]
     (when has_contestation
       [:span.badge.badge-review {:style {:margin-top "6px"}}
        "⚠ contestação aberta"])]))

(defn- action-button [cycle {:keys [kind label confirm? route] :as action}]
  (when action
    [:button.btn.btn-primary.btn-sm
     {:on-click
      (fn []
        (cond
          (= kind :navigate)
          (rf/dispatch [:navigate route])

          (and confirm?
               (not (js/confirm (str label "? Esta ação avança o ciclo."))))
          nil

          :else
          (rf/dispatch [:revops/cycle-action
                        (assoc action :cycle-id (:id cycle))])))}
     label]))

(defn- detail-link [k]
  (when-let [route (component-routes k)]
    [:button.btn.btn-secondary.btn-sm
     {:on-click #(rf/dispatch [:navigate route])}
     "Ver detalhes →"]))

(defn- bonus-guidance
  "Soft warning when a bonus step is opened while apurações are open.
   Guides, never blocks."
  [cycle k]
  (when (and (#{"cn_bonus" "ev_bonus" "leadership_bonus"} k)
             (some #(not= "LOCKED" (:status (component-of cycle %)))
                   ["ev_apuracao" "cn_apuracao"]))
    [:div.callout {:style {:margin "8px 0"}}
     [layout/icon "info" {:width 16 :height 16}]
     [:div {:style {:font-size "12px" :color "var(--fg-3)"}}
      "Recomendado concluir as Apurações EV e CN antes dos bônus."]]))

(defn- step-card
  [cycle idx k label {:keys [expanded? current? read-only? on-toggle]}]
  (let [component (component-of cycle k)
        status    (or (:status component) "PENDING")
        done?     (= "LOCKED" status)]
    [:div.card {:style {:margin-top "12px"
                        :border (when current?
                                  "1px solid var(--accent, #4f7cff)")
                        :opacity (if (or done? current? expanded?) 1 0.72)}}
     [:div.card-head {:style {:cursor "pointer"} :on-click on-toggle}
      [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
       [:div.step-dot {:style {:flex-shrink 0}} (if done? "✓" (str idx))]
       [:div
        [:h4 label]
        (when current?
          [:div.card-sub "Você está aqui"])]]
      [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
       (when-not expanded? [step-summary k component])
       [status->badge status]]]
     (when expanded?
       [:div {:style {:padding "4px 0 8px"}}
        (when-not (= "PENDING" status)
          [mini-stepper k status])
        [:div {:style {:padding "10px 0"}}
         [step-summary k component]]
        [bonus-guidance cycle k]
        (when (= "VALIDATING" status)
          [:div.muted {:style {:font-size "12px" :margin-bottom "8px"}}
           (if (= k "ev_apuracao")
             "Aguardando os EVs validarem; avança sozinho ao concluir."
             "Aguardando validações.")])
        [:div {:style {:display "flex" :gap "8px" :margin-top "4px"}}
         (when-not read-only?
           [action-button cycle (next-action k component cycle)])
         [detail-link k]]])]))

(defn- quarter-divider [cycle]
  [:div {:style {:display "flex" :align-items "center" :gap "12px"
                 :margin "20px 0 4px"}}
   [:div {:style {:flex 1 :height "1px" :background "var(--border, #333)"}}]
   [:strong {:style {:font-size "12px" :letter-spacing "0.08em"
                     :color "var(--fg-3)"}}
    (str "FECHAMENTO DO Q" (:quarter cycle))]
   [:div {:style {:flex 1 :height "1px" :background "var(--border, #333)"}}]])

(defn- next-action-band [cycle]
  (when (not= "LOCKED" (:status cycle))
    (let [k         (current-step-key cycle)
          labels    (into {} (components-for cycle))
          component (component-of cycle k)
          action    (when k (next-action k component cycle))]
      (when k
        [:div.callout {:style {:margin-top "16px"}}
         [layout/icon "info" {:width 20 :height 20}]
         [:div {:style {:flex 1}}
          [:strong (str "Próximo passo: " (get labels k))]
          [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
           (if action
             (:label action)
             "Aguardando validações — nada a fazer agora.")]]
         (when action [action-button cycle action])]))))

(defn- progress-bar [cycle]
  (let [{:keys [done total]} (progress cycle)]
    [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
     [:div {:style {:flex 1 :height "6px" :border-radius "3px"
                    :background "var(--bg-3, #222)" :overflow "hidden"}}
      [:div {:style {:width (str (if (pos? total)
                                   (js/Math.round (* 100 (/ done total)))
                                   0) "%")
                     :height "100%"
                     :background "var(--accent, #4f7cff)"}}]]
     [:span.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
      (str done " de " total " passos concluídos")]]))

(defn- cycle-selector [cycles selection]
  (let [cyc    (cycle-for-month cycles selection)
        sorted (->> (or cycles [])
                    (sort-by (juxt :year :month) #(compare %2 %1)))]
    [:div.card {:style {:display "flex" :align-items "center" :gap "12px"
                        :padding "14px 18px"}}
     [:button.btn.btn-secondary.btn-sm
      {:on-click #(rf/dispatch [:revops/select-cycle-month
                                (prev-month selection)])}
      "‹"]
     [:div {:style {:flex 1 :text-align "center"}}
      [:strong {:style {:font-size "16px"}} (cycle-label selection)]
      [:span {:style {:margin-left "10px"}}
       (cond
         (nil? cyc)                    [:span.badge.badge-locked "Sem ciclo"]
         (= "OPEN" (:status cyc))      [:span.badge.badge-calc "Em andamento"]
         (= "LOCKED" (:status cyc))    [:span.badge.badge-paid "Fechado"]
         :else                         [:span.badge.badge-locked (:status cyc)])]]
     [:button.btn.btn-secondary.btn-sm
      {:on-click #(rf/dispatch [:revops/select-cycle-month
                                (next-month selection)])}
      "›"]
     (when (seq sorted)
       [:select {:value     (str (:month selection) "-" (:year selection))
                 :on-change (fn [e]
                              (let [[m y] (.split (.. e -target -value) "-")]
                                (rf/dispatch [:revops/select-cycle-month
                                              {:month (js/parseInt m)
                                               :year  (js/parseInt y)}])))
                 :style {:margin-left "8px"}}
        (when (nil? (cycle-for-month sorted selection))
          [:option {:value (str (:month selection) "-" (:year selection))}
           (cycle-label selection)])
        (for [c sorted]
          ^{:key (:id c)}
          [:option {:value (str (:month c) "-" (:year c))}
           (str (cycle-label c)
                (if (= "LOCKED" (:status c)) " · fechado" " · aberto"))])])]))

(defn- delete-cycle-btn [cycle]
  (let [{:keys [id status]} cycle
        locked? (= "LOCKED" status)]
    [:button.btn.btn-danger.btn-sm
     {:disabled locked?
      :title    (if locked?
                  "Ciclos LOCKED não podem ser excluídos."
                  "Excluir este ciclo mensal.")
      :on-click #(when (js/confirm
                        (str "Tem certeza que deseja excluir o ciclo "
                             (cycle-label cycle) "? "
                             "Esta ação não pode ser desfeita."))
                   (rf/dispatch [:revops/delete-monthly-cycle id]))}
     "Excluir ciclo"]))

(defn- open-cycle-cta [selection]
  [:div.card
   [:div.empty
    [:h4 (str "Nenhum ciclo para " (cycle-label selection))]
    [:p "Abra o ciclo para começar a apuração deste mês."]
    [:button.btn.btn-primary
     {:on-click #(rf/dispatch [:revops/open-monthly-cycle selection])}
     (str "Abrir " (cycle-label selection))]]])

(defn- rail [cycle read-only? expanded toggle!]
  (let [comps (components-for cycle)
        cur   (when-not read-only? (current-step-key cycle))]
    [:<>
     (for [[i [k label]] (map-indexed vector comps)]
       ^{:key k}
       [:<>
        (when (= k "cn_bonus") [quarter-divider cycle])
        [step-card cycle (inc i) k label
         {:expanded?  (or (contains? @expanded k)
                          (and (not read-only?) (= k cur)))
          :current?   (= k cur)
          :read-only? read-only?
          :on-toggle  #(toggle! k)}]])]))

(defn page []
  (rf/dispatch [:revops/fetch-monthly-cycles])
  (let [expanded (r/atom #{})
        toggle!  (fn [k] (swap! expanded
                                #(if (contains? % k) (disj % k) (conj % k))))]
    (fn []
      (let [cycles    @(rf/subscribe [:revops/monthly-cycles])
            loading?  @(rf/subscribe [:revops/monthly-cycle-loading?])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            selection (or @(rf/subscribe [:revops/monthly-cycle-selection])
                          (when-let [t (pick-cycle cycles)]
                            {:month (:month t) :year (:year t)})
                          (current-cycle-suggestion))
            target    (cycle-for-month cycles selection)
            detail    @(rf/subscribe [:revops/monthly-cycle])
            cycle     (when (and detail target (= (:id detail) (:id target)))
                        detail)
            read-only? (= "LOCKED" (:status cycle))]
        (when (and target (or (not detail) (not= (:id detail) (:id target))))
          (rf/dispatch [:revops/fetch-monthly-cycle-detail (:id target)]))
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "ciclo mensal"]
          :title "Ciclo Mensal"
          :subtitle "Sequência da apuração: EVs, CNs e — no fechamento do trimestre — os bônus"
          :header-actions (when cycle (delete-cycle-btn cycle))}

         [cycle-selector cycles selection]

         (cond
           (not target)
           [open-cycle-cta selection]

           (or loading? (not cycle))
           [:div.card [:div {:style {:padding "32px" :text-align "center"
                                      :color "var(--fg-3)"}} "Carregando…"]]

           :else
           [:<>
            [:div.card {:style {:padding "16px 20px" :margin-top "16px"}}
             [progress-bar cycle]]
            (if read-only?
              (let [nm (next-month {:month (:month cycle)
                                    :year  (:year cycle)})]
                [:div.callout {:style {:margin-top "16px"}}
                 [layout/icon "info" {:width 20 :height 20}]
                 [:div {:style {:flex 1}}
                  [:strong "Ciclo fechado"]
                  [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
                   (str "Travado em "
                        (some-> (:locked_at cycle) (subs 0 10))
                        ". Histórico em modo leitura.")]]
                 (when-not (cycle-for-month cycles nm)
                   [:button.btn.btn-primary.btn-sm
                    {:on-click #(do (rf/dispatch [:revops/select-cycle-month nm])
                                    (rf/dispatch [:revops/open-monthly-cycle nm]))}
                    (str "Abrir " (cycle-label nm))])])
              [next-action-band cycle])
            [rail cycle read-only? expanded toggle!]])]))))
```

- [ ] **Step 2: Rodar testes e lint**

```powershell
cd frontend
npm test
npm run lint
```

Expected: testes PASS; lint sem erros novos (warnings pré-existentes ok).

- [ ] **Step 3: Verificação visual (se o dev server estiver disponível)**

Subir o preview e verificar: seletor navega entre meses; mês sem ciclo mostra CTA; ciclo aberto mostra trilho com passo atual expandido; mês 6 mostra divisor "FECHAMENTO DO Q2" + 5 passos; ciclo LOCKED renderiza read-only sem botões de ação.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/app/views/revops/monthly_cycle.cljs
git commit -m "feat: monthly cycle page as a guided step rail"
```

---

### Task 7: Deep links com filtro de período

**Files:**
- Create: `frontend/src/app/util/url.cljs`
- Modify: `frontend/src/app/routes.cljs` (efeito `:navigate!`, linhas ~126-134)
- Modify: `frontend/src/app/views/revops/monthly_cycle.cljs` (`detail-link`)
- Modify: `frontend/src/app/views/revops/cn_appraisal.cljs` (linha ~248)
- Modify: `frontend/src/app/views/revops/ev_bonus.cljs` (linha ~43)
- Modify: `frontend/src/app/views/revops/cn_quarterly_bonus.cljs` (linha ~67)
- Modify: `frontend/src/app/views/revops/leadership_appraisal.cljs` (linha ~100)

- [ ] **Step 1: Criar o util de query param**

Criar `frontend/src/app/util/url.cljs`:

```clojure
(ns app.util.url)

(defn query-param
  "Read a query-string parameter from the current URL, or nil."
  [k]
  (let [params (js/URLSearchParams. (.. js/window -location -search))]
    (.get params k)))
```

- [ ] **Step 2: Estender o efeito `:navigate!` para query params**

Em `frontend/src/app/routes.cljs`, substituir o `reg-fx :navigate!` por:

```clojure
;; Navigate effect — pushes state into browser history via reitit
;; Accepts a route-name keyword, [route-name params] or
;; [route-name params query-params]
(rf/reg-fx
 :navigate!
 (fn [route-or-vec]
   (if (vector? route-or-vec)
     (let [[route-name params query] route-or-vec]
       (rfe/push-state route-name (or params {}) (or query {})))
     (rfe/push-state route-or-vec))))
```

- [ ] **Step 3: `detail-link` passa o período do ciclo**

Em `frontend/src/app/views/revops/monthly_cycle.cljs`, substituir `detail-link` por:

```clojure
(defn- detail-link [cycle k]
  (when-let [route (component-routes k)]
    (let [{:keys [month year quarter]} cycle
          query (if (#{"cn_bonus" "ev_bonus" "leadership_bonus"} k)
                  {:quarter quarter :year year}
                  {:month month :year year})]
      [:button.btn.btn-secondary.btn-sm
       {:on-click #(rf/dispatch [:navigate [route nil query]])}
       "Ver detalhes →"])))
```

E atualizar o ponto de chamada em `step-card`: `[detail-link k]` → `[detail-link cycle k]`.

- [ ] **Step 4: Seed dos filtros nas páginas dedicadas**

4a. `frontend/src/app/views/revops/cn_appraisal.cljs` — adicionar `[app.util.url :as url]` ao `:require` do ns e trocar a linha ~248:

```clojure
  (let [filter-s    (r/atom {:month "4" :year "2026"})
```
por:
```clojure
  (let [filter-s    (r/atom {:month (or (url/query-param "month") "4")
                             :year  (or (url/query-param "year") "2026")})
```

4b. `frontend/src/app/views/revops/ev_bonus.cljs` — mesmo `:require`; trocar a linha ~43:

```clojure
  (let [filter-s (r/atom {:quarter "2" :year "2026"})]
```
por:
```clojure
  (let [filter-s (r/atom {:quarter (or (url/query-param "quarter") "2")
                          :year    (or (url/query-param "year") "2026")})]
```

4c. `frontend/src/app/views/revops/cn_quarterly_bonus.cljs` — mesma troca na linha ~67 (código idêntico ao 4b).

4d. `frontend/src/app/views/revops/leadership_appraisal.cljs` — mesma troca na linha ~100 (mantendo o `form-inputs (r/atom {})` da linha seguinte intacto).

- [ ] **Step 5: Rodar testes e commitar**

```powershell
cd frontend
npm test
npm run lint
```

Expected: PASS.

```powershell
git add frontend/src/app/util/url.cljs frontend/src/app/routes.cljs frontend/src/app/views/revops/monthly_cycle.cljs frontend/src/app/views/revops/cn_appraisal.cljs frontend/src/app/views/revops/ev_bonus.cljs frontend/src/app/views/revops/cn_quarterly_bonus.cljs frontend/src/app/views/revops/leadership_appraisal.cljs
git commit -m "feat: cycle deep links carry the period into detail pages"
```

---

### Task 8: Verificação final

- [ ] **Step 1: Suíte backend completa**

```powershell
cd backend
python -m pytest tests/ -q
```

Expected: PASS, zero failures.

- [ ] **Step 2: Suíte frontend completa + lint**

```powershell
cd frontend
npm test
npm run lint
```

Expected: PASS.

- [ ] **Step 3: Atualizar CONTEXT.md**

Em `CONTEXT.md`, atualizar a entrada **Ciclo Mensal** (linha ~99) para refletir a página única:

```markdown
**Ciclo Mensal**:
The monthly orchestration cycle that runs the apuracao sequence — Apuracao EV, Apuracao CN, and, only on quarter-end months (March, June, September, December), Bonus CN, Bonus EV and Bonus Lideranca. Operated from a single step-rail page with global (team-less) component aggregation.
_Avoid_: ciclo trimestral, quarterly cycle, per-team cycle progress
```

- [ ] **Step 4: Commit final**

```powershell
git add CONTEXT.md
git commit -m "docs: Ciclo Mensal reflects the single-page step rail"
```
