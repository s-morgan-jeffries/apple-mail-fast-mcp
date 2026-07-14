"""Persisted per-account IMAP login overrides (#341).

`_resolve_imap_config` derives the IMAP LOGIN username from Mail.app's
account properties. For a few account shapes that derivation is wrong and
can't be corrected from the properties alone — notably an iCloud account
whose Apple ID is a third-party email (e.g. ``@gmail.com``) with no
``@icloud.com`` alias in Mail.app's ``email addresses`` (#299's apple-alias
rule has nothing to pick from). The login then fails with
AUTHENTICATIONFAILED against ``*.mail.me.com``.

This module persists an explicit ``account -> login email`` override the
user supplies via ``setup-imap --email``, so runtime resolution honors the
same login that setup verified. The override value is a non-secret email
address (the password stays in the Keychain), so a small JSON file under
``~/.apple_mail_mcp/`` is the right home — matching the templates/ and
drafts/ stores.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _overrides_path() -> Path:
    """Path to the overrides file, honoring ``APPLE_MAIL_MCP_HOME``.

    Resolved at call time so env-var overrides and test-time monkeypatching
    are honored (same convention as templates/drafts ``default_root``).
    """
    home_override = os.environ.get("APPLE_MAIL_MCP_HOME")
    base = (
        Path(home_override)
        if home_override
        else Path.home() / ".apple_mail_mcp"
    )
    return base / "imap_login_overrides.json"


def _load() -> dict[str, str]:
    """Load the override map. A missing, unreadable, or corrupt file yields
    an empty map — overrides must never raise into the IMAP resolve path."""
    path = _overrides_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Keep only str->str entries; ignore anything malformed.
    return {
        str(k): str(v)
        for k, v in data.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def get_login_override(account: str) -> str | None:
    """Return the persisted IMAP login email for ``account``, or ``None``.

    Empty/whitespace-only stored values are treated as absent.
    """
    value = _load().get(account)
    if value and value.strip():
        return value.strip()
    return None


def set_login_override(account: str, email: str) -> None:
    """Persist ``account -> email`` (the IMAP LOGIN username). Creates the
    home directory and file if needed; merges with any existing entries."""
    overrides = _load()
    overrides[account] = email.strip()
    path = _overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(overrides, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def delete_login_override(account: str) -> None:
    """Remove ``account``'s override if present. No-op when absent or when
    the file doesn't exist."""
    overrides = _load()
    if account not in overrides:
        return
    del overrides[account]
    path = _overrides_path()
    if overrides:
        path.write_text(
            json.dumps(overrides, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        # Last entry removed — drop the file so an empty store leaves no
        # stray artifact.
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Server (host / port) overrides (#405)
#
# `_resolve_imap_config` reads the IMAP host/port from Mail.app's account
# properties. Some accounts (e.g. an institutional Zimbra account) misreport
# `port` scriptably — Mail.app's UI shows 993 (implicit TLS) but the
# scripting property returns 143 (the plaintext/STARTTLS default), so the
# implicit-TLS handshake fails with WRONG_VERSION_NUMBER. `setup-imap
# --host/--port` persists an explicit override here, honored at runtime, so
# the connection uses the correct values regardless of what Mail.app reports.
# Kept in a separate file from the login override so the two evolve
# independently.
# ---------------------------------------------------------------------------


def _server_overrides_path() -> Path:
    """Path to the server-override (host/port) file, honoring
    ``APPLE_MAIL_MCP_HOME`` (resolved at call time, same convention as
    :func:`_overrides_path`)."""
    home_override = os.environ.get("APPLE_MAIL_MCP_HOME")
    base = (
        Path(home_override)
        if home_override
        else Path.home() / ".apple_mail_mcp"
    )
    return base / "imap_server_overrides.json"


def _load_server() -> dict[str, dict[str, Any]]:
    """Load the server-override map. A missing, unreadable, or corrupt file
    yields an empty map — overrides must never raise into the IMAP resolve
    path. Keeps only ``str -> dict`` entries."""
    path = _server_overrides_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(k): v
        for k, v in data.items()
        if isinstance(k, str) and isinstance(v, dict)
    }


def get_host_override(account: str) -> str | None:
    """Return the persisted IMAP host override for ``account``, or ``None``.
    Empty/whitespace-only values are treated as absent."""
    host = _load_server().get(account, {}).get("host")
    if isinstance(host, str) and host.strip():
        return host.strip()
    return None


def get_port_override(account: str) -> int | None:
    """Return the persisted IMAP port override for ``account``, or ``None``.
    Non-int / out-of-range values are treated as absent (``bool`` is a
    subclass of ``int`` and is deliberately excluded)."""
    port = _load_server().get(account, {}).get("port")
    if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
        return port
    return None


def set_server_override(
    account: str, *, host: str | None, port: int | None
) -> None:
    """Persist host and/or port overrides for ``account`` (#405).

    Only the provided fields are stored; passing both ``None`` is a no-op
    (never creates a stray entry/file). Replaces any existing entry for the
    account, and merges with entries for other accounts.
    """
    entry: dict[str, Any] = {}
    if host and host.strip():
        entry["host"] = host.strip()
    if port is not None:
        entry["port"] = port
    if not entry:
        return
    overrides = _load_server()
    overrides[account] = entry
    path = _server_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(overrides, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def delete_server_override(account: str) -> None:
    """Remove ``account``'s server override if present. No-op when absent or
    when the file doesn't exist; drops the file when the last entry goes."""
    overrides = _load_server()
    if account not in overrides:
        return
    del overrides[account]
    path = _server_overrides_path()
    if overrides:
        path.write_text(
            json.dumps(overrides, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        path.unlink(missing_ok=True)
