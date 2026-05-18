"""Seed script — creates initial users, teams, goals, commission % table, and sample data."""
import uuid
from decimal import Decimal
from datetime import date
from app import create_app
from app.extensions import db
from app.models import (
    User, UserRole, Team, Client, Policy, Goal,
    CommissionPctTable, Segment, BenefitType, CommissionStatus,
    PlatformSetting,
)


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Check if already seeded
        if User.query.filter_by(email="eric.valoz@piposaude.com").first():
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # ==========================================
        # TEAMS
        # ==========================================
        team_vendas_1 = Team(name="Time P/M")
        team_vendas_2 = Team(name="Time G+")
        db.session.add_all([team_vendas_1, team_vendas_2])
        db.session.flush()

        # ==========================================
        # USERS
        # ==========================================
        eric = User(
            email="eric.valoz@piposaude.com",
            name="Eric Valoz",
            role=UserRole.ADMIN,
        )
        fernando = User(
            email="fernando.galeazzo@piposaude.com.br",
            name="Fernando Galeazzo",
            role=UserRole.ADMIN,
        )
        fred = User(
            email="frederico.lofredo@piposaude.com",
            name="Frederico Lofredo",
            role=UserRole.FINANCE,
        )
        felipe = User(
            email="felipe.valenca@piposaude.com",
            name="Felipe Valença",
            role=UserRole.LIDER_VENDAS,
            team_id=team_vendas_1.id,
        )
        ev1 = User(
            email="joao.silva@piposaude.com",
            name="João Silva",
            role=UserRole.EV,
            team_id=team_vendas_1.id,
        )
        ev2 = User(
            email="maria.santos@piposaude.com",
            name="Maria Santos",
            role=UserRole.EV,
            team_id=team_vendas_1.id,
        )
        ev3 = User(
            email="pedro.oliveira@piposaude.com",
            name="Pedro Oliveira",
            role=UserRole.EV,
            team_id=team_vendas_2.id,
        )
        cn1 = User(
            email="ana.costa@piposaude.com",
            name="Ana Costa",
            role=UserRole.CN,
            team_id=team_vendas_2.id,
        )

        all_users = [eric, fernando, fred, felipe, ev1, ev2, ev3, cn1]
        db.session.add_all(all_users)
        db.session.flush()

        # Set team leaders
        team_vendas_1.leader_id = felipe.id
        team_vendas_2.leader_id = ev3.id

        print(f"  Created {len(all_users)} users")

        # ==========================================
        # COMMISSION % TABLE (version 1)
        # ==========================================
        pct_rows = [
            # PP (1-80 vidas) — mesma faixa que P
            ("PP", "0.0000", "0.4999", "0.07"),
            ("PP", "0.5000", "0.9999", "0.08"),
            ("PP", "1.0000", "99.9999", "0.10"),
            # P (81-199 vidas)
            ("P", "0.0000", "0.4999", "0.07"),
            ("P", "0.5000", "0.9999", "0.08"),
            ("P", "1.0000", "99.9999", "0.10"),
            # M (200-999 vidas)
            ("M", "0.0000", "0.4999", "0.05"),
            ("M", "0.5000", "0.9999", "0.06"),
            ("M", "1.0000", "99.9999", "0.08"),
            # G (1000+ vidas)
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
        print("  Created commission % table v1 (4 segments x 3 faixas)")

        # ==========================================
        # GOALS Q1 2026
        # ==========================================
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
        print("  Created Q1/2026 goals for 4 EVs")

        # ==========================================
        # CLIENTS
        # ==========================================
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
            c = Client(
                name=name,
                name_normalized=name.strip().lower(),
                ev_id=ev.id,
            )
            db.session.add(c)
            clients.append(c)
        db.session.flush()
        print(f"  Created {len(clients)} clients")

        # ==========================================
        # SAMPLE POLICIES (deals gongados Q1 2026)
        # ==========================================
        policies_data = [
            # (ticket_id, ev, client_idx, segment, benefit, mrr, headcount, closed_date, status)
            ("TICK-1001", ev1, 0, Segment.P, BenefitType.SAUDE, Decimal("12000"), 150, date(2026, 1, 10), CommissionStatus.IN_PAYMENT),
            ("TICK-1002", ev1, 0, Segment.PP, BenefitType.ODONTO, Decimal("3000"), 50, date(2026, 1, 15), CommissionStatus.PROJECTED),
            ("TICK-1003", ev1, 1, Segment.PP, BenefitType.SAUDE, Decimal("8000"), 30, date(2026, 2, 5), CommissionStatus.PROJECTED),
            ("TICK-1004", ev2, 2, Segment.M, BenefitType.SAUDE, Decimal("25000"), 500, date(2026, 1, 20), CommissionStatus.IN_PAYMENT),
            ("TICK-1005", ev2, 3, Segment.P, BenefitType.VIDA, Decimal("5000"), 100, date(2026, 2, 12), CommissionStatus.PROJECTED),
            ("TICK-1006", ev3, 4, Segment.G, BenefitType.SAUDE, Decimal("45000"), 2000, date(2026, 1, 8), CommissionStatus.IN_PAYMENT),
            ("TICK-1007", ev3, 5, Segment.P, BenefitType.SAUDE, Decimal("10000"), 120, date(2026, 2, 20), CommissionStatus.PROJECTED),
            ("TICK-1008", cn1, 6, Segment.M, BenefitType.SAUDE, Decimal("18000"), 350, date(2026, 1, 25), CommissionStatus.PROJECTED),
            ("TICK-1009", cn1, 7, Segment.PP, BenefitType.ODONTO, Decimal("4000"), 60, date(2026, 3, 1), CommissionStatus.PROJECTED),
        ]
        for ticket, ev, cidx, seg, benefit, mrr, hc, closed, status in policies_data:
            p = Policy(
                hubspot_ticket_id=ticket,
                ev_id=ev.id,
                client_id=clients[cidx].id,
                segment=seg,
                benefit_type=benefit,
                mrr_projected=mrr,
                headcount=hc,
                closed_date=closed,
                commission_status=status,
                installments_paid=2 if status == CommissionStatus.IN_PAYMENT else 0,
                first_payment_real=date(2026, 2, 1) if status == CommissionStatus.IN_PAYMENT else None,
            )
            db.session.add(p)
        print(f"  Created {len(policies_data)} sample policies")

        # ==========================================
        # PLATFORM SETTINGS
        # ==========================================
        settings = {
            "validation_deadline_days": 5,
            "hubspot_sync_interval_minutes": 30,
            "notifications_slack_enabled": True,
            "notifications_email_enabled": False,
        }
        for key, value in settings.items():
            PlatformSetting.set(key, value, user_id=eric.id)
        print("  Created platform settings")

        # ==========================================
        # COMMIT
        # ==========================================
        db.session.commit()
        print("\nSeed complete!")
        print(f"\nAdmin users:")
        print(f"  - Eric Valoz (eric.valoz@piposaude.com) — ADMIN")
        print(f"  - Fernando Galeazzo (fernando.galeazzo@piposaude.com.br) — ADMIN")
        print(f"\nOther users:")
        print(f"  - Frederico Lofredo — FINANCE")
        print(f"  - Felipe Valença — LIDER_VENDAS (Time P/M)")
        print(f"  - João Silva — EV (Time P/M)")
        print(f"  - Maria Santos — EV (Time P/M)")
        print(f"  - Pedro Oliveira — EV (Time G+)")
        print(f"  - Ana Costa — CN (Time G+)")
        print(f"\nQ1/2026: 9 policies, 4 goals, commission table v1")


if __name__ == "__main__":
    seed()
