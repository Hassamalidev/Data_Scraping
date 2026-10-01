.PHONY: db-up db-down migrate rollback migrate-status scraper-install scraper-test \
	scraper-lint web-install web-test web-lint web-typecheck test lint

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

migrate: db-up
	docker compose run --rm dbmate up

rollback:
	docker compose run --rm dbmate down

migrate-status:
	docker compose run --rm dbmate status

scraper-install:
	cd scraper && uv sync

scraper-test:
	cd scraper && uv run python -m pytest

scraper-lint:
	cd scraper && uv run ruff check . && uv run black --check .

web-install:
	pnpm --dir web install

web-test:
	pnpm --dir web test

web-lint:
	pnpm --dir web lint && pnpm --dir web format:check

web-typecheck:
	pnpm --dir web typecheck

test: scraper-test web-test

lint: scraper-lint web-lint web-typecheck
