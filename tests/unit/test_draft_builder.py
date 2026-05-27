"""Unit tests for the clean RFC822 draft builder (issue #245).

The builder exists so drafts can be created via IMAP APPEND instead of
Mail.app's AppleScript ``content`` setter, which wraps every body in an
``Apple-Mail-URLShareWrapper`` ``<blockquote type="cite">`` (renders as a
quote on iOS). These tests pin the clean output.
"""

from __future__ import annotations

import email
from email import policy

from apple_mail_mcp.draft_builder import build_draft_mime


def test_builds_plain_text_draft_without_quote_wrapper():
    msgid, raw = build_draft_mime(
        sender="email@fmasi.eu",
        to=["lazar@hadleigh.co.uk"],
        subject="Re: Flat 9 Constable House",
        body="Hi Lazar,\n\nLine two.",
    )
    text = raw.decode("utf-8")
    # The whole point of the fix: no cite-blockquote wrapper.
    assert "blockquote" not in text.lower()
    assert "urlshare" not in text.lower()

    msg = email.message_from_bytes(raw, policy=policy.default)
    assert msg["From"] == "email@fmasi.eu"
    assert msg["To"] == "lazar@hadleigh.co.uk"
    assert msg["Subject"] == "Re: Flat 9 Constable House"
    assert msg["Message-ID"] == msgid
    assert msg.get_content_type() == "text/plain"
    assert "Line two." in msg.get_content()


def test_multiple_recipients_and_cc_bcc():
    _msgid, raw = build_draft_mime(
        sender="email@fmasi.eu",
        to=["a@example.invalid", "b@example.invalid"],
        cc=["c@example.invalid"],
        bcc=["d@example.invalid"],
        subject="hi",
        body="body",
    )
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert msg["To"] == "a@example.invalid, b@example.invalid"
    assert msg["Cc"] == "c@example.invalid"
    assert msg["Bcc"] == "d@example.invalid"


def test_attachment_is_included_with_body(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake")
    _msgid, raw = build_draft_mime(
        sender="email@fmasi.eu",
        to=["x@example.invalid"],
        subject="hi",
        body="see attached",
        attachments=[pdf],
    )
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert msg.is_multipart()
    parts = list(msg.iter_parts())
    body_part = next(p for p in parts if p.get_content_type() == "text/plain")
    assert "see attached" in body_part.get_content()
    att = next(p for p in parts if p.get_filename() == "invoice.pdf")
    assert att.get_content_type() == "application/pdf"
    assert att.get_payload(decode=True) == b"%PDF-1.7\nfake"
    assert "blockquote" not in raw.decode("utf-8", "replace").lower()


def test_sanitizes_header_injection_chars():
    # NUL and CR/LF in header-bound fields must not survive into the
    # serialized headers (parity with the AppleScript path, #173, and
    # header-injection safety).
    _msgid, raw = build_draft_mime(
        sender="Alice\x00Smith <me@x.com>",
        to=["a@example.invalid\r\nBcc: evil@example.invalid"],
        subject="hi\r\nX-Injected: yes",
        body="body",
    )
    assert b"\x00" not in raw
    msg = email.message_from_bytes(raw, policy=policy.default)
    # No header injection: the CR/LF collapse into a single (harmless)
    # value, so the smuggled headers never materialize as real headers.
    assert msg["From"] == "AliceSmith <me@x.com>"
    assert msg["Bcc"] is None
    assert msg["X-Injected"] is None
