"""Statement import pipeline: parse (Celery) -> preview lines -> user review -> confirm into Transactions."""

import hashlib
import logging
from collections import Counter
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Category, Kind, MerchantCategoryRule, StatementImport, StatementLine, Transaction
from .services import FALLBACK_CATEGORY
from .statements import StatementParseError, detect_and_parse
from .statements.registry import BANK_LABELS
from .statements.classify import merchant_key, skip_reason, suggest_category_name
from .statements.utils import normalize

logger = logging.getLogger(__name__)

MATCH_WINDOW_DAYS = 7
REFUND_WINDOW_DAYS = 90
Action, SkipReason = StatementLine.Action, StatementLine.SkipReason


def line_key(bank: str, parsed, occurrence: int) -> str:
    """Stable dedupe key: bank reference if present, else hash of date/amount/description/occurrence."""
    if parsed.external_ref:
        return f"{bank}:{parsed.external_ref}"[:80]
    raw = f"{parsed.date.isoformat()}|{parsed.amount}|{normalize(parsed.description)}|{occurrence}"
    return f"{bank}:h:{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


def imported_keys(account) -> set[str]:
    """Keys already imported to this account: transactions + refund lines (which create no transaction)."""
    keys = set(Transaction.objects.filter(account=account).exclude(external_key="").values_list("external_key", flat=True))
    keys |= set(
        StatementLine.objects.filter(
            statement__account=account, statement__status=StatementImport.Status.IMPORTED, action=Action.REFUND
        ).values_list("external_key", flat=True)
    )
    return keys


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


def _link_refunds(statement, lines, taken_ids):
    """
    Card refunds (money in) cancel the original purchase: same amount + same merchant,
    first within this statement, then among paid transactions of the last 90 days.
    """
    used_lines = set()
    for refund in lines:
        if refund.kind != Kind.INCOME or refund.action == Action.SKIP:
            continue
        key = merchant_key(refund.description)
        if not key:
            continue
        same_statement = [
            x for x in lines
            if x.kind == Kind.EXPENSE and x.action != Action.SKIP and x.amount == refund.amount
            and x.pk not in used_lines and merchant_key(x.description) == key
        ]
        if same_statement:
            target = min(same_statement, key=lambda x: abs((x.date - refund.date).days))
            refund.action, refund.refund_target_line = Action.REFUND, target
            used_lines.add(target.pk)
            continue
        existing = [
            t for t in Transaction.objects.filter(
                account=statement.account, kind=Kind.EXPENSE, amount=refund.amount,
                status__in=(Transaction.Status.PAID, Transaction.Status.CANCELLED),
                date__range=(refund.date - timedelta(days=REFUND_WINDOW_DAYS), refund.date),
            ).exclude(pk__in=taken_ids)
            if merchant_key(t.description) == key
        ]
        paid = [t for t in existing if t.status == Transaction.Status.PAID]
        if paid:
            target = max(paid, key=lambda t: t.date)
            refund.action, refund.matched_transaction = Action.REFUND, target
            taken_ids.add(target.pk)
        elif existing:
            # purchase already cancelled by this refund in an earlier import (statement data may be deleted)
            refund.action, refund.skip_reason = Action.SKIP, SkipReason.DUPLICATE
            taken_ids.add(existing[0].pk)


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
    learned = {
        (r.kind, r.merchant_key): r
        for r in MerchantCategoryRule.objects.filter(user=statement.user).select_related("category")
    }
    rule_hits = Counter()
    existing_keys = imported_keys(statement.account)
    # Earlier imports by date + amount + kind: catches the same row read with a slightly different description
    # (e.g. after a reader update), counted so two real same-day same-amount purchases are not merged.
    imported = Counter(
        Transaction.objects.filter(account=statement.account).exclude(external_key="")
        .values_list("date", "amount", "kind")
    )
    seen, keys = {}, []
    for p in parsed.lines:
        base = (p.date, p.amount, normalize(p.description))
        seen[base] = seen.get(base, 0) + 1
        keys.append(line_key(parsed.bank, p, seen[base]))
    for p, key in zip(parsed.lines, keys):
        slot = (p.date, abs(p.amount), Kind.EXPENSE if p.amount < 0 else Kind.INCOME)
        if key in existing_keys and imported[slot] > 0:
            imported[slot] -= 1  # exact matches use up their slot first
    taken, lines = set(), []
    for no, (p, key) in enumerate(zip(parsed.lines, keys), start=1):
        kind = Kind.EXPENSE if p.amount < 0 else Kind.INCOME
        line = StatementLine(
            statement=statement, line_no=no, date=p.date, description=p.description[:255],
            raw_text=p.raw_text, kind=kind, amount=abs(p.amount), installment=p.installment, external_key=key,
        )
        # 1) user's learned merchant rule, 2) built-in reasoning, 3) fallback category
        rule = learned.get((kind, merchant_key(p.description)))
        if rule and not rule.category.is_archived:
            line.category = rule.category
            rule_hits[rule.pk] += 1
        else:
            name = suggest_category_name(p, parsed.statement_type)
            line.category = categories.get((kind, name.casefold())) or categories.get(
                (kind, FALLBACK_CATEGORY[kind].casefold())
            )

        slot = (p.date, abs(p.amount), kind)
        if key in existing_keys:
            reason = "duplicate"
        elif imported[slot] > 0 and p.hint != "card_payment":
            imported[slot] -= 1
            reason = "duplicate"
        else:
            reason = skip_reason(p, parsed.holder_name)
        if reason:
            line.action, line.skip_reason = Action.SKIP, reason
        elif not statement.exclude_from_balance and (match := _find_pending_match(statement, line, taken)):
            line.action, line.matched_transaction = Action.MATCH, match
            taken.add(match.pk)
        lines.append(line)

    if parsed.statement_type == "card":
        _link_refunds(statement, lines, taken)

    StatementLine.objects.bulk_create(lines)
    for rule_id, hits in rule_hits.items():
        MerchantCategoryRule.objects.filter(pk=rule_id).update(hits=F("hits") + hits)
    statement.bank = parsed.bank
    statement.is_generic = parsed.generic
    statement.statement_type = parsed.statement_type
    statement.period_start, statement.period_end = parsed.period_start, parsed.period_end
    statement.closing_balance = parsed.closing_balance
    statement.check_status, statement.check_message = parsed.check_status, parsed.check_message
    statement.status = StatementImport.Status.READY
    statement.error = ""
    statement.save()


def apply_learned_category(line: StatementLine) -> int:
    """After the user picks a category for a preview line: remember it and apply to same-merchant lines."""
    from .services import learn_category

    key = learn_category(line.statement.user, line.kind, line.description, line.category)
    if not key:
        return 0
    same = [
        x.pk for x in line.statement.lines.filter(kind=line.kind).exclude(pk=line.pk)
        if merchant_key(x.description) == key
    ]
    return StatementLine.objects.filter(pk__in=same).update(category=line.category, updated_at=timezone.now())


def _is_card(statement) -> bool:
    return statement.statement_type == StatementImport.StatementType.CARD


def _create_from_line(statement, line):
    is_card = _is_card(statement)
    return Transaction.objects.create(
        user=statement.user, account=statement.account, kind=line.kind, amount=line.amount,
        date=line.date, status=Transaction.Status.PAID, paid_on=line.date,
        description=line.description, category=line.category,
        is_card=is_card, cycle_end=statement.period_end if is_card else None,
        in_balance=not statement.exclude_from_balance,
        source=Transaction.Source.STATEMENT, external_key=line.external_key,
    )


@db_transaction.atomic
def confirm_statement(statement: StatementImport) -> StatementImport:
    """
    Create paid transactions (import), mark matched pending ones paid (match),
    cancel refunded purchases (refund). Duplicates are re-checked.
    """
    statement = StatementImport.objects.select_for_update().get(pk=statement.pk)
    if statement.status != StatementImport.Status.READY:
        raise ValidationError({"detail": "Bu ekstre aktarılmaya hazır değil."})

    existing_keys = imported_keys(statement.account)
    imported = matched = cancelled = 0
    lines = list(statement.lines.select_related("matched_transaction", "refund_target_line"))
    # refunds last: their target purchase line must be imported first
    for line in sorted(lines, key=lambda x: x.action == Action.REFUND):
        if line.action == Action.SKIP or line.external_key in existing_keys:
            continue
        if line.action == Action.REFUND:
            target = line.matched_transaction
            if line.refund_target_line_id:
                target_line = next(x for x in lines if x.pk == line.refund_target_line_id)
                target = target_line.result_transaction
            if target and target.status != Transaction.Status.CANCELLED:
                target.status, target.paid_on = Transaction.Status.CANCELLED, None
                target.save(update_fields=["status", "paid_on", "updated_at"])
                line.result_transaction = target
                cancelled += 1
            else:  # purchase not imported/available -> keep the money as a refund income
                line.result_transaction = _create_from_line(statement, line)
                imported += 1
        elif line.action == Action.MATCH and line.matched_transaction and \
                line.matched_transaction.status == Transaction.Status.PENDING:
            pending = line.matched_transaction
            pending.status, pending.paid_on = Transaction.Status.PAID, line.date
            pending.amount, pending.external_key = line.amount, line.external_key
            if _is_card(statement):
                pending.is_card, pending.cycle_end = True, statement.period_end
            pending.save(update_fields=["status", "paid_on", "amount", "external_key", "is_card", "cycle_end",
                                        "updated_at"])
            line.result_transaction = pending
            matched += 1
        else:
            line.result_transaction = _create_from_line(statement, line)
            imported += 1
        existing_keys.add(line.external_key)
        line.save(update_fields=["result_transaction", "updated_at"])

    # first card statement for this account: remember its cut-off day and card name
    account = statement.account
    if statement.statement_type == StatementImport.StatementType.CARD:
        fields = []
        if statement.period_end and not account.statement_day:
            account.statement_day = statement.period_end.day
            fields.append("statement_day")
        if not account.card_name:
            from .statements.registry import BANK_LABELS

            account.card_name = f"{BANK_LABELS.get(statement.bank, account.name)} Kredi Kartı"[:60]
            fields.append("card_name")
        if fields:
            account.save(update_fields=[*fields, "updated_at"])

    statement.status = StatementImport.Status.IMPORTED
    statement.imported_count, statement.matched_count, statement.cancelled_count = imported, matched, cancelled
    statement.save(update_fields=["status", "imported_count", "matched_count", "cancelled_count", "updated_at"])
    # raw statement text (counterparty names, references) is only needed for parsing/classification
    statement.lines.update(raw_text="")
    return statement


def delete_statement_data(statement: StatementImport) -> None:
    """Remove the statement record, its preview lines and any leftover file. Imported transactions stay."""
    if statement.file:
        statement.file.delete(save=False)
    statement.delete()


def statement_snapshot(user, statement_id) -> dict | None:
    """Issue report context (support registry, type "saving.statement"): what the user's statement looked like
    when the problem was reported. No file content, no line texts; None if not found / not the user's."""
    try:
        s = StatementImport.objects.select_related("account").get(pk=statement_id, user=user)
    except (StatementImport.DoesNotExist, DjangoValidationError, ValueError):
        return None
    actions = Counter(s.lines.values_list("action", flat=True))
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": str(s.pk),
        "original_name": s.original_name,
        "bank": s.bank,
        "bank_label": BANK_LABELS.get(s.bank, s.bank),
        "is_generic_parser": s.is_generic,
        "check": [s.check_status, s.check_message],
        "statement_type": s.statement_type,
        "status": s.status,
        "error": s.error,
        "period": [iso(s.period_start), iso(s.period_end)],
        "closing_balance": str(s.closing_balance) if s.closing_balance is not None else None,
        "account": s.account.name,
        "lines": sum(actions.values()),
        "line_actions": dict(actions),
        "imported": s.imported_count,
        "matched": s.matched_count,
        "cancelled": s.cancelled_count,
        "uploaded_at": s.created_at.isoformat(),
    }


def cleanup_stale_statement_files(max_age_hours: int = 1) -> int:
    """Safety net: delete files that were never parsed (e.g. worker was down). Returns number of files removed."""
    cutoff = timezone.now() - timedelta(hours=max_age_hours)
    removed = 0
    for statement in StatementImport.objects.filter(created_at__lt=cutoff).exclude(file=""):
        statement.file.delete(save=False)
        StatementImport.objects.filter(pk=statement.pk).update(
            file="", status=StatementImport.Status.FAILED, error="Ekstre zamanında işlenemedi, lütfen tekrar yükleyin."
        )
        removed += 1
    return removed
