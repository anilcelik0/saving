"""
Reward kinds registered by client apps (in AppConfig.ready), e.g. lineup registers "lineup.energy". This shared app
calls them without importing client apps.

check(user, ref) runs when the client asks for a reward and again before granting; it raises RewardRefused when the
reward makes no sense now (energy full, run cannot continue). grant(user, ref) applies it inside the grant
transaction. A daily cap per client app limits rewarded ads per user and day.
"""

from collections.abc import Callable
from dataclasses import dataclass


class RewardRefused(Exception):
    def __init__(self, message: str, code: str = "reward_refused"):
        super().__init__(message)
        self.message, self.code = message, code


@dataclass(frozen=True)
class RewardKind:
    key: str
    check: Callable
    grant: Callable


_kinds: dict[str, RewardKind] = {}
_daily_caps: dict[str, int] = {}


def register_reward(key: str, check: Callable, grant: Callable) -> None:
    if "." not in key:
        raise ValueError('Reward keys are "<app slug>.<name>".')
    _kinds[key] = RewardKind(key, check, grant)


def set_daily_cap(app_slug: str, cap: int) -> None:
    _daily_caps[app_slug] = cap


def reward_kind(key: str) -> RewardKind | None:
    return _kinds.get(key)


def daily_cap(app_slug: str) -> int | None:
    return _daily_caps.get(app_slug)


def kinds() -> list[str]:
    return sorted(_kinds)
