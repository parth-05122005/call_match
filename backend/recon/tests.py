from decimal import Decimal
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from recon.models import LineItem, Match, Transaction

HEADER = "date,description,amount,type,reference\n"


class ReconTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())  # StringIO hides the "ready" message

    def setUp(self):
        self.client = APIClient()

    def upload(self, csv_text, org="northwind"):
        """POST a CSV file to the import endpoint and return the response."""
        file = SimpleUploadedFile("statement.csv", csv_text.encode("utf-8"), content_type="text/csv")
        return self.client.post(
            "/api/transactions/import/", {"file": file}, HTTP_X_ORGANIZATION=org, format="multipart"
        )

    def transaction(self, bank_reference):
        return Transaction.objects.get(bank_reference=bank_reference)

    def line_item(self, reference):
        return LineItem.objects.get(reference=reference)


class ImportTests(ReconTestCase):
    # 1. A missing column rejects the file and saves nothing.
    def test_missing_column_rejects_whole_file(self):
        response = self.upload("date,description,amount,type\n2026-04-03,WIRE,100.00,credit\n")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reference", response.json()["detail"])
        self.assertEqual(Transaction.objects.count(), 0)

    # 2. Amount parsing: thousands separators, sign/type mismatch, invalid dates.
    def test_amount_and_date_parsing(self):
        response = self.upload(
            HEADER
            + '2026-04-03,WIRE ONE,"25,000.50",credit,REF1\n'   # line 2: valid
            + "2026-04-04,FEE,-25.00,DEBIT,REF2\n"              # line 3: valid debit
            + "2026-04-31,BAD DATE,100.00,credit,REF3\n"        # line 4: not a real date
            + "2026-04-05,WRONG SIGN,-100.00,credit,REF4\n"     # line 5: credit must be positive
            + "2026-04-05,WRONG SIGN,100.00,debit,REF5\n"       # line 6: debit must be negative
            + "2026-04-05,ZERO,0.00,credit,REF6\n"              # line 7: zero is invalid
            + "2026-04-05,TEXT,abc,credit,REF7\n"               # line 8: not a number
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["imported"], 2)
        self.assertEqual([error["line"] for error in body["errors"]], [4, 5, 6, 7, 8])

        txn = self.transaction("REF1")
        self.assertIsInstance(txn.amount, Decimal)
        self.assertEqual(txn.amount, Decimal("25000.50"))
        self.assertEqual(self.transaction("REF2").status, Transaction.IGNORED)

    # 3. Duplicates: a re-upload and a duplicate inside one file.
    def test_duplicates_are_skipped(self):
        csv_text = (
            HEADER
            + "2026-04-03,WIRE A,100.00,credit,DUP1\n"
            + "2026-04-03,WIRE A,100.00,credit,DUP1\n"  # duplicate inside the file
        )
        first = self.upload(csv_text).json()
        self.assertEqual(first["imported"], 1)
        self.assertEqual(first["duplicates"], 1)
        self.assertEqual(first["duplicate_rows"][0]["line"], 3)

        second = self.upload(csv_text).json()  # re-upload the same file
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["duplicates"], 2)
        self.assertEqual(Transaction.objects.filter(bank_reference="DUP1").count(), 1)

        # Another organization may use the same bank reference.
        self.assertEqual(self.upload(csv_text, org="bluebird").json()["imported"], 1)


class MatchingTests(ReconTestCase):
    # 4. Reference match, including "cc1001" and a partial payment.
    def test_reference_match_with_partial_payment(self):
        self.upload(HEADER + "2026-04-14,ACH CREDIT HALLER CAPITAL cc1001,7500.00,CREDIT,R1\n")
        txn = self.transaction("R1")
        self.assertEqual(txn.status, Transaction.SUGGESTED)
        match = txn.matches.get()
        self.assertEqual(match.line_item.reference, "CC-1001")
        self.assertEqual(match.status, Match.PROPOSED)
        self.assertIn("partial", match.reason)

    def test_reference_in_bank_reference_column(self):
        self.upload(HEADER + "2026-04-03,INCOMING WIRE,25000.00,credit,CC-1002\n")
        self.assertEqual(self.transaction("CC-1002").matches.get().line_item.reference, "CC-1002")

    # 5. Name and amount match, including more than one candidate.
    def test_name_and_amount_match(self):
        self.upload(HEADER + "2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,N1\n")
        txn = self.transaction("N1")
        self.assertEqual(txn.status, Transaction.SUGGESTED)
        self.assertEqual(txn.matches.get().line_item.reference, "CC-1003")

    def test_name_and_amount_with_two_candidates(self):
        # Oakridge has CC-1005 and CC-1006, both 15,000.00 and both called before 04-11.
        self.upload(HEADER + "2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,N2\n")
        txn = self.transaction("N2")
        self.assertEqual(txn.status, Transaction.NEEDS_REVIEW)
        self.assertEqual(
            sorted(m.line_item.reference for m in txn.matches.all()), ["CC-1005", "CC-1006"]
        )

    def test_name_with_wrong_amount_does_not_match(self):
        self.upload(HEADER + "2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,500.00,credit,N3\n")
        txn = self.transaction("N3")
        self.assertEqual(txn.status, Transaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)
        self.assertTrue(txn.reason)

    # 6. Overpayment becomes needs_review with no match.
    def test_overpayment_needs_review(self):
        self.upload(HEADER + "2026-04-15,WIRE PATEL FAMILY TRUST CC-1003,13000.00,credit,O1\n")
        txn = self.transaction("O1")
        self.assertEqual(txn.status, Transaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)
        self.assertIn("overpayment", txn.reason)


class ActionTests(ReconTestCase):
    def approve(self, match_id, org="northwind"):
        return self.client.post(f"/api/matches/{match_id}/approve/", HTTP_X_ORGANIZATION=org)

    # 7. Approving updates the funded amount; a second approval returns 409.
    def test_approve_updates_funding_once(self):
        self.upload(HEADER + "2026-04-03,WIRE RAHUL SHAH TRUST REF CC-1002,25000.00,credit,A1\n")
        match = self.transaction("A1").matches.get()

        response = self.approve(match.id)
        self.assertEqual(response.status_code, 200)
        item = self.line_item("CC-1002")
        self.assertEqual(item.amount_funded, Decimal("25000.00"))
        self.assertEqual(item.status, LineItem.FUNDED)
        self.assertEqual(self.transaction("A1").status, Transaction.RECONCILED)

        second = self.approve(match.id)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self.line_item("CC-1002").amount_funded, Decimal("25000.00"))

    def test_approve_rechecks_remaining_amount(self):
        # Two partial payments that together are more than CC-1001's 27,500.00.
        self.upload(
            HEADER
            + "2026-04-04,HALLER CC-1001,20000.00,credit,P1\n"
            + "2026-04-05,HALLER CC-1001,20000.00,credit,P2\n"
        )
        self.assertEqual(self.approve(self.transaction("P1").matches.get().id).status_code, 200)
        self.assertEqual(self.approve(self.transaction("P2").matches.get().id).status_code, 409)
        item = self.line_item("CC-1001")
        self.assertEqual(item.amount_funded, Decimal("20000.00"))
        self.assertEqual(item.status, LineItem.PARTIALLY_FUNDED)

    def test_reject_and_ignore(self):
        self.upload(HEADER + "2026-04-07,WIRE PATEL FAMILY TRUST,12500.00,credit,I1\n")
        txn = self.transaction("I1")
        match = txn.matches.get()

        response = self.client.post(f"/api/matches/{match.id}/reject/", HTTP_X_ORGANIZATION="northwind")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaction("I1").status, Transaction.NEEDS_REVIEW)

        response = self.client.post(f"/api/transactions/{txn.id}/ignore/", HTTP_X_ORGANIZATION="northwind")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transaction("I1").status, Transaction.IGNORED)

    def test_ignore_reconciled_returns_409(self):
        self.upload(HEADER + "2026-04-03,RAHUL SHAH TRUST CC-1002,25000.00,credit,I2\n")
        txn = self.transaction("I2")
        self.approve(txn.matches.get().id)
        response = self.client.post(f"/api/transactions/{txn.id}/ignore/", HTTP_X_ORGANIZATION="northwind")
        self.assertEqual(response.status_code, 409)


class OrganizationTests(ReconTestCase):
    # 8. Organization isolation for listing and approving (404).
    def test_isolation_between_organizations(self):
        self.upload(HEADER + "2026-04-16,CEDAR GROVE FUND CC-2001,40000.00,credit,B1\n", org="bluebird")
        match = self.transaction("B1").matches.get()

        listing = self.client.get("/api/transactions/", HTTP_X_ORGANIZATION="northwind").json()
        self.assertEqual(listing, [])
        items = self.client.get("/api/line-items/", HTTP_X_ORGANIZATION="northwind").json()
        self.assertNotIn("CC-2001", [item["reference"] for item in items])

        response = self.client.post(f"/api/matches/{match.id}/approve/", HTTP_X_ORGANIZATION="northwind")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.line_item("CC-2001").amount_funded, Decimal("0.00"))

    def test_missing_and_unknown_header(self):
        self.assertEqual(self.client.get("/api/transactions/").status_code, 400)
        response = self.client.get("/api/transactions/", HTTP_X_ORGANIZATION="nobody")
        self.assertEqual(response.status_code, 404)