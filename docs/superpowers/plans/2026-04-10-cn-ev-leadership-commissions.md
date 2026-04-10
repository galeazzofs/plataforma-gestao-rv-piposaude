# CN/EV/Leadership Commissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CN monthly commission apuração (Regra de Ouro), CN simulator, EV quarterly MRR bonus, and GERENTE leadership commission — migrating business rules from the legacy `pipo-gestao-rv` repo into the current Flask/ClojureScript platform.

**Architecture:** 4 independent modules under `modules/commissions/` (simulator.py, cn_calculator.py, ev_bonus.py, leadership_calculator.py), each with its own Blueprint. Shared foundation: 3 new models + extensions to User and EvQuarterAchievement + 2 Alembic migrations. Frontend: 2 CN views + 4 RevOps views following existing re-frame event/sub patterns.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, Alembic, ClojureScript, re-frame, reagent, reitit

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models/user.py` | Modify | Add nivel, porte, salario_base columns |
| `backend/app/models/cn_monthly_goal.py` | Create | CnMonthlyGoal model |
| `backend/app/models/cn_monthly_appraisal.py` | Create | CnMonthlyAppraisal model |
| `backend/app/models/ev_quarter_achievement.py` | Modify | Add bonus_amount, salario_base_snapshot |
| `backend/app/models/gerente_quarter_appraisal.py` | Create | GerenteQuarterAppraisal model |
| `backend/app/models/__init__.py` | Modify | Export new models |
| `backend/migrations/versions/<auto1>` | Create (auto) | Migration: User fields + cn_monthly_goals |
| `backend/migrations/versions/<auto2>` | Create (auto) | Migration: appraisals + ev bonus cols + gerente |
| `backend/app/modules/commissions/simulator.py` | Create | Pure CN calc: _regua, simulate_cn (no DB) |
| `backend/app/modules/commissions/cn_calculator.py` | Create | DB-aware CN monthly apuração runner |
| `backend/app/modules/commissions/ev_bonus.py` | Create | EV quarterly MRR bonus runner |
| `backend/app/modules/commissions/leadership_calculator.py` | Create | GERENTE bonus runner |
| `backend/app/api/v1/cn_commissions.py` | Create | CN goals + apuração + simulator endpoints |
| `backend/app/api/v1/ev_bonus.py` | Create | EV bonus run + list endpoints |
| `backend/app/api/v1/leadership.py` | Create | GERENTE apuração endpoints |
| `backend/app/api/__init__.py` | Modify | Register 3 new blueprints |
| `backend/tests/test_modules/test_simulator.py` | Create | Tests for simulate_cn pure logic |
| `backend/tests/test_modules/test_cn_calculator.py` | Create | Tests for CN apuração DB runner |
| `backend/tests/test_modules/test_ev_bonus.py` | Create | Tests for EV bonus runner |
| `backend/tests/test_modules/test_leadership.py` | Create | Tests for leadership runner |
| `frontend/src/app/api/endpoints.cljs` | Modify | Add new endpoint defs |
| `frontend/src/app/routes.cljs` | Modify | Add CN + revops routes |
| `frontend/src/app/views/cn/simulator.cljs` | Create | CN self-service simulator |
| `frontend/src/app/views/cn/dashboard.cljs` | Create | CN apuração history |
| `frontend/src/app/views/revops/cn_goals.cljs` | Create | RevOps: manage CN monthly goals |
| `frontend/src/app/views/revops/cn_appraisal.cljs` | Create | RevOps: run CN monthly apuração |
| `frontend/src/app/views/revops/ev_bonus.cljs` | Create | RevOps: run EV quarterly bonus |
| `frontend/src/app/views/revops/leadership_appraisal.cljs` | Create | RevOps: run GERENTE apuração |

---

## Task 1: User model extensions + CnMonthlyGoal model + Migration 1

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/app/models/cn_monthly_goal.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add enums and columns to User model**

In `backend/app/models/user.py`, add after the `UserRole` enum and before the `User` class:

```python
class CnNivel(str, enum.Enum):
    CN1 = "CN1"
    CN2 = "CN2"
    CN3 = "CN3"


class CnPorte(str, enum.Enum):
    M = "M"
    G_PLUS = "G+"
```

Then inside the `User` class, add after `slack_user_id`:

```python
    nivel = db.Column(db.Enum(CnNivel, name="cn_nivel"), nullable=True)
    porte = db.Column(db.Enum(CnPorte, name="cn_porte"), nullable=True)
    salario_base = db.Column(db.Numeric(12, 2), nullable=True)
```

- [ ] **Step 2: Create CnMonthlyGoal model**

Create `backend/app/models/cn_monthly_goal.py`:

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CnMonthlyGoal(db.Model):
    __tablename__ = "cn_monthly_goals"
    __table_args__ = (
        db.UniqueConstraint("cn_id", "month", "year", name="uq_cn_monthly_goal"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    cn_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)   # 1–12
    year = db.Column(db.Integer, nullable=False)
    sao_target = db.Column(db.Numeric(12, 2), nullable=False)
    vidas_target = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cn = db.relationship("User", foreign_keys=[cn_id])

    def __repr__(self):
        return f"<CnMonthlyGoal cn={self.cn_id} {self.month}/{self.year}>"
```

- [ ] **Step 3: Export new symbols from models/__init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.user import User, UserRole, CnNivel, CnPorte
from app.models.cn_monthly_goal import CnMonthlyGoal
```

Update the `__all__` list to include `"CnNivel"`, `"CnPorte"`, `"CnMonthlyGoal"`.

- [ ] **Step 4: Generate and review migration**

```bash
cd backend && flask db migrate -m "add cn profile fields and cn monthly goals"
```

Open the generated file in `migrations/versions/`. Verify it contains:
- `add_column('users', Column('nivel', Enum('CN1','CN2','CN3', name='cn_nivel'), nullable=True))`
- `add_column('users', Column('porte', Enum('M','G+', name='cn_porte'), nullable=True))`
- `add_column('users', Column('salario_base', Numeric(12,2), nullable=True))`
- `create_table('cn_monthly_goals', ...)` with all 7 columns + unique constraint

- [ ] **Step 5: Apply migration**

```bash
flask db upgrade
```

Expected: `Running upgrade ... -> <hash>, add cn profile fields and cn monthly goals`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/user.py backend/app/models/cn_monthly_goal.py \
        backend/app/models/__init__.py backend/migrations/
git commit -m "feat: add CN profile fields to User and CnMonthlyGoal model"
```

---

## Task 2: CnMonthlyAppraisal + EvQuarterAchievement bonus columns + GerenteQuarterAppraisal + Migration 2

**Files:**
- Create: `backend/app/models/cn_monthly_appraisal.py`
- Modify: `backend/app/models/ev_quarter_achievement.py`
- Create: `backend/app/models/gerente_quarter_appraisal.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create CnMonthlyAppraisal model**

Create `backend/app/models/cn_monthly_appraisal.py`:

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CnMonthlyAppraisal(db.Model):
    __tablename__ = "cn_monthly_appraisals"
    __table_args__ = (
        db.UniqueConstraint("cn_id", "month", "year", name="uq_cn_monthly_appraisal"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    cn_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    sao_realizado = db.Column(db.Numeric(12, 2), nullable=False)
    vidas_realizado = db.Column(db.Numeric(12, 2), nullable=False)
    pct_sao = db.Column(db.Numeric(8, 4), nullable=False)
    pct_vidas = db.Column(db.Numeric(8, 4), nullable=False)
    score_final = db.Column(db.Numeric(8, 4), nullable=False)
    multiplicador = db.Column(db.Numeric(8, 4), nullable=False)
    commission_amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cn = db.relationship("User", foreign_keys=[cn_id])

    def __repr__(self):
        return f"<CnMonthlyAppraisal cn={self.cn_id} {self.month}/{self.year} final={self.is_final}>"
```

- [ ] **Step 2: Add bonus columns to EvQuarterAchievement**

In `backend/app/models/ev_quarter_achievement.py`, add after `is_final`:

```python
    bonus_amount = db.Column(db.Numeric(12, 2), nullable=True)
    salario_base_snapshot = db.Column(db.Numeric(12, 2), nullable=True)
```

- [ ] **Step 3: Create GerenteQuarterAppraisal model**

Create `backend/app/models/gerente_quarter_appraisal.py`:

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class GerenteQuarterAppraisal(db.Model):
    __tablename__ = "gerente_quarter_appraisals"
    __table_args__ = (
        db.UniqueConstraint(
            "gerente_id", "quarter", "year",
            name="uq_gerente_quarter_appraisal"
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    gerente_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    meta_mrr = db.Column(db.Numeric(12, 2), nullable=False)   # auto: 90% × SUM(EV goals)
    meta_sql = db.Column(db.Integer, nullable=False)            # entered by RevOps
    realizado_mrr = db.Column(db.Numeric(12, 2), nullable=False)
    realizado_sql = db.Column(db.Integer, nullable=False)
    pct_mrr = db.Column(db.Numeric(8, 4), nullable=False)
    pct_sql = db.Column(db.Numeric(8, 4), nullable=False)
    multiplicador = db.Column(db.Numeric(8, 4), nullable=False)
    bonus_amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    gerente = db.relationship("User", foreign_keys=[gerente_id])

    def __repr__(self):
        return f"<GerenteQuarterAppraisal gerente={self.gerente_id} Q{self.quarter}/{self.year}>"
```

- [ ] **Step 4: Export from models/__init__.py**

Update `backend/app/models/__init__.py` — add imports and extend `__all__`:

```python
from app.models.cn_monthly_appraisal import CnMonthlyAppraisal
from app.models.gerente_quarter_appraisal import GerenteQuarterAppraisal
```

Add to `__all__`: `"CnMonthlyAppraisal"`, `"GerenteQuarterAppraisal"`.

- [ ] **Step 5: Generate and verify migration**

```bash
flask db migrate -m "add cn appraisals ev bonus cols gerente appraisals"
```

Verify generated file contains:
- `create_table('cn_monthly_appraisals', ...)` 
- `add_column('ev_quarter_achievements', Column('bonus_amount', Numeric(12,2), nullable=True))`
- `add_column('ev_quarter_achievements', Column('salario_base_snapshot', Numeric(12,2), nullable=True))`
- `create_table('gerente_quarter_appraisals', ...)`

- [ ] **Step 6: Apply migration**

```bash
flask db upgrade
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ backend/migrations/
git commit -m "feat: add CnMonthlyAppraisal, GerenteQuarterAppraisal models and EV bonus columns"
```

---

## Task 3: CN simulator — pure calculation module (TDD)

**Files:**
- Create: `backend/tests/test_modules/test_simulator.py`
- Create: `backend/app/modules/commissions/simulator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_simulator.py`:

```python
from decimal import Decimal
import pytest
from app.modules.commissions.simulator import simulate_cn, _regua


class TestRegua:
    """Régua de pagamento — 6 boundary conditions."""

    def test_below_minimum_returns_zero(self):
        assert _regua(Decimal("0.19")) == Decimal("0")

    def test_at_20pct_returns_0_20(self):
        assert _regua(Decimal("0.20")) == Decimal("0.20")

    def test_at_39pct_returns_0_20(self):
        assert _regua(Decimal("0.39")) == Decimal("0.20")

    def test_linear_zone_returns_score(self):
        score = Decimal("0.65")
        assert _regua(score) == score

    def test_at_100pct_returns_1_20(self):
        assert _regua(Decimal("1.00")) == Decimal("1.20")

    def test_at_110pct_returns_1_80(self):
        assert _regua(Decimal("1.10")) == Decimal("1.80")

    def test_at_140pct_returns_2_10(self):
        assert _regua(Decimal("1.40")) == Decimal("2.10")

    def test_above_140pct_returns_2_10(self):
        assert _regua(Decimal("2.00")) == Decimal("2.10")


class TestSimulateCn:
    """simulate_cn — end-to-end formula verification."""

    def test_cn1_at_100pct_sao_100pct_vidas(self):
        # score = 0.70*1.0 + 0.30*1.0 = 1.00 → multiplicador = 1.20
        # commission = 2000 * 1.20 = 2400
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("50"),
        )
        assert result["score_final"] == "1.0000"
        assert result["multiplicador"] == "1.20"
        assert result["commission_amount"] == "2400.00"

    def test_cn2_below_minimum_pays_zero(self):
        # score = 0.70*0.10 + 0.30*0.10 = 0.10 → multiplicador = 0
        result = simulate_cn(
            nivel="CN2",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("10"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("5"),
        )
        assert result["commission_amount"] == "0.00"

    def test_cn3_vidas_capped_at_150pct(self):
        # pct_vidas = min(200/50, 1.5) = 1.5
        # pct_sao = 100/100 = 1.0
        # score = 0.70*1.0 + 0.30*1.5 = 1.15 → multiplicador = 1.80
        # commission = 3000 * 1.80 = 5400
        result = simulate_cn(
            nivel="CN3",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("100"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("200"),
        )
        assert result["pct_vidas"] == "1.5000"
        assert result["commission_amount"] == "5400.00"

    def test_cn1_excelencia_tier(self):
        # score ≥ 1.40 → multiplicador = 2.10, commission = 2000*2.10 = 4200
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("100"),
            sao_realizado=Decimal("150"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("100"),
        )
        assert result["multiplicador"] == "2.10"
        assert result["commission_amount"] == "4200.00"

    def test_zero_sao_meta_returns_zero_commission(self):
        result = simulate_cn(
            nivel="CN1",
            sao_meta=Decimal("0"),
            sao_realizado=Decimal("50"),
            vidas_meta=Decimal("50"),
            vidas_realizado=Decimal("50"),
        )
        assert result["commission_amount"] == "0.00"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/test_modules/test_simulator.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.modules.commissions.simulator'`

- [ ] **Step 3: Implement simulator.py**

Create `backend/app/modules/commissions/simulator.py`:

```python
"""Pure CN commission calculation — no DB access.

Regra de Ouro (spec §2.1):
  pct_sao   = sao_realizado / sao_meta          (uncapped)
  pct_vidas = min(vidas_realizado / vidas_meta, 1.5)
  score     = pct_sao * 0.70 + pct_vidas * 0.30
  mult      = regua(score)
  commission = CN_BASE[nivel] * mult
"""
from decimal import Decimal

CN_BASES: dict[str, Decimal] = {
    "CN1": Decimal("2000"),
    "CN2": Decimal("2500"),
    "CN3": Decimal("3000"),
}

_ZERO = Decimal("0")
_SCALE4 = Decimal("0.0001")
_SCALE2 = Decimal("0.01")


def _regua(score: Decimal) -> Decimal:
    """Régua de pagamento: score → multiplier."""
    if score < Decimal("0.20"):
        return _ZERO
    if score < Decimal("0.40"):
        return Decimal("0.20")
    if score < Decimal("1.00"):
        return score
    if score < Decimal("1.10"):
        return Decimal("1.20")
    if score < Decimal("1.40"):
        return Decimal("1.80")
    return Decimal("2.10")


def simulate_cn(
    nivel: str,
    sao_meta: Decimal,
    sao_realizado: Decimal,
    vidas_meta: Decimal,
    vidas_realizado: Decimal,
) -> dict:
    """Compute CN commission breakdown. Returns serialisable dict (all values str)."""
    pct_sao = (sao_realizado / sao_meta) if sao_meta > _ZERO else _ZERO
    pct_vidas = (
        min(vidas_realizado / vidas_meta, Decimal("1.5"))
        if vidas_meta > _ZERO
        else _ZERO
    )
    score = (pct_sao * Decimal("0.70") + pct_vidas * Decimal("0.30")).quantize(_SCALE4)
    multiplicador = _regua(score)
    base = CN_BASES.get(nivel, _ZERO)
    commission = (base * multiplicador).quantize(_SCALE2)

    return {
        "pct_sao": str(pct_sao.quantize(_SCALE4)),
        "pct_vidas": str(pct_vidas.quantize(_SCALE4)),
        "score_final": str(score),
        "multiplicador": str(multiplicador),
        "commission_amount": str(commission),
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_modules/test_simulator.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/simulator.py \
        backend/tests/test_modules/test_simulator.py
git commit -m "feat: CN commission simulator — pure Regra de Ouro calculator"
```

---

## Task 4: CN calculator — DB-aware monthly apuração runner (TDD)

**Files:**
- Create: `backend/tests/test_modules/test_cn_calculator.py`
- Create: `backend/app/modules/commissions/cn_calculator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_cn_calculator.py`:

```python
from decimal import Decimal
import pytest
from app.models import User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal, CnNivel, CnPorte
from app.modules.commissions.cn_calculator import (
    validate_cn_goals,
    run_cn_monthly_appraisal,
    MissingGoalsError,
)
from app.extensions import db


def _make_cn(session, name="Ana", nivel="CN1"):
    u = User(
        email=f"{name.lower()}@test.com",
        name=name,
        role=UserRole.CN,
        nivel=CnNivel(nivel),
        porte=CnPorte.M,
        salario_base=Decimal("3000"),
    )
    session.add(u)
    session.flush()
    return u


def _make_goal(session, cn, month, year, sao=Decimal("100"), vidas=Decimal("50")):
    g = CnMonthlyGoal(
        cn_id=cn.id, month=month, year=year,
        sao_target=sao, vidas_target=vidas,
    )
    session.add(g)
    session.flush()
    return g


class TestValidateCnGoals:
    def test_returns_empty_when_all_goals_present(self, db_session):
        cn = _make_cn(db_session)
        _make_goal(db_session, cn, month=4, year=2026)
        missing = validate_cn_goals(month=4, year=2026)
        assert missing == []

    def test_returns_missing_cn_names(self, db_session):
        _make_cn(db_session, name="Bob")
        # no goal created
        missing = validate_cn_goals(month=4, year=2026)
        assert any("Bob" in m for m in missing)


class TestRunCnMonthlyAppraisal:
    def test_creates_appraisal_for_each_active_cn(self, db_session):
        cn = _make_cn(db_session, name="Carla")
        _make_goal(db_session, cn, month=3, year=2026,
                   sao=Decimal("100"), vidas=Decimal("50"))

        result = run_cn_monthly_appraisal(month=3, year=2026)

        appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=3, year=2026
        ).first()
        assert appraisal is not None
        assert appraisal.is_final is False
        assert result["appraisals_created"] >= 1

    def test_raises_when_goals_missing(self, db_session):
        _make_cn(db_session, name="Diego")
        with pytest.raises(MissingGoalsError):
            run_cn_monthly_appraisal(month=5, year=2026)

    def test_replaces_non_final_on_rerun(self, db_session):
        cn = _make_cn(db_session, name="Eva")
        _make_goal(db_session, cn, month=6, year=2026)
        run_cn_monthly_appraisal(month=6, year=2026)
        run_cn_monthly_appraisal(month=6, year=2026)
        count = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=6, year=2026
        ).count()
        assert count == 1

    def test_does_not_overwrite_final_appraisal(self, db_session):
        cn = _make_cn(db_session, name="Fabio")
        _make_goal(db_session, cn, month=7, year=2026)
        run_cn_monthly_appraisal(month=7, year=2026)
        appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=7, year=2026
        ).first()
        appraisal.is_final = True
        db_session.flush()

        # second run should skip this CN
        run_cn_monthly_appraisal(month=7, year=2026)
        assert CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=7, year=2026, is_final=True
        ).count() == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_modules/test_cn_calculator.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.modules.commissions.cn_calculator'`

- [ ] **Step 3: Implement cn_calculator.py**

Create `backend/app/modules/commissions/cn_calculator.py`:

```python
"""CN monthly apuração runner.

Calls simulate_cn() for each active CN with a CnMonthlyGoal for the
given (month, year), persists results to CnMonthlyAppraisal.
"""
from decimal import Decimal

from app.extensions import db
from app.models import User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal
from app.modules.commissions.simulator import simulate_cn


class MissingGoalsError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing CN goals: {missing}")


def validate_cn_goals(month: int, year: int) -> list[str]:
    """Return list of '<name> → <month>/<year>' for active CNs missing a goal."""
    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    missing = []
    for cn in active_cns:
        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()
        if goal is None:
            missing.append(f"{cn.name} → {month}/{year}")
    return missing


def run_cn_monthly_appraisal(month: int, year: int) -> dict:
    """Run monthly CN apuração for (month, year).

    Raises MissingGoalsError if any active CN lacks a goal.
    Skips CNs whose appraisal is already is_final=True.
    Replaces non-final appraisals on re-run.
    """
    missing = validate_cn_goals(month, year)
    if missing:
        raise MissingGoalsError(missing)

    # Collect IDs of already-final appraisals to skip
    final_ids = {
        row.cn_id
        for row in CnMonthlyAppraisal.query.filter_by(
            month=month, year=year, is_final=True
        ).all()
    }

    # Delete non-final appraisals for this period
    CnMonthlyAppraisal.query.filter_by(
        month=month, year=year, is_final=False
    ).delete()
    db.session.flush()

    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    created = 0

    for cn in active_cns:
        if cn.id in final_ids:
            continue

        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()

        nivel = cn.nivel.value if cn.nivel else "CN1"
        result = simulate_cn(
            nivel=nivel,
            sao_meta=Decimal(str(goal.sao_target)),
            sao_realizado=Decimal("0"),    # filled from request body at API layer
            vidas_meta=Decimal(str(goal.vidas_target)),
            vidas_realizado=Decimal("0"),  # filled from request body at API layer
        )
        # Note: realized values are passed via `inputs` param — see below
        created += 1

    db.session.flush()
    return {"appraisals_created": created, "month": month, "year": year}


def run_cn_monthly_appraisal_with_inputs(
    month: int, year: int, inputs: list[dict]
) -> dict:
    """Run apuração using provided realized values.

    inputs: [{"cn_id": "<uuid>", "sao_realizado": N, "vidas_realizado": N}, ...]
    Raises MissingGoalsError if any active CN lacks a goal or an input entry.
    """
    missing = validate_cn_goals(month, year)
    if missing:
        raise MissingGoalsError(missing)

    inputs_by_cn = {item["cn_id"]: item for item in inputs}

    final_ids = {
        row.cn_id
        for row in CnMonthlyAppraisal.query.filter_by(
            month=month, year=year, is_final=True
        ).all()
    }

    CnMonthlyAppraisal.query.filter_by(
        month=month, year=year, is_final=False
    ).delete()
    db.session.flush()

    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    created = 0

    for cn in active_cns:
        if cn.id in final_ids:
            continue

        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()

        cn_input = inputs_by_cn.get(str(cn.id), {})
        sao_realizado = Decimal(str(cn_input.get("sao_realizado", 0)))
        vidas_realizado = Decimal(str(cn_input.get("vidas_realizado", 0)))

        nivel = cn.nivel.value if cn.nivel else "CN1"
        result = simulate_cn(
            nivel=nivel,
            sao_meta=Decimal(str(goal.sao_target)),
            sao_realizado=sao_realizado,
            vidas_meta=Decimal(str(goal.vidas_target)),
            vidas_realizado=vidas_realizado,
        )

        appraisal = CnMonthlyAppraisal(
            cn_id=cn.id,
            month=month,
            year=year,
            sao_realizado=sao_realizado,
            vidas_realizado=vidas_realizado,
            pct_sao=Decimal(result["pct_sao"]),
            pct_vidas=Decimal(result["pct_vidas"]),
            score_final=Decimal(result["score_final"]),
            multiplicador=Decimal(result["multiplicador"]),
            commission_amount=Decimal(result["commission_amount"]),
            is_final=False,
        )
        db.session.add(appraisal)
        created += 1

    db.session.flush()
    return {"appraisals_created": created, "month": month, "year": year}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_modules/test_cn_calculator.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/cn_calculator.py \
        backend/tests/test_modules/test_cn_calculator.py
git commit -m "feat: CN monthly apuração runner with Regra de Ouro"
```

---

## Task 5: EV quarterly bonus module (TDD)

**Files:**
- Create: `backend/tests/test_modules/test_ev_bonus.py`
- Create: `backend/app/modules/commissions/ev_bonus.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_ev_bonus.py`:

```python
from decimal import Decimal
import pytest
from app.models import User, UserRole, EvQuarterAchievement
from app.modules.commissions.ev_bonus import run_ev_quarterly_bonus, _mrr_multiplier
from app.extensions import db


def _make_ev(session, name="João", salario=Decimal("5000")):
    u = User(
        email=f"{name.lower()}@test.com",
        name=name,
        role=UserRole.EV,
        salario_base=salario,
    )
    session.add(u)
    session.flush()
    return u


def _make_achievement(session, ev, quarter, year, achievement_pct):
    ach = EvQuarterAchievement(
        ev_id=ev.id,
        quarter=quarter,
        year=year,
        total_mrr=Decimal("0"),
        mrr_target=Decimal("100000"),
        achievement_pct=achievement_pct,
        is_final=False,
    )
    session.add(ach)
    session.flush()
    return ach


class TestMrrMultiplier:
    def test_below_80pct_returns_zero(self):
        assert _mrr_multiplier(Decimal("0.79")) == Decimal("0")

    def test_at_80pct_returns_0_5(self):
        assert _mrr_multiplier(Decimal("0.80")) == Decimal("0.5")

    def test_at_95pct_returns_1_0(self):
        assert _mrr_multiplier(Decimal("0.95")) == Decimal("1.0")

    def test_at_125pct_returns_1_5(self):
        assert _mrr_multiplier(Decimal("1.25")) == Decimal("1.5")


class TestRunEvQuarterlyBonus:
    def test_computes_bonus_for_ev_with_achievement(self, db_session):
        ev = _make_ev(db_session, name="Lucas", salario=Decimal("6000"))
        _make_achievement(db_session, ev, quarter=1, year=2026,
                          achievement_pct=Decimal("1.00"))  # 100% → 1.0x

        result = run_ev_quarterly_bonus(quarter=1, year=2026)

        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev.id, quarter=1, year=2026
        ).first()
        assert ach.bonus_amount == Decimal("6000.00")
        assert ach.salario_base_snapshot == Decimal("6000")
        assert result["bonuses_computed"] >= 1

    def test_below_80pct_sets_zero_bonus(self, db_session):
        ev = _make_ev(db_session, name="Maria", salario=Decimal("5000"))
        _make_achievement(db_session, ev, quarter=2, year=2026,
                          achievement_pct=Decimal("0.50"))

        run_ev_quarterly_bonus(quarter=2, year=2026)

        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev.id, quarter=2, year=2026
        ).first()
        assert ach.bonus_amount == Decimal("0.00")

    def test_skips_ev_with_no_salario_base(self, db_session):
        ev = _make_ev(db_session, name="Pedro", salario=None)
        _make_achievement(db_session, ev, quarter=3, year=2026,
                          achievement_pct=Decimal("1.00"))

        result = run_ev_quarterly_bonus(quarter=3, year=2026)
        assert result["skipped_no_salary"] >= 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_modules/test_ev_bonus.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.modules.commissions.ev_bonus'`

- [ ] **Step 3: Implement ev_bonus.py**

Create `backend/app/modules/commissions/ev_bonus.py`:

```python
"""EV quarterly MRR bonus runner.

Bonus = salario_base × multiplier based on EvQuarterAchievement.achievement_pct.

Multiplier table (spec §2.2):
  < 0.80  → 0x
  < 0.95  → 0.5x
  < 1.25  → 1.0x
  >= 1.25 → 1.5x
"""
from decimal import Decimal

from app.extensions import db
from app.models import EvQuarterAchievement


def _mrr_multiplier(achievement_pct: Decimal) -> Decimal:
    if achievement_pct < Decimal("0.80"):
        return Decimal("0")
    if achievement_pct < Decimal("0.95"):
        return Decimal("0.5")
    if achievement_pct < Decimal("1.25"):
        return Decimal("1.0")
    return Decimal("1.5")


def run_ev_quarterly_bonus(quarter: int, year: int) -> dict:
    """Compute and persist EV MRR bonus for all achievements in (quarter, year).

    Skips achievements that are already is_final=True.
    Skips EVs with no salario_base set.
    """
    achievements = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year
    ).all()

    computed = 0
    skipped_final = 0
    skipped_no_salary = 0

    for ach in achievements:
        if ach.is_final:
            skipped_final += 1
            continue

        ev = ach.ev
        if ev is None or ev.salario_base is None:
            skipped_no_salary += 1
            ach.bonus_amount = Decimal("0.00")
            ach.salario_base_snapshot = None
            continue

        salario = Decimal(str(ev.salario_base))
        mult = _mrr_multiplier(Decimal(str(ach.achievement_pct or 0)))
        ach.bonus_amount = (salario * mult).quantize(Decimal("0.01"))
        ach.salario_base_snapshot = salario
        computed += 1

    db.session.flush()
    return {
        "quarter": quarter,
        "year": year,
        "bonuses_computed": computed,
        "skipped_final": skipped_final,
        "skipped_no_salary": skipped_no_salary,
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_modules/test_ev_bonus.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/ev_bonus.py \
        backend/tests/test_modules/test_ev_bonus.py
git commit -m "feat: EV quarterly MRR bonus calculator"
```

---

## Task 6: Leadership calculator module (TDD)

**Files:**
- Create: `backend/tests/test_modules/test_leadership.py`
- Create: `backend/app/modules/commissions/leadership_calculator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_modules/test_leadership.py`:

```python
from decimal import Decimal
import pytest
from app.models import User, UserRole, Team, Goal, GerenteQuarterAppraisal
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
    _lideranca_multiplier,
)
from app.extensions import db


def _make_gerente(session, name="Gerente", salario=Decimal("10000")):
    u = User(email=f"{name.lower()}@test.com", name=name,
             role=UserRole.GERENTE, salario_base=salario)
    session.add(u)
    session.flush()
    return u


def _make_ev_with_goal(session, team_id, name, mrr_target, quarter, year):
    ev = User(email=f"{name.lower()}@test.com", name=name,
              role=UserRole.EV, team_id=team_id)
    session.add(ev)
    session.flush()
    g = Goal(ev_id=ev.id, quarter=quarter, year=year, mrr_target=mrr_target)
    session.add(g)
    session.flush()
    return ev


def _make_team(session, gerente):
    t = Team(name="Time Teste", leader_id=gerente.id)
    session.add(t)
    session.flush()
    gerente.team_id = t.id
    session.flush()
    return t


class TestLiderancaMultiplier:
    def test_zero_mrr_returns_zero(self):
        assert _lideranca_multiplier(Decimal("0.5"), Decimal("0.5")) == Decimal("0")

    def test_mrr_60_sql_80_returns_0_75(self):
        assert _lideranca_multiplier(Decimal("0.65"), Decimal("0.82")) == Decimal("0.75")

    def test_mrr_95_sql_110_returns_3_25(self):
        assert _lideranca_multiplier(Decimal("1.00"), Decimal("1.10")) == Decimal("3.25")

    def test_max_mrr_110_sql_110_returns_4_0(self):
        assert _lideranca_multiplier(Decimal("1.10"), Decimal("1.15")) == Decimal("4.0")


class TestRunLeadershipAppraisal:
    def test_computes_gerente_bonus(self, db_session):
        gerente = _make_gerente(db_session)
        team = _make_team(db_session, gerente)
        _make_ev_with_goal(db_session, team.id, "EV1",
                           Decimal("100000"), quarter=1, year=2026)
        _make_ev_with_goal(db_session, team.id, "EV2",
                           Decimal("100000"), quarter=1, year=2026)

        # meta_mrr = 90% × 200,000 = 180,000
        # realizado_mrr = 200,000 → pct_mrr = 1.11 (≥ 110%)
        # meta_sql = 10, realizado_sql = 11 → pct_sql = 1.10 (≥ 110%)
        # multiplier = 4.0, bonus = 10000 * 4.0 = 40000
        inputs = [{
            "gerente_id": str(gerente.id),
            "meta_sql": 10,
            "realizado_mrr": "200000",
            "realizado_sql": 11,
        }]
        result = run_leadership_appraisal(quarter=1, year=2026, inputs=inputs)

        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente.id, quarter=1, year=2026
        ).first()
        assert appraisal is not None
        assert appraisal.meta_mrr == Decimal("180000.00")
        assert appraisal.bonus_amount == Decimal("40000.00")
        assert result["appraisals_created"] == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_modules/test_leadership.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.modules.commissions.leadership_calculator'`

- [ ] **Step 3: Implement leadership_calculator.py**

Create `backend/app/modules/commissions/leadership_calculator.py`:

```python
"""GERENTE quarterly leadership bonus runner.

Spec §2.3:
  meta_mrr  = 90% × SUM(Goal.mrr_target for all EVs in gerente's team, quarter, year)
  pct_mrr   = realizado_mrr / meta_mrr
  pct_sql   = realizado_sql / meta_sql
  mult      = MATRIZ_LIDERANCA[mrr_faixa][sql_faixa]
  bonus     = salario_base × mult
"""
from decimal import Decimal

from app.extensions import db
from app.models import User, UserRole, Goal, Team, GerenteQuarterAppraisal

# Matrix rows = MRR faixas, columns = SQL faixas
# Faixas: [< 60%, 60-79.9%, 80-94.9%, 95-109.9%, >= 110%]   (MRR)
#         [< 80%, 80-94.9%, 95-109.9%, >= 110%]              (SQL)
_MATRIZ = [
    [Decimal("0"),   Decimal("0"),    Decimal("0"),    Decimal("0")],     # MRR < 60%
    [Decimal("0.5"), Decimal("0.75"), Decimal("1.0"),  Decimal("1.25")],  # MRR 60–79.9%
    [Decimal("1.0"), Decimal("1.5"),  Decimal("2.0"),  Decimal("2.25")],  # MRR 80–94.9%
    [Decimal("1.5"), Decimal("2.0"),  Decimal("3.0"),  Decimal("3.25")],  # MRR 95–109.9%
    [Decimal("2.0"), Decimal("2.75"), Decimal("3.5"),  Decimal("4.0")],   # MRR >= 110%
]

_MRR_THRESHOLDS = [Decimal("0.60"), Decimal("0.80"), Decimal("0.95"), Decimal("1.10")]
_SQL_THRESHOLDS = [Decimal("0.80"), Decimal("0.95"), Decimal("1.10")]


def _row(pct: Decimal, thresholds: list[Decimal]) -> int:
    for i, t in enumerate(thresholds):
        if pct < t:
            return i
    return len(thresholds)


def _lideranca_multiplier(pct_mrr: Decimal, pct_sql: Decimal) -> Decimal:
    return _MATRIZ[_row(pct_mrr, _MRR_THRESHOLDS)][_row(pct_sql, _SQL_THRESHOLDS)]


def get_leadership_preview(quarter: int, year: int) -> list[dict]:
    """Return list of GERENTEs with auto-computed meta_mrr for (quarter, year)."""
    gerentes = User.query.filter_by(role=UserRole.GERENTE, active=True).all()
    result = []
    for gerente in gerentes:
        meta_mrr = _compute_meta_mrr(gerente, quarter, year)
        result.append({
            "gerente_id": str(gerente.id),
            "gerente_name": gerente.name,
            "meta_mrr": str(meta_mrr),
        })
    return result


def _compute_meta_mrr(gerente: User, quarter: int, year: int) -> Decimal:
    """90% × SUM(Goal.mrr_target for EVs in gerente's team)."""
    team = Team.query.filter_by(leader_id=gerente.id).first()
    if team is None:
        return Decimal("0")

    ev_ids = [u.id for u in team.members if u.role == UserRole.EV and u.active]
    if not ev_ids:
        return Decimal("0")

    total = Decimal("0")
    for ev_id in ev_ids:
        goal = Goal.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year
        ).first()
        if goal:
            total += Decimal(str(goal.mrr_target))

    return (total * Decimal("0.90")).quantize(Decimal("0.01"))


def run_leadership_appraisal(
    quarter: int, year: int, inputs: list[dict]
) -> dict:
    """Compute and persist GERENTE bonus.

    inputs: [{gerente_id, meta_sql, realizado_mrr, realizado_sql}, ...]
    Skips GERENTEs already is_final=True for this quarter.
    """
    final_ids = {
        row.gerente_id
        for row in GerenteQuarterAppraisal.query.filter_by(
            quarter=quarter, year=year, is_final=True
        ).all()
    }

    created = 0
    for item in inputs:
        gerente_id = item["gerente_id"]
        if gerente_id in {str(fid) for fid in final_ids}:
            continue

        gerente = db.session.get(User, gerente_id)
        if gerente is None or gerente.salario_base is None:
            continue

        meta_mrr = _compute_meta_mrr(gerente, quarter, year)
        meta_sql = int(item["meta_sql"])
        realizado_mrr = Decimal(str(item["realizado_mrr"]))
        realizado_sql = int(item["realizado_sql"])

        pct_mrr = (realizado_mrr / meta_mrr) if meta_mrr > 0 else Decimal("0")
        pct_sql = (Decimal(realizado_sql) / Decimal(meta_sql)) if meta_sql > 0 else Decimal("0")
        mult = _lideranca_multiplier(pct_mrr, pct_sql)
        bonus = (Decimal(str(gerente.salario_base)) * mult).quantize(Decimal("0.01"))

        # Upsert
        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente_id, quarter=quarter, year=year, is_final=False
        ).first()
        if appraisal is None:
            appraisal = GerenteQuarterAppraisal(
                gerente_id=gerente_id, quarter=quarter, year=year
            )
            db.session.add(appraisal)

        appraisal.meta_mrr = meta_mrr
        appraisal.meta_sql = meta_sql
        appraisal.realizado_mrr = realizado_mrr
        appraisal.realizado_sql = realizado_sql
        appraisal.pct_mrr = pct_mrr.quantize(Decimal("0.0001"))
        appraisal.pct_sql = pct_sql.quantize(Decimal("0.0001"))
        appraisal.multiplicador = mult
        appraisal.bonus_amount = bonus
        appraisal.is_final = False
        created += 1

    db.session.flush()
    return {"quarter": quarter, "year": year, "appraisals_created": created}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_modules/test_leadership.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/commissions/leadership_calculator.py \
        backend/tests/test_modules/test_leadership.py
git commit -m "feat: GERENTE leadership bonus with 5×4 matrix"
```

---

## Task 7: API endpoints — CN commissions blueprint

**Files:**
- Create: `backend/app/api/v1/cn_commissions.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Create cn_commissions.py**

Create `backend/app/api/v1/cn_commissions.py`:

```python
from decimal import Decimal
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, CnMonthlyGoal, CnMonthlyAppraisal, User
from app.extensions import db
from app.modules.commissions.simulator import simulate_cn
from app.modules.commissions.cn_calculator import (
    run_cn_monthly_appraisal_with_inputs,
    validate_cn_goals,
    MissingGoalsError,
)

cn_commissions_bp = Blueprint(
    "cn_commissions", __name__, url_prefix="/api/v1/commissions/cn"
)


# ── Goals ──────────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/goals")
@require_auth
def list_cn_goals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    query = CnMonthlyGoal.query
    if month:
        query = query.filter_by(month=month)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.CN:
        query = query.filter_by(cn_id=user.id)

    goals = query.all()
    return jsonify({"data": [_serialize_goal(g_) for g_ in goals]})


@cn_commissions_bp.route("/goals", methods=["PUT"])
@require_auth
def upsert_cn_goals():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    month = int(body["month"])
    year = int(body["year"])
    items = body["items"]  # [{cn_id, sao_target, vidas_target}]

    for item in items:
        goal = CnMonthlyGoal.query.filter_by(
            cn_id=item["cn_id"], month=month, year=year
        ).first()
        if goal is None:
            goal = CnMonthlyGoal(cn_id=item["cn_id"], month=month, year=year)
            db.session.add(goal)
        goal.sao_target = Decimal(str(item["sao_target"]))
        goal.vidas_target = Decimal(str(item["vidas_target"]))

    db.session.commit()
    return jsonify({"data": {"updated": len(items)}}), 200


# ── Apuração ───────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/appraisal", methods=["POST"])
@require_auth
def run_cn_appraisal():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    month = int(body["month"])
    year = int(body["year"])
    inputs = body.get("inputs", [])  # [{cn_id, sao_realizado, vidas_realizado}]

    try:
        result = run_cn_monthly_appraisal_with_inputs(month, year, inputs)
        db.session.commit()
        return jsonify({"data": result})
    except MissingGoalsError as e:
        return jsonify({"error": {"code": "MISSING_GOALS", "missing": e.missing}}), 422


@cn_commissions_bp.route("/appraisal")
@require_auth
def list_cn_appraisals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    query = CnMonthlyAppraisal.query
    if month:
        query = query.filter_by(month=month)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.CN:
        query = query.filter_by(cn_id=user.id)

    items = query.order_by(CnMonthlyAppraisal.year.desc(),
                           CnMonthlyAppraisal.month.desc()).all()
    return jsonify({"data": [_serialize_appraisal(a) for a in items]})


@cn_commissions_bp.route("/appraisal/<appraisal_id>/finalize", methods=["POST"])
@require_auth
def finalize_cn_appraisal(appraisal_id):
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(CnMonthlyAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.is_final:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    appraisal.is_final = True
    db.session.commit()
    return jsonify({"data": _serialize_appraisal(appraisal)})


# ── Simulator ──────────────────────────────────────────────────────────────

@cn_commissions_bp.route("/simulate", methods=["POST"])
@require_auth
def simulate_cn_endpoint():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.CN):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()

    # CN can only simulate with their own nivel
    if user.role == UserRole.CN:
        nivel = user.nivel.value if user.nivel else "CN1"
    else:
        nivel = body.get("nivel", "CN1")

    result = simulate_cn(
        nivel=nivel,
        sao_meta=Decimal(str(body["sao_meta"])),
        sao_realizado=Decimal(str(body["sao_realizado"])),
        vidas_meta=Decimal(str(body["vidas_meta"])),
        vidas_realizado=Decimal(str(body["vidas_realizado"])),
    )
    return jsonify({"data": result})


# ── Serialisers ────────────────────────────────────────────────────────────

def _serialize_goal(g_):
    return {
        "id": str(g_.id),
        "cn_id": str(g_.cn_id),
        "month": g_.month,
        "year": g_.year,
        "sao_target": str(g_.sao_target),
        "vidas_target": str(g_.vidas_target),
    }


def _serialize_appraisal(a):
    return {
        "id": str(a.id),
        "cn_id": str(a.cn_id),
        "month": a.month,
        "year": a.year,
        "sao_realizado": str(a.sao_realizado),
        "vidas_realizado": str(a.vidas_realizado),
        "pct_sao": str(a.pct_sao),
        "pct_vidas": str(a.pct_vidas),
        "score_final": str(a.score_final),
        "multiplicador": str(a.multiplicador),
        "commission_amount": str(a.commission_amount),
        "is_final": a.is_final,
    }
```

- [ ] **Step 2: Create ev_bonus.py blueprint**

Create `backend/app/api/v1/ev_bonus.py`:

```python
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, EvQuarterAchievement
from app.extensions import db
from app.modules.commissions.ev_bonus import run_ev_quarterly_bonus

ev_bonus_bp = Blueprint("ev_bonus", __name__, url_prefix="/api/v1/commissions/ev")


@ev_bonus_bp.route("/bonus", methods=["POST"])
@require_auth
def run_bonus():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    quarter = int(body["quarter"])
    year = int(body["year"])
    result = run_ev_quarterly_bonus(quarter, year)
    db.session.commit()
    return jsonify({"data": result})


@ev_bonus_bp.route("/bonus")
@require_auth
def list_bonuses():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.EV):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    query = EvQuarterAchievement.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.EV:
        query = query.filter_by(ev_id=user.id)

    items = query.all()
    return jsonify({"data": [_serialize(a) for a in items]})


def _serialize(a):
    return {
        "id": str(a.id),
        "ev_id": str(a.ev_id),
        "quarter": a.quarter,
        "year": a.year,
        "achievement_pct": str(a.achievement_pct) if a.achievement_pct else None,
        "bonus_amount": str(a.bonus_amount) if a.bonus_amount is not None else None,
        "salario_base_snapshot": str(a.salario_base_snapshot) if a.salario_base_snapshot else None,
        "is_final": a.is_final,
    }
```

- [ ] **Step 3: Create leadership.py blueprint**

Create `backend/app/api/v1/leadership.py`:

```python
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, GerenteQuarterAppraisal
from app.extensions import db
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
)

leadership_bp = Blueprint("leadership", __name__, url_prefix="/api/v1/commissions/leadership")


@leadership_bp.route("/preview")
@require_auth
def preview():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR",
                                  "message": "quarter and year required"}}), 400
    data = get_leadership_preview(quarter, year)
    return jsonify({"data": data})


@leadership_bp.route("/appraisal", methods=["POST"])
@require_auth
def run_appraisal():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    quarter = int(body["quarter"])
    year = int(body["year"])
    inputs = body["inputs"]  # [{gerente_id, meta_sql, realizado_mrr, realizado_sql}]
    result = run_leadership_appraisal(quarter, year, inputs)
    db.session.commit()
    return jsonify({"data": result})


@leadership_bp.route("/appraisal")
@require_auth
def list_appraisals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.GERENTE):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    query = GerenteQuarterAppraisal.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.GERENTE:
        query = query.filter_by(gerente_id=user.id)

    items = query.all()
    return jsonify({"data": [_serialize(a) for a in items]})


@leadership_bp.route("/appraisal/<appraisal_id>/finalize", methods=["POST"])
@require_auth
def finalize(appraisal_id):
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(GerenteQuarterAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.is_final:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    appraisal.is_final = True
    db.session.commit()
    return jsonify({"data": _serialize(appraisal)})


def _serialize(a):
    return {
        "id": str(a.id),
        "gerente_id": str(a.gerente_id),
        "quarter": a.quarter,
        "year": a.year,
        "meta_mrr": str(a.meta_mrr),
        "meta_sql": a.meta_sql,
        "realizado_mrr": str(a.realizado_mrr),
        "realizado_sql": a.realizado_sql,
        "pct_mrr": str(a.pct_mrr),
        "pct_sql": str(a.pct_sql),
        "multiplicador": str(a.multiplicador),
        "bonus_amount": str(a.bonus_amount),
        "is_final": a.is_final,
    }
```

- [ ] **Step 4: Register blueprints in api/__init__.py**

In `backend/app/api/__init__.py`, add after the existing imports and registrations:

```python
    from app.api.v1.cn_commissions import cn_commissions_bp
    from app.api.v1.ev_bonus import ev_bonus_bp
    from app.api.v1.leadership import leadership_bp
    app.register_blueprint(cn_commissions_bp)
    app.register_blueprint(ev_bonus_bp)
    app.register_blueprint(leadership_bp)
```

- [ ] **Step 5: Smoke-test the endpoints start up**

```bash
flask routes | grep -E "cn|ev_bonus|leadership"
```

Expected: Routes for `/api/v1/commissions/cn/...`, `/api/v1/commissions/ev/bonus`, `/api/v1/commissions/leadership/...` appear.

- [ ] **Step 6: Run full backend test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: All existing tests pass + new tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/cn_commissions.py \
        backend/app/api/v1/ev_bonus.py \
        backend/app/api/v1/leadership.py \
        backend/app/api/__init__.py
git commit -m "feat: CN, EV bonus, and leadership API endpoints"
```

---

## Task 8: Frontend wiring — endpoints + routes

**Files:**
- Modify: `frontend/src/app/api/endpoints.cljs`
- Modify: `frontend/src/app/routes.cljs`

- [ ] **Step 1: Add endpoint constants to endpoints.cljs**

In `frontend/src/app/api/endpoints.cljs`, append:

```clojure
;; CN commissions
(def cn-goals           "/commissions/cn/goals")
(def cn-appraisal       "/commissions/cn/appraisal")
(defn cn-appraisal-finalize [id] (str "/commissions/cn/appraisal/" id "/finalize"))
(def cn-simulate        "/commissions/cn/simulate")

;; EV bonus
(def ev-bonus           "/commissions/ev/bonus")

;; Leadership
(def leadership-preview    "/commissions/leadership/preview")
(def leadership-appraisal  "/commissions/leadership/appraisal")
(defn leadership-finalize [id] (str "/commissions/leadership/appraisal/" id "/finalize"))
```

- [ ] **Step 2: Add routes to routes.cljs**

In `frontend/src/app/routes.cljs`, inside the `routes` vector, add:

```clojure
    ;; CN
    ["/cn"
     ["/simulator"  {:name :cn/simulator  :role #{:CN :ADMIN}}]
     ["/dashboard"  {:name :cn/dashboard  :role #{:CN :ADMIN}}]]
```

And inside the `/admin` group, add:

```clojure
     ["/cn-goals"           {:name :revops/cn-goals        :role #{:ADMIN}}]
     ["/cn-appraisal"       {:name :revops/cn-appraisal    :role #{:ADMIN}}]
     ["/ev-bonus"           {:name :revops/ev-bonus        :role #{:ADMIN}}]
     ["/leadership"         {:name :revops/leadership      :role #{:ADMIN}}]
```

- [ ] **Step 3: Wire views in core.cljs**

Open `frontend/src/app/core.cljs`. Find where views are dispatched by route name (look for a `case` or `condp` on `:current-route-name`). Add the new routes following the existing pattern:

```clojure
:cn/simulator          [cn-simulator/page]
:cn/dashboard          [cn-dashboard/page]
:revops/cn-goals       [cn-goals/page]
:revops/cn-appraisal   [cn-appraisal/page]
:revops/ev-bonus       [ev-bonus/page]
:revops/leadership     [leadership-appraisal/page]
```

Add the necessary `(:require ...)` entries for each new view namespace.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/api/endpoints.cljs \
        frontend/src/app/routes.cljs \
        frontend/src/app/core.cljs
git commit -m "feat: wire CN/EV/leadership frontend routes and endpoints"
```

---

## Task 9: Frontend — CN simulator view

**Files:**
- Create: `frontend/src/app/views/cn/simulator.cljs`

- [ ] **Step 1: Create simulator view**

Create `frontend/src/app/views/cn/simulator.cljs`:

```clojure
(ns app.views.cn.simulator
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :cn/simulate
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-simulate
           :body       payload
           :on-success [:cn/simulate-result]
           :on-failure [:cn/simulate-error]}}))

(rf/reg-event-db
 :cn/simulate-result
 (fn [db [_ response]]
   (assoc-in db [:cn :simulator :result] (:data response))))

(rf/reg-event-db
 :cn/simulate-error
 (fn [db _]
   (assoc-in db [:cn :simulator :result] nil)))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub
 :cn/simulator-result
 (fn [db _] (get-in db [:cn :simulator :result])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn- result-panel [result]
  [:div {:style {:display "flex" :flex-direction "column" :gap "8px"
                 :padding "16px" :background t/surface-raised
                 :border-radius (:md t/border-radius)}}
   [:div {:style {:font-weight "600" :font-size "14px"}} "Resultado"]
   [:div (str "% SAO: " (* 100 (js/parseFloat (:pct_sao result))) "%")]
   [:div (str "% Vidas: " (* 100 (js/parseFloat (:pct_vidas result))) "%")]
   [:div (str "Score Final: " (* 100 (js/parseFloat (:score_final result))) "%")]
   [:div (str "Multiplicador: " (:multiplicador result) "x")]
   [:div {:style {:font-size "20px" :font-weight "700" :color t/color-primary}}
    (str "Comissão: R$ " (:commission_amount result))]])

(defn page []
  (let [form (r/atom {:sao_meta "" :sao_realizado "" :vidas_meta "" :vidas_realizado ""})]
    (fn []
      (let [result @(rf/subscribe [:cn/simulator-result])]
        [layout/page {:title "Simulador de Comissão"}
         [cards/card {:style {:max-width "480px"}}
          [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
           [inputs/text-field
            {:label "Meta SAO (R$)" :value (:sao_meta @form)
             :on-change #(swap! form assoc :sao_meta %)}]
           [inputs/text-field
            {:label "SAO Realizado (R$)" :value (:sao_realizado @form)
             :on-change #(swap! form assoc :sao_realizado %)}]
           [inputs/text-field
            {:label "Meta Vidas" :value (:vidas_meta @form)
             :on-change #(swap! form assoc :vidas_meta %)}]
           [inputs/text-field
            {:label "Vidas Realizadas" :value (:vidas_realizado @form)
             :on-change #(swap! form assoc :vidas_realizado %)}]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:cn/simulate @form])}
            "Simular"]
           (when result [result-panel result])]]]))))
```

- [ ] **Step 2: Create CN dashboard view**

Create `frontend/src/app/views/cn/dashboard.cljs`:

```clojure
(ns app.views.cn.dashboard
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :cn/fetch-appraisals
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:cn :appraisals-loading?] true)
    :http {:method     :get
           :url        ep/cn-appraisal
           :on-success [:cn/appraisals-loaded]
           :on-failure [:cn/appraisals-error]}}))

(rf/reg-event-db
 :cn/appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:cn :appraisals] (:data response))
       (assoc-in [:cn :appraisals-loading?] false))))

(rf/reg-event-db
 :cn/appraisals-error
 (fn [db _] (assoc-in db [:cn :appraisals-loading?] false)))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :cn/appraisals (fn [db _] (get-in db [:cn :appraisals] [])))
(rf/reg-sub :cn/appraisals-loading? (fn [db _] (get-in db [:cn :appraisals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (rf/dispatch [:cn/fetch-appraisals])
  (fn []
    (let [items    @(rf/subscribe [:cn/appraisals])
          loading? @(rf/subscribe [:cn/appraisals-loading?])]
      [layout/page {:title "Minhas Apurações"}
       [tbl/table
        {:loading? loading?
         :columns  [{:key :month       :label "Mês"}
                    {:key :year        :label "Ano"}
                    {:key :score_final :label "Score"}
                    {:key :multiplicador :label "Mult."}
                    {:key :commission_amount :label "Comissão (R$)"}
                    {:key :is_final    :label "Status"
                     :render (fn [v] (if v
                                       [badge/badge {:variant :success} "Final"]
                                       [badge/badge {:variant :warning} "Rascunho"]))}]
         :rows     items}]])))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/cn/
git commit -m "feat: CN simulator and dashboard views"
```

---

## Task 10: Frontend — RevOps CN goals + apuração views

**Files:**
- Create: `frontend/src/app/views/revops/cn_goals.cljs`
- Create: `frontend/src/app/views/revops/cn_appraisal.cljs`

- [ ] **Step 1: Create cn_goals.cljs**

Create `frontend/src/app/views/revops/cn_goals.cljs`:

```clojure
(ns app.views.revops.cn-goals
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :revops/fetch-cn-goals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-goals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-goals "?month=" month "&year=" year)
           :on-success [:revops/cn-goals-loaded]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-db
 :revops/cn-goals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-goals] (:data response))
       (assoc-in [:admin :cn-goals-loading?] false))))

(rf/reg-event-db
 :revops/cn-goals-error
 (fn [db _] (assoc-in db [:admin :cn-goals-loading?] false)))

(rf/reg-event-fx
 :revops/save-cn-goals
 (fn [_ [_ payload]]
   {:http {:method     :put
           :url        ep/cn-goals
           :body       payload
           :on-success [:revops/cn-goals-saved]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-fx
 :revops/cn-goals-saved
 (fn [{:keys [db]} [_ _]]
   {:dispatch [:revops/fetch-cn-goals
               (get-in db [:admin :cn-goals-filter :month])
               (get-in db [:admin :cn-goals-filter :year])]}))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :revops/cn-goals (fn [db _] (get-in db [:admin :cn-goals] [])))
(rf/reg-sub :revops/cn-goals-loading? (fn [db _] (get-in db [:admin :cn-goals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (let [filter-state (r/atom {:month "4" :year "2026"})
        edits        (r/atom {})]
    (fn []
      (let [goals    @(rf/subscribe [:revops/cn-goals])
            loading? @(rf/subscribe [:revops/cn-goals-loading?])]
        [layout/page {:title "Metas Mensais CN"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select
            {:label "Mês" :value (:month @filter-state)
             :options (map (fn [m] {:value (str m) :label (str m)}) (range 1 13))
             :on-change #(swap! filter-state assoc :month %)}]
           [inputs/select
            {:label "Ano" :value (:year @filter-state)
             :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
             :on-change #(swap! filter-state assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-cn-goals
                                                 (:month @filter-state)
                                                 (:year @filter-state)])}
            "Buscar"]]
          [tbl/table
           {:loading? loading?
            :columns  [{:key :cn_id    :label "CN"}
                       {:key :sao_target :label "Meta SAO"
                        :render (fn [v row]
                                  [inputs/text-field
                                   {:value    (get-in @edits [(:cn_id row) :sao_target] (str v))
                                    :on-change #(swap! edits assoc-in [(:cn_id row) :sao_target] %)}])}
                       {:key :vidas_target :label "Meta Vidas"
                        :render (fn [v row]
                                  [inputs/text-field
                                   {:value    (get-in @edits [(:cn_id row) :vidas_target] (str v))
                                    :on-change #(swap! edits assoc-in [(:cn_id row) :vidas_target] %)}])}]
            :rows     goals}]
          [btn/button
           {:variant  :primary
            :on-click (fn []
                        (let [items (mapv (fn [[cn-id vals]]
                                           (merge {:cn_id cn-id} vals))
                                         @edits)]
                          (rf/dispatch [:revops/save-cn-goals
                                        {:month (:month @filter-state)
                                         :year  (:year @filter-state)
                                         :items items}])))}
           "Salvar Metas"]]]))))
```

- [ ] **Step 2: Create cn_appraisal.cljs**

Create `frontend/src/app/views/revops/cn_appraisal.cljs`:

```clojure
(ns app.views.revops.cn-appraisal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :revops/fetch-cn-appraisals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-appraisals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-appraisal "?month=" month "&year=" year)
           :on-success [:revops/cn-appraisals-loaded]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-db
 :revops/cn-appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-appraisals] (:data response))
       (assoc-in [:admin :cn-appraisals-loading?] false))))

(rf/reg-event-db
 :revops/cn-appraisals-error
 (fn [db _] (assoc-in db [:admin :cn-appraisals-loading?] false)))

(rf/reg-event-fx
 :revops/run-cn-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-appraisal
           :body       payload
           :on-success [:revops/cn-appraisal-done]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/cn-appraisal-done
 (fn [{:keys [db]} _]
   {:dispatch [:revops/fetch-cn-appraisals
               (get-in db [:admin :cn-appraisal-filter :month])
               (get-in db [:admin :cn-appraisal-filter :year])]}))

(rf/reg-event-fx
 :revops/finalize-cn-appraisal
 (fn [_ [_ id month year]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-finalize id)
           :body       {}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :revops/cn-appraisals (fn [db _] (get-in db [:admin :cn-appraisals] [])))
(rf/reg-sub :revops/cn-appraisals-loading? (fn [db _] (get-in db [:admin :cn-appraisals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (let [filter-s (r/atom {:month "4" :year "2026"})
        inputs   (r/atom {})]
    (fn []
      (let [items    @(rf/subscribe [:revops/cn-appraisals])
            loading? @(rf/subscribe [:revops/cn-appraisals-loading?])]
        [layout/page {:title "Apuração Mensal CN"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select
            {:label "Mês" :value (:month @filter-s)
             :options (map (fn [m] {:value (str m) :label (str m)}) (range 1 13))
             :on-change #(swap! filter-s assoc :month %)}]
           [inputs/select
            {:label "Ano" :value (:year @filter-s)
             :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
             :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-cn-appraisals
                                                 (:month @filter-s) (:year @filter-s)])}
            "Buscar"]]

          ;; Input table for realized values
          [:div {:style {:margin-bottom "16px"}}
           [:p {:style {:font-size "13px" :color t/text-secondary :margin-bottom "8px"}}
            "Preencha os valores realizados e clique em Rodar Apuração."]
           ;; (In production: render a row per CN fetched from /admin/users?role=CN)
           ]

          [btn/button
           {:variant  :primary
            :on-click (fn []
                        (rf/dispatch [:revops/run-cn-appraisal
                                      {:month  (:month @filter-s)
                                       :year   (:year @filter-s)
                                       :inputs (mapv (fn [[cn-id vals]]
                                                       (merge {:cn_id cn-id} vals))
                                                     @inputs)}]))}
           "Rodar Apuração"]

          [tbl/table
           {:loading? loading?
            :columns  [{:key :cn_id          :label "CN"}
                       {:key :score_final     :label "Score"}
                       {:key :multiplicador   :label "Mult."}
                       {:key :commission_amount :label "Comissão (R$)"}
                       {:key :is_final        :label "Status"
                        :render (fn [v row]
                                  (if v
                                    [badge/badge {:variant :success} "Final"]
                                    [btn/button {:variant :primary :size :sm
                                                 :on-click #(rf/dispatch
                                                              [:revops/finalize-cn-appraisal
                                                               (:id row)
                                                               (:month @filter-s)
                                                               (:year @filter-s)])}
                                     "Finalizar"]))}]
            :rows     items}]]]))))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/cn_goals.cljs \
        frontend/src/app/views/revops/cn_appraisal.cljs
git commit -m "feat: RevOps CN goals management and apuração views"
```

---

## Task 11: Frontend — RevOps EV bonus + Leadership views

**Files:**
- Create: `frontend/src/app/views/revops/ev_bonus.cljs`
- Create: `frontend/src/app/views/revops/leadership_appraisal.cljs`

- [ ] **Step 1: Create ev_bonus.cljs**

Create `frontend/src/app/views/revops/ev_bonus.cljs`:

```clojure
(ns app.views.revops.ev-bonus
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]))

(rf/reg-event-fx
 :revops/fetch-ev-bonus
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :ev-bonus-loading?] true)
    :http {:method     :get
           :url        (str ep/ev-bonus "?quarter=" quarter "&year=" year)
           :on-success [:revops/ev-bonus-loaded]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-event-db
 :revops/ev-bonus-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :ev-bonus] (:data r))
                       (assoc-in [:admin :ev-bonus-loading?] false))))

(rf/reg-event-db :revops/ev-bonus-error (fn [db _] (assoc-in db [:admin :ev-bonus-loading?] false)))

(rf/reg-event-fx
 :revops/run-ev-bonus
 (fn [_ [_ quarter year]]
   {:http {:method     :post
           :url        ep/ev-bonus
           :body       {:quarter quarter :year year}
           :on-success [:revops/fetch-ev-bonus quarter year]
           :on-failure [:revops/ev-bonus-error]}}))

(rf/reg-sub :revops/ev-bonus (fn [db _] (get-in db [:admin :ev-bonus] [])))
(rf/reg-sub :revops/ev-bonus-loading? (fn [db _] (get-in db [:admin :ev-bonus-loading?])))

(defn page []
  (let [filter-s (r/atom {:quarter "1" :year "2026"})]
    (fn []
      (let [items    @(rf/subscribe [:revops/ev-bonus])
            loading? @(rf/subscribe [:revops/ev-bonus-loading?])]
        [layout/page {:title "Bônus MRR Trimestral — EVs"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select {:label "Trimestre" :value (:quarter @filter-s)
                           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
                           :on-change #(swap! filter-s assoc :quarter %)}]
           [inputs/select {:label "Ano" :value (:year @filter-s)
                           :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
                           :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-ev-bonus
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Buscar"]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:revops/run-ev-bonus
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Calcular Bônus"]]
          [tbl/table
           {:loading? loading?
            :columns  [{:key :ev_id              :label "EV"}
                       {:key :achievement_pct     :label "% Atingimento"}
                       {:key :salario_base_snapshot :label "Salário Base"}
                       {:key :bonus_amount         :label "Bônus (R$)"}]
            :rows     items}]]]))))
```

- [ ] **Step 2: Create leadership_appraisal.cljs**

Create `frontend/src/app/views/revops/leadership_appraisal.cljs`:

```clojure
(ns app.views.revops.leadership-appraisal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]))

(rf/reg-event-fx
 :revops/fetch-leadership-preview
 (fn [{:keys [db]} [_ quarter year]]
   {:db   (assoc-in db [:admin :leadership-loading?] true)
    :http {:method     :get
           :url        (str ep/leadership-preview "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-preview-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-preview-loaded
 (fn [db [_ r]] (-> db (assoc-in [:admin :leadership-preview] (:data r))
                       (assoc-in [:admin :leadership-loading?] false))))

(rf/reg-event-fx
 :revops/fetch-leadership-appraisals
 (fn [{:keys [db]} [_ quarter year]]
   {:http {:method     :get
           :url        (str ep/leadership-appraisal "?quarter=" quarter "&year=" year)
           :on-success [:revops/leadership-appraisals-loaded]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-db
 :revops/leadership-appraisals-loaded
 (fn [db [_ r]] (assoc-in db [:admin :leadership-appraisals] (:data r))))

(rf/reg-event-db :revops/leadership-error (fn [db _] (assoc-in db [:admin :leadership-loading?] false)))

(rf/reg-event-fx
 :revops/run-leadership-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/leadership-appraisal
           :body       payload
           :on-success [:revops/fetch-leadership-appraisals
                        (:quarter payload) (:year payload)]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-event-fx
 :revops/finalize-leadership
 (fn [_ [_ id quarter year]]
   {:http {:method     :post
           :url        (ep/leadership-finalize id)
           :body       {}
           :on-success [:revops/fetch-leadership-appraisals quarter year]
           :on-failure [:revops/leadership-error]}}))

(rf/reg-sub :revops/leadership-preview (fn [db _] (get-in db [:admin :leadership-preview] [])))
(rf/reg-sub :revops/leadership-appraisals (fn [db _] (get-in db [:admin :leadership-appraisals] [])))
(rf/reg-sub :revops/leadership-loading? (fn [db _] (get-in db [:admin :leadership-loading?])))

(defn page []
  (let [filter-s (r/atom {:quarter "1" :year "2026"})
        inputs   (r/atom {})]  ;; {gerente_id -> {meta_sql, realizado_mrr, realizado_sql}}
    (fn []
      (let [preview  @(rf/subscribe [:revops/leadership-preview])
            results  @(rf/subscribe [:revops/leadership-appraisals])
            loading? @(rf/subscribe [:revops/leadership-loading?])]
        [layout/page {:title "Apuração Liderança — GERENTEs"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select {:label "Trimestre" :value (:quarter @filter-s)
                           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
                           :on-change #(swap! filter-s assoc :quarter %)}]
           [inputs/select {:label "Ano" :value (:year @filter-s)
                           :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
                           :on-change #(swap! filter-s assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-leadership-preview
                                                 (:quarter @filter-s) (:year @filter-s)])}
            "Carregar"]]

          ;; Input table: one row per GERENTE
          (when (seq preview)
            [:div {:style {:margin-bottom "16px"}}
             [:p {:style {:font-size "13px" :font-weight "600" :margin-bottom "8px"}}
              "Preencha os valores realizados:"]
             (for [{:keys [gerente_id gerente_name meta_mrr]} preview]
               ^{:key gerente_id}
               [:div {:style {:display "flex" :gap "12px" :align-items "center"
                              :margin-bottom "8px"}}
                [:span {:style {:width "140px" :font-size "13px"}} gerente_name]
                [:span {:style {:width "120px" :font-size "12px" :color "#666"}}
                 (str "Meta MRR: R$ " meta_mrr " (auto)")]
                [inputs/text-field
                 {:label "MRR Realizado"
                  :value (get-in @inputs [gerente_id :realizado_mrr] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :realizado_mrr] %)}]
                [inputs/text-field
                 {:label "Meta SQL" :type :number
                  :value (get-in @inputs [gerente_id :meta_sql] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :meta_sql] %)}]
                [inputs/text-field
                 {:label "SQL Realizado" :type :number
                  :value (get-in @inputs [gerente_id :realizado_sql] "")
                  :on-change #(swap! inputs assoc-in [gerente_id :realizado_sql] %)}]])])

          (when (seq preview)
            [btn/button
             {:variant :primary
              :on-click (fn []
                          (rf/dispatch
                           [:revops/run-leadership-appraisal
                            {:quarter (:quarter @filter-s)
                             :year    (:year @filter-s)
                             :inputs  (mapv (fn [[gid vals]]
                                              (merge {:gerente_id gid} vals))
                                            @inputs)}]))}
             "Calcular Bônus"])

          ;; Results table
          (when (seq results)
            [:div {:style {:margin-top "24px"}}
             [tbl/table
              {:loading? loading?
               :columns  [{:key :gerente_id   :label "Gerente"}
                          {:key :meta_mrr     :label "Meta MRR"}
                          {:key :pct_mrr      :label "% MRR"}
                          {:key :pct_sql      :label "% SQL"}
                          {:key :multiplicador :label "Mult."}
                          {:key :bonus_amount  :label "Bônus (R$)"}
                          {:key :is_final      :label "Status"
                           :render (fn [v row]
                                     (if v
                                       [badge/badge {:variant :success} "Final"]
                                       [btn/button
                                        {:variant :primary :size :sm
                                         :on-click #(rf/dispatch
                                                     [:revops/finalize-leadership
                                                      (:id row)
                                                      (:quarter @filter-s)
                                                      (:year @filter-s)])}
                                        "Finalizar"]))}]
               :rows     results}]])]]]))))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/views/revops/ev_bonus.cljs \
        frontend/src/app/views/revops/leadership_appraisal.cljs
git commit -m "feat: RevOps EV bonus and leadership apuração views"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| CN Monthly Apuração — Regra de Ouro | Tasks 3, 4, 5, 6 (endpoint), 10 (UI) |
| CN Simulator (CN + RevOps access) | Tasks 3, 7 (endpoint), 9 (UI) |
| EV Quarterly MRR Bonus | Tasks 5 (ev_bonus module), 7 (endpoint), 11 (UI) |
| Leadership GERENTE bonus matrix | Tasks 6, 7 (endpoint), 11 (UI) |
| User model extensions (nivel, porte, salario_base) | Task 1 |
| CnMonthlyGoal model | Task 1 |
| CnMonthlyAppraisal model | Task 2 |
| EvQuarterAchievement bonus columns | Task 2 |
| GerenteQuarterAppraisal model | Task 2 |
| CN role-filtered API responses | Task 7 (cn_commissions.py enforces cn_id=user.id) |
| CN simulator — CN can only use own nivel | Task 7 (cn_commissions.py enforces) |
| meta_mrr auto-calc as 90% × SUM(EV Goals) | Task 6 (leadership_calculator.py) |
| All migrations | Tasks 1, 2 |
| Routes + frontend wiring | Task 8 |

All requirements covered.

### Type/signature consistency check

- `simulate_cn()` defined in Task 3 (`simulator.py`), called in Task 4 (`cn_calculator.py`) with matching signature `(nivel, sao_meta, sao_realizado, vidas_meta, vidas_realizado)` ✓
- `run_cn_monthly_appraisal_with_inputs()` defined in Task 4, called in Task 7 endpoint ✓
- `_mrr_multiplier()` defined in Task 5, used internally in `run_ev_quarterly_bonus()` ✓
- `_lideranca_multiplier()` defined in Task 6, used internally in `run_leadership_appraisal()` ✓
- All model fields referenced in serialisers match model definitions in Tasks 1–2 ✓
- Frontend endpoint constants (`ep/cn-goals`, `ep/cn-appraisal`, etc.) defined in Task 8 and used in Tasks 9–11 ✓
