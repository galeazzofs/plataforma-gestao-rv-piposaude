#!/bin/bash
set -e

echo "Initializing database..."
python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    db.create_all()
    print('Tables created/verified.')

    from alembic.runtime.migration import MigrationContext
    conn = db.engine.connect()
    context = MigrationContext.configure(conn)
    current_rev = context.get_current_revision()
    conn.close()
    if current_rev is None:
        from flask_migrate import stamp
        stamp(revision='head')
        print('Alembic stamped at head.')
    else:
        from flask_migrate import upgrade
        upgrade()
        print('Migrations applied.')
print('Database ready.')
"

echo "Seeding database (if empty)..."
python seed.py

echo "Starting gunicorn..."
exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 4 --timeout 120
