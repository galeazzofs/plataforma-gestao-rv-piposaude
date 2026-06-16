# CN Rampagem Commission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "rampagem" commission mode for CNs: when a CN is flagged `em_rampagem`, the monthly appraisal is computed from a cadence-attainment régua (two variants — with or without a SAO target) instead of the normal SAO/vidas score.

**Architecture:** Pure calc functions in `simulator.py` (mirrored in `calc.cljs`) gain two rampagem variants plus an inclusive-bounds régua `_regua_rampagem`. A dispatcher picks NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO from `cn.em_rampagem` + the month's `sao_target`. New columns carry cadence metas (on `CnMonthlyGoal`), cadence realizados + `sao_fora_da_meta` (on `CnMonthlyAppraisal`), and `calc_mode`. The appraisal reuses `score_final` (=atingimento) and `multiplicador` (=gatilho). The SAO bonus value lives in `PlatformSetting`.

**Tech Stack:** Python/Flask + SQLAlchemy + Alembic (backend), ClojureScript/reagent/re-frame (frontend), pytest (Postgres `comissoes_test`).

**Spec:** `docs/superpowers/specs/2026-06-16-cn-rampagem-design.md`

**Conventions verified:**
- Alembic single head = `c0d1e2f3a4b5` (use as `down_revision`).
- Tests run on Postgres `comissoes_test`; use the `db_session` fixture (see `tests/test_modules/test_cn_calculator.py`). Run from the `backend/` dir.
- `simulate_cn` returns a dict of **strings**; tests assert exact strings like `"2400.00"`.
- `_regua` and `calc/regua` are the NORMAL régua and must NOT change in this plan.

---

## Task 1: `_regua_rampagem` (inclusive-bounds régua)

**Files:**
- Modify: `backend/app/modules/commissions/simulator.py`
- Test: `backend/tests/test_modules/test_simulator.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_modules/test_simulator.py`:

```python
from app.modules.commissions.simulator import _regua_rampagem


class TestReguaRampagem:
    """Régua de rampagem — limites SUPERIORES inclusivos (diverge de _regua)."""

    def test_at_or_below_20pct_returns_zero(self):
        assert _regua_rampagem(Decimal("0.20")) == Decimal("0")
        assert _regua_rampagem(Decimal("0.10")) == Decimal("0")

    def test_21_to_40_returns_0_20(self):
        assert _regua_rampagem(Decimal("0.21")) == Decimal("0.20")
        assert _regua_rampagem(Decimal("0.40")) == Decimal("0.20")

    def test_em_linha_zone_returns_score_inclusive_of_100(self):
        assert _regua_rampagem(Decimal("0.65")) == Decimal("0.65")
        assert _regua_rampagem(Decimal("1.00")) == Decimal("1.00")  # 100% → em linha

    def test_101_to_110_returns_1_20(self):
        assert _regua_rampagem(Decimal("1.01")) == Decimal("1.20")
        assert _regua_rampagem(Decimal("1.10")) == Decimal("1.20")  # 110% → 120%

    def test_111_to_139_returns_1_80(self):
        assert _regua_rampagem(Decimal("1.11")) == Decimal("1.80")
        assert _regua_rampagem(Decimal("1.39")) == Decimal("1.80")

    def test_140_and_above_returns_2_10(self):
        assert _regua_rampagem(Decimal("1.40")) == Decimal("2.10")
        assert _regua_rampagem(Decimal("2.00")) == Decimal("2.10")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_modules/test_simulator.py::TestReguaRampagem -v`
Expected: FAIL — `ImportError: cannot import name '_regua_rampagem'`.

- [ ] **Step 3: Implement `_regua_rampagem`**

In `backend/app/modules/commissions/simulator.py`, add right after the existing `_regua`:

```python
def _regua_rampagem(score: Decimal) -> Decimal:
    """Régua da rampagem — limites superiores INCLUSIVOS (tabela do print).

    Diverge de _regua (cálculo normal): aqui 100% → em linha (o próprio
    score) e 110% → 120%. Ver docs/.../2026-06-16-cn-rampagem-design.md.
    """
    if score <= Decimal("0.20"):
        return _ZERO
    if score <= Decimal("0.40"):
        return Decimal("0.20")
    if score <= Decimal("1.00"):
        return score
    if score <= Decimal("1.10"):
        return Decimal("1.20")
    if score < Decimal("1.40"):
        return Decimal("1.80")
    return Decimal("2.10")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_modules/test_simulator.py::TestReguaRampagem -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/simulator.py backend/tests/test_modules/test_simulator.py
git commit -m "feat(cn): add inclusive-bounds régua for rampagem"
```

---

## Task 2: Rampagem calc functions + auto dispatcher (pure)

**Files:**
- Modify: `backend/app/modules/commissions/simulator.py`
- Test: `backend/tests/test_modules/test_simulator.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_modules/test_simulator.py`:

```python
from app.modules.commissions.simulator import (
    simulate_cn_rampagem_sem_sao,
    simulate_cn_rampagem_com_sao,
    simulate_cn_auto,
)


class TestRampagemSemSao:
    def test_print_example_gives_3300(self):
        # neg 103/60 → min(1.7167,1)=1 ; emails 1133/400 → min(2.83,1)=1
        # atingimento = 0.5*1 + 0.5*1 = 1.00 → gatilho 1.00 (em linha)
        # comissão = 3000*1.00 + 300*1 = 3300
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN3",
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=1, bonus_sao=Decimal("300"),
        )
        assert r["calc_mode"] == "RAMPAGEM_SEM_SAO"
        assert r["atingimento"] == "1.0000"
        assert r["gatilho"] == "1.00"
        assert r["bonus_sao_amount"] == "300.00"
        assert r["commission_amount"] == "3300.00"
        # compat aliases
        assert r["score_final"] == "1.0000"
        assert r["multiplicador"] == "1.00"

    def test_no_bonus_when_zero_sao_fora(self):
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN3",
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=0, bonus_sao=Decimal("300"),
        )
        assert r["commission_amount"] == "3000.00"

    def test_zero_meta_is_safe(self):
        r = simulate_cn_rampagem_sem_sao(
            nivel="CN1",
            neg_meta=Decimal("0"), neg_real=Decimal("0"),
            emails_meta=Decimal("0"), emails_real=Decimal("0"),
            sao_fora_da_meta=0, bonus_sao=Decimal("300"),
        )
        assert r["atingimento"] == "0.0000"
        assert r["commission_amount"] == "0.00"


class TestRampagemComSao:
    def test_sao_uncapped_pushes_above_100(self):
        # SAO 5/3 = 1.6667 (sem teto); Qualis 10/10 = min(1,1)=1
        # atingimento = 0.5*1.6667 + 0.5*1 = 1.3333 → faixa 111-139 → 1.80
        # comissão = 3000 * 1.80 = 5400 ; sem bônus de SAO
        r = simulate_cn_rampagem_com_sao(
            nivel="CN3",
            sao_meta=Decimal("3"), sao_real=Decimal("5"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("10"),
        )
        assert r["calc_mode"] == "RAMPAGEM_COM_SAO"
        assert r["atingimento"] == "1.3333"
        assert r["gatilho"] == "1.80"
        assert r["commission_amount"] == "5400.00"
        assert r["bonus_sao_amount"] == "0.00"

    def test_qualis_is_capped_at_100(self):
        # SAO 3/3 = 1.0 ; Qualis 50/10 = min(5,1)=1 → atingimento 1.00 → 1.00
        r = simulate_cn_rampagem_com_sao(
            nivel="CN3",
            sao_meta=Decimal("3"), sao_real=Decimal("3"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("50"),
        )
        assert r["atingimento"] == "1.0000"
        assert r["commission_amount"] == "3000.00"


class TestSimulateCnAuto:
    def test_normal_when_not_rampagem(self):
        r = simulate_cn_auto(
            em_rampagem=False, nivel="CN1",
            sao_meta=Decimal("100"), sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"), vidas_realizado=Decimal("50"),
        )
        assert r["calc_mode"] == "NORMAL"
        assert r["commission_amount"] == "2400.00"  # unchanged normal path

    def test_dispatches_sem_sao_when_sao_meta_zero(self):
        r = simulate_cn_auto(
            em_rampagem=True, nivel="CN3", sao_meta=Decimal("0"),
            neg_meta=Decimal("60"), neg_real=Decimal("103"),
            emails_meta=Decimal("400"), emails_real=Decimal("1133"),
            sao_fora_da_meta=1, bonus_sao=Decimal("300"),
        )
        assert r["calc_mode"] == "RAMPAGEM_SEM_SAO"
        assert r["commission_amount"] == "3300.00"

    def test_dispatches_com_sao_when_sao_meta_positive(self):
        r = simulate_cn_auto(
            em_rampagem=True, nivel="CN3",
            sao_meta=Decimal("3"), sao_realizado=Decimal("5"),
            qualis_meta=Decimal("10"), qualis_real=Decimal("10"),
        )
        assert r["calc_mode"] == "RAMPAGEM_COM_SAO"
        assert r["commission_amount"] == "5400.00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_modules/test_simulator.py::TestRampagemSemSao tests/test_modules/test_simulator.py::TestRampagemComSao tests/test_modules/test_simulator.py::TestSimulateCnAuto -v`
Expected: FAIL — `ImportError` for the new names.

- [ ] **Step 3: Implement the calc functions**

In `backend/app/modules/commissions/simulator.py`, add after `simulate_cn`:

```python
def _capped(num: Decimal, den: Decimal) -> Decimal:
    """ratio capped at 1.0 (KPI de atividade)."""
    if den <= _ZERO:
        return _ZERO
    return min(num / den, Decimal("1"))


def _uncapped(num: Decimal, den: Decimal) -> Decimal:
    """ratio without cap (KPI de resultado / SAO)."""
    if den <= _ZERO:
        return _ZERO
    return num / den


def _rampagem_result(calc_mode, atingimento, base, bonus_total):
    gatilho = _regua_rampagem(atingimento)
    comissao = (base * gatilho + bonus_total).quantize(_SCALE2)
    at4 = atingimento.quantize(_SCALE4)
    g2 = gatilho.quantize(_SCALE2)
    return {
        "calc_mode": calc_mode,
        "atingimento": str(at4),
        "gatilho": str(g2),
        "bonus_sao_amount": str(bonus_total.quantize(_SCALE2)),
        "commission_amount": str(comissao),
        # compat aliases so existing serializer / régua-pipeline keep working
        "pct_sao": "0.0000",
        "pct_vidas": "0.0000",
        "score_final": str(at4),
        "multiplicador": str(g2),
    }


def simulate_cn_rampagem_sem_sao(
    nivel: str,
    neg_meta: Decimal, neg_real: Decimal,
    emails_meta: Decimal, emails_real: Decimal,
    sao_fora_da_meta: int,
    bonus_sao: Decimal,
) -> dict:
    """Rampagem sem meta de SAO: dois KPIs de atividade (ambos com teto)."""
    atingimento = (
        Decimal("0.5") * _capped(neg_real, neg_meta)
        + Decimal("0.5") * _capped(emails_real, emails_meta)
    )
    base = CN_BASES.get(nivel, _ZERO)
    bonus_total = (bonus_sao * Decimal(str(sao_fora_da_meta)))
    return _rampagem_result("RAMPAGEM_SEM_SAO", atingimento, base, bonus_total)


def simulate_cn_rampagem_com_sao(
    nivel: str,
    sao_meta: Decimal, sao_real: Decimal,
    qualis_meta: Decimal, qualis_real: Decimal,
) -> dict:
    """Rampagem com meta de SAO: SAO sem teto + Qualis com teto. Sem bônus."""
    atingimento = (
        Decimal("0.5") * _uncapped(sao_real, sao_meta)
        + Decimal("0.5") * _capped(qualis_real, qualis_meta)
    )
    base = CN_BASES.get(nivel, _ZERO)
    return _rampagem_result("RAMPAGEM_COM_SAO", atingimento, base, _ZERO)


def simulate_cn_auto(
    em_rampagem: bool,
    nivel: str,
    sao_meta: Decimal,
    *,
    sao_realizado: Decimal = _ZERO,
    vidas_meta: Decimal = _ZERO,
    vidas_realizado: Decimal = _ZERO,
    neg_meta: Decimal = _ZERO,
    neg_real: Decimal = _ZERO,
    emails_meta: Decimal = _ZERO,
    emails_real: Decimal = _ZERO,
    qualis_meta: Decimal = _ZERO,
    qualis_real: Decimal = _ZERO,
    sao_fora_da_meta: int = 0,
    bonus_sao: Decimal = Decimal("300"),
) -> dict:
    """Pick the calc mode: NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO."""
    if not em_rampagem:
        result = simulate_cn(
            nivel=nivel, sao_meta=sao_meta, sao_realizado=sao_realizado,
            vidas_meta=vidas_meta, vidas_realizado=vidas_realizado,
        )
        result["calc_mode"] = "NORMAL"
        result["atingimento"] = result["score_final"]
        result["gatilho"] = result["multiplicador"]
        result["bonus_sao_amount"] = "0.00"
        return result
    if sao_meta > _ZERO:
        return simulate_cn_rampagem_com_sao(
            nivel=nivel, sao_meta=sao_meta, sao_real=sao_realizado,
            qualis_meta=qualis_meta, qualis_real=qualis_real,
        )
    return simulate_cn_rampagem_sem_sao(
        nivel=nivel, neg_meta=neg_meta, neg_real=neg_real,
        emails_meta=emails_meta, emails_real=emails_real,
        sao_fora_da_meta=sao_fora_da_meta, bonus_sao=bonus_sao,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_modules/test_simulator.py -v`
Expected: PASS (new classes + existing ones unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/simulator.py backend/tests/test_modules/test_simulator.py
git commit -m "feat(cn): add rampagem calc variants + auto dispatcher"
```

---

## Task 3: DB columns + migration

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/models/cn_monthly_goal.py`, `backend/app/models/cn_monthly_appraisal.py`
- Create: `backend/migrations/versions/e1f2a3b4c5d6_cn_rampagem_columns.py`
- Test: `backend/tests/test_modules/test_cn_rampagem_models.py`

- [ ] **Step 1: Add the model columns**

In `backend/app/models/user.py`, after the `porte` column (line ~42):

```python
    em_rampagem = db.Column(db.Boolean, default=False, nullable=False)
```

In `backend/app/models/cn_monthly_goal.py`, after `vidas_target` (line ~18):

```python
    negocios_cadencia_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    emails_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qualis_agendadas_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
```

In `backend/app/models/cn_monthly_appraisal.py`, after `commission_amount` (line ~26):

```python
    calc_mode = db.Column(db.String(32), nullable=False, default="NORMAL")
    negocios_cadencia_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    emails_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qualis_agendadas_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sao_fora_da_meta = db.Column(db.Integer, nullable=False, default=0)
    bonus_sao_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
```

- [ ] **Step 2: Write the migration**

Create `backend/migrations/versions/e1f2a3b4c5d6_cn_rampagem_columns.py`:

```python
"""CN rampagem columns

Adds the em_rampagem flag (users), cadence metas (cn_monthly_goals) and
cadence realizados + calc_mode + sao bonus (cn_monthly_appraisals) needed
for the rampagem commission mode.

Revision ID: e1f2a3b4c5d6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column(
        "em_rampagem", sa.Boolean(), nullable=False, server_default=sa.false()))

    for col in ("negocios_cadencia_meta", "emails_meta", "qualis_agendadas_meta"):
        op.add_column("cn_monthly_goals", sa.Column(
            col, sa.Numeric(12, 2), nullable=False, server_default="0"))

    op.add_column("cn_monthly_appraisals", sa.Column(
        "calc_mode", sa.String(32), nullable=False, server_default="NORMAL"))
    for col in ("negocios_cadencia_realizado", "emails_realizado",
                "qualis_agendadas_realizado", "bonus_sao_amount"):
        op.add_column("cn_monthly_appraisals", sa.Column(
            col, sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cn_monthly_appraisals", sa.Column(
        "sao_fora_da_meta", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for col in ("negocios_cadencia_realizado", "emails_realizado",
                "qualis_agendadas_realizado", "bonus_sao_amount",
                "sao_fora_da_meta", "calc_mode"):
        op.drop_column("cn_monthly_appraisals", col)
    for col in ("negocios_cadencia_meta", "emails_meta", "qualis_agendadas_meta"):
        op.drop_column("cn_monthly_goals", col)
    op.drop_column("users", "em_rampagem")
```

- [ ] **Step 3: Write a model round-trip test**

Create `backend/tests/test_modules/test_cn_rampagem_models.py`:

```python
from decimal import Decimal
from app.models import User, UserRole, CnNivel, CnPorte, CnMonthlyGoal, CnMonthlyAppraisal
from app.models.appraisal import AppraisalStatus


def test_user_em_rampagem_defaults_false_and_persists(db_session):
    u = User(email="ramp@test.com", name="Ramp", role=UserRole.CN,
             nivel=CnNivel("CN1"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    assert u.em_rampagem is False
    u.em_rampagem = True
    db_session.flush()
    assert db_session.get(User, u.id).em_rampagem is True


def test_goal_cadence_metas_persist(db_session):
    u = User(email="g@test.com", name="G", role=UserRole.CN,
             nivel=CnNivel("CN1"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    g = CnMonthlyGoal(cn_id=u.id, month=4, year=2026,
                      sao_target=Decimal("0"), vidas_target=Decimal("0"),
                      negocios_cadencia_meta=Decimal("60"),
                      emails_meta=Decimal("400"),
                      qualis_agendadas_meta=Decimal("10"))
    db_session.add(g); db_session.flush()
    got = db_session.get(CnMonthlyGoal, g.id)
    assert got.negocios_cadencia_meta == Decimal("60.00")
    assert got.emails_meta == Decimal("400.00")
    assert got.qualis_agendadas_meta == Decimal("10.00")


def test_appraisal_rampagem_columns_persist(db_session):
    u = User(email="a@test.com", name="A", role=UserRole.CN,
             nivel=CnNivel("CN3"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    a = CnMonthlyAppraisal(
        cn_id=u.id, month=4, year=2026,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("1"), multiplicador=Decimal("1"),
        commission_amount=Decimal("3300"),
        status=AppraisalStatus.CALCULATING,
        calc_mode="RAMPAGEM_SEM_SAO",
        negocios_cadencia_realizado=Decimal("103"),
        emails_realizado=Decimal("1133"),
        sao_fora_da_meta=1, bonus_sao_amount=Decimal("300"))
    db_session.add(a); db_session.flush()
    got = db_session.get(CnMonthlyAppraisal, a.id)
    assert got.calc_mode == "RAMPAGEM_SEM_SAO"
    assert got.sao_fora_da_meta == 1
    assert got.bonus_sao_amount == Decimal("300.00")
```

- [ ] **Step 4: Apply migration & run tests**

Run:
```bash
cd backend && alembic upgrade head && pytest tests/test_modules/test_cn_rampagem_models.py -v
```
Expected: migration applies cleanly; 3 tests PASS.
(If the test DB is created fresh per run via metadata, the test still passes because the model columns exist; the migration is verified by `alembic upgrade head` returning success on `e1f2a3b4c5d6`.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/models/cn_monthly_goal.py backend/app/models/cn_monthly_appraisal.py backend/migrations/versions/e1f2a3b4c5d6_cn_rampagem_columns.py backend/tests/test_modules/test_cn_rampagem_models.py
git commit -m "feat(cn): add rampagem db columns + migration"
```

---

## Task 4: Bonus setting helper (`PlatformSetting`)

**Files:**
- Modify: `backend/app/modules/commissions/simulator.py` (or a small helper in `cn_calculator.py`)
- Test: `backend/tests/test_modules/test_cn_rampagem_setting.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_modules/test_cn_rampagem_setting.py`:

```python
from decimal import Decimal
from app.models import PlatformSetting
from app.modules.commissions.cn_calculator import get_rampagem_bonus_sao


def test_default_is_300_when_unset(db_session):
    assert get_rampagem_bonus_sao() == Decimal("300")


def test_reads_value_from_platform_setting(db_session):
    PlatformSetting.set("cn_rampagem_bonus_sao", "450")
    db_session.flush()
    assert get_rampagem_bonus_sao() == Decimal("450")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_modules/test_cn_rampagem_setting.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_rampagem_bonus_sao'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/modules/commissions/cn_calculator.py`, add near the top (after imports):

```python
from app.models import PlatformSetting

RAMPAGEM_BONUS_SAO_KEY = "cn_rampagem_bonus_sao"
DEFAULT_RAMPAGEM_BONUS_SAO = Decimal("300")


def get_rampagem_bonus_sao() -> Decimal:
    """Configurable SAO-fora-da-meta bonus (R$ por SAO). Default 300."""
    raw = PlatformSetting.get(RAMPAGEM_BONUS_SAO_KEY, None)
    if raw in (None, ""):
        return DEFAULT_RAMPAGEM_BONUS_SAO
    try:
        return Decimal(str(raw))
    except (ValueError, ArithmeticError):
        return DEFAULT_RAMPAGEM_BONUS_SAO
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_modules/test_cn_rampagem_setting.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/cn_calculator.py backend/tests/test_modules/test_cn_rampagem_setting.py
git commit -m "feat(cn): configurable rampagem SAO bonus via PlatformSetting"
```

---

## Task 5: Wire rampagem into the appraisal runner

**Files:**
- Modify: `backend/app/modules/commissions/cn_calculator.py`
- Test: `backend/tests/test_modules/test_cn_calculator.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_modules/test_cn_calculator.py`:

```python
from app.models.appraisal import AppraisalStatus


class TestRampagemAppraisal:
    def _ramp_cn(self, session, name, nivel="CN3"):
        u = _make_cn(session, name=name, nivel=nivel)
        u.em_rampagem = True
        session.flush()
        return u

    def test_sem_sao_persists_rampagem_result(self, db_session):
        cn = self._ramp_cn(db_session, "Rafa")
        # goal with SAO target 0 → SEM SAO variant
        g = CnMonthlyGoal(cn_id=cn.id, month=4, year=2026,
                          sao_target=Decimal("0"), vidas_target=Decimal("0"),
                          negocios_cadencia_meta=Decimal("60"),
                          emails_meta=Decimal("400"),
                          qualis_agendadas_meta=Decimal("0"))
        db_session.add(g); db_session.flush()

        run_cn_monthly_appraisal_with_inputs(4, 2026, [{
            "cn_id": str(cn.id),
            "negocios_cadencia_realizado": "103",
            "emails_realizado": "1133",
            "sao_fora_da_meta": "1",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=4, year=2026).one()
        assert a.calc_mode == "RAMPAGEM_SEM_SAO"
        assert str(a.commission_amount) == "3300.00"
        assert a.sao_fora_da_meta == 1
        assert str(a.bonus_sao_amount) == "300.00"

    def test_com_sao_uses_sao_and_qualis(self, db_session):
        cn = self._ramp_cn(db_session, "Bia")
        g = CnMonthlyGoal(cn_id=cn.id, month=5, year=2026,
                          sao_target=Decimal("3"), vidas_target=Decimal("0"),
                          negocios_cadencia_meta=Decimal("0"),
                          emails_meta=Decimal("0"),
                          qualis_agendadas_meta=Decimal("10"))
        db_session.add(g); db_session.flush()

        run_cn_monthly_appraisal_with_inputs(5, 2026, [{
            "cn_id": str(cn.id),
            "sao_realizado": "5",
            "qualis_agendadas_realizado": "10",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=5, year=2026).one()
        assert a.calc_mode == "RAMPAGEM_COM_SAO"
        assert str(a.commission_amount) == "5400.00"

    def test_non_rampagem_cn_uses_normal(self, db_session):
        cn = _make_cn(db_session, name="Normal", nivel="CN1")
        _make_goal(db_session, cn, month=6, year=2026,
                   sao=Decimal("100"), vidas=Decimal("50"))
        run_cn_monthly_appraisal_with_inputs(6, 2026, [{
            "cn_id": str(cn.id),
            "sao_realizado": "100", "vidas_realizado": "50",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=6, year=2026).one()
        assert a.calc_mode == "NORMAL"
        assert str(a.commission_amount) == "2400.00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_modules/test_cn_calculator.py::TestRampagemAppraisal -v`
Expected: FAIL — `calc_mode` not set / commission wrong (runner still calls `simulate_cn`).

- [ ] **Step 3: Refactor the runner to dispatch by mode**

In `backend/app/modules/commissions/cn_calculator.py`:

Add the import at the top:
```python
from app.modules.commissions.simulator import (
    simulate_cn, simulate_cn_auto, vidas_meta_from_sao,
)
```

Add a shared builder near the top (after `get_rampagem_bonus_sao`):
```python
def _build_appraisal(cn, goal, month, year, cn_input):
    """Compute one CN appraisal row from goal + realized inputs, dispatching
    NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO by cn.em_rampagem + sao_target."""
    nivel = cn.nivel if isinstance(cn.nivel, str) else (cn.nivel.value if cn.nivel else "CN1")
    sao_meta = Decimal(str(goal.sao_target))

    def num(key):
        return Decimal(str(cn_input.get(key, 0) or 0))

    result = simulate_cn_auto(
        em_rampagem=bool(getattr(cn, "em_rampagem", False)),
        nivel=nivel,
        sao_meta=sao_meta,
        sao_realizado=num("sao_realizado"),
        vidas_meta=_vidas_meta_for(cn, goal),
        vidas_realizado=num("vidas_realizado"),
        neg_meta=Decimal(str(goal.negocios_cadencia_meta)),
        neg_real=num("negocios_cadencia_realizado"),
        emails_meta=Decimal(str(goal.emails_meta)),
        emails_real=num("emails_realizado"),
        qualis_meta=Decimal(str(goal.qualis_agendadas_meta)),
        qualis_real=num("qualis_agendadas_realizado"),
        sao_fora_da_meta=int(cn_input.get("sao_fora_da_meta", 0) or 0),
        bonus_sao=get_rampagem_bonus_sao(),
    )

    return CnMonthlyAppraisal(
        cn_id=cn.id, month=month, year=year,
        sao_realizado=num("sao_realizado"),
        vidas_realizado=num("vidas_realizado"),
        pct_sao=Decimal(result["pct_sao"]),
        pct_vidas=Decimal(result["pct_vidas"]),
        score_final=Decimal(result["score_final"]),
        multiplicador=Decimal(result["multiplicador"]),
        commission_amount=Decimal(result["commission_amount"]),
        calc_mode=result["calc_mode"],
        negocios_cadencia_realizado=num("negocios_cadencia_realizado"),
        emails_realizado=num("emails_realizado"),
        qualis_agendadas_realizado=num("qualis_agendadas_realizado"),
        sao_fora_da_meta=int(cn_input.get("sao_fora_da_meta", 0) or 0),
        bonus_sao_amount=Decimal(result["bonus_sao_amount"]),
        status=AppraisalStatus.CALCULATING,
    )
```

Then replace the per-CN body inside **both** `run_cn_monthly_appraisal` and
`run_cn_monthly_appraisal_with_inputs` so the appraisal object is built via
`_build_appraisal`. For `run_cn_monthly_appraisal` (zero inputs), pass `cn_input={}`:

```python
        appraisal = _build_appraisal(cn, goal, month, year, {})
        db.session.add(appraisal)
        created += 1
```

For `run_cn_monthly_appraisal_with_inputs`:

```python
        cn_input = inputs_by_cn.get(str(cn.id), {})
        appraisal = _build_appraisal(cn, goal, month, year, cn_input)
        db.session.add(appraisal)
        created += 1
```

(Delete the now-unused inline `simulate_cn(...)`/`CnMonthlyAppraisal(...)` blocks
in both functions.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_modules/test_cn_calculator.py -v`
Expected: PASS (new `TestRampagemAppraisal` + all existing cn_calculator tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/cn_calculator.py backend/tests/test_modules/test_cn_calculator.py
git commit -m "feat(cn): dispatch rampagem modes in monthly appraisal runner"
```

---

## Task 6: API — goals, profile flag, simulate, serializers, bonus setting

**Files:**
- Modify: `backend/app/api/v1/cn_commissions.py`, `backend/app/api/v1/admin.py`
- Test: `backend/tests/test_api/test_cn_rampagem_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api/test_cn_rampagem_api.py`. Mirror the auth/client
setup used in `backend/tests/test_api/test_cn_simulator_profile.py` (open that
file first and copy its fixture/login helper verbatim — do not invent a new auth
flow). Then add:

```python
# --- assumes `client` + an admin-authenticated request helper from the
# --- existing test_cn_simulator_profile.py pattern (copy it here) ---

def test_upsert_goals_accepts_cadence_metas(admin_client, make_cn):
    cn = make_cn(nivel="CN3")
    resp = admin_client.put("/api/v1/commissions/cn/goals", json={
        "month": 4, "year": 2026,
        "items": [{"cn_id": str(cn.id), "sao_target": "0",
                   "negocios_cadencia_meta": "60", "emails_meta": "400",
                   "qualis_agendadas_meta": "0"}],
    })
    assert resp.status_code == 200
    listing = admin_client.get("/api/v1/commissions/cn/goals?month=4&year=2026").get_json()
    row = next(r for r in listing["data"] if r["cn_id"] == str(cn.id))
    assert row["negocios_cadencia_meta"] == "60.00"
    assert row["emails_meta"] == "400.00"


def test_admin_can_set_em_rampagem(admin_client, make_cn):
    cn = make_cn(nivel="CN1")
    resp = admin_client.put(f"/api/v1/admin/users/{cn.id}", json={"em_rampagem": True})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["em_rampagem"] is True


def test_simulate_rampagem_sem_sao(admin_client):
    resp = admin_client.post("/api/v1/commissions/cn/simulate", json={
        "nivel": "CN3", "em_rampagem": True, "sao_meta": "0",
        "negocios_cadencia_meta": "60", "negocios_cadencia_realizado": "103",
        "emails_meta": "400", "emails_realizado": "1133",
        "sao_fora_da_meta": "1",
    })
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["calc_mode"] == "RAMPAGEM_SEM_SAO"
    assert data["commission_amount"] == "3300.00"
```

Note: adapt `admin_client` / `make_cn` to whatever the existing test module
provides (e.g. an `auth_headers` dict + `User` factory). Keep behavior identical.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api/test_cn_rampagem_api.py -v`
Expected: FAIL (fields not accepted / not serialized; simulate lacks rampagem).

- [ ] **Step 3a: Goals — accept & serialize cadence metas**

In `backend/app/api/v1/cn_commissions.py`, inside `upsert_cn_goals`'s loop, after
the `goal.vidas_target = ...` block, add:

```python
            goal.negocios_cadencia_meta = _decimal_or_zero(item.get("negocios_cadencia_meta"))
            goal.emails_meta = _decimal_or_zero(item.get("emails_meta"))
            goal.qualis_agendadas_meta = _decimal_or_zero(item.get("qualis_agendadas_meta"))
```

In `_serialize_cn_row`, add the cadence metas + the CN flag to the returned dict:

```python
        "em_rampagem": bool(getattr(cn, "em_rampagem", False)),
        "negocios_cadencia_meta": str(goal.negocios_cadencia_meta) if goal else "0",
        "emails_meta": str(goal.emails_meta) if goal else "0",
        "qualis_agendadas_meta": str(goal.qualis_agendadas_meta) if goal else "0",
```

- [ ] **Step 3b: Appraisal serializer — expose rampagem fields**

In `_serialize_appraisal`, add:

```python
        "calc_mode": a.calc_mode,
        "negocios_cadencia_realizado": str(a.negocios_cadencia_realizado),
        "emails_realizado": str(a.emails_realizado),
        "qualis_agendadas_realizado": str(a.qualis_agendadas_realizado),
        "sao_fora_da_meta": a.sao_fora_da_meta,
        "bonus_sao_amount": str(a.bonus_sao_amount),
        "atingimento": str(a.score_final),
        "gatilho": str(a.multiplicador),
```

- [ ] **Step 3c: Simulate — support rampagem**

In `simulate_cn_endpoint`, replace the `result = simulate_cn(...)` block with a
dispatch via `simulate_cn_auto`. Read `em_rampagem` from the body for ADMIN, and
from `user.em_rampagem` for a CN:

```python
    from app.modules.commissions.simulator import simulate_cn_auto
    from app.modules.commissions.cn_calculator import get_rampagem_bonus_sao

    if user.role == UserRole.CN:
        em_rampagem = bool(getattr(user, "em_rampagem", False))
    else:
        em_rampagem = bool(body.get("em_rampagem", False))

    def _b(key):
        from decimal import Decimal as _D
        v = body.get(key)
        return _D(str(v)) if v not in (None, "") else _D("0")

    try:
        sao_meta = _b("sao_meta")
        result = simulate_cn_auto(
            em_rampagem=em_rampagem, nivel=nivel, sao_meta=sao_meta,
            sao_realizado=_b("sao_realizado"),
            vidas_meta=(Decimal(str(body["vidas_meta"]))
                        if body.get("vidas_meta") not in (None, "")
                        else vidas_meta_from_sao(sao_meta, porte)),
            vidas_realizado=_b("vidas_realizado"),
            neg_meta=_b("negocios_cadencia_meta"), neg_real=_b("negocios_cadencia_realizado"),
            emails_meta=_b("emails_meta"), emails_real=_b("emails_realizado"),
            qualis_meta=_b("qualis_agendadas_meta"), qualis_real=_b("qualis_agendadas_realizado"),
            sao_fora_da_meta=int(body.get("sao_fora_da_meta", 0) or 0),
            bonus_sao=get_rampagem_bonus_sao(),
        )
        result.update({"nivel": nivel, "porte": porte})
    except (KeyError, TypeError, ValueError, InvalidOperation) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400
    return jsonify({"data": result})
```

(Keep the existing CN-vs-admin `nivel`/`porte` resolution above this block.)

- [ ] **Step 3d: Admin — accept & serialize `em_rampagem`**

In `backend/app/api/v1/admin.py`, inside `_apply_profile_fields`, after the
`salario_base` block and before the role-reset block:

```python
    if "em_rampagem" in data:
        user.em_rampagem = bool(data.get("em_rampagem"))
```

In the same `role != CN` reset block, also clear it:

```python
    if "role" in data and user.role != UserRole.CN:
        user.nivel = None
        user.porte = None
        user.em_rampagem = False
```

In `_serialize_user` add:

```python
        "em_rampagem": bool(getattr(u, "em_rampagem", False)),
```

And in `_serialize_team`'s member dict, add the same `"em_rampagem"` key.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api/test_cn_rampagem_api.py tests/test_api/test_cn_simulator_profile.py tests/test_api/test_admin_cn_profile.py -v`
Expected: PASS (new + existing API tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/cn_commissions.py backend/app/api/v1/admin.py backend/tests/test_api/test_cn_rampagem_api.py
git commit -m "feat(cn): rampagem fields in goals/simulate/admin/serializers API"
```

---

## Task 7: Bonus-setting endpoint (Settings)

**Files:**
- Modify: `backend/app/api/v1/admin.py` (or wherever PlatformSetting endpoints live — grep first)
- Test: `backend/tests/test_api/test_cn_rampagem_api.py`

- [ ] **Step 1: Locate the settings endpoints**

Run: `cd backend && grep -rn "platform_settings\|PlatformSetting\|/settings" app/api/v1/ | head`
Use the existing settings GET/PUT handler. If a generic key/value settings endpoint
already exists, **no backend change is needed** — the key `cn_rampagem_bonus_sao`
flows through it; skip to Step 4 and only add the frontend field in Task 11.
If settings are per-key, add `cn_rampagem_bonus_sao` to the allowed keys list.

- [ ] **Step 2: Write the failing test (only if a code change is needed)**

```python
def test_set_and_get_rampagem_bonus_setting(admin_client):
    put = admin_client.put("/api/v1/settings", json={"cn_rampagem_bonus_sao": "450"})
    assert put.status_code in (200, 204)
    got = admin_client.get("/api/v1/settings").get_json()
    # adapt to the real settings response shape
    assert str(got["data"]["cn_rampagem_bonus_sao"]) == "450"
```

Adapt the URL/shape to the actual settings API discovered in Step 1.

- [ ] **Step 3: Implement (only if needed)**

Add `cn_rampagem_bonus_sao` to the settings allow-list / schema following the
existing pattern for other keys. No new endpoint if a generic one exists.

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_api/test_cn_rampagem_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/admin.py backend/tests/test_api/test_cn_rampagem_api.py
git commit -m "feat(cn): expose rampagem bonus setting via settings API"
```

---

## Task 8: Frontend calc mirror (`calc.cljs`)

**Files:**
- Modify: `frontend/src/app/views/cn/calc.cljs`

- [ ] **Step 1: Add rampagem régua + calc fns**

In `frontend/src/app/views/cn/calc.cljs`, after `regua`:

```clojure
(defn regua-rampagem
  "Régua da rampagem: limites superiores INCLUSIVOS (≠ regua normal)."
  [score]
  (cond
    (<= score 0.20) 0
    (<= score 0.40) 0.20
    (<= score 1.00) score
    (<= score 1.10) 1.20
    (<  score 1.40) 1.80
    :else 2.10))

(defn- capped [num den]
  (if (and den (pos? den)) (min (/ num den) 1) 0))

(defn- uncapped [num den]
  (if (and den (pos? den)) (/ num den) 0))

(defn rampagem-sem-sao
  [{:keys [nivel neg_meta neg_real emails_meta emails_real sao_fora_da_meta bonus_sao]}]
  (let [atg   (+ (* 0.5 (capped (or (->num neg_real) 0) (or (->num neg_meta) 0)))
                 (* 0.5 (capped (or (->num emails_real) 0) (or (->num emails_meta) 0))))
        gat   (regua-rampagem atg)
        base  (get cn-bases nivel 0)
        bonus (* (or (->num bonus_sao) 300) (or (->num sao_fora_da_meta) 0))]
    {:calc_mode "RAMPAGEM_SEM_SAO" :atingimento atg :gatilho gat
     :bonus_sao_amount bonus :commission_amount (+ (* base gat) bonus)
     :score_final atg :multiplicador gat}))

(defn rampagem-com-sao
  [{:keys [nivel sao_meta sao_real qualis_meta qualis_real]}]
  (let [atg  (+ (* 0.5 (uncapped (or (->num sao_real) 0) (or (->num sao_meta) 0)))
               (* 0.5 (capped (or (->num qualis_real) 0) (or (->num qualis_meta) 0))))
        gat  (regua-rampagem atg)
        base (get cn-bases nivel 0)]
    {:calc_mode "RAMPAGEM_COM_SAO" :atingimento atg :gatilho gat
     :bonus_sao_amount 0 :commission_amount (* base gat)
     :score_final atg :multiplicador gat}))

(defn calculate-auto
  "Pick NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO from em_rampagem + sao_meta."
  [{:keys [em_rampagem sao_meta] :as form}]
  (cond
    (not em_rampagem) (assoc (calculate form) :calc_mode "NORMAL")
    (pos? (or (->num sao_meta) 0)) (rampagem-com-sao form)
    :else (rampagem-sem-sao form)))
```

- [ ] **Step 2: Verify the frontend compiles**

Run the project's CLJS build/check (see `frontend/` README or `package.json`).
Run: `cd frontend && npx shadow-cljs compile app` (or the project's configured build alias).
Expected: compile succeeds with no warnings about `calc.cljs`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/cn/calc.cljs
git commit -m "feat(cn): mirror rampagem calc in calc.cljs"
```

---

## Task 9: Admin user modal — `em_rampagem` toggle

**Files:**
- Modify: `frontend/src/app/views/revops/users.cljs`

- [ ] **Step 1: Add the flag to the form & payload**

In `empty-form`, add `:em_rampagem false`.
In `form-from-user`'s `select-keys` vector, add `:em_rampagem`.

Inside the `(when (= (:role @form) "CN") ...)` block, after the porte select, add
a checkbox (mirror the existing `left_company` checkbox markup):

```clojure
                [:label {:style {:display "flex" :align-items "center" :gap "8px"
                                 :font-size "13px" :color "var(--fg-2)"}}
                 [:input {:type "checkbox"
                          :checked (boolean (:em_rampagem @form))
                          :on-change #(swap! form assoc :em_rampagem
                                             (.. % -target -checked))}]
                 [:span "CN em rampagem"]]
```

In the submit `payload` builder, ensure non-CN clears it:

```clojure
                                  payload (if (= (:role payload) "CN")
                                            payload
                                            (assoc payload :nivel nil :porte nil :em_rampagem false))
```

- [ ] **Step 2: Verify compile + smoke**

Run: `cd frontend && npx shadow-cljs compile app`
Expected: compiles. (Manual smoke happens in Task 12.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/users.cljs
git commit -m "feat(cn): em_rampagem toggle in admin user modal"
```

---

## Task 10: CN goals page — cadence meta inputs

**Files:**
- Modify: `frontend/src/app/views/revops/cn_goals.cljs`

- [ ] **Step 1: Show cadence metas for rampagem CNs**

The goals listing now returns `em_rampagem`, `negocios_cadencia_meta`,
`emails_meta`, `qualis_agendadas_meta`. For a row where `(:em_rampagem row)` is
true, render the relevant meta inputs and include them in the saved item.

Add columns to the table header (after "Meta SAO"):
```clojure
             [:th.right "Cadência (rampagem)"]
```

In the row, when `(:em_rampagem row)`, render the variant-specific inputs in that
cell (SAO=0 → negócios + emails; SAO>0 → qualis):
```clojure
                 [:td.right
                  (if (:em_rampagem row)
                    (let [sao (calc/->num (field-val row :sao_target))]
                      (if (and sao (pos? sao))
                        [:input.field-input
                         {:type "number" :placeholder "Qualis (meta)"
                          :style {:width "120px" :text-align "right"}
                          :value (field-val row :qualis_agendadas_meta)
                          :on-change #(swap! edits assoc-in [(:cn_id row) :qualis_agendadas_meta] (.. % -target -value))}]
                        [:div {:style {:display "flex" :gap "6px" :justify-content "flex-end"}}
                         [:input.field-input
                          {:type "number" :placeholder "Negócios (meta)"
                           :style {:width "120px" :text-align "right"}
                           :value (field-val row :negocios_cadencia_meta)
                           :on-change #(swap! edits assoc-in [(:cn_id row) :negocios_cadencia_meta] (.. % -target -value))}]
                         [:input.field-input
                          {:type "number" :placeholder "Emails (meta)"
                           :style {:width "120px" :text-align "right"}
                           :value (field-val row :emails_meta)
                           :on-change #(swap! edits assoc-in [(:cn_id row) :emails_meta] (.. % -target -value))}]]))
                    [:span.muted "—"])]
```

In the save handler's `items` map, include the cadence metas (falling back to the
existing row value):
```clojure
                                               {:cn_id      cn-id
                                                :sao_target (or (:sao_target vals) (:sao_target row) "0")
                                                :negocios_cadencia_meta (or (:negocios_cadencia_meta vals) (:negocios_cadencia_meta row) "0")
                                                :emails_meta (or (:emails_meta vals) (:emails_meta row) "0")
                                                :qualis_agendadas_meta (or (:qualis_agendadas_meta vals) (:qualis_agendadas_meta row) "0")}
```

Update the table's `col-span` placeholders (loading/empty rows) from 3 to 4.

- [ ] **Step 2: Verify compile**

Run: `cd frontend && npx shadow-cljs compile app`
Expected: compiles.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/cn_goals.cljs
git commit -m "feat(cn): cadence meta inputs for rampagem on CN goals page"
```

---

## Task 11: CN appraisal page — rampagem inputs + live preview

**Files:**
- Modify: `frontend/src/app/views/revops/cn_appraisal.cljs`

- [ ] **Step 1: Branch the row by mode**

The goals rows now carry `em_rampagem` and the cadence metas. In the `rows` mapv,
compute the preview with `calc/calculate-auto` instead of `calc/calculate`,
threading the cadence fields and `em_rampagem`. For rampagem rows, store the
cadence realizados from `@edits` (same `field-val` pattern as SAO/vidas).

Replace the `preview (calc/calculate {...})` form with:
```clojure
                               preview (calc/calculate-auto
                                        {:nivel (:nivel g)
                                         :em_rampagem (:em_rampagem g)
                                         :sao_meta (:sao_target g)
                                         :sao_realizado sao-real
                                         :vidas_meta vidas-meta
                                         :vidas_realizado vidas-real
                                         :neg_meta (:negocios_cadencia_meta g)
                                         :neg_real (field-val (:cn_id g) :negocios_cadencia_realizado (when a (:negocios_cadencia_realizado a)))
                                         :emails_meta (:emails_meta g)
                                         :emails_real (field-val (:cn_id g) :emails_realizado (when a (:emails_realizado a)))
                                         :qualis_meta (:qualis_agendadas_meta g)
                                         :qualis_real (field-val (:cn_id g) :qualis_agendadas_realizado (when a (:qualis_agendadas_realizado a)))
                                         :sao_fora_da_meta (field-val (:cn_id g) :sao_fora_da_meta (when a (:sao_fora_da_meta a)))})
```
(assoc the extra realizados onto the row map alongside `:sao_realizado` so `run!`
can read them.)

- [ ] **Step 2: Swap the input columns per mode**

For a rampagem row, the SAO/vidas realizado inputs are replaced by the cadence
inputs. Implement a helper that, given the row, returns the right input cells:
- `em_rampagem` + sao_meta=0 → "Negócios realiz.", "Emails realiz.", "SAO fora da meta"
- `em_rampagem` + sao_meta>0 → "SAO realiz.", "Qualis realiz."
- else → existing "SAO realiz.", "Vidas realiz."

Keep the Score/Mult./Comissão columns but relabel Score→"Atingimento" and
Mult.→"Gatilho" when the row is rampagem (use `(:calc_mode preview)`), reading
`(:atingimento preview)` / `(:gatilho preview)`. The simplest non-invasive
approach: keep the same columns and feed them `:score_final`/`:multiplicador`
(which equal atingimento/gatilho for rampagem rows — already aliased in calc).

- [ ] **Step 3: Include cadence realizados in the run! payload**

In `run!`, build each input with the cadence fields when the row is rampagem:
```clojure
                                                {:cn_id (:cn_id row)
                                                 :sao_realizado (if (str/blank? s) "0" s)
                                                 :vidas_realizado (if (str/blank? v) "0" v)
                                                 :negocios_cadencia_realizado (str (or (:negocios_cadencia_realizado row) "0"))
                                                 :emails_realizado (str (or (:emails_realizado row) "0"))
                                                 :qualis_agendadas_realizado (str (or (:qualis_agendadas_realizado row) "0"))
                                                 :sao_fora_da_meta (str (or (:sao_fora_da_meta row) "0"))}
```

- [ ] **Step 4: Verify compile**

Run: `cd frontend && npx shadow-cljs compile app`
Expected: compiles with no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/views/revops/cn_appraisal.cljs
git commit -m "feat(cn): rampagem inputs + atingimento/gatilho preview on apuração"
```

---

## Task 12: Settings field for the SAO bonus + manual verification

**Files:**
- Modify: `frontend/src/app/views/revops/settings.cljs`

- [ ] **Step 1: Add the bonus field**

Add a numeric field bound to the `cn_rampagem_bonus_sao` setting, following the
existing settings field pattern in `settings.cljs` (read current value, PUT on
change). Label: "Bônus por SAO fora da meta (rampagem)", default 300.

- [ ] **Step 2: Verify compile**

Run: `cd frontend && npx shadow-cljs compile app`
Expected: compiles.

- [ ] **Step 3: Manual end-to-end verification (preview tools)**

Start the dev stack (Flask :5000 + shadow :8080, per the project's dev notes) and,
using the preview tools:
1. Admin → Usuários: edit a CN, check "CN em rampagem", save.
2. Metas CN: for that CN leave SAO=0, set Negócios=60, Emails=400, save.
3. Apuração CN: enter Negócios=103, Emails=1133, SAO fora da meta=1 → preview
   shows Atingimento 100%, Gatilho 100%, Comissão **R$ 3.300**. Run apuração; the
   saved row keeps R$ 3.300 and `calc_mode` RAMPAGEM_SEM_SAO.
4. Set SAO meta=3 for a month, mark realizado SAO=5, Qualis meta=10/realiz=10 →
   Comissão **R$ 5.400** (gatilho 180%).
5. Settings: change the bonus to 450, re-run a SEM-SAO apuração with 1 SAO fora →
   Comissão R$ 3.000 + 450 = **R$ 3.450**.

Capture a screenshot of the R$ 3.300 preview as proof.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/views/revops/settings.cljs
git commit -m "feat(cn): settings field for rampagem SAO bonus"
```

---

## Task 13: Full suite + open follow-up issue

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && pytest -q`
Expected: all green (no regressions in cn_calculator, simulator, admin, cycles).

- [ ] **Step 2: Open the follow-up issue for the NORMAL régua**

Per the spec decision, file a GitHub issue (`galeazzofs/plataforma-gestao-rv-piposaude`):
title "Avaliar alinhar a régua do cálculo NORMAL (`_regua`) à tabela de limites inclusivos";
body: the boundary divergence (100%→120% vs 100%→100%, 110%→180% vs 110%→120%),
that rampagem already uses inclusive bounds (`_regua_rampagem`), and the impact of
changing the normal régua (existing tests + locked appraisals). Label `needs-triage`.

Run:
```bash
gh issue create -R galeazzofs/plataforma-gestao-rv-piposaude \
  -t "Avaliar alinhar régua do cálculo NORMAL à tabela de limites inclusivos" \
  -l needs-triage \
  -b "A régua de rampagem (_regua_rampagem) usa limites superiores inclusivos (100%→em linha, 110%→120%, 140%→210%), conforme a tabela do print. O cálculo NORMAL (_regua) ainda usa limites exclusivos: 100%→120%, 110%→180%. Avaliar se o normal deve ser alinhado à mesma tabela. Impacto: muda resultados de borda do cálculo normal e quebra testes existentes (test_simulator TestRegua); apurações já LOCKED não devem ser recalculadas. Origem: spec docs/superpowers/specs/2026-06-16-cn-rampagem-design.md."
```

- [ ] **Step 3: Final commit (if anything pending)**

```bash
git add -A && git commit -m "chore(cn): rampagem feature complete" || echo "nothing to commit"
```

---

## Self-review notes

- **Spec coverage:** régua inclusiva (T1) · 3 modos + dispatcher (T2) · DB+migration (T3) · bônus configurável (T4) · runner (T5) · API goals/profile/simulate/serializers (T6) · settings endpoint (T7) · calc.cljs (T8) · admin toggle (T9) · goals UI (T10) · apuração UI (T11) · settings UI + manual verify (T12) · suite + follow-up issue (T13). All spec sections mapped.
- **Reuse decision honored:** `score_final`=atingimento, `multiplicador`=gatilho; quarterly bonus untouched (reads `sao_realizado`/`sao_target`).
- **Names consistent:** `simulate_cn_auto`, `simulate_cn_rampagem_sem_sao`, `simulate_cn_rampagem_com_sao`, `_regua_rampagem`, `get_rampagem_bonus_sao`, `_build_appraisal`, `calc_mode` values `NORMAL`/`RAMPAGEM_SEM_SAO`/`RAMPAGEM_COM_SAO` used identically across backend + frontend.
- **Verify-before-claim:** every backend task ends in a pytest run with expected output; frontend tasks compile; T12 is real end-to-end proof.
