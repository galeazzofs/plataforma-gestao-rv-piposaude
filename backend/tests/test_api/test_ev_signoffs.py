"""API da conferência por EV: marcar, reabrir, authz, estados, gate, payload."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, Commission,
    EvSignoff, Policy, Segment, SignoffStatus, User, UserRole,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def signoff_setup():
    """Admin + 2 EVs ativos; EV1 tem apólice + Commission na apuração
    09/2026 em CALCULATING; EV2 é ativo sem movimento."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"soa-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev1 = User(email=f"soa-ev1-{suffix}@x", name=f"Alice {suffix}",
               role=UserRole.EV, active=True)
    ev2 = User(email=f"soa-ev2-{suffix}@x", name=f"Bruno {suffix}",
               role=UserRole.EV, active=True)
    db.session.add_all([admin, ev1, ev2])
    db.session.flush()

    client_obj = Client.find_or_create(f"SoaClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"SOA-{suffix}",
        numero_apolice=f"AP-SOA-{suffix}",
        ev_id=ev1.id, client_id=client_obj.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Amil", closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(month=9, year=2026,
                          status=AppraisalStatus.CALCULATING,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()

    comm = Commission(
        policy_id=policy.id, ev_id=ev1.id, month=9, year=2026,
        segment="P", achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.08"),
        monthly_actual=Decimal("80.00"), total_actual=Decimal("80.00"),
        is_final=False,
    )
    db.session.add(comm)
    db.session.commit()
    return admin, ev1, ev2, policy, appraisal, comm


def test_signoff_and_reopen_roundtrip(client, signoff_setup):
    from app.models import AuditLog

    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["ev_id"] == str(ev1.id)
    assert data["signoff"]["status"] == "DONE"
    assert data["signoff"]["signed_off_by_name"] == admin.name
    assert data["signoff"]["values_changed"] is False
    assert data["signoff_totals"] == {"total": 2, "done": 1,
                                      "all_done": False}
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 1

    # idempotente
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["signoff_totals"]["done"] == 1
    # no-op não gera nova auditoria
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 1

    # reabrir
    resp = client.delete(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["signoff"]["status"] == "PENDING"
    assert data["signoff_totals"]["done"] == 0
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 2

    # reabrir de novo (já PENDING) é no-op: 200, sem nova auditoria
    resp = client.delete(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["signoff"]["status"] == "PENDING"
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 2


def test_idempotent_noop_still_commits(client, signoff_setup, monkeypatch):
    """O caminho no-op TEM que commitar: ensure_signoffs pode ter criado
    linhas de outros EVs que precisam sobreviver ao teardown da request."""
    admin, ev1, _, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}"
    assert client.post(url, headers=_auth_header(admin)).status_code == 200

    calls = {"n": 0}
    real_commit = db.session.commit

    def counting_commit(*a, **kw):
        calls["n"] += 1
        return real_commit(*a, **kw)

    monkeypatch.setattr(db.session, "commit", counting_commit)
    resp = client.post(url, headers=_auth_header(admin))  # no-op
    assert resp.status_code == 200
    assert calls["n"] >= 1


def test_signoff_requires_admin(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}"

    resp = client.post(url, headers=_auth_header(ev1))
    assert resp.status_code == 403
    resp = client.delete(url, headers=_auth_header(ev1))
    assert resp.status_code == 403


def test_signoff_only_in_calculating(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "INVALID_STATE"


def test_signoff_out_of_scope_and_not_found(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{admin.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400          # ADMIN não é EV do escopo

    resp = client.post(
        f"/api/v1/appraisals/{uuid.uuid4()}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/nao-e-uuid",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_release_gate_via_api(client, signoff_setup):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/transition"

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 422
    assert "sem conferência" in resp.get_json()["error"]["message"]

    for ev in (ev1, ev2):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "VALIDATING"


def test_detail_payload_includes_signoffs_and_zero_movement(
    client, signoff_setup,
):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )

    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["signoff_totals"] == {"total": 2, "done": 1,
                                      "all_done": False}

    by_id = {s["ev_id"]: s for s in data["ev_summary"]}
    # EV1 (com comissão): conferida
    assert by_id[str(ev1.id)]["signoff"]["status"] == "DONE"
    assert by_id[str(ev1.id)].get("no_movement") is None
    # EV2 (sem movimento): entra zerada na lista, pendente
    zero = by_id[str(ev2.id)]
    assert zero["no_movement"] is True
    assert zero["total_commission"] == 0.0
    assert zero["policies"] == []
    assert zero["signoff"]["status"] == "PENDING"
    # lista continua ordenada por nome
    names = [s["ev_name"] for s in data["ev_summary"]]
    assert names == sorted(names)


def test_lider_scoped_view_recomputes_signoff_totals(client, signoff_setup):
    from app.models import Team

    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    suffix = uuid.uuid4().hex[:8]
    lider = User(email=f"soa-lider-{suffix}@x", name="Líder",
                 role=UserRole.LIDER_VENDAS, active=True)
    db.session.add(lider)
    db.session.flush()
    team = Team(name=f"Time-{suffix}", leader_id=lider.id)
    db.session.add(team)
    db.session.flush()
    lider.team_id = team.id
    ev1.team_id = team.id           # só a EV1 é do time do líder
    db.session.commit()

    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(lider))
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert [s["ev_id"] for s in data["ev_summary"]] == [str(ev1.id)]
    assert data["signoff_totals"] == {"total": 1, "done": 0,
                                      "all_done": False}


def test_preview_has_no_signoff_fields(client, signoff_setup):
    """O preview roda _build_period_detail direto — sem conferência (spec)."""
    admin, *_ = signoff_setup
    resp = client.post("/api/v1/appraisals/preview",
                       json={"month": 9, "year": 2026},
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "signoff_totals" not in data
    assert all("signoff" not in s for s in data["ev_summary"])


def test_locked_detail_freezes_conference_list(client, signoff_setup):
    """Fora de CALCULATING a lista da conferência é história congelada:
    EV nova contratada depois não entra; EV desligada com conferência
    gravada continua aparecendo — lista e totais no mesmo racional."""
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    for ev in (ev1, ev2):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    appraisal.status = AppraisalStatus.LOCKED
    ev2.active = False
    ev2.left_company = True
    new_ev = User(email=f"soa-ev3-{uuid.uuid4().hex[:8]}@x", name="Nova EV",
                  role=UserRole.EV, active=True)
    db.session.add(new_ev)
    db.session.commit()

    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    ids = [s["ev_id"] for s in data["ev_summary"]]
    assert str(new_ev.id) not in ids      # contratada depois do lock: fora
    assert str(ev2.id) in ids             # desligada com conferência: dentro
    assert data["signoff_totals"] == {"total": 2, "done": 2,
                                      "all_done": True}


def test_zero_movement_block_shape_matches_real_blocks(client, signoff_setup):
    """Trava de paridade: o bloco sintético (sem movimento) tem que cobrir
    todas as chaves do bloco real, para a UI não quebrar em campo faltante."""
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    resp = client.get(f"/api/v1/appraisals/{appraisal.id}",
                      headers=_auth_header(admin))
    by_id = {s["ev_id"]: s for s in resp.get_json()["data"]["ev_summary"]}
    real, zero = by_id[str(ev1.id)], by_id[str(ev2.id)]
    assert set(real.keys()) - set(zero.keys()) == set()
    assert set(zero.keys()) - set(real.keys()) == {"no_movement"}


def test_recalculate_invalidates_changed_signoffs(client, signoff_setup):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    for ev in (ev1, ev2):
        client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )

    # O recálculo real apaga a Commission da EV1 (não há NF que a recrie),
    # então o fingerprint dela muda; a EV2 segue vazia (mantida).
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["signoffs"]["invalidated"] == [ev1.name]
    assert body["signoffs"]["kept"] == 1

    by_id = {s["ev_id"]: s for s in body["data"]["ev_summary"]}
    assert by_id[str(ev1.id)]["signoff"]["status"] == "PENDING"
    assert by_id[str(ev1.id)]["signoff"]["values_changed"] is True
    assert by_id[str(ev2.id)]["signoff"]["status"] == "DONE"

    # Re-conferir limpa o aviso de "valores mudaram" (spec, teste 3d).
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    signoff = resp.get_json()["data"]["signoff"]
    assert signoff["status"] == "DONE"
    assert signoff["values_changed"] is False


def test_shared_client_recalc_invalidates_both_evs(client, db_session):
    """Duas EVs, duas apólices do MESMO cliente. Um Perk novo no cliente
    muda a base das duas no recálculo → as duas conferências caem. É o
    cenário que justifica o recálculo global (spec: 'Por que recálculo
    global e não escopado por EV')."""
    from app.models import (
        CommissionPctTable, EvQuarterAchievement, FinancialImport,
        ImportBatch, Perk,
    )

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
    admin = User(email=f"shc-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    eva = User(email=f"shc-eva-{suffix}@x", name=f"Ana {suffix}",
               role=UserRole.EV, active=True)
    evb = User(email=f"shc-evb-{suffix}@x", name=f"Bia {suffix}",
               role=UserRole.EV, active=True)
    db.session.add_all([admin, eva, evb])
    db.session.flush()

    shared_client = Client.find_or_create(f"SharedCo-{suffix}")
    db.session.flush()
    for ev, tag, produto in ((eva, "A", BenefitType.SAUDE),
                             (evb, "B", BenefitType.ODONTO)):
        db.session.add(Policy(
            hubspot_ticket_id=f"SHC-{tag}-{suffix}",
            numero_apolice=f"AP-SHC-{tag}-{suffix}",
            ev_id=ev.id, client_id=shared_client.id,
            segment=Segment.P, benefit_type=produto,
            partner_operator="Amil", closed_date=date(2026, 7, 1),
        ))
        db.session.add(EvQuarterAchievement(
            ev_id=ev.id, quarter=3, year=2026,
            achievement_pct=Decimal("0.75"),
        ))
    db.session.flush()

    batch = ImportBatch(filename="shc.xlsx", uploaded_by=admin.id,
                        status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    for tag, produto in (("A", "Saúde"), ("B", "Odonto")):
        db.session.add(FinancialImport(
            import_batch_id=batch.id, month=9, year=2026,
            nf_valor_liquido=Decimal("1000.00"),
            nf_mes_recebimento="2026-09",
            cliente_mae=shared_client.name,
            operadora="Amil", produto=produto,
            numero_apolice=f"AP-SHC-{tag}-{suffix}",
            tipo_receita="Comissão", status_recebimento="RECEBIDO",
            data_recebimento=date(2026, 9, 10),
            match_status="UNMATCHED",
        ))
    db.session.commit()

    # DRAFT → CALCULATING roda o calculator de verdade e cria os signoffs
    resp = client.post("/api/v1/appraisals", json={"month": 9, "year": 2026},
                       headers=_auth_header(admin))
    assert resp.status_code == 201
    appraisal_id = resp.get_json()["data"]["id"]
    resp = client.post(f"/api/v1/appraisals/{appraisal_id}/transition",
                       json={"to": "CALCULATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 200

    for ev in (eva, evb):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal_id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    # Perk novo no cliente compartilhado → recálculo muda a base das DUAS
    db.session.add(Perk(client_id=shared_client.id, month=9, year=2026,
                        amount=Decimal("500.00"),
                        import_batch_id=batch.id))
    db.session.commit()

    resp = client.post(f"/api/v1/appraisals/{appraisal_id}/recalculate",
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    invalidated = resp.get_json()["signoffs"]["invalidated"]
    assert sorted(invalidated) == sorted([eva.name, evb.name])


def test_delete_appraisal_removes_signoffs(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert EvSignoff.query.filter_by(appraisal_id=appraisal.id).count() > 0

    resp = client.delete(f"/api/v1/appraisals/{appraisal.id}",
                         headers=_auth_header(admin))
    assert resp.status_code == 200
    assert EvSignoff.query.filter_by(appraisal_id=appraisal.id).count() == 0


def test_recalculate_after_release_still_flags_changes(client, signoff_setup):
    """Recalcular em VALIDATING+ continua permitido: o gate já passou, mas o
    hook ainda roda e marca values_changed (informativo, spec)."""
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    for ev in (ev1, ev2):
        client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    resp = client.post(f"/api/v1/appraisals/{appraisal.id}/recalculate",
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["signoffs"]["invalidated"] == [ev1.name]

    by_id = {s["ev_id"]: s for s in body["data"]["ev_summary"]}
    assert by_id[str(ev1.id)]["signoff"]["values_changed"] is True
