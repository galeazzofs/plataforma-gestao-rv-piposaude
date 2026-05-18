"""Tests for the auto-advance + Slack wiring behaviour added on top of
issues #37a and #38: VALIDATING → LIDER_REVIEW fires when 100% of the
team has validated AND every Líder has validated own; the CALCULATING →
VALIDATING transition DMs each EV; LIDER_REVIEW → REVOPS_REVIEW posts to
ops; REVOPS_REVIEW → LOCKED posts to finance."""
from decimal import Decimal
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, EvValidation, LiderVendasQuarterAppraisal,
    Policy, Client, Segment, BenefitType,
    Team, User, UserRole, ValidationStatus,
)
from app.modules.workflow.state_machine import (
    transition_appraisal, transition_cn_monthly_appraisal,
    transition_lider_vendas_appraisal,
    maybe_auto_advance_appraisal_after_validation,
    InvalidTransitionError,
)


@pytest.fixture(autouse=True)
def slack_config(app):
    """Make Slack senders runnable in tests."""
    app.config["SLACK_BOT_TOKEN"] = "xoxb-test"
    app.config["SLACK_OPS_CHANNEL"] = "#ops"
    app.config["SLACK_FINANCE_CHANNEL"] = "#finance"
    app.config["PLATFORM_PUBLIC_URL"] = "https://platform.example.com"
    yield
    app.config["SLACK_BOT_TOKEN"] = ""
    app.config["SLACK_OPS_CHANNEL"] = ""
    app.config["SLACK_FINANCE_CHANNEL"] = ""


def _user(role, name, team_id=None, slack_id="U-X"):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower()}-{suffix}@x", name=name, role=role,
        active=True, salario_base=Decimal("8000"),
        team_id=team_id, slack_user_id=slack_id,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _team(name, leader):
    t = Team(name=name, leader_id=leader.id)
    db.session.add(t)
    db.session.flush()
    leader.team_id = t.id
    db.session.flush()
    return t


def _appraisal(quarter, year, status, admin):
    a = Appraisal(
        quarter=quarter, year=year, status=status,
        created_by=admin.id,
    )
    db.session.add(a)
    db.session.flush()
    return a


def _ev_validation(appraisal, ev, status=ValidationStatus.PENDING):
    suffix = uuid.uuid4().hex[:6]
    client = Client.find_or_create(f"AC-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_apolice_id=f"AP-{suffix}",
        hubspot_ticket_id=f"T-{suffix}",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
    )
    db.session.add(policy)
    db.session.flush()
    v = EvValidation(
        appraisal_id=appraisal.id, policy_id=policy.id,
        ev_id=ev.id, status=status,
    )
    db.session.add(v)
    db.session.flush()
    return v


def _lider_appraisal(lider, quarter, year, status):
    a = LiderVendasQuarterAppraisal(
        lider_vendas_id=lider.id, quarter=quarter, year=year,
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("1.0"), bonus_amount=Decimal("8000"),
        status=status,
    )
    db.session.add(a)
    db.session.flush()
    return a


# ── Slack wiring (issue #38) ──────────────────────────────────────────


def test_calc_to_validating_dms_each_ev(db_session):
    admin = _user(UserRole.ADMIN, "AdminS")
    ev = _user(UserRole.EV, "EvS")
    appraisal = _appraisal(1, 2040, AppraisalStatus.CALCULATING, admin)
    _ev_validation(appraisal, ev)

    mock = MagicMock(return_value={"ok": True})
    with patch("slack_sdk.WebClient.chat_postMessage", mock):
        transition_appraisal(appraisal, AppraisalStatus.VALIDATING)

    assert mock.called
    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    assert ev.slack_user_id in channels


def test_calc_to_validating_auto_approves_departed_ev_without_dm(db_session):
    admin = _user(UserRole.ADMIN, "AdminDeparted")
    ev = _user(UserRole.EV, "EvDeparted")
    ev.left_company = True
    ev.active = False
    appraisal = _appraisal(1, 2042, AppraisalStatus.CALCULATING, admin)
    validation = _ev_validation(appraisal, ev)

    mock = MagicMock(return_value={"ok": True})
    with patch("slack_sdk.WebClient.chat_postMessage", mock):
        transition_appraisal(appraisal, AppraisalStatus.VALIDATING)

    assert validation.status == ValidationStatus.AUTO_APPROVED
    assert validation.resolution_comment == (
        "Autoaprovado: EV saiu da empresa; aprovacao fica com RevOps."
    )
    assert not mock.called


def test_lider_review_to_revops_review_posts_ops(db_session):
    admin = _user(UserRole.ADMIN, "AdminL")
    appraisal = _appraisal(2, 2040, AppraisalStatus.LIDER_REVIEW, admin)

    mock = MagicMock(return_value={"ok": True})
    with patch("slack_sdk.WebClient.chat_postMessage", mock):
        transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)

    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    assert "#ops" in channels


def test_revops_review_to_locked_posts_finance(db_session):
    admin = _user(UserRole.ADMIN, "AdminF")
    appraisal = _appraisal(3, 2040, AppraisalStatus.REVOPS_REVIEW, admin)

    mock = MagicMock(return_value={"ok": True})
    with patch("slack_sdk.WebClient.chat_postMessage", mock):
        transition_appraisal(
            appraisal, AppraisalStatus.LOCKED, approved_by=admin.id,
        )

    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    assert "#finance" in channels


def test_slack_failure_does_not_block_transition(db_session):
    admin = _user(UserRole.ADMIN, "AdminFB")
    appraisal = _appraisal(4, 2040, AppraisalStatus.LIDER_REVIEW, admin)

    bad = MagicMock(side_effect=RuntimeError("slack down"))
    with patch("slack_sdk.WebClient.chat_postMessage", bad):
        transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)

    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW


# ── Contestation guards on CN/Líder (issue #36) ───────────────────────


def test_cn_monthly_blocks_lider_review_with_contestation(db_session):
    from app.models import CnMonthlyAppraisal
    cn = _user(UserRole.CN, "CnG")
    a = CnMonthlyAppraisal(
        cn_id=cn.id, month=4, year=2040,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("0"), multiplicador=Decimal("0"),
        commission_amount=Decimal("0"),
        status=AppraisalStatus.VALIDATING,
        has_contestation=True,
    )
    db.session.add(a)
    db.session.flush()

    with pytest.raises(InvalidTransitionError):
        transition_cn_monthly_appraisal(a, AppraisalStatus.LIDER_REVIEW)


def test_lider_blocks_lider_review_with_contestation(db_session):
    lider = _user(UserRole.LIDER_VENDAS, "LdrG")
    a = _lider_appraisal(lider, 1, 2040, AppraisalStatus.VALIDATING)
    a.has_contestation = True
    db.session.flush()

    with pytest.raises(InvalidTransitionError):
        transition_lider_vendas_appraisal(a, AppraisalStatus.LIDER_REVIEW)


# ── Auto-advance trigger (issue #37a) ─────────────────────────────────


def test_auto_advance_skips_when_validations_pending(db_session):
    admin = _user(UserRole.ADMIN, "AdminA")
    ev = _user(UserRole.EV, "EvA")
    appraisal = _appraisal(1, 2041, AppraisalStatus.VALIDATING, admin)
    _ev_validation(appraisal, ev, ValidationStatus.PENDING)

    advanced = maybe_auto_advance_appraisal_after_validation(appraisal)

    assert advanced is False
    assert appraisal.status == AppraisalStatus.VALIDATING


def test_auto_advance_skips_when_lider_has_not_validated_own(db_session):
    admin = _user(UserRole.ADMIN, "AdminB")
    lider = _user(UserRole.LIDER_VENDAS, "LdrB")
    _team("TeamB", lider)
    ev = _user(UserRole.EV, "EvB", team_id=lider.team_id)
    appraisal = _appraisal(2, 2041, AppraisalStatus.VALIDATING, admin)
    _ev_validation(appraisal, ev, ValidationStatus.APPROVED)
    # Líder still in VALIDATING for own row.
    _lider_appraisal(lider, 2, 2041, AppraisalStatus.VALIDATING)

    advanced = maybe_auto_advance_appraisal_after_validation(appraisal)

    assert advanced is False
    assert appraisal.status == AppraisalStatus.VALIDATING


def test_auto_advance_fires_when_team_done_and_lider_validated_own(db_session):
    admin = _user(UserRole.ADMIN, "AdminC")
    lider = _user(UserRole.LIDER_VENDAS, "LdrC")
    _team("TeamC", lider)
    ev = _user(UserRole.EV, "EvC", team_id=lider.team_id)
    appraisal = _appraisal(3, 2041, AppraisalStatus.VALIDATING, admin)
    _ev_validation(appraisal, ev, ValidationStatus.APPROVED)
    _lider_appraisal(lider, 3, 2041, AppraisalStatus.LIDER_REVIEW)

    mock = MagicMock(return_value={"ok": True})
    with patch("slack_sdk.WebClient.chat_postMessage", mock):
        advanced = maybe_auto_advance_appraisal_after_validation(appraisal)

    assert advanced is True
    assert appraisal.status == AppraisalStatus.LIDER_REVIEW


def test_current_ev_cannot_skip_lider_review_when_team_has_leader(db_session):
    admin = _user(UserRole.ADMIN, "AdminSkip")
    lider = _user(UserRole.LIDER_VENDAS, "LdrSkip")
    _team("TeamSkip", lider)
    ev = _user(UserRole.EV, "EvSkip", team_id=lider.team_id)
    appraisal = _appraisal(2, 2043, AppraisalStatus.VALIDATING, admin)
    _ev_validation(appraisal, ev, ValidationStatus.APPROVED)

    with pytest.raises(InvalidTransitionError):
        transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)


def test_auto_advance_departed_ev_only_goes_to_revops_review(db_session):
    admin = _user(UserRole.ADMIN, "AdminE")
    ev = _user(UserRole.EV, "EvE")
    ev.left_company = True
    appraisal = _appraisal(1, 2043, AppraisalStatus.VALIDATING, admin)
    _ev_validation(appraisal, ev, ValidationStatus.AUTO_APPROVED)

    advanced = maybe_auto_advance_appraisal_after_validation(appraisal)

    assert advanced is True
    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW


def test_auto_advance_blocked_by_open_contestation(db_session):
    admin = _user(UserRole.ADMIN, "AdminD")
    lider = _user(UserRole.LIDER_VENDAS, "LdrD")
    _team("TeamD", lider)
    ev = _user(UserRole.EV, "EvD", team_id=lider.team_id)
    appraisal = _appraisal(4, 2041, AppraisalStatus.VALIDATING, admin)
    appraisal.has_contestation = True
    _ev_validation(appraisal, ev, ValidationStatus.APPROVED)
    _lider_appraisal(lider, 4, 2041, AppraisalStatus.LIDER_REVIEW)

    advanced = maybe_auto_advance_appraisal_after_validation(appraisal)

    assert advanced is False
    assert appraisal.status == AppraisalStatus.VALIDATING
