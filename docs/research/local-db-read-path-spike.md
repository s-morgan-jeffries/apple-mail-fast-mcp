# Local-DB Fast Read Path — Spike Findings & Recommendation

**Status:** Output of #376 (spike). **Recommendation: GO** — pursue a local-DB read
accelerator behind an opt-in flag. Measured 4,000–7,000× faster than AppleScript and
100–800× faster than IMAP for metadata search on a real 32k-message mailbox; one current
query type (`subject_contains`) *fails* today by exceeding the 60s timeout.
**Related issues:** #376, #331 (origin), #217 (read-only mode — composes), #72/#243/#205
(dispatch & id scheme this must mirror).
**Date:** 2026-06-15

## Question

#331 surfaced a strategic gap: three competitors (imdinu FTS5, che Swift/SQLite, rusty Rust)
get millisecond search on large mailboxes by reading Apple Mail's on-disk store directly;
imdinu publishes benchmarks weaponized against AppleScript servers like ours. #376 asked: is a
local-DB read path (reading `~/Library/Mail/V*/MailData/Envelope Index` + `.emlx`) beneath
`search_messages`/`get_messages` worth building? Spike scope was research, not production
wiring — keep AppleScript + IMAP as fallback; writes stay where they are.

## Method

Throwaway prototype + benchmark (kept in `scripts/`, clearly marked, mirroring the existing
`scripts/spike_imap_*.py` convention):
- `scripts/spike_localdb_envelope.py` — read-only (`mode=ro`) Envelope Index reader producing
  the connector's common row shape, plus an `.emlx` body parser.
- `scripts/spike_localdb_bench.py` — times identical queries through local-DB vs
  `_search_messages_applescript` vs `_imap_search` on the same account/mailbox.

Environment: spike author's machine, **real Gmail INBOX = 32,623 messages** (whole store =
128,469 messages / 176 MB Envelope Index). Medians; local-DB n=3, AppleScript n=1 (slow),
IMAP n=2. Single-machine/single-mailbox — treat magnitudes, not exact ms, as the signal.

## Finding 1 — Speed (the headline)

| query (INBOX, limit 50) | local-DB | AppleScript | IMAP |
|---|---|---|---|
| recent 50, no filter | **0.4 ms** | 9,275 ms | 2,289 ms |
| `sender_contains`, unread | **2.3 ms** | 31,435 ms | 1,812 ms |
| `subject_contains` | **19.7 ms** | **136,993 ms** | 1,858 ms |

- local-DB is **~4,000–7,000× faster than AppleScript**, **~100–800× faster than IMAP**.
- `subject_contains` via AppleScript took **137 s** — past our 60s default timeout, so that
  query **fails today** on a large mailbox. This is exactly the competitor "timeout" critique,
  reproduced on our own path.
- IMAP is steady ~1.8–2.3s (network round-trips) and only helps IMAP-configured accounts;
  local-DB helps *every* account whose mail is on disk, with no network.

## Finding 2 — The id-mapping problem is solved by the DB

The #205/#243 dual-id scheme (`id` = Mail's numeric id, `rfc_message_id` = RFC 5322 header)
maps cleanly onto Envelope Index columns — **no `.emlx` parse needed for metadata**:
- `messages.message_id` → our `id` (Mail's internal numeric id; can be negative 64-bit).
- `message_global_data.message_id_header` → our `rfc_message_id` (verified populated on live
  rows). Join: `message_global_data.message_id = messages.message_id`.
- `messages.subject`/`sender`/`mailbox` are integer FKs → `subjects`, `addresses`, `mailboxes`.
  `date_received` is Unix epoch seconds. `read`/`flagged`/`flag_color`/`deleted` are columns.
- `.emlx` filename stem = `messages.ROWID` (not `message_id`); path is
  `V10/<account-uuid>/<Mailbox>.mbox/<uuid>/Data/<shard>/Messages/<ROWID>.emlx`.

So a `LocalDbConnector` can emit rows byte-compatible with `imap_connector._envelope_to_dict`,
slotting in beside the IMAP path with the same downstream normalization.

## Finding 3 — Body fetch is the one slow spot

`.emlx` parsing itself is trivial (`<byte-count>\n<rfc822>\n<plist>`), but *locating* the file
by walking the account subtree cost ~1.9 s (60k+ files). Metadata is instant; body-by-FS-walk
is not. A production path needs either (a) a derived shard path from `ROWID`, or (b) a
`ROWID → path` index built once and watched. **Don't ship body fetch via `rglob`.**

## Finding 4 — Writes & sync freshness (coherence model)

The Envelope Index is in **WAL mode** (`-wal`/`-shm` present); Mail.app is its **sole writer**.
Implications for a read-only accelerator:

- **Writes are unchanged & safe.** We only read (`mode=ro`); we never write the local DB, so no
  dual-write/corruption hazard. All mutations stay on AppleScript/IMAP.
- **Read-after-write coherence.** AppleScript writes go *through* Mail.app, which updates the
  Envelope Index as part of the op → a later local-DB read sees it once the WAL txn commits
  (near-immediate; exact lag unmeasured — a safe bench-mailbox measurement is a follow-up).
  **Our IMAP fast-path writes bypass Mail.app**, so the Envelope Index — *and the current
  AppleScript read path* — won't reflect them until Mail.app re-syncs. This wrinkle already
  exists for AppleScript today; local-DB inherits it, doesn't worsen it.
- **Freshness == the AppleScript path.** The local store is only as fresh as Mail.app's last
  sync (seconds with Mail.app running + IMAP IDLE/push; stale if Mail.app is closed). This is
  *identical* to the AppleScript path's freshness — both read Mail.app's local store. Only the
  **IMAP path is server-authoritative.** → Dispatch rule: local-DB may front the **AppleScript**
  path (strict win: same freshness, ~5,000× faster) but must **not** front the **IMAP** path
  when an account needs server-fresh reads.
- **WAL read gotcha.** Open `mode=ro` (reads the `-wal`); do **not** use `immutable=1` — it
  skips the WAL and yields stale reads.

## Answers to the issue's open questions

- **Full Disk Access tradeoff.** Real: today we need only Automation; this adds FDA (the spike
  was blocked until granted). FDA to the host app is broad. → **Gate behind an explicit opt-in
  flag** (e.g. `--local-db` / env), default off; degrade to AppleScript/IMAP when unavailable.
  Composes with `--read-only` (#217) for a "fast, read-only" deployment posture.
- **Cache/invalidation.** Envelope Index is Mail's own live DB — no metadata cache needed; open
  `mode=ro` per query (cheap: 0.4 ms) and you read Mail's current local state (freshness caveats
  in Finding 4). A `ROWID→path` cache for bodies needs invalidation (FSEvents watcher or TTL).
  EWS/Exchange accounts may have no `.emlx` (per che) → fall back.
- **Schema-stability risk.** We read `V10` + a handful of columns (`messages`, `subjects`,
  `addresses`, `mailboxes`, `message_global_data`). Apple bumps `V<n>` across major macOS
  releases and can rename columns. → Version-detect the `V*` dir, feature-probe columns at
  startup, and **fall back to AppleScript on any schema surprise** rather than failing.
- **Security.** Read-only (`mode=ro`), local, metadata-first — low risk, but it's a new trust
  surface (direct disk read of all mail incl. other accounts). Document it; keep behind the
  opt-in; never write to Mail's DB.
- **Parity.** Result *counts* matched the limit across paths; a real implementation must
  prove row-level parity (same messages, same flags) against AppleScript/IMAP in tests before
  it's allowed to front either.

## Recommendation — GO (phased), behind a flag

The speed delta is too large to ignore and directly answers imdinu's public benchmark framing.
Proceed, but scoped and safe:

1. **`LocalDbConnector` (metadata search first)** — Envelope Index reads only, emitting the
   common row shape; wire as a *first-attempt accelerator* under `search_messages` (and
   `get_message` metadata), with AppleScript/IMAP fallback unchanged. Opt-in flag, default off.
2. **Body/`get_message` content** — add `.emlx` reading with a real `ROWID→path` strategy (not
   `rglob`); only after #1 proves parity.
3. **Defer/optional:** an FTS5 body index for full-coverage body search (imdinu's headline) —
   biggest payoff, biggest build; its own issue once #1–#2 land.

Hard constraints: opt-in flag + FDA gating; startup schema/version probe with AppleScript
fallback; row-level parity tests before fronting either existing path; preserve our defended
advantages (IMAP fast path, security/test rigor). Writes stay on AppleScript/IMAP.

Suggested follow-ups to file on a GO: (a) implement `LocalDbConnector` metadata search behind
a flag; (b) `.emlx` body fetch with path index; (c) optional FTS5 body-search index.

## Provenance

- Prototype/bench: `scripts/spike_localdb_envelope.py`, `scripts/spike_localdb_bench.py`
  (this branch). Reproduce: `MAIL_TEST_MODE=true uv run python scripts/spike_localdb_bench.py`
  (needs Full Disk Access + a large local mailbox).
- Store read: `~/Library/Mail/V10/MailData/Envelope Index`, 128,469 messages, on 2026-06-15.
- Dispatch/id refs: `mail_connector.py` `search_messages` (1756), `_search_messages_applescript`
  (1884), `_imap_search` (1707), `get_message` (2090); `imap_connector._envelope_to_dict` (617).
