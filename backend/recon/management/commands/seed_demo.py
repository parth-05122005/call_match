from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from recon.models import CapitalCall, InvestorEntity, LineItem, Organization

ORGANIZATIONS = {
    "northwind": "Northwind Ventures",
    "bluebird": "Bluebird Capital",
}

# (org slug, call number, call date, due date)
CAPITAL_CALLS = [
    ("northwind", 1, date(2026, 3, 25), date(2026, 4, 10)),
    ("northwind", 2, date(2026, 4, 1), date(2026, 4, 20)),
    ("bluebird", 1, date(2026, 4, 1), date(2026, 4, 15)),
]

# (org slug, call number, investor entity, reference, amount called)
LINE_ITEMS = [
    ("northwind", 1, "Haller Capital LLC", "CC-1001", "27500.00"),
    ("northwind", 1, "Rahul Shah Trust", "CC-1002", "25000.00"),
    ("northwind", 1, "Patel Family Trust", "CC-1003", "12500.00"),
    ("northwind", 1, "Meridian Partners LP", "CC-1004", "15000.00"),
    ("northwind", 1, "Oakridge Holdings LLC", "CC-1005", "15000.00"),
    ("northwind", 2, "Oakridge Holdings LLC", "CC-1006", "15000.00"),
    ("bluebird", 1, "Cedar Grove Fund LP", "CC-2001", "40000.00"),
]


class Command(BaseCommand):
    help = "Create demo organizations, capital calls and line items (safe to run twice)."

    @transaction.atomic
    def handle(self, *args, **options):
        orgs = {}
        for slug, name in ORGANIZATIONS.items():
            orgs[slug], _ = Organization.objects.get_or_create(slug=slug, defaults={"name": name})

        calls = {}
        for slug, number, call_date, due_date in CAPITAL_CALLS:
            calls[(slug, number)], _ = CapitalCall.objects.get_or_create(
                organization=orgs[slug],
                number=number,
                defaults={"call_date": call_date, "due_date": due_date},
            )

        for slug, number, investor_name, reference, amount in LINE_ITEMS:
            investor, _ = InvestorEntity.objects.get_or_create(organization=orgs[slug], name=investor_name)
            LineItem.objects.get_or_create(
                organization=orgs[slug],
                reference=reference,
                defaults={
                    "capital_call": calls[(slug, number)],
                    "investor": investor,
                    "amount_called": Decimal(amount),
                },
            )

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))