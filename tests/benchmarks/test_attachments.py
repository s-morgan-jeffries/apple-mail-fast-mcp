"""Benchmarks for attachment-handling operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from apple_mail_fast_mcp.mail_connector import AppleMailConnector

from .conftest import (
    BenchmarkResult,
    assert_within_baseline,
    measure_median,
)


@pytest.fixture(scope="module")
def message_with_attachment(
    connector: AppleMailConnector, test_account: str
) -> tuple[str, str]:
    """Find a message in the test account that has at least one
    attachment. Returns ``(message_id, mailbox)``. Skips if none exists.

    The mailbox is returned, not discarded: `save_attachments` requires
    `account` + `mailbox` for an RFC Message-ID since #415, and that pair
    is also what engages the #371 IMAP fast path — so this benchmark
    measures the call shape callers are meant to use.
    """
    for mb in ("INBOX", "Archive", "Sent Messages"):
        try:
            results = connector.search_messages(
                account=test_account, mailbox=mb, has_attachment=True, limit=1
            )
        except Exception:
            continue
        if results:
            return results[0]["id"], mb
    pytest.skip(
        f"No messages with attachments in account {test_account!r}. "
        f"Benchmark requires at least one such message in INBOX, Archive, "
        f"or Sent Messages."
    )


def test_save_attachments_one_file(
    connector: AppleMailConnector,
    message_with_attachment: tuple[str, str],
    test_account: str,
    tmp_path: Path,
    baselines: dict[str, float],
    capture_mode: bool,
) -> None:
    """Baseline: save attachments from one message into a tmp dir.

    Each iteration uses a fresh subdirectory to avoid filename-collision
    overwrites, but does NOT redownload from the IMAP server — Mail.app
    serves attachments from its local cache for read messages.

    Passes `account` + `mailbox`: since #415 an RFC Message-ID without them
    is refused outright (the all-mailbox `whose message id` scan freezes
    Mail), so the un-scoped call this used to make has been failing since
    that guard landed — benchmarks aren't in CI, so it went unnoticed.
    """
    name = "save_attachments_one_file"
    message_id, mailbox = message_with_attachment

    iteration = [0]

    # Scope ONLY an RFC Message-ID. `search_messages` emits the RFC id on the
    # IMAP path but Mail's numeric id when it degrades to AppleScript, so the
    # form here is not deterministic. A numeric id must go unscoped: the #415
    # guard only rejects "@" ids, `whose id is N` is indexed and safe, and
    # passing account+mailbox with a numeric id routes it to an IMAP fetch
    # that cannot use it.
    scope = (
        {"account": test_account, "mailbox": mailbox}
        if "@" in message_id
        else {}
    )

    def run() -> None:
        iteration[0] += 1
        out_dir = tmp_path / f"run_{iteration[0]}"
        out_dir.mkdir()
        connector.save_attachments(message_id, out_dir, **scope)

    result: BenchmarkResult = measure_median(run, name=name)
    assert_within_baseline(name, result, baselines, capture_mode)
