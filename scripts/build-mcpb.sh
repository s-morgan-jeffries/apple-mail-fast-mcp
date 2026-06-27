#!/usr/bin/env bash
# Build the Claude Desktop .mcpb bundle (#332).
#
# Produces dist/apple-mail-fast-mcp-<version>.mcpb — a uv-type MCP bundle
# (manifest_version 0.4). Claude Desktop manages Python + uv and resolves
# dependencies from the bundled pyproject.toml/uv.lock at install time, so we
# never bundle compiled wheels (the spec warns those aren't portable).
#
# Requires Node (for `npx @anthropic-ai/mcpb`). Run: ./scripts/build-mcpb.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MANIFEST="mcpb/manifest.json"
VERSION="$(grep '"version"' "$MANIFEST" | head -1 | sed -E 's/.*"version": *"([^"]+)".*/\1/')"
BUILD_DIR="$(mktemp -d)"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/apple-mail-fast-mcp-${VERSION}.mcpb"

cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

echo "Building apple-mail-fast-mcp.mcpb v${VERSION}"

# Stage only what `uv run` needs at the bundle root to resolve + launch the
# server: the manifest, the project metadata/lock, the README referenced by
# pyproject, the license, and the package source.
cp "$MANIFEST" "$BUILD_DIR/manifest.json"
cp pyproject.toml uv.lock README.md LICENSE "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/src"
cp -R src/apple_mail_fast_mcp "$BUILD_DIR/src/"

# Validate against the MCPB schema, then pack the directory into a .mcpb (zip).
npx --yes @anthropic-ai/mcpb@latest validate "$BUILD_DIR/manifest.json"
mkdir -p "$OUT_DIR"
npx --yes @anthropic-ai/mcpb@latest pack "$BUILD_DIR" "$OUT"

echo ""
npx --yes @anthropic-ai/mcpb@latest info "$OUT" || true
echo ""
echo "Built: $OUT"
