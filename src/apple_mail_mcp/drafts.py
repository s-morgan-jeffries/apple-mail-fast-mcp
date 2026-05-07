"""Persistent state for drafts created by ``create_draft``.

Stores forward-seed metadata so ``update_draft`` can rebuild a forwarded
draft. Mail.app's ``forward`` AppleScript command does not set any
header that would let us recover the original message ID later
(unlike ``reply``, which populates ``In-Reply-To``), so the seed has
to be persisted by the caller path.

Reply seeds don't need persistence — ``In-Reply-To`` carries the
original Message-ID through Mail's ``reply`` command. Fresh drafts
have no seed at all.

File layout: one JSON file per draft at ``<root>/<draft_id>.json``,
with the shape ``{"forward_of": "<mail-app-internal-message-id>"}``.

``draft_id`` is regex-validated before any path is constructed so
user-controlled input cannot escape the drafts directory.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .exceptions import MailDraftInvalidIdError

# Mail.app internal message ids are numeric strings in practice
# (e.g. "160991"), but allow alphanumerics + - _ for safety. The 128
# char cap is generous for any conceivable id format.
_DRAFT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_EXT = ".json"


def _validate_draft_id(draft_id: str) -> None:
    if not isinstance(draft_id, str) or not _DRAFT_ID_RE.match(draft_id):
        raise MailDraftInvalidIdError(
            f"draft_id {draft_id!r} must match {_DRAFT_ID_RE.pattern}"
        )


def default_root() -> Path:
    """Default drafts state directory, honoring ``APPLE_MAIL_MCP_HOME``.

    Resolved at call time so env-var overrides and test-time monkeypatching
    are honored.
    """
    home_override = os.environ.get("APPLE_MAIL_MCP_HOME")
    base = Path(home_override) if home_override else Path.home() / ".apple_mail_mcp"
    return base / "drafts"


class DraftStateStore:
    """File-backed store for forward-seed metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    def _path_for(self, draft_id: str) -> Path:
        _validate_draft_id(draft_id)
        return self.root / f"{draft_id}{_EXT}"

    def get_forward_of(self, draft_id: str) -> str | None:
        """Return the forward-seed message id for ``draft_id``, or None.

        Corrupt or unreadable state files are treated as "no state" rather
        than raised — they would just block update_draft for a draft we
        can't recover anyway, and the user can still delete + re-create.
        """
        path = self._path_for(draft_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        forward_of = data.get("forward_of")
        return forward_of if isinstance(forward_of, str) else None

    def set_forward_of(self, draft_id: str, forward_of: str) -> None:
        """Persist the forward-seed message id for ``draft_id``."""
        path = self._path_for(draft_id)
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"forward_of": forward_of}),
            encoding="utf-8",
        )

    def delete(self, draft_id: str) -> None:
        """Remove the state file for ``draft_id``. Idempotent."""
        path = self._path_for(draft_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
