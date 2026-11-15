import json

from .api_client import ApiClient

BASE = "support/"
CONTENT_TYPES = {
    "pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xls": "application/vnd.ms-excel",
    "csv": "text/csv", "txt": "text/plain", "log": "text/plain",
}


def _content_type(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return CONTENT_TYPES.get(ext, "application/octet-stream")


class SupportService:
    """Issue reports ("Sorun bildir") of the shared backend app `support`."""

    def __init__(self, api: ApiClient):
        self.api = api

    async def report(self, *, category: str, message: str, context: dict, related_type: str = "",
                     related_id: str = "", attachments=(), statement_file=None, consent=False) -> dict:
        """attachments: [(name, bytes)]; statement_file: (name, bytes) or None."""
        data = {
            "category": category, "message": message, "context": json.dumps(context, ensure_ascii=False),
            "related_type": related_type, "related_id": related_id, "attachments_consent": "true" if consent else "false",
        }
        files = [("attachments", (name, content, _content_type(name))) for name, content in attachments]
        if statement_file:
            name, content = statement_file
            files.append(("statement_file", (name, content, _content_type(name))))
        return await self.api.upload(BASE + "issues/", data=data, files=files or None)

    async def reports(self) -> list:
        """The user's reports, newest first (status, developer response)."""
        return await self.api.get(BASE + "issues/")
