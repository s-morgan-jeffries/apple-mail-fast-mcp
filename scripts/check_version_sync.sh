#!/bin/bash
# Verify version string is consistent across all authoritative files.
# Authoritative source: pyproject.toml
set -euo pipefail

echo "Checking version synchronization..."

# Extract version from pyproject.toml (authoritative)
PYPROJECT_VERSION=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

if [ -z "$PYPROJECT_VERSION" ]; then
    echo "ERROR: Could not extract version from pyproject.toml"
    exit 1
fi

echo "  pyproject.toml: $PYPROJECT_VERSION (authoritative)"

ERRORS=0

# Check __init__.py
INIT_VERSION=$(grep '__version__' src/apple_mail_fast_mcp/__init__.py | sed 's/__version__ = "\(.*\)"/\1/')
echo "  __init__.py:    $INIT_VERSION"
if [ "$INIT_VERSION" != "$PYPROJECT_VERSION" ]; then
    echo "  ERROR: __init__.py version mismatch!"
    ERRORS=$((ERRORS + 1))
fi

# Check CLAUDE.md
if [ -f ".claude/CLAUDE.md" ]; then
    CLAUDE_VERSION=$(grep '^\*\*Version:\*\*' .claude/CLAUDE.md | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | sed 's/^v//')
    if [ -n "$CLAUDE_VERSION" ]; then
        echo "  CLAUDE.md:      $CLAUDE_VERSION"
        if [ "$CLAUDE_VERSION" != "$PYPROJECT_VERSION" ]; then
            echo "  ERROR: CLAUDE.md version mismatch!"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "  CLAUDE.md:      (no version found - OK if not yet formatted)"
    fi
fi

# Check mcpb/manifest.json (#332 — the .mcpb bundle version must track pyproject)
if [ -f "mcpb/manifest.json" ]; then
    MCPB_VERSION=$(grep '"version"' mcpb/manifest.json | head -1 | sed -E 's/.*"version": *"([^"]+)".*/\1/')
    echo "  mcpb/manifest:  $MCPB_VERSION"
    if [ "$MCPB_VERSION" != "$PYPROJECT_VERSION" ]; then
        echo "  ERROR: mcpb/manifest.json version mismatch!"
        ERRORS=$((ERRORS + 1))
    fi
fi

# Check Claude Code plugin manifests (#398). Both files carry version fields
# (marketplace has a top-level + per-plugin-entry version); every one must
# track pyproject. `for v in $(...)` runs in the current shell so ERRORS sticks.
for PLUGIN_FILE in .claude-plugin/marketplace.json .claude-plugin/plugin.json; do
    if [ -f "$PLUGIN_FILE" ]; then
        for v in $(grep -oE '"version"[[:space:]]*:[[:space:]]*"[0-9]+\.[0-9]+\.[0-9]+"' "$PLUGIN_FILE" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+'); do
            if [ "$v" != "$PYPROJECT_VERSION" ]; then
                echo "  ERROR: $PLUGIN_FILE version $v != $PYPROJECT_VERSION"
                ERRORS=$((ERRORS + 1))
            fi
        done
        echo "  $PLUGIN_FILE: $PYPROJECT_VERSION"
    fi
done

# Check CHANGELOG.md
if [ -f "CHANGELOG.md" ]; then
    CHANGELOG_VERSION=$(grep '^## \[' CHANGELOG.md | grep -v 'Unreleased' | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "")
    if [ -n "$CHANGELOG_VERSION" ]; then
        echo "  CHANGELOG.md:   $CHANGELOG_VERSION (latest entry)"
        if [ "$CHANGELOG_VERSION" != "$PYPROJECT_VERSION" ]; then
            echo "  WARNING: CHANGELOG.md latest entry doesn't match (may be OK if unreleased changes exist)"
        fi
    fi
fi

echo ""

if [ $ERRORS -gt 0 ]; then
    echo "FAILED: $ERRORS version mismatch(es) found."
    exit 1
else
    echo "All versions synchronized."
fi
