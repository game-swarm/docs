#!/usr/bin/env python3
"""Synchronize generated API Registry metadata with docs IDL inputs."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "specs/reference/api-registry.md"
GAME_IDL = ROOT / "specs/reference/game_api.idl.yaml"
AUTH_IDL = ROOT / "specs/reference/auth_api.idl.yaml"
ECONOMY_IDL = ROOT / "specs/reference/economy.idl.yaml"

BEGIN_MARKER = "<!-- BEGIN GENERATED API REGISTRY METADATA -->"
END_MARKER = "<!-- END GENERATED API REGISTRY METADATA -->"
VERSION_RE = re.compile(
    r"^\*\*API 版本\*\*:\s*`([^`]+)`\s*\(game_api\)\s*/\s*"
    r"`([^`]+)`\s*\(auth_api\)\s*/\s*`([^`]+)`\s*\(economy\)\s*$",
    re.MULTILINE,
)
TOOL_COUNT_ROW_RE = re.compile(
    r"^\| `(?P<name>all_declared|active_only|gated)` \|\s*\d+ \|\s*\d+ \|\s*\d+ \|(?P<tail>.*)$",
    re.MULTILINE,
)
GAME_TOOL_HEADING_RE = re.compile(
    r"^### 3\.2 Game API 工具清单 \(`all_declared=\d+`, `active_only=\d+`, `rfc_gated=\d+`\)$",
    re.MULTILINE,
)
SYNC_REQUIREMENT_RE = re.compile(
    r"^> \*\*同步要求\*\*: 工具计数必须与 IDL YAML 一致。.*$",
    re.MULTILINE,
)
HOST_SYNC_REQUIREMENT_RE = re.compile(
    r"^> \*\*同步要求\*\*: Host Function 清单和计数必须与 IDL YAML 一致。.*$",
    re.MULTILINE,
)


class YamlSubsetError(ValueError):
    pass


@dataclass(frozen=True)
class RegistryMetadata:
    game_version: str
    auth_version: str
    economy_version: str
    command_variants: int
    rejection_reasons: int
    game_tools_active: int
    game_tools_gated: int
    auth_tools: int
    host_functions: int
    economy_operations: int
    engine_summary: str

    @property
    def game_tools_all_declared(self) -> int:
        return self.game_tools_active + self.game_tools_gated

    @property
    def all_tools_declared(self) -> int:
        return self.game_tools_all_declared + self.auth_tools

    @property
    def all_tools_active(self) -> int:
        return self.game_tools_active + self.auth_tools

    @property
    def all_tools_gated(self) -> int:
        return self.game_tools_gated


def strip_inline_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip()
    return line.rstrip()


def split_key_value(text: str) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == ":" and quote is None:
            return text[:index].strip(), text[index + 1 :].strip()
    raise YamlSubsetError(f"expected key/value pair, got: {text!r}")


def has_mapping_separator(text: str) -> bool:
    try:
        split_key_value(text)
    except YamlSubsetError:
        return False
    return True


def parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"{}", "{ }"}:
        return {}
    if value in {"[]", "[ ]"}:
        return []
    if value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    normalized = value.replace("_", "")
    if re.fullmatch(r"-?\d+", normalized):
        return int(normalized)
    return value


def preprocess_yaml(path: Path) -> list[tuple[int, str]]:
    processed: list[tuple[int, str]] = []
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(raw_lines):
        raw = raw_lines[index].rstrip()
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        line = strip_inline_comment(raw)
        if not line.strip():
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if body.endswith(": >") or body.endswith(": |") or body.endswith(": >-") or body.endswith(": |-"):
            key = body.split(":", 1)[0].strip()
            block_lines: list[str] = []
            index += 1
            while index < len(raw_lines):
                candidate = raw_lines[index].rstrip()
                if not candidate.strip():
                    block_lines.append("")
                    index += 1
                    continue
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate_indent <= indent:
                    break
                block_lines.append(candidate.strip())
                index += 1
            processed.append((indent, f'{key}: "{" ".join(block_lines).strip()}"'))
            continue
        processed.append((indent, body))
        index += 1
    return processed


def parse_yaml_subset(path: Path) -> Any:
    lines = preprocess_yaml(path)
    if not lines:
        return {}
    value, index = parse_node(lines, 0, lines[0][0])
    if index != len(lines):
        raise YamlSubsetError(f"unparsed YAML content remains in {path}")
    return value


def parse_node(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_indent != indent:
        raise YamlSubsetError(f"unexpected indentation before {text!r}")
    if text.startswith("- "):
        return parse_list(lines, index, indent)
    return parse_map(lines, index, indent)


def parse_map(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent or text.startswith("- "):
            break
        if current_indent != indent:
            raise YamlSubsetError(f"unexpected map indentation before {text!r}")
        key, value = split_key_value(text)
        index += 1
        if value:
            result[key] = parse_scalar(value)
            continue
        if index < len(lines) and lines[index][0] > indent:
            child, index = parse_node(lines, index, lines[index][0])
            result[key] = child
        else:
            result[key] = {}
    return result, index


def parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not text.startswith("- "):
            break
        item_text = text[2:].strip()
        index += 1
        if not item_text:
            if index < len(lines) and lines[index][0] > indent:
                item, index = parse_node(lines, index, lines[index][0])
            else:
                item = None
        elif has_mapping_separator(item_text):
            key, value = split_key_value(item_text)
            item = {key: parse_scalar(value)} if value else {key: {}}
            if not value and index < len(lines) and lines[index][0] > indent:
                child, index = parse_node(lines, index, lines[index][0])
                item[key] = child
            if index < len(lines) and lines[index][0] > indent:
                child, index = parse_node(lines, index, lines[index][0])
                if not isinstance(child, dict):
                    raise YamlSubsetError(f"expected mapping fields for list item {item_text!r}")
                item.update(child)
        else:
            item = parse_scalar(item_text)
            if index < len(lines) and lines[index][0] > indent:
                raise YamlSubsetError(f"unexpected nested data under scalar list item {item_text!r}")
        result.append(item)
    return result, index


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def validate_declared_total(mapping: dict[str, Any], key: str, actual: int, name: str) -> None:
    declared = mapping.get(key)
    if not isinstance(declared, int):
        raise ValueError(f"{name}.{key} must be an integer")
    if declared != actual:
        raise ValueError(f"{name}.{key} declares {declared} but parsed list contains {actual}")


def gated_tool_list(mcp_tools: dict[str, Any]) -> list[Any]:
    gated = mcp_tools.get("gated_tools", [])
    if isinstance(gated, dict):
        return require_list(gated.get("tools", []), "game_api.mcp_tools.gated_tools.tools")
    return require_list(gated, "game_api.mcp_tools.gated_tools")


def count_engine_idl(path: Path | None) -> str:
    if path is None:
        return "not supplied"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Engine IDL JSON root must be an object")
    counts = []
    candidates = [
        ("commands", "commands"),
        ("command_actions", "command_actions"),
        ("rejection_reasons", "rejection_reasons"),
        ("mcp_tools", "mcp_tools"),
        ("tools", "tools"),
        ("host_functions", "host_functions"),
    ]
    for key, label in candidates:
        value = data.get(key)
        if isinstance(value, list):
            counts.append(f"{label}={len(value)}")
        elif isinstance(value, dict):
            counts.append(f"{label}={len(value)}")
    return ", ".join(counts) if counts else "supplied; no recognized count arrays"


def collect_metadata(
    game_idl: Path,
    auth_idl: Path,
    economy_idl: Path,
    engine_idl: Path | None = None,
) -> RegistryMetadata:
    game = require_mapping(parse_yaml_subset(game_idl), str(game_idl))
    auth = require_mapping(parse_yaml_subset(auth_idl), str(auth_idl))
    economy = require_mapping(parse_yaml_subset(economy_idl), str(economy_idl))

    command_action = require_mapping(game.get("command_action"), "game_api.command_action")
    rejection_reason = require_mapping(game.get("rejection_reason"), "game_api.rejection_reason")
    mcp_tools = require_mapping(game.get("mcp_tools"), "game_api.mcp_tools")
    host_functions = require_mapping(game.get("host_functions"), "game_api.host_functions")
    action_registry = require_mapping(command_action.get("action_registry"), "game_api.command_action.action_registry")
    vanilla_actions = require_mapping(
        action_registry.get("vanilla_actions"),
        "game_api.command_action.action_registry.vanilla_actions",
    )
    tick_trace_envelope = require_mapping(game.get("tick_trace_envelope"), "game_api.tick_trace_envelope")
    auth_tools = require_mapping(auth.get("csr_lifecycle_tools"), "auth_api.csr_lifecycle_tools")
    auth_rejection_reason = require_mapping(auth.get("rejection_reason"), "auth_api.rejection_reason")
    auth_trace_events = require_mapping(auth.get("auth_trace_events"), "auth_api.auth_trace_events")
    economy_ops = require_mapping(economy.get("resource_operation"), "economy.resource_operation")

    game_tools = require_list(mcp_tools.get("tools"), "game_api.mcp_tools.tools")
    gated_tools = gated_tool_list(mcp_tools)
    vanilla_action_list = require_list(
        vanilla_actions.get("actions"),
        "game_api.command_action.action_registry.vanilla_actions.actions",
    )
    tick_trace_fields = require_list(tick_trace_envelope.get("fields"), "game_api.tick_trace_envelope.fields")
    auth_tool_list = require_list(auth_tools.get("tools"), "auth_api.csr_lifecycle_tools.tools")
    auth_rejection_variants = require_list(
        auth_rejection_reason.get("variants"),
        "auth_api.rejection_reason.variants",
    )
    auth_event_list = require_list(auth_trace_events.get("events"), "auth_api.auth_trace_events.events")
    host_function_list = require_list(host_functions.get("functions"), "game_api.host_functions.functions")
    operation_list = require_list(economy_ops.get("operations"), "economy.resource_operation.operations")
    command_variants = require_list(command_action.get("variants"), "game_api.command_action.variants")
    rejection_variants = require_list(rejection_reason.get("variants"), "game_api.rejection_reason.variants")

    validate_declared_total(command_action, "total_variants", len(command_variants), "game_api.command_action")
    validate_declared_total(
        action_registry,
        "total_vanilla",
        len(vanilla_action_list),
        "game_api.command_action.action_registry",
    )
    validate_declared_total(
        rejection_reason,
        "total_canonical_codes",
        len(rejection_variants),
        "game_api.rejection_reason",
    )
    validate_declared_total(mcp_tools, "total_tools", len(game_tools), "game_api.mcp_tools")
    validate_declared_total(auth_tools, "total_tools", len(auth_tool_list), "auth_api.csr_lifecycle_tools")
    validate_declared_total(
        auth_rejection_reason,
        "total_canonical_codes",
        len(auth_rejection_variants),
        "auth_api.rejection_reason",
    )
    validate_declared_total(
        auth_trace_events,
        "total_event_types",
        len(auth_event_list),
        "auth_api.auth_trace_events",
    )
    validate_declared_total(host_functions, "total_functions", len(host_function_list), "game_api.host_functions")
    validate_declared_total(
        tick_trace_envelope,
        "total_fields",
        len(tick_trace_fields),
        "game_api.tick_trace_envelope",
    )

    return RegistryMetadata(
        game_version=str(game["api_version"]),
        auth_version=str(auth["api_version"]),
        economy_version=str(economy["api_version"]),
        command_variants=len(command_variants),
        rejection_reasons=len(rejection_variants),
        game_tools_active=len(game_tools),
        game_tools_gated=len(gated_tools),
        auth_tools=len(auth_tool_list),
        host_functions=len(host_function_list),
        economy_operations=len(operation_list),
        engine_summary=count_engine_idl(engine_idl),
    )


def generated_block(metadata: RegistryMetadata) -> str:
    lines = [
        BEGIN_MARKER,
        "<!-- Generated by scripts/sync_api_registry.py; edit IDL inputs, then rerun the CLI. -->",
        "",
        "| Field | Value | Source |",
        "|---|---:|---|",
        f"| game_api version | `{metadata.game_version}` | game_api.idl.yaml |",
        f"| auth_api version | `{metadata.auth_version}` | auth_api.idl.yaml |",
        f"| economy version | `{metadata.economy_version}` | economy.idl.yaml |",
        f"| CommandAction variants | {metadata.command_variants} | game_api.idl.yaml |",
        f"| RejectionReason canonical codes | {metadata.rejection_reasons} | game_api.idl.yaml |",
        f"| MCP tools all_declared | {metadata.all_tools_declared} | game_api.idl.yaml + auth_api.idl.yaml |",
        f"| MCP tools active_only | {metadata.all_tools_active} | game_api.idl.yaml + auth_api.idl.yaml |",
        f"| MCP tools gated | {metadata.all_tools_gated} | game_api.idl.yaml |",
        f"| Host functions | {metadata.host_functions} | game_api.idl.yaml |",
        f"| Economy operations | {metadata.economy_operations} | economy.idl.yaml |",
        f"| Engine-extracted IDL | {metadata.engine_summary} | optional `--engine-idl` JSON |",
        "",
        END_MARKER,
    ]
    return "\n".join(lines)


def replace_or_insert_generated_block(text: str, metadata: RegistryMetadata) -> str:
    block = generated_block(metadata)
    pattern = re.compile(
        rf"{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    anchor = "**维护与校验**:"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(anchor):
            lines[index + 1 : index + 1] = ["", block]
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise ValueError("api-registry.md is missing the maintenance metadata anchor")


def update_registry_text(text: str, metadata: RegistryMetadata) -> str:
    expected_version = (
        f"**API 版本**: `{metadata.game_version}` (game_api) / "
        f"`{metadata.auth_version}` (auth_api) / `{metadata.economy_version}` (economy)"
    )
    text, version_count = VERSION_RE.subn(expected_version, text, count=1)
    if version_count != 1:
        raise ValueError("api-registry.md must contain exactly one API version line")

    text = replace_or_insert_generated_block(text, metadata)

    def tool_row(match: re.Match[str]) -> str:
        name = match.group("name")
        if name == "all_declared":
            values = (metadata.game_tools_all_declared, metadata.auth_tools, metadata.all_tools_declared)
        elif name == "active_only":
            values = (metadata.game_tools_active, metadata.auth_tools, metadata.all_tools_active)
        else:
            values = (metadata.game_tools_gated, 0, metadata.all_tools_gated)
        return f"| `{name}` | {values[0]} | {values[1]} | {values[2]} |{match.group('tail')}"

    text, row_count = TOOL_COUNT_ROW_RE.subn(tool_row, text)
    if row_count != 3:
        raise ValueError("api-registry.md must contain the three MCP tool count rows")

    expected_heading = (
        "### 3.2 Game API 工具清单 "
        f"(`all_declared={metadata.game_tools_all_declared}`, "
        f"`active_only={metadata.game_tools_active}`, `rfc_gated={metadata.game_tools_gated}`)"
    )
    text, heading_count = GAME_TOOL_HEADING_RE.subn(expected_heading, text, count=1)
    if heading_count != 1:
        raise ValueError("api-registry.md must contain the generated Game API tool-count heading")

    sync_text = (
        "> **同步要求**: 工具计数必须与 IDL YAML 一致。"
        "`scripts/sync_api_registry.py --check` 会验证本节生成的版本与计数；"
        "修改工具定义时必须在同一变更中同步 IDL、本表和相关引用。"
    )
    text = SYNC_REQUIREMENT_RE.sub(sync_text, text, count=1)
    host_sync_text = (
        "> **同步要求**: Host Function 清单和计数必须与 IDL YAML 一致。"
        "`scripts/sync_api_registry.py --check` 会验证生成 metadata 中的函数计数；"
        "修改函数定义时必须同步更新 IDL 与本表。"
    )
    text = HOST_SYNC_REQUIREMENT_RE.sub(host_sync_text, text, count=1)
    return text


def synchronize(
    registry: Path,
    game_idl: Path,
    auth_idl: Path,
    economy_idl: Path,
    engine_idl: Path | None,
    check: bool,
) -> tuple[bool, str]:
    metadata = collect_metadata(game_idl, auth_idl, economy_idl, engine_idl)
    original = registry.read_text(encoding="utf-8")
    updated = update_registry_text(original, metadata)
    if original == updated:
        return False, "API Registry metadata is in sync"
    if check:
        diff = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=str(registry),
                tofile=f"{registry} (generated)",
                lineterm="",
            )
        )
        return True, diff
    registry.write_text(updated, encoding="utf-8")
    return True, "API Registry metadata updated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or update generated API Registry metadata, tool counts, "
            "and versions from docs IDL YAML files."
        )
    )
    parser.add_argument("--check", action="store_true", help="exit nonzero and print a diff if generated metadata is stale")
    parser.add_argument("--registry", type=Path, default=REGISTRY, help="path to api-registry.md")
    parser.add_argument("--game-idl", type=Path, default=GAME_IDL, help="path to game_api.idl.yaml")
    parser.add_argument("--auth-idl", type=Path, default=AUTH_IDL, help="path to auth_api.idl.yaml")
    parser.add_argument("--economy-idl", type=Path, default=ECONOMY_IDL, help="path to economy.idl.yaml")
    parser.add_argument("--engine-idl", type=Path, default=None, help="optional Engine-extracted IDL JSON to summarize in generated metadata")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed, message = synchronize(
            registry=args.registry,
            game_idl=args.game_idl,
            auth_idl=args.auth_idl,
            economy_idl=args.economy_idl,
            engine_idl=args.engine_idl,
            check=args.check,
        )
    except (OSError, ValueError, YamlSubsetError, json.JSONDecodeError) as exc:
        print(f"api registry sync failed: {exc}", file=sys.stderr)
        return 2
    if args.check and changed:
        print("api registry metadata is stale:", file=sys.stderr)
        print(message, file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
