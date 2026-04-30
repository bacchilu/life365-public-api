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
