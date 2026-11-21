"""
Energy, computed lazily (no cron): energy = min(max, stored + (now - since) // refill). `since` is the start of the
current refill period, so partial progress is kept when energy is spent. Rewards may push energy above max; while
at or above max the refill clock is idle.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

MAX = 5
REFILL = timedelta(minutes=25)


class NotEnoughEnergy(Exception):
    pass


@dataclass(frozen=True)
class EnergyRules:
    max: int = MAX
    refill: timedelta = REFILL


@dataclass(frozen=True)
class Energy:
    stored: int
    since: datetime


def full(now: datetime, rules: EnergyRules) -> Energy:
    return Energy(stored=rules.max, since=now)


def settle(energy: Energy, now: datetime, rules: EnergyRules) -> Energy:
    """Adds the whole refill periods passed since `since`."""
    if energy.stored >= rules.max:
        return replace(energy, since=now)
    gained = max(0, (now - energy.since) // rules.refill)
    stored = min(rules.max, energy.stored + gained)
    since = now if stored >= rules.max else energy.since + gained * rules.refill
    return Energy(stored=stored, since=since)


def spend(energy: Energy, now: datetime, rules: EnergyRules, cost: int = 1) -> Energy:
    current = settle(energy, now, rules)
    if current.stored < cost:
        raise NotEnoughEnergy
    # leaving "full" starts the refill clock now; otherwise the running period continues
    since = now if current.stored >= rules.max else current.since
    return Energy(stored=current.stored - cost, since=since)


def grant(energy: Energy, now: datetime, rules: EnergyRules, amount: int = 1) -> Energy:
    """Reward energy (may exceed max)."""
    current = settle(energy, now, rules)
    return replace(current, stored=current.stored + amount)


def next_at(energy: Energy, rules: EnergyRules) -> datetime | None:
    """When the next point arrives (on a settled state); None when full."""
    return None if energy.stored >= rules.max else energy.since + rules.refill


def full_at(energy: Energy, rules: EnergyRules) -> datetime | None:
    if energy.stored >= rules.max:
        return None
    return energy.since + (rules.max - energy.stored) * rules.refill


def in_grace(joined: datetime, now: datetime, grace: timedelta) -> bool:
    """New players have no energy limit for their first days."""
    return now < joined + grace
