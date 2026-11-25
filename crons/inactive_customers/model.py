from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class InactiveCustomer:
    id: int
    last_order_date: datetime


class CustomerSyncStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CustomerSyncResult:
    customer_id: int
    status: CustomerSyncStatus
    completed_at: datetime
    http_status: int | None = None
    error: str | None = None
