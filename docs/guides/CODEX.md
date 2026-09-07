# Developing with Codex

Open this repository in Codex and start a new session. The root
[AGENTS.md](../../AGENTS.md) supplies shared project instructions automatically;
[.claude/CLAUDE.md](../../.claude/CLAUDE.md) points Claude Code to the same source.
Instruction discovery happens at session startup, so start a fresh session after
changing guidance. See [official instruction discovery documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Local setup

Use a Mac for work requiring Apple Mail. From the repository root:

```bash
uv sync --dev
./scripts/install-git-hooks.sh
gh auth status
make check-all
```

If GitHub CLI has no login, run `gh auth login`. Its authentication is separate
from Codex permissions: a sandbox approval permits a command to run, while `gh`
uses its existing credentials to access GitHub. Do not put tokens in repository
configuration. See [DEVELOPMENT.md](DEVELOPMENT.md) for the Python environment.

This setup needs no project model override, additional MCP connection, or copied
skills. The existing skills are linked from AGENTS.md and can be read directly.
Connecting Codex to this server to operate email is a separate client setup task.

## Workflow automation mapping

| Existing Claude mechanism | Shared/Codex behavior |
|---|---|
| `scripts/hooks/session_start.sh` | AGENTS.md instructs the agent to inspect Git state, issue discussion, milestone, and open PRs at task start; this is an explicit workflow step, not an installed Codex hook. `uv run` supplies the Python environment. |
| `scripts/hooks/pre_bash.sh` | Shared pre-commit hook blocks ordinary commits to main; AGENTS.md also requires an issue branch and the `scripts/create_tag.sh` wrapper. |
| `scripts/hooks/post_bash.sh` | Explicitly inspect the current PR's checks after push/PR creation; wait for CI before merge. No automatic Codex post-command watcher is installed. |
| `.claude/commands/merge-and-status.md` | Both agents read [MERGE_AND_STATUS.md](MERGE_AND_STATUS.md); Codex can be asked to “merge and show status.” |
| `.claude/skills/*/SKILL.md` | Shared by reference from AGENTS.md; Claude retains its existing discovery paths. |
| `scripts/git-hooks/pre-commit` and `pre-push` | Installed Git hooks execute for either agent: version/branch checks at commit and unit tests at push. |

Git hooks and written instructions complement CI; they are not identical
enforcement. In particular, Git does not automatically execute the custom
`pre-tag` hook: the tag wrapper performs its own branch, format, and version checks. See the shared workflow before
performing a release. The `.claude/settings.json` hooks remain Claude-specific;
this change does not translate their payloads into Codex hooks.

## Verify a fresh session

Start a new Codex session in this repository and ask:

> Without changing files, using GitHub, or accessing Mail, summarize the project
> instructions you received: issue/branch/PR workflow, checks before pushing,
> post-merge reporting, backend architecture, and where to find domain guidance.

Expected: the answer identifies root AGENTS.md; explains issue-linked branches,
TDD for code, `make check-all` plus relevant real-Mail tests, the normal squash
merge and release exception, contributor visibility after merge, and the
AppleScript/IMAP/SMTP paths. It should name the referenced domain files without
requiring a Claude plugin. This is a read-only comprehension check, not a request
to work an issue or run a release.

If available, the CLI can run the same prompt with `codex exec --sandbox read-only`.
Use a fresh invocation, not `resume`. If instructions are missing, check the
working directory and any applicable `AGENTS.override.md` or global guidance
using the official documentation above.

Run `make check-all` after instruction edits. Its documentation check validates
links in AGENTS.md, the Claude entry point, and the shared workflow. Version sync
still checks the Claude wrapper's version field, preserving release compatibility.

## Real-Mail testing is separate

`make check-all` uses mocked unit tests and does not establish real-Mail behavior.
For full integration/e2e tests, read [TESTING.md](TESTING.md), configure a dedicated
test account, and set `MAIL_TEST_MODE=true` and `MAIL_TEST_ACCOUNT` explicitly.
macOS Automation permission and, for network paths, test-account credentials may
also be needed. Never use production mail or send email to validate Codex setup.

This setup overlaps the orientation cleanup in GitHub #424: shared guidance drops
derived counts and documents both network backends. A broader audit of historical
domain examples remains separate; check current code and API docs when using them.
