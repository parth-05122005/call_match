import re
from recon.models import Match, Transaction
# Company suffixes dropped from the end of an investor name ("TRUST" is kept).
NAME_SUFFIXES = {"LLC", "LP", "LTD", "INC"}

def money(amount):
    """Format a Decimal as money text, e.g. 12500 -> "12,500.00"."""
    return f"{amount:,.2f}"


def normalize_reference(text):
    """Uppercase and keep only letters and digits: "cc-1003" -> "CC1003"."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def normalize_words(text):
    """Uppercase, turn every non letter/digit into a space, collapse spaces."""
    return " ".join(re.sub(r"[^A-Z0-9]", " ", text.upper()).split())


def normalize_name(name):
    """Like normalize_words, then drop a trailing LLC / LP / LTD / INC."""
    words = normalize_words(name).split()
    if words and words[-1] in NAME_SUFFIXES:
        words = words[:-1]
    return " ".join(words)


def name_found(name, description):
    """True if the normalised name appears as whole words in the normalised description."""
    name = normalize_name(name)
    if not name:
        return False
    # Spaces around both sides make sure we only match whole words
    # ("SHAH" must not match inside "SHAHID").
    return f" {name} " in f" {normalize_words(description)} "


def find_matches(txn, line_items):
    """
    Apply the matching rule to one credit transaction.
    Sets txn.status / txn.reason and returns a list of unsaved Match objects.
    """
    # Step 1: eligible line items.
    eligible = [
        item for item in line_items
        if item.amount_remaining > 0 and item.capital_call.call_date <= txn.date
    ]

    # Step 2: reference check.
    description_ref = normalize_reference(txn.description)
    bank_ref = normalize_reference(txn.bank_reference)
    by_reference = [
        item for item in eligible
        if normalize_reference(item.reference) in description_ref
        or normalize_reference(item.reference) in bank_ref
    ]

    if len(by_reference) == 1:
        item = by_reference[0]
        remaining = item.amount_remaining
        if txn.amount > remaining:
            # Overpayment: no match, a person has to look at it.
            txn.status = Transaction.NEEDS_REVIEW
            txn.reason = (
                f"Reference {item.reference} found, but amount {money(txn.amount)} "
                f"is more than remaining {money(remaining)} (overpayment)"
            )
            return []
        if txn.amount == remaining:
            reason = f"Reference {item.reference} found; amount equals remaining {money(remaining)}"
        else:
            reason = (
                f"Reference {item.reference} found; partial payment of {money(txn.amount)} "
                f"towards remaining {money(remaining)}"
            )
        txn.status = Transaction.SUGGESTED
        txn.reason = ""
        return [Match(transaction=txn, line_item=item, reason=reason)]

    if len(by_reference) > 1:
        txn.status = Transaction.NEEDS_REVIEW
        txn.reason = "References for more than one line item found; choose the right one"
        return [
            Match(transaction=txn, line_item=item, reason=f"Reference {item.reference} found")
            for item in by_reference
        ]

    # Step 3: name and amount check (only runs when no reference was found).
    by_name = [
        item for item in eligible
        if txn.amount == item.amount_remaining and name_found(item.investor.name, txn.description)
    ]
    matches = [
        Match(
            transaction=txn,
            line_item=item,
            reason=f"Name {item.investor.name} found; amount equals remaining {money(item.amount_remaining)}",
        )
        for item in by_name
    ]

    if len(by_name) == 1:
        txn.status = Transaction.SUGGESTED
        txn.reason = ""
    elif len(by_name) > 1:
        txn.status = Transaction.NEEDS_REVIEW
        txn.reason = "Name and amount match more than one line item; choose the right one"
    else:
        txn.status = Transaction.NEEDS_REVIEW
        txn.reason = "No reference found and no investor name with a matching amount"
    return matches