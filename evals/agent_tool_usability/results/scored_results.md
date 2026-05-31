# Blind Agent Eval Results

**Date:** 2026-05-31
**Scenarios:** 42 (3 under-specified / MANUAL: #32, #33, #34 → not scored)
**Version:** v0.9.0 (23 tools — drafts lifecycle, templates, rule CRUD, IMAP fast paths)
**Runs:** Claude 1 run (Claude Code subagent, deterministic). OpenRouter models 5 runs each @ temperature=0.
**Scoring:** PASS=2, PARTIAL=1, FAIL=0, MANUAL=not scored. Rule-based regex scorer
(`score_response_regex`). Max per run over 39 scored scenarios = 78.
**Context:** Models receive *only* the regenerated server instructions + tool descriptions
(`tool_descriptions.md`, now generated from the live FastMCP server — see `generate_descriptions.py`).

## Summary

| Model | Score (MANUAL excl.) | PASS/run | FAIL/run | PASS% | Notes |
|-------|----------------------|----------|----------|-------|-------|
| Claude Sonnet 4.6 (Claude Code subagent) | 58/78 (1 run) | 29.0 | 10.0 | 74% | deterministic |
| DeepSeek V3 0324 | 298/390 (5 runs) | 29.8 | 9.2 | 76% | |
| Llama 3.3 70B Instruct | 294/390 (5 runs) | 29.4 | 9.6 | 75% | |
| Qwen 2.5 72B Instruct | 285/390 (5 runs) | 28.0 | 10.0 | 72% | +5 PARTIAL |
| Mistral Large 2411 | 275/390 (5 runs) | 27.2 | 9.8 | 70% | +3 PARTIAL |

All five models cluster at **70–76%** — and, critically, they all FAIL the **same ~10 scenarios**.

## Key Findings

**1. Tool descriptions were badly stale — fixed in this change.** Before this run,
`tool_descriptions.md` documented only ~9 of the 23 shipped tools and `server_instructions.md`
referenced removed tools. They are now **generated from the live server** via
`generate_descriptions.py` (`make eval-descriptions`), so they can't silently drift again.

**2. The headline FAILs are a stale-*scenario* bug, not a model/description problem.**
**10 scenarios FAIL across all 5 models**; 9 of them list **removed tool names** in
`scenarios.py`'s `expected.tools`, so a correct answer using the current surface scores FAIL:

| Scenario(s) | expected (stale) | what models correctly produce |
|---|---|---|
| 14, 15, 17 — Send | `send_email` | `create_draft` + `send_now=true` |
| 16 — Send w/ attachment | `send_email_with_attachments` | `create_draft` + `attachment_paths`, `send_now=true` |
| 26 — Reply | `reply_to_message` | `create_draft` + `reply_to` |
| 27 — Reply all | `reply_to_message` | `create_draft` + `reply_to`, `reply_all=true` |
| 28 — Forward | `forward_message` | `create_draft` + `forward_of` |
| 12 — Headers only | `get_message` | `get_messages` + `headers_only=true` |
| 13 — Latest from sender | `search_messages`, `get_message` | `search_messages` + `get_messages` |

That **all five independent models fail the identical set** is the signature of a scenario bug, not a
capability gap. Tracked in **#284**. With those scenarios corrected, every model is expected to jump
to the high-30s/39 — i.e. the regenerated descriptions are clear enough for blind tool selection.

**3. The one genuine design divergence** is scenario #3 ("which account has the most unread"): all
models run `search_messages(read_status=false)` per account rather than reading `unread_count` from
`list_mailboxes`. Both are defensible — the scenario's single-tool expectation is arguably too
narrow. (#41 "find messages with attachments" failed for only 1/5 models — genuine model variance.)

**4. MANUAL (correct behavior):** #32 ("delete all my old emails"), #33 ("email John" — ambiguous
recipient), #34 ("archive everything") are under-specified; the right move is to ask for
clarification, which the scorer treats as not-scored.

## Takeaways

- **Descriptions ship clear.** Excluding the 10 mis-specified scenarios, all five models pass
  essentially everything — strong evidence the v0.9.0 tool descriptions are unambiguous for an
  unbriefed model.
- **Models are close.** 70–76% raw, tightly clustered; differences are mostly PARTIALs (Qwen/Mistral
  parameter-formatting) rather than tool-selection misses.
- **Next:** fix `scenarios.py` (#284) and re-run for a clean baseline; the harness + descriptions
  are now in place (`make eval-descriptions`, `make eval-tools`).

## Notes
- Raw `raw_*.json` dumps stay git-ignored; only this summary is committed.
- Claude scored via Claude Code subagent (Sonnet 4.6), blind: given only the generated descriptions,
  forbidden from reading the repo. OpenRouter models run at `temperature=0`.
- Total OpenRouter tokens this run: ~5.7M across 4 models × 5 runs × 42 scenarios.
