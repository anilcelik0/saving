from .api_client import ApiClient

BASE = "saving/budget/"


def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if v not in (None, "")}


class Resource:
    """Generic REST resource: list/get/create/update/delete."""

    def __init__(self, api: ApiClient, path: str, base: str = BASE):
        self.api = api
        self.path = base + path

    async def list(self, **params):
        return await self.api.get(self.path, params=_clean(params))

    async def get(self, obj_id):
        return await self.api.get(f"{self.path}{obj_id}/")

    async def create(self, data: dict):
        return await self.api.post(self.path, data)

    async def update(self, obj_id, data: dict):
        return await self.api.patch(f"{self.path}{obj_id}/", data)

    async def delete(self, obj_id):
        return await self.api.delete(f"{self.path}{obj_id}/")


class Transactions(Resource):
    """Single money-movement resource. scope: 'this' | 'following' (series occurrences)."""

    async def update(self, obj_id, data: dict, scope: str = "this"):
        return await self.api.patch(f"{self.path}{obj_id}/?scope={scope}", data)

    async def delete(self, obj_id, scope: str = "this"):
        return await self.api.delete(f"{self.path}{obj_id}/?scope={scope}")

    async def upcoming(self, days: int = 30) -> list:
        return await self.api.get(self.path + "upcoming/", params={"days": days})

    async def pay(self, obj_id, amount: str | None = None, date: str | None = None) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/pay/", _clean({"amount": amount, "date": date}))

    async def unpay(self, obj_id) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/unpay/", {})

    async def bulk_status(self, account_id, date_from: str, date_to: str, status: str) -> dict:
        """Mark all card transactions of an account cycle as 'paid' or 'pending'."""
        return await self.api.post(self.path + "bulk-status/", {
            "account": account_id, "date_from": date_from, "date_to": date_to, "status": status,
        })

    async def cancel(self, obj_id) -> dict:
        """Refunded purchase / skipped occurrence: kept in history, excluded from totals."""
        return await self.api.post(f"{self.path}{obj_id}/cancel/", {})

    async def restore(self, obj_id) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/restore/", {})


CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class Statements(Resource):
    """Upload -> poll get() until status 'ready' -> lines() / update_line() -> confirm()."""

    async def upload(self, account_id, filename: str, content: bytes, exclude_from_balance=False) -> dict:
        ext = filename.rsplit(".", 1)[-1].lower()
        files = {"file": (filename, content, CONTENT_TYPES.get(ext, "application/octet-stream"))}
        data = {"account": account_id, "exclude_from_balance": "true" if exclude_from_balance else "false"}
        return await self.api.upload(self.path, data=data, files=files)

    async def lines(self, statement_id) -> list:
        return await self.api.get(f"{self.path}{statement_id}/lines/")

    async def update_line(self, line_id, data: dict) -> dict:
        return await self.api.patch(f"{BASE}statement-lines/{line_id}/", data)

    async def confirm(self, statement_id, delete_after: bool = True) -> dict:
        """delete_after: remove statement record + lines after importing (imported transactions stay)."""
        return await self.api.post(f"{self.path}{statement_id}/confirm/", {"delete_after": delete_after})


class BudgetService:
    def __init__(self, api: ApiClient):
        self.api = api
        self.categories = Resource(api, "categories/")  # not paginated
        self.accounts = Resource(api, "accounts/")  # not paginated
        self.transactions = Transactions(api, "transactions/")  # paginated
        self.statements = Statements(api, "statements/")  # paginated
        self.category_rules = Resource(api, "category-rules/")  # learned merchant -> category; list/delete

    async def series(self, active: bool = True) -> list:
        """Recurring/installment plans with their next pending occurrence."""
        return await self.api.get(BASE + "series/", params={"active": "true" if active else "false"})

    async def activity(self, month: str) -> list:
        """History items for 'YYYY-MM': transaction rows + one row per card statement cycle."""
        return await self.api.get(BASE + "activity/", params={"month": month})

    async def activity_upcoming(self, days: int = 30) -> list:
        return await self.api.get(BASE + "activity/upcoming/", params={"days": days})

    async def summary(self, month: str | None = None) -> dict:
        """month: 'YYYY-MM' (default current)."""
        return await self.api.get(BASE + "summary/", params=_clean({"month": month}))
