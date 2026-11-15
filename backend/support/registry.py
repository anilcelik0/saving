"""
Related-object snapshots for issue reports. Client apps register a provider for their own object types
(e.g. saving_budget registers "saving.statement"), so this shared app never imports client apps.

A provider is called as provider(user, object_id) and returns a JSON-serializable dict describing the user's
object (stored on the report, so it stays readable after the object is deleted), or None if the object does not
exist or belongs to someone else.
"""

_providers: dict = {}


def register_related_provider(related_type: str, provider) -> None:
    _providers[related_type] = provider


def related_types() -> list[str]:
    return sorted(_providers)


def related_snapshot(user, related_type: str, object_id: str):
    provider = _providers.get(related_type)
    return provider(user, object_id) if provider else None
