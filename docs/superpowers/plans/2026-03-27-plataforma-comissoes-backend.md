# Plataforma de Comissões — Backend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Python/Flask backend for the Pipo Saúde commission management platform — from project scaffold through all API endpoints, business logic, and integrations.

**Architecture:** Monolito modular Flask com módulos separados (auth, models, hubspot_sync, commissions, financial, workflow, notifications). PostgreSQL como banco único. JWT auth via Google SSO. Deploy via Docker + Helm + GitLab CI no EKS da Pipo.

**Tech Stack:** Python 3.12, Flask 3.x, SQLAlchemy 2.x, Alembic, PostgreSQL 16, pytest, openpyxl, slack-sdk, google-auth, PyJWT, gunicorn, Docker

**Spec:** `docs/superpowers/specs/2026-03-27-plataforma-comissoes-design.md`

---

## File Structure

```
backend/
├── app/
│   ├── __init__.py                    # Flask app factory (create_app)
│   ├── config.py                      # Settings por ambiente (dev/test/stag/prod)
│   ├── extensions.py                  # SQLAlchemy, Migrate, JWT instances
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── google_sso.py             # Google OAuth 2.0 flow
│   │   ├── jwt_manager.py            # JWT create/verify/refresh
│   │   ├── roles.py                  # Role enum + permission matrix
│   │   └── decorators.py             # @require_auth, @require_role
│   ├── models/
│   │   ├── __init__.py               # Import all models
│   │   ├── user.py                   # User model
│   │   ├── team.py                   # Team model
│   │   ├── client.py                 # Client model (empresa normalizada)
│   │   ├── policy.py                 # Policy model (âncora: ticket cotação)
│   │   ├── commission.py             # Commission model
│   │   ├── goal.py                   # Goal model (meta EV/tri)
│   │   ├── financial_import.py       # FinancialImport + ImportBatch models
│   │   ├── perk.py                   # Perk model
│   │   ├── appraisal.py             # Appraisal model (apuração tri)
│   │   ├── commission_pct_table.py   # CommissionPctTable model (versionada)
│   │   ├── ev_validation.py          # EvValidation model
│   │   ├── notification.py           # Notification model
│   │   ├── platform_setting.py       # PlatformSetting model
│   │   └── audit_log.py             # AuditLog model + mixin
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── hubspot_sync/
│   │   │   ├── __init__.py
│   │   │   ├── client.py            # HubSpot API client (requests)
│   │   │   ├── mapper.py            # HubSpot fields → policy fields
│   │   │   ├── sync.py              # Sync orchestration
│   │   │   └── scheduler.py         # APScheduler cron config
│   │   ├── commissions/
│   │   │   ├── __init__.py
│   │   │   ├── calculator.py        # Motor de cálculo (projeção + apuração)
│   │   │   ├── achievement.py       # Cálculo de atingimento por EV
│   │   │   └── pct_lookup.py        # Lookup na tabela de % versionada
│   │   ├── financial/
│   │   │   ├── __init__.py
│   │   │   ├── parser.py            # Parse XLSX (openpyxl)
│   │   │   ├── validator.py         # Validação de dados do upload
│   │   │   └── processor.py         # Processamento: grava NFs, atualiza policies
│   │   ├── workflow/
│   │   │   ├── __init__.py
│   │   │   ├── state_machine.py     # Máquina de estados da apuração
│   │   │   ├── auto_approve.py      # Cron de auto-aprovação por prazo
│   │   │   └── transitions.py       # Regras de transição + validações
│   │   └── notifications/
│   │       ├── __init__.py
│   │       ├── service.py           # Cria notificações in-app
│   │       └── slack.py             # Envia mensagens Slack
│   └── api/
│       ├── __init__.py              # Register all blueprints
│       └── v1/
│           ├── __init__.py
│           ├── auth.py              # /api/v1/auth/*
│           ├── policies.py          # /api/v1/policies/*
│           ├── commissions.py       # /api/v1/commissions/*
│           ├── goals.py             # /api/v1/goals/*
│           ├── financial.py         # /api/v1/financial/*
│           ├── workflow.py          # /api/v1/appraisals/*
│           ├── validations.py       # /api/v1/validations/*
│           ├── finance_dashboard.py # /api/v1/finance/*
│           ├── admin.py             # /api/v1/admin/*
│           ├── notifications.py     # /api/v1/notifications/*
│           └── health.py            # /health, /ready
├── migrations/                      # Alembic (auto-generated)
├── tests/
│   ├── conftest.py                  # Fixtures: app, db, client, auth helpers
│   ├── factories.py                 # Factory Boy factories para todos os models
│   ├── test_models/
│   │   ├── test_user.py
│   │   ├── test_policy.py
│   │   ├── test_commission.py
│   │   └── ...
│   ├── test_modules/
│   │   ├── test_hubspot_sync/
│   │   ├── test_commissions/
│   │   ├── test_financial/
│   │   ├── test_workflow/
│   │   └── test_notifications/
│   └── test_api/
│       ├── test_auth.py
│       ├── test_policies.py
│       ├── test_commissions.py
│       └── ...
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── Makefile
├── .env.example
└── wsgi.py                          # Gunicorn entry point
```

---

## Chunk 1: Project Foundation

### Task 1.1: Project Scaffold

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/extensions.py`
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/wsgi.py`
- Create: `backend/Makefile`
- Create: `backend/.env.example`

- [ ] **Step 1: Create requirements.txt**

```
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.0.7
Flask-CORS==5.0.0
SQLAlchemy==2.0.36
psycopg2-binary==2.9.10
PyJWT==2.10.1
google-auth==2.37.0
google-auth-oauthlib==1.2.1
requests==2.32.3
openpyxl==3.1.5
slack-sdk==3.33.5
APScheduler==3.10.4
gunicorn==23.0.0
python-dotenv==1.0.1
marshmallow==3.23.2
```

- [ ] **Step 2: Create requirements-dev.txt**

```
-r requirements.txt
pytest==8.3.4
pytest-cov==6.0.0
factory-boy==3.3.1
freezegun==1.4.0
responses==0.25.6
flake8==7.1.1
black==24.10.0
```

- [ ] **Step 3: Create backend/app/config.py**

```python
import os


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/comissoes_dev"
    )

    # JWT
    JWT_ACCESS_TOKEN_EXPIRES = 8 * 60 * 60  # 8 hours in seconds
    JWT_REFRESH_TOKEN_EXPIRES = 7 * 24 * 60 * 60  # 7 days in seconds

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
    ALLOWED_EMAIL_DOMAIN = "piposaude.com"

    # HubSpot
    HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
    HUBSPOT_SYNC_INTERVAL_MINUTES = int(
        os.environ.get("HUBSPOT_SYNC_INTERVAL_MINUTES", "30")
    )

    # Slack
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


class DevConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://localhost:5432/comissoes_test"
    )


class StagConfig(Config):
    DEBUG = False


class ProdConfig(Config):
    DEBUG = False


config_map = {
    "dev": DevConfig,
    "test": TestConfig,
    "stag": StagConfig,
    "prod": ProdConfig,
}
```

- [ ] **Step 4: Create backend/app/extensions.py**

```python
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
```

- [ ] **Step 5: Create backend/app/__init__.py**

```python
import os
from flask import Flask
from app.config import config_map
from app.extensions import db, migrate, cors


def create_app(config_name=None):
    """Flask application factory."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "dev")

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})

    # Register blueprints
    from app.api import register_blueprints
    register_blueprints(app)

    return app
```

- [ ] **Step 6: Create backend/app/api/__init__.py**

```python
def register_blueprints(app):
    """Register all API blueprints."""
    from app.api.v1.health import health_bp
    app.register_blueprint(health_bp)
```

- [ ] **Step 7: Create backend/app/api/v1/__init__.py**

```python
# V1 API blueprints
```

- [ ] **Step 8: Create backend/app/api/v1/health.py**

```python
from flask import Blueprint, jsonify
from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Liveness check — app is running."""
    return jsonify({"status": "ok"})


@health_bp.route("/ready")
def ready():
    """Readiness check — DB connected."""
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ready"})
    except Exception as e:
        return jsonify({"status": "not_ready", "error": str(e)}), 503
```

- [ ] **Step 9: Create backend/wsgi.py**

```python
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
```

- [ ] **Step 10: Create backend/Makefile**

```makefile
.PHONY: test lint format check run migrate

run:
	flask run --debug

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	flake8 app/ tests/

format:
	black app/ tests/

check: lint test

migrate:
	flask db upgrade

migrate-new:
	flask db migrate -m "$(msg)"
```

- [ ] **Step 11: Create backend/.env.example**

```
FLASK_ENV=dev
SECRET_KEY=change-me-in-production
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/comissoes_dev
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/comissoes_test
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:5000/api/v1/auth/google/callback
HUBSPOT_TOKEN=
SLACK_BOT_TOKEN=
```

- [ ] **Step 12: Commit**

```bash
cd backend && git add -A
git commit -m "feat: scaffold Flask project with app factory, config, and health endpoints

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.2: Test Infrastructure

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create backend/tests/conftest.py**

```python
import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app("test")
    with app.app_context():
        yield app


@pytest.fixture(scope="session")
def _setup_db(app):
    """Create all tables once per test session."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=True)
def db_session(app, _setup_db):
    """Roll back each test's DB changes."""
    with app.app_context():
        connection = _setup_db.engine.connect()
        transaction = connection.begin()
        session = _db.session
        old_bind = session.get_bind()

        session.configure(bind=connection)
        yield session

        transaction.rollback()
        connection.close()
        session.configure(bind=old_bind)


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()
```

- [ ] **Step 2: Create backend/tests/__init__.py** (empty file)

- [ ] **Step 3: Write smoke test**

Create `backend/tests/test_health.py`:

```python
def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_ready_returns_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json["status"] == "ready"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pip install -r requirements-dev.txt && pytest tests/test_health.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add test infrastructure and health endpoint smoke tests

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.3: All SQLAlchemy Models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/team.py`
- Create: `backend/app/models/client.py`
- Create: `backend/app/models/policy.py`
- Create: `backend/app/models/commission.py`
- Create: `backend/app/models/goal.py`
- Create: `backend/app/models/financial_import.py`
- Create: `backend/app/models/perk.py`
- Create: `backend/app/models/appraisal.py`
- Create: `backend/app/models/commission_pct_table.py`
- Create: `backend/app/models/ev_validation.py`
- Create: `backend/app/models/notification.py`
- Create: `backend/app/models/platform_setting.py`
- Create: `backend/app/models/audit_log.py`
- Test: `backend/tests/test_models/`

- [ ] **Step 1: Create backend/app/models/audit_log.py — AuditMixin + AuditLog model**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name = db.Column(db.String(100), nullable=False, index=True)
    record_id = db.Column(UUID(as_uuid=True), nullable=False, index=True)
    action = db.Column(db.String(10), nullable=False)  # CREATE, UPDATE, DELETE
    old_values = db.Column(JSONB, nullable=True)
    new_values = db.Column(JSONB, nullable=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<AuditLog {self.action} {self.table_name} {self.record_id}>"
```

- [ ] **Step 2: Create backend/app/models/user.py**

```python
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    FINANCE = "FINANCE"
    GERENTE = "GERENTE"
    EV = "EV"
    CN = "CN"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(UserRole, name="user_role"), nullable=True)
    google_id = db.Column(db.String(255), nullable=True)
    team_id = db.Column(UUID(as_uuid=True), db.ForeignKey("teams.id"), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    refresh_token = db.Column(db.String(500), nullable=True)
    slack_user_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    team = db.relationship("Team", back_populates="members", foreign_keys=[team_id])

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

    def has_role(self, *roles):
        return self.role in roles

    def is_admin(self):
        return self.role == UserRole.ADMIN
```

- [ ] **Step 3: Create backend/app/models/team.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    leader_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    slack_channel_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    leader = db.relationship("User", foreign_keys=[leader_id])
    members = db.relationship(
        "User", back_populates="team", foreign_keys="User.team_id"
    )

    def __repr__(self):
        return f"<Team {self.name}>"
```

- [ ] **Step 4: Create backend/app/models/client.py**

```python
import uuid
import unicodedata
import re
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


def normalize_client_name(name):
    """Normalize company name: lowercase, strip accents, trim whitespace."""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"\s+", " ", name)
    return name


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(500), nullable=False, index=True)
    name_normalized = db.Column(db.String(500), unique=True, nullable=False, index=True)
    hubspot_company_id = db.Column(db.String(100), nullable=True)
    ev_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ev = db.relationship("User", foreign_keys=[ev_id])
    policies = db.relationship("Policy", back_populates="client")

    def __repr__(self):
        return f"<Client {self.name}>"

    @classmethod
    def find_or_create(cls, name, ev_id=None):
        """Find by normalized name or create new client."""
        normalized = normalize_client_name(name)
        client = cls.query.filter_by(name_normalized=normalized).first()
        if client is None:
            client = cls(name=name, name_normalized=normalized, ev_id=ev_id)
            db.session.add(client)
        return client
```

- [ ] **Step 5: Create backend/app/models/policy.py**

```python
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class BenefitType(str, enum.Enum):
    SAUDE = "SAUDE"
    ODONTO = "ODONTO"
    VIDA = "VIDA"


class Segment(str, enum.Enum):
    PP = "PP"
    P = "P"
    M = "M"
    G = "G"


class CommissionStatus(str, enum.Enum):
    PROJECTED = "PROJECTED"
    IN_PAYMENT = "IN_PAYMENT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class Policy(db.Model):
    __tablename__ = "policies"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hubspot_ticket_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    ev_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    client_id = db.Column(UUID(as_uuid=True), db.ForeignKey("clients.id"), nullable=False)
    deal_id = db.Column(db.String(100), nullable=True)
    benefit_type = db.Column(db.Enum(BenefitType, name="benefit_type"), nullable=True)
    segment = db.Column(db.Enum(Segment, name="segment"), nullable=True)
    headcount = db.Column(db.Integer, nullable=True)
    mrr_projected = db.Column(db.Numeric(12, 2), nullable=True)
    mrr_post_deploy = db.Column(db.Numeric(12, 2), nullable=True)
    mrr_actual = db.Column(db.Numeric(12, 2), nullable=True)
    closed_date = db.Column(db.Date, nullable=True)
    deploy_date = db.Column(db.Date, nullable=True)
    first_payment_prev = db.Column(db.Date, nullable=True)
    first_payment_real = db.Column(db.Date, nullable=True)
    installments_paid = db.Column(db.Integer, default=0, nullable=False)
    commission_status = db.Column(
        db.Enum(CommissionStatus, name="commission_status"),
        default=CommissionStatus.PROJECTED,
        nullable=False,
    )
    partner_operator = db.Column(db.String(255), nullable=True)
    deal_stage = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ev = db.relationship("User", foreign_keys=[ev_id])
    client = db.relationship("Client", back_populates="policies")
    commissions = db.relationship("Commission", back_populates="policy")

    def __repr__(self):
        return f"<Policy {self.hubspot_ticket_id} ({self.commission_status})>"

    @property
    def mrr_for_commission(self):
        """MRR cascade: actual > post_deploy > projected."""
        if self.mrr_actual is not None:
            return self.mrr_actual
        if self.mrr_post_deploy is not None:
            return self.mrr_post_deploy
        return self.mrr_projected

    @property
    def quarter_closed(self):
        """Quarter when deal was closed (gongo)."""
        if self.closed_date is None:
            return None, None
        q = (self.closed_date.month - 1) // 3 + 1
        return q, self.closed_date.year
```

- [ ] **Step 6: Create backend/app/models/goal.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class Goal(db.Model):
    __tablename__ = "goals"
    __table_args__ = (
        db.UniqueConstraint("ev_id", "quarter", "year", name="uq_goal_ev_quarter_year"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ev_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    mrr_target = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ev = db.relationship("User", foreign_keys=[ev_id])

    def __repr__(self):
        return f"<Goal EV={self.ev_id} Q{self.quarter}/{self.year} target={self.mrr_target}>"
```

- [ ] **Step 7: Create backend/app/models/commission.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class Commission(db.Model):
    __tablename__ = "commissions"
    __table_args__ = (
        db.UniqueConstraint(
            "policy_id", "quarter", "year", name="uq_commission_policy_quarter_year"
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = db.Column(UUID(as_uuid=True), db.ForeignKey("policies.id"), nullable=False)
    ev_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    segment = db.Column(db.String(10), nullable=True)
    achievement_pct = db.Column(db.Numeric(8, 4), nullable=True)
    commission_pct = db.Column(db.Numeric(8, 4), nullable=True)
    commission_pct_version = db.Column(db.Integer, nullable=True)
    monthly_estimated = db.Column(db.Numeric(12, 2), nullable=True)
    monthly_actual = db.Column(db.Numeric(12, 2), nullable=True)
    total_estimated = db.Column(db.Numeric(12, 2), nullable=True)
    total_actual = db.Column(db.Numeric(12, 2), nullable=True)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    policy = db.relationship("Policy", back_populates="commissions")
    ev = db.relationship("User", foreign_keys=[ev_id])

    def __repr__(self):
        return f"<Commission policy={self.policy_id} Q{self.quarter}/{self.year}>"
```

- [ ] **Step 8: Create backend/app/models/financial_import.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class ImportBatch(db.Model):
    __tablename__ = "import_batches"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    nf_count = db.Column(db.Integer, default=0)
    perk_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="PENDING")  # PENDING, CONFIRMED, CANCELLED
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class FinancialImport(db.Model):
    __tablename__ = "financial_imports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = db.Column(UUID(as_uuid=True), db.ForeignKey("policies.id"), nullable=False)
    nf_valor_liquido = db.Column(db.Numeric(12, 2), nullable=False)
    nf_mes_recebimento = db.Column(db.String(7), nullable=False)  # YYYY-MM
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    import_batch_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("import_batches.id"), nullable=False
    )
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "policy_id", "nf_mes_recebimento", name="uq_financial_policy_month"
        ),
    )

    policy = db.relationship("Policy", foreign_keys=[policy_id])
    batch = db.relationship("ImportBatch", foreign_keys=[import_batch_id])
```

- [ ] **Step 9: Create backend/app/models/perk.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class Perk(db.Model):
    __tablename__ = "perks"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = db.Column(UUID(as_uuid=True), db.ForeignKey("clients.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    import_batch_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("import_batches.id"), nullable=False
    )
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    client = db.relationship("Client", foreign_keys=[client_id])
    batch = db.relationship("ImportBatch", foreign_keys=[import_batch_id])
```

- [ ] **Step 10: Create backend/app/models/appraisal.py**

```python
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class AppraisalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CALCULATING = "CALCULATING"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"


class Appraisal(db.Model):
    __tablename__ = "appraisals"
    __table_args__ = (
        db.UniqueConstraint("quarter", "year", name="uq_appraisal_quarter_year"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum(AppraisalStatus, name="appraisal_status"),
        default=AppraisalStatus.DRAFT,
        nullable=False,
    )
    validation_deadline = db.Column(db.Date, nullable=True)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    approved_by_finance = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True
    )
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = db.relationship("User", foreign_keys=[created_by])
    approver = db.relationship("User", foreign_keys=[approved_by_finance])
    validations = db.relationship("EvValidation", back_populates="appraisal")

    def __repr__(self):
        return f"<Appraisal Q{self.quarter}/{self.year} ({self.status})>"

    @property
    def is_locked(self):
        return self.status == AppraisalStatus.LOCKED
```

- [ ] **Step 11: Create backend/app/models/commission_pct_table.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class CommissionPctTable(db.Model):
    __tablename__ = "commission_pct_table"
    __table_args__ = (
        db.UniqueConstraint(
            "version", "segment", "achievement_min",
            name="uq_pct_version_segment_min",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = db.Column(db.Integer, nullable=False, index=True)
    segment = db.Column(db.String(10), nullable=False)
    achievement_min = db.Column(db.Numeric(8, 4), nullable=False)
    achievement_max = db.Column(db.Numeric(8, 4), nullable=False)
    commission_pct = db.Column(db.Numeric(8, 4), nullable=False)
    valid_from = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)

    @classmethod
    def current_version(cls):
        """Get the latest version number."""
        result = db.session.query(db.func.max(cls.version)).scalar()
        return result or 0

    @classmethod
    def lookup(cls, segment, achievement_pct, version=None):
        """Find commission % for given segment and achievement."""
        if version is None:
            version = cls.current_version()
        return cls.query.filter(
            cls.version == version,
            cls.segment == segment,
            cls.achievement_min <= achievement_pct,
            cls.achievement_max >= achievement_pct,
        ).first()
```

- [ ] **Step 12: Create backend/app/models/ev_validation.py**

```python
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID


class ValidationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CONTESTED = "CONTESTED"
    RESOLVED = "RESOLVED"
    AUTO_APPROVED = "AUTO_APPROVED"


class EvValidation(db.Model):
    __tablename__ = "ev_validations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("appraisals.id"), nullable=False
    )
    policy_id = db.Column(UUID(as_uuid=True), db.ForeignKey("policies.id"), nullable=False)
    ev_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    status = db.Column(
        db.Enum(ValidationStatus, name="validation_status"),
        default=ValidationStatus.PENDING,
        nullable=False,
    )
    comment = db.Column(db.Text, nullable=True)
    resolution_comment = db.Column(db.Text, nullable=True)
    contested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    appraisal = db.relationship("Appraisal", back_populates="validations")
    policy = db.relationship("Policy", foreign_keys=[policy_id])
    ev = db.relationship("User", foreign_keys=[ev_id])
    resolver = db.relationship("User", foreign_keys=[resolved_by])
```

- [ ] **Step 13: Create backend/app/models/notification.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=True)
    read = db.Column(db.Boolean, default=False, nullable=False)
    metadata_ = db.Column("metadata", JSONB, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", foreign_keys=[user_id])
```

- [ ] **Step 14: Create backend/app/models/platform_setting.py**

```python
import uuid
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class PlatformSetting(db.Model):
    __tablename__ = "platform_settings"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(JSONB, nullable=True)
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @classmethod
    def get(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            return default
        return setting.value

    @classmethod
    def set(cls, key, value, user_id=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key, value=value, updated_by=user_id)
            db.session.add(setting)
        else:
            setting.value = value
            setting.updated_by = user_id
        return setting
```

- [ ] **Step 15: Create backend/app/models/__init__.py — import all models**

```python
from app.models.user import User, UserRole
from app.models.team import Team
from app.models.client import Client
from app.models.policy import Policy, BenefitType, Segment, CommissionStatus
from app.models.goal import Goal
from app.models.commission import Commission
from app.models.financial_import import FinancialImport, ImportBatch
from app.models.perk import Perk
from app.models.appraisal import Appraisal, AppraisalStatus
from app.models.commission_pct_table import CommissionPctTable
from app.models.ev_validation import EvValidation, ValidationStatus
from app.models.notification import Notification
from app.models.platform_setting import PlatformSetting
from app.models.audit_log import AuditLog

__all__ = [
    "User", "UserRole",
    "Team",
    "Client",
    "Policy", "BenefitType", "Segment", "CommissionStatus",
    "Goal",
    "Commission",
    "FinancialImport", "ImportBatch",
    "Perk",
    "Appraisal", "AppraisalStatus",
    "CommissionPctTable",
    "EvValidation", "ValidationStatus",
    "Notification",
    "PlatformSetting",
    "AuditLog",
]
```

- [ ] **Step 16: Update app/__init__.py to import models**

Add after extensions init, before blueprints:

```python
    # Import models so Alembic sees them
    import app.models  # noqa: F401
```

- [ ] **Step 17: Write model tests**

Create `backend/tests/test_models/__init__.py` (empty) and `backend/tests/test_models/test_policy.py`:

```python
from decimal import Decimal
from datetime import date
from app.models import Policy, CommissionStatus


def test_mrr_for_commission_prefers_actual(db_session):
    """MRR cascade: actual > post_deploy > projected."""
    policy = Policy(
        hubspot_ticket_id="TEST-1",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=Decimal("1200"),
        mrr_actual=Decimal("1100"),
    )
    assert policy.mrr_for_commission == Decimal("1100")


def test_mrr_for_commission_falls_back_to_post_deploy(db_session):
    policy = Policy(
        hubspot_ticket_id="TEST-2",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=Decimal("1200"),
        mrr_actual=None,
    )
    assert policy.mrr_for_commission == Decimal("1200")


def test_mrr_for_commission_falls_back_to_projected(db_session):
    policy = Policy(
        hubspot_ticket_id="TEST-3",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=None,
        mrr_actual=None,
    )
    assert policy.mrr_for_commission == Decimal("1000")


def test_quarter_closed_from_date(db_session):
    policy = Policy(
        hubspot_ticket_id="TEST-4",
        ev_id=None,
        client_id=None,
        closed_date=date(2026, 2, 15),
    )
    q, y = policy.quarter_closed
    assert q == 1
    assert y == 2026
```

- [ ] **Step 18: Run model tests**

```bash
cd backend && pytest tests/test_models/ -v
```

Expected: 4 PASSED

- [ ] **Step 19: Commit**

```bash
git add app/models/ tests/test_models/
git commit -m "feat: add all SQLAlchemy models with relationships and constraints

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.4: Initial Migration

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend && flask db init
```

- [ ] **Step 2: Generate migration**

```bash
flask db migrate -m "initial schema - all tables"
```

- [ ] **Step 3: Apply migration**

```bash
flask db upgrade
```

- [ ] **Step 4: Commit**

```bash
git add migrations/
git commit -m "feat: add initial Alembic migration with all tables

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.5: Test Factories

**Files:**
- Create: `backend/tests/factories.py`

- [ ] **Step 1: Create backend/tests/factories.py**

```python
import uuid
import factory
from datetime import date, datetime, timezone
from decimal import Decimal
from app.extensions import db
from app.models import (
    User, UserRole, Team, Client, Policy, Segment, BenefitType,
    CommissionStatus, Goal, Commission, Appraisal, AppraisalStatus,
    CommissionPctTable, EvValidation, ValidationStatus, Notification,
    FinancialImport, ImportBatch, Perk, PlatformSetting,
)


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = None  # Set in conftest

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        instance = model_class(*args, **kwargs)
        db.session.add(instance)
        db.session.flush()
        return instance


class TeamFactory(BaseFactory):
    class Meta:
        model = Team

    name = factory.Sequence(lambda n: f"Time Vendas {n}")


class UserFactory(BaseFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@piposaude.com")
    name = factory.Sequence(lambda n: f"Usuário {n}")
    role = UserRole.EV
    active = True


class ClientFactory(BaseFactory):
    class Meta:
        model = Client

    name = factory.Sequence(lambda n: f"Empresa {n} Ltda")
    name_normalized = factory.LazyAttribute(
        lambda o: o.name.strip().lower()
    )


class PolicyFactory(BaseFactory):
    class Meta:
        model = Policy

    hubspot_ticket_id = factory.Sequence(lambda n: f"TICKET-{n}")
    ev_id = factory.LazyAttribute(lambda o: UserFactory().id)
    client_id = factory.LazyAttribute(lambda o: ClientFactory().id)
    segment = Segment.P
    benefit_type = BenefitType.SAUDE
    mrr_projected = Decimal("5000.00")
    commission_status = CommissionStatus.PROJECTED
    closed_date = date(2026, 1, 15)


class GoalFactory(BaseFactory):
    class Meta:
        model = Goal

    ev_id = factory.LazyAttribute(lambda o: UserFactory().id)
    quarter = 1
    year = 2026
    mrr_target = Decimal("50000.00")


class CommissionFactory(BaseFactory):
    class Meta:
        model = Commission

    policy_id = factory.LazyAttribute(lambda o: PolicyFactory().id)
    ev_id = factory.LazyAttribute(lambda o: UserFactory().id)
    quarter = 1
    year = 2026


class AppraisalFactory(BaseFactory):
    class Meta:
        model = Appraisal

    quarter = 1
    year = 2026
    status = AppraisalStatus.DRAFT
    created_by = factory.LazyAttribute(lambda o: UserFactory(role=UserRole.ADMIN).id)


class ImportBatchFactory(BaseFactory):
    class Meta:
        model = ImportBatch

    filename = "financeiro_q1_2026.xlsx"
    uploaded_by = factory.LazyAttribute(lambda o: UserFactory(role=UserRole.ADMIN).id)


class CommissionPctTableFactory(BaseFactory):
    class Meta:
        model = CommissionPctTable

    version = 1
    segment = "P"
    achievement_min = Decimal("0.50")
    achievement_max = Decimal("0.999")
    commission_pct = Decimal("0.10")
```

- [ ] **Step 2: Update conftest.py to configure factories**

Add to `backend/tests/conftest.py`:

```python
from tests.factories import BaseFactory

# In the app fixture, after yield:
# BaseFactory.Meta.sqlalchemy_session = db_session
```

- [ ] **Step 3: Commit**

```bash
git add tests/factories.py
git commit -m "test: add Factory Boy factories for all models

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 2: Auth + RBAC

### Task 2.1: JWT Manager

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/jwt_manager.py`
- Test: `backend/tests/test_auth/test_jwt_manager.py`

- [ ] **Step 1: Write failing test for JWT creation and verification**

Create `backend/tests/test_auth/__init__.py` (empty) and `backend/tests/test_auth/test_jwt_manager.py`:

```python
import uuid
from app.auth.jwt_manager import create_access_token, create_refresh_token, decode_token


def test_create_and_decode_access_token(app):
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, "ADMIN")
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token(app):
    user_id = str(uuid.uuid4())
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_expired_token_raises(app):
    from freezegun import freeze_time
    from datetime import datetime, timedelta
    from app.auth.jwt_manager import InvalidTokenError

    user_id = str(uuid.uuid4())
    with freeze_time(datetime(2020, 1, 1)):
        token = create_access_token(user_id, "EV")

    # Token created in 2020 should be expired now
    try:
        decode_token(token)
        assert False, "Should have raised InvalidTokenError"
    except InvalidTokenError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_auth/test_jwt_manager.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Implement JWT manager**

Create `backend/app/auth/__init__.py` (empty) and `backend/app/auth/jwt_manager.py`:

```python
import jwt
from datetime import datetime, timedelta, timezone
from flask import current_app


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id, role):
    """Create JWT access token with user_id and role."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc)
        + timedelta(seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def create_refresh_token(user_id):
    """Create JWT refresh token."""
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc)
        + timedelta(seconds=current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(token):
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token expired")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Invalid token: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_auth/test_jwt_manager.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/auth/ tests/test_auth/
git commit -m "feat: add JWT manager with access/refresh token creation and validation

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 2.2: Roles and Permission Decorators

**Files:**
- Create: `backend/app/auth/roles.py`
- Create: `backend/app/auth/decorators.py`
- Test: `backend/tests/test_auth/test_decorators.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_auth/test_decorators.py`:

```python
import uuid
from app.models import User, UserRole
from app.auth.jwt_manager import create_access_token


def test_require_auth_blocks_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_require_auth_allows_valid_token(client, app, db_session):
    user = User(
        email="test@piposaude.com",
        name="Test User",
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.flush()

    with app.app_context():
        token = create_access_token(str(user.id), user.role.value)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["data"]["email"] == "test@piposaude.com"


def test_require_role_blocks_wrong_role(client, app, db_session):
    user = User(
        email="ev@piposaude.com",
        name="EV User",
        role=UserRole.EV,
    )
    db_session.add(user)
    db_session.flush()

    with app.app_context():
        token = create_access_token(str(user.id), user.role.value)

    response = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_auth/test_decorators.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement roles.py**

```python
from app.models.user import UserRole

# Permission matrix: role → list of allowed permission keys
PERMISSIONS = {
    UserRole.ADMIN: ["*"],  # Admin has access to everything
    UserRole.FINANCE: [
        "policies:read_all",
        "commissions:read_all",
        "finance:dashboard",
        "finance:export",
        "appraisals:approve_payment",
        "appraisals:return",
    ],
    UserRole.GERENTE: [
        "policies:read_team",
        "commissions:read_team",
    ],
    UserRole.EV: [
        "policies:read_own",
        "commissions:read_own",
        "validations:read_own",
        "validations:approve",
        "validations:contest",
    ],
    UserRole.CN: [
        "policies:read_own",
        "commissions:read_own",
        "validations:read_own",
        "validations:approve",
        "validations:contest",
    ],
}


def user_has_permission(role, permission):
    """Check if a role has a specific permission."""
    if role is None:
        return False
    perms = PERMISSIONS.get(role, [])
    return "*" in perms or permission in perms


def user_has_any_role(role, *allowed_roles):
    """Check if user role is in the allowed list. ADMIN always passes."""
    if role == UserRole.ADMIN:
        return True
    return role in allowed_roles
```

- [ ] **Step 4: Implement decorators.py**

```python
from functools import wraps
from flask import request, jsonify, g
from app.auth.jwt_manager import decode_token, InvalidTokenError
from app.models.user import User, UserRole


def require_auth(f):
    """Decorator: require valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"}}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except InvalidTokenError as e:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": str(e)}}), 401

        if payload.get("type") != "access":
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Invalid token type"}}), 401

        user = User.query.get(payload["sub"])
        if user is None or not user.active:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "User not found or inactive"}}), 401

        if user.role is None:
            return jsonify({"error": {"code": "FORBIDDEN", "message": "User has no role assigned"}}), 403

        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def require_role(*allowed_roles):
    """Decorator: require specific role(s). ADMIN always passes."""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            user = g.current_user
            if user.role == UserRole.ADMIN:
                return f(*args, **kwargs)
            if user.role not in allowed_roles:
                return jsonify({"error": {"code": "FORBIDDEN", "message": "Insufficient permissions"}}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
```

- [ ] **Step 5: Create auth API endpoints (me)**

Create `backend/app/api/v1/auth.py`:

```python
from flask import Blueprint, jsonify, g
from app.auth.decorators import require_auth

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/me")
@require_auth
def me():
    """Return current user data."""
    user = g.current_user
    return jsonify({
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value if user.role else None,
            "team_id": str(user.team_id) if user.team_id else None,
            "active": user.active,
        }
    })
```

- [ ] **Step 6: Create placeholder admin API**

Create `backend/app/api/v1/admin.py`:

```python
from flask import Blueprint, jsonify
from app.auth.decorators import require_role
from app.models.user import UserRole

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@admin_bp.route("/users")
@require_role(UserRole.ADMIN)
def list_users():
    """List all users (ADMIN only)."""
    from app.models import User
    users = User.query.filter_by(active=True).all()
    return jsonify({
        "data": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role.value if u.role else None,
                "team_id": str(u.team_id) if u.team_id else None,
            }
            for u in users
        ]
    })
```

- [ ] **Step 7: Register blueprints**

Update `backend/app/api/__init__.py`:

```python
def register_blueprints(app):
    """Register all API blueprints."""
    from app.api.v1.health import health_bp
    from app.api.v1.auth import auth_bp
    from app.api.v1.admin import admin_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
```

- [ ] **Step 8: Run tests**

```bash
cd backend && pytest tests/test_auth/ -v
```

Expected: All PASSED

- [ ] **Step 9: Commit**

```bash
git add app/auth/ app/api/ tests/test_auth/
git commit -m "feat: add RBAC with JWT auth, role decorators, and auth/admin endpoints

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 2.3: Google SSO

**Files:**
- Create: `backend/app/auth/google_sso.py`
- Modify: `backend/app/api/v1/auth.py`

- [ ] **Step 1: Implement Google SSO**

Create `backend/app/auth/google_sso.py`:

```python
import requests
from flask import current_app


class GoogleSSOError(Exception):
    pass


def exchange_code_for_tokens(code):
    """Exchange authorization code for Google tokens."""
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"Token exchange failed: {response.text}")
    return response.json()


def get_user_info(access_token):
    """Get Google user profile info."""
    response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"User info fetch failed: {response.text}")
    return response.json()


def validate_email_domain(email):
    """Check email is from allowed domain."""
    domain = email.split("@")[-1]
    allowed = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    if domain != allowed:
        raise GoogleSSOError(f"Email domain {domain} not allowed. Must be @{allowed}")
    return True
```

- [ ] **Step 2: Add Google callback endpoint to auth.py**

Add to `backend/app/api/v1/auth.py`:

```python
from flask import request
from app.auth.google_sso import exchange_code_for_tokens, get_user_info, validate_email_domain, GoogleSSOError
from app.auth.jwt_manager import create_access_token, create_refresh_token, decode_token, InvalidTokenError
from app.models import User
from app.extensions import db


@auth_bp.route("/google", methods=["POST"])
def google_login():
    """Exchange Google auth code for JWT tokens."""
    code = request.json.get("code")
    if not code:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Authorization code required"}}), 400

    try:
        tokens = exchange_code_for_tokens(code)
        user_info = get_user_info(tokens["access_token"])
        validate_email_domain(user_info["email"])
    except GoogleSSOError as e:
        return jsonify({"error": {"code": "AUTH_ERROR", "message": str(e)}}), 401

    # Find or create user
    user = User.query.filter_by(email=user_info["email"]).first()
    if user is None:
        user = User(
            email=user_info["email"],
            name=user_info.get("name", user_info["email"]),
            google_id=user_info.get("id"),
            role=None,  # No role until admin assigns
        )
        db.session.add(user)

    # Generate tokens
    access_token = create_access_token(
        str(user.id), user.role.value if user.role else None
    )
    refresh_token = create_refresh_token(str(user.id))
    user.refresh_token = refresh_token
    db.session.commit()

    return jsonify({
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role.value if user.role else None,
            },
        }
    })


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """Refresh access token using refresh token."""
    refresh_token = request.json.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Refresh token required"}}), 400

    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError as e:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": str(e)}}), 401

    if payload.get("type") != "refresh":
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Invalid token type"}}), 401

    user = User.query.get(payload["sub"])
    if user is None or not user.active:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "User not found"}}), 401

    if user.refresh_token != refresh_token:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Token revoked"}}), 401

    access_token = create_access_token(
        str(user.id), user.role.value if user.role else None
    )
    return jsonify({"data": {"access_token": access_token}})
```

- [ ] **Step 3: Commit**

```bash
git add app/auth/google_sso.py app/api/v1/auth.py
git commit -m "feat: add Google SSO login, token refresh, and user auto-creation

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 3: Core Business Logic

### Task 3.1: Commission Calculator — Achievement

**Files:**
- Create: `backend/app/modules/__init__.py`
- Create: `backend/app/modules/commissions/__init__.py`
- Create: `backend/app/modules/commissions/achievement.py`
- Test: `backend/tests/test_modules/test_commissions/test_achievement.py`

- [ ] **Step 1: Write failing test**

Create dirs and `backend/tests/test_modules/__init__.py`, `backend/tests/test_modules/test_commissions/__init__.py`, then:

```python
# backend/tests/test_modules/test_commissions/test_achievement.py
from decimal import Decimal
from app.modules.commissions.achievement import calculate_achievement


def test_achievement_100_percent(db_session):
    """EV with MRR equal to target = 100%."""
    result = calculate_achievement(
        total_mrr_gongos=Decimal("50000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("1.0")


def test_achievement_50_percent(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("25000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("0.5")


def test_achievement_over_100(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("75000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("1.5")


def test_achievement_zero_target_returns_zero(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("10000"),
        mrr_target=Decimal("0"),
    )
    assert result == Decimal("0")
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && pytest tests/test_modules/test_commissions/test_achievement.py -v
```

- [ ] **Step 3: Implement achievement.py**

```python
from decimal import Decimal


def calculate_achievement(total_mrr_gongos, mrr_target):
    """Calculate EV achievement percentage.

    achievement = sum(MRR gongos no tri) / meta MRR do tri
    """
    if mrr_target is None or mrr_target == 0:
        return Decimal("0")
    return (total_mrr_gongos / mrr_target).quantize(Decimal("0.0001"))
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && pytest tests/test_modules/test_commissions/test_achievement.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/ tests/test_modules/
git commit -m "feat: add achievement percentage calculator

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.2: Commission Calculator — Pct Lookup

**Files:**
- Create: `backend/app/modules/commissions/pct_lookup.py`
- Test: `backend/tests/test_modules/test_commissions/test_pct_lookup.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_modules/test_commissions/test_pct_lookup.py
from decimal import Decimal
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.models import CommissionPctTable
from app.extensions import db


def _seed_pct_table(session):
    """Seed version 1 of commission pct table: 3 segments x 3 faixas."""
    rows = [
        # PP
        ("PP", "0.0000", "0.4999", "0.05"),
        ("PP", "0.5000", "0.9999", "0.08"),
        ("PP", "1.0000", "9.9999", "0.12"),
        # P
        ("P", "0.0000", "0.4999", "0.06"),
        ("P", "0.5000", "0.9999", "0.10"),
        ("P", "1.0000", "9.9999", "0.15"),
        # M
        ("M", "0.0000", "0.4999", "0.04"),
        ("M", "0.5000", "0.9999", "0.07"),
        ("M", "1.0000", "9.9999", "0.10"),
    ]
    for segment, amin, amax, pct in rows:
        row = CommissionPctTable(
            version=1,
            segment=segment,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        )
        session.add(row)
    session.flush()


def test_lookup_p_segment_medium_achievement(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("P", Decimal("0.75"))
    assert pct == Decimal("0.10")
    assert version == 1


def test_lookup_pp_segment_high_achievement(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("PP", Decimal("1.20"))
    assert pct == Decimal("0.12")
    assert version == 1


def test_lookup_returns_none_for_unknown_segment(db_session):
    _seed_pct_table(db_session)
    pct, version = lookup_commission_pct("G", Decimal("0.75"))
    assert pct is None
    assert version == 1
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement pct_lookup.py**

```python
from decimal import Decimal
from app.models import CommissionPctTable


def lookup_commission_pct(segment, achievement_pct, version=None):
    """Lookup commission percentage for segment and achievement.

    Returns (commission_pct, version) or (None, version) if not found.
    """
    if version is None:
        version = CommissionPctTable.current_version()

    if version == 0:
        return None, 0

    row = CommissionPctTable.lookup(segment, achievement_pct, version)
    if row is None:
        return None, version

    return row.commission_pct, version
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/modules/commissions/pct_lookup.py tests/test_modules/test_commissions/test_pct_lookup.py
git commit -m "feat: add commission percentage lookup with versioned table

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.3: Commission Calculator — Full Engine

**Files:**
- Create: `backend/app/modules/commissions/calculator.py`
- Test: `backend/tests/test_modules/test_commissions/test_calculator.py`

- [ ] **Step 1: Write failing test for projection**

```python
# backend/tests/test_modules/test_commissions/test_calculator.py
from decimal import Decimal
from datetime import date
from app.modules.commissions.calculator import (
    calculate_projection_for_policy,
    run_quarterly_appraisal,
)
from app.models import (
    User, UserRole, Client, Policy, Goal, Commission,
    CommissionPctTable, Segment, CommissionStatus,
)
from app.extensions import db


def _setup_ev_and_policy(session):
    """Create an EV, client, goal, pct table, and a policy."""
    ev = User(email="ev1@piposaude.com", name="EV 1", role=UserRole.EV)
    session.add(ev)
    session.flush()

    client = Client(name="Acme Corp", name_normalized="acme corp", ev_id=ev.id)
    session.add(client)
    session.flush()

    goal = Goal(ev_id=ev.id, quarter=1, year=2026, mrr_target=Decimal("50000"))
    session.add(goal)

    # Pct table version 1 for P segment
    for amin, amax, pct in [
        ("0.0000", "0.4999", "0.06"),
        ("0.5000", "0.9999", "0.10"),
        ("1.0000", "9.9999", "0.15"),
    ]:
        session.add(CommissionPctTable(
            version=1, segment="P",
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))

    policy = Policy(
        hubspot_ticket_id="T-100",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.PROJECTED,
    )
    session.add(policy)
    session.flush()

    return ev, client, goal, policy


def test_calculate_projection_uses_medium_faixa(db_session):
    ev, client, goal, policy = _setup_ev_and_policy(db_session)

    commission = calculate_projection_for_policy(policy, quarter=1, year=2026)

    # Projection uses medium faixa (50-99.9%) = 10%
    assert commission.commission_pct == Decimal("0.10")
    # monthly = 10000 * 0.10 = 1000
    assert commission.monthly_estimated == Decimal("1000.00")
    # total = 1000 * 12 = 12000
    assert commission.total_estimated == Decimal("12000.00")
    assert commission.is_final is False
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement calculator.py**

```python
from decimal import Decimal
from app.extensions import db
from app.models import (
    Policy, Commission, Goal, CommissionPctTable,
    Appraisal, FinancialImport, Perk, Client,
)
from app.modules.commissions.achievement import calculate_achievement
from app.modules.commissions.pct_lookup import lookup_commission_pct


def get_ev_total_mrr_in_quarter(ev_id, quarter, year):
    """Sum MRR of all gongos for an EV in a quarter."""
    policies = Policy.query.filter(
        Policy.ev_id == ev_id,
        db.extract("quarter", Policy.closed_date) == quarter,
        db.extract("year", Policy.closed_date) == year,
    ).all()
    return sum(p.mrr_for_commission or Decimal("0") for p in policies)


def get_ev_goal(ev_id, quarter, year):
    """Get EV's MRR target for a quarter."""
    goal = Goal.query.filter_by(ev_id=ev_id, quarter=quarter, year=year).first()
    return goal.mrr_target if goal else Decimal("0")


def calculate_projection_for_policy(policy, quarter, year):
    """Calculate projected commission for a single policy.

    Uses the MEDIUM faixa (50-99.9%) as estimate for projection.
    """
    mrr = policy.mrr_for_commission or Decimal("0")

    # For projection, use medium faixa estimate
    commission_pct, version = lookup_commission_pct(
        policy.segment.value if policy.segment else "P",
        Decimal("0.75"),  # Middle of medium faixa
    )
    if commission_pct is None:
        commission_pct = Decimal("0")

    monthly_estimated = (mrr * commission_pct).quantize(Decimal("0.01"))
    total_estimated = (monthly_estimated * 12).quantize(Decimal("0.01"))

    # Upsert commission record
    commission = Commission.query.filter_by(
        policy_id=policy.id, quarter=quarter, year=year
    ).first()

    if commission is None:
        commission = Commission(
            policy_id=policy.id,
            ev_id=policy.ev_id,
            quarter=quarter,
            year=year,
        )
        db.session.add(commission)

    if not commission.is_final:
        commission.segment = policy.segment.value if policy.segment else None
        commission.commission_pct = commission_pct
        commission.commission_pct_version = version
        commission.monthly_estimated = monthly_estimated
        commission.total_estimated = total_estimated

    db.session.flush()
    return commission


def run_quarterly_appraisal(quarter, year):
    """Run final commission calculation for a quarter.

    1. Calculate final achievement for each EV
    2. Lookup final % from table
    3. For each policy in the quarter:
       - Calculate using FINAL %
       - Apply retroactively to ALL deals in the quarter
    4. Mark commissions as is_final=True

    Returns dict of {ev_id: {achievement, commission_pct, policies: [...]}}
    """
    results = {}

    # Get all policies gongoed in this quarter
    policies = Policy.query.filter(
        db.extract("quarter", Policy.closed_date) == quarter,
        db.extract("year", Policy.closed_date) == year,
        Policy.commission_status != "CANCELLED",
    ).all()

    # Group by EV
    ev_policies = {}
    for p in policies:
        ev_policies.setdefault(p.ev_id, []).append(p)

    for ev_id, ev_policy_list in ev_policies.items():
        # 1. Calculate achievement
        total_mrr = sum(p.mrr_for_commission or Decimal("0") for p in ev_policy_list)
        target = get_ev_goal(ev_id, quarter, year)
        achievement = calculate_achievement(total_mrr, target)

        # 2. For each policy, calculate with FINAL %
        policy_results = []
        for policy in ev_policy_list:
            segment = policy.segment.value if policy.segment else "P"
            commission_pct, version = lookup_commission_pct(segment, achievement)
            if commission_pct is None:
                commission_pct = Decimal("0")

            mrr = policy.mrr_for_commission or Decimal("0")

            # Calculate based on real NFs if available
            monthly_actual = _calculate_actual_monthly(
                policy, commission_pct, quarter, year
            )
            monthly_estimated = (mrr * commission_pct).quantize(Decimal("0.01"))
            total_estimated = (monthly_estimated * 12).quantize(Decimal("0.01"))

            # Upsert commission
            commission = Commission.query.filter_by(
                policy_id=policy.id, quarter=quarter, year=year
            ).first()
            if commission is None:
                commission = Commission(
                    policy_id=policy.id, ev_id=ev_id,
                    quarter=quarter, year=year,
                )
                db.session.add(commission)

            commission.segment = segment
            commission.achievement_pct = achievement
            commission.commission_pct = commission_pct
            commission.commission_pct_version = version
            commission.monthly_estimated = monthly_estimated
            commission.monthly_actual = monthly_actual
            commission.total_estimated = total_estimated
            commission.total_actual = (
                (monthly_actual * 12).quantize(Decimal("0.01"))
                if monthly_actual else None
            )
            commission.is_final = True

            policy_results.append({
                "policy_id": str(policy.id),
                "mrr": mrr,
                "commission_pct": commission_pct,
                "monthly_estimated": monthly_estimated,
                "monthly_actual": monthly_actual,
            })

        db.session.flush()

        results[str(ev_id)] = {
            "achievement_pct": achievement,
            "total_mrr": total_mrr,
            "target": target,
            "policies": policy_results,
        }

    return results


def _calculate_actual_monthly(policy, commission_pct, quarter, year):
    """Calculate actual monthly commission based on real NFs.

    base = SUM(NFs da empresa no tri) - perks da empresa no tri
    comissao = base * commission_pct / num_policies_empresa_no_tri
    """
    if policy.client_id is None:
        return None

    # Sum NFs for this client in the quarter
    nf_total = db.session.query(
        db.func.coalesce(db.func.sum(FinancialImport.nf_valor_liquido), Decimal("0"))
    ).join(
        Policy, FinancialImport.policy_id == Policy.id
    ).filter(
        Policy.client_id == policy.client_id,
        FinancialImport.quarter == quarter,
        FinancialImport.year == year,
    ).scalar()

    if nf_total == 0:
        return None

    # Subtract perks for this client
    perk_total = db.session.query(
        db.func.coalesce(db.func.sum(Perk.amount), Decimal("0"))
    ).filter(
        Perk.client_id == policy.client_id,
        Perk.quarter == quarter,
        Perk.year == year,
    ).scalar()

    base = nf_total - perk_total
    if base <= 0:
        return Decimal("0")

    # Divide by number of policies for this client in the quarter
    policy_count = Policy.query.filter(
        Policy.client_id == policy.client_id,
        db.extract("quarter", Policy.closed_date) == quarter,
        db.extract("year", Policy.closed_date) == year,
    ).count()
    if policy_count == 0:
        policy_count = 1

    return ((base / policy_count) * commission_pct).quantize(Decimal("0.01"))
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && pytest tests/test_modules/test_commissions/test_calculator.py -v
```

- [ ] **Step 5: Write test for full appraisal**

Add to `test_calculator.py`:

```python
def test_run_quarterly_appraisal_applies_retroactive_pct(db_session):
    ev, client, goal, policy = _setup_ev_and_policy(db_session)

    # Add a second policy for the same EV to total 20k MRR (40% of 50k target)
    policy2 = Policy(
        hubspot_ticket_id="T-101",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 2, 10),
        commission_status=CommissionStatus.PROJECTED,
    )
    db_session.add(policy2)
    db_session.flush()

    results = run_quarterly_appraisal(quarter=1, year=2026)

    ev_result = results[str(ev.id)]
    # 20k / 50k = 0.4 → faixa baixa (0-49.9%) = 6%
    assert ev_result["achievement_pct"] == Decimal("0.4000")

    # Both policies should have 6% (retroactive)
    c1 = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    c2 = Commission.query.filter_by(policy_id=policy2.id, quarter=1, year=2026).first()
    assert c1.commission_pct == Decimal("0.06")
    assert c2.commission_pct == Decimal("0.06")
    assert c1.is_final is True
    assert c2.is_final is True
```

- [ ] **Step 6: Run test — expect PASS**

- [ ] **Step 7: Commit**

```bash
git add app/modules/commissions/ tests/test_modules/test_commissions/
git commit -m "feat: add full commission calculator with projection and quarterly appraisal

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.4: Financial Import Module

**Files:**
- Create: `backend/app/modules/financial/__init__.py`
- Create: `backend/app/modules/financial/parser.py`
- Create: `backend/app/modules/financial/validator.py`
- Create: `backend/app/modules/financial/processor.py`
- Test: `backend/tests/test_modules/test_financial/`

- [ ] **Step 1: Write failing test for XLSX parser**

```python
# backend/tests/test_modules/test_financial/test_parser.py
import os
import tempfile
from openpyxl import Workbook
from app.modules.financial.parser import parse_financial_xlsx


def _create_test_xlsx():
    """Create a minimal test XLSX with NFs and Perks tabs."""
    wb = Workbook()

    # NFs tab
    ws_nf = wb.active
    ws_nf.title = "NFs"
    ws_nf.append(["hubspot_ticket_id", "client_name", "nf_valor_liquido", "nf_mes_recebimento"])
    ws_nf.append(["TICKET-1", "Acme Corp", 5000.50, "2026-01"])
    ws_nf.append(["TICKET-2", "Beta Inc", 3000.00, "2026-02"])

    # Perks tab
    ws_perks = wb.create_sheet("Perks")
    ws_perks.append(["client_name", "quarter", "year", "amount"])
    ws_perks.append(["Acme Corp", 1, 2026, 500.00])

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


def test_parse_xlsx_returns_nfs_and_perks():
    path = _create_test_xlsx()
    try:
        result = parse_financial_xlsx(path)
        assert len(result["nfs"]) == 2
        assert result["nfs"][0]["hubspot_ticket_id"] == "TICKET-1"
        assert result["nfs"][0]["nf_valor_liquido"] == 5000.50
        assert len(result["perks"]) == 1
        assert result["perks"][0]["client_name"] == "Acme Corp"
        assert result["perks"][0]["amount"] == 500.00
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement parser.py**

```python
from openpyxl import load_workbook


REQUIRED_NF_COLUMNS = ["hubspot_ticket_id", "client_name", "nf_valor_liquido", "nf_mes_recebimento"]
REQUIRED_PERK_COLUMNS = ["client_name", "quarter", "year", "amount"]


class ParseError(Exception):
    pass


def parse_financial_xlsx(filepath):
    """Parse financial XLSX file with NFs and Perks tabs.

    Returns: {"nfs": [...], "perks": [...]}
    """
    wb = load_workbook(filepath, read_only=True, data_only=True)

    nfs = _parse_sheet(wb, "NFs", REQUIRED_NF_COLUMNS)
    perks = _parse_sheet(wb, "Perks", REQUIRED_PERK_COLUMNS)

    wb.close()
    return {"nfs": nfs, "perks": perks}


def _parse_sheet(wb, sheet_name, required_columns):
    """Parse a single sheet into list of dicts."""
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    rows = list(ws.rows)
    if len(rows) < 2:
        return []

    # Header row
    headers = [cell.value.strip().lower() if cell.value else "" for cell in rows[0]]

    # Validate required columns
    for col in required_columns:
        if col not in headers:
            raise ParseError(f"Missing required column '{col}' in sheet '{sheet_name}'")

    # Parse data rows
    records = []
    for row_idx, row in enumerate(rows[1:], start=2):
        values = [cell.value for cell in row]
        record = dict(zip(headers, values))

        # Skip completely empty rows
        if all(v is None for v in values):
            continue

        record["_row"] = row_idx
        records.append(record)

    return records
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Write test for validator**

```python
# backend/tests/test_modules/test_financial/test_validator.py
from decimal import Decimal
from app.modules.financial.validator import validate_nf_rows, validate_perk_rows
from app.models import Policy, User, UserRole, Client
from app.extensions import db


def test_validate_nf_rows_valid(db_session):
    ev = User(email="ev@piposaude.com", name="EV", role=UserRole.EV)
    db_session.add(ev)
    db_session.flush()
    client = Client(name="Acme", name_normalized="acme", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    policy = Policy(hubspot_ticket_id="T-1", ev_id=ev.id, client_id=client.id)
    db_session.add(policy)
    db_session.flush()

    rows = [{"hubspot_ticket_id": "T-1", "nf_valor_liquido": 5000, "nf_mes_recebimento": "2026-01", "_row": 2}]
    valid, errors = validate_nf_rows(rows)
    assert len(valid) == 1
    assert len(errors) == 0


def test_validate_nf_rows_unknown_ticket(db_session):
    rows = [{"hubspot_ticket_id": "UNKNOWN", "nf_valor_liquido": 5000, "nf_mes_recebimento": "2026-01", "_row": 2}]
    valid, errors = validate_nf_rows(rows)
    assert len(valid) == 0
    assert len(errors) == 1
    assert "not found" in errors[0]["message"].lower()
```

- [ ] **Step 6: Implement validator.py**

```python
from decimal import Decimal, InvalidOperation
import re
from app.models import Policy, FinancialImport


def validate_nf_rows(rows):
    """Validate NF rows against database.

    Returns (valid_rows, errors).
    """
    valid = []
    errors = []

    for row in rows:
        row_num = row.get("_row", "?")
        ticket_id = row.get("hubspot_ticket_id")
        valor = row.get("nf_valor_liquido")
        mes = row.get("nf_mes_recebimento")

        # Required fields
        if not ticket_id:
            errors.append({"row": row_num, "message": "hubspot_ticket_id is required"})
            continue

        # Ticket exists?
        policy = Policy.query.filter_by(hubspot_ticket_id=str(ticket_id)).first()
        if policy is None:
            errors.append({"row": row_num, "message": f"Ticket '{ticket_id}' not found in database"})
            continue

        # Valor is numeric?
        try:
            valor = Decimal(str(valor))
            if valor <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError, TypeError):
            errors.append({"row": row_num, "message": f"Invalid nf_valor_liquido: {valor}"})
            continue

        # Mes format
        if not mes or not re.match(r"^\d{4}-\d{2}$", str(mes)):
            errors.append({"row": row_num, "message": f"Invalid nf_mes_recebimento format: {mes}. Expected YYYY-MM"})
            continue

        # Duplicate check
        existing = FinancialImport.query.filter_by(
            policy_id=policy.id, nf_mes_recebimento=str(mes)
        ).first()
        if existing:
            errors.append({"row": row_num, "message": f"NF already exists for ticket {ticket_id} month {mes}"})
            continue

        valid.append({
            "policy_id": policy.id,
            "hubspot_ticket_id": str(ticket_id),
            "nf_valor_liquido": valor,
            "nf_mes_recebimento": str(mes),
            "_row": row_num,
        })

    return valid, errors


def validate_perk_rows(rows):
    """Validate perk rows. Returns (valid_rows, errors)."""
    valid = []
    errors = []

    for row in rows:
        row_num = row.get("_row", "?")
        client_name = row.get("client_name")
        quarter = row.get("quarter")
        year = row.get("year")
        amount = row.get("amount")

        if not client_name:
            errors.append({"row": row_num, "message": "client_name is required"})
            continue

        try:
            quarter = int(quarter)
            year = int(year)
            amount = Decimal(str(amount))
            if quarter < 1 or quarter > 4:
                raise ValueError("quarter must be 1-4")
            if amount < 0:
                raise ValueError("amount must be >= 0")
        except (TypeError, ValueError) as e:
            errors.append({"row": row_num, "message": f"Invalid data: {e}"})
            continue

        valid.append({
            "client_name": str(client_name),
            "quarter": quarter,
            "year": year,
            "amount": amount,
            "_row": row_num,
        })

    return valid, errors
```

- [ ] **Step 7: Implement processor.py**

```python
from decimal import Decimal
from app.extensions import db
from app.models import (
    FinancialImport, ImportBatch, Perk, Policy, Client, CommissionStatus,
)
from app.models.client import normalize_client_name


def process_financial_import(batch_id, valid_nfs, valid_perks):
    """Process validated financial data: insert NFs, perks, update policies.

    Args:
        batch_id: UUID of the ImportBatch
        valid_nfs: List of validated NF dicts
        valid_perks: List of validated perk dicts

    Returns summary dict.
    """
    nfs_created = 0
    perks_created = 0

    # Process NFs
    for nf in valid_nfs:
        mes = nf["nf_mes_recebimento"]
        month = int(mes.split("-")[1])
        year_val = int(mes.split("-")[0])
        quarter = (month - 1) // 3 + 1

        fi = FinancialImport(
            policy_id=nf["policy_id"],
            nf_valor_liquido=nf["nf_valor_liquido"],
            nf_mes_recebimento=mes,
            quarter=quarter,
            year=year_val,
            import_batch_id=batch_id,
        )
        db.session.add(fi)
        nfs_created += 1

        # Update policy
        policy = Policy.query.get(nf["policy_id"])
        if policy:
            policy.installments_paid = (policy.installments_paid or 0) + 1

            # First payment?
            if policy.first_payment_real is None:
                from datetime import date
                policy.first_payment_real = date(year_val, month, 1)

            # Status transition
            if policy.commission_status == CommissionStatus.PROJECTED:
                policy.commission_status = CommissionStatus.IN_PAYMENT

            if policy.installments_paid >= 12:
                policy.commission_status = CommissionStatus.SETTLED

    # Process Perks
    for perk_data in valid_perks:
        client = Client.query.filter_by(
            name_normalized=normalize_client_name(perk_data["client_name"])
        ).first()

        if client:
            perk = Perk(
                client_id=client.id,
                quarter=perk_data["quarter"],
                year=perk_data["year"],
                amount=perk_data["amount"],
                import_batch_id=batch_id,
            )
            db.session.add(perk)
            perks_created += 1

    db.session.flush()

    # Update batch
    batch = ImportBatch.query.get(batch_id)
    if batch:
        batch.nf_count = nfs_created
        batch.perk_count = perks_created
        batch.status = "CONFIRMED"

    return {
        "nfs_created": nfs_created,
        "perks_created": perks_created,
    }
```

- [ ] **Step 8: Run all financial tests**

```bash
cd backend && pytest tests/test_modules/test_financial/ -v
```

- [ ] **Step 9: Commit**

```bash
git add app/modules/financial/ tests/test_modules/test_financial/
git commit -m "feat: add financial import module — XLSX parser, validator, and processor

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.5: Workflow State Machine

**Files:**
- Create: `backend/app/modules/workflow/__init__.py`
- Create: `backend/app/modules/workflow/state_machine.py`
- Create: `backend/app/modules/workflow/transitions.py`
- Create: `backend/app/modules/workflow/auto_approve.py`
- Test: `backend/tests/test_modules/test_workflow/`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_modules/test_workflow/test_state_machine.py
from datetime import date
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    InvalidTransitionError,
)
from app.models import Appraisal, AppraisalStatus, User, UserRole
from app.extensions import db


def test_start_appraisal_creates_draft(db_session):
    admin = User(email="admin@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=1, year=2026, created_by=admin.id)
    assert appraisal.status == AppraisalStatus.DRAFT
    assert appraisal.quarter == 1
    assert appraisal.year == 2026


def test_transition_draft_to_calculating(db_session):
    admin = User(email="admin2@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=1, year=2026, created_by=admin.id)
    transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    assert appraisal.status == AppraisalStatus.CALCULATING


def test_invalid_transition_raises(db_session):
    admin = User(email="admin3@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=2, year=2026, created_by=admin.id)
    try:
        # DRAFT → APPROVED is invalid
        transition_appraisal(appraisal, AppraisalStatus.APPROVED)
        assert False, "Should have raised InvalidTransitionError"
    except InvalidTransitionError:
        pass


def test_locked_appraisal_cannot_transition(db_session):
    admin = User(email="admin4@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=3, year=2026, created_by=admin.id)
    transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.REVIEWING)
    transition_appraisal(appraisal, AppraisalStatus.APPROVED)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED)

    try:
        transition_appraisal(appraisal, AppraisalStatus.DRAFT)
        assert False, "Should have raised"
    except InvalidTransitionError:
        pass
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement state_machine.py**

```python
from datetime import datetime, timezone
from app.extensions import db
from app.models import Appraisal, AppraisalStatus


class InvalidTransitionError(Exception):
    pass


# Valid transitions: from_status → [to_statuses]
VALID_TRANSITIONS = {
    AppraisalStatus.DRAFT: [AppraisalStatus.CALCULATING],
    AppraisalStatus.CALCULATING: [AppraisalStatus.VALIDATING],
    AppraisalStatus.VALIDATING: [AppraisalStatus.REVIEWING],
    AppraisalStatus.REVIEWING: [
        AppraisalStatus.APPROVED,
        AppraisalStatus.CALCULATING,  # Recalculate if needed
    ],
    AppraisalStatus.APPROVED: [
        AppraisalStatus.LOCKED,
        AppraisalStatus.REVIEWING,  # Finance returns to RevOps
    ],
    AppraisalStatus.LOCKED: [],  # Terminal state
}


def start_appraisal(quarter, year, created_by):
    """Create a new appraisal in DRAFT status."""
    existing = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if existing:
        raise InvalidTransitionError(
            f"Appraisal for Q{quarter}/{year} already exists (status: {existing.status.value})"
        )

    appraisal = Appraisal(
        quarter=quarter,
        year=year,
        status=AppraisalStatus.DRAFT,
        created_by=created_by,
    )
    db.session.add(appraisal)
    db.session.flush()
    return appraisal


def transition_appraisal(appraisal, new_status, **kwargs):
    """Transition appraisal to a new status.

    Validates the transition is allowed.
    """
    allowed = VALID_TRANSITIONS.get(appraisal.status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from {appraisal.status.value} to {new_status.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    appraisal.status = new_status

    # Side effects
    if new_status == AppraisalStatus.LOCKED:
        appraisal.locked_at = datetime.now(timezone.utc)
        appraisal.approved_by_finance = kwargs.get("approved_by")

    if new_status == AppraisalStatus.VALIDATING:
        appraisal.validation_deadline = kwargs.get("validation_deadline")

    db.session.flush()
    return appraisal
```

- [ ] **Step 4: Implement auto_approve.py**

```python
from datetime import date, datetime, timezone
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, EvValidation, ValidationStatus,
)


def auto_approve_expired_validations():
    """Auto-approve validations where deadline has passed.

    Runs as daily cron job.
    Returns count of auto-approved validations.
    """
    today = date.today()
    count = 0

    appraisals = Appraisal.query.filter(
        Appraisal.status == AppraisalStatus.VALIDATING,
        Appraisal.validation_deadline <= today,
    ).all()

    for appraisal in appraisals:
        pending = EvValidation.query.filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.status == ValidationStatus.PENDING,
        ).all()

        for validation in pending:
            validation.status = ValidationStatus.AUTO_APPROVED
            validation.resolved_at = datetime.now(timezone.utc)
            count += 1

        # If all validations are now done, advance to REVIEWING
        remaining_pending = EvValidation.query.filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.status == ValidationStatus.PENDING,
        ).count()

        if remaining_pending == 0:
            appraisal.status = AppraisalStatus.REVIEWING

    db.session.flush()
    return count
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_modules/test_workflow/ -v
```

- [ ] **Step 6: Commit**

```bash
git add app/modules/workflow/ tests/test_modules/test_workflow/
git commit -m "feat: add workflow state machine with transitions and auto-approve cron

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.6: Notification Service

**Files:**
- Create: `backend/app/modules/notifications/__init__.py`
- Create: `backend/app/modules/notifications/service.py`
- Create: `backend/app/modules/notifications/slack.py`

- [ ] **Step 1: Implement notification service**

```python
# backend/app/modules/notifications/service.py
from app.extensions import db
from app.models import Notification, User


def create_notification(user_id, type_, title, message, metadata=None):
    """Create an in-app notification."""
    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        metadata_=metadata or {},
    )
    db.session.add(notification)
    db.session.flush()
    return notification


def notify_users_by_role(role, type_, title, message, metadata=None):
    """Send notification to all users with a specific role."""
    users = User.query.filter_by(role=role, active=True).all()
    for user in users:
        create_notification(user.id, type_, title, message, metadata)
    return len(users)


def notify_ev_team(ev_ids, type_, title, message, metadata=None):
    """Send notification to a list of EV user IDs."""
    for ev_id in ev_ids:
        create_notification(ev_id, type_, title, message, metadata)
    return len(ev_ids)
```

- [ ] **Step 2: Implement Slack integration**

```python
# backend/app/modules/notifications/slack.py
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def send_slack_dm(user_slack_id, text, blocks=None):
    """Send a Slack DM to a user."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack DM")
        return False

    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        result = client.chat_postMessage(
            channel=user_slack_id,
            text=text,
            blocks=blocks,
        )
        return result["ok"]
    except Exception as e:
        logger.error(f"Slack DM failed: {e}")
        return False


def send_slack_channel(channel_id, text, blocks=None):
    """Send a message to a Slack channel."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack message")
        return False

    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        result = client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
        )
        return result["ok"]
    except Exception as e:
        logger.error(f"Slack channel message failed: {e}")
        return False


def build_appraisal_blocks(title, summary, action_url=None):
    """Build Slack blocks for appraisal notifications."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        },
    ]
    if action_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Ver na plataforma"},
                    "url": action_url,
                }
            ],
        })
    return blocks
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/notifications/
git commit -m "feat: add notification service (in-app) and Slack integration

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.7: HubSpot Sync Module

**Files:**
- Create: `backend/app/modules/hubspot_sync/__init__.py`
- Create: `backend/app/modules/hubspot_sync/client.py`
- Create: `backend/app/modules/hubspot_sync/mapper.py`
- Create: `backend/app/modules/hubspot_sync/sync.py`

- [ ] **Step 1: Implement HubSpot API client**

```python
# backend/app/modules/hubspot_sync/client.py
import time
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, token=None):
        self.token = token or current_app.config.get("HUBSPOT_TOKEN")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers["Content-Type"] = "application/json"

    def _request(self, method, path, **kwargs):
        """Make request with rate limit handling and retry."""
        url = f"{HUBSPOT_API_BASE}{path}"
        max_retries = 3

        for attempt in range(max_retries):
            response = self.session.request(method, url, **kwargs)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited, retrying after {retry_after}s")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.json()

        raise Exception(f"Max retries exceeded for {path}")

    def search_tickets(self, filters, properties, limit=100, after=None):
        """Search tickets via CRM search API."""
        body = {
            "filterGroups": [{"filters": filters}],
            "properties": properties,
            "limit": limit,
        }
        if after:
            body["after"] = after
        return self._request("POST", "/crm/v3/objects/tickets/search", json=body)

    def get_associations(self, object_type, object_id, to_type):
        """Get associations for an object."""
        return self._request(
            "GET",
            f"/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}",
        )

    def get_deal(self, deal_id, properties):
        """Get a deal by ID."""
        params = {"properties": ",".join(properties)}
        return self._request("GET", f"/crm/v3/objects/deals/{deal_id}", params=params)

    def get_ticket(self, ticket_id, properties):
        """Get a ticket by ID."""
        params = {"properties": ",".join(properties)}
        return self._request("GET", f"/crm/v3/objects/tickets/{ticket_id}", params=params)
```

- [ ] **Step 2: Implement mapper.py**

```python
# backend/app/modules/hubspot_sync/mapper.py
from datetime import date

# HubSpot property → Policy field mapping
TICKET_COTACAO_MAP = {
    "solicitante_demanda": "ev_email",
    "cotar___segmentacao_pipo": "segment_raw",
    "mrr___receita_mensal": "mrr_projected",
    "closed_date": "closed_date",
    "apolice___beneficio": "benefit_type_raw",
    "cliente___nome_da_empresa": "client_name",
}

DEAL_MAP = {
    "dealstage": "deal_stage",
    "hs_v2_date_entered_8438574": "deploy_date",
}

TICKET_IMPLANT_MAP = {
    "previsao_primeiro_pagamento": "first_payment_prev",
    "mrr_pos_implantacao": "mrr_post_deploy",
}

# Segment mapping: HubSpot text → enum value
SEGMENT_MAP = {
    "pp": "PP",
    "p": "P",
    "m": "M",
    "g": "G",
    "startup": "PP",
    "enterprise": "G",
}

BENEFIT_MAP = {
    "saude": "SAUDE",
    "saúde": "SAUDE",
    "odonto": "ODONTO",
    "odontológico": "ODONTO",
    "vida": "VIDA",
}


def map_segment(raw):
    if not raw:
        return None
    return SEGMENT_MAP.get(raw.strip().lower())


def map_benefit_type(raw):
    if not raw:
        return None
    return BENEFIT_MAP.get(raw.strip().lower())


def parse_date(raw):
    if not raw:
        return None
    try:
        if "T" in str(raw):
            return date.fromisoformat(str(raw).split("T")[0])
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def parse_decimal(raw):
    if not raw:
        return None
    try:
        from decimal import Decimal
        return Decimal(str(raw))
    except Exception:
        return None
```

- [ ] **Step 3: Implement sync.py**

```python
# backend/app/modules/hubspot_sync/sync.py
import logging
from datetime import datetime, timezone
from app.extensions import db
from app.models import User, Policy, Client
from app.models.client import normalize_client_name
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "apolice___beneficio", "cliente___nome_da_empresa",
]

DEAL_PROPERTIES = ["dealstage", "hs_v2_date_entered_8438574"]

TICKET_IMPLANT_PROPERTIES = ["previsao_primeiro_pagamento", "mrr_pos_implantacao"]


def run_sync():
    """Main sync job: pull gongoed tickets from HubSpot, upsert into policies.

    Returns summary dict.
    """
    client = HubSpotClient()
    created = 0
    updated = 0
    errors = []

    # Search gongoed tickets (won + MRR > 0)
    filters = [
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": "closed_won"},
    ]

    after = None
    while True:
        try:
            result = client.search_tickets(
                filters=filters,
                properties=TICKET_PROPERTIES,
                after=after,
            )
        except Exception as e:
            logger.error(f"HubSpot search failed: {e}")
            errors.append(f"Search failed: {e}")
            break

        for ticket in result.get("results", []):
            try:
                was_created = _process_ticket(client, ticket)
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                ticket_id = ticket.get("id", "unknown")
                logger.error(f"Error processing ticket {ticket_id}: {e}")
                errors.append(f"Ticket {ticket_id}: {e}")

        # Pagination
        paging = result.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after:
            break

    db.session.commit()

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "created": created,
        "updated": updated,
        "errors": errors,
        "error_count": len(errors),
    }
    logger.info(f"HubSpot sync completed: {summary}")
    return summary


def _process_ticket(hs_client, ticket):
    """Process a single HubSpot ticket into a policy. Returns True if created."""
    props = ticket.get("properties", {})
    ticket_id = ticket["id"]

    # Map EV by email
    ev_email = props.get("solicitante_demanda", "")
    ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    # Upsert client
    client_name = props.get("cliente___nome_da_empresa", "")
    client_obj = None
    if client_name:
        client_obj = Client.find_or_create(client_name, ev_id=ev.id if ev else None)
        db.session.flush()

    # Find or create policy
    policy = Policy.query.filter_by(hubspot_ticket_id=str(ticket_id)).first()
    is_new = policy is None
    if is_new:
        policy = Policy(hubspot_ticket_id=str(ticket_id))
        db.session.add(policy)

    # Update fields
    if ev:
        policy.ev_id = ev.id
    if client_obj:
        policy.client_id = client_obj.id
    policy.segment = map_segment(props.get("cotar___segmentacao_pipo"))
    policy.benefit_type = map_benefit_type(props.get("apolice___beneficio"))
    policy.mrr_projected = parse_decimal(props.get("mrr___receita_mensal"))
    policy.closed_date = parse_date(props.get("closed_date"))

    # Fetch deal associations
    try:
        assoc = hs_client.get_associations("tickets", ticket_id, "deals")
        deal_ids = [r["toObjectId"] for r in assoc.get("results", [])]
        if deal_ids:
            policy.deal_id = str(deal_ids[0])
            deal = hs_client.get_deal(deal_ids[0], DEAL_PROPERTIES)
            deal_props = deal.get("properties", {})
            policy.deal_stage = deal_props.get("dealstage")
            policy.deploy_date = parse_date(deal_props.get("hs_v2_date_entered_8438574"))
    except Exception as e:
        logger.warning(f"Deal association fetch failed for ticket {ticket_id}: {e}")

    db.session.flush()
    return is_new
```

- [ ] **Step 4: Commit**

```bash
git add app/modules/hubspot_sync/
git commit -m "feat: add HubSpot sync module — API client, field mapper, and sync orchestration

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 4: API Endpoints

### Task 4.1: Audit Log Middleware

**Files:**
- Create: `backend/app/api/middlewares.py`

- [ ] **Step 1: Implement audit log helper**

```python
# backend/app/api/middlewares.py
from flask import g
from app.extensions import db
from app.models import AuditLog


def log_audit(table_name, record_id, action, old_values=None, new_values=None):
    """Log an audit entry for data changes."""
    user_id = getattr(g, "current_user", None)
    if user_id and hasattr(user_id, "id"):
        user_id = user_id.id

    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_values=old_values,
        new_values=new_values,
        user_id=user_id,
    )
    db.session.add(entry)


def paginate_query(query, page, per_page, max_per_page=100):
    """Apply pagination to a SQLAlchemy query.

    Returns (items, meta_dict).
    """
    per_page = min(per_page, max_per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
    }
```

- [ ] **Step 2: Commit**

```bash
git add app/api/middlewares.py
git commit -m "feat: add audit log helper and pagination utility

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 4.2: Policies API

**Files:**
- Create: `backend/app/api/v1/policies.py`
- Test: `backend/tests/test_api/test_policies.py`

- [ ] **Step 1: Implement policies endpoint**

```python
# backend/app/api/v1/policies.py
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import Policy, UserRole
from app.api.middlewares import paginate_query

policies_bp = Blueprint("policies", __name__, url_prefix="/api/v1/policies")


@policies_bp.route("")
@require_auth
def list_policies():
    """List policies with role-based filtering."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Policy.query

    # Role-based filtering
    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(Policy.ev_id == user.id)
    elif user.role == UserRole.GERENTE:
        from app.models import User
        team_member_ids = [
            u.id for u in User.query.filter_by(team_id=user.team_id, active=True).all()
        ]
        query = query.filter(Policy.ev_id.in_(team_member_ids))
    # ADMIN and FINANCE see all

    # Optional filters
    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(Policy.ev_id == ev_id)

    client_id = request.args.get("client_id")
    if client_id:
        query = query.filter(Policy.client_id == client_id)

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if quarter and year:
        from sqlalchemy import extract
        query = query.filter(
            extract("quarter", Policy.closed_date) == quarter,
            extract("year", Policy.closed_date) == year,
        )

    status = request.args.get("status")
    if status:
        query = query.filter(Policy.commission_status == status)

    query = query.order_by(Policy.closed_date.desc())
    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_policy(p) for p in items],
        "meta": meta,
    })


@policies_bp.route("/<policy_id>")
@require_auth
def get_policy(policy_id):
    """Get a single policy detail."""
    user = g.current_user
    policy = Policy.query.get_or_404(policy_id)

    # Access control
    if user.role in (UserRole.EV, UserRole.CN) and policy.ev_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    return jsonify({"data": _serialize_policy(policy, detail=True)})


def _serialize_policy(policy, detail=False):
    data = {
        "id": str(policy.id),
        "hubspot_ticket_id": policy.hubspot_ticket_id,
        "ev_id": str(policy.ev_id) if policy.ev_id else None,
        "client_id": str(policy.client_id) if policy.client_id else None,
        "client_name": policy.client.name if policy.client else None,
        "benefit_type": policy.benefit_type.value if policy.benefit_type else None,
        "segment": policy.segment.value if policy.segment else None,
        "mrr_projected": str(policy.mrr_projected) if policy.mrr_projected else None,
        "mrr_for_commission": str(policy.mrr_for_commission) if policy.mrr_for_commission else None,
        "closed_date": policy.closed_date.isoformat() if policy.closed_date else None,
        "installments_paid": policy.installments_paid,
        "commission_status": policy.commission_status.value,
    }
    if detail:
        data.update({
            "deal_id": policy.deal_id,
            "headcount": policy.headcount,
            "mrr_post_deploy": str(policy.mrr_post_deploy) if policy.mrr_post_deploy else None,
            "mrr_actual": str(policy.mrr_actual) if policy.mrr_actual else None,
            "deploy_date": policy.deploy_date.isoformat() if policy.deploy_date else None,
            "first_payment_prev": policy.first_payment_prev.isoformat() if policy.first_payment_prev else None,
            "first_payment_real": policy.first_payment_real.isoformat() if policy.first_payment_real else None,
            "partner_operator": policy.partner_operator,
            "deal_stage": policy.deal_stage,
        })
    return data
```

- [ ] **Step 2: Register blueprint**

Add to `app/api/__init__.py`:

```python
    from app.api.v1.policies import policies_bp
    app.register_blueprint(policies_bp)
```

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/policies.py app/api/__init__.py
git commit -m "feat: add policies API with role-based filtering and pagination

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 4.3: Commissions API

**Files:**
- Create: `backend/app/api/v1/commissions.py`

- [ ] **Step 1: Implement commissions endpoints**

```python
# backend/app/api/v1/commissions.py
from decimal import Decimal
from flask import Blueprint, jsonify, request, g
from sqlalchemy import func
from app.auth.decorators import require_auth
from app.models import Commission, Policy, Goal, UserRole
from app.api.middlewares import paginate_query
from app.extensions import db

commissions_bp = Blueprint("commissions", __name__, url_prefix="/api/v1/commissions")


@commissions_bp.route("")
@require_auth
def list_commissions():
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Commission.query

    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(Commission.ev_id == user.id)

    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(Commission.ev_id == ev_id)

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if quarter:
        query = query.filter(Commission.quarter == quarter)
    if year:
        query = query.filter(Commission.year == year)

    is_final = request.args.get("is_final")
    if is_final is not None:
        query = query.filter(Commission.is_final == (is_final.lower() == "true"))

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_commission(c) for c in items],
        "meta": meta,
    })


@commissions_bp.route("/summary")
@require_auth
def commission_summary():
    """Summary: saldo a receber, atingimento, projeção."""
    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    # Total estimated balance (non-settled)
    balance = db.session.query(
        func.coalesce(func.sum(Commission.total_estimated), 0)
    ).filter(
        Commission.ev_id == ev_id,
        Commission.is_final == False,
    ).scalar()

    # Current quarter achievement
    from datetime import date
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1
    current_year = today.year

    goal = Goal.query.filter_by(
        ev_id=ev_id, quarter=current_quarter, year=current_year
    ).first()

    quarter_mrr = db.session.query(
        func.coalesce(func.sum(Policy.mrr_projected), 0)
    ).filter(
        Policy.ev_id == ev_id,
        db.extract("quarter", Policy.closed_date) == current_quarter,
        db.extract("year", Policy.closed_date) == current_year,
    ).scalar()

    target = goal.mrr_target if goal else Decimal("0")
    achievement = (quarter_mrr / target * 100) if target > 0 else Decimal("0")

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


@commissions_bp.route("/projection")
@require_auth
def commission_projection():
    """12-month projection of estimated receivables."""
    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    commissions = Commission.query.filter(
        Commission.ev_id == ev_id,
        Commission.is_final == False,
    ).all()

    # Build monthly projection (simplified: spread evenly over remaining months)
    from datetime import date
    today = date.today()
    months = []
    for i in range(12):
        month = today.month + i
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        total = sum(
            c.monthly_estimated or Decimal("0")
            for c in commissions
        )
        months.append({
            "month": f"{year}-{month:02d}",
            "projected": str(total),
        })

    return jsonify({"data": months})


def _serialize_commission(c):
    return {
        "id": str(c.id),
        "policy_id": str(c.policy_id),
        "ev_id": str(c.ev_id),
        "quarter": c.quarter,
        "year": c.year,
        "segment": c.segment,
        "achievement_pct": str(c.achievement_pct) if c.achievement_pct else None,
        "commission_pct": str(c.commission_pct) if c.commission_pct else None,
        "monthly_estimated": str(c.monthly_estimated) if c.monthly_estimated else None,
        "monthly_actual": str(c.monthly_actual) if c.monthly_actual else None,
        "total_estimated": str(c.total_estimated) if c.total_estimated else None,
        "total_actual": str(c.total_actual) if c.total_actual else None,
        "is_final": c.is_final,
    }
```

- [ ] **Step 2: Register blueprint and commit**

```bash
git add app/api/v1/commissions.py app/api/__init__.py
git commit -m "feat: add commissions API with summary and 12-month projection

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 4.4: Goals, Financial, Workflow, Validations, Finance, Admin, Notifications APIs

These follow the exact same pattern. I'll list the key endpoints for each — the implementation follows the patterns from policies.py and commissions.py.

**Files to create:**
- `backend/app/api/v1/goals.py` — GET /goals, POST /goals, POST /goals/import
- `backend/app/api/v1/financial.py` — POST /financial/upload, POST /financial/confirm/:batch_id, GET /financial/history, GET /financial/template
- `backend/app/api/v1/workflow.py` — POST /appraisals, POST /appraisals/:id/calculate, POST /appraisals/:id/release, POST /appraisals/:id/send-to-finance, POST /appraisals/:id/approve-payment, POST /appraisals/:id/return, GET /appraisals/:id
- `backend/app/api/v1/validations.py` — GET /validations, POST /validations/:id/approve, POST /validations/:id/contest, POST /validations/:id/resolve
- `backend/app/api/v1/finance_dashboard.py` — GET /finance/dashboard, GET /finance/export
- `backend/app/api/v1/admin.py` — (expand existing) CRUD users, teams, commission-table, settings, sync-status, audit-log
- `backend/app/api/v1/notifications.py` — GET /notifications, POST /notifications/:id/read, POST /notifications/read-all

Each endpoint will:
1. Use `@require_auth` or `@require_role(...)` decorator
2. Use `paginate_query` for list endpoints
3. Use `log_audit` for any CREATE/UPDATE/DELETE
4. Follow the standard response format `{"data": ..., "meta": ...}`
5. Check immutability (no changes to LOCKED appraisal data)

- [ ] **Step 1: Implement all remaining API files** (one commit per file)

- [ ] **Step 2: Register all blueprints in app/api/__init__.py**

- [ ] **Step 3: Run full test suite**

```bash
cd backend && pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add app/api/ tests/test_api/
git commit -m "feat: add all remaining API endpoints — goals, financial, workflow, validations, finance, admin, notifications

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 5: Docker + CI/CD + Infra

### Task 5.1: Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: add backend Dockerfile with gunicorn

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 5.2: Helm Values

**Files:**
- Create: `.k8s/helm/stag/values.yaml`
- Create: `.k8s/helm/prod/values.yaml`

- [ ] **Step 1: Create staging values**

```yaml
# .k8s/helm/stag/values.yaml
replicaCount: 1

image:
  repository: <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/plataforma-comissoes-backend
  tag: latest

resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"

nodeToRun: pipo-core-arm64

env:
  FLASK_ENV: stag

secrets:
  DATABASE_URL: STAG_DATABASE_URL
  GOOGLE_CLIENT_ID: GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET: GOOGLE_CLIENT_SECRET
  HUBSPOT_TOKEN: STAG_HUBSPOT_TOKEN
  SLACK_BOT_TOKEN: SLACK_BOT_TOKEN
  SECRET_KEY: STAG_SECRET_KEY

ingress:
  enabled: true
  host: comissoes-stag.piposaude.com
  tls: true

livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /ready
    port: 8000

tags:
  Squad: RevOps
  Domain: Comissoes
  Environment: stag
  Service: plataforma-comissoes
```

- [ ] **Step 2: Create prod values** (similar but with 2 replicas, t3.small, etc.)

- [ ] **Step 3: Commit**

```bash
git add .k8s/
git commit -m "feat: add Helm values for stag and prod environments

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 5.3: Terraform

**Files:**
- Create: `.tf/global/ecr.tf`
- Create: `.tf/stag/rds.tf`
- Create: `.tf/prod/rds.tf`

- [ ] **Step 1: Create ECR repos**

```hcl
# .tf/global/ecr.tf
resource "aws_ecr_repository" "backend" {
  name                 = "plataforma-comissoes-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Squad       = "RevOps"
    Domain      = "Comissoes"
    Service     = "plataforma-comissoes"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "plataforma-comissoes-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Squad       = "RevOps"
    Domain      = "Comissoes"
    Service     = "plataforma-comissoes"
  }
}
```

- [ ] **Step 2: Create RDS staging**

```hcl
# .tf/stag/rds.tf
resource "aws_db_instance" "comissoes_stag" {
  identifier     = "comissoes-stag"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 50

  db_name  = "comissoes_stag"
  username = "comissoes_admin"
  password = var.db_password

  multi_az               = false
  backup_retention_period = 7
  skip_final_snapshot     = true

  tags = {
    Squad       = "RevOps"
    Domain      = "Comissoes"
    Environment = "stag"
  }
}
```

- [ ] **Step 3: Create RDS prod** (similar but t3.small, multi_az=true, 30 day backups)

- [ ] **Step 4: Commit**

```bash
git add .tf/
git commit -m "feat: add Terraform for ECR repos and RDS instances (stag + prod)

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 5.4: GitLab CI

**Files:**
- Create: `.gitlab-ci.yml`

- [ ] **Step 1: Create CI pipeline**

```yaml
# .gitlab-ci.yml
stages:
  - test
  - lint
  - build
  - push
  - deploy-stag
  - deploy-prod

variables:
  DOCKER_IMAGE_BACKEND: $CI_REGISTRY_IMAGE/backend
  DOCKER_IMAGE_FRONTEND: $CI_REGISTRY_IMAGE/frontend

# --- Backend ---
test-backend:
  stage: test
  image: python:3.12-slim
  services:
    - postgres:16
  variables:
    POSTGRES_DB: comissoes_test
    POSTGRES_USER: test
    POSTGRES_PASSWORD: test
    TEST_DATABASE_URL: postgresql://test:test@postgres:5432/comissoes_test
  script:
    - cd backend
    - pip install -r requirements-dev.txt
    - pytest tests/ -v --tb=short --junitxml=report.xml
  artifacts:
    reports:
      junit: backend/report.xml

lint-backend:
  stage: lint
  image: python:3.12-slim
  script:
    - cd backend
    - pip install flake8 black
    - flake8 app/ tests/
    - black --check app/ tests/

build-backend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - cd backend
    - docker build -t $DOCKER_IMAGE_BACKEND:$CI_COMMIT_SHA .
    - docker tag $DOCKER_IMAGE_BACKEND:$CI_COMMIT_SHA $DOCKER_IMAGE_BACKEND:latest
  only:
    - main

push-backend:
  stage: push
  image: docker:24
  services:
    - docker:24-dind
  script:
    - aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY
    - docker push $DOCKER_IMAGE_BACKEND:$CI_COMMIT_SHA
    - docker push $DOCKER_IMAGE_BACKEND:latest
  only:
    - main

deploy-stag:
  stage: deploy-stag
  image: alpine/helm:3.14
  script:
    - helm upgrade --install plataforma-comissoes-backend
      pipoengineering/platform/charts/microservice
      -f .k8s/helm/stag/values.yaml
      --set image.tag=$CI_COMMIT_SHA
      --namespace default
  environment:
    name: staging
    url: https://comissoes-stag.piposaude.com
  only:
    - main

deploy-prod:
  stage: deploy-prod
  image: alpine/helm:3.14
  script:
    - helm upgrade --install plataforma-comissoes-backend
      pipoengineering/platform/charts/microservice
      -f .k8s/helm/prod/values.yaml
      --set image.tag=$CI_COMMIT_SHA
      --namespace default
  environment:
    name: production
    url: https://comissoes.piposaude.com
  when: manual
  only:
    - main
```

- [ ] **Step 2: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "feat: add GitLab CI pipeline — test, lint, build, push, deploy

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-03-27-plataforma-comissoes-backend.md`. Ready to execute?**

O plano do **frontend ClojureScript** será o próximo documento separado. Este plano backend tem **5 chunks, ~25 tasks, ~100+ steps**.

Quer que eu:
1. **Execute este plano agora** (backend primeiro, depois frontend)?
2. **Escreva o plano do frontend primeiro** antes de começar a implementar?
3. **Ajuste algo** no plano antes de executar?