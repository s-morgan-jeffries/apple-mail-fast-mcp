"""Build a clean RFC822 draft message for IMAP APPEND (issue #245).

Mail.app's AppleScript ``content`` setter wraps every body in an
``Apple-Mail-URLShareWrapper`` ``<blockquote type="cite">`` (a Mail.app
bug, FB11734014) that renders as a quote on iOS. Creating the draft as a
hand-built RFC822 message and APPENDing it over IMAP bypasses that path
entirely.

This module is intentionally pure (no Mail.app, no IMAP) so the MIME
shape is unit-testable in isolation.
"""

from __future__ import annotations

import mimetypes
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path


def _sanitize_header(value: str) -> str:
    """Strip characters that would corrupt or inject email headers.

    Removes NUL (which the email lib passes through silently) and CR/LF
    (which would otherwise raise or enable header injection). Mirrors the
    AppleScript path's sanitize_input convention (#173).
    """
    return value.replace("\x00", "").replace("\r", "").replace("\n", "")


def build_draft_mime(
    *,
    sender: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> tuple[str, bytes]:
    """Build a plain-text draft message.

    Returns ``(message_id, raw_bytes)`` where ``message_id`` is the
    generated RFC 5322 Message-ID (angle-bracketed) and ``raw_bytes`` is
    the serialized message suitable for ``IMAPClient.append``.
    """
    msg = EmailMessage()
    message_id = make_msgid()
    msg["Message-ID"] = message_id
    msg["From"] = _sanitize_header(sender)
    msg["To"] = ", ".join(_sanitize_header(a) for a in to)
    if cc:
        msg["Cc"] = ", ".join(_sanitize_header(a) for a in cc)
    if bcc:
        msg["Bcc"] = ", ".join(_sanitize_header(a) for a in bcc)
    msg["Subject"] = _sanitize_header(subject)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    for path in attachments or []:
        path = Path(path)
        ctype, _encoding = mimetypes.guess_type(path.name)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=path.name,
        )

    return message_id, msg.as_bytes()
