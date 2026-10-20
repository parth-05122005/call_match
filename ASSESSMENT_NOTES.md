# CallMatch — Bank Reconciliation for Capital Calls

**App name:** CallMatch. It imports a bank statement, suggests which capital call line item each
payment belongs to (and why), and lets the GP approve, reject or ignore each suggestion.

**Stack:** Django 5.2 + Django REST Framework, PostgreSQL, React 18 (Vite).

## Setup from a fresh clone

Requirements: Python 3.12, Node 20+, PostgreSQL running locally.

```bash
# 1. Database
createdb -U postgres callmatch

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env  — then set DB_PASSWORD
python manage.py migrate
python manage.py seed_demo
python manage.py runserver      # http://localhost:8000

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Vite forwards `/api/*` to Django on port 8000, so no CORS setup is needed.

**Run the tests (single command, from `backend/`):**

```bash
python manage.py test
```

## Project layout

```
backend/
  config/            Django settings and root URLs
  recon/
    models.py        Database tables
    organization.py  Reads the X-Organization header (400 / 404)
    serializers.py   Model -> JSON
    views.py         Thin API views
    urls.py          API paths
    services/
      importer.py    CSV parsing, validation, duplicates
      matching.py    Normalisation and the matching rule
      actions.py     Approve / reject / ignore (atomic, row locks)
    management/commands/seed_demo.py
    tests.py
frontend/src/
  App.jsx            Page: org switcher, loading/error state, data loading
  api.js             fetch helper + money formatting
  components/        UploadForm, TransactionTable, LineItemPanel
```

## Data model

| Model | Key fields |
|-|-|
| Organization | slug (unique), name |
| InvestorEntity | organization, name |
| CapitalCall | organization, number, call_date, due_date |
| LineItem | organization, capital_call, investor, reference, amount_called, amount_funded, status. `amount_remaining` is calculated (called − funded). |
| Transaction | organization, date, description, amount, type, bank_reference, status, reason |
| Match | transaction, line_item, status, reason |

Database constraints: `(organization, bank_reference)` is unique on Transaction (duplicate protection),
`(organization, reference)` is unique on LineItem, and a check constraint makes sure
`amount_funded <= amount_called`. All money columns are `DecimalField(12, 2)`.

## API endpoints

Every endpoint except the organizations list needs the header `X-Organization: <slug>`.
Missing header → `400`; unknown organization → `404`; a record of another organization → `404`.

| Method | Path | What it does |
|-|-|-|
| GET | `/api/organizations/` | List organizations (for the switcher) |
| GET | `/api/transactions/` | Transactions with their matches and reasons, newest first |
| POST | `/api/transactions/import/` | Upload a CSV (multipart field `file`). Returns `201` with the summary |
| POST | `/api/transactions/{id}/ignore/` | Ignore a transaction (`409` if reconciled) |
| GET | `/api/line-items/` | Line items with called, funded, remaining and status |
| POST | `/api/matches/{id}/approve/` | Approve a proposed match (`409` if no longer possible) |
| POST | `/api/matches/{id}/reject/` | Reject a proposed match |

Import summary example:

```json
{
  "imported": 11,
  "duplicates": 1,
  "duplicate_rows": [{"line": 11, "reference": "FT20260403A"}],
  "errors": [{"line": 13, "message": "Invalid date '2026-04-31': not a real calendar date"}]
}
```

Errors always look like `{"detail": "message"}`.

## How the important rules are enforced

- **Decimals:** amounts are parsed with `Decimal` after removing thousands separators, never `float`.
- **Duplicates:** checked against the database and against earlier rows of the same file, and backed
  by a unique constraint. The import locks the organization row, so two uploads for the same
  organization run one after another.
- **Approve is safe to repeat:** it runs in one database transaction and locks the match, the
  transaction and the line item with `SELECT ... FOR UPDATE`. A second approval waits for the
  first, then sees the match is already approved and gets `409`. The amount is re-checked against
  the line item's remaining amount after locking. The check constraint is a last safety net.
- **Tenant isolation:** every query filters by the organization from the header; lookups by ID
  include the organization, so another organization's record is simply "not found".

## Assumptions

- Line numbers are physical line numbers in the file (header is line 1).
- A row that is both invalid and a duplicate is reported as an error.
- Amounts may have at most 2 decimal places and an optional `+`/`-` sign.
- Header names are trimmed and compared case-insensitively; extra columns are ignored.
- Reference check uses "appears in" literally (substring after normalisation), as the spec says.
- When several line items match by reference, all are proposed, even if one would be an overpayment;
  approval re-checks the amount and returns `409` in that case.
- Ignoring an already-ignored transaction is allowed (no change). Ignoring a reconciled one is `409`.
- Approving a match on an ignored transaction returns `409`.
- Rejecting the last proposed match moves the transaction to `needs_review` with a reason.
- Suggestions are calculated once, at import, using the remaining amounts at that moment.
- Running `seed_demo` again does not reset funded amounts; it only creates missing rows.

## Trade-offs and next steps

- The importer loads the organization's existing bank references into memory for the duplicate
  check. Fine for thousands of rows; for very large histories, query only the references in the file.
- No pagination on the transaction list yet.
- The Airtable bonus was not built. Next step: an `AirtableClient` class passed into the importer
  (easy to fake in tests), with `airtable_record_id` and `sync_status` on Transaction, and errors caught
  so the import never fails.
- Possible extras: a threaded test for two simultaneous approvals, and a deployed version.

## Integrity

I confirm that this submission is my own work, built within the given time.
