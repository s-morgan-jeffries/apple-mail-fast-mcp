"""Unit tests for the DraftStateStore module."""

from pathlib import Path

import pytest

from apple_mail_mcp.exceptions import MailDraftInvalidIdError


class TestValidateDraftId:
    def test_accepts_numeric_id(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # Mail.app internal ids are numeric strings in practice.
        _validate_draft_id("160991")

    def test_accepts_alphanumeric_with_dashes_and_underscores(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        _validate_draft_id("abc_123-xyz")

    def test_accepts_bare_rfc_message_id(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # IMAP-APPEND drafts (#245) return the RFC 5322 Message-ID as the
        # draft_id; the bare (bracket-stripped) form must validate.
        _validate_draft_id("178031450722.27521.4532321693417753548@frederics-mbp.lan")

    def test_accepts_message_id_with_plus_and_equals(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # atext allows + and = ; real-world Message-IDs use them.
        _validate_draft_id("a+b=c.123@mail.example.com")

    def test_rejects_path_traversal(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("../etc/passwd")

    def test_rejects_slashes(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("foo/bar")

    def test_rejects_empty_string(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("")

    def test_rejects_trailing_newline(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # #325: `$` + re.match let a trailing newline slip past an
        # otherwise-valid id; fullmatch rejects it.
        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("160991\n")

    def test_rejects_embedded_newline(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("160\n991")

    def test_rejects_double_dot(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # #325: `.` is in the charset, so `..` matches the regex; it's a
        # path-traversal sequence and must be rejected explicitly.
        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("..")
        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("a..b@host")

    def test_rejects_non_string(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id(160991)  # type: ignore[arg-type]

    def test_rejects_overlong(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("a" * 256)

    def test_rejects_backslash(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # No path separators, even after widening for Message-IDs.
        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("foo\\bar")

    def test_rejects_angle_brackets(self):
        from apple_mail_mcp.drafts import _validate_draft_id

        # draft_id is the BARE Message-ID; the bracketed form is normalized
        # away at the boundary and must not validate here.
        with pytest.raises(MailDraftInvalidIdError):
            _validate_draft_id("<abc@host>")


class TestDefaultRoot:
    def test_uses_home_default_when_no_override(self, monkeypatch):
        from apple_mail_mcp.drafts import default_root

        monkeypatch.delenv("APPLE_MAIL_MCP_HOME", raising=False)
        assert default_root() == Path.home() / ".apple_mail_mcp" / "drafts"

    def test_honors_apple_mail_mcp_home_env(self, monkeypatch, tmp_path):
        from apple_mail_mcp.drafts import default_root

        monkeypatch.setenv("APPLE_MAIL_MCP_HOME", str(tmp_path))
        assert default_root() == tmp_path / "drafts"

    def test_resolves_at_call_time_not_import_time(self, monkeypatch, tmp_path):
        from apple_mail_mcp.drafts import default_root

        monkeypatch.setenv("APPLE_MAIL_MCP_HOME", str(tmp_path / "first"))
        first = default_root()
        monkeypatch.setenv("APPLE_MAIL_MCP_HOME", str(tmp_path / "second"))
        second = default_root()
        assert first != second


class TestDraftStateStore:
    def test_get_seed_returns_none_when_no_state(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        assert store.get_seed("160991") is None

    def test_set_then_get_reply_seed(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        store.set_seed(
            "160991",
            SeedRecord(seed_kind="reply", seed_id="999888", reply_all=True),
        )
        seed = store.get_seed("160991")
        assert seed is not None
        assert seed.seed_kind == "reply"
        assert seed.seed_id == "999888"
        assert seed.reply_all is True

    def test_set_then_get_forward_seed(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        store.set_seed(
            "160991",
            SeedRecord(seed_kind="forward", seed_id="999888"),
        )
        seed = store.get_seed("160991")
        assert seed is not None
        assert seed.seed_kind == "forward"
        assert seed.seed_id == "999888"
        assert seed.reply_all is False

    def test_set_creates_root_directory_if_missing(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        nested = tmp_path / "nested" / "drafts"
        assert not nested.exists()
        store = DraftStateStore(root=nested)
        store.set_seed(
            "160991", SeedRecord(seed_kind="reply", seed_id="999888")
        )
        assert nested.is_dir()

    def test_set_overwrites_existing_entry(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        store.set_seed(
            "160991", SeedRecord(seed_kind="reply", seed_id="aaa")
        )
        store.set_seed(
            "160991", SeedRecord(seed_kind="forward", seed_id="bbb")
        )
        seed = store.get_seed("160991")
        assert seed is not None
        assert seed.seed_kind == "forward"
        assert seed.seed_id == "bbb"

    def test_delete_removes_state(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        store.set_seed(
            "160991", SeedRecord(seed_kind="reply", seed_id="999888")
        )
        store.delete("160991")
        assert store.get_seed("160991") is None

    def test_delete_is_idempotent(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        # No exception when nothing to delete.
        store.delete("160991")

    def test_get_with_invalid_id_raises(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        with pytest.raises(MailDraftInvalidIdError):
            store.get_seed("../escape")

    def test_set_with_invalid_id_raises(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        with pytest.raises(MailDraftInvalidIdError):
            store.set_seed(
                "../escape", SeedRecord(seed_kind="reply", seed_id="x")
            )

    def test_delete_with_invalid_id_raises(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        with pytest.raises(MailDraftInvalidIdError):
            store.delete("../escape")

    def test_get_handles_corrupt_json_gracefully(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "160991.json").write_text("{not valid json")
        # Corrupt state should be treated as "no state" rather than crashing
        # an update_draft call.
        assert store.get_seed("160991") is None

    def test_get_handles_missing_seed_kind_key(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "160991.json").write_text('{"seed_id": "999"}')
        assert store.get_seed("160991") is None

    def test_get_handles_invalid_seed_kind(self, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        store = DraftStateStore(root=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        # "new" is not a persisted seed kind — fresh drafts get no file.
        (tmp_path / "160991.json").write_text(
            '{"seed_kind": "new", "seed_id": "x"}'
        )
        assert store.get_seed("160991") is None

    def test_default_constructor_uses_default_root(self, monkeypatch, tmp_path):
        from apple_mail_mcp.drafts import DraftStateStore

        monkeypatch.setenv("APPLE_MAIL_MCP_HOME", str(tmp_path))
        store = DraftStateStore()
        assert store.root == tmp_path / "drafts"

    def test_forward_seed_does_not_persist_reply_all(self, tmp_path):
        """Forward seeds shouldn't carry reply_all (it's reply-only)."""
        import json

        from apple_mail_mcp.drafts import DraftStateStore, SeedRecord

        store = DraftStateStore(root=tmp_path)
        store.set_seed(
            "160991",
            SeedRecord(seed_kind="forward", seed_id="999888", reply_all=True),
        )
        # The on-disk JSON shouldn't have reply_all for forward seeds.
        data = json.loads((tmp_path / "160991.json").read_text())
        assert "reply_all" not in data


class TestExtractDraftAttachmentsPathTraversal:
    """extract_draft_attachments must not let an attachment filename (which
    can originate from a forwarded message's attacker-set MIME filename)
    escape dest_dir. ``.resolve()`` collapses ``..`` deterministically, so an
    unsanitized name would write attacker bytes to an arbitrary path."""

    def test_traversal_name_contained(self, tmp_path: Path) -> None:
        from apple_mail_mcp.mail_connector import _compute_draft_extract_targets

        targets = _compute_draft_extract_targets(
            ["../../../../tmp/evil.sh", "report.pdf"], tmp_path
        )
        for p in targets:
            assert p.resolve().is_relative_to(tmp_path.resolve())
        # Reduced to a safe basename, kept under its index subdir.
        assert targets[0].name == "evil.sh"
        assert len(targets) == 2

    def test_absolute_name_contained(self, tmp_path: Path) -> None:
        from apple_mail_mcp.mail_connector import _compute_draft_extract_targets

        targets = _compute_draft_extract_targets(["/etc/passwd"], tmp_path)
        assert targets[0].resolve().is_relative_to(tmp_path.resolve())
        assert targets[0].name == "passwd"

    def test_extract_script_targets_sanitized_path(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from apple_mail_mcp.mail_connector import AppleMailConnector

        conn = AppleMailConnector(timeout=30)
        with patch.object(AppleMailConnector, "_run_applescript") as mock_run:
            mock_run.return_value = "0"
            conn.extract_draft_attachments(
                "160991", ["../../../../tmp/evil.sh"], tmp_path
            )
            script = mock_run.call_args[0][0]

        # The AppleScript saves to the sanitized path under dest_dir/0/,
        # never the resolved-out-of-tree path the raw name would produce.
        expected = str((tmp_path / "0" / "evil.sh").resolve())
        assert expected in script
