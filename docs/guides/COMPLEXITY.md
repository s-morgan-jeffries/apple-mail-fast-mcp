# Cyclomatic Complexity

This project enforces a cyclomatic complexity (CC) ceiling via `./scripts/check_complexity.sh`, run as part of `make check-all` and in CI.

## Threshold

**CC ≤ 20** per function / method. Any function with CC > 20 fails the build.

The ceiling is intentionally generous. The goal is not to chase a low complexity score for its own sake — it's to flag functions whose branching has grown beyond what can be reasoned about while reviewing. A CC of 20 is roughly the upper bound of "I can hold this whole control-flow graph in my head." Beyond that, extract.

Why not CC ≤ 10 or CC ≤ 15? Several MCP tool functions in `server.py` naturally reach CC 11–16 because they chain independent validation gates (safety gate, rate limit, input validation, file existence, elicitation, connector call). Each gate is a single `if X: return error` — simple in isolation but additive in CC. Splitting them would fragment the linear gate-then-act pattern that makes server tools readable.

## Currently complex functions (CC ≥ 11)

The functions below sit above CC 10 intentionally. When touching them, prefer adding one more gate over restructuring. If a change would push any of them above 20, extract a helper first.

> **Known above-threshold functions (v0.7.0):** `create_draft` (CC 37) and `update_draft` (CC 35) currently exceed the documented CC ≤ 20 threshold. They were the unified replacements for the four removed v0.6 send tools (`send_email`, `send_email_with_attachments`, `reply_to_message`, `forward_message`) plus the new save-as-draft semantics, which folded their combined gate chains into one tool each. The connector-side `AppleMailConnector.create_draft` (CC 25) is similarly elevated. These are tracked for refactoring; documented as known exceptions until then.

| File | Function | CC | Why it's complex |
|---|---|---|---|
| [`server.py`](../../src/apple_mail_mcp/server.py) | `create_draft` | 37 | Unified compose / reply / reply_all / forward authoring loop with `send_now` opt-in; subsumes the four removed v0.6 send tools. Each `seed_kind` adds branches; `send_now=True` re-enters the safety + rate-limit gate chain previously in `send_email`. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `update_draft` | 35 | Same gate stack as `create_draft` plus the existing-draft lookup and patch-semantic body/recipient updates. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `AppleMailConnector.create_draft` | 25 | Per-`seed_kind` AppleScript dispatch (compose vs reply/reply_all/forward), template rendering branch, recipient list builders for to/cc/bcc, then save-vs-send tail. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `AppleMailConnector.update_message` | 21 | Patch semantics: each optional field (`read_status`, `flag_color`, `destination_mailbox`, `is_flagged`, `source_mailbox`, ...) adds a branch; mutation-order rules add a few more. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_thread_via_xgm_per_mailbox` | 21 | Tier 1.5 (#125): anchor lookup with INBOX→Sent fallback, THRID FETCH, then per-folder iteration with \\Noselect / select-failure / fetch-failure handling. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_thread_via_imap_thread` | 21 | Tier 2 (#123): per-mailbox SELECT + narrow-search + THREAD + cluster-walk + FETCH, with rejection branches at each step. **Above CC ≤ 20 threshold — refactor candidate.** |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `AppleMailConnector._search_messages_applescript` | 18 | Each optional filter (`sender_contains`, `subject_contains`, `body_contains`, `text_contains`, date range, `read_status`, `is_flagged`, `has_attachment`) generates an AppleScript IF clause. |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `AppleMailConnector.update_mailbox` | 18 | Two delivery paths (rename via AppleScript, move via IMAP) plus the Gmail-system-label refusal pre-flight (#164). |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_bodystructure_has_attachment` | 18 | RFC 3501 BODYSTRUCTURE walk: nested multipart, disposition-vs-name detection, inline-image-with-filename surfacing. |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `update_mailbox` | 17 | Same gate stack as the v0.6 send tools (safety, rate limit, validation), plus the rename-vs-move dispatch and Gmail-system-label error mapping. |
| [`cli.py`](../../src/apple_mail_mcp/cli.py) | `run_setup_imap` | 17 | Each setup failure mode (no Mail.app account, empty password, KeychainAccessDenied, IMAP login error, network error) rolls back the Keychain entry on a distinct branch. |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `_validate_rule_actions` | 16 | One branch per AppleScript rule action that's not modeled in the schema (run-AppleScript, redirect, reply, play sound, ...). |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `AppleMailConnector.update_rule` | 16 | Patch semantics across `enabled`, `name`, `conditions`, `actions`, `match_logic` plus the conditional-elicitation gate. |
| [`security.py`](../../src/apple_mail_mcp/security.py) | `check_test_mode_safety` | 15 | Three distinct safety categories (reply-message block, account-gated operations, send-to-reserved-domain), each with sub-conditions. Splitting would hide the unified "is this safe?" question. |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `delete_mailbox` | 14 | Validation gates plus confirmation elicitation plus exception-to-`error_type` mapping (six exception classes). |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_thread_via_xgm_thrid` | 14 | Tier 1: anchor lookup, THRID FETCH, single-mailbox FETCH, with rejection branches. |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_find_thread_members_bfs` | 14 | Tier 3: nested per-folder × per-known-id × per-header SEARCH loop with select-failure handling. |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `update_message` | 13 | Patch validation across `read_status`, `is_flagged`, `flag_color`, `destination_mailbox`, plus the three-tool-replacement gate stack. |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `update_rule` | 12 | Same patch validation as the connector method plus the conditional elicitation. |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `_build_search_criteria` | 12 | One branch per IMAP SEARCH key derived from the filter set. |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `ImapConnector.search_messages` | 12 | Filter assembly + UID limit slicing + envelope translation, each adding a branch. |
| [`server.py`](../../src/apple_mail_mcp/server.py) | `search_messages` | 11 | Validation across the expanded filter set (#145 added `body_contains` / `text_contains`; #131/#144 reshaped `source`). |
| [`mail_connector.py`](../../src/apple_mail_mcp/mail_connector.py) | `_collect_thread_applescript` | 11 | AppleScript-side BFS fallback when IMAP thread tiers don't apply. |
| [`imap_connector.py`](../../src/apple_mail_mcp/imap_connector.py) | `ImapConnector.get_message` | 11 | `headers_only` vs full-body fetch, search-by-bracketed-msgid path, error mapping. |

Accepted because: each is a sequence of orthogonal gates or optional-parameter branches, not tangled logic. They read top-to-bottom and each branch has a clear exit. The four `# Above threshold` entries are documented exceptions pending refactor — see follow-up issues.

## Adding a new documented exception

If a legitimately complex new function needs to exceed CC 20 (rare), do this in the same PR as the function:

1. Add a row to the table above: file, function, CC, and a one-sentence "why it's complex" that names the specific structural reason.
2. If CC is > 20, update `THRESHOLD` in [`scripts/check_complexity.sh`](../../scripts/check_complexity.sh) — this affects all functions, so prefer extracting a helper instead.
3. Mention the exception in the PR description so reviewers see it.

If you can't write a one-sentence justification, the function probably needs refactoring, not documentation.

## Checking complexity locally

```bash
./scripts/check_complexity.sh        # Gate check (CC > 20 fails)
uv run radon cc src/apple_mail_mcp -n B -s   # See all functions rated B (CC 6+) or worse
uv run radon cc src/apple_mail_mcp -n C -s   # See all functions rated C (CC 11+) or worse
```
