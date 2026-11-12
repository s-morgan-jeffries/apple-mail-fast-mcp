"""Compile the AppleScript that create_draft generates, with the real
``osacompile``.

String-match tests (``"reply origMsg ..." in script``) can pass while the
script itself does not compile: reply-all shipped as
``reply to all origMsg opening window false``, which Mail rejects with
-2741 ("Expected end of line, etc. but found application constant or
consideration"). ``reply to all`` is a boolean parameter of ``reply``, not
a verb. These tests capture the script ``create_draft`` would hand to
``osascript`` and compile it against Mail's dictionary, so a syntax error
fails here instead of at a user's first reply-all.

Compiling only resolves terminology from Mail's scripting dictionary; it
does not run the script, touch any mailbox, or send anything.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from apple_mail_fast_mcp.mail_connector import AppleMailConnector

OSACOMPILE = shutil.which("osacompile")

pytestmark = [
    pytest.mark.allow_real_io,
    pytest.mark.skipif(
        sys.platform != "darwin" or OSACOMPILE is None,
        reason="osacompile (macOS) is required to compile AppleScript",
    ),
]


def _generated_script(**kwargs: object) -> str:
    """Return the AppleScript create_draft builds for ``kwargs``.

    The clean IMAP/SMTP paths are disabled so the AppleScript path is the
    one taken, and ``_run_applescript`` is captured instead of executed.
    """
    connector = AppleMailConnector(timeout=30)
    with (
        patch.object(
            AppleMailConnector, "_try_clean_create_or_send", return_value=None
        ),
        patch.object(
            AppleMailConnector, "_effective_from_account", return_value=None
        ),
        patch.object(
            AppleMailConnector, "_run_applescript", return_value="1"
        ) as run,
    ):
        connector.create_draft(**kwargs)  # type: ignore[arg-type]
    script = run.call_args[0][0]
    assert isinstance(script, str)
    return script


def _compile(script: str, tmp_path: Path) -> None:
    src = tmp_path / "draft.applescript"
    src.write_text(script, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 — fixed binary, our own temp file
        [OSACOMPILE, "-o", str(tmp_path / "draft.scpt"), str(src)],  # type: ignore[list-item]
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"generated AppleScript does not compile:\n{result.stderr}\n"
        f"--- script ---\n{script}"
    )


@pytest.fixture
def attachment(tmp_path: Path) -> Path:
    p = tmp_path / "note.pdf"
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


class TestCreateDraftScriptsCompile:
    def test_new(self, tmp_path: Path) -> None:
        _compile(
            _generated_script(
                seed="new", to=["a@example.com"], subject="s", body="b"
            ),
            tmp_path,
        )

    def test_reply(self, tmp_path: Path) -> None:
        script = _generated_script(seed="reply", seed_id="160989", body="b")
        assert "reply to all" not in script
        _compile(script, tmp_path)

    def test_reply_all(self, tmp_path: Path) -> None:
        script = _generated_script(
            seed="reply", seed_id="160989", reply_all=True, body="b"
        )
        assert "reply to all true" in script
        _compile(script, tmp_path)

    def test_reply_all_with_recipient_overrides(self, tmp_path: Path) -> None:
        _compile(
            _generated_script(
                seed="reply",
                seed_id="160989",
                reply_all=True,
                to=["a@example.com"],
                cc=["b@example.com"],
                bcc=[],
                subject="Re: s",
                body="b",
            ),
            tmp_path,
        )

    def test_forward(self, tmp_path: Path) -> None:
        _compile(
            _generated_script(
                seed="forward", seed_id="160989", to=["a@example.com"], body="b"
            ),
            tmp_path,
        )

    def test_new_with_attachment(self, tmp_path: Path, attachment: Path) -> None:
        script = _generated_script(
            seed="new",
            to=["a@example.com"],
            subject="s",
            body="b",
            attachment_paths=[attachment],
        )
        assert "make new attachment" in script
        _compile(script, tmp_path)

    def test_reply_all_with_attachment(
        self, tmp_path: Path, attachment: Path
    ) -> None:
        script = _generated_script(
            seed="reply",
            seed_id="160989",
            reply_all=True,
            body="b",
            attachment_paths=[attachment],
        )
        assert "make new attachment" in script
        _compile(script, tmp_path)
