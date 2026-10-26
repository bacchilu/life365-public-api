.PHONY: update build clean run test codex clean-all \
	docker-network docker-dev-up docker-dev-down docker-prod-up docker-prod-down \
	docker-test-db-up docker-test-db-down test-postgresql

HOST_USER_ID := $(shell id -u)
HOST_GROUP_ID := $(shell id -g)
DOCKER_COMPOSE := USER_ID=$(HOST_USER_ID) GROUP_ID=$(HOST_GROUP_ID) docker compose
SHARED_DOCKER_NETWORK := life365-shared
LOCAL_DB := python3 -m scripts.local_postgres

update:
	python3 -m venv .venv
	rm -rf .venv/.gitignore
	./.venv/bin/pip3 install -r requirements.txt
	./.venv/bin/pip3 freeze > requirements-lock.txt

build:
	python3 -m venv .venv
	rm -rf .venv/.gitignore
	./.venv/bin/pip3 install -r requirements-lock.txt

run: docker-test-db-up
	./.venv/bin/fastapi dev app/main.py

test:
	./.venv/bin/pytest

test-postgresql: docker-test-db-up
	$(LOCAL_DB) test

docker-network:
	docker network inspect $(SHARED_DOCKER_NETWORK) >/dev/null 2>&1 || docker network create $(SHARED_DOCKER_NETWORK)

docker-dev-up: docker-test-db-up
	$(DOCKER_COMPOSE) --profile dev build api-dev
	@trap '$(DOCKER_COMPOSE) --profile dev rm --stop --force api-dev scheduler' EXIT; \
		$(DOCKER_COMPOSE) --profile dev up --no-deps --no-build --pull never api-dev scheduler

docker-dev-down:
	$(DOCKER_COMPOSE) --profile dev rm --stop --force api-dev scheduler

docker-prod-up: docker-network docker-test-db-up
	$(DOCKER_COMPOSE) --profile prod build life365-public-api
	$(DOCKER_COMPOSE) --profile prod up --detach --no-deps --no-build --pull never life365-public-api scheduler

docker-prod-down:
	$(DOCKER_COMPOSE) --profile prod rm --stop --force life365-public-api scheduler

docker-test-db-up:
	$(LOCAL_DB) up

docker-test-db-down:
	$(LOCAL_DB) stop

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete

clean-all:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	rm -rf .venv
	rm -rf node_modules
	rm -rf .codex

codex:
	npm install @openai/codex --save-dev
	rm package.json package-lock.json
	npx codex
