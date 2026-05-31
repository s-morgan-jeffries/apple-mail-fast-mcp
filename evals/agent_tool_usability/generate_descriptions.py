#!/usr/bin/env python3
"""Regenerate tool_descriptions.md from the live FastMCP server.

The blind agent eval feeds models *only* the server instructions +
tool descriptions. Those descriptions used to be hand-maintained and rotted
badly (documented ~9 of 23 tools after the drafts/templates/rule-CRUD work).
This generator makes the file a derived artifact so it can't silently drift
again: it pulls every registered tool's name, description (docstring), and
parameter schema straight from `mcp.list_tools()`.

`server_instructions.md` stays hand-maintained (the server registers no
`instructions=` string) and is embedded verbatim here.

Usage:
    uv run python evals/agent_tool_usability/generate_descriptions.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from apple_mail_mcp.server import mcp

SCRIPT_DIR = Path(__file__).parent
SERVER_INSTRUCTIONS_PATH = SCRIPT_DIR / "server_instructions.md"
TOOL_DESCRIPTIONS_PATH = SCRIPT_DIR / "tool_descriptions.md"


def _type_str(schema: dict[str, Any]) -> str:
    """Best-effort human type label for a JSON-schema property."""
    if "anyOf" in schema:
        parts = [_type_str(s) for s in schema["anyOf"]]
        non_null = [p for p in parts if p != "null"]
        return " | ".join(dict.fromkeys(non_null)) or "any"
    t = schema.get("type")
    if t == "array":
        items = schema.get("items", {})
        return f"list[{_type_str(items)}]" if items else "list"
    if isinstance(t, list):
        return " | ".join(t)
    return t or "any"


def _render_params(input_schema: dict[str, Any]) -> str:
    props: dict[str, Any] = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not props:
        return "_No parameters._"
    lines = []
    for name, spec in props.items():
        req = "required" if name in required else "optional"
        type_label = _type_str(spec)
        desc = (spec.get("description") or "").strip().replace("\n", " ")
        default = spec.get("default", None)
        default_note = ""
        if name not in required and default is not None:
            default_note = f" (default: {default!r})"
        suffix = f": {desc}" if desc else ""
        lines.append(f"- `{name}` ({type_label}, {req}){default_note}{suffix}")
    return "\n".join(lines)


async def _build() -> str:
    tools = await mcp.list_tools()
    instructions = SERVER_INSTRUCTIONS_PATH.read_text().strip()

    out: list[str] = [
        "# Apple Mail MCP — Tool Descriptions",
        "",
        "This file contains exactly what an MCP-connected agent sees: the "
        "server instructions and all tool schemas with docstrings. Used as "
        "input for the blind agent eval.",
        "",
        "**Generated** by `generate_descriptions.py` from the live FastMCP "
        "server — do not edit by hand (run `make eval-descriptions`).",
        "",
        "## Server Instructions",
        "",
        instructions,
        "",
        "---",
        "",
        f"## Tools ({len(tools)})",
        "",
    ]

    for tool in sorted(tools, key=lambda t: t.name):
        desc = (tool.description or "").strip()
        out.append(f"### {tool.name}")
        out.append("")
        if desc:
            out.append(desc)
            out.append("")
        out.append("**Parameters:**")
        out.append("")
        out.append(_render_params(tool.parameters or {}))
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    content = asyncio.run(_build())
    TOOL_DESCRIPTIONS_PATH.write_text(content)
    tool_count = content.count("\n### ")
    print(f"Wrote {TOOL_DESCRIPTIONS_PATH} ({tool_count} tools)")


if __name__ == "__main__":
    main()
