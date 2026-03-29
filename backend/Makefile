.PHONY: test lint format check run migrate

run:
	flask run --debug

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	flake8 app/ tests/

format:
	black app/ tests/

check: lint test

migrate:
	flask db upgrade

migrate-new:
	flask db migrate -m "$(msg)"
