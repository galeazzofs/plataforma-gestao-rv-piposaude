"""End-to-end lifecycle test for the EV apuração.

Drives the whole pipeline through the real HTTP endpoints:
  create → CALCULATING (calculator) → VALIDATING (validations created)
  → every EV approves (across pages) → leader validates own
  → auto-advance to LIDER_REVIEW → REVOPS_REVIEW → LOCKED.

This is the regression guard for the flow the user hit: an EV with more than
one page of validations must be able to approve all of them, and the apuração
must then walk every state to LOCKED.
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    FinancialImport, ImportBatch, Commission, EvQuarterAchievement,
    Appraisal, AppraisalStatus, EvValidation, ValidationStatus,
    Team, CommissionPctTable, LiderVendasQuarterAppraisal, AuditLog,
)
from app.auth.jwt_manager import create_access_token

MONTH, YEAR, QUARTER = 5, 2027, 2  # Q2/2027 — isolated from other tests' periods


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


@pytest.fixture
def lifecycle_setup():
    """Admin + 1 líder (with team) + 2 EVs; each EV has matched policies/NFs so
    the calculator produces commissions. EV A gets 22 policies (>1 page of 20)
    to exercise pagination; EV B gets 2."""
    sfx = uuid.uuid4().hex[:8]

    for seg, mn, mx, pct in [
        ("M", "0.0000", "0.4999", "0.05"),
        ("M", "0.5000", "0.9999", "0.06"),
        ("M", "1.0000", "99.9999", "0.08"),
    ]:
        if not CommissionPctTable.query.filter_by(version=1, segment=seg,
                                                   commission_pct=Decimal(pct)).first():
            db.session.add(CommissionPctTable(
                version=1, segment=seg,
                achievement_min=Decimal(mn), achievement_max=Decimal(mx),
                commission_pct=Decimal(pct), valid_from=date(2020, 1, 1),
            ))
    db.session.flush()

    admin = User(email=f"lc-admin-{sfx}@x", name="LC Admin",
                 role=UserRole.ADMIN, active=True)
    lider = User(email=f"lc-lider-{sfx}@x", name="LC Lider",
                 role=UserRole.LIDER_VENDAS, active=True,
                 salario_base=Decimal("10000"))
    db.session.add_all([admin, lider])
    db.session.flush()

    team = Team(name=f"LC Team {sfx}", leader_id=lider.id)
    db.session.add(team)
    db.session.flush()
    lider.team_id = team.id

    ev_a = User(email=f"lc-eva-{sfx}@x", name="LC EV A",
                role=UserRole.EV, active=True, team_id=team.id)
    ev_b = User(email=f"lc-evb-{sfx}@x", name="LC EV B",
                role=UserRole.EV, active=True, team_id=team.id)
    db.session.add_all([ev_a, ev_b])
    db.session.flush()

    for ev in (ev_a, ev_b):
        db.session.add(EvQuarterAchievement(
            ev_id=ev.id, quarter=QUARTER, year=YEAR,
            achievement_pct=Decimal("0.75"),
        ))
    db.session.flush()

    batch = ImportBatch(filename="lc.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    def _policy_with_nf(ev, i):
        client = Client.find_or_create(f"LCClient-{sfx}-{ev.id.hex[:4]}-{i}")
        db.session.flush()
        ap = f"AP-LC-{sfx}-{ev.id.hex[:4]}-{i}"
        policy = Policy(
            hubspot_apolice_id=ap, hubspot_ticket_id=f"T-{ap}",
            numero_apolice=ap, ev_id=ev.id, client_id=client.id,
            segment=Segment.M, benefit_type=BenefitType.SAUDE,
            partner_operator="SulAmerica",
            closed_date=date(YEAR, 4, 1),          # Q2/2027 gongo
            first_payment_real=date(YEAR, 4, 15),
        )
        db.session.add(policy)
        db.session.flush()
        db.session.add(FinancialImport(
            import_batch_id=batch.id, month=MONTH, year=YEAR,
            nf_valor_liquido=Decimal("1000.00"), nf_mes_recebimento=f"{YEAR}-05",
            cliente_mae=client.name, operadora="SulAmerica", produto="Saude",
            numero_apolice=ap, tipo_receita="Comissao",
            status_recebimento="RECEBIDO", data_recebimento=date(YEAR, 5, 10),
            match_status="UNMATCHED",
        ))
        return policy

    # 22 policies for EV A (> one page of 20), 2 for EV B.
    for i in range(22):
        _policy_with_nf(ev_a, i)
    for i in range(2):
        _policy_with_nf(ev_b, i)
    db.session.commit()

    yield {"admin": admin, "lider": lider, "ev_a": ev_a, "ev_b": ev_b}

    # Teardown — children first, audit logs cleared to free user FKs.
    ap = Appraisal.query.filter_by(month=MONTH, year=YEAR).first()
    if ap:
        EvValidation.query.filter_by(appraisal_id=ap.id).delete()
    Commission.query.filter_by(month=MONTH, year=YEAR).delete()
    LiderVendasQuarterAppraisal.query.filter_by(quarter=QUARTER, year=YEAR).delete()
    FinancialImport.query.filter_by(month=MONTH, year=YEAR).delete()
    EvQuarterAchievement.query.filter(
        EvQuarterAchievement.ev_id.in_([ev_a.id, ev_b.id])
    ).delete(synchronize_session=False)
    Policy.query.filter(Policy.ev_id.in_([ev_a.id, ev_b.id])).delete(
        synchronize_session=False)
    Client.query.filter(Client.name.like(f"LCClient-{sfx}-%")).delete(
        synchronize_session=False)
    if ap:
        db.session.delete(ap)
    db.session.delete(batch)
    db.session.flush()
    user_ids = [admin.id, lider.id, ev_a.id, ev_b.id]
    AuditLog.query.filter(AuditLog.user_id.in_(user_ids)).delete(
        synchronize_session=False)
    db.session.query(Team).filter_by(id=team.id).update({Team.leader_id: None})
    db.session.flush()
    User.query.filter(User.id.in_(user_ids)).update(
        {User.team_id: None}, synchronize_session=False)
    db.session.flush()
    db.session.delete(team)
    User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    CommissionPctTable.query.filter_by(version=1).delete()
    db.session.commit()


def _approve_all_as(client, ev):
    """Walk every page of the EV's validations and approve each PENDING one —
    exactly what the fixed frontend now does."""
    approved = 0
    page = 1
    while True:
        resp = client.get(
            f"/api/v1/validations?per_page=100&page={page}", headers=_auth(ev))
        assert resp.status_code == 200
        body = resp.get_json()
        for row in body["data"]:
            if row["status"] == "PENDING":
                r = client.post(f"/api/v1/validations/{row['id']}/approve",
                                headers=_auth(ev))
                assert r.status_code == 200, r.get_json()
                approved += 1
        meta = body["meta"]
        if meta["page"] >= meta["total_pages"]:
            break
        page += 1
    return approved


@patch("slack_sdk.WebClient.chat_postMessage", MagicMock(return_value={"ok": True}))
def test_lider_approve_sends_team_appraisal_to_revops(client, lifecycle_setup):
    """The líder's direct 'Aprovar apuração' button: blocked until every team EV
    has approved, then advances the apuração straight to REVOPS_REVIEW."""
    admin = lifecycle_setup["admin"]
    lider = lifecycle_setup["lider"]
    ev_a, ev_b = lifecycle_setup["ev_a"], lifecycle_setup["ev_b"]

    aid = client.post("/api/v1/appraisals", json={"month": MONTH, "year": YEAR},
                      headers=_auth(admin)).get_json()["data"]["id"]
    client.post(f"/api/v1/appraisals/{aid}/transition",
                json={"to": "CALCULATING"}, headers=_auth(admin))
    client.post(f"/api/v1/appraisals/{aid}/transition",
                json={"to": "VALIDATING"}, headers=_auth(admin))

    # Before the EVs approve: the líder cannot approve yet.
    summary = client.get("/api/v1/lider-vendas/appraisal",
                         headers=_auth(lider)).get_json()["data"]
    assert summary["status"] == "VALIDATING"
    assert summary["can_approve"] is False
    blocked = client.post(f"/api/v1/lider-vendas/appraisal/{aid}/approve",
                          headers=_auth(lider))
    assert blocked.status_code == 409

    # EVs approve everything.
    _approve_all_as(client, ev_a)
    _approve_all_as(client, ev_b)

    summary = client.get("/api/v1/lider-vendas/appraisal",
                         headers=_auth(lider)).get_json()["data"]
    assert summary["can_approve"] is True
    assert summary["team_approved"] == summary["team_total"] == 24

    # Líder approves → straight to REVOPS_REVIEW (no leadership-bonus needed).
    resp = client.post(f"/api/v1/lider-vendas/appraisal/{aid}/approve",
                       headers=_auth(lider))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["status"] == "REVOPS_REVIEW"
    appraisal = db.session.get(Appraisal, aid)
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW


@patch("slack_sdk.WebClient.chat_postMessage", MagicMock(return_value={"ok": True}))
def test_full_apuracao_lifecycle_create_to_locked(client, lifecycle_setup):
    admin = lifecycle_setup["admin"]
    lider = lifecycle_setup["lider"]
    ev_a, ev_b = lifecycle_setup["ev_a"], lifecycle_setup["ev_b"]

    # 1. Create the appraisal (DRAFT).
    resp = client.post("/api/v1/appraisals", json={"month": MONTH, "year": YEAR},
                       headers=_auth(admin))
    assert resp.status_code == 201, resp.get_json()
    aid = resp.get_json()["data"]["id"]

    # 2. CALCULATING — runs the calculator, matches NFs, creates commissions.
    resp = client.post(f"/api/v1/appraisals/{aid}/transition",
                       json={"to": "CALCULATING"}, headers=_auth(admin))
    assert resp.status_code == 200, resp.get_json()
    assert Commission.query.filter_by(month=MONTH, year=YEAR).count() == 24

    # 3. VALIDATING — creates one EvValidation per commissioned policy.
    resp = client.post(f"/api/v1/appraisals/{aid}/transition",
                       json={"to": "VALIDATING"}, headers=_auth(admin))
    assert resp.status_code == 200, resp.get_json()
    assert EvValidation.query.filter_by(appraisal_id=aid).count() == 24

    # 4. Each EV approves ALL their validations (EV A spans 2 pages → 22).
    assert _approve_all_as(client, ev_a) == 22
    assert _approve_all_as(client, ev_b) == 2
    assert EvValidation.query.filter_by(
        appraisal_id=aid, status=ValidationStatus.PENDING).count() == 0

    # 5. Still VALIDATING — the líder gate hasn't been satisfied yet.
    appraisal = db.session.get(Appraisal, aid)
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.VALIDATING

    # 6. Create the líder's leadership appraisal for the quarter.
    resp = client.post(
        "/api/v1/commissions/leadership/appraisal",
        json={"quarter": QUARTER, "year": YEAR,
              "inputs": [{"lider_vendas_id": str(lider.id), "meta_sql": 10,
                          "realizado_mrr": "100000", "realizado_sql": 10}]},
        headers=_auth(admin))
    assert resp.status_code == 200, resp.get_json()
    lead = LiderVendasQuarterAppraisal.query.filter_by(
        lider_vendas_id=lider.id, quarter=QUARTER, year=YEAR).first()
    assert lead is not None

    # 7. Líder validates own: CALCULATING → VALIDATING → LIDER_REVIEW. The last
    #    hop re-triggers the global advance.
    for to in ("VALIDATING", "LIDER_REVIEW"):
        r = client.post(
            f"/api/v1/commissions/leadership/appraisal/{lead.id}/transition",
            json={"to": to}, headers=_auth(admin))
        assert r.status_code == 200, r.get_json()

    # 8. Global appraisal auto-advanced out of VALIDATING.
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.LIDER_REVIEW

    # 9. LIDER_REVIEW → REVOPS_REVIEW.
    resp = client.post(f"/api/v1/appraisals/{aid}/transition",
                       json={"to": "REVOPS_REVIEW"}, headers=_auth(admin))
    assert resp.status_code == 200, resp.get_json()

    # 10. REVOPS_REVIEW → LOCKED — commissions become final.
    resp = client.post(f"/api/v1/appraisals/{aid}/transition",
                       json={"to": "LOCKED"}, headers=_auth(admin))
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.LOCKED
    assert Commission.query.filter_by(
        month=MONTH, year=YEAR, is_final=True).count() == 24
