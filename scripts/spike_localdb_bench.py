#!/usr/bin/env python3
"""THROWAWAY SPIKE (#376) — benchmark local-DB vs AppleScript vs IMAP.

Times the same search queries through three read paths against a real large
mailbox (Gmail INBOX, ~32k messages on the spike author's machine):

  * local-DB  — scripts/spike_localdb_envelope.py (Envelope Index SQLite)
  * AppleScript — AppleMailConnector._search_messages_applescript
  * IMAP        — AppleMailConnector._imap_search (if a Keychain entry exists)

Read-only, metadata only. Requires Full Disk Access (local-DB path) and
MAIL_TEST_MODE=true. Run:

    MAIL_TEST_MODE=true uv run python scripts/spike_localdb_bench.py
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable

from apple_mail_mcp.mail_connector import AppleMailConnector

import spike_localdb_envelope as ldb  # the prototype reader

ACCOUNT = "Gmail"
ACCOUNT_UUID = "04E9E040-D5C2-4B6B-8FFA-5AAF3DCCAB16"
MAILBOX = "INBOX"


def timed(fn: Callable[[], Any], runs: int) -> tuple[float, int, str]:
    """Return (median_seconds, result_count, error) over N runs."""
    times: list[float] = []
    count = -1
    for _ in range(runs):
        t = time.perf_counter()
        try:
            res = fn()
            count = len(res) if res is not None else 0
        except Exception as exc:  # noqa: BLE001 — spike: report, don't crash
            return (time.perf_counter() - t, -1, f"{type(exc).__name__}: {exc}")
        times.append(time.perf_counter() - t)
    return (statistics.median(times), count, "")


QUERIES = [
    ("recent 50, no filter", dict(limit=50)),
    ("sender_contains=linkedin, unread", dict(sender_contains="linkedin", read_status=False, limit=50)),
    ("subject_contains=invoice", dict(subject_contains="invoice", limit=50)),
]


def run() -> None:
    conn = AppleMailConnector(timeout=180)
    db = ldb._connect(ldb.envelope_index_path())

    print(f"Benchmark: {ACCOUNT}/{MAILBOX} (large mailbox)\n")
    header = f"{'query':<38} {'local-DB':>12} {'AppleScript':>14} {'IMAP':>12}"
    print(header)
    print("-" * len(header))

    for label, q in QUERIES:
        # local-DB (3 runs: cold + warm)
        ldb_q = ldb.Query(
            mailbox_like=f"{ACCOUNT_UUID}/{MAILBOX}",
            sender_contains=q.get("sender_contains"),
            subject_contains=q.get("subject_contains"),
            read=(False if q.get("read_status") is False else None),
            limit=q.get("limit", 50),
        )
        d_t, d_n, d_e = timed(lambda: ldb.search(db, ldb_q), runs=3)

        # AppleScript (1 run — slow path on a 32k mailbox)
        a_t, a_n, a_e = timed(
            lambda: conn._search_messages_applescript(
                account=ACCOUNT, mailbox=MAILBOX, **q
            ),
            runs=1,
        )

        # IMAP (2 runs; benign skip if no Keychain entry)
        i_t, i_n, i_e = timed(
            lambda: conn._imap_search(account=ACCOUNT, mailbox=MAILBOX, **q),
            runs=2,
        )

        def cell(t: float, n: int, e: str) -> str:
            if e:
                return "ERR/skip"
            return f"{t * 1000:7.1f}ms n={n}"

        print(f"{label:<38} {cell(d_t, d_n, d_e):>12} {cell(a_t, a_n, a_e):>14} {cell(i_t, i_n, i_e):>12}")
        for tag, e in (("local-DB", d_e), ("AppleScript", a_e), ("IMAP", i_e)):
            if e:
                print(f"    {tag} note: {e[:90]}")

    db.close()
    print("\n(medians; local-DB n=3 runs, AppleScript n=1, IMAP n=2)")


if __name__ == "__main__":
    run()
