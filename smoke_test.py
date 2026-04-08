"""End-to-end smoke test for the new financeiro+apuração flow.
Run inside backend container after migrations + seed are applied."""
from app import create_app
from app.extensions import db
from app.modules.financial.parser import parse_financial_xlsx
from app.modules.financial.processor import persist_financial_rows
from app.modules.commissions.calculator import (
    run_quarterly_appraisal,
    validate_achievements_for_appraisal,
    MissingAchievementsError,
)
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    EvQuarterAchievement, Commission, FinancialImport,
)
from decimal import Decimal
from datetime import date

app = create_app()
with app.app_context():
    print("=" * 50)
    print("STEP 1: Parse real XLSX (Q1/2026)")
    print("=" * 50)
    parsed = parse_financial_xlsx('/tmp/real.xlsx', target_quarter=1, target_year=2026)
    s = parsed['stats']
    print(f"  Total lidas: {s['total_lidas']}")
    print(f"  Descartadas (status): {s['descartadas_status']}")
    print(f"  Descartadas (período): {s['descartadas_periodo']}")
    print(f"  Descartadas (vazias): {s['descartadas_vazias']}")
    print(f"  Persistidas: {s['persistidas']}")

    print()
    print("=" * 50)
    print("STEP 2: Persist to financial_imports")
    print("=" * 50)
    admin = User.query.filter_by(email='eric.valoz@piposaude.com').first()
    batch_id = persist_financial_rows(parsed['rows'], 1, 2026, 'real.xlsx', admin.id)
    db.session.commit()
    print(f"  Batch ID: {batch_id}")
    print(f"  Total in DB: {FinancialImport.query.filter_by(quarter=1, year=2026).count()}")

    print()
    print("=" * 50)
    print("STEP 3: Validate achievements")
    print("=" * 50)
    missing = validate_achievements_for_appraisal(1, 2026)
    if missing:
        print(f"  Missing count: {len(missing)}")
        print(f"  Sample: {missing[:5]}")
        for u in User.query.filter_by(role=UserRole.EV, active=True).all():
            for q, y in [(4, 2025), (1, 2026), (3, 2025), (2, 2025), (1, 2025)]:
                ach = EvQuarterAchievement.query.filter_by(
                    ev_id=u.id, quarter=q, year=y).first()
                if not ach:
                    ach = EvQuarterAchievement(
                        ev_id=u.id, quarter=q, year=y,
                        achievement_pct=Decimal('0.75'),
                    )
                    db.session.add(ach)
        db.session.commit()
        print("  Seeded achievements for active EVs (Q1-Q4/2025 + Q1/2026 @ 75%)")
        missing = validate_achievements_for_appraisal(1, 2026)
        print(f"  After seed: missing={len(missing)}")

    print()
    print("=" * 50)
    print("STEP 4: Run quarterly appraisal")
    print("=" * 50)
    try:
        result = run_quarterly_appraisal(1, 2026)
        db.session.commit()
        print(f"  Result: {result}")
    except MissingAchievementsError as e:
        print(f"  MISSING: count={len(e.missing)}, sample={e.missing[:5]}")

    print()
    print("=" * 50)
    print("STEP 5: Outcome")
    print("=" * 50)
    statuses = ['MATCHED', 'UNMATCHED', 'EXPIRED', 'PRE_VIGENCIA', 'PRODUTO_NAO_SUPORTADO']
    for st in statuses:
        c = FinancialImport.query.filter_by(
            quarter=1, year=2026, match_status=st).count()
        print(f"  {st}: {c}")

    commissions = Commission.query.filter_by(quarter=1, year=2026).all()
    print(f"  Commissions created: {len(commissions)}")
    total = sum((c.total_actual or Decimal('0')) for c in commissions)
    print(f"  Total commission: R$ {total:.2f}")

    # Per EV breakdown
    by_ev = {}
    for c in commissions:
        ev = User.query.get(c.ev_id)
        name = ev.name if ev else str(c.ev_id)
        by_ev[name] = by_ev.get(name, Decimal('0')) + (c.total_actual or Decimal('0'))
    print("  Per EV:")
    for name, total in sorted(by_ev.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {name}: R$ {total:.2f}")
