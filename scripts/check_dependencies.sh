#!/bin/bash
# Check dependencies for known advisories with pip-audit (release gate).
#
# Direct-vs-transitive split (#296): this gate hard-fails (exit 1) ONLY on
# advisories affecting our DIRECT runtime deps (pyproject [project].dependencies
# — fastmcp, imapclient). Advisories in TRANSITIVE deps are printed as warnings
# and DO NOT block (exit 0): a freshly-disclosed transitive CVE shouldn't force a
# last-minute bump on a release branch. Transitive advisories are surfaced
# continuously off the release path by the weekly .github/workflows/dependency-audit.yml
# job, which opens/updates a tracking issue so they land on their own PRs.
set -euo pipefail

echo "Checking dependencies for vulnerabilities..."

# pip-audit is declared in pyproject.toml's dev dep group, so `uv sync --dev`
# installs it into .venv. `uv run` resolves it from there — calling bare
# `pip-audit` (or trying to install it ad-hoc) doesn't work because the
# .venv bin isn't on the script-runtime PATH. pip-audit exits non-zero when it
# finds advisories; we drive the verdict from the JSON, so swallow that here.
AUDIT_JSON=$(uv run pip-audit --format json 2>/dev/null) || true

# Pass the JSON via the environment, not stdin: `python3 - <<'PY'` already uses
# stdin for the program text, so a piped payload would be swallowed.
AUDIT_JSON="$AUDIT_JSON" python3 - <<'PY'
import json
import os
import re
import sys

# Direct runtime deps = names declared in pyproject.toml [project].dependencies.
# Parsed by regex (not tomllib) so this works on Python 3.10 too. Names are
# normalized (lowercased, '_'->'-') to match pip-audit's reporting.
def _norm(name):
    return re.split(r"[<>=!~;\[\s]", name, 1)[0].strip().lower().replace("_", "-")

direct = set()
try:
    pyproject = open("pyproject.toml", encoding="utf-8").read()
    m = re.search(r"(?ms)^\[project\].*?^dependencies\s*=\s*\[(.*?)\]", pyproject)
    if m:
        for raw in re.findall(r'"([^"]+)"', m.group(1)):
            n = _norm(raw)
            if n:
                direct.add(n)
except OSError:
    pass

raw = os.environ.get("AUDIT_JSON", "").strip()
if not raw:
    # pip-audit produced no JSON (e.g. scanner/network failure). Fail closed —
    # a release gate that can't actually scan must not silently pass.
    print("ERROR: pip-audit produced no output; cannot assess advisories.")
    sys.exit(1)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("ERROR: could not parse pip-audit output:")
    print(raw)
    sys.exit(1)

deps = data.get("dependencies", []) if isinstance(data, dict) else data

direct_hits, transitive_hits = [], []
for dep in deps:
    vulns = dep.get("vulns") or []
    if not vulns:
        continue
    name = _norm(dep.get("name", ""))
    version = dep.get("version", "?")
    for v in vulns:
        vid = v.get("id", "?")
        fixes = ", ".join(v.get("fix_versions") or []) or "no fix listed"
        line = f"  {name} {version} — {vid} (fix: {fixes})"
        (direct_hits if name in direct else transitive_hits).append(line)

if transitive_hits:
    print("")
    print("WARNING: advisories in TRANSITIVE dependencies (not release-blocking):")
    print("\n".join(transitive_hits))
    print("")
    print("  These are tracked off the release path by the weekly dependency-audit")
    print("  workflow (see the open '[deps] Dependency advisories detected' issue).")

if direct_hits:
    print("")
    print("FAIL: advisories in DIRECT dependencies (release-blocking):")
    print("\n".join(direct_hits))
    print("")
    print("  Bump the affected direct dependency in pyproject.toml and re-run.")
    sys.exit(1)

if not transitive_hits:
    print("")
    print("No known vulnerabilities found.")
else:
    print("OK: no direct-dependency advisories (transitive warnings above).")
PY
