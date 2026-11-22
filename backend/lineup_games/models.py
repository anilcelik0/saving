"""
Game runs (one played round), their moves, energy and the daily puzzle. Decks are frozen at creation: later pool
changes never alter a run or a puzzle.
"""

from django.conf import settings
from django.db import models

from core.base_models import BaseModel
from lineup_cards.models import Attribute, Card

from .engine import daily, energy, status, streak, timeline


class Run(BaseModel):
    class Mode(models.TextChoices):
        TIMELINE = "timeline", "Zaman Çizgisi"
        STREAK = "streak", "Seri"

    class Status(models.TextChoices):
        PLAYING = status.PLAYING, "Oynanıyor"
        WON = status.WON, "Kazanıldı"
        LOST = status.LOST, "Kaybedildi"
        FINISHED = status.FINISHED, "Kartlar bitti"
        ABANDONED = status.ABANDONED, "Yarıda bırakıldı"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_runs")
    mode = models.CharField("mod", max_length=20, choices=Mode.choices)
    difficulty = models.CharField("zorluk", max_length=10, default="normal")
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="runs", verbose_name="nitelik")
    seed = models.CharField(max_length=32)
    deck = models.JSONField(default=list, help_text="Frozen card ids in play order")
    line = models.JSONField(default=list, help_text="Timeline: placed card ids, ordered by value")
    next_index = models.PositiveSmallIntegerField(default=1)
    lives = models.PositiveSmallIntegerField(default=timeline.LIVES)
    target = models.PositiveSmallIntegerField(default=timeline.TARGET, help_text="Timeline: line length that wins")
    score = models.PositiveSmallIntegerField("skor", default=0, help_text="Timeline: cards placed; Streak: streak length")
    continues_used = models.PositiveSmallIntegerField(default=0, help_text="Streak: continues after a loss")
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

    def timeline_state(self) -> timeline.TimelineState:
        return timeline.TimelineState(deck=tuple(self.deck), line=tuple(self.line), next_index=self.next_index,
                                      lives=self.lives, target=self.target, status=self.status)

    def set_timeline_state(self, state: timeline.TimelineState) -> None:
        self.line, self.next_index, self.lives, self.status = list(state.line), state.next_index, state.lives, state.status
        self.score = state.score

    def streak_state(self) -> streak.StreakState:
        return streak.StreakState(deck=tuple(self.deck), next_index=self.next_index, lives=self.lives,
                                  score=self.score, continues_used=self.continues_used, status=self.status)

    def set_streak_state(self, state: streak.StreakState) -> None:
        self.next_index, self.lives, self.score = state.next_index, state.lives, state.score
        self.continues_used, self.status = state.continues_used, state.status


class Move(BaseModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="moves")
    number = models.PositiveSmallIntegerField()
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, related_name="+")
    slot = models.SmallIntegerField(null=True, blank=True, help_text="Timeline: chosen gap")
    guess = models.CharField(max_length=10, blank=True, help_text="Streak: higher / lower")
    correct = models.BooleanField()
    elapsed_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["number"]
        verbose_name = "hamle"
        verbose_name_plural = "hamleler"
        constraints = [models.UniqueConstraint(fields=["run", "number"], name="uniq_lineup_move_number")]


class Energy(BaseModel):
    """Lazy energy (engine/energy.py): stored points + start of the current refill period. Created full."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_energy")
    stored = models.PositiveSmallIntegerField(default=energy.MAX)
    since = models.DateTimeField()

    class Meta:
        verbose_name = "enerji"
        verbose_name_plural = "enerji"

    def __str__(self):
        return f"{self.user} · {self.stored}"

    def state(self) -> energy.Energy:
        return energy.Energy(stored=self.stored, since=self.since)

    def set_state(self, state: energy.Energy) -> None:
        self.stored, self.since = state.stored, state.since


class DailyPuzzle(BaseModel):
    """The same cards for everyone on one day (Europe/Istanbul). Created by the first request of the day."""

    date = models.DateField("tarih", unique=True)
    number = models.PositiveIntegerField("no", unique=True)
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="daily_puzzles",
                                  verbose_name="nitelik")
    seed = models.CharField(max_length=32)
    deck = models.JSONField(default=list, help_text="Frozen card ids in the order they are shown")

    class Meta:
        ordering = ["-date"]
        verbose_name = "günlük bulmaca"
        verbose_name_plural = "günlük bulmacalar"

    def __str__(self):
        return f"#{self.number} · {self.date}"


class DailyPlay(BaseModel):
    """One user's attempts at one puzzle. Free (no energy); at most engine.daily.ATTEMPTS attempts."""

    class Status(models.TextChoices):
        PLAYING = status.PLAYING, "Oynanıyor"
        WON = status.WON, "Çözüldü"
        LOST = status.LOST, "Çözülemedi"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lineup_daily_plays")
    puzzle = models.ForeignKey(DailyPuzzle, on_delete=models.CASCADE, related_name="plays")
    attempts = models.JSONField(default=list, help_text='[{"order": [card ids], "marks": [right|near|wrong]}]')
    status = models.CharField("durum", max_length=10, choices=Status.choices, default=Status.PLAYING)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "günlük bulmaca oyunu"
        verbose_name_plural = "günlük bulmaca oyunları"
        constraints = [models.UniqueConstraint(fields=["user", "puzzle"], name="uniq_lineup_daily_play")]

    def __str__(self):
        return f"{self.puzzle} · {self.user} · {self.get_status_display()}"

    def state(self) -> daily.DailyState:
        return daily.DailyState(deck=tuple(self.puzzle.deck), attempts=tuple(tuple(a["order"]) for a in self.attempts),
                                status=self.status)

    @property
    def solved_in(self) -> int | None:
        return len(self.attempts) if self.status == self.Status.WON else None
