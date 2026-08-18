Here's a complete README you can copy-paste directly into GitHub (click "Add a README" → paste this in):

```markdown
# Lakebase Ticket App

A lightweight internal support ticketing system built with Flask and deployed as a Databricks App, backed entirely by **Lakebase** (Databricks-managed Postgres) for persistent, transactional storage.

Built as Day 1 homework for the DataExpert.io Databricks bootcamp — this app is the foundation for later context-engineering and AI-agent projects in the program.

## Live App

🔗 **App URL:** https://lakebase-ticket-app-7474655037253536.aws.databricksapps.com/

## Features

- **View all support tickets** — list view with status, priority, category, message count, and creation date
- **Select a ticket and view its messages** — click any ticket to open a detail modal with full conversation history
- **Create new tickets** — with title, creator name, priority, and optional category
- **Add messages to a ticket** — threaded conversation per ticket
- **Update ticket status** — `open` → `in_progress` → `resolved`
- **Delete tickets** — with confirmation step
- **Filter tickets by status**
- **Live ticket statistics** — total, open, resolved, in-progress counts

All reads and writes go through Lakebase — there is no hard-coded or mock data.

## Tech Stack

- **Backend:** Flask (Python)
- **Database:** Lakebase (Databricks-managed Postgres), accessed via `psycopg2`
- **Secrets:** Databricks secret scope (connection URL stored securely, never hard-coded)
- **Frontend:** Single-page HTML/CSS/JS (`templates/index.html`)
- **Deployment:** Databricks Apps

## Database Schema

### `tickets`
| Column | Type | Notes |
|---|---|---|
| `ticket_id` | SERIAL PRIMARY KEY | |
| `title` | TEXT NOT NULL | |
| `status` | TEXT NOT NULL DEFAULT 'open' | `open`, `in_progress`, `resolved` |
| `priority` | TEXT NOT NULL DEFAULT 'medium' | `low`, `medium`, `high` |
| `category` | TEXT | optional |
| `created_by` | TEXT NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

### `ticket_messages`
| Column | Type | Notes |
|---|---|---|
| `message_id` | SERIAL PRIMARY KEY | |
| `ticket_id` | INTEGER NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE | |
| `message_text` | TEXT NOT NULL | |
| `author` | TEXT NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Tables are created automatically on first app request via `ensure_tables()` in `app.py` — no manual SQL setup required.

## Project Structure

```
lakebase-ticket-app/
├── app.py              # Flask app: routes, API, schema creation
├── lakebase.py         # Lakebase connection helper (psycopg2 + secret scope)
├── setup_secrets.py    # One-time script to store the Lakebase URL as a Databricks secret
├── app.yaml             # Databricks App environment config
├── requirements.txt    # Python dependencies
├── .env.example         # Local dev env template
└── templates/
    └── index.html       # Single-page UI
```

## How It Connects to Lakebase

`lakebase.py` fetches the Postgres connection URL from a Databricks secret scope (never hard-coded or committed to the repo):

```python
def _lakebase_url() -> str:
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")
```

Two helper functions handle all database access:

- **`run_query(sql, params)`** — for SELECT and any statement returning rows (e.g. `INSERT ... RETURNING *`). Commits after execution so writes persist.
- **`run_write(sql, params)`** — for UPDATE/DELETE/DDL statements that return a row count.

```python
def run_query(sql, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()
            return rows
```

> **Debugging note:** An early version of `run_query` didn't call `conn.commit()`. Inserts via `INSERT ... RETURNING *` appeared to succeed (the API returned 201) but the data silently rolled back once the connection closed, so nothing persisted. Fixed by committing before returning.

## API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api/tickets` | List all tickets (optional `?status=` filter) |
| POST | `/api/tickets` | Create a new ticket |
| GET | `/api/tickets/<id>` | Get a ticket with its messages |
| POST | `/api/tickets/<id>/status` | Update ticket status |
| DELETE | `/api/tickets/<id>` | Delete a ticket |
| POST | `/api/tickets/<id>/messages` | Add a message to a ticket |
| GET | `/api/stats` | Ticket counts by status |

## Setup / Deployment (Databricks)

1. Create/use a **Lakebase project** in Databricks and copy its Postgres connection URL.
2. Run `setup_secrets.py` in a Databricks notebook — it prompts (via `getpass`) for the connection URL and stores it in a Databricks secret scope (`database` / `lakebase-url` by default).
3. Create a **Databricks App**, point its source at this repo's folder, and deploy.
4. Open the app URL — this triggers `ensure_tables()` on first load, auto-creating the schema.
5. Create tickets/messages through the UI.

No manual SQL, no credentials in code — everything flows through the Databricks secret scope.

## Reflection

**Most difficult part:** Tracking down a subtle transaction-commit bug — inserts looked successful (API returned 201) but silently didn't persist because `run_query` wasn't committing.

**Lakebase vs. a traditional analytics table:** Lakebase is a fully managed, transactional Postgres database built for live application data — fast reads/writes, foreign keys, row-level updates. A traditional analytics table is optimized for large batch reads/aggregations, not frequent small transactional writes like creating one ticket or adding one message.

**Next feature:** Assign tickets to specific support agents, track ownership, and send email notifications on status changes.
```

Want me to also add a `LICENSE` or `.gitignore` suggestion, or is this good as-is?
