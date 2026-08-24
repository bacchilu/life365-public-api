.PHONY: update build clean run codex clean-all \
	docker-network docker-dev-up docker-dev-down docker-prod-up docker-prod-down

HOST_USER_ID := $(shell id -u)
HOST_GROUP_ID := $(shell id -g)
DOCKER_COMPOSE := USER_ID=$(HOST_USER_ID) GROUP_ID=$(HOST_GROUP_ID) docker compose
SHARED_DOCKER_NETWORK := life365-shared

update:
	python3 -m venv .venv
	rm -rf .venv/.gitignore
	./.venv/bin/pip3 install -r requirements.txt
	./.venv/bin/pip3 freeze > requirements-lock.txt

build:
	python3 -m venv .venv
	rm -rf .venv/.gitignore
	./.venv/bin/pip3 install -r requirements-lock.txt

run:
	./.venv/bin/fastapi dev app/main.py

docker-network:
	docker network inspect $(SHARED_DOCKER_NETWORK) >/dev/null 2>&1 || docker network create $(SHARED_DOCKER_NETWORK)

docker-dev-up:
	$(DOCKER_COMPOSE) --profile dev build api-dev
	@trap '$(DOCKER_COMPOSE) --profile dev down' EXIT; \
		$(DOCKER_COMPOSE) --profile dev up --no-build --pull never

docker-dev-down:
	$(DOCKER_COMPOSE) --profile dev down

docker-prod-up: docker-network
	$(DOCKER_COMPOSE) --profile prod build life365-public-api
	$(DOCKER_COMPOSE) --profile prod up --detach --no-build --pull never

docker-prod-down:
	$(DOCKER_COMPOSE) --profile prod down

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
