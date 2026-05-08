"""Transition tests for CnMonthlyAppraisal (issue #34)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    AppraisalStatus, CnMonthlyAppraisal, User, UserRole,
)
from app.modules.workflow.state_machine import (
    transition_cn_monthly_appraisal,
    InvalidTransitionError,
)


def _make_cn_appraisal(month=1, year=2031, status=AppraisalStatus.DRAFT):
    suffix = uuid.uuid4().hex[:8]
    cn = User(
        email=f"sm-cn-{suffix}@x", name="SM CN",
        role=UserRole.CN, active=True, salario_base=Decimal("8000"),
    )
    db.session.add(cn)
    db.session.flush()

    a = CnMonthlyAppraisal(
        cn_id=cn.id, month=month, year=year,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("0"), multiplicador=Decimal("0"),
        commission_amount=Decimal("0"),
        status=status,
    )
    db.session.add(a)
    db.session.flush()
    return a


def test_full_chain_draft_to_locked(db_session):
    a = _make_cn_appraisal(month=1, year=2031)
    transition_cn_monthly_appraisal(a, AppraisalStatus.CALCULATING)
    assert a.status == AppraisalStatus.CALCULATING
    transition_cn_monthly_appraisal(a, AppraisalStatus.VALIDATING)
    transition_cn_monthly_appraisal(a, AppraisalStatus.LIDER_REVIEW)
    transition_cn_monthly_appraisal(a, AppraisalStatus.REVOPS_REVIEW)
    transition_cn_monthly_appraisal(a, AppraisalStatus.LOCKED)
    assert a.is_final is True


def test_invalid_skip_raises(db_session):
    a = _make_cn_appraisal(month=2, year=2031)
    with pytest.raises(InvalidTransitionError):
        transition_cn_monthly_appraisal(a, AppraisalStatus.LOCKED)


def test_lider_review_can_send_back_to_calculating(db_session):
    a = _make_cn_appraisal(month=3, year=2031, status=AppraisalStatus.LIDER_REVIEW)
    transition_cn_monthly_appraisal(a, AppraisalStatus.CALCULATING)
    assert a.status == AppraisalStatus.CALCULATING


def test_revops_review_can_send_back_to_calculating(db_session):
    a = _make_cn_appraisal(month=4, year=2031, status=AppraisalStatus.REVOPS_REVIEW)
    transition_cn_monthly_appraisal(a, AppraisalStatus.CALCULATING)
    assert a.status == AppraisalStatus.CALCULATING


def test_locked_can_reopen_to_revops_review(db_session):
    a = _make_cn_appraisal(month=5, year=2031, status=AppraisalStatus.LOCKED)
    transition_cn_monthly_appraisal(a, AppraisalStatus.REVOPS_REVIEW)
    assert a.status == AppraisalStatus.REVOPS_REVIEW
    assert a.is_final is False


def test_is_final_property_tracks_status(db_session):
    a = _make_cn_appraisal(month=6, year=2031)
    assert a.is_final is False
    a.status = AppraisalStatus.LOCKED
    db.session.flush()
    assert a.is_final is True
