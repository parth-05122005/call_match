import csv
import io
import re
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ParseError

from recon.models import LineItem, Match, Organization, Transaction
from recon.services.matching import find_matches

REQUIRED_COLUMNS = ["date", "description", "amount", "type", "reference"]

# A plain number with an optional sign and at most 2 decimals, e.g. "-25.00" or "15000".
AMOUNT_PATTERN = re.compile(r"[+-]?\d+(\.\d{1,2})?")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
MAX_AMOUNT = Decimal("9999999999.99")  # biggest value our money columns can hold


class RowError(Exception):
    """Raised when one CSV row is invalid. The message is shown to the user."""


def parse_row(row):
    """Validate one CSV row (a dict) and return clean values, or raise RowError."""
    # Trim spaces around every field first. Missing cells come back as None.
    values = {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}

    # date: must be YYYY-MM-DD and a real calendar date (2026-04-31 is not).
    if not DATE_PATTERN.fullmatch(values["date"]):
        raise RowError(f"Invalid date '{values['date']}': use YYYY-MM-DD")
    try:
        txn_date = datetime.strptime(values["date"], "%Y-%m-%d").date()
    except ValueError:
        raise RowError(f"Invalid date '{values['date']}': not a real calendar date")

    if not values["description"]:
        raise RowError("Description is required")

    # amount: remove thousands separators, then parse as Decimal (never float).
    amount_text = values["amount"].replace(",", "")
    if not AMOUNT_PATTERN.fullmatch(amount_text):
        raise RowError(f"Invalid amount '{values['amount']}'")
    amount = Decimal(amount_text)
    if amount == 0:
        raise RowError("Amount cannot be zero")
    if abs(amount) > MAX_AMOUNT:
        raise RowError("Amount is too large")

    # type: credit or debit, any letter case. Credits positive, debits negative.
    txn_type = values["type"].lower()
    if txn_type not in (Transaction.CREDIT, Transaction.DEBIT):
        raise RowError(f"Invalid type '{values['type']}': use credit or debit")
    if txn_type == Transaction.CREDIT and amount < 0:
        raise RowError("A credit must have a positive amount")
    if txn_type == Transaction.DEBIT and amount > 0:
        raise RowError("A debit must have a negative amount")

    if not values["reference"]:
        raise RowError("Reference is required")

    return {
        "date": txn_date,
        "description": values["description"],
        "amount": amount,
        "type": txn_type,
        "bank_reference": values["reference"],
    }


def read_csv(uploaded_file):
    """Turn the uploaded file into a csv.DictReader, checking the header columns."""
    try:
        # "utf-8-sig" also removes the invisible BOM that Excel adds.
        text = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("The file must be a UTF-8 encoded CSV file")

    reader = csv.DictReader(io.StringIO(text))
    # Clean header names so " Date " still counts as "date".
    reader.fieldnames = [name.strip().lower() for name in (reader.fieldnames or [])]

    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise ParseError(f"Missing column(s): {', '.join(missing)}")
    return reader


@transaction.atomic
def import_bank_statement(organization, uploaded_file):
    """Import the CSV and return the import summary (a dict)."""
    reader = read_csv(uploaded_file)

    # Lock the organization row so two uploads for the same organization
    # run one after the other (keeps the duplicate check correct).
    Organization.objects.select_for_update().get(pk=organization.pk)

    seen_references = set(
        Transaction.objects.filter(organization=organization).values_list("bank_reference", flat=True)
    )
    line_items = list(
        LineItem.objects.filter(organization=organization).select_related("capital_call", "investor")
    )

    new_transactions = []
    new_matches = []
    duplicates = []
    errors = []

    for row in reader:
        line = reader.line_num  # line number in the file (header is line 1)
        try:
            data = parse_row(row)
        except RowError as error:
            errors.append({"line": line, "message": str(error)})
            continue

        if data["bank_reference"] in seen_references:
            duplicates.append({"line": line, "reference": data["bank_reference"]})
            continue
        seen_references.add(data["bank_reference"])

        txn = Transaction(organization=organization, **data)
        if txn.type == Transaction.DEBIT:
            txn.status = Transaction.IGNORED
            txn.reason = "Debit (money out) cannot pay a capital call"
        else:
            new_matches += find_matches(txn, line_items)
        new_transactions.append(txn)

    # Save everything in two queries. bulk_create fills in txn.pk (on PostgreSQL),
    # so the matches can point to their transactions afterwards.
    Transaction.objects.bulk_create(new_transactions)
    Match.objects.bulk_create(new_matches)

    return {
        "imported": len(new_transactions),
        "duplicates": len(duplicates),
        "duplicate_rows": duplicates,
        "errors": errors,
    }