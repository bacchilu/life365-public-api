# Life365 Public API

FastAPI application for Life365 public APIs.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
pip3 freeze > requirements-lock.txt
```

## Run

Create a local `.env` file from the example and set the real database URL:

```bash
cp .env.example .env
```

`.env` is ignored by git.

```bash
fastapi dev app/main.py
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok", "db": "ok"}
```

## Docker

Build the image with a container user matching the current host user:

```bash
docker build --build-arg USER_ID="$(id -u)" --build-arg GROUP_ID="$(id -g)" -t life365-public-api:latest .
```

Run the source bundled in the image in production mode:

```bash
docker run --rm -it --env-file .env -p 8000:8000 life365-public-api
```

Run in development mode with automatic reload and the repository bind-mounted
at `/app`:

```bash
docker run --rm -it --env-file .env -p 8000:8000 -v "$(pwd):/app" life365-public-api fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

The same modes are available through Docker Compose. Start development mode
with:

```bash
make docker-dev-up
```

Start production mode in the background with:

```bash
make docker-prod-up
```

Stop the corresponding Compose services with:

```bash
make docker-dev-down
make docker-prod-down
```

The production service joins the external `life365-shared` network and exposes
port `8000` only to containers on that network. The production Make target
creates the shared network when it does not already exist.

The production command intentionally uses one worker while authentication
sessions are held in process-local memory. Configure a shared durable session
store before scaling to multiple workers or containers.

If PostgreSQL runs directly on the Docker host, use
`host.docker.internal` instead of `localhost` in `DATABASE_URL` and add this
option to `docker run` on Linux:

```text
--add-host host.docker.internal:host-gateway
```
