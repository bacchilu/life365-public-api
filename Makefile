.PHONY: update build clean run codex clean-all \
	docker-dev-up docker-dev-down docker-prod-up docker-prod-down

HOST_USER_ID := $(shell id -u)
HOST_GROUP_ID := $(shell id -g)
DOCKER_COMPOSE := USER_ID=$(HOST_USER_ID) GROUP_ID=$(HOST_GROUP_ID) docker compose

# ensure-networks:
# 	docker network inspect public >/dev/null 2>&1 || docker network create public
# 	docker network inspect internal-life365-net >/dev/null 2>&1 || docker network create --internal internal-life365-net

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

docker-dev-up:
	$(DOCKER_COMPOSE) --profile dev run --rm --service-ports --build api-dev

docker-dev-down:
	$(DOCKER_COMPOSE) --profile dev down

docker-prod-up:
	$(DOCKER_COMPOSE) --profile prod up --build --detach

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

# up-dev: ensure-networks
# 	@set -e; \
# 	user_id="$$(id -u)"; \
# 	group_id="$$(id -g)"; \
# 	cd dev; \
# 	USER_ID="$$user_id" GROUP_ID="$$group_id" docker compose up

# up-prod: ensure-networks
# 	@set -e; \
# 	user_id="$$(id -u)"; \
# 	group_id="$$(id -g)"; \
# 	cd prod; \
# 	USER_ID="$$user_id" GROUP_ID="$$group_id" docker compose up -d

# down:
# 	@set -e; \
# 	user_id="$$(id -u)"; \
# 	group_id="$$(id -g)"; \
# 	cd dev; \
# 	USER_ID="$$user_id" GROUP_ID="$$group_id" docker compose down -v --rmi local; \
# 	cd ../prod; \
# 	USER_ID="$$user_id" GROUP_ID="$$group_id" docker compose down -v --rmi local

# networks-clean:
# 	if docker network inspect public >/dev/null 2>&1; then docker network rm public; fi
# 	if docker network inspect internal-life365-net >/dev/null 2>&1; then docker network rm internal-life365-net; fi
