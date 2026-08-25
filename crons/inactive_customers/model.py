from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InactiveCustomer:
    id: int
    last_order_date: datetime
