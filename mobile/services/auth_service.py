from config import APP_SLUG

from .api_client import ApiClient, ApiError


class AuthService:
    def __init__(self, api: ApiClient):
        self.api = api

    async def login(self, identifier: str, password: str) -> dict:
        data = await self.api.post(
            "auth/login/",
            {"app": APP_SLUG, "identifier": identifier.strip(), "password": password},
            auth=False,
        )
        await self.api.tokens.save(data["access"], data["refresh"])
        return data["user"]

    async def register(self, **fields) -> dict:
        data = await self.api.post("auth/register/", {"app": APP_SLUG, **fields}, auth=False)
        await self.api.tokens.save(data["access"], data["refresh"])
        return data["user"]

    async def me(self) -> dict:
        return await self.api.get("auth/me/")

    # ---- legal documents (privacy policy, KVKK notice) and the user's acceptances
    async def legal_documents(self) -> list:
        """Current documents (public; shown on the register screen)."""
        return await self.api.request("GET", f"legal/{APP_SLUG}/", auth=False)

    async def legal_document(self, kind: str) -> dict:
        """Current version with Markdown `body` (public)."""
        return await self.api.request("GET", f"legal/{APP_SLUG}/{kind}/", auth=False)

    async def consents(self) -> dict:
        """{"documents": [... accepted_version, accepted_at, is_accepted], "pending": [...]}"""
        return await self.api.get("auth/consents/")

    async def accept(self, document_ids: list[str]) -> dict:
        return await self.api.post("auth/consents/", {"documents": document_ids})

    async def update_me(self, **fields) -> dict:
        return await self.api.patch("auth/me/", fields)

    async def logout(self):
        refresh = self.api.tokens.refresh
        try:
            if refresh:
                await self.api.post("auth/logout/", {"refresh": refresh})
        except ApiError:
            pass  # logging out locally is enough if the server call fails
        finally:
            await self.api.tokens.clear()
