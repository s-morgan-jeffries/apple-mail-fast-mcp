# Apple Mail Fast MCP — shared agent instructions

This is the canonical project guidance for Codex and Claude Code. Read it at the
start of work, then load only the domain references needed for the task.

## Project map

Python 3.10+, FastMCP, AppleScript via `osascript`, IMAP via `imapclient`, and
SMTP. The server exposes structured MCP tools for Apple Mail on macOS.

All modules below live in `src/apple_mail_fast_mcp/`:

- `server.py`: tool registration, validation, confirmation gates, responses.
- `mail_connector.py`: domain logic and dispatch between AppleScript and network paths.
- `imap_connector.py`: IMAP reads, mutations, connection pool, and tiered thread
  lookup (Gmail X-GM-THRID, IMAP THREAD, header-search BFS).
- `draft_builder.py`, `smtp_sender.py`: MIME construction and clean SMTP sends.
  Drafts can use IMAP APPEND; compose/send is not exclusively AppleScript.
  Credentials and account/seed information determine which path engages.
- `security.py`, `utils.py`, `exceptions.py`: safety gates, sanitization, escaping,
  parsing, and typed errors.
- `drafts.py`, `templates.py`, `imap_overrides.py`, `keychain.py`: state and credentials.

AppleScript is the baseline for many operations, with optional IMAP fast paths.
Some mailbox operations require IMAP. Fallback is not a guarantee of equivalent
latency or completeness: preserve partial/incomplete-result reporting and never
turn an indeterminate lookup into a definitive not-found result.

Use [TOOLS.md](docs/reference/TOOLS.md) for the API and
[ARCHITECTURE.md](docs/reference/ARCHITECTURE.md) for dispatch details. Read current
code before changing a path. `pyproject.toml` is authoritative for version and
dependencies; collect tests and run coverage for current counts. Do not add
hand-maintained line counts, timings, or test totals to these instructions.

## Working a GitHub issue

GitHub is the source of truth for planned work and status. Follow
[CONTRIBUTING.md](CONTRIBUTING.md) and the repository PR template.

1. Inspect the working tree, current branch, issue body/comments/assignees,
   milestone, and open PRs before coding. Respect existing claims and contributor
   work; do not duplicate an in-flight fix. Preserve unrelated local changes.
2. Work from an issue. For new work, file one first; for an existing issue, record
   the claim as described in CONTRIBUTING when authorized to post. A request to
   review an issue alone is not a request to implement it.
3. Start from current `origin/main` on `{type}/issue-{num}-{description}`
   (`feature/`, `fix/`, or `docs/`). Do not commit directly to `main`.
4. For code changes use RED/GREEN/REFACTOR. Keep connector behavior and MCP
   exposure aligned when the API changes; internal or documentation work need
   not modify both modules. Run the relevant checks below before pushing.
5. Open a PR against `main`, using the PR template and `Closes #N` for completed
   issues (or `Related to #N` for partial work). Explain behavior and validation,
   including checks that could not run. Assign the issue's milestone to the PR.
6. After pushing/opening a PR, inspect checks for that PR/current commit. Do not
   report an unrelated latest repository run as this branch's CI result.
7. When asked to merge, follow [MERGE_AND_STATUS.md](docs/guides/MERGE_AND_STATUS.md):
   wait for CI, squash merge ordinary PRs, delete the branch, update local main,
   surface contributor PRs and untriaged contributor issues with counts, then
   report remaining milestone work. Never silently close outside contributions.

`CHANGELOG.md` and version bumps belong on release branches. Use
`./scripts/create_tag.sh` for tags. Release PRs use the release procedure's rebase
merge, not the ordinary PR squash workflow. Read the release reference only when
performing release work; setup or feature work does not execute a release.

## Commit attribution

Keep the human contributor's Git author identity. For work materially authored
with an AI agent, append the appropriate `Co-authored-by` trailer to the commit
message, separated from the body by a blank line. Codex contributions use:

```text
Co-authored-by: Codex <codex@openai.com>
```

For Claude-assisted work, retain the established Claude model attribution using
`noreply@anthropic.com`; use the actual known model name, not a guessed version.
Credit only agents that contributed to the change, and preserve other authors.
Include the same attribution in PR descriptions. Before squash merging, assemble
an explicit merge message preserving all legitimate co-author trailers, then
verify the merged commit. A PR-body edit alone cannot change a merged commit's
authorship. See [CONTRIBUTING.md](CONTRIBUTING.md) for retrospective corrections.

## Setup and validation

```bash
uv sync --dev
./scripts/install-git-hooks.sh
gh auth status
make check-all
```

The Git hooks are shared by both agents. Claude's `.claude/settings.json` hooks
are not this project's Codex automation: explicitly perform the session checks,
branch/tag safeguards, and CI monitoring above. See the full mapping and a
fresh-session smoke check in [CODEX.md](docs/guides/CODEX.md).

| Change | Validation |
|---|---|
| All changes | `make check-all` (lint, mypy, unit tests, complexity, version sync, parity, doc drift) |
| Coverage assessment | `make coverage` (90% minimum; CI enforces coverage separately from `make check-all`) |
| AppleScript changes | Integration tests covering the changed operation, then `make test-integration` on a dedicated test account |
| IMAP paths, AppleScript paths, or elicitation-gated tools | `make test-e2e` before pushing, per CONTRIBUTING |
| New/modified MCP tools | E2E coverage and updated TOOLS.md; regenerate eval descriptions if needed |
| Performance work | Profile the actual path/account first; use `make benchmark` and [BENCHMARKING.md](docs/guides/BENCHMARKING.md) |

Unit tests mock real I/O. Full integration/e2e/benchmark runs have additional
prerequisites and are excluded from CI. Read [TESTING.md](docs/guides/TESTING.md)
and relevant fixtures before running them. Use `MAIL_TEST_MODE=true` and an
explicit dedicated `MAIL_TEST_ACCOUNT`; never assume a default account is safe.
Test-mode gates are not universal isolation (see open #352); inspect the targeted
operations and fixtures. Do not send real email as a setup smoke test.

## Implementation rules

- Return structured `{"success": bool, ...}` responses; errors include `error`
  and `error_type`. Preserve typed failures and partial-result semantics.
- Follow [SECURITY_CHECKLIST.md](docs/guides/SECURITY_CHECKLIST.md): sanitize inputs,
  escape interpolated AppleScript strings, validate path-bearing names, apply
  rate limits and audit logging, and consider confirmation for effects.
- Use the existing AppleScript JSON wrapper/parser (`NSJSONSerialization`), quote
  record key `|name|`, and coerce `missing value` before serialization. Let errors
  that need typed routing reach `_run_applescript` via stderr.
- Build AppleScript dates with `_construct_as_date_var`, never date-string literals.
- Numeric Mail IDs and RFC Message-IDs are different. Preserve both ID forms;
  avoid unindexed `whose message id is ...` scans that freeze Mail. Use existing
  resolvers and account/mailbox hints. Profile property reads as well as subprocess
  and network costs; batching is not automatically faster (see #450).
- Gmail labels need provider-aware handling. `gmail_mode` is deprecated; do not
  introduce it on new tools. Inspect current connector behavior before changing moves.
- Persistent application data uses `~/.apple_mail_mcp/` or `APPLE_MAIL_MCP_HOME`.
  Resolve storage roots at use time and validate filename stems before building
  paths. Keep credentials out of source, issue bodies, and logs.

## Domain references

These remain single-source files under `.claude/skills/`. Codex should open them
as task-specific references; no copied Codex skill installation is required.
Their historical examples can lag current behavior. The current rules above and
maintained API docs take precedence over stale tool counts, old timings, or
examples claiming that rule mutation is unimplemented.

- AppleScript work: [applescript-mail](.claude/skills/applescript-mail/SKILL.md)
- API changes: [api-design](.claude/skills/api-design/SKILL.md)
- Real-Mail testing: [integration-testing](.claude/skills/integration-testing/SKILL.md)
- Performance work: [performance-patterns](.claude/skills/performance-patterns/SKILL.md)
- Releases: [release](.claude/skills/release/SKILL.md). If a named reviewer plugin
  is unavailable, use an available review workflow and report that substitution.
