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

```bash
fastapi dev app/main.py
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```
