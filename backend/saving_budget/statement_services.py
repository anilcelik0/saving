"""Statement import pipeline: parse (Celery) -> preview lines -> user review -> confirm into Transactions."""

import hashlib
import logging
from datetime import timedelta

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Category, Kind, StatementImport, StatementLine, Transaction
from .statements import StatementParseError, detect_and_parse
from .statements.classify import skip_reason, suggest_category_name
from .statements.utils import normalize

logger = logging.getLogger(__name__)

MATCH_WINDOW_DAYS = 7


def line_key(bank: str, parsed, occurrence: int) -> str:
    """Stable dedupe key: bank reference if present, else hash of date/amount/description/occurrence."""
    if parsed.external_ref:
        return f"{bank}:{parsed.external_ref}"[:80]
    raw = f"{parsed.date.isoformat()}|{parsed.amount}|{normalize(parsed.description)}|{occurrence}"
    return f"{bank}:h:{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


def _find_pending_match(statement, line, taken_ids):
    """Pending transaction on the same account with the same amount/kind near the line date.
    Installment lines use the whole statement period (statement shows the original purchase date)."""
    if line.installment and statement.period_start and statement.period_end:
        start = statement.period_start - timedelta(days=MATCH_WINDOW_DAYS)
        end = statement.period_end + timedelta(days=MATCH_WINDOW_DAYS)
    else:
        start = line.date - timedelta(days=MATCH_WINDOW_DAYS)
        end = line.date + timedelta(days=MATCH_WINDOW_DAYS)
    candidates = (
        Transaction.objects.filter(
            account=statement.account, status=Transaction.Status.PENDING, kind=line.kind,
            amount=line.amount, date__range=(start, end),
        )
        .exclude(pk__in=taken_ids)
        .order_by("date")
    )
    return min(candidates, key=lambda t: abs((t.date - line.date).days), default=None)


def parse_statement(statement_id) -> None:
    statement = StatementImport.objects.select_related("account").get(pk=statement_id)
    statement.status = StatementImport.Status.PARSING
    statement.save(update_fields=["status", "updated_at"])
    try:
        parsed = detect_and_parse(statement.file.path)
        _build_lines(statement, parsed)
    except StatementParseError as exc:
        _fail(statement, str(exc))
    except Exception:
        logger.exception("Statement %s parse failed", statement_id)
        _fail(statement, "Ekstre okunurken beklenmeyen bir hata oluştu.")
    finally:
        if statement.file:
            statement.file.delete(save=False)  # personal data: keep only parsed lines
            StatementImport.objects.filter(pk=statement.pk).update(file="")


def _fail(statement, message):
    StatementImport.objects.filter(pk=statement.pk).update(
        status=StatementImport.Status.FAILED, error=message[:255], updated_at=timezone.now()
    )


@db_transaction.atomic
def _build_lines(statement, parsed):
    categories = {
        (c.kind, c.name.casefold()): c
        for c in Category.objects.filter(user=statement.user, is_archived=False)
    }
    existing_keys = set(
        Transaction.objects.filter(account=statement.account).exclude(external_key="").values_list("external_key", flat=True)
    )
    seen, taken, lines = {}, set(), []
    for no, p in enumerate(parsed.lines, start=1):
        base = (p.date, p.amount, normalize(p.description))
        seen[base] = seen.get(base, 0) + 1
        key = line_key(parsed.bank, p, seen[base])
        kind = Kind.EXPENSE if p.amount < 0 else Kind.INCOME
        line = StatementLine(
            statement=statement, line_no=no, date=p.date, description=p.description[:255],
            raw_text=p.raw_text, kind=kind, amount=abs(p.amount), installment=p.installment, external_key=key,
        )
        name = suggest_category_name(p)
        line.category = categories.get((kind, name.casefold())) if name else None

        reason = "duplicate" if key in existing_keys else skip_reason(p, parsed.holder_name)
        if reason:
            line.action, line.skip_reason = StatementLine.Action.SKIP, reason
        elif match := _find_pending_match(statement, line, taken):
            line.action, line.matched_transaction = StatementLine.Action.MATCH, match
            taken.add(match.pk)
        lines.append(line)

    StatementLine.objects.bulk_create(lines)
    statement.bank = parsed.bank
    statement.statement_type = parsed.statement_type
    statement.period_start, statement.period_end = parsed.period_start, parsed.period_end
    statement.closing_balance = parsed.closing_balance
    statement.status = StatementImport.Status.READY
    statement.error = ""
    statement.save()


@db_transaction.atomic
def confirm_statement(statement: StatementImport) -> StatementImport:
    """Create paid transactions (import) / mark matched pending ones paid (match). Duplicates re-checked."""
    statement = StatementImport.objects.select_for_update().get(pk=statement.pk)
    if statement.status != StatementImport.Status.READY:
        raise ValidationError({"detail": "Bu ekstre aktarılmaya hazır değil."})

    existing_keys = set(
        Transaction.objects.filter(account=statement.account).exclude(external_key="").values_list("external_key", flat=True)
    )
    imported = matched = 0
    for line in statement.lines.select_related("matched_transaction"):
        if line.action == StatementLine.Action.SKIP or line.external_key in existing_keys:
            continue
        pending = line.matched_transaction
        if line.action == StatementLine.Action.MATCH and pending and pending.status == Transaction.Status.PENDING:
            pending.status, pending.paid_on = Transaction.Status.PAID, line.date
            pending.amount, pending.external_key = line.amount, line.external_key
            pending.save(update_fields=["status", "paid_on", "amount", "external_key", "updated_at"])
            line.result_transaction = pending
            matched += 1
        else:
            line.result_transaction = Transaction.objects.create(
                user=statement.user, account=statement.account, kind=line.kind, amount=line.amount,
                date=line.date, status=Transaction.Status.PAID, paid_on=line.date,
                description=line.description, category=line.category,
                source=Transaction.Source.STATEMENT, external_key=line.external_key,
            )
            imported += 1
        existing_keys.add(line.external_key)
        line.save(update_fields=["result_transaction", "updated_at"])

    statement.status = StatementImport.Status.IMPORTED
    statement.imported_count, statement.matched_count = imported, matched
    statement.save(update_fields=["status", "imported_count", "matched_count", "updated_at"])
    return statement
