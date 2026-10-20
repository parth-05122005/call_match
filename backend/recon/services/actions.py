from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException

from recon.models import LineItem, Match, Transaction
from recon.services.matching import money


class Conflict(APIException):
    """Returned as HTTP 409 when the action is no longer allowed."""

    status_code = 409
    default_detail = "This action conflicts with the current state."


def lock_match(organization, match_id):
    """Load and lock a match plus its transaction. Another org's match gives 404."""
    match = get_object_or_404(
        Match.objects.select_for_update(), pk=match_id, transaction__organization=organization
    )
    txn = Transaction.objects.select_for_update().get(pk=match.transaction_id)
    return match, txn


@transaction.atomic
def approve_match(organization, match_id):
    match, txn = lock_match(organization, match_id)
    line_item = LineItem.objects.select_for_update().get(pk=match.line_item_id)

    # Checked after locking, so a repeated approval always sees the first one.
    if match.status != Match.PROPOSED or txn.status == Transaction.RECONCILED:
        raise Conflict("This match is no longer proposed")
    if txn.status == Transaction.IGNORED:
        raise Conflict("This transaction was ignored")
    # Re-check the amount: the line item may have been paid by another approval.
    if txn.amount > line_item.amount_remaining:
        raise Conflict(
            f"Amount {money(txn.amount)} is more than remaining {money(line_item.amount_remaining)}"
        )

    line_item.amount_funded += txn.amount
    line_item.update_status()
    line_item.save()

    match.status = Match.APPROVED
    match.save()
    txn.matches.exclude(pk=match.pk).update(status=Match.REJECTED)

    txn.status = Transaction.RECONCILED
    txn.reason = ""
    txn.save()
    return match


@transaction.atomic
def reject_match(organization, match_id):
    match, txn = lock_match(organization, match_id)
    if match.status != Match.PROPOSED:
        raise Conflict("Only a proposed match can be rejected")

    match.status = Match.REJECTED
    match.save()

    if not txn.matches.filter(status=Match.PROPOSED).exists():
        txn.status = Transaction.NEEDS_REVIEW
        txn.reason = "All suggested matches were rejected"
        txn.save()
    return match


@transaction.atomic
def ignore_transaction(organization, transaction_id):
    txn = get_object_or_404(
        Transaction.objects.select_for_update(), pk=transaction_id, organization=organization
    )
    if txn.status == Transaction.RECONCILED:
        raise Conflict("A reconciled transaction cannot be ignored")

    txn.status = Transaction.IGNORED
    txn.save()
    txn.matches.filter(status=Match.PROPOSED).update(status=Match.REJECTED)
    return txn