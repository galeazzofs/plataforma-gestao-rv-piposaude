"""Tests for the enriched appraisal serializer + recalculate endpoint."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    FinancialImport, ImportBatch, Commission, EvQuarterAchievement,
    Appraisal, AppraisalStatus, CommissionPctTable, EvSignoff, Perk,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def review_setup():
    """One admin, one EV, one matched policy + commission + NF for the
    08/2026 apuração (policy gongado Q3/2026)."""
    suffix = uuid.uuid4().hex[:8]

    # Seed pct table for M segment if not present (idempotent on the test DB)
    existing = CommissionPctTable.query.filter_by(version=1, segment="M").first()
    if not existing:
        for seg, mn, mx, pct in [
            ("M", "0.0000", "0.4999", "0.05"),
            ("M", "0.5000", "0.9999", "0.06"),
            ("M", "1.0000", "99.9999", "0.08"),
        ]:
            db.session.add(CommissionPctTable(
                version=1, segment=seg,
                achievement_min=Decimal(mn), achievement_max=Decimal(mx),
                commission_pct=Decimal(pct), valid_from=date.today(),
            ))
        db.session.flush()

    admin = User(email=f"rev-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"rev-ev-{suffix}@x", name="Maria Silva",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    client = Client.find_or_create(f"RevClient-{suffix}")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id=f"A-REV-T-{suffix}",
        hubspot_ticket_id=f"REV-T-{suffix}",
        numero_apolice=f"AP-REV-{suffix}",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2026, 7, 1),  # Q3/2026 gongo
        first_payment_real=date(2026, 7, 15),
    )
    db.session.add(policy)
    db.session.flush()

    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=3, year=2026,
        achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    appraisal = Appraisal(
        month=8, year=2026, status=AppraisalStatus.CALCULATING,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.flush()

    batch = ImportBatch(filename="rev.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, month=8, year=2026,
        nf_valor_liquido=Decimal("1000.00"),
        nf_mes_recebimento="2026-08",
        cliente_mae=client.name,
        operadora="SulAmerica",
        produto="Saúde",
        numero_apolice=f"AP-REV-{suffix}",
        tipo_receita="Comissão",
        status_recebimento="RECEBIDO",
        data_recebimento=date(2026, 8, 10),
        match_status="UNMATCHED",
    )
    db.session.add(nf)
    db.session.flush()
    db.session.commit()

    yield admin, ev, client, policy, appraisal, nf

    # Teardown
    Commission.query.filter_by(month=8, year=2026).delete()
    FinancialImport.query.filter_by(month=8, year=2026).delete()
    EvQuarterAchievement.query.filter_by(ev_id=ev.id).delete()
    db.session.delete(batch)
    db.session.delete(appraisal)
    Policy.query.filter_by(id=policy.id).delete()
    db.session.delete(client)
    db.session.delete(admin)
    db.session.delete(ev)
    # Clean up the seeded pct table so other tests can re-seed
    CommissionPctTable.query.filter_by(version=1).delete()
    db.session.commit()


def test_calculating_transition_without_achievements_does_not_block(client, db_session):
    """A CALCULATING transition used to 422 (MissingAchievements) when a
    gongo-quarter achievement was missing. Now it runs with a 0% fallback
    (floor tier) and surfaces the gap as a warning instead of blocking."""
    suffix = uuid.uuid4().hex[:8]
    for seg, mn, mx, pct in [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "99.9999", "0.10"),
    ]:
        db.session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(mn), achievement_max=Decimal(mx),
            commission_pct=Decimal(pct), valid_from=date.today(),
        ))
    admin = User(email=f"noach-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"noach-ev-{suffix}@x", name="EV NoAch",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()
    client_obj = Client.find_or_create(f"NoAchClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"NOACH-{suffix}",
        numero_apolice=f"AP-NOACH-{suffix}",
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Bradesco",
        closed_date=date(2026, 7, 1),  # Q3/2026 gongo — NO achievement seeded
        first_payment_real=date(2026, 7, 15),
    )
    db.session.add(policy)
    db.session.flush()
    appraisal = Appraisal(month=8, year=2026, status=AppraisalStatus.DRAFT,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()
    batch = ImportBatch(filename="noach.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    db.session.add(FinancialImport(
        import_batch_id=batch.id, month=8, year=2026,
        nf_valor_liquido=Decimal("1000.00"), nf_mes_recebimento="2026-08",
        cliente_mae=client_obj.name, operadora="Bradesco", produto="Saúde",
        numero_apolice=f"AP-NOACH-{suffix}", tipo_receita="Comissão",
        status_recebimento="RECEBIDO", data_recebimento=date(2026, 8, 10),
        match_status="UNMATCHED",
    ))
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/transition",
        json={"to": "CALCULATING"},
        headers=_auth_header(admin),
    )

    try:
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()["data"]
        # Gap surfaced as a warning, not a block.
        assert any("Q3/2026" in m for m in body["missing_achievements"])
        # Commission still produced — at the floor (achievement 0 → 7% for P).
        comm = Commission.query.filter_by(
            policy_id=policy.id, month=8, year=2026
        ).first()
        assert comm is not None
        assert comm.achievement_pct == Decimal("0")
        assert comm.commission_pct == Decimal("0.07")
    finally:
        from app.models import AuditLog
        db.session.rollback()
        Commission.query.filter_by(month=8, year=2026).delete()
        FinancialImport.query.filter_by(month=8, year=2026).delete()
        # The CALCULATING transition writes an audit_log referencing the user;
        # clear it before deleting users to avoid an FK violation.
        AuditLog.query.filter(
            AuditLog.user_id.in_([admin.id, ev.id])
        ).delete(synchronize_session=False)
        # The CALCULATING transition now also seeds EvSignoff rows for the
        # scope (Task 3, 2026-07-07); clear them before deleting the
        # appraisal to avoid an FK violation.
        EvSignoff.query.filter_by(appraisal_id=appraisal.id).delete()
        db.session.delete(appraisal)
        db.session.delete(batch)
        Policy.query.filter_by(id=policy.id).delete()
        db.session.delete(client_obj)
        db.session.delete(admin)
        db.session.delete(ev)
        CommissionPctTable.query.filter_by(version=1).delete()
        db.session.commit()


def test_recalculate_runs_calculator_and_returns_detail(client, review_setup):
    admin, ev, client_obj, policy, appraisal, nf = review_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]

    assert body["status"] == "CALCULATING"
    assert "ev_summary" in body
    assert "totals" in body
    assert body["totals"]["matched_nf_count"] == 1

    # The single EV's policy + commission should appear in ev_summary
    assert len(body["ev_summary"]) == 1
    ev_block = body["ev_summary"][0]
    assert ev_block["ev_name"] == "Maria Silva"
    assert ev_block["policies_count"] == 1
    assert ev_block["total_commission"] == 60.0  # 1000 * 0.06
    assert len(ev_block["policies"]) == 1
    assert ev_block["policies"][0]["nfs"][0]["nf_liquido"] == 1000.0


def test_ev_summary_exposes_subsidy_before_commission_base(client, review_setup):
    admin, ev, client_obj, policy, appraisal, nf = review_setup
    batch = ImportBatch(filename="perks.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    db.session.add(Perk(
        client_id=client_obj.id,
        month=8,
        year=2026,
        amount=Decimal("200.00"),
        import_batch_id=batch.id,
    ))
    db.session.commit()

    try:
        resp = client.post(
            f"/api/v1/appraisals/{appraisal.id}/recalculate",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200
        body = resp.get_json()["data"]

        ev_block = body["ev_summary"][0]
        policy_block = ev_block["policies"][0]
        assert ev_block["nf_liquido_total"] == 1000.0
        assert ev_block["subsidio_aplicado_total"] == 200.0
        assert ev_block["base_comissionavel_total"] == 800.0
        assert ev_block["total_commission"] == 48.0
        assert policy_block["subsidio_aplicado"] == 200.0
        assert policy_block["base_comissionavel"] == 800.0
        assert body["totals"]["subsidio_aplicado_total"] == 200.0
        assert body["totals"]["base_comissionavel_total"] == 800.0
    finally:
        Commission.query.filter_by(month=8, year=2026).delete()
        Perk.query.filter_by(import_batch_id=batch.id).delete()
        db.session.delete(batch)
        db.session.commit()


def test_ev_summary_exposes_nao_apuradas_and_nf_liquido_total(client, review_setup):
    """The Por EV payload carries (a) the EV's full book split into apuradas /
    não apuradas with a reason, and (b) the summed NF líquido alongside the
    commission total."""
    admin, ev, client_obj, policy, appraisal, nf = review_setup

    # A second policy for the same EV with no NF this month → não apurada.
    suffix = uuid.uuid4().hex[:8]
    other = Policy(
        hubspot_ticket_id=f"REV-T2-{suffix}",
        numero_apolice=f"AP-REV2-{suffix}",
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.VIDA,
        partner_operator="Prudential",
        closed_date=date(2026, 7, 1),
        first_payment_real=date(2026, 7, 15),
    )
    db.session.add(other)
    db.session.commit()

    try:
        # Apura the first (matched) policy.
        client.post(
            f"/api/v1/appraisals/{appraisal.id}/recalculate",
            headers=_auth_header(admin),
        )
        resp = client.get(
            f"/api/v1/appraisals/{appraisal.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200
        body = resp.get_json()["data"]

        ev_block = body["ev_summary"][0]
        # Counts split between apuradas and the rest of the book.
        assert ev_block["policies_count"] == 1
        assert ev_block["nao_apuradas_count"] == 1
        # NF líquido sum surfaces at EV and totals level.
        assert ev_block["nf_liquido_total"] == 1000.0
        assert body["totals"]["nf_liquido_total"] == 1000.0

        blocks = {b["policy_id"]: b for b in ev_block["policies"]}
        apurada = blocks[str(policy.id)]
        nao = blocks[str(other.id)]
        assert apurada["apurada"] is True
        assert apurada["nf_liquido_total"] == 1000.0
        assert nao["apurada"] is False
        assert nao["subtotal"] == 0.0
        assert nao["reason"] == "Sem NF no mês"
    finally:
        Commission.query.filter_by(month=8, year=2026).delete()
        Policy.query.filter_by(id=other.id).delete()
        db.session.commit()


def test_recalculate_blocked_when_locked(client, review_setup):
    admin, _, _, _, appraisal, _ = review_setup
    appraisal.status = AppraisalStatus.LOCKED
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"]["code"] == "CONFLICT"


def test_get_appraisal_detail_includes_drill_down(client, review_setup):
    admin, _, _, _, appraisal, _ = review_setup

    # First trigger a recalc to populate commissions
    client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )

    resp = client.get(
        f"/api/v1/appraisals/{appraisal.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "ev_summary" in body
    assert "unmatched" in body
    assert "nao_suportado" in body
    assert "apolices_finalizadas" in body
    assert body["totals"]["matched_nf_count"] == 1


def test_get_appraisal_detail_includes_finalized_policy_bucket(client, review_setup):
    admin, _, _, policy, appraisal, nf = review_setup
    nf.match_status = "APOLICE_FINALIZADA"
    nf.policy_id = policy.id
    db.session.commit()

    resp = client.get(
        f"/api/v1/appraisals/{appraisal.id}",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["totals"]["apolices_finalizadas_count"] == 1
    assert body["apolices_finalizadas"][0]["match_status"] == "APOLICE_FINALIZADA"
    assert body["apolices_finalizadas"][0]["policy_id"] == str(policy.id)


def test_finalized_policy_bucket_includes_completion_month(client, review_setup):
    admin, _, client_obj, policy, appraisal, nf = review_setup
    policy.initial_installments_paid = 11
    policy.installments_paid = 12
    nf.match_status = "MATCHED"
    nf.policy_id = policy.id
    nf.nf_mes_recebimento = "2026-08"
    nf.tipo_receita = "Comissao"

    finalized_nf = FinancialImport(
        import_batch_id=nf.import_batch_id,
        month=8,
        year=2026,
        nf_valor_liquido=Decimal("500.00"),
        nf_mes_recebimento="2026-09",
        cliente_mae=client_obj.name,
        operadora="SulAmerica",
        produto="Saude",
        numero_apolice=policy.numero_apolice,
        tipo_receita="Comissao",
        status_recebimento="RECEBIDO",
        data_recebimento=date(2026, 9, 10),
        match_status="APOLICE_FINALIZADA",
        policy_id=policy.id,
    )
    db.session.add(finalized_nf)
    db.session.commit()

    resp = client.get(
        f"/api/v1/appraisals/{appraisal.id}",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["apolices_finalizadas"][0]["apolice_finalizada_mes"] == "2026-08"


# ── Monthly preview (read-only draft) ─────────────────────────────────


def test_preview_returns_detail_without_persisting(client, review_setup):
    """Preview runs the real calculator and returns the same review payload,
    but leaves zero trace: no commissions, no policy mutations, no NF match
    changes, no appraisal."""
    admin, ev, _client, policy, appraisal, nf = review_setup

    # Snapshot the pre-preview state straight from the DB.
    before = {
        "commission_count": Commission.query.filter_by(month=8, year=2026).count(),
        "appraisal_count": Appraisal.query.count(),
        "appraisal_status": appraisal.status,
        "nf_status": nf.match_status,
        "nf_policy_id": nf.policy_id,
        "installments_paid": policy.installments_paid,
        "first_payment_real": policy.first_payment_real,
        "commission_status": policy.commission_status,
    }
    assert before["commission_count"] == 0
    assert before["nf_status"] == "UNMATCHED"

    resp = client.post(
        "/api/v1/appraisals/preview",
        json={"month": 8, "year": 2026},
        headers=_auth_header(admin),
    )

    # The numbers come back exactly as a real CALCULATING run would produce.
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["preview"] is True
    assert body["month"] == 8 and body["year"] == 2026
    assert body["missing_achievements"] == []  # the seed EV has its achievement
    assert body["totals"]["matched_nf_count"] == 1
    assert len(body["ev_summary"]) == 1
    ev_block = body["ev_summary"][0]
    assert ev_block["ev_name"] == "Maria Silva"
    assert ev_block["total_commission"] == 60.0  # 1000 * 0.06 — same as a real run

    # Nothing persisted: re-read every touched row fresh from the DB.
    db.session.expire_all()
    assert Commission.query.filter_by(month=8, year=2026).count() == 0
    assert Appraisal.query.count() == before["appraisal_count"]
    fresh_appraisal = db.session.get(Appraisal, appraisal.id)
    assert fresh_appraisal.status == before["appraisal_status"]
    fresh_nf = db.session.get(FinancialImport, nf.id)
    assert fresh_nf.match_status == before["nf_status"] == "UNMATCHED"
    assert fresh_nf.policy_id == before["nf_policy_id"]
    fresh_policy = db.session.get(Policy, policy.id)
    assert fresh_policy.installments_paid == before["installments_paid"]
    assert fresh_policy.first_payment_real == before["first_payment_real"]
    assert fresh_policy.commission_status == before["commission_status"]


def test_preview_runs_despite_missing_achievements(client, review_setup):
    """A draft must not be blocked by the achievement gate — it runs anyway,
    reports the missing combos, and those policies fall back to 0%
    achievement (the table's floor bracket)."""
    admin, ev, _client, _policy, _appraisal, _nf = review_setup
    # Drop the achievement the policy's gongo quarter needs.
    EvQuarterAchievement.query.filter_by(ev_id=ev.id).delete()
    db.session.commit()

    resp = client.post(
        "/api/v1/appraisals/preview",
        json={"month": 8, "year": 2026},
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    body = resp.get_json()["data"]
    # The missing (ev, gongo-quarter) combo is reported as a warning…
    # The gongo quarter comes from the policy's closed_date (Q3/2026), not
    # from the appraisal month.
    assert any("Q3/2026" in m for m in body["missing_achievements"])
    # …and a draft is still produced, at the 0%-achievement bracket (5%).
    assert len(body["ev_summary"]) == 1
    assert body["ev_summary"][0]["total_commission"] == 50.0  # 1000 * 0.05


def test_preview_rejects_invalid_month(client, review_setup):
    admin, *_ = review_setup

    resp = client.post(
        "/api/v1/appraisals/preview",
        json={"month": 13, "year": 2026},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_preview_empty_month_points_at_months_with_data(client, review_setup):
    """When the chosen month has no NFs, the payload still reports the months
    that DO carry imported data — so the UI can tell the user where their
    upload landed instead of showing a silent blank apuração. The fixture's
    only NF is in month 8/2026, so a preview of month 5 comes back empty but
    surfaces month 8."""
    admin, *_ = review_setup

    resp = client.post(
        "/api/v1/appraisals/preview",
        json={"month": 5, "year": 2026},
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    body = resp.get_json()["data"]
    # Month 5 is genuinely empty.
    assert body["totals"]["matched_nf_count"] == 0
    assert body["totals"]["unmatched_count"] == 0
    assert body["ev_summary"] == []
    # …but the import that landed in month 8 is surfaced as a pointer.
    periods = body["financial_data_periods"]
    assert {"year": 2026, "month": 8, "nf_count": 1} in periods
