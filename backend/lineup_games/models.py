"""Game runs (one played round) and their moves. Decks are frozen at creation: later pool changes never alter a run."""

from django.conf import settings
from django.db import models

from core.base_models import BaseModel
from lineup_cards.models import Attribute, Card

from .engine import timeline


class Run(BaseModel):
    class Mode(models.TextChoices):
        TIMELINE = "timeline", "Zaman Çizgisi"

    class Status(models.TextChoices):
        PLAYING = timeline.PLAYING, "Oynanıyor"
        WON = timeline.WON, "Kazanıldı"
        LOST = timeline.LOST, "Kaybedildi"
        FINISHED = timeline.FINISHED, "Kartlar bitti"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_runs")
    mode = models.CharField("mod", max_length=20, choices=Mode.choices)
    difficulty = models.CharField("zorluk", max_length=10, default="normal")
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="runs", verbose_name="nitelik")
    seed = models.CharField(max_length=32)
    deck = models.JSONField(default=list, help_text="Frozen card ids in play order")
    line = models.JSONField(default=list, help_text="Placed card ids, ordered by value")
    next_index = models.PositiveSmallIntegerField(default=1)
    lives = models.PositiveSmallIntegerField(default=timeline.LIVES)
    target = models.PositiveSmallIntegerField(default=timeline.TARGET)
    status = models.CharField("durum", max_length=10, choices=Status.choices, default=Status.PLAYING)
    dealt_at = models.DateTimeField(null=True, blank=True, help_text="When the current card was shown (for elapsed_ms)")
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "tur"
        verbose_name_plural = "turlar"
        indexes = [models.Index(fields=["user", "status"], name="lineup_run_user_status")]

    def __str__(self):
        return f"{self.get_mode_display()} · {self.user} · {self.get_status_display()}"

    @property
    def score(self) -> int:
        return max(0, len(self.line) - 1)

    def timeline_state(self) -> timeline.TimelineState:
        return timeline.TimelineState(deck=tuple(self.deck), line=tuple(self.line), next_index=self.next_index,
                                      lives=self.lives, target=self.target, status=self.status)

    def set_timeline_state(self, state: timeline.TimelineState) -> None:
        self.line, self.next_index, self.lives, self.status = list(state.line), state.next_index, state.lives, state.status


class Move(BaseModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="moves")
    number = models.PositiveSmallIntegerField()
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, related_name="+")
    slot = models.SmallIntegerField(null=True, blank=True, help_text="Chosen gap")
    correct = models.BooleanField()
    elapsed_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["number"]
        verbose_name = "hamle"
        verbose_name_plural = "hamleler"
        constraints = [models.UniqueConstraint(fields=["run", "number"], name="uniq_lineup_move_number")]
