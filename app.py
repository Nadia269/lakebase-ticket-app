"""
Lakebase Support Ticket App
- Serves a small Flask API + single-page UI
- Reads/writes tickets and ticket_messages in Lakebase via lakebase.py
"""

import logging
import os

from flask import Flask, jsonify, render_template, request

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticket-app")

app = Flask(__name__)

VALID_STATUSES = ("open", "in_progress", "resolved")
VALID_PRIORITIES = ("low", "medium", "high")


def ensure_tables():
    """Create tickets and ticket_messages tables if they don't exist yet."""
    lakebase.run_write(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            priority TEXT NOT NULL DEFAULT 'medium',
            category TEXT,
            created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    lakebase.run_write(
        """
        CREATE TABLE IF NOT EXISTS ticket_messages (
            message_id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
            message_text TEXT NOT NULL,
            author TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


@app.errorhandler(Exception)
def handle_exception(err):
    logger.exception("Unhandled exception")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template("index.html")


# ---------- Tickets ----------

@app.route("/api/tickets", methods=["GET"])
def list_tickets():
    ensure_tables()
    status = request.args.get("status")
    if status:
        if status not in VALID_STATUSES:
            return jsonify({"error": f"Invalid status filter: {status!r}"}), 400
        rows = lakebase.run_query(
            """
            SELECT t.*, COUNT(m.message_id) AS message_count
            FROM tickets t
            LEFT JOIN ticket_messages m ON m.ticket_id = t.ticket_id
            WHERE t.status = %s
            GROUP BY t.ticket_id
            ORDER BY t.created_at DESC
            """,
            (status,),
        )
    else:
        rows = lakebase.run_query(
            """
            SELECT t.*, COUNT(m.message_id) AS message_count
            FROM tickets t
            LEFT JOIN ticket_messages m ON m.ticket_id = t.ticket_id
            GROUP BY t.ticket_id
            ORDER BY t.created_at DESC
            """
        )
    return jsonify(rows)


@app.route("/api/tickets", methods=["POST"])
def create_ticket():
    ensure_tables()
    data = request.get_json(force=True, silent=True) or {}

    title = (data.get("title") or "").strip()
    created_by = (data.get("created_by") or "").strip()
    priority = data.get("priority", "medium")
    category = data.get("category")

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not created_by:
        return jsonify({"error": "created_by is required"}), 400
    if priority not in VALID_PRIORITIES:
        return jsonify({"error": f"Invalid priority: {priority!r}"}), 400

    rows = lakebase.run_query(
        """
        INSERT INTO tickets (title, created_by, priority, category)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (title, created_by, priority, category),
    )
    return jsonify(rows[0]), 201


@app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    ensure_tables()
    ticket_rows = lakebase.run_query(
        "SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id,)
    )
    if not ticket_rows:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    messages = lakebase.run_query(
        """
        SELECT * FROM ticket_messages
        WHERE ticket_id = %s
        ORDER BY created_at ASC
        """,
        (ticket_id,),
    )
    ticket = ticket_rows[0]
    ticket["messages"] = messages
    return jsonify(ticket)


@app.route("/api/tickets/<int:ticket_id>/status", methods=["POST"])
def update_status(ticket_id):
    ensure_tables()
    data = request.get_json(force=True, silent=True) or {}
    status = data.get("status")

    if status not in VALID_STATUSES:
        return jsonify({"error": f"Invalid status: {status!r}. Must be one of {VALID_STATUSES}"}), 400

    rowcount = lakebase.run_write(
        "UPDATE tickets SET status = %s WHERE ticket_id = %s",
        (status, ticket_id),
    )
    if rowcount == 0:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    return jsonify({"ticket_id": ticket_id, "status": status})


@app.route("/api/tickets/<int:ticket_id>", methods=["DELETE"])
def delete_ticket(ticket_id):
    ensure_tables()
    rowcount = lakebase.run_write(
        "DELETE FROM tickets WHERE ticket_id = %s", (ticket_id,)
    )
    if rowcount == 0:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404
    return jsonify({"message": f"Ticket {ticket_id} deleted"})


# ---------- Messages ----------

@app.route("/api/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_message(ticket_id):
    ensure_tables()
    exists = lakebase.run_query(
        "SELECT ticket_id FROM tickets WHERE ticket_id = %s", (ticket_id,)
    )
    if not exists:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    message_text = (data.get("message_text") or "").strip()
    author = (data.get("author") or "").strip()

    if not message_text:
        return jsonify({"error": "message_text is required"}), 400
    if not author:
        return jsonify({"error": "author is required"}), 400

    rows = lakebase.run_query(
        """
        INSERT INTO ticket_messages (ticket_id, message_text, author)
        VALUES (%s, %s, %s)
        RETURNING *
        """,
        (ticket_id, message_text, author),
    )
    return jsonify(rows[0]), 201


# ---------- Stats (bonus) ----------

@app.route("/api/stats", methods=["GET"])
def stats():
    ensure_tables()
    rows = lakebase.run_query(
        "SELECT status, COUNT(*) AS count FROM tickets GROUP BY status"
    )
    total = lakebase.run_query("SELECT COUNT(*) AS count FROM tickets")
    return jsonify({"by_status": rows, "total": total[0]["count"]})


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", 8000))
    app.run(debug=True, host=host, port=port)