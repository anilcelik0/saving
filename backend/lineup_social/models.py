"""
Invite challenges (asynchronous): a finished run's frozen deck is shared by link / code (and optionally sent to a
username); whoever accepts plays the same cards for free, and the scores are compared.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.base_models import BaseModel
from lineup_games.models import Run


class Challenge(BaseModel):
    code = models.CharField("kod", max_length=8, unique=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_challenges")
    source_run = models.OneToOneField(Run, on_delete=models.CASCADE, related_name="challenge",
                                      help_text="The creator's finished run: deck, rules and the score to beat")
    expires_at = models.DateTimeField("bitiş")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "meydan okuma"
        verbose_name_plural = "meydan okumalar"

    def __str__(self):
        return f"{self.code} · {self.creator}"

    @property
    def expired(self) -> bool:
        return self.expires_at <= timezone.now()


class ChallengeInvite(BaseModel):
    """Sent to a username: shows in their incoming list and pushes them."""

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="invites")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_invites")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "davet"
        verbose_name_plural = "davetler"
        constraints = [models.UniqueConstraint(fields=["challenge", "user"], name="uniq_lineup_invite")]


class ChallengeEntry(BaseModel):
    """Someone accepted: their free run on the challenge deck. The creator is pushed once when it ends."""

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_entries")
    run = models.OneToOneField(Run, on_delete=models.CASCADE, related_name="challenge_entry")
    notified = models.BooleanField(default=False, help_text="Creator pushed about the result")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "katılım"
        verbose_name_plural = "katılımlar"
        constraints = [models.UniqueConstraint(fields=["challenge", "user"], name="uniq_lineup_entry")]
