---
name: performance-patterns
description: Use when optimizing Apple Mail MCP operations, diagnosing slow queries, adding new filtering logic, or modifying how data is fetched from Mail.app. Covers osascript overhead, whose clause optimization, batch operation patterns, and known operation timings.
---

# Apple Mail MCP Performance Patterns

## The Core Insight

**The bottleneck is per-subprocess overhead.** Each `osascript` call costs 100-300ms regardless of what it does. All performance work reduces the number of subprocess calls.

## Known Operation Timings

| Operation | Time | Notes |
|-----------|------|-------|
| Single `osascript` call overhead | 100-300ms | Minimum cost per subprocess |
| `search_messages` (typical INBOX) | ~1-5s | Depends on mailbox size and filter count |
| `get_message` (single) | <1s | Direct ID lookup |
| `create_draft` (with `send_now=True`) | ~1-2s | Includes Mail.app compose + send |
| `update_message` (bulk read/flag) | ~1-2s | Single script for N messages via `_bulk_repeat_block` |
| `update_message` (move) | ~1-3s | Varies by account type (Gmail slower) |
| `save_attachments` | ~2-5s | Depends on attachment count/size |

## Pattern 1: Use `whose` Clauses for Server-Side Filtering

```applescript
-- GOOD: Server-side filter (fast, Mail.app evaluates internally)
set msgs to (messages of mbox whose sender contains "user@example.com")

-- BAD: Fetch all then filter in Python (slow, transfers all data)
set msgs to every message of mbox
-- then filter in Python loop
```

`whose` clauses let Mail.app filter internally without transferring unmatched messages over IPC. This is 10-50x faster for large mailboxes.

## Pattern 2: Single Script Per Batch Operation

```python
# GOOD: One osascript call for N messages (near-constant time)
script = """
tell application "Mail"
    repeat with msgId in {id1, id2, id3}
        set read status of (first message whose id is msgId) to true
    end repeat
end tell
"""
self._run_applescript(script)

# BAD: N osascript calls for N messages (linear time)
for msg_id in message_ids:
    self._run_applescript(f'tell application "Mail" ...')
```

Batch operations should always build a single AppleScript that handles all items.

## Pattern 3: Use `limit` for Pagination

The `search_messages` tool accepts a `limit` parameter (default: 50). AppleScript uses `items 1 thru N of` for server-side limiting. Always pass a reasonable limit — fetching 10,000 messages when the user wants the latest 10 wastes time.

## Pattern 4: Accept Optional Account/Mailbox Parameters

Message ID lookup is O(accounts x mailboxes) when searching globally. Always accept optional `account` and `mailbox` parameters to narrow the search scope. If the caller knows which account, the search is dramatically faster.

## Anti-Patterns

- **Repeated subprocess calls in loops** — Build one script, execute once
- **Fetching all properties when only some are needed** — Scripts currently fetch a fixed set of fields; when adding a new field, consider whether every caller needs it
- **Not using `whose` clauses** — Manual filtering in Python transfers all data first
- **Default timeout too low for large operations** — Increase from 60s for bulk operations on large mailboxes

## Gmail Performance Notes

Gmail operations are inherently slower than IMAP because:
- Move requires copy + delete (two operations instead of one)
- Label operations don't map cleanly to folder operations
- Search across Gmail labels may scan differently than IMAP folders

**Threading cost scales with folder count (not account size).** IMAP `SEARCH` runs
against one selected mailbox at a time — there is no cross-folder search — so
`get_thread`'s member collection probes each candidate folder in turn. Gmail exposes
every label as an IMAP folder *and* copies each message into every label it carries, so
a thread's members are scattered across many folders. The mitigation is All Mail: enable
Gmail Settings → Labels → "All Mail" → *Show in IMAP*, and `_find_all_mail_folder`
(`\All` SPECIAL-USE, RFC 6154) collapses the probe to that single mailbox holding one
copy of everything. Without it, threading falls back to per-label probing. This is not
Gmail-specific in principle: any IMAP account with dozens of folders pays the same
per-folder cost — non-Gmail accounts are usually fast only because their mail is
concentrated in a handful of folders (INBOX/Sent). See #415 and the `get_thread`
performance callout in `docs/reference/TOOLS.md`.

**Bound the mailbox set on the AppleScript side too — with the unified mailboxes.**
The same "don't visit every mailbox" rule applies to AppleScript lookups, and Mail.app
gives you ready-made bounds: the application-level `inbox`, `sent mailbox`, and
`drafts mailbox` aggregate the corresponding folder across *every* account, so probing
them needs no per-account mailbox iteration and no name matching (which would break on
localized names). `whose id is N` works against them, and `account of (mailbox of msg)`
walks back to the owning account. `_resolve_numeric_anchor_fast` uses this to replace a
`repeat with acc in accounts / repeat with mb in mailboxes of acc` scan: ~1.3s vs ~3.0s
on a 33k-message Gmail account (#419). Keep the full walk as a not-found backstop.

**Don't assume IMAP is the fast side.** Indexed does not mean instant at scale: on that
same account `SEARCH HEADER Message-ID` over a 33k-message All Mail measured ~17s, so
replacing the AppleScript anchor above with an IMAP lookup would have been ~13× *slower*,
not faster. Measure per-phase against a real large account before moving work across the
AppleScript/IMAP boundary — and re-measure, because Gmail's server-side latency swings
by tens of seconds with throttling.

## Profiling

No formal benchmarking infrastructure yet (see issue #31). When added:
- Use 5 iterations per operation
- Calculate mean, stdev, CV%
- Set thresholds at 5x documented baseline
- Detect cold starts (first run > 2x median of remaining)
