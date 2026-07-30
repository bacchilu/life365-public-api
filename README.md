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

Inspect the SQLite token sessions:

```bash
sqlite3 -header -column data/token-sessions.sqlite3 \
  'SELECT * FROM token_sessions;'
```

Example output:

```text
token_id                              principal_id  principal_type  issued_at                         expires_at                        revoked
------------------------------------  ------------  --------------  --------------------------------  --------------------------------  -------
388331e6-aa53-4e9e-a0a7-2c63de38c2a3  2             user            2026-07-29T12:12:02.239790+00:00  2026-08-28T12:12:02.239790+00:00  0
6b14e691-3ec1-4649-9174-12e1bc67f79d  2             user            2026-07-29T12:12:06.377408+00:00  2026-08-28T12:12:06.377408+00:00  0
```

## Docker

Build the image with a container user matching the current host user:

```bash
docker build --build-arg USER_ID="$(id -u)" --build-arg GROUP_ID="$(id -g)" -t life365-public-api:latest .
```

Run the source bundled in the image in production mode:

```bash
docker run --rm -it --env-file .env -p 8000:8000 \
  -v "$(pwd)/data:/data" life365-public-api
```

Run in development mode with automatic reload and the repository bind-mounted
at `/app`:

```bash
docker run --rm -it --env-file .env -p 8000:8000 \
  -v "$(pwd):/app" -v "$(pwd)/data:/data" \
  life365-public-api fastapi dev app/main.py \
  --host 0.0.0.0 --port 8000
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

Authentication sessions are stored in `/data/token-sessions.sqlite3`. Docker
Compose bind-mounts the repository's `data` directory at `/data`; Git tracks
the directory scaffold but ignores the generated SQLite files.

If PostgreSQL runs directly on the Docker host, use
`host.docker.internal` instead of `localhost` in `DATABASE_URL` and add this
option to `docker run` on Linux:

```text
--add-host host.docker.internal:host-gateway
```
