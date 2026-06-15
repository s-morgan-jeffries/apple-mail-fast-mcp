# Competitor Feature-Gap Analysis — Research Findings

**Status:** Output of #331. Recommendation: pursue **one strategic gap** (a local-DB fast
read path for large-mailbox search) plus **2–3 thin-add convenience tools** (smart-inbox,
statistics); decline send-merge/contacts/VIP scope creep; most "gaps" the field has over us
are already covered by `create_draft` consolidation, `--read-only` (#217), or are tracked in
#332/#333.
**Related issues:** #331, #332 (distribution), #333 (self-documenting), #335 (rename), #251
(rich HTML drafts), #217 (read-only mode). Follow-ups filed: #376, #377, #378.
**Date:** 2026-06-14

## Background & methodology

We renamed off `apple-mail-mcp` partly because of a name collision with
patrickfreyer/apple-mail-mcp (#335). #331 is the research step: survey the Apple Mail MCP
landscape, find where others lead, and decide *per item* whether each gap fits our direction
(security-first, IMAP fast path, tested rigor) and is worth adopting.

**How repos were found/ranked.** GitHub repo search across several framings (`apple mail mcp`,
`mcp-apple-mail`, `applescript mail mcp`, `macos mail mcp`, `mail.app mcp`) on 2026-06-14,
ranked by stars + recent push activity. "Live tool surface" means each competitor's tool list
was read from their **actual current source** (registered tool decorators/`Tool(...)`
registrations), not from their README's marketing count — several misstate their own counts.
Each deep dive records the repo URL + the commit SHA/date it was read at (see Provenance).

**Our 24-tool baseline** (from `docs/reference/TOOLS.md`, verified in
`src/apple_mail_mcp/server.py`): `list_accounts, list_mailboxes, list_rules, list_templates,
search_messages, get_messages, get_thread, get_template, render_template, update_message,
update_mailbox, update_rule, update_draft, delete_draft, delete_mailbox, delete_messages,
delete_rule, delete_template, create_mailbox, create_draft, create_rule, save_template,
save_attachments, get_attachment_content`. No prior competitive notes existed in the repo —
this is the first such analysis.

## The landscape

Apple-Mail-focused MCP servers, ranked by stars (2026-06-14). "Tools" is the **code-verified**
count where deep-dived (✦), else the advertised number.

| Repo | ★ | Stack / backend | Tools | R/W | Niche |
|---|---|---|---|---|---|
| **patrickfreyer/apple-mail-mcp** ✦ | 145 | Python · AppleScript | 24✦ | RW | Smart-inbox, analytics, dashboard, best onboarding |
| **s-morgan-jeffries/apple-mail-fast-mcp (us)** | 87 | Python · AppleScript + **IMAP fast path** | 24 | RW | Security rigor, rules/templates, IMAP moves, tests |
| **imdinu/apple-mail-mcp** ✦ | 37 | Python · **local SQLite FTS5 + .emlx** | 8✦ | RO | Full-coverage body search; public benchmarks |
| **sweetrb/apple-mail-mcp** ✦ | 36 | TS/Node · AppleScript | 40✦ | RW | Mail-merge serial send, contacts, granular verbs |
| **PsychQuant/che-apple-mail-mcp** ✦ | 5 | Swift · **SQLite/.emlx read** + AppleScript write | 48✦ | RW | Breadth (VIP/signatures/SMTP), batch, MD export |
| **like-a-freedom/rusty_apple_mail_mcp** ✦ | 5 | Rust · **Envelope Index + .emlx**, read-only | 5✦ | RO | "Dead fast"; rich multi-format attachment extraction |
| GodModeAI2025/AppleMCP | 11 | multi-app suite (Mail+Calendar+…) | — | — | Not Mail-dedicated (landscape only) |
| l22-io/orchard-mcp | 6 | multi-app (Mail+Calendar+Reminders) | — | — | Not Mail-dedicated (landscape only) |

Long tail: ~20 more repos at 0–1★ (forks, language ports — Go `maximbilan`, Haskell
`titouancreach`, Ruby `vlasikhin`, read-only `BastianZim`). The two multi-app suites are noted
for completeness but not deep-dived — they're not Mail-specialists. Deep dives below cover
patrickfreyer + the next four Mail-dedicated repos by stars/notability.

## Per-competitor deep dives

### patrickfreyer/apple-mail-mcp — 145★ · commit `6ed3746f0` (2026-06-13) · MIT
Python/FastMCP, **pure AppleScript** (same backend as us, no IMAP/DB). 24 code-registered tools
(README says 22; omits `list_account_addresses`, `synchronize_account`). PyPI `mcp-apple-mail`.
- **Leads on:** smart-inbox triage (`get_awaiting_reply`, `get_needs_response`,
  `get_top_senders`), analytics (`get_statistics`), `export_emails` (TXT/HTML), `inbox_dashboard`
  (mcp-ui) + `get_inbox_overview`, `create_rich_email_draft` (multipart `.eml`),
  `USER_EMAIL_PREFERENCES` context env var, and **onboarding** (marketplace plugin + uvx +
  `.mcpb` + companion skill + `/email-management` slash command).
- **Security:** single-layer `escape_applescript()` (no separate sanitize pass), conservative
  batch caps, dry-run defaults on trash/move, a thin `--read-only`. No audit log, no
  path-traversal name validation, no test-mode gate, ~7 test files.

### imdinu/apple-mail-mcp — 37★ · commit `463e22565` (2026-06-12) · GPL-3.0
Python, **read-only**, 3-layer disk-first: `.emlx` reads (~3ms), **SQLite FTS5 index** of the
whole mailbox (BM25, ~2ms), JXA fallback. Reads Apple's Envelope Index directly. 8 tools.
- **Leads on:** the headline **full-coverage body search** ("only server with it"; competitors
  "timeout" or "live-scan only the 5000 most recent — silent miss on anything older"). Ships a
  **public benchmark suite** (`docs/benchmarks.md`) run against 6 servers on a 73K-message
  mailbox — explicitly weaponized against AppleScript-based servers *like ours*. Also: standalone
  CLI, `--watch` live re-index, `index://status` MCP resource, `get_email_links`.
- **Security:** read-only by design; FTS5 query sanitization, clamped limits, `0o600` files,
  path-traversal guard. No write tools shipped (compose/move/delete are roadmap #22/#23/#24).

### sweetrb/apple-mail-mcp — 36★ · commit `c57c66647` (2026-06-01) · MIT
TypeScript/Node, **AppleScript only**, full read-write, 40 granular tools.
- **Leads on:** **`send-serial-email`** (mail-merge: `{{placeholder}}` per-recipient send,
  throttled, ≤100), `search-contacts` (Contacts.app), diagnostics (`health-check`,
  `get-mail-stats` 24h/7d/30d, `get-sync-status`), explicit batch flag/read variants.
- **Solid security:** numeric-only id schema, AppleScript+shell escaping, path-traversal
  allowlist on save, injection tests (`security.test.ts`). **No enforced confirmation gate**
  (review-before-send is advisory), no audit log, no test-mode gate. Templates are **in-memory
  only** (lost on restart). HTML *read* but not HTML *send*.

### PsychQuant/che-apple-mail-mcp — 5★ · commit `a703fd073` (2026-06-14) · MIT
Swift native, hybrid: **SQLite/Envelope-Index + .emlx reads** with AppleScript writes; 48
code-registered tools (README inconsistently says 47/48; detail table undercounts). Needs both
Automation **and** Full Disk Access. `.mcpb` bundle + MCP registry.
- **Leads on:** breadth — `get_email_headers/_source/_metadata`, `list_vip_senders`,
  `list_signatures`/`get_signature`, `list_smtp_servers`, `set_flag_color`/`set_background_color`,
  `mark_as_junk`/`copy_email`/`redirect_email`, `get_emails_batch`/`list_attachments_batch`,
  `export_emails_markdown`, sync tools, account-UUID disambiguation.
- **Security:** real `SECURITY.md` threat model, Int-id validation on 17 tools, attachment
  path deny-list + symlink canonicalization, header-injection defense. No audit log, no
  rate limiting, no confirmation/test-mode gate. The 48 count is breadth of thin wrappers, not
  advanced workflows (no smart-inbox/analytics/threading/templates).

### like-a-freedom/rusty_apple_mail_mcp — 5★ · commit `647054185` (2026-05-30) · no license
Rust, **local-first read-only** (Envelope Index via `rusqlite` + `.emlx` lazy hydration), no
AppleScript/network at all. 5 tools (1 deprecated). aarch64-only prebuilt binary.
- **Leads on:** speed-by-construction, **rich multi-format attachment text extraction**
  (PDF/DOCX/XLSX/PPTX/HTML/CSV/JSON/XML + nested rfc822), dual MCP+CLI binary, `participant`
  (To/CC) search, type-level read-only guarantee.
- **Security:** read-only by construction eliminates the AppleScript-injection class entirely;
  `deny_unknown_fields` schemas; 332 tests. Caveats: 5★, no license, no Intel build.

## Feature-gap matrix

Aggregated across all five. "Have it?" = us. Sourced to the deep dives above.

| Capability | Who has it | Us? | Verdict |
|---|---|---|---|
| Compose **send / reply / forward / HTML** | patrickfreyer, sweetrb, che | **Yes** — consolidated in `create_draft` (`reply_to`, `forward_of`, `reply_all`, `body_html`, `send_now`) | **Not a gap** (discoverability — #333) |
| **Read-only deployment mode** | patrickfreyer, imdinu, rusty | **Yes** — `--read-only` (#217) | **Not a gap** |
| Rich HTML draft (`.eml`) | patrickfreyer | Partial — `body_html` w/ IMAP; rich `.eml` overlaps **#251** | Fold into #251 |
| Flag color | che | **Yes** — `update_message.flag_color` | Not a gap |
| **Local-DB fast read path** (Envelope Index / .emlx / FTS5) | imdinu, che, rusty | **No** (AppleScript `whose` + IMAP fast path) | **GAP — strategic** |
| Smart-inbox: awaiting-reply, top-senders | patrickfreyer | No | **GAP — thin add** |
| Statistics / analytics | patrickfreyer, sweetrb, che | No | **GAP — thin add** |
| Inbox overview / unread-count tool | patrickfreyer, sweetrb, che | Partial — `list_mailboxes.unread_count` | thin add / recipe |
| Link extraction | imdinu | No | thin add (niche) |
| Multi-format attachment **text extraction** | rusty | Partial — `get_attachment_content` inline read | low priority |
| Raw headers / source / metadata | che | No | thin add (niche) |
| Sync tools (`check_for_new_mail`) | patrickfreyer, che, sweetrb | No | thin add (niche) |
| Mail-merge / serial send | sweetrb | No | **Decline** (vs philosophy) |
| Contacts.app lookup | sweetrb | No | **Decline** (scope creep) |
| VIP / signatures / SMTP introspection | che | No | **Decline** (niche) |
| Export to TXT/HTML/MD (as a tool) | patrickfreyer, che | No — `get_messages` returns content | Decline-as-tool / recipe |
| Onboarding (PyPI/uvx/.mcpb/marketplace/skill) | patrickfreyer, sweetrb, che, imdinu | Narrower | **Out of scope** (#332/#333) |

**Our defended advantages — do not regress when adopting anything:**
- **IMAP fast path** — unique hybrid; everyone else is pure-AppleScript *or* read-only local-DB.
- **`get_thread` threading** — *none* of the five has a thread tool.
- **Full rules CRUD incl. `update_rule`** — others have at most enable/disable (sweetrb, che).
- **Persistent on-disk templates + `render_template`** — sweetrb's are in-memory; others have none.
- **Mailbox lifecycle** (`update_mailbox` rename/IMAP-move, `delete_mailbox`) and **draft
  lifecycle** (`update_draft`/`delete_draft`) — most have create-only.
- **`get_attachment_content` inline read** — most are save-to-disk only.
- **Security depth** — double sanitization, path-traversal name validation, audit logging,
  confirmation gates, `MAIL_TEST_MODE` safety gate, 1396/29/62 tests. Strongest in the field;
  no competitor has an audit log, rate limiting, *and* a test-mode/reserved-domain gate.

## Thin-add analysis

Most read-side "gaps" compose over primitives we already have — they're aggregations, not new
backends. Foundations: `search_messages` (filters `sender_contains`, `read_status`,
`date_from/to`, `received_within_hours`, `is_flagged`, `body_contains`, `source=[ids]`;
`server.py:952`), `list_mailboxes` (`unread_count` per folder; `server.py:704`), `get_thread`
(metadata rows, tiered IMAP; `server.py:1495`).

- **Smart-inbox** — `get_awaiting_reply` = sent messages whose `get_thread` has no later inbound
  reply; `get_top_senders` = aggregate `search_messages` rows by sender. Pure post-processing.
  (`get_needs_response` is fuzzier/heuristic — lower confidence, ship cautiously or omit.)
- **Statistics** — counts/ratios over `search_messages` + `list_mailboxes`. Pure calculation.
- **Inbox overview / unread counts** — `list_mailboxes` already returns `unread_count`; an
  overview is a convenience roll-up.
- **NOT thin adds:** the **local-DB fast read path** is a real architecture project (new reader
  over Apple's Envelope Index/`.emlx`, cache, invalidation) — it's the one item that can't be
  faked over existing tools. Multi-format attachment *text* extraction adds heavy deps
  (PDF/Office parsers).

## Per-item recommendations

Scored against the issue's three questions — (1) fits security-first + IMAP-fast-path
philosophy? (2) own long-term or scope creep? (3) thin add over primitives?

| Item | Fit | Own it? | Thin? | Verdict |
|---|---|---|---|---|
| **Local-DB fast read path** | Yes — *is* a faster path; read-only ⇒ low risk | Core differentiator | No (architecture) | **ADOPT — research/spike issue.** Highest strategic value; directly answers imdinu's public benchmarks. |
| **Smart-inbox** (`get_awaiting_reply`, `get_top_senders`) | Yes | Yes | Yes (over `get_thread`/search) | **ADOPT — one thin-add issue.** Omit/flag `needs_response` as heuristic. |
| **`get_statistics`** | Yes | Yes | Yes | **ADOPT — small thin-add issue** (can fold with smart-inbox). |
| Inbox overview / unread-count tool | Yes | Marginal | Yes | **Thin-add recipe / low priority** — document over `list_mailboxes`; build only on demand. |
| Link extraction, raw headers/source, sync, multi-format extraction | Mostly | Niche | Mixed | **Backlog / low priority** — note in doc, don't file now. |
| Rich HTML `.eml` draft | Yes | Yes | — | **Fold into #251** (no new issue). |
| Send/reply/forward discoverability | — | — | — | **Tie to #333** — surface that `create_draft` already does this. |
| Mail-merge / serial send | **Fights** draft-first human-review posture | Risky | — | **DECLINE** (revisit only with a hard confirmation gate). |
| Contacts.app, VIP/signatures/SMTP | Cross-app / niche | Scope creep | — | **DECLINE.** |
| Export-as-tool (TXT/HTML/MD) | Neutral | Low value | Recipe | **DECLINE-as-tool** — `get_messages` + caller writes disk. |
| Onboarding / distribution | Yes | Yes | — | **Already #332/#333** — out of scope here. |

## Proposed follow-up issues (the adopt-list)

Filed 2026-06-15 on milestone **v0.11.0**:

1. **#376 — [research] Spike a local-DB fast read path for large-mailbox search** — evaluate
   reading Apple's Envelope Index (`~/Library/Mail/V*/MailData/Envelope Index`) + `.emlx` directly
   (à la imdinu/rusty/che) as a read accelerator beneath `search_messages`/`get_messages`, keeping
   AppleScript+IMAP as fallback. Decide: worth it? Full Disk Access tradeoff? cache/invalidation
   model? Answers imdinu's public AppleScript-vs-DB benchmarks. *Label: research.*
2. **#377 — [feature] Smart-inbox thin adds: `get_awaiting_reply` + `get_top_senders`** over
   `get_thread`/`search_messages` (no new backend). Treats `get_needs_response` as out-of-scope
   (heuristic). *Label: enhancement.*
3. **#378 — [feature] `get_statistics` — mailbox/volume/sender analytics** aggregating
   `search_messages` + `list_mailboxes`. Small; may land with #377. *Label: enhancement.*

Decline/》defer (recorded, not filed): mail-merge serial send, Contacts integration,
VIP/signatures/SMTP, export-as-tool, multi-format attachment extraction, link/raw-headers/sync
tools. Rich-HTML `.eml` → #251. Send/reply/forward + onboarding discoverability → #333/#332.

## Provenance / references

All read live on 2026-06-14 via `gh api`/source:
- patrickfreyer/apple-mail-mcp — https://github.com/patrickfreyer/apple-mail-mcp — `6ed3746f0` (2026-06-13), v3.1.7, MIT, PyPI `mcp-apple-mail`.
- imdinu/apple-mail-mcp — https://github.com/imdinu/apple-mail-mcp — `463e22565` (2026-06-12), v0.4.1, GPL-3.0.
- sweetrb/apple-mail-mcp — https://github.com/sweetrb/apple-mail-mcp — `c57c66647` (2026-06-01), v1.5.5, MIT.
- PsychQuant/che-apple-mail-mcp — https://github.com/PsychQuant/che-apple-mail-mcp — `a703fd073` (2026-06-14), v2.0.1, MIT (Swift). cyber404/che-apple-mail-mcp is a stale code copy (45 tools), not the canonical repo.
- like-a-freedom/rusty_apple_mail_mcp — https://github.com/like-a-freedom/rusty_apple_mail_mcp — `647054185` (2026-05-30), v1.4.1, no license.
- Landscape ranking: GitHub repo search, 2026-06-14. Multi-app suites (GodModeAI2025/AppleMCP, l22-io/orchard-mcp) noted but not deep-dived.
