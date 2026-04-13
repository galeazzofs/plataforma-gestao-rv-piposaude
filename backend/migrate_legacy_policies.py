"""One-time migration: seed initial_installments_paid and first_payment_real
from apolices_legado.csv into existing Policy records."""
import argparse
import csv
import unicodedata
from datetime import date

from dateutil.relativedelta import relativedelta

from app import create_app
from app.extensions import db
from app.models import Client, Policy, BenefitType

# Reference month: the last apuração before the platform launched
_LAST_APPRAISAL = date(2025, 12, 1)

_BENEFIT_MAP = {
    'saude': BenefitType.SAUDE,
    'odonto': BenefitType.ODONTO,
    'vida': BenefitType.VIDA,
}


def _normalize(s):
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower().strip())
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def _parse_date(s):
    day, month, year = s.strip().split('/')
    return date(int(year), int(month), int(day))


def _infer_first_payment(meses_pagos):
    """Work backwards from Dec 2025: month 1 = Dec, month 2 = Nov, etc."""
    return _LAST_APPRAISAL - relativedelta(months=meses_pagos - 1)


def _map_benefit(produto):
    norm = _normalize(produto)
    for key, val in _BENEFIT_MAP.items():
        if key in norm:
            return val
    return None


def run(csv_path, dry_run=False):
    """Process CSV and update matching policies. Returns (updated, skipped, missed)."""
    updated = skipped = missed = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        cliente   = (row.get('Cliente')         or '').strip()
        operadora = (row.get('Operadora')        or '').strip()
        produto   = (row.get('Produto')          or '').strip()
        inicio_raw = (row.get('Inicio_Vigencia') or '').strip()
        meses_pagos = int((row.get('Meses_Pagos') or '0').strip() or '0')

        if meses_pagos == 0 and not inicio_raw:
            print(f'[SKIP]  {cliente} | {operadora} | {produto} → Meses_Pagos=0, sem data')
            skipped += 1
            continue

        first_payment = _parse_date(inicio_raw) if inicio_raw else _infer_first_payment(meses_pagos)

        benefit = _map_benefit(produto)
        if benefit is None:
            print(f'[MISS]  {cliente} | {operadora} | {produto} → produto não mapeado')
            missed += 1
            continue

        client = Client.query.filter_by(name_normalized=_normalize(cliente)).first()
        if client is None:
            print(f'[MISS]  {cliente} → cliente não encontrado no banco')
            missed += 1
            continue

        norm_op = _normalize(operadora)
        policy = None
        for p in Policy.query.filter_by(client_id=client.id, benefit_type=benefit).all():
            if not norm_op or norm_op in _normalize(p.partner_operator or ''):
                policy = p
                break

        if policy is None:
            print(f'[MISS]  {cliente} | {operadora} | {produto} → apólice não encontrada')
            missed += 1
            continue

        if policy.is_locked:
            print(f'[SKIP]  {cliente} | {operadora} | {produto} → policy is_locked=True')
            skipped += 1
            continue

        tag = '[INFER]' if not inicio_raw else '[MATCH]'
        print(f'{tag}  {cliente} | {operadora} | {produto} → '
              f'initial_installments_paid={meses_pagos}, first_payment_real={first_payment}')

        if not dry_run:
            policy.initial_installments_paid = meses_pagos
            policy.first_payment_real = first_payment

        updated += 1

    print(f'---\nSummary: {updated} updated, {skipped} skipped, {missed} not found')
    return updated, skipped, missed


def main():
    parser = argparse.ArgumentParser(description='Seed legacy policy baselines from CSV.')
    parser.add_argument('--dry-run', action='store_true', help='Print without saving.')
    parser.add_argument('--csv', default='apolices_legado.csv', help='Path to CSV file.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(args.csv, dry_run=args.dry_run)
        if not args.dry_run:
            db.session.commit()


if __name__ == '__main__':
    main()
