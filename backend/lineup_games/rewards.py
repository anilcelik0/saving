"""
Line Up rewards for the shared billing app (registered in apps.ready): a rewarded ad gives +1 energy, or one
continue for a lost run. check() runs when the client asks and again when AdMob's verified callback arrives.
"""

from django.conf import settings
from django.utils import timezone

from billing.registry import RewardRefused, register_reward, set_daily_cap

from . import services
from .engine import energy, streak, timeline
from .models import Energy, Run

ENERGY = "lineup.energy"
CONTINUE = "lineup.continue"


def check_energy(user, ref: str) -> None:
    now = timezone.now()
    if services.unlimited_until(user, now):
        raise RewardRefused("Enerjin zaten sınırsız.", code="energy_unlimited")
    if services.energy_payload(user, now)["current"] >= services.energy_rules().max:
        raise RewardRefused("Enerjin zaten dolu.", code="energy_full")


def grant_energy(user, ref: str) -> None:
    now = timezone.now()
    rules = services.energy_rules()
    row, _ = Energy.objects.select_for_update().get_or_create(user=user, defaults={"stored": rules.max, "since": now})
    row.set_state(energy.grant(energy.settle(row.state(), now, rules), now, rules, 1))
    row.save()


def _run(user, ref: str) -> Run:
    run = Run.objects.filter(user=user, pk=ref).first() if ref else None
    if run is None:
        raise RewardRefused("Tur bulunamadı.", code="run_not_found")
    return run


def can_continue(run: Run) -> bool:
    if run.mode == Run.Mode.STREAK:
        return streak.can_continue(run.streak_state())
    return timeline.can_continue(run.timeline_state())


def check_continue(user, ref: str) -> None:
    if not can_continue(_run(user, ref)):
        raise RewardRefused("Bu tur devam ettirilemez.", code="cannot_continue")


def grant_continue(user, ref: str) -> None:
    run = Run.objects.select_for_update().filter(user=user, pk=ref).first()
    if run is None or not can_continue(run):
        raise RewardRefused("Bu tur devam ettirilemez.", code="cannot_continue")
    services.resume_run(run)


def register() -> None:
    register_reward(ENERGY, check_energy, grant_energy)
    register_reward(CONTINUE, check_continue, grant_continue)
    set_daily_cap("lineup", settings.LINEUP_DAILY_AD_CAP)
