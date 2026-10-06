from datetime import date

from .engine import BeancountQuery


class LedgerService:
    def __init__(self, gateway: BeancountQuery):
        self.gateway = gateway

    def execute(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        start, end = payload.get("start_date"), payload.get("end_date")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("start_date and end_date must be strings")
        start, end = date.fromisoformat(start), date.fromisoformat(end)
        if end < start:
            raise ValueError("end_date must not be earlier than start_date")
        if (end - start).days >= 366:
            raise ValueError("date range must not exceed 366 days")
        limit = payload.get("max_transactions", 500)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise ValueError("max_transactions must be between 1 and 500")
        return self.gateway.query(start, end, limit)
