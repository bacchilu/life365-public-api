from datetime import datetime, timezone
from uuid import uuid4

TOKEN_EXPIRATION_DAYS = 30


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_token_id() -> str:
    return str(uuid4())
