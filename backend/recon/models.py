from django.db import models

# Create your models here.

from decimal import Decimal

# Used for every money column: up to 9,999,999,999.99
MONEY = {"max_digits": 12, "decimal_places": 2}

class Organization(models.Model):
    """One GP firm (a tenant). Every other record belongs to one organization."""

    slug = models.SlugField(unique=True)  # e.g. "northwind", sent in X-Organization
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name



class InvestorEntity(models.Model):
    """The legal entity an LP invests through, e.g. "Patel Family Trust"."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_investor_per_org"),
        ]

    def __str__(self):
        return self.name


class CapitalCall(models.Model):
    """A request for money sent by the GP to its LPs."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    number = models.PositiveIntegerField()  # call #1, #2, ... inside the organization
    call_date = models.DateField()
    due_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="unique_call_number_per_org"),
        ]

    def __str__(self):
        return f"Capital call #{self.number}"


class LineItem(models.Model):
    """One LP's share of one capital call. Payments are matched to line items."""

    OPEN = "open"
    PARTIALLY_FUNDED = "partially_funded"
    FUNDED = "funded"
    STATUS_CHOICES = [(OPEN, OPEN), (PARTIALLY_FUNDED, PARTIALLY_FUNDED), (FUNDED, FUNDED)]

    # organization is copied here (not only on the capital call) so that
    # scoping queries stay simple: LineItem.objects.filter(organization=org)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    capital_call = models.ForeignKey(CapitalCall, on_delete=models.CASCADE, related_name="line_items")
    investor = models.ForeignKey(InvestorEntity, on_delete=models.CASCADE)
    reference = models.CharField(max_length=50)  # expected wire reference, e.g. "CC-1003"
    amount_called = models.DecimalField(**MONEY)
    amount_funded = models.DecimalField(**MONEY, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)

    class Meta:
        ordering = ["reference"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "reference"], name="unique_reference_per_org"),
            # Database-level safety net: a line item can never be funded beyond its amount.
            models.CheckConstraint(
                condition=models.Q(amount_funded__lte=models.F("amount_called")),
                name="funded_not_above_called",
            ),
        ]

    @property
    def amount_remaining(self):
        return self.amount_called - self.amount_funded

    def update_status(self):
        """Set status from the funded amount. Call this after changing amount_funded."""
        if self.amount_funded == 0:
            self.status = self.OPEN
        elif self.amount_funded < self.amount_called:
            self.status = self.PARTIALLY_FUNDED
        else:
            self.status = self.FUNDED

    def __str__(self):
        return self.reference



class Transaction(models.Model):
    """One row from an imported bank statement."""

    CREDIT = "credit"
    DEBIT = "debit"
    TYPE_CHOICES = [(CREDIT, CREDIT), (DEBIT, DEBIT)]

    SUGGESTED = "suggested"        # exactly one clear match
    NEEDS_REVIEW = "needs_review"  # no match, several matches or an overpayment
    RECONCILED = "reconciled"      # a match was approved (final)
    IGNORED = "ignored"            # debits, or ignored by the GP
    STATUS_CHOICES = [
        (SUGGESTED, SUGGESTED),
        (NEEDS_REVIEW, NEEDS_REVIEW),
        (RECONCILED, RECONCILED),
        (IGNORED, IGNORED),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=500)
    amount = models.DecimalField(**MONEY)  # positive for credits, negative for debits
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    bank_reference = models.CharField(max_length=100)  # the bank's unique ID, e.g. "FT20260403A"
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    reason = models.CharField(max_length=500, blank=True)  # why it needs review (empty otherwise)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Same bank reference only once per organization (two orgs may share one).
            models.UniqueConstraint(fields=["organization", "bank_reference"], name="unique_bank_reference_per_org"),
        ]

    def __str__(self):
        return self.bank_reference


class Match(models.Model):
    """A suggested link from one transaction to one line item, with the reason why."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [(PROPOSED, PROPOSED), (APPROVED, APPROVED), (REJECTED, REJECTED)]

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="matches")
    line_item = models.ForeignKey(LineItem, on_delete=models.CASCADE, related_name="matches")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PROPOSED)
    reason = models.CharField(max_length=500)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.transaction} -> {self.line_item}"