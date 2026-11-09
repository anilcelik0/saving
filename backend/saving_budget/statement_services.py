"""Statement import pipeline: parse (Celery) -> preview lines -> user review -> confirm into Transactions."""

import hashlib
import logging
from collections import Counter
from datetime import timedelta

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Category, Kind, MerchantCategoryRule, StatementImport, StatementLine, Transaction
from .services import FALLBACK_CATEGORY
from .statements import StatementParseError, detect_and_parse
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
                account=statement.account, kind=Kind.EXPENSE, status=Transaction.Status.PAID, amount=refund.amount,
                date__range=(refund.date - timedelta(days=REFUND_WINDOW_DAYS), refund.date),
            ).exclude(pk__in=taken_ids)
            if merchant_key(t.description) == key
        ]
        if existing:
            target = max(existing, key=lambda t: t.date)
            refund.action, refund.matched_transaction = Action.REFUND, target
            taken_ids.add(target.pk)


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

        reason = "duplicate" if key in existing_keys else skip_reason(p, parsed.holder_name)
        if reason:
            line.action, line.skip_reason = Action.SKIP, reason
        elif match := _find_pending_match(statement, line, taken):
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


def _create_from_line(statement, line, kind=None, category=None):
    return Transaction.objects.create(
        user=statement.user, account=statement.account, kind=kind or line.kind, amount=line.amount,
        date=line.date, status=Transaction.Status.PAID, paid_on=line.date,
        description=line.description, category=category or line.category,
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
            pending.save(update_fields=["status", "paid_on", "amount", "external_key", "updated_at"])
            line.result_transaction = pending
            matched += 1
        else:
            line.result_transaction = _create_from_line(statement, line)
            imported += 1
        existing_keys.add(line.external_key)
        line.save(update_fields=["result_transaction", "updated_at"])

    statement.status = StatementImport.Status.IMPORTED
    statement.imported_count, statement.matched_count, statement.cancelled_count = imported, matched, cancelled
    statement.save(update_fields=["status", "imported_count", "matched_count", "cancelled_count", "updated_at"])
    return statement
