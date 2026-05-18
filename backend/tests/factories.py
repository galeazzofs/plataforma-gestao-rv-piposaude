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
    name = factory.Sequence(lambda n: f"Time P/M {n}")


class UserFactory(BaseFactory):
    class Meta:
        model = User
    email = factory.Sequence(lambda n: f"user{n}@piposaude.com")
    name = factory.Sequence(lambda n: f"Usuario {n}")
    role = UserRole.EV
    active = True


class ClientFactory(BaseFactory):
    class Meta:
        model = Client
    name = factory.Sequence(lambda n: f"Empresa {n} Ltda")
    name_normalized = factory.LazyAttribute(lambda o: o.name.strip().lower())


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
