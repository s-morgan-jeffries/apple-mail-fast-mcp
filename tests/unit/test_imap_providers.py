"""Unit tests for provider detection (#384)."""

import pytest

from apple_mail_fast_mcp.imap_providers import (
    GENERIC,
    PROVIDERS,
    Provider,
    detect_provider,
)


class TestDetectByHost:
    """Host is the reliable signal — match it first."""

    @pytest.mark.parametrize(
        "host, expected_key",
        [
            ("imap.gmail.com", "gmail"),
            ("imap.googlemail.com", "gmail"),
            ("imap.mail.me.com", "icloud"),
            ("p42-imap.mail.me.com", "icloud"),  # per-partition iCloud host
            ("imap.mail.yahoo.com", "yahoo"),
            ("outlook.office365.com", "outlook"),
            ("imap-mail.outlook.com", "outlook"),
            ("imap.fastmail.com", "fastmail"),
            ("imap.messagingengine.com", "fastmail"),  # Fastmail's backend
        ],
    )
    def test_known_hosts(self, host, expected_key):
        # Email is deliberately unrelated — host must win.
        p = detect_provider(host, "someone@example.org")
        assert p.key == expected_key
        assert p.app_password_url  # every known provider has a URL

    def test_host_is_case_insensitive(self):
        assert detect_provider("IMAP.GMAIL.COM", "").key == "gmail"


class TestDetectByEmailFallback:
    """When the host is empty/unknown, fall back to the email domain."""

    @pytest.mark.parametrize(
        "email, expected_key",
        [
            ("alice@gmail.com", "gmail"),
            ("alice@icloud.com", "icloud"),
            ("alice@me.com", "icloud"),
            ("alice@yahoo.com", "yahoo"),
            ("alice@yahoo.co.uk", "yahoo"),
            ("alice@outlook.com", "outlook"),
            ("alice@hotmail.com", "outlook"),
            ("alice@fastmail.com", "fastmail"),
        ],
    )
    def test_email_domain(self, email, expected_key):
        assert detect_provider("", email).key == expected_key

    def test_host_wins_over_email(self):
        # A Gmail host with an icloud address (unusual) → trust the host.
        assert detect_provider("imap.gmail.com", "x@icloud.com").key == "gmail"


class TestGeneric:
    def test_unknown_host_and_email_is_generic(self):
        p = detect_provider("imap.example.org", "bob@example.org")
        assert p.key == GENERIC.key
        assert p.app_password_url is None  # no page to point at

    def test_empty_inputs_are_generic(self):
        assert detect_provider("", "").key == GENERIC.key


class TestProviderTable:
    def test_all_providers_shaped(self):
        for p in PROVIDERS.values():
            assert isinstance(p, Provider)
            assert p.key and p.name and p.steps
        # Generic is the only one without a URL.
        assert GENERIC.app_password_url is None
        assert all(
            p.app_password_url for k, p in PROVIDERS.items() if k != "generic"
        )
