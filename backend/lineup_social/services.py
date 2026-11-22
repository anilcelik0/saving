"""
Challenges: created from the creator's finished run (same frozen deck), shared by link / code or sent to a username;
accepting is free (no energy) and starts a challenge run on that deck. Pushes: an invite to the target, each result
to the creator.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from lineup_games.models import Run
from lineup_games.services import GameConflict, new_challenge_run
from notifications.services import notify

from .models import Challenge, ChallengeEntry, ChallengeInvite

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
CODE_LENGTH = 6
DONE = (Run.Status.WON, Run.Status.LOST, Run.Status.FINISHED)
MODE_LABELS = dict(Run.Mode.choices)


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def link(code: str) -> str:
    return f"{settings.LINEUP_PUBLIC_URL.rstrip('/')}/lineup/c/{code}"


def get_challenge(code: str) -> Challenge:
    challenge = (Challenge.objects.select_related("creator", "source_run__attribute")
                 .filter(code=(code or "").strip().upper()).first())
    if challenge is None:
        raise NotFound("Meydan okuma bulunamadı.", code="challenge_not_found")
    return challenge


def create_challenge(user, run_id) -> Challenge:
    """From the user's finished normal run; the same run always gives the same challenge."""
    run = Run.objects.filter(user=user, pk=run_id).select_related("attribute").first()
    if run is None:
        raise NotFound("Tur bulunamadı.", code="run_not_found")
    if run.status not in DONE:
        raise GameConflict("Meydan okumak için önce turu bitir.", code="run_not_finished")
    existing = Challenge.objects.filter(source_run=run).first()
    if existing:
        return existing
    expires = timezone.now() + timedelta(days=settings.LINEUP_CHALLENGE_DAYS)
    for _ in range(10):
        try:
            with transaction.atomic():
                return Challenge.objects.create(code=_new_code(), creator=user, source_run=run, expires_at=expires)
        except IntegrityError:
            existing = Challenge.objects.filter(source_run=run).first()
            if existing:  # a parallel request created it
                return existing
    raise GameConflict("Kod üretilemedi, tekrar dene.", code="code_failed")


def _summary(challenge: Challenge) -> str:
    run = challenge.source_run
    unit = "kart" if run.mode == Run.Mode.TIMELINE else "seri"
    return f"{MODE_LABELS[run.mode]} · {run.attribute.name} · {run.score} {unit}"


@transaction.atomic
def send_challenge(user, code: str, username: str) -> ChallengeInvite:
    challenge = get_challenge(code)
    if challenge.creator_id != user.pk:
        raise GameConflict("Sadece kendi meydan okumanı gönderebilirsin.", code="not_creator")
    if challenge.expired:
        raise GameConflict("Bu meydan okumanın süresi doldu.", code="challenge_expired")
    target = (get_user_model().objects.filter(app_id=user.app_id, username=(username or "").strip().lower(),
                                              is_active=True).first())
    if target is None:
        raise NotFound("Bu kullanıcı adıyla bir oyuncu yok.", code="user_not_found")
    if target.pk == user.pk:
        raise GameConflict("Kendine meydan okuyamazsın.", code="own_challenge")
    invite, created = ChallengeInvite.objects.get_or_create(challenge=challenge, user=target)
    if created:
        notify(target, "Meydan okuma!", f"{user.username} sana meydan okudu: {_summary(challenge)}",
               data={"type": "challenge", "code": challenge.code})
    return invite


@transaction.atomic
def accept(user, code: str) -> ChallengeEntry:
    """Free: no energy. Accepting twice returns the same entry (and run)."""
    challenge = get_challenge(code)
    entry = ChallengeEntry.objects.filter(challenge=challenge, user=user).select_related("run").first()
    if entry:
        return entry
    if challenge.creator_id == user.pk:
        raise GameConflict("Kendi meydan okumanı kabul edemezsin.", code="own_challenge")
    if challenge.expired:
        raise GameConflict("Bu meydan okumanın süresi doldu.", code="challenge_expired")
    run = new_challenge_run(user, challenge.source_run)
    try:
        with transaction.atomic():
            return ChallengeEntry.objects.create(challenge=challenge, user=user, run=run)
    except IntegrityError:  # double tap: keep the first entry
        run.delete()
        return ChallengeEntry.objects.select_related("run").get(challenge=challenge, user=user)


def _outcome(mine: int, theirs: int) -> str:
    return "win" if mine > theirs else "lose" if mine < theirs else "tie"


def on_run_finished(sender, run: Run, **kwargs) -> None:
    """A challenge run ended: push the creator once."""
    if not run.is_challenge:
        return
    entry = ChallengeEntry.objects.select_related("challenge__creator", "challenge__source_run").filter(run=run).first()
    if entry is None or entry.notified:
        return
    challenge = entry.challenge
    target = challenge.source_run.score
    verdict = {"win": "seni geçti", "lose": "seni geçemedi", "tie": "berabere"}[_outcome(run.score, target)]
    notify(challenge.creator, "Meydan okuma sonucu",
           f"{run.user.username} meydan okumanı oynadı: {run.score} – {target} ({verdict})",
           data={"type": "challenge", "code": challenge.code})
    entry.notified = True
    entry.save(update_fields=["notified", "updated_at"])


# ---------------------------------------------------------------- payloads
def _entry_payload(entry: ChallengeEntry, target: int) -> dict:
    run = entry.run
    finished = run.status in DONE
    return {"username": entry.user.username, "run_id": str(run.pk), "score": run.score, "status": run.status,
            "finished": finished, "outcome": _outcome(run.score, target) if finished else None}


def challenge_payload(challenge: Challenge, viewer) -> dict:
    run = challenge.source_run
    entries = list(challenge.entries.select_related("user", "run").order_by("created_at"))
    mine = next((e for e in entries if e.user_id == viewer.pk), None)
    a = run.attribute
    return {
        "code": challenge.code, "link": link(challenge.code), "mode": run.mode, "mode_label": MODE_LABELS[run.mode],
        "attribute": {"key": a.key, "name": a.name, "unit": a.unit},
        "difficulty": run.difficulty, "creator": challenge.creator.username,
        "creator_score": run.score, "creator_status": run.status,
        "expires_at": challenge.expires_at.isoformat(), "expired": challenge.expired,
        "is_creator": challenge.creator_id == viewer.pk,
        "my_entry": _entry_payload(mine, run.score) if mine else None,
        "entries": [_entry_payload(e, run.score) for e in entries],
        "share_text": (f"{challenge.creator.username} sana Line Up'ta meydan okuyor: {_summary(challenge)}. "
                       f"Geçebilir misin? {link(challenge.code)} (kod: {challenge.code})"),
    }


def _row(challenge: Challenge, viewer) -> dict:
    run = challenge.source_run
    return {"code": challenge.code, "mode": run.mode, "mode_label": MODE_LABELS[run.mode],
            "attribute": run.attribute.name, "creator": challenge.creator.username, "creator_score": run.score,
            "expired": challenge.expired, "created_at": challenge.created_at.isoformat()}


def challenge_lists(user) -> dict:
    """Incoming (sent to me, not played yet), sent (mine) and played (accepted by me)."""
    base = Challenge.objects.select_related("creator", "source_run__attribute")
    played_ids = ChallengeEntry.objects.filter(user=user).values("challenge_id")
    incoming = (base.filter(invites__user=user, expires_at__gt=timezone.now()).exclude(pk__in=played_ids)
                .order_by("-created_at")[:20])
    sent = base.filter(creator=user).order_by("-created_at")[:20]
    entries = (ChallengeEntry.objects.filter(user=user)
               .select_related("run", "challenge__creator", "challenge__source_run__attribute")[:20])
    played = []
    for e in entries:
        row = _row(e.challenge, user)
        row["my_entry"] = _entry_payload(e, e.challenge.source_run.score)
        played.append(row)
    sent_rows = []
    for c in sent:
        row = _row(c, user)
        row["entries"] = c.entries.count()
        sent_rows.append(row)
    return {"incoming": [_row(c, user) for c in incoming], "sent": sent_rows, "played": played}
