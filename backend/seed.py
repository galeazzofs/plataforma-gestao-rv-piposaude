"""Seed script: initial data plus an idempotent dev E2E scenario."""
from decimal import Decimal
from datetime import date

from app import create_app
from app.extensions import db
from app.models import (
    BenefitType,
    Client,
    CnMonthlyGoal,
    CommissionPctTable,
    CommissionStatus,
    EvQuarterAchievement,
    FinancialImport,
    Goal,
    ImportBatch,
    PlatformSetting,
    Policy,
    Segment,
    Team,
    User,
    UserRole,
)


DEV_MONTH = 4
DEV_YEAR = 2026
DEV_QUARTER = 2
DEV_BATCH_FILENAME = "dev_e2e_apuracao_2026_04.xlsx"

USER_EMAILS = {
    "admin": "eric.valoz@piposaude.com",
    "finance": "frederico.lofredo@piposaude.com",
    "lider_pm": "aline.furlaneto@piposaude.com.br",
    "lider_gp": "carla.mendes@piposaude.com",
    "ev1": "joao.silva@piposaude.com",
    "ev2": "maria.santos@piposaude.com",
    "ev3": "pedro.oliveira@piposaude.com",
    "cn1": "ana.costa@piposaude.com",
}

POLICY_APOLICES = {
    "TICK-1001": ("AP-1001", "SulAmerica"),
    "TICK-1002": ("AP-1002", "Porto Seguro"),
    "TICK-1003": ("AP-1003", "Amil"),
    "TICK-1004": ("AP-1004", "Bradesco"),
    "TICK-1005": ("AP-1005", "MetLife"),
    "TICK-1006": ("AP-1006", "SulAmerica"),
    "TICK-1007": ("AP-1007", "Amil"),
    "TICK-1008": ("AP-1008", "Bradesco"),
    "TICK-1009": ("AP-1009", "Porto Seguro"),
}


def _get_user(email):
    return User.query.filter_by(email=email).first()


def _ensure_user(email, name, role, team=None, **attrs):
    user = _get_user(email)
    if user is None:
        user = User(email=email, name=name, role=role)
        db.session.add(user)
        db.session.flush()
    user.name = name
    user.role = role
    user.active = attrs.pop("active", True)
    if team is not None:
        user.team_id = team.id
    for key, value in attrs.items():
        setattr(user, key, value)
    return user


def _ensure_team(name):
    team = Team.query.filter_by(name=name).first()
    if team is None:
        team = Team(name=name)
        db.session.add(team)
        db.session.flush()
    return team


def _upsert_goal(user, quarter, year, target):
    goal = Goal.query.filter_by(
        ev_id=user.id,
        quarter=quarter,
        year=year,
    ).first()
    if goal is None:
        goal = Goal(ev_id=user.id, quarter=quarter, year=year)
        db.session.add(goal)
    goal.mrr_target = Decimal(str(target))
    return goal


def _upsert_achievement(user, quarter, year, total_mrr, target):
    achievement = EvQuarterAchievement.query.filter_by(
        ev_id=user.id,
        quarter=quarter,
        year=year,
    ).first()
    if achievement is None:
        achievement = EvQuarterAchievement(
            ev_id=user.id,
            quarter=quarter,
            year=year,
        )
        db.session.add(achievement)
    total = Decimal(str(total_mrr))
    target_dec = Decimal(str(target))
    achievement.total_mrr = total
    achievement.mrr_target = target_dec
    achievement.achievement_pct = (
        (total / target_dec).quantize(Decimal("0.0001"))
        if target_dec else Decimal("0")
    )
    achievement.is_final = False
    return achievement


def _upsert_cn_goal(cn):
    goal = CnMonthlyGoal.query.filter_by(
        cn_id=cn.id,
        month=DEV_MONTH,
        year=DEV_YEAR,
    ).first()
    if goal is None:
        goal = CnMonthlyGoal(cn_id=cn.id, month=DEV_MONTH, year=DEV_YEAR)
        db.session.add(goal)
    goal.sao_target = Decimal("50000.00")
    goal.vidas_target = Decimal("300.00")
    return goal


def _ensure_financial_imports(admin):
    batch = ImportBatch.query.filter_by(filename=DEV_BATCH_FILENAME).first()
    if batch is None:
        batch = ImportBatch(
            filename=DEV_BATCH_FILENAME,
            uploaded_by=admin.id,
            status="CONFIRMED",
        )
        db.session.add(batch)
        db.session.flush()

    created = 0
    for ticket, (numero_apolice, _operadora) in POLICY_APOLICES.items():
        policy = Policy.query.filter_by(hubspot_ticket_id=ticket).first()
        if policy is None:
            continue

        row = FinancialImport.query.filter_by(
            month=DEV_MONTH,
            year=DEV_YEAR,
            numero_apolice=numero_apolice,
            tipo_receita="Comissao",
        ).first()
        if row is None:
            row = FinancialImport(
                import_batch_id=batch.id,
                nf_valor_liquido=policy.mrr_for_commission
                or policy.mrr_projected
                or Decimal("0"),
                nf_mes_recebimento=f"{DEV_YEAR}-{DEV_MONTH:02d}",
                month=DEV_MONTH,
                year=DEV_YEAR,
                tipo_receita="Comissao",
                numero_apolice=numero_apolice,
                status_recebimento="RECEBIDO",
                data_recebimento=date(DEV_YEAR, DEV_MONTH, 10),
                match_status="UNMATCHED",
                cliente_mae=policy.client.name if policy.client else None,
                operadora=policy.partner_operator,
                produto=(
                    policy.benefit_type.value if policy.benefit_type else None
                ),
            )
            db.session.add(row)
            created += 1
        else:
            row.import_batch_id = row.import_batch_id or batch.id
            row.nf_mes_recebimento = f"{DEV_YEAR}-{DEV_MONTH:02d}"
            row.status_recebimento = "RECEBIDO"
            row.data_recebimento = row.data_recebimento or date(
                DEV_YEAR, DEV_MONTH, 10,
            )
            row.cliente_mae = (
                row.cliente_mae
                or (policy.client.name if policy.client else None)
            )
            row.operadora = row.operadora or policy.partner_operator
            row.produto = row.produto or (
                policy.benefit_type.value if policy.benefit_type else None
            )

    batch.nf_count = FinancialImport.query.filter_by(
        import_batch_id=batch.id,
    ).count()
    return created


def ensure_dev_e2e_data():
    """Backfill the dev data needed to run the EV monthly flow end to end."""
    team_pm = _ensure_team("Time P/M")
    team_gp = _ensure_team("Time G+")

    admin = _ensure_user(
        USER_EMAILS["admin"], "Eric Valoz", UserRole.ADMIN,
    )
    _ensure_user(
        "fernando.galeazzo@piposaude.com.br",
        "Fernando Galeazzo",
        UserRole.ADMIN,
    )
    _ensure_user(
        USER_EMAILS["finance"], "Frederico Lofredo", UserRole.FINANCE,
    )
    lider_pm = _ensure_user(
        USER_EMAILS["lider_pm"],
        "Aline Furlaneto",
        UserRole.LIDER_VENDAS,
        team_pm,
        salario_base=Decimal("12000.00"),
    )
    lider_gp = _ensure_user(
        USER_EMAILS["lider_gp"],
        "Carla Mendes",
        UserRole.LIDER_VENDAS,
        team_gp,
        salario_base=Decimal("12000.00"),
    )
    ev1 = _ensure_user(
        USER_EMAILS["ev1"],
        "Joao Silva",
        UserRole.EV,
        team_pm,
        salario_base=Decimal("8000.00"),
    )
    ev2 = _ensure_user(
        USER_EMAILS["ev2"],
        "Maria Santos",
        UserRole.EV,
        team_pm,
        salario_base=Decimal("8500.00"),
    )
    ev3 = _ensure_user(
        USER_EMAILS["ev3"],
        "Pedro Oliveira",
        UserRole.EV,
        team_gp,
        salario_base=Decimal("9000.00"),
    )
    cn1 = _ensure_user(
        USER_EMAILS["cn1"],
        "Ana Costa",
        UserRole.CN,
        team_gp,
        nivel="CN1",
        porte="M",
        salario_base=Decimal("7000.00"),
    )

    team_pm.leader_id = lider_pm.id
    team_gp.leader_id = lider_gp.id

    targets = {
        ev1.id: Decimal("80000.00"),
        ev2.id: Decimal("60000.00"),
        ev3.id: Decimal("70000.00"),
    }
    totals_q1 = {
        ev1.id: Decimal("23000.00"),
        ev2.id: Decimal("30000.00"),
        ev3.id: Decimal("55000.00"),
    }
    totals_q2 = {
        ev1.id: Decimal("42000.00"),
        ev2.id: Decimal("30000.00"),
        ev3.id: Decimal("50000.00"),
    }
    users_by_id = {ev1.id: ev1, ev2.id: ev2, ev3.id: ev3}
    for ev_id, target in targets.items():
        ev = users_by_id[ev_id]
        _upsert_goal(ev, 1, DEV_YEAR, target)
        _upsert_goal(ev, DEV_QUARTER, DEV_YEAR, target)
        _upsert_achievement(ev, 1, DEV_YEAR, totals_q1[ev_id], target)
        _upsert_achievement(ev, DEV_QUARTER, DEV_YEAR, totals_q2[ev_id], target)

    _upsert_cn_goal(cn1)

    for ticket, (numero_apolice, operadora) in POLICY_APOLICES.items():
        policy = Policy.query.filter_by(hubspot_ticket_id=ticket).first()
        if policy is None:
            continue
        policy.numero_apolice = numero_apolice
        policy.hubspot_apolice_id = policy.hubspot_apolice_id or numero_apolice
        policy.partner_operator = operadora

    created_imports = _ensure_financial_imports(admin)
    return {"created_imports": created_imports}


def seed(app=None):
    if app is None:
        app = create_app(start_schedulers=False)
    with app.app_context():
        if not app.config.get("DEV_SEED_ALLOWED"):
            # entrypoint.sh runs this on every container boot. Outside dev the
            # E2E dataset (fake users/goals/achievements/NFs) must never touch
            # the database — stag/prod boots are a hard no-op.
            print("Seed skipped: DEV_SEED_ALLOWED is off in this environment.")
            return

        db.create_all()

        already_seeded = bool(_get_user(USER_EMAILS["admin"]))
        if already_seeded:
            print("Database already seeded. Ensuring dev E2E scenario...")
            result = ensure_dev_e2e_data()
            db.session.commit()
            print(
                "Dev E2E ready: "
                f"{result['created_imports']} financial rows created."
            )
            return

        print("Seeding database...")

        team_vendas_1 = Team(name="Time P/M")
        team_vendas_2 = Team(name="Time G+")
        db.session.add_all([team_vendas_1, team_vendas_2])
        db.session.flush()

        eric = User(
            email=USER_EMAILS["admin"],
            name="Eric Valoz",
            role=UserRole.ADMIN,
        )
        fernando = User(
            email="fernando.galeazzo@piposaude.com.br",
            name="Fernando Galeazzo",
            role=UserRole.ADMIN,
        )
        fred = User(
            email=USER_EMAILS["finance"],
            name="Frederico Lofredo",
            role=UserRole.FINANCE,
        )
        lider_pm = User(
            email=USER_EMAILS["lider_pm"],
            name="Aline Furlaneto",
            role=UserRole.LIDER_VENDAS,
            team_id=team_vendas_1.id,
            salario_base=Decimal("12000.00"),
        )
        carla = User(
            email=USER_EMAILS["lider_gp"],
            name="Carla Mendes",
            role=UserRole.LIDER_VENDAS,
            team_id=team_vendas_2.id,
            salario_base=Decimal("12000.00"),
        )
        ev1 = User(
            email=USER_EMAILS["ev1"],
            name="Joao Silva",
            role=UserRole.EV,
            team_id=team_vendas_1.id,
            salario_base=Decimal("8000.00"),
        )
        ev2 = User(
            email=USER_EMAILS["ev2"],
            name="Maria Santos",
            role=UserRole.EV,
            team_id=team_vendas_1.id,
            salario_base=Decimal("8500.00"),
        )
        ev3 = User(
            email=USER_EMAILS["ev3"],
            name="Pedro Oliveira",
            role=UserRole.EV,
            team_id=team_vendas_2.id,
            salario_base=Decimal("9000.00"),
        )
        cn1 = User(
            email=USER_EMAILS["cn1"],
            name="Ana Costa",
            role=UserRole.CN,
            team_id=team_vendas_2.id,
            nivel="CN1",
            porte="M",
            salario_base=Decimal("7000.00"),
        )

        all_users = [
            eric, fernando, fred, lider_pm, carla, ev1, ev2, ev3, cn1,
        ]
        db.session.add_all(all_users)
        db.session.flush()

        team_vendas_1.leader_id = lider_pm.id
        team_vendas_2.leader_id = carla.id

        print(f"  Created {len(all_users)} users")

        pct_rows = [
            ("PP", "0.0000", "0.4999", "0.07"),
            ("PP", "0.5000", "0.9999", "0.08"),
            ("PP", "1.0000", "99.9999", "0.10"),
            ("P", "0.0000", "0.4999", "0.07"),
            ("P", "0.5000", "0.9999", "0.08"),
            ("P", "1.0000", "99.9999", "0.10"),
            ("M", "0.0000", "0.4999", "0.05"),
            ("M", "0.5000", "0.9999", "0.06"),
            ("M", "1.0000", "99.9999", "0.08"),
            ("G", "0.0000", "0.4999", "0.03"),
            ("G", "0.5000", "0.9999", "0.04"),
            ("G", "1.0000", "99.9999", "0.06"),
        ]
        for segment, amin, amax, pct in pct_rows:
            db.session.add(CommissionPctTable(
                version=1,
                segment=segment,
                achievement_min=Decimal(amin),
                achievement_max=Decimal(amax),
                commission_pct=Decimal(pct),
                valid_from=date(2026, 1, 1),
                created_by=eric.id,
            ))
        print("  Created commission pct table v1")

        goals = [
            (ev1, Decimal("80000")),
            (ev2, Decimal("60000")),
            (ev3, Decimal("70000")),
            (cn1, Decimal("40000")),
        ]
        for ev, target in goals:
            db.session.add(Goal(
                ev_id=ev.id,
                quarter=1,
                year=2026,
                mrr_target=target,
            ))
        print("  Created Q1/2026 goals")

        clients_data = [
            ("TechCorp Ltda", ev1),
            ("Startup XYZ", ev1),
            ("Industria ABC S.A.", ev2),
            ("Consultoria Beta", ev2),
            ("MegaCorp Brasil", ev3),
            ("Fintech Omega", ev3),
            ("Agro Solutions", cn1),
            ("Varejo Digital", cn1),
        ]
        clients = []
        for name, ev in clients_data:
            client = Client(
                name=name,
                name_normalized=name.strip().lower(),
                ev_id=ev.id,
            )
            db.session.add(client)
            clients.append(client)
        db.session.flush()
        print(f"  Created {len(clients)} clients")

        policies_data = [
            ("TICK-1001", ev1, 0, Segment.P, BenefitType.SAUDE,
             Decimal("12000"), 150, date(2026, 1, 10),
             CommissionStatus.IN_PAYMENT),
            ("TICK-1002", ev1, 0, Segment.PP, BenefitType.ODONTO,
             Decimal("3000"), 50, date(2026, 1, 15),
             CommissionStatus.PROJECTED),
            ("TICK-1003", ev1, 1, Segment.PP, BenefitType.SAUDE,
             Decimal("8000"), 30, date(2026, 2, 5),
             CommissionStatus.PROJECTED),
            ("TICK-1004", ev2, 2, Segment.M, BenefitType.SAUDE,
             Decimal("25000"), 500, date(2026, 1, 20),
             CommissionStatus.IN_PAYMENT),
            ("TICK-1005", ev2, 3, Segment.P, BenefitType.VIDA,
             Decimal("5000"), 100, date(2026, 2, 12),
             CommissionStatus.PROJECTED),
            ("TICK-1006", ev3, 4, Segment.G, BenefitType.SAUDE,
             Decimal("45000"), 2000, date(2026, 1, 8),
             CommissionStatus.IN_PAYMENT),
            ("TICK-1007", ev3, 5, Segment.P, BenefitType.SAUDE,
             Decimal("10000"), 120, date(2026, 2, 20),
             CommissionStatus.PROJECTED),
            ("TICK-1008", cn1, 6, Segment.M, BenefitType.SAUDE,
             Decimal("18000"), 350, date(2026, 1, 25),
             CommissionStatus.PROJECTED),
            ("TICK-1009", cn1, 7, Segment.PP, BenefitType.ODONTO,
             Decimal("4000"), 60, date(2026, 3, 1),
             CommissionStatus.PROJECTED),
        ]
        for ticket, ev, cidx, seg, benefit, mrr, hc, closed, status in policies_data:
            numero_apolice, operadora = POLICY_APOLICES[ticket]
            db.session.add(Policy(
                hubspot_apolice_id=numero_apolice,
                hubspot_ticket_id=ticket,
                numero_apolice=numero_apolice,
                partner_operator=operadora,
                ev_id=ev.id,
                client_id=clients[cidx].id,
                segment=seg,
                benefit_type=benefit,
                mrr_projected=mrr,
                headcount=hc,
                closed_date=closed,
                commission_status=status,
                installments_paid=(
                    2 if status == CommissionStatus.IN_PAYMENT else 0
                ),
                initial_installments_paid=(
                    2 if status == CommissionStatus.IN_PAYMENT else 0
                ),
                first_payment_real=(
                    date(2026, 2, 1)
                    if status == CommissionStatus.IN_PAYMENT else None
                ),
            ))
        print(f"  Created {len(policies_data)} sample policies")

        settings = {
            "validation_deadline_days": 5,
            "hubspot_sync_interval_minutes": 30,
            "notifications_slack_enabled": True,
            "notifications_email_enabled": False,
        }
        for key, value in settings.items():
            PlatformSetting.set(key, value, user_id=eric.id)
        print("  Created platform settings")

        result = ensure_dev_e2e_data()

        db.session.commit()
        print("\nSeed complete!")
        print("Dev E2E ready:")
        print(f"  - month/year: {DEV_MONTH:02d}/{DEV_YEAR}")
        print(f"  - financial rows created: {result['created_imports']}")
        print("  - roles: ADMIN, FINANCE, LIDER_VENDAS, EV, CN")


if __name__ == "__main__":
    seed()
