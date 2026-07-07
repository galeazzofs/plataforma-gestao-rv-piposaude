"""Signoff service: scope, fingerprint, ensure, refresh, pending, totals."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, Commission,
    EvSignoff, Policy, Segment, SignoffStatus, User, UserRole,
)
from app.modules.workflow.signoffs import (
    compute_ev_fingerprint,
    ensure_signoffs,
    pending_signoff_evs,
    refresh_signoffs_after_recalc,
    signoff_scope_ev_ids,
    signoff_totals,
)


def _mk_users(suffix):
    admin = User(email=f"sos-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev_active = User(email=f"sos-ev1-{suffix}@x", name=f"Ativa {suffix}",
                     role=UserRole.EV, active=True)
    ev_inactive = User(email=f"sos-ev2-{suffix}@x", name=f"Inativa {suffix}",
                       role=UserRole.EV, active=False, left_company=True)
    db.session.add_all([admin, ev_active, ev_inactive])
    db.session.flush()
    return admin, ev_active, ev_inactive


def _mk_commission(ev, suffix, total="80.00", month=9, year=2026):
    client = Client.find_or_create(f"SosClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"SOS-{suffix}",
        numero_apolice=f"AP-SOS-{suffix}",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Amil", closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.flush()
    comm = Commission(
        policy_id=policy.id, ev_id=ev.id, month=month, year=year,
        segment="P", achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.08"),
        monthly_actual=Decimal(total), total_actual=Decimal(total),
        is_final=False,
    )
    db.session.add(comm)
    db.session.flush()
    return policy, comm


def _mk_appraisal(admin, month=9, year=2026,
                  status=AppraisalStatus.CALCULATING):
    appraisal = Appraisal(month=month, year=year, status=status,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()
    return appraisal


def test_scope_active_in_inactive_out_departed_with_commission_in(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev_active, ev_departed = _mk_users(suffix)

    scope = signoff_scope_ev_ids(9, 2026)
    assert ev_active.id in scope
    assert ev_departed.id not in scope          # inativa e sem comissão
    assert admin.id not in scope                # ADMIN nunca entra

    _mk_commission(ev_departed, suffix)         # desligada COM comissão
    scope = signoff_scope_ev_ids(9, 2026)
    assert ev_departed.id in scope


def test_fingerprint_stable_and_sensitive(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)

    empty = compute_ev_fingerprint(ev.id, 9, 2026)
    assert empty == compute_ev_fingerprint(ev.id, 9, 2026)  # estável

    _, comm = _mk_commission(ev, suffix)
    with_comm = compute_ev_fingerprint(ev.id, 9, 2026)
    assert with_comm != empty

    comm.total_actual = Decimal("81.00")
    db.session.flush()
    after_total = compute_ev_fingerprint(ev.id, 9, 2026)
    assert after_total != with_comm

    comm.commission_pct = Decimal("0.10")
    db.session.flush()
    after_pct = compute_ev_fingerprint(ev.id, 9, 2026)
    assert after_pct != after_total

    comm.achievement_pct = Decimal("1.00")
    db.session.flush()
    assert compute_ev_fingerprint(ev.id, 9, 2026) != after_pct


def test_fingerprint_survives_db_roundtrip(db_session):
    """O fingerprint da conferência (calculado sobre objetos in-memory ou
    lidos do banco) tem que bater: NUMERIC devolve Decimal em escala de
    coluna (0.0800), o calculator atribui em escala própria (0.08)."""
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    # Referência forte obrigatória: o identity map guarda weak refs, e sem
    # ela o objeto in-memory (0.08) é coletado e o fingerprint do sign-off
    # releria do banco (0.0800) — o teste deixaria de exercer o mismatch.
    _, comm = _mk_commission(ev, suffix)
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    db.session.commit()
    db.session.expire_all()

    appraisal = Appraisal.query.filter_by(month=9, year=2026).first()
    result = refresh_signoffs_after_recalc(appraisal)
    assert result == {"invalidated": [], "kept": 1}


def test_ensure_signoffs_idempotent(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin)

    assert ensure_signoffs(appraisal) == 1      # só a EV ativa
    assert ensure_signoffs(appraisal) == 0      # segunda chamada não duplica
    rows = EvSignoff.query.filter_by(appraisal_id=appraisal.id).all()
    assert len(rows) == 1
    assert rows[0].status == SignoffStatus.PENDING


def test_refresh_keeps_unchanged_and_invalidates_changed(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    _, comm = _mk_commission(ev, suffix)
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    row.signed_off_by = admin.id
    row.signed_off_at = datetime.now(timezone.utc)
    db.session.flush()

    # Sem mudança → mantém
    result = refresh_signoffs_after_recalc(appraisal)
    assert result == {"invalidated": [], "kept": 1}
    assert row.status == SignoffStatus.DONE

    # Valor mudou → invalida com aviso
    comm.total_actual = Decimal("99.99")
    db.session.flush()
    result = refresh_signoffs_after_recalc(appraisal)
    assert result["invalidated"] == [ev.name]
    assert result["kept"] == 0
    assert row.status == SignoffStatus.PENDING
    assert row.values_changed is True
    assert row.fingerprint is None
    assert row.signed_off_by is None
    assert row.signed_off_at is None


def test_refresh_ignores_orphan_done_rows(db_session):
    """Linha DONE de EV que saiu do escopo é história congelada: o refresh
    não re-hasheia, não invalida e não lista no toast."""
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    _, comm = _mk_commission(ev, suffix)
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    db.session.flush()

    # EV sai do escopo (inativa) e o valor dela muda — mesmo assim, intocada.
    ev.active = False
    db.session.delete(comm)
    db.session.flush()

    result = refresh_signoffs_after_recalc(appraisal)
    assert result == {"invalidated": [], "kept": 0}
    assert row.status == SignoffStatus.DONE


def test_pending_and_totals(db_session):
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    ev2 = User(email=f"sos-ev3-{suffix}@x", name=f"Zeta {suffix}",
               role=UserRole.EV, active=True)
    db.session.add(ev2)
    db.session.flush()
    appraisal = _mk_appraisal(admin)
    ensure_signoffs(appraisal)

    pending = pending_signoff_evs(appraisal)
    assert [name for _, name in pending] == sorted([ev.name, ev2.name])
    assert signoff_totals(appraisal) == {
        "total": 2, "done": 0, "all_done": False,
    }

    row = EvSignoff.query.filter_by(
        appraisal_id=appraisal.id, ev_id=ev.id,
    ).first()
    row.status = SignoffStatus.DONE
    row.fingerprint = compute_ev_fingerprint(ev.id, 9, 2026)
    db.session.flush()

    assert [eid for eid, _ in pending_signoff_evs(appraisal)] == [ev2.id]
    assert signoff_totals(appraisal) == {
        "total": 2, "done": 1, "all_done": False,
    }

    # Linha órfã (EV saiu do escopo) não bloqueia o gate nem conta no total:
    ev2.active = False
    db.session.flush()
    assert pending_signoff_evs(appraisal) == []
    assert signoff_totals(appraisal) == {
        "total": 1, "done": 1, "all_done": True,
    }


def test_totals_frozen_from_rows_when_not_calculating(db_session):
    """Fora de CALCULATING os totais vêm das linhas gravadas (histórico),
    não do escopo recomputado — mudanças na tabela de usuários não podem
    reescrever a história de uma apuração liberada/travada."""
    suffix = uuid.uuid4().hex[:8]
    admin, ev, _ = _mk_users(suffix)
    appraisal = _mk_appraisal(admin, status=AppraisalStatus.VALIDATING)
    db.session.add(EvSignoff(
        appraisal_id=appraisal.id, ev_id=ev.id,
        status=SignoffStatus.DONE, fingerprint="x",
    ))
    db.session.flush()

    # A EV nova (ativa) NÃO entra nos totais de uma apuração já liberada.
    ev_new = User(email=f"sos-ev4-{suffix}@x", name="Nova",
                  role=UserRole.EV, active=True)
    db.session.add(ev_new)
    db.session.flush()

    assert signoff_totals(appraisal) == {
        "total": 1, "done": 1, "all_done": True,
    }
