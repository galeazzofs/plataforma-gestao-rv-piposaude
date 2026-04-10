# Design: CN Apuração, CN Simulator, EV Quarterly Bonus, Leadership Commission

**Date:** 2026-04-10  
**Status:** Approved  
**Reference:** Legacy repo `galeazzofs/pipo-gestao-rv` (React + Supabase)  
**App stack:** Python/Flask backend + ClojureScript/re-frame frontend

---

## Context

The current app has a complete EV commission engine (safra via NF matching, `EvQuarterAchievement` for commission % lookup). The `UserRole.CN` and `UserRole.GERENTE` roles exist but have zero commission logic. This design migrates four features from the legacy app:

1. **CN Monthly Apuração** — "Regra de Ouro" formula, runs monthly per CN
2. **CN Commission Simulator** — stateless preview of the same formula, accessible to CN and RevOps
3. **EV Quarterly MRR Bonus** — salary × multiplier based on MRR achievement, runs quarterly
4. **Leadership (GERENTE) Commission** — 2D matrix (MRR faixa × SQL faixa) × salary, runs quarterly

---

## Architecture Decision

**Approach: Independent modules per role** (`modules/commissions/cn_calculator.py`, `ev_bonus.py`, `leadership_calculator.py`, `simulator.py`). Each module has one responsibility, its own endpoints, and is independently testable. The quarterly full closing calls them in sequence: CN (month 3) → EV safra (existing) → EV bonus → Leadership.

---

## 1. Data Model

### 1.1 `User` — new nullable columns (migration required)

| Column | Type | Used by |
|---|---|---|
| `nivel` | `Enum('CN1','CN2','CN3')` | CN |
| `porte` | `Enum('M','G+')` | CN (informational profile field only; calculation targets come from `CnMonthlyGoal`) |
| `salario_base` | `Numeric(12,2)` | EV, GERENTE |

### 1.2 New model: `CnMonthlyGoal`

Monthly SAO and vidas targets per CN, set by RevOps before running apuração.

```python
cn_id      FK users.id   NOT NULL
month      Integer        NOT NULL   # 1–12
year       Integer        NOT NULL
sao_target Numeric(12,2) NOT NULL
vidas_target Numeric(12,2) NOT NULL
UNIQUE (cn_id, month, year)
```

### 1.3 New model: `CnMonthlyAppraisal`

Stores the result of each monthly CN apuração run. `is_final=True` locks the record.

```python
cn_id              FK users.id    NOT NULL
month              Integer         NOT NULL
year               Integer         NOT NULL
sao_realizado      Numeric(12,2)  NOT NULL
vidas_realizado    Numeric(12,2)  NOT NULL
pct_sao            Numeric(8,4)   NOT NULL   # sao_realizado / sao_target
pct_vidas          Numeric(8,4)   NOT NULL   # min(vidas_realizado / vidas_target, 1.5)
score_final        Numeric(8,4)   NOT NULL   # pct_sao×0.70 + pct_vidas×0.30
multiplicador      Numeric(8,4)   NOT NULL   # from régua de pagamento
commission_amount  Numeric(12,2)  NOT NULL   # CN_BASE[nivel] × multiplicador
is_final           Boolean         NOT NULL  DEFAULT false
UNIQUE (cn_id, month, year)
```

### 1.4 `EvQuarterAchievement` — 2 new nullable columns

The existing model already has `mrr_target`, `achievement_pct`, and `is_final`. Adding bonus fields avoids a new table.

```python
bonus_amount          Numeric(12,2)  nullable   # salario_base × multiplicador
salario_base_snapshot Numeric(12,2)  nullable   # snapshot at time of calculation
```

### 1.5 New model: `GerenteQuarterAppraisal`

Quarterly leadership bonus. `meta_mrr` is auto-calculated by the backend; all other `realizado_*` and `meta_sql` fields are entered by RevOps.

```python
gerente_id      FK users.id    NOT NULL
quarter         Integer         NOT NULL
year            Integer         NOT NULL
meta_mrr        Numeric(12,2)  NOT NULL   # 90% × SUM(Goal.mrr_target of team EVs)
meta_sql        Integer         NOT NULL   # entered by RevOps; whole number (SQL = Sales Qualified Leads count)
realizado_mrr   Numeric(12,2)  NOT NULL
realizado_sql   Integer         NOT NULL
pct_mrr         Numeric(8,4)   NOT NULL
pct_sql         Numeric(8,4)   NOT NULL
multiplicador   Numeric(8,4)   NOT NULL
bonus_amount    Numeric(12,2)  NOT NULL
is_final        Boolean         NOT NULL  DEFAULT false
UNIQUE (gerente_id, quarter, year)
```

---

## 2. Business Rules

### 2.1 CN Commission — Regra de Ouro

**Step 1 — KPIs:**
```
pct_sao   = sao_realizado / sao_target
pct_vidas = min(vidas_realizado / vidas_target, 1.5)   # capped at 150%
```

**Step 2 — Weighted score:**
```
score_final = (pct_sao × 0.70) + (pct_vidas × 0.30)
```

**Step 3 — Régua de pagamento (multiplier):**

| Score | Multiplier |
|---|---|
| < 20% | 0x |
| 20% – 39.9% | 0.20x |
| 40% – 99.9% | = score_final (linear) |
| 100% – 109.9% | 1.20x |
| 110% – 139.9% | 1.80x |
| ≥ 140% | 2.10x |

**Step 4 — Commission:**
```
CN_BASE = { CN1: R$2,000 | CN2: R$2,500 | CN3: R$3,000 }
commission_amount = CN_BASE[nivel] × multiplicador
```

### 2.2 EV MRR Quarterly Bonus

Uses `EvQuarterAchievement.achievement_pct` (already calculated by the existing engine).

**Multiplier table:**

| MRR Achievement | Multiplier |
|---|---|
| < 80% | 0x |
| 80% – 94.9% | 0.5x |
| 95% – 124.9% | 1.0x |
| ≥ 125% | 1.5x |

```
bonus_amount = user.salario_base × multiplicador
```

### 2.3 Leadership Commission — GERENTE

**Meta MRR (auto-calculated):**
```
meta_mrr_gerente = 90% × SUM(Goal.mrr_target for all EVs in gerente's team, quarter, year)
```

**Achievement:**
```
pct_mrr = realizado_mrr / meta_mrr_gerente
pct_sql = realizado_sql / meta_sql
```

**Multiplier matrix (MRR faixa × SQL faixa):**

| MRR \ SQL | < 80% | 80–94.9% | 95–109.9% | ≥ 110% |
|---|---|---|---|---|
| < 60% | 0x | 0x | 0x | 0x |
| 60–79.9% | 0.5x | 0.75x | 1.0x | 1.25x |
| 80–94.9% | 1.0x | 1.5x | 2.0x | 2.25x |
| 95–109.9% | 1.5x | 2.0x | 3.0x | 3.25x |
| ≥ 110% | 2.0x | 2.75x | 3.5x | 4.0x |

```
bonus_amount = gerente.salario_base × multiplicador   # max: salario_base × 4.0
```

---

## 3. Backend Modules

All new files under `backend/app/modules/commissions/`:

### `cn_calculator.py`
- `run_cn_monthly_appraisal(month, year)` — main entry point
  1. Validate: all active CNs have a `CnMonthlyGoal` for (month, year)
  2. Delete non-final `CnMonthlyAppraisal` for (month, year)
  3. For each active CN: compute KPIs, score, multiplier, commission
  4. Upsert `CnMonthlyAppraisal` (is_final=False)
  5. Return summary dict
- `validate_cn_goals(month, year)` → list of missing CNs

### `ev_bonus.py`
- `run_ev_quarterly_bonus(quarter, year)` — main entry point
  1. Query all `EvQuarterAchievement` for (quarter, year) where not is_final
  2. For each: fetch `user.salario_base`, compute multiplier, compute bonus
  3. Update `EvQuarterAchievement.bonus_amount` and `salario_base_snapshot`
  4. Return summary dict

### `leadership_calculator.py`
- `run_leadership_appraisal(quarter, year, inputs: list[dict])` — main entry point
  - `inputs`: `[{ gerente_id, meta_sql, realizado_mrr, realizado_sql }, ...]`
  1. For each GERENTE input:
     - Auto-compute `meta_mrr` = 90% × SUM team EV Goals for (quarter, year)
     - Compute pct_mrr, pct_sql, multiplier, bonus
     - Upsert `GerenteQuarterAppraisal` (is_final=False)
  2. Return summary dict
- `get_leadership_preview(quarter, year)` → list of GERENTEs with auto-computed `meta_mrr`

### `simulator.py`
- `simulate_cn(nivel, sao_meta, sao_realizado, vidas_meta, vidas_realizado)` → dict
  - Pure function, no DB reads, returns full breakdown (pct_sao, pct_vidas, score, multiplier, commission)

---

## 4. API Endpoints

All under `/api/v1/`:

| Method | Route | Roles | Description |
|---|---|---|---|
| GET | `/commissions/cn/goals` | ADMIN | List CnMonthlyGoals (query: month, year) |
| PUT | `/commissions/cn/goals` | ADMIN | Upsert goals for month/year |
| POST | `/commissions/cn/appraisal` | ADMIN | Run monthly apuração (body: month, year) |
| GET | `/commissions/cn/appraisal` | ADMIN, CN | List results (query: month, year, cn_id); CN role always filtered to own user_id by backend |
| POST | `/commissions/cn/appraisal/<id>/finalize` | ADMIN | Lock a CN apuração |
| POST | `/commissions/ev/bonus` | ADMIN | Run EV quarterly bonus (body: quarter, year) |
| GET | `/commissions/ev/bonus` | ADMIN, EV | List EV bonus results (query: quarter, year) |
| GET | `/commissions/leadership/preview` | ADMIN | Preview meta_mrr per GERENTE |
| POST | `/commissions/leadership/appraisal` | ADMIN | Run leadership apuração |
| GET | `/commissions/leadership/appraisal` | ADMIN, GERENTE | List results |
| POST | `/commissions/leadership/appraisal/<id>/finalize` | ADMIN | Lock a GERENTE apuração |
| POST | `/commissions/simulate/cn` | ADMIN, CN | Stateless CN simulator; CN can only simulate with own `nivel` (backend enforces) |

---

## 5. Frontend

### New: `frontend/src/app/views/cn/`

| File | Route | Role | Description |
|---|---|---|---|
| `simulator.cljs` | `/cn/simulator` | CN | Self-service simulator: inputs SAO/vidas, displays full breakdown |
| `dashboard.cljs` | `/cn/dashboard` | CN | Monthly apuração history for the logged-in CN |

### New views in `frontend/src/app/views/revops/`

| File | Route | Description |
|---|---|---|
| `cn_goals.cljs` | `/revops/cn-goals` | CRUD for CnMonthlyGoal (SAO + vidas targets by CN/month) |
| `cn_appraisal.cljs` | `/revops/cn-appraisal` | Run monthly CN apuração; table with sao/vidas realizado inputs per CN; inline simulator panel for any CN |
| `ev_bonus.cljs` | `/revops/ev-bonus` | Trigger EV quarterly bonus; view results table |
| `leadership_appraisal.cljs` | `/revops/leadership` | Input meta_sql + realizados per GERENTE; meta_mrr shown readonly; run + finalize |

### re-frame pattern
Each new view follows the existing `events.cljs` + `subs.cljs` per-namespace pattern. No shared state between the new views.

---

## 6. Migration Summary

1. Alembic migration: add `nivel`, `porte`, `salario_base` to `users`
2. Alembic migration: create `cn_monthly_goals` table
3. Alembic migration: create `cn_monthly_appraisals` table
4. Alembic migration: add `bonus_amount`, `salario_base_snapshot` to `ev_quarter_achievements`
5. Alembic migration: create `gerente_quarter_appraisals` table

---

## 7. Out of Scope

- EV safra commission (already implemented in `calculator.py`)
- Quarterly full-closing orchestration UI (can be a follow-up)
- Email/Slack notifications for CN apuração results
- Historical data backfill from legacy Supabase
