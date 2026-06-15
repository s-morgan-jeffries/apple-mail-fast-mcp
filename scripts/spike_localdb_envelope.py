#!/usr/bin/env python3
"""THROWAWAY SPIKE (#376) — local-DB fast read path proof of concept.

Reads Apple Mail's on-disk store directly, bypassing osascript:
  * ``~/Library/Mail/V*/MailData/Envelope Index`` (SQLite) for metadata/search
  * ``*.emlx`` files for message bodies

This is a research prototype to answer "is a local-DB read path worth it?" for
#376 — it is NOT production code and is NOT wired into the connector. It reads
read-only (``mode=ro``), touches metadata only, and prints nothing but counts
and timings. Requires Full Disk Access on the host app.

Run:  uv run python scripts/spike_localdb_envelope.py
"""

from __future__ import annotations

import glob
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- locate the store -------------------------------------------------------


def envelope_index_path() -> Path:
    hits = sorted(
        glob.glob(os.path.expanduser("~/Library/Mail/V*/MailData/Envelope Index"))
    )
    if not hits:
        raise SystemExit(
            "No Envelope Index found. Either Mail.app isn't set up or the host "
            "app lacks Full Disk Access (System Settings > Privacy & Security)."
        )
    return Path(hits[-1])


def mail_root() -> Path:
    return envelope_index_path().parents[1]  # .../V10


def _connect(idx: Path) -> sqlite3.Connection:
    # Read-only URI so we never write/lock Mail's live DB.
    return sqlite3.connect(f"file:{idx}?mode=ro", uri=True)


# --- the prototype reader ---------------------------------------------------

# Mirrors the connector's common row shape (see imap_connector._envelope_to_dict):
# id, rfc_message_id, subject, sender, date_received(ISO), read_status, flagged.
_BASE_SQL = """
SELECT m.ROWID                   AS rowid,
       m.message_id              AS id,
       g.message_id_header       AS rfc,
       s.subject                 AS subject,
       a.address                 AS sender,
       a.comment                 AS sender_name,
       m.date_received           AS date_received,
       m.read                    AS read,
       m.flagged                 AS flagged,
       mb.url                    AS mailbox_url
FROM messages m
LEFT JOIN subjects s          ON s.ROWID = m.subject
LEFT JOIN addresses a         ON a.ROWID = m.sender
LEFT JOIN mailboxes mb        ON mb.ROWID = m.mailbox
LEFT JOIN message_global_data g ON g.message_id = m.message_id
WHERE m.deleted = 0
"""


@dataclass
class Query:
    mailbox_like: str | None = None  # substring of mailbox url, e.g. "/INBOX"
    sender_contains: str | None = None
    subject_contains: str | None = None
    read: bool | None = None
    flagged: bool | None = None
    since_epoch: int | None = None
    limit: int = 50


def _row_to_common(r: sqlite3.Row) -> dict[str, Any]:
    iso = (
        datetime.fromtimestamp(r["date_received"], tz=timezone.utc).isoformat()
        if r["date_received"]
        else None
    )
    rfc = (r["rfc"] or "").strip("<>") or None
    return {
        "id": str(r["id"]),
        "rowid": r["rowid"],  # spike-only: .emlx filename stem
        "rfc_message_id": rfc,
        "subject": r["subject"] or "",
        "sender": r["sender"] or "",
        "date_received": iso,
        "read_status": bool(r["read"]),
        "flagged": bool(r["flagged"]),
        "mailbox_url": r["mailbox_url"],
    }


def search(conn: sqlite3.Connection, q: Query) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    sql = _BASE_SQL
    params: list[Any] = []
    if q.mailbox_like:
        sql += " AND mb.url LIKE ?"
        params.append(f"%{q.mailbox_like}%")
    if q.sender_contains:
        sql += " AND a.address LIKE ?"
        params.append(f"%{q.sender_contains}%")
    if q.subject_contains:
        sql += " AND s.subject LIKE ?"
        params.append(f"%{q.subject_contains}%")
    if q.read is not None:
        sql += " AND m.read = ?"
        params.append(1 if q.read else 0)
    if q.flagged is not None:
        sql += " AND m.flagged = ?"
        params.append(1 if q.flagged else 0)
    if q.since_epoch is not None:
        sql += " AND m.date_received >= ?"
        params.append(q.since_epoch)
    sql += " ORDER BY m.date_received DESC LIMIT ?"
    params.append(q.limit)
    return [_row_to_common(r) for r in conn.execute(sql, params)]


def read_emlx_body(rowid: int, mailbox_url: str | None = None) -> str | None:
    """Locate and parse one .emlx body. The filename stem is messages.ROWID.

    Scope the search to the account subtree (parsed from the mailbox url's
    host = account UUID) so we don't walk the whole 128k-file store.
    """
    root = mail_root()
    scope = root
    if mailbox_url and "://" in mailbox_url:
        uuid = mailbox_url.split("://", 1)[1].split("/", 1)[0]
        cand = root / uuid
        if cand.is_dir():
            scope = cand
    hits = list(scope.rglob(f"{rowid}.emlx"))
    if not hits:
        return None
    raw = hits[0].read_bytes()
    # .emlx = <byte-count>\n<rfc822 message>\n<plist trailer>
    nl = raw.index(b"\n")
    length = int(raw[:nl].strip())
    body = raw[nl + 1 : nl + 1 + length]
    return body.decode("utf-8", errors="replace")


# --- spike self-check -------------------------------------------------------

if __name__ == "__main__":
    idx = envelope_index_path()
    with _connect(idx) as conn:
        total = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
        print(f"Envelope Index: {idx}  ({total:,} messages)")
        rows = search(conn, Query(mailbox_like="/INBOX", read=False, limit=5))
        print(f"sample unread INBOX rows: {len(rows)}")
        for r in rows:
            print(
                f"  id={r['id']:>20}  rfc={'yes' if r['rfc_message_id'] else 'NO '} "
                f"  {r['date_received']}  unread={not r['read_status']}"
            )
        if rows:
            t = time.perf_counter()
            body = read_emlx_body(rows[0]["rowid"], rows[0]["mailbox_url"])
            dt = (time.perf_counter() - t) * 1000
            print(
                f".emlx body read: {'ok' if body else 'not found'} "
                f"({len(body) if body else 0} bytes, {dt:.0f}ms)"
            )
