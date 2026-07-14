"""Shared fixtures for unit tests."""

import socket
import subprocess

import pytest

from apple_mail_fast_mcp.mail_connector import AppleMailConnector
from apple_mail_fast_mcp.security import rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Reset rate limiter state between tests to prevent cross-contamination."""
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _block_real_io(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail fast on real network / DNS / subprocess in the unit suite (#408).

    A unit test that reaches real DNS, a real socket, or a real subprocess
    (``osascript`` / the ``security`` Keychain CLI) is a bug: it's fast on a
    dev machine but blocks for seconds in CI, silently ballooning the suite.
    That's exactly what #408 was — ``build_draft_mime`` → ``make_msgid()`` →
    ``socket.getfqdn()`` reverse-DNS, ~5s per call in CI — and #298 before it
    (an un-mocked osascript fallback). A first osascript can also trigger a
    ~20-30s Mail.app cold-launch in CI. Surface such leaks as an immediate
    ``RuntimeError`` instead of a multi-minute hang.

    Everything that touches the OS in production is already mocked in the unit
    suite (``IMAPClient`` at the module symbol, ``smtplib``, ``_run_applescript``,
    ``subprocess.run``), so this breaks nothing; an in-test ``mock.patch`` of a
    seam shadows this fixture. Tests that genuinely need a live seam opt out
    with ``@pytest.mark.allow_real_io``.
    """
    if request.node.get_closest_marker("allow_real_io"):
        return

    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(
            "Real network/DNS/subprocess in a unit test (#408): mock it, or "
            "mark the test @pytest.mark.allow_real_io."
        )

    for name in (
        "getfqdn",
        "getaddrinfo",
        "gethostbyaddr",
        "gethostbyname",
        "create_connection",
    ):
        monkeypatch.setattr(socket, name, _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)


@pytest.fixture(autouse=True)
def _no_applescript_keychain_fallback(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the unit suite off real AppleScript.

    On a Keychain miss, ``_get_imap_password_with_fallback`` calls
    ``_alternative_account_identifier`` → ``list_accounts()`` → real
    ``osascript`` (the #243 name↔UUID fallback). The ~14 keychain-miss
    unit tests mock ``get_imap_password``/``_resolve_imap_config`` but not
    that fallback, so each fired a live osascript call — ~0.85s locally but
    ~30s in CI (Mail.app unresponsive), ballooning the suite to ~5 min
    (#298). Stub it to ``None`` so the fallback re-raises the original
    ``MailKeychainEntryNotFoundError`` (what those tests already assert)
    without touching AppleScript.

    Tests that exercise the real fallback (``TestKeychainDualFormLookup``)
    mock ``list_accounts`` on the instance and opt out via the
    ``real_account_fallback`` marker.
    """
    if request.node.get_closest_marker("real_account_fallback"):
        return
    monkeypatch.setattr(
        AppleMailConnector,
        "_alternative_account_identifier",
        lambda self, account: None,
    )
