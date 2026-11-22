"""
AdMob rewarded ad server-side verification (SSV). Google calls our callback URL with the reward as query
parameters, signed with ECDSA (P-256, SHA-256); the signed message is the query string before "&signature=",
signature and key_id are the last two parameters. Public keys: BILLING_ADMOB_KEYS_URL, cached for a day and refetched
once when a key id is unknown (key rotation).
"""

import base64
from urllib.parse import parse_qsl

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.cache import cache

CACHE_KEY = "billing:admob-verifier-keys"
CACHE_SECONDS = 24 * 3600


class SSVError(Exception):
    pass


def _fetch_keys() -> dict[str, str]:
    response = requests.get(settings.BILLING_ADMOB_KEYS_URL, timeout=5)
    response.raise_for_status()
    keys = {str(k["keyId"]): k["pem"] for k in response.json()["keys"]}
    cache.set(CACHE_KEY, keys, CACHE_SECONDS)
    return keys


def _public_key(key_id: str) -> str:
    keys = cache.get(CACHE_KEY)
    if not keys or key_id not in keys:
        try:
            keys = _fetch_keys()
        except (requests.RequestException, KeyError, ValueError) as e:
            raise SSVError(f"verifier keys unavailable: {e}") from e
    if key_id not in keys:
        raise SSVError(f"unknown key_id {key_id}")
    return keys[key_id]


def verify(query_string: str) -> dict[str, str]:
    """The callback's parameters when the signature is valid, else SSVError."""
    position = query_string.find("&signature=")
    if position < 0:
        raise SSVError("no signature")
    params = dict(parse_qsl(query_string, keep_blank_values=True))
    try:
        signature = base64.urlsafe_b64decode(params["signature"] + "=" * (-len(params["signature"]) % 4))
        public_key = serialization.load_pem_public_key(_public_key(params["key_id"]).encode())
        public_key.verify(signature, query_string[:position].encode(), ec.ECDSA(hashes.SHA256()))
    except (KeyError, ValueError, InvalidSignature) as e:
        raise SSVError(f"bad signature: {e!r}") from e
    params.pop("signature")
    return params
