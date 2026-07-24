from datetime import datetime
from decimal import Decimal

from pydantic import TypeAdapter

DATETIME_ADAPTER = TypeAdapter(datetime)
DECIMAL_ADAPTER = TypeAdapter(Decimal)
