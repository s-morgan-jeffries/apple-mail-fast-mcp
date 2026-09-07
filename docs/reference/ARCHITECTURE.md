# Architecture

## Component diagram

```
MCP client
        |  (MCP JSON-RPC over stdio)
        v
server.py (FastMCP)
  |-- tools (@_tool / @mcp.tool; see TOOLS.md for the current surface)
  |-- input validation + sanitization
  |-- elicitation (confirmation) gates on destructive ops
  |-- structured responses ({"success": bool, ...})
        |
        v
mail_connector.py (AppleMailConnector) — dispatch + domain logic
        |                                   \
        | AppleScript path (baseline)        | IMAP fast path (when hinted + creds)
        v                                     v
  subprocess.run(["osascript", "-"])    imap_connector.py (ImapConnector / pool)
        |                                     |
        v                                     v
  Apple Mail.app (macOS Automation)     the account's IMAP server
```

## Dispatch model (the central v0.8.0 abstraction)

**AppleScript is the baseline for many operations**, using `osascript` against Mail.app.
Some operations, including mailbox deletion and re-parenting, require IMAP. Several read and
bulk-mutation operations take an **IMAP fast path** when two conditions hold:

1. the caller hints the location — an `account` (and, where relevant, a `source_mailbox` / `mailbox`), and
2. the account has Keychain IMAP credentials (opt-in via `apple-mail-fast-mcp setup-imap`).

When both hold, the connector issues server-side IMAP (e.g. `SEARCH`, `UID MOVE`, `STORE`) instead of
driving Mail.app's per-message AppleScript loop. **Where an AppleScript fallback exists**, eligible
IMAP failures can switch to that path. Fallback may be slower or less complete; callers must
preserve incomplete-result indicators and distinguish an indeterminate lookup from a definitive
not-found result. Eligible failures are handled by the
`_IMAP_FALLBACK_EXCS` set and a **per-account circuit breaker** (`_imap_breaker_*`, ~30 s cooldown,
#118) so a flaky account doesn't pay the connect/login cost on every call.

IMAP connections are created per call by default; an opt-in **connection pool** (`APPLE_MAIL_MCP_IMAP_POOL=1`,
#75) amortizes the ~400 ms TCP+TLS+LOGIN across calls.

Fast paths shipped in v0.8.0: search (#32-era), `get_messages` / `get_attachments` / `get_thread`
reads, and the bulk mutations — move (#149), delete (#150), read-status (#151), flag (#152) — each
with an AppleScript fallback.

Compose/save (`create_draft`) can use IMAP APPEND of MIME built by `draft_builder.py`;
`send_now=true` can use `smtp_sender.py`. These paths avoid Mail.app's quoted-body
formatting behavior and depend on credentials plus account/seed information. When
unavailable, eligible calls fall back to AppleScript. See `create_draft` in the connector.

## Dual-emit message-ID model (#148)

A message row's `id` is **path-native**: Mail.app's internal numeric id on the AppleScript path, the
RFC 5322 `Message-ID` (bracketless) on the IMAP path. To let callers cross paths without caring which
produced a row, read tools also emit `rfc_message_id` (always the RFC id, or null). The mutation
fast-paths and `create_draft(reply_to=/forward_of=)` accept **either** form — pass back the `id` a
read tool gave you verbatim.

## Drafts lifecycle (#134)

Mail.app's real primitive is the draft — every outgoing message is a draft until sent. Three tools
model the lifecycle:

- `create_draft` — new / reply (`reply_to`) / forward (`forward_of`); can save via IMAP APPEND.
  `send_now=true` sends instead of saving, using SMTP when available or AppleScript fallback.
- `update_draft` — **delete-and-recreate** (Mail.app forbids mutating a saved draft in place); reply/forward threading headers are preserved by re-seeding from the original.
- `delete_draft` — move a draft to Trash.

## IMAP thread tiers (`get_thread`)

`find_thread_members` picks the cheapest correct strategy per provider (see
[../research/imap-thread-strategies.md](../research/imap-thread-strategies.md)):

| Tier | Strategy | When | Cost |
|------|----------|------|------|
| 1 | Gmail `X-GM-THRID` via `[Gmail]/All Mail` | Gmail, All Mail exposed over IMAP | ~4 round-trips, mailbox-count-independent |
| 1.5 | per-mailbox `X-GM-THRID` iteration | Gmail, All Mail hidden | ~6× faster than BFS, but ∝ label count |
| 2 | RFC 5256 `THREAD REFERENCES` per mailbox | server advertises THREAD (e.g. Fastmail) | per-mailbox THREAD × M |
| 3 | per-mailbox header-search BFS | universal (e.g. iCloud — no THREAD/X-GM) | M × N × 3 `SEARCH HEADER` round-trips |

If IMAP isn't configured/reachable, `get_thread` reconstructs the thread via AppleScript (subject
prefilter + `In-Reply-To`/`References` header walk).

### Anchor resolution

The tiers above cover **member collection**, which is shared by both `message_id` forms. Resolving
the *anchor* first is what differs, and it is bounded in both cases (#415, #419):

| id form | Strategy | Cost |
|---------|----------|------|
| RFC Message-ID | `ImapConnector.resolve_anchor` — indexed `SEARCH HEADER Message-ID` over Gmail All Mail, else INBOX + Sent | one bounded IMAP probe; no AppleScript |
| numeric | `_resolve_numeric_anchor_fast` — `whose id is N` against Mail's unified `inbox`, then `sent mailbox` | 2 indexed lookups, account-count-independent |
| numeric (not in either) | `_resolve_thread_anchor_applescript` — every mailbox of every account | correctness backstop; ~2× the probe on a 33k Gmail account |

Both numeric paths emit the same anchor record (`_anchor_record_applescript` /
`_anchor_from_applescript_record` are shared), so the choice between them is purely a cost decision.
The unified mailboxes are used because they aggregate across accounts and are locale-independent —
the same reason `drafts mailbox` is used for draft lookups (#407). Note that the numeric anchor
deliberately stays in AppleScript: routing it through `resolve_anchor` instead measured ~17s on a
33k-message Gmail account, since `SEARCH HEADER` over a 33k All Mail is far from instant.

## Module responsibilities

| Module | Role |
|--------|------|
| `server.py` | MCP tool registration, validation, elicitation gates, response formatting |
| `mail_connector.py` | AppleScript generation/execution + IMAP-fast-path dispatch |
| `imap_connector.py` | IMAP client, connection pool, search/fetch/bulk-mutation fast paths |
| `draft_builder.py` / `smtp_sender.py` | MIME construction and clean SMTP sending |
| `security.py` | Input sanitization, rate limiting, audit logging, confirmation flows |
| `utils.py` | Pure functions: escaping, parsing, validation |
| `drafts.py` / `templates.py` | Draft-seed state and email-template storage under `~/.apple_mail_mcp/` |
| `exceptions.py` | Typed exception hierarchy |

## Design decisions

- **Thin server, thick connector.** Business logic never lives in `server.py`; it stays in the connector.
- **Single AppleScript execution point.** All AppleScript runs through `_run_applescript()` — the unit-test mock boundary and the one place timeout/error-routing lives (stderr → typed exceptions).
- **JSON output via ASObjC.** AppleScript emits JSON through `NSJSONSerialization` (`_wrap_as_json_script` / `parse_applescript_json`), not fragile pipe-delimited text. See [APPLESCRIPT_GOTCHAS.md](APPLESCRIPT_GOTCHAS.md).
- **Structured responses.** Every tool returns `{"success": bool, ...}`; errors carry `error` + `error_type`. No exception reaches the LLM.
- **Confirmation by elicitation.** Destructive tools (`delete_*`, `create_rule` with move/forward/delete actions, `create_draft` with `send_now`) gate behind MCP elicitation, fail-closed.
- **Gmail label mode.** `gmail_mode` uses copy+delete instead of move for Gmail's label-based system.
