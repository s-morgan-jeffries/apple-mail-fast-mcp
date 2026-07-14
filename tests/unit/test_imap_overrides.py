"""Unit tests for the persisted IMAP login overrides (#341)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apple_mail_fast_mcp import imap_overrides


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the store at a temp APPLE_MAIL_MCP_HOME for every test."""
    monkeypatch.setenv("APPLE_MAIL_MCP_HOME", str(tmp_path))
    return tmp_path


class TestImapOverrides:
    def test_home_env_honored(self, _home: Path) -> None:
        assert imap_overrides._overrides_path() == (
            _home / "imap_login_overrides.json"
        )

    def test_missing_file_returns_none(self) -> None:
        assert imap_overrides.get_login_override("iCloud") is None

    def test_set_get_roundtrip(self, _home: Path) -> None:
        imap_overrides.set_login_override("iCloud", "me@icloud.com")
        assert imap_overrides.get_login_override("iCloud") == "me@icloud.com"
        # Persisted as JSON on disk.
        data = json.loads(
            (_home / "imap_login_overrides.json").read_text()
        )
        assert data == {"iCloud": "me@icloud.com"}

    def test_set_strips_whitespace(self) -> None:
        imap_overrides.set_login_override("iCloud", "  me@icloud.com\n")
        assert imap_overrides.get_login_override("iCloud") == "me@icloud.com"

    def test_set_merges_multiple_accounts(self) -> None:
        imap_overrides.set_login_override("iCloud", "me@icloud.com")
        imap_overrides.set_login_override("Work", "me@work.example")
        assert imap_overrides.get_login_override("iCloud") == "me@icloud.com"
        assert imap_overrides.get_login_override("Work") == "me@work.example"

    def test_delete_removes_entry(self) -> None:
        imap_overrides.set_login_override("iCloud", "me@icloud.com")
        imap_overrides.set_login_override("Work", "me@work.example")
        imap_overrides.delete_login_override("iCloud")
        assert imap_overrides.get_login_override("iCloud") is None
        assert imap_overrides.get_login_override("Work") == "me@work.example"

    def test_delete_last_entry_removes_file(self, _home: Path) -> None:
        imap_overrides.set_login_override("iCloud", "me@icloud.com")
        imap_overrides.delete_login_override("iCloud")
        assert not (_home / "imap_login_overrides.json").exists()

    def test_delete_missing_is_noop(self) -> None:
        imap_overrides.delete_login_override("Nope")  # must not raise

    def test_corrupt_file_returns_none(self, _home: Path) -> None:
        (_home / "imap_login_overrides.json").write_text("{not json")
        assert imap_overrides.get_login_override("iCloud") is None

    def test_non_dict_json_returns_none(self, _home: Path) -> None:
        (_home / "imap_login_overrides.json").write_text("[1, 2, 3]")
        assert imap_overrides.get_login_override("iCloud") is None

    def test_empty_value_treated_as_absent(self, _home: Path) -> None:
        (_home / "imap_login_overrides.json").write_text('{"iCloud": "  "}')
        assert imap_overrides.get_login_override("iCloud") is None


class TestServerOverrides:
    """Per-account IMAP host/port overrides for setup-imap --host/--port
    (#405). Stored in a separate file from the login override."""

    def test_home_env_honored(self, _home: Path) -> None:
        assert imap_overrides._server_overrides_path() == (
            _home / "imap_server_overrides.json"
        )

    def test_missing_file_returns_none(self) -> None:
        assert imap_overrides.get_host_override("Work") is None
        assert imap_overrides.get_port_override("Work") is None

    def test_set_get_roundtrip_host_and_port(self, _home: Path) -> None:
        imap_overrides.set_server_override(
            "Work", host="imap.corp.example", port=993
        )
        assert imap_overrides.get_host_override("Work") == "imap.corp.example"
        assert imap_overrides.get_port_override("Work") == 993
        data = json.loads(
            (_home / "imap_server_overrides.json").read_text()
        )
        assert data == {"Work": {"host": "imap.corp.example", "port": 993}}

    def test_port_only_override(self, _home: Path) -> None:
        imap_overrides.set_server_override("Work", host=None, port=993)
        assert imap_overrides.get_host_override("Work") is None
        assert imap_overrides.get_port_override("Work") == 993
        data = json.loads(
            (_home / "imap_server_overrides.json").read_text()
        )
        assert data == {"Work": {"port": 993}}

    def test_host_only_override(self) -> None:
        imap_overrides.set_server_override(
            "Work", host="imap.corp.example", port=None
        )
        assert imap_overrides.get_host_override("Work") == "imap.corp.example"
        assert imap_overrides.get_port_override("Work") is None

    def test_port_is_int(self) -> None:
        imap_overrides.set_server_override("Work", host=None, port=993)
        assert isinstance(imap_overrides.get_port_override("Work"), int)

    def test_set_strips_host_whitespace(self) -> None:
        imap_overrides.set_server_override(
            "Work", host="  imap.corp.example \n", port=None
        )
        assert imap_overrides.get_host_override("Work") == "imap.corp.example"

    def test_merges_multiple_accounts(self) -> None:
        imap_overrides.set_server_override("Work", host=None, port=993)
        imap_overrides.set_server_override("Zimbra", host="z.example", port=993)
        assert imap_overrides.get_port_override("Work") == 993
        assert imap_overrides.get_host_override("Zimbra") == "z.example"

    def test_delete_removes_entry(self) -> None:
        imap_overrides.set_server_override("Work", host=None, port=993)
        imap_overrides.set_server_override("Keep", host=None, port=143)
        imap_overrides.delete_server_override("Work")
        assert imap_overrides.get_port_override("Work") is None
        assert imap_overrides.get_port_override("Keep") == 143

    def test_delete_last_entry_removes_file(self, _home: Path) -> None:
        imap_overrides.set_server_override("Work", host=None, port=993)
        imap_overrides.delete_server_override("Work")
        assert not (_home / "imap_server_overrides.json").exists()

    def test_delete_missing_is_noop(self) -> None:
        imap_overrides.delete_server_override("Nope")  # must not raise

    def test_corrupt_file_returns_none(self, _home: Path) -> None:
        (_home / "imap_server_overrides.json").write_text("{not json")
        assert imap_overrides.get_host_override("Work") is None
        assert imap_overrides.get_port_override("Work") is None

    def test_set_with_both_none_is_noop(self, _home: Path) -> None:
        # Nothing to store — must not create a stray entry/file.
        imap_overrides.set_server_override("Work", host=None, port=None)
        assert imap_overrides.get_host_override("Work") is None
        assert not (_home / "imap_server_overrides.json").exists()
