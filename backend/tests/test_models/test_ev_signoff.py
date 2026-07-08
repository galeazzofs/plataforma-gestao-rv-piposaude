"""EvSignoff model: shape + unique constraint."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appraisal, AppraisalStatus, EvSignoff, SignoffStatus, User, UserRole


def _mk_appraisal_and_ev(suffix):
    admin = User(email=f"sig-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"sig-ev-{suffix}@x", name="EV Sig",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()
    appraisal = Appraisal(month=9, year=2026,
                          status=AppraisalStatus.CALCULATING,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()
    return appraisal, ev


def test_ev_signoff_defaults(db_session):
    appraisal, ev = _mk_appraisal_and_ev(uuid.uuid4().hex[:8])
    row = EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id)
    db.session.add(row)
    db.session.flush()

    assert row.status == SignoffStatus.PENDING
    assert row.values_changed is False
    assert row.fingerprint is None
    assert row.signed_off_by is None
    assert row.signed_off_at is None
    assert row.appraisal.id == appraisal.id
    assert row.ev.id == ev.id


def test_ev_signoff_unique_per_appraisal_ev(db_session):
    appraisal, ev = _mk_appraisal_and_ev(uuid.uuid4().hex[:8])
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id))
    db.session.flush()
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_ev_signoff_unique_scoped_to_pair(db_session):
    """Só o PAR (apuração, EV) é único: mesmo EV noutra apuração e
    outro EV na mesma apuração inserem sem conflito."""
    suffix = uuid.uuid4().hex[:8]
    appraisal, ev = _mk_appraisal_and_ev(suffix)
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=ev.id))
    db.session.flush()

    other_appraisal = Appraisal(month=10, year=2026,
                                status=AppraisalStatus.CALCULATING,
                                created_by=appraisal.created_by)
    other_ev = User(email=f"sig-ev2-{suffix}@x", name="EV Sig 2",
                    role=UserRole.EV, active=True)
    db.session.add_all([other_appraisal, other_ev])
    db.session.flush()

    # mesmo EV, outra apuração
    db.session.add(EvSignoff(appraisal_id=other_appraisal.id, ev_id=ev.id))
    db.session.flush()
    # mesma apuração, outro EV
    db.session.add(EvSignoff(appraisal_id=appraisal.id, ev_id=other_ev.id))
    db.session.flush()

    assert db.session.query(EvSignoff).filter(
        EvSignoff.ev_id.in_([ev.id, other_ev.id])
    ).count() == 3
