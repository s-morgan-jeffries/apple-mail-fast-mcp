"""Email-provider detection + app-password guidance for guided setup (#384).

Pure data + a host/email → :class:`Provider` lookup. The CLI (`setup-imap`)
uses this to point users at the right app-specific-password page and print
provider-specific two-factor guidance. No I/O here — the CLI does the printing
and (optionally) opens the URL.
"""

from __future__ import annotations

from dataclasses import dataclass

from .utils import is_icloud_imap_host


@dataclass(frozen=True)
class Provider:
    """A known email provider and how to generate an app-specific password."""

    key: str
    name: str
    app_password_url: str | None
    steps: tuple[str, ...]


ICLOUD = Provider(
    key="icloud",
    name="iCloud",
    app_password_url="https://account.apple.com/account/manage",
    steps=(
        "Requires two-factor authentication on your Apple Account.",
        "Sign-In and Security → App-Specific Passwords → Generate.",
        "Copy the generated password (looks like xxxx-xxxx-xxxx-xxxx).",
    ),
)

GMAIL = Provider(
    key="gmail",
    name="Gmail",
    app_password_url="https://myaccount.google.com/apppasswords",
    steps=(
        "Requires 2-Step Verification to be turned on.",
        "Create an app password (any name) — you get a 16-character code.",
        "Paste it below (spaces are fine — they're stripped).",
    ),
)

YAHOO = Provider(
    key="yahoo",
    name="Yahoo",
    app_password_url="https://login.yahoo.com/account/security",
    steps=(
        "Turn on two-step verification, then 'Generate app password'.",
        "Copy the generated password and paste it below.",
    ),
)

OUTLOOK = Provider(
    key="outlook",
    name="Outlook / Microsoft",
    app_password_url="https://account.microsoft.com/security",
    steps=(
        "Advanced security options → App passwords → Create.",
        "App passwords require two-step verification to be on, and are "
        "unavailable on some managed/work accounts.",
    ),
)

FASTMAIL = Provider(
    key="fastmail",
    name="Fastmail",
    app_password_url="https://app.fastmail.com/settings/security/apppassword",
    steps=(
        "Settings → Password & Security → App Passwords → New.",
        "Scope it to 'Mail (IMAP/SMTP)' and paste the password below.",
    ),
)

GENERIC = Provider(
    key="generic",
    name="your email provider",
    app_password_url=None,
    steps=(
        "In your provider's account security settings, look for "
        "'app password' or 'app-specific password'.",
        "You'll usually need to enable two-factor auth first.",
        "Generate one scoped to Mail/IMAP and paste it below.",
    ),
)

PROVIDERS: dict[str, Provider] = {
    p.key: p for p in (ICLOUD, GMAIL, YAHOO, OUTLOOK, FASTMAIL, GENERIC)
}

# Host-suffix → provider key. iCloud is handled separately via
# ``is_icloud_imap_host`` (it covers the per-partition ``p*-imap.mail.me.com``
# names). Order doesn't matter — suffixes are unambiguous.
_HOST_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("gmail.com", "gmail"),
    ("googlemail.com", "gmail"),
    ("mail.yahoo.com", "yahoo"),
    ("yahoo.com", "yahoo"),
    ("outlook.com", "outlook"),
    ("office365.com", "outlook"),
    ("hotmail.com", "outlook"),
    ("fastmail.com", "fastmail"),
    ("messagingengine.com", "fastmail"),
)

# Email-domain → provider key, used only when the host doesn't match.
_EMAIL_DOMAINS: dict[str, str] = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "icloud.com": "icloud",
    "me.com": "icloud",
    "mac.com": "icloud",
    "yahoo.com": "yahoo",
    "yahoo.co.uk": "yahoo",
    "ymail.com": "yahoo",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "msn.com": "outlook",
    "fastmail.com": "fastmail",
    "fastmail.fm": "fastmail",
}


def detect_provider(host: str, email: str) -> Provider:
    """Map an IMAP ``host`` (preferred) or ``email`` domain to a Provider.

    Host is the reliable signal, so it wins; the email domain is a fallback for
    when Mail.app reports no server (POP / mid-config). Unknown → ``GENERIC``.
    """
    h = (host or "").strip().lower()
    if is_icloud_imap_host(h):
        return ICLOUD
    for suffix, key in _HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return PROVIDERS[key]

    domain = (email or "").strip().lower().rsplit("@", 1)[-1]
    email_key = _EMAIL_DOMAINS.get(domain)
    return PROVIDERS[email_key] if email_key else GENERIC
