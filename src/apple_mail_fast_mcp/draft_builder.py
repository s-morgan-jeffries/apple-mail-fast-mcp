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

import email
import mimetypes
import re
from dataclasses import dataclass, field
from email.message import EmailMessage, MIMEPart
from email.policy import default as _default_policy
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parseaddr
from pathlib import Path
from typing import Any

# A single forwarded attachment carried over from the original message:
# (filename, maintype, subtype, payload_bytes).
ForwardedAttachment = tuple[str, str, str, bytes]

_RE_PREFIX = re.compile(r"^\s*re:\s*", re.IGNORECASE)
_FWD_PREFIX = re.compile(r"^\s*(?:fwd?|forward):\s*", re.IGNORECASE)
# Message-ID tokens inside a References header (angle-bracketed, no spaces).
_TAG_TOKENS = re.compile(r"<[^>\s]+>")


def _sanitize_header(value: str) -> str:
    """Strip characters that would corrupt or inject email headers.

    Removes NUL (which the email lib passes through silently) and CR/LF
    (which would otherwise raise or enable header injection). Mirrors the
    AppleScript path's sanitize_input convention (#173).
    """
    return value.replace("\x00", "").replace("\r", "").replace("\n", "")


def _attach_forwarded(
    msg: EmailMessage,
    filename: str,
    maintype: str,
    subtype: str,
    payload: bytes,
) -> None:
    """Attach one carried-over original attachment to a draft being built.

    A forwarded email (``message/rfc822``) is attached as a parsed
    sub-Message so the part is encoded idiomatically (7bit/8bit per RFC 2046
    §5.2.1) and re-parses cleanly. Attaching the raw bytes would base64-encode
    them — non-conformant for ``message/*``, and the parser then reads that
    back as corrupt content. Everything else attaches as raw bytes.
    (rfc822 empty-bytes fix)
    """
    safe_name = _sanitize_header(filename) or "attachment"
    if (maintype, subtype) == ("message", "rfc822"):
        sub_msg = email.message_from_bytes(payload, policy=_default_policy)
        msg.add_attachment(sub_msg, filename=safe_name)
    else:
        msg.add_attachment(
            payload,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=safe_name,
        )


def build_draft_mime(
    *,
    sender: str,
    to: list[str],
    subject: str,
    body: str,
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[Path] | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    forwarded_attachments: list[ForwardedAttachment] | None = None,
) -> tuple[str, bytes]:
    """Build a draft message (plain-text, or multipart/alternative for HTML).

    Returns ``(message_id, raw_bytes)`` where ``message_id`` is the
    generated RFC 5322 Message-ID (angle-bracketed) and ``raw_bytes`` is
    the serialized message suitable for ``IMAPClient.append``.

    HTML body (issue #251): when ``body_html`` is given the message is built
    as ``multipart/alternative`` with a ``text/html`` part and a
    ``text/plain`` alternative. The plain part is ``body`` when supplied,
    otherwise a crude text rendering of the HTML (so non-HTML readers and
    reply-quoting still have something). ``body_html`` is caller-trusted
    content (like ``body``); it is MIME-encoded but not HTML-sanitized.

    Reply/forward extras (issue #245 follow-up):

    - ``in_reply_to`` / ``references`` set the threading headers so the
      drafted reply/forward stays in the original conversation. Pass the
      values bracketed (``<id@host>``); they are header-sanitized but not
      otherwise reshaped.
    - ``forwarded_attachments`` are ``(filename, maintype, subtype,
      payload)`` tuples carried over from the original message, used when
      forwarding so the original's files travel with the draft.
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
    if in_reply_to:
        msg["In-Reply-To"] = _sanitize_header(in_reply_to)
    if references:
        msg["References"] = " ".join(_sanitize_header(r) for r in references)
    if body_html is not None:
        # multipart/alternative: text/plain first (fallback + reply quoting),
        # then text/html. Derive the plain part from the HTML when no
        # explicit plain body was supplied. (#251)
        msg.set_content(body if body else _html_to_text(body_html))
        msg.add_alternative(body_html, subtype="html")
    else:
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

    for filename, maintype, subtype, payload in forwarded_attachments or []:
        _attach_forwarded(msg, filename, maintype, subtype, payload)

    return message_id, msg.as_bytes()


def reply_subject(original_subject: str) -> str:
    """``Re:``-prefix a subject, without stacking a second ``Re:``."""
    s = (original_subject or "").strip()
    if _RE_PREFIX.match(s):
        return s
    return f"Re: {s}" if s else "Re:"


def forward_subject(original_subject: str) -> str:
    """``Fwd:``-prefix a subject, without stacking a second ``Fwd:``."""
    s = (original_subject or "").strip()
    if _FWD_PREFIX.match(s):
        return s
    return f"Fwd: {s}" if s else "Fwd:"


def _email_of(addr: str) -> str:
    return parseaddr(addr)[1].lower()


def derive_reply_recipients(
    *,
    from_header: str,
    reply_to_header: str = "",
    to_header: str = "",
    cc_header: str = "",
    self_addresses: list[str] | None = None,
    reply_all: bool = False,
) -> tuple[list[str], list[str]]:
    """Derive (to, cc) for a reply from the original message's headers.

    - Primary recipient is the original ``Reply-To`` if present, else
      ``From``.
    - ``reply_all`` adds the original ``To`` + ``Cc`` as Cc, minus any of
      the account's own ``self_addresses`` and minus the primary (so the
      replier isn't cc'ing themselves or duplicating the To).
    - Address display names are preserved (``Name <email>``).

    Returns ``(to, cc)`` as lists of formatted address strings.
    """
    selves = {a.lower() for a in (self_addresses or [])}

    primary_pairs = getaddresses([reply_to_header or from_header])
    to_list = [formataddr(p) for p in primary_pairs if p[1]]
    primary_emails = {p[1].lower() for p in primary_pairs if p[1]}

    cc_list: list[str] = []
    if reply_all:
        seen = set(primary_emails) | selves
        for name, email_addr in getaddresses([to_header, cc_header]):
            if not email_addr:
                continue
            key = email_addr.lower()
            if key in seen:
                continue
            seen.add(key)
            cc_list.append(formataddr((name, email_addr)))
    return to_list, cc_list


def _quote_lines(text: str) -> str:
    """Prefix each line of ``text`` with ``> `` (email plain-text quoting)."""
    return "\n".join(
        (f"> {line}" if line else ">") for line in (text or "").splitlines()
    )


def build_reply_body(
    *,
    new_body: str,
    original_from: str,
    original_date: str,
    original_text: str,
) -> str:
    """Compose a plain-text reply body: the new text, then an attribution
    line, then the original quoted with ``> ``.
    """
    attribution = f"On {original_date.strip()}, {original_from.strip()} wrote:"
    return (
        f"{new_body.rstrip()}\n\n"
        f"{attribution}\n"
        f"{_quote_lines(original_text)}\n"
    )


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str) -> str:
    """Crude HTML→text fallback for messages with no text/plain part.

    Drops tags and collapses runs of spaces. Good enough to quote in a
    reply; we are not trying to faithfully render HTML.
    """
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = _TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return _WS_RE.sub(" ", text).strip()


@dataclass
class OriginalMessage:
    """The fields of an original message needed to rebuild a clean
    reply/forward draft. Produced by :func:`parse_original_message`.
    """

    message_id: str = ""
    from_header: str = ""
    reply_to_header: str = ""
    to_header: str = ""
    cc_header: str = ""
    subject: str = ""
    date: str = ""
    references: list[str] = field(default_factory=list)
    text: str = ""
    attachments: list[ForwardedAttachment] = field(default_factory=list)


def _attachment_payload_bytes(part: MIMEPart[Any, Any]) -> bytes:
    """Decode one attachment part to its raw bytes.

    Ordinary parts decode via ``get_payload(decode=True)``. A ``message/*``
    part (a forwarded email) holds a sub-Message, not a transfer-encoded
    string, so decode returns ``None`` — serialize the sub-message, but only
    when the transfer encoding is one RFC 2046 §5.2.1 permits for ``message/*``
    (7bit/8bit/binary/none). A non-conformant base64/quoted-printable message
    part is parsed from its *still-encoded* text and would serialize to corrupt
    bytes, so degrade to ``b""``. (rfc822 empty-bytes fix)
    """
    decoded = part.get_payload(decode=True)
    if isinstance(decoded, (bytes, bytearray)):
        return bytes(decoded)
    if part.get_content_maintype() == "message":
        cte = (part.get("Content-Transfer-Encoding") or "").strip().lower()
        sub = part.get_payload()
        if (
            cte in ("", "7bit", "8bit", "binary")
            and isinstance(sub, list)
            and sub
            and hasattr(sub[0], "as_bytes")
        ):
            return sub[0].as_bytes()
    return b""


def _walk_attachment_parts(
    part: MIMEPart[Any, Any], out: list[MIMEPart[Any, Any]]
) -> None:
    """Collect attachment parts in MIME document order.

    Applies the same inclusion predicate as the IMAP BODYSTRUCTURE metadata
    walk (``imap_connector._bodystructure_extract_attachments``): a leaf counts
    if its disposition is ``attachment``, or ``inline`` with a filename, or it
    is ``message/rfc822``. A ``message/rfc822`` part is emitted whole and NOT
    descended into — its own sub-parts belong to the forwarded email, not the
    outer message — matching the metadata walk's leaf treatment.
    """
    if part.get_content_type() == "message/rfc822":
        out.append(part)
        return
    if part.get_content_maintype() == "multipart":
        for child in part.iter_parts():
            _walk_attachment_parts(child, out)
        return
    disp = part.get_content_disposition()
    if disp == "attachment" or (disp == "inline" and part.get_filename()):
        out.append(part)


def extract_attachment_payloads(raw: bytes) -> list[ForwardedAttachment]:
    """Enumerate a message's attachments AS BYTES, matching the order and
    membership of the IMAP BODYSTRUCTURE metadata list that ``get_attachments``
    / ``get_messages`` report.

    The byte-fetch tools (``get_attachment_content`` / ``save_attachments``)
    index into this with a 0-based ``attachment_index`` that callers take from
    the metadata list — so the two MUST agree. ``email.iter_attachments()``
    does not: it drops body-referenced inline parts (multipart/related inline
    images with filenames) and skips parts nested under a multipart/
    alternative, so it diverges from the metadata list and broke the index
    contract (out-of-range, or — worse — a different part's bytes). The
    concrete divergences were found by dogfooding real iCloud messages.

    Distinct from :func:`parse_original_message`, which deliberately keeps
    stdlib ``iter_attachments`` semantics for the reply/forward draft path.
    """
    msg = email.message_from_bytes(raw, policy=_default_policy)
    parts: list[MIMEPart[Any, Any]] = []
    _walk_attachment_parts(msg, parts)
    out: list[ForwardedAttachment] = []
    for part in parts:
        maintype, _, subtype = part.get_content_type().partition("/")
        # Membership/order match the metadata list (that's the index
        # contract); the name default differs by design — a nameless part
        # lists as "" in metadata but needs a usable save name here.
        out.append(
            (
                part.get_filename() or "attachment",
                maintype,
                subtype,
                _attachment_payload_bytes(part),
            )
        )
    return out


def parse_original_message(raw: bytes) -> OriginalMessage:
    """Parse a raw RFC 822 message into the pieces needed for a reply or
    forward. Prefers the ``text/plain`` body; falls back to a crude
    text rendering of ``text/html`` when that's all the message has.
    """
    msg = email.message_from_bytes(raw, policy=_default_policy)

    text = ""
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        text = plain.get_content()
    else:
        html = msg.get_body(preferencelist=("html",))
        if html is not None:
            text = _html_to_text(html.get_content())

    # NOTE: the reply/forward path keeps stdlib iter_attachments semantics
    # (carry only non-inline attachments into the new draft). The byte-fetch
    # path uses extract_attachment_payloads instead — it must match the IMAP
    # metadata list's membership/order for the attachment_index contract.
    attachments: list[ForwardedAttachment] = []
    for part in msg.iter_attachments():
        maintype, _, subtype = part.get_content_type().partition("/")
        attachments.append(
            (
                part.get_filename() or "attachment",
                maintype,
                subtype,
                _attachment_payload_bytes(part),
            )
        )

    refs_raw = msg.get("References", "") or ""
    references = _TAG_TOKENS.findall(refs_raw)

    return OriginalMessage(
        message_id=(msg.get("Message-ID", "") or "").strip(),
        from_header=str(msg.get("From", "") or ""),
        reply_to_header=str(msg.get("Reply-To", "") or ""),
        to_header=str(msg.get("To", "") or ""),
        cc_header=str(msg.get("Cc", "") or ""),
        subject=str(msg.get("Subject", "") or ""),
        date=str(msg.get("Date", "") or ""),
        references=references,
        text=text,
        attachments=attachments,
    )


def build_forward_body(
    *,
    new_body: str,
    original_from: str,
    original_date: str,
    original_subject: str,
    original_to: str,
    original_text: str,
) -> str:
    """Compose a plain-text forward body: the new text, then a standard
    forwarded-message header block, then the original text (unquoted).
    """
    header_block = (
        "---------- Forwarded message ----------\n"
        f"From: {original_from.strip()}\n"
        f"Date: {original_date.strip()}\n"
        f"Subject: {original_subject.strip()}\n"
        f"To: {original_to.strip()}\n"
    )
    return f"{new_body.rstrip()}\n\n{header_block}\n{original_text}\n"
