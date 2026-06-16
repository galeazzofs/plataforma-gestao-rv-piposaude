#!/bin/bash
set -e

echo "Initializing database..."
# create_all only on a never-stamped DB (then stamp head); otherwise pure
# `alembic upgrade`. See app/bootstrap.py for why the order matters.
python -m app.bootstrap

echo "Seeding (no-op unless DEV_SEED_ALLOWED, i.e. FLASK_ENV=dev)..."
python seed.py

echo "Starting gunicorn..."
exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 4 --timeout 600
