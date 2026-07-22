#!/usr/bin/env python3
"""Validate active Markdown links and documentation source metadata."""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

import sync_api_registry


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "reviews"
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
REGISTRY = ROOT / "specs/reference/api-registry.md"
MCP_TOOLS_REFERENCE = ROOT / "specs/reference/mcp-tools.md"
ECONOMY_IDL = ROOT / "specs/reference/economy.idl.yaml"
ACTION_TABLE = ROOT / "specs/reference/special-attack-table.md"
RESOURCE_LEDGER = ROOT / "specs/core/resource-ledger.md"
ECONOMY_BALANCE = ROOT / "design/economy-balance-sheet.md"
GAMEPLAY_DESIGN = ROOT / "design/gameplay.md"
WORLD_RULES = ROOT / "specs/core/world-rules.md"
SNAPSHOT_CONTRACT = ROOT / "specs/core/snapshot-contract.md"
INCREMENTAL_SNAPSHOT = ROOT / "specs/core/incremental-snapshot.md"
VISIBILITY_CONTRACT = ROOT / "specs/security/visibility.md"
ENGINE_DESIGN = ROOT / "design/engine.md"
INTERFACE_DESIGN = ROOT / "design/interface.md"
TECH_CHOICES = ROOT / "design/tech-choices.md"
COMMANDS_REFERENCE = ROOT / "specs/reference/commands.md"
COMMAND_VALIDATION = ROOT / "specs/core/command-validation.md"
GAMEPLAY_IDL = ROOT / "specs/gameplay/api-idl.md"
BODY_PART_DOCS = [ROOT / "design/gameplay.md", ROOT / "specs/core/world-rules.md"]
CORE_ACTIONS = {
    "Attack": "ATTACK",
    "RangedAttack": "RANGED_ATTACK",
    "Heal": "HEAL",
}
VANILLA_BODY_PARTS = {
    "Move": "MOVE",
    "Work": "WORK",
    "Carry": "CARRY",
    "Attack": "ATTACK",
    "RangedAttack": "RANGED_ATTACK",
    "Heal": "HEAL",
    "Claim": "CLAIM",
    "Tough": "TOUGH",
}
FORBIDDEN_GAP_MARKERS = [
    "未实现",
    "待实现",
    "尚未接入",
    "not implemented",
    "not yet implemented",
    "feature-gated",
    "metadata only",
    "currently no",
    "当前没有",
    "目前没有",
    "尚未发布",
    "非当前工具",
    "当前实现边界",
    "当前支持",
]
SCHEMAS = {
    "game_api": ROOT / "specs/reference/game_api.idl.yaml",
    "auth_api": ROOT / "specs/reference/auth_api.idl.yaml",
    "economy": ROOT / "specs/reference/economy.idl.yaml",
}

LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+['\"][^)]*['\"])?\s*\)")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
EXPLICIT_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)=[\"']([^\"']+)[\"']", re.IGNORECASE)
VERSION_RE = re.compile(
    r'^api_version:\s*(?:"([^"\n]+)"|\'([^\'\n]+)\'|([^\s#]+))\s*(?:#.*)?$',
    re.MULTILINE,
)
REGISTRY_VERSION_RE = re.compile(
    r"^\*\*API 版本\*\*:\s*`([^`]+)`\s*\(game_api\)\s*/\s*"
    r"`([^`]+)`\s*\(auth_api\)\s*/\s*`([^`]+)`\s*\(economy\)\s*$",
    re.MULTILINE,
)
MCP_TOOL_COUNT_RE = re.compile(
    r"^\| \*\*Game MCP 小计\*\* \| \*\*`all_declared=(\d+)`, "
    r"`active_only=(\d+)`, `gated=(\d+)`\*\* \|",
    re.MULTILINE,
)


def without_code(text: str, *, strip_inline: bool = True) -> str:
    """Remove fenced code and optionally inline code, preserving line numbers."""
    output: list[str] = []
    fence: tuple[str, int] | None = None
    in_comment = False
    for line in text.splitlines():
        stripped = line.lstrip()
        marker_match = re.match(r"(`{3,}|~{3,})", stripped)
        if marker_match:
            marker = marker_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            output.append("")
            continue
        if fence is not None:
            output.append("")
            continue

        cleaned = line
        if in_comment:
            if "-->" not in cleaned:
                output.append("")
                continue
            cleaned = cleaned.split("-->", 1)[1]
            in_comment = False
        while "<!--" in cleaned:
            before, after = cleaned.split("<!--", 1)
            if "-->" in after:
                cleaned = before + after.split("-->", 1)[1]
            else:
                cleaned = before
                in_comment = True
                break
        if strip_inline:
            cleaned = re.sub(r"(`+).*?\1", "CODE", cleaned)
        output.append(cleaned)
    return "\n".join(output)


def slugify(heading: str) -> str:
    heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = html.unescape(heading).strip().lower()
    heading = re.sub(r"\s", "-", heading)
    return "".join(
        char
        for char in heading
        if char in "-_" or unicodedata.category(char)[0] in {"L", "M", "N"}
    )


def anchors_for(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    text = without_code(path.read_text(encoding="utf-8"), strip_inline=False)
    for line in text.splitlines():
        heading_match = HEADING_RE.match(line)
        if heading_match:
            heading = re.sub(r"\s+#+\s*$", "", heading_match.group(2))
            base = slugify(heading)
            duplicate = counts.get(base, 0)
            anchor = base if duplicate == 0 else f"{base}-{duplicate}"
            counts[base] = duplicate + 1
            anchors.add(anchor)
        anchors.update(EXPLICIT_ANCHOR_RE.findall(line))
    return anchors


def is_archive_path(path: Path) -> bool:
    try:
        path.relative_to(ARCHIVE_ROOT)
    except ValueError:
        return False
    return True


def check_input_paths(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        if path.is_symlink() or not path.is_file():
            errors.append(f"{relative}: input must be a regular non-symlink file")
            continue
        if path.suffix.lower() == ".md" and path.stat().st_size > MAX_MARKDOWN_BYTES:
            errors.append(f"{relative}: active Markdown exceeds {MAX_MARKDOWN_BYTES} bytes")
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(ROOT)
        except (OSError, RuntimeError, ValueError):
            errors.append(f"{relative}: input must resolve inside the repository")
    return errors


def check_links(markdown_files: list[Path]) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for source in markdown_files:
        source_name = str(source.relative_to(ROOT))
        text = without_code(source.read_text(encoding="utf-8"))
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in LINK_RE.finditer(line):
                raw_target = match.group(1) or match.group(2)
                parsed = urlsplit(raw_target)
                if parsed.scheme or raw_target.startswith("//"):
                    continue

                raw_path = unquote(parsed.path)
                candidate = source if not raw_path else source.parent / raw_path
                if candidate.is_symlink():
                    errors.append(f"{source_name}:{line_number}: symlink targets are not allowed: {raw_target}")
                    continue
                target = candidate.resolve()
                if is_archive_path(target):
                    continue
                try:
                    target.relative_to(ROOT)
                except ValueError:
                    errors.append(f"{source.relative_to(ROOT)}:{line_number}: link escapes repository: {raw_target}")
                    continue
                if not target.exists():
                    errors.append(f"{source.relative_to(ROOT)}:{line_number}: missing target: {raw_target}")
                    continue
                if parsed.fragment:
                    if not target.is_file() or target.suffix.lower() != ".md":
                        errors.append(f"{source.relative_to(ROOT)}:{line_number}: anchor target is not Markdown: {raw_target}")
                        continue
                    anchors = anchor_cache.setdefault(target, anchors_for(target))
                    fragment = unquote(parsed.fragment)
                    if fragment.startswith("user-content-"):
                        fragment = fragment[len("user-content-") :]
                    if fragment not in anchors:
                        errors.append(f"{source_name}:{line_number}: missing anchor: {raw_target}")
    return errors


def schema_version(path: Path) -> str | None:
    match = VERSION_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return None
    return next(value for value in match.groups() if value is not None)


def check_registry_metadata() -> list[str]:
    errors: list[str] = []
    registry_text = REGISTRY.read_text(encoding="utf-8")
    declared_match = REGISTRY_VERSION_RE.search(registry_text)
    if not declared_match:
        errors.append("specs/reference/api-registry.md: missing canonical API version declaration")
        return errors

    declared = dict(zip(SCHEMAS, declared_match.groups()))
    for name, path in SCHEMAS.items():
        if re.search(r"^\s*[A-Za-z_][A-Za-z0-9_]*:\s*generated\s*(?:#.*)?$", path.read_text(encoding="utf-8"), re.MULTILINE):
            errors.append(f"{path.relative_to(ROOT)}: unresolved generated metadata placeholder")
        version = schema_version(path)
        if version is None:
            errors.append(f"{path.relative_to(ROOT)}: missing top-level api_version")
        elif declared[name] != version:
            errors.append(
                f"specs/reference/api-registry.md: {name} version {declared[name]} "
                f"does not match {path.name} {version}"
            )

    inputs_match = re.search(r"^\*\*Schema inputs\*\*:\s*(.+)$", registry_text, re.MULTILINE)
    if not inputs_match:
        errors.append("specs/reference/api-registry.md: missing Schema inputs declaration")
    else:
        targets = {match.group(1) or match.group(2) for match in LINK_RE.finditer(inputs_match.group(1))}
        expected = {path.name for path in SCHEMAS.values()}
        if targets != expected:
            errors.append(
                "specs/reference/api-registry.md: Schema inputs must link exactly to "
                + ", ".join(sorted(expected))
            )
    return errors


def economy_body_part_costs() -> dict[str, int]:
    text = ECONOMY_IDL.read_text(encoding="utf-8")
    part_names = "|".join(VANILLA_BODY_PARTS.values())
    return {
        name: int(cost)
        for name, cost in re.findall(
            rf"- part:\s*({part_names})\s*\n\s+cost:\s*(\d+)", text
        )
    }


def economy_structure_cost_groups() -> tuple[dict[str, int], dict[str, int]]:
    text = ECONOMY_IDL.read_text(encoding="utf-8")
    core_match = re.search(
        r"^\s+structures:\s*$\n(?P<section>.*?)(?=^\s+computation:)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    optional_match = re.search(
        r"^\s+optional_structures:\s*$\n(?P<section>.*?)(?=^\s+# -+|^\s+- name: SpawnCost)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    core = {
        name: int(cost)
        for name, cost in re.findall(
            r"- type:\s*(\w+)\s*\n\s+cost:\s*(\d+)",
            core_match.group("section") if core_match else "",
        )
    }
    optional = {
        name: int(cost)
        for name, cost in re.findall(
            r"- type:\s*(\w+)\s*\n\s+cost:\s*(\d+)",
            optional_match.group("section") if optional_match else "",
        )
    }
    return core, optional


def economy_structure_costs() -> dict[str, int]:
    core, optional = economy_structure_cost_groups()
    return core | optional


def canonical_action_ranges() -> dict[str, int]:
    ranges: dict[str, int] = {}
    for line in ACTION_TABLE.read_text(encoding="utf-8").splitlines():
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) < 10:
            continue
        action = columns[1].strip("*")
        if action in CORE_ACTIONS and columns[9].isdigit():
            ranges[action] = int(columns[9])
    return ranges


def documented_body_parts(path: Path) -> dict[str, tuple[int, int]]:
    parts: dict[str, tuple[int, int]] = {}
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(
        r"\[\[body_part_types\]\]\s*\n(?P<body>.*?)(?=\n\[\[|\Z)", text, re.DOTALL
    ):
        body = match.group("body")
        name_match = re.search(r'^name\s*=\s*"([^"]+)"', body, re.MULTILINE)
        if not name_match or name_match.group(1) not in CORE_ACTIONS:
            continue
        range_match = re.search(r"^range\s*=\s*(\d+)", body, re.MULTILINE)
        cost_match = re.search(r"^cost\s*=\s*\{\s*Energy\s*=\s*(\d+)\s*\}", body, re.MULTILINE)
        if range_match and cost_match:
            parts[name_match.group(1)] = (int(range_match.group(1)), int(cost_match.group(1)))
    return parts


def documented_body_part_costs(path: Path) -> dict[str, int]:
    parts: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(
        r"\[\[body_part_types\]\]\s*\n(?P<body>.*?)(?=\n\[\[|\Z)", text, re.DOTALL
    ):
        body = match.group("body")
        name_match = re.search(r'^name\s*=\s*"([^"]+)"', body, re.MULTILINE)
        cost_match = re.search(r"^cost\s*=\s*\{\s*Energy\s*=\s*(\d+)\s*\}", body, re.MULTILINE)
        if name_match and cost_match and name_match.group(1) in VANILLA_BODY_PARTS:
            parts[name_match.group(1)] = int(cost_match.group(1))
    return parts


def documented_structure_costs(path: Path) -> dict[str, int]:
    structures: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(
        r"\[\[structure_types\]\]\s*\n(?P<body>.*?)(?=\n\[\[|\Z)", text, re.DOTALL
    ):
        body = match.group("body")
        name_match = re.search(r'^name\s*=\s*"([^"]+)"', body, re.MULTILINE)
        cost_match = re.search(r"^cost\s*=\s*\{\s*Energy\s*=\s*(\d+)\s*\}", body, re.MULTILINE)
        if name_match and cost_match:
            structures[name_match.group(1)] = int(cost_match.group(1))
    return structures


def check_gameplay_constants() -> list[str]:
    errors: list[str] = []
    costs = economy_body_part_costs()
    structure_costs = economy_structure_costs()
    core_structure_costs, optional_structure_costs = economy_structure_cost_groups()
    ranges = canonical_action_ranges()
    expected_names = set(CORE_ACTIONS)
    if set(costs) != set(VANILLA_BODY_PARTS.values()):
        errors.append("specs/reference/economy.idl.yaml: missing Vanilla body-part costs")
    if set(ranges) != expected_names:
        errors.append("specs/reference/special-attack-table.md: missing core action ranges")
    if not structure_costs:
        errors.append("specs/reference/economy.idl.yaml: missing structure cost schedule")
    if len(core_structure_costs) != 13:
        errors.append(
            "specs/reference/economy.idl.yaml: core structure cost schedule must contain 13 entries"
        )
    if len(optional_structure_costs) != 4:
        errors.append(
            "specs/reference/economy.idl.yaml: optional structure cost schedule must contain 4 entries"
        )
    if set(core_structure_costs) & set(optional_structure_costs):
        errors.append(
            "specs/reference/economy.idl.yaml: core and optional structure cost schedules overlap"
        )

    registry_text = REGISTRY.read_text(encoding="utf-8")
    for action, economy_name in VANILLA_BODY_PARTS.items():
        expected_cost = costs.get(economy_name)
        if expected_cost is not None and not re.search(
            rf"\b{economy_name}={expected_cost}\b", registry_text
        ):
            errors.append(
                f"specs/reference/api-registry.md: SpawnCost for {economy_name} "
                f"does not match economy.idl.yaml ({expected_cost})"
            )

    for path in BODY_PART_DOCS:
        documented_costs = documented_body_part_costs(path)
        for part, economy_name in VANILLA_BODY_PARTS.items():
            expected_cost = costs.get(economy_name)
            actual_cost = documented_costs.get(part)
            if actual_cost is None:
                errors.append(f"{path.relative_to(ROOT)}: missing {part} body-part cost")
            elif actual_cost != expected_cost:
                errors.append(
                    f"{path.relative_to(ROOT)}: {part} cost {actual_cost} does not match "
                    f"economy.idl.yaml ({expected_cost})"
                )
        documented = documented_body_parts(path)
        for action, economy_name in CORE_ACTIONS.items():
            expected_range = ranges.get(action)
            expected_cost = costs.get(economy_name)
            actual = documented.get(action)
            if actual is None:
                errors.append(f"{path.relative_to(ROOT)}: missing {action} body-part definition")
            elif actual != (expected_range, expected_cost):
                errors.append(
                    f"{path.relative_to(ROOT)}: {action} range/cost {actual} does not match "
                    f"canonical ({expected_range}, {expected_cost})"
                )
        documented_structures = documented_structure_costs(path)
        for structure, expected_cost in structure_costs.items():
            actual_cost = documented_structures.get(structure)
            if actual_cost is None and path.name != "world-rules.md":
                continue
            if actual_cost != expected_cost:
                errors.append(
                    f"{path.relative_to(ROOT)}: {structure} cost {actual_cost} does not match "
                    f"economy.idl.yaml ({expected_cost})"
                )

    registry_text = REGISTRY.read_text(encoding="utf-8")
    for structure, expected_cost in structure_costs.items():
        if not re.search(rf"\b{structure}={expected_cost}\b", registry_text):
            errors.append(
                f"specs/reference/api-registry.md: BuildCost for {structure} "
                f"does not match economy.idl.yaml ({expected_cost})"
            )
    return errors


def check_economy_upkeep_defaults() -> list[str]:
    errors: list[str] = []
    ledger_text = RESOURCE_LEDGER.read_text(encoding="utf-8")
    balance_text = ECONOMY_BALANCE.read_text(encoding="utf-8")
    gameplay_text = GAMEPLAY_DESIGN.read_text(encoding="utf-8")

    defaults_match = re.search(
        r"base_upkeep\s*=\s*(\d+) \(Standard\) / (\d+) \(Vanilla\) / (\d+) \(Tutorial\)\s+"
        r"room_soft_cap\s*=\s*(\d+) \(Standard\) / (\d+) \(Vanilla\) / (\d+) \(Tutorial\)",
        ledger_text,
    )
    if defaults_match is None:
        return ["specs/core/resource-ledger.md: missing canonical Empire Upkeep defaults"]

    values = tuple(int(value) for value in defaults_match.groups())
    expected_rows = {
        "base_upkeep": values[:3],
        "room_soft_cap": values[3:],
    }
    for field, expected in expected_rows.items():
        row_match = re.search(
            rf"^\| `{field}` \| (\d+) \| (\d+) \| (\d+) \|$",
            balance_text,
            re.MULTILINE,
        )
        if row_match is None:
            errors.append(f"design/economy-balance-sheet.md: missing {field} defaults row")
            continue
        actual = tuple(int(value) for value in row_match.groups())
        if actual != expected:
            errors.append(
                f"design/economy-balance-sheet.md: {field} {actual} does not match "
                f"resource-ledger.md {expected}"
            )

    standard_base, standard_cap = values[0], values[3]
    for rooms in (1, 5, 20, 50):
        expected_cost = standard_base * rooms * (standard_cap + rooms) // standard_cap
        row_match = re.search(
            rf"^\| {rooms} \| ([\d,]+) \| [\d,]+ \|",
            balance_text,
            re.MULTILINE,
        )
        if row_match is None:
            errors.append(
                f"design/economy-balance-sheet.md: missing {rooms}-room maintenance row"
            )
            continue
        actual_cost = int(row_match.group(1).replace(",", ""))
        if actual_cost != expected_cost:
            errors.append(
                f"design/economy-balance-sheet.md: {rooms}-room maintenance {actual_cost} "
                f"does not match canonical formula ({expected_cost})"
            )

    gameplay_match = re.search(
        r"Standard 默认 `base_upkeep=(\d+), room_soft_cap=(\d+)`",
        gameplay_text,
    )
    expected_gameplay = (standard_base, standard_cap)
    if gameplay_match is None:
        errors.append("design/gameplay.md: missing Standard Empire Upkeep defaults")
    elif tuple(int(value) for value in gameplay_match.groups()) != expected_gameplay:
        errors.append(
            "design/gameplay.md: Empire Upkeep defaults do not match resource-ledger.md"
        )

    return errors


REPAIR_CONFIG_DEFAULTS = {
    "repair_hp_per_work_part": 5,
    "repair_energy_per_hp": 1,
}


def documented_repair_config(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    combat_match = re.search(
        r"^\[combat\]\s*\n(?P<body>.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if combat_match is None:
        return {}
    body = combat_match.group("body")
    values: dict[str, int] = {}
    for key in REPAIR_CONFIG_DEFAULTS:
        match = re.search(rf"^{re.escape(key)}\s*=\s*(\d+)\b", body, re.MULTILINE)
        if match is not None:
            values[key] = int(match.group(1))
    return values


def check_repair_config_defaults(
    paths: tuple[Path, ...] = (GAMEPLAY_DESIGN, WORLD_RULES),
) -> list[str]:
    errors: list[str] = []
    for path in paths:
        actual = documented_repair_config(path)
        if actual != REPAIR_CONFIG_DEFAULTS:
            relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            errors.append(
                f"{relative}: [combat] Repair defaults {actual} do not match "
                f"{REPAIR_CONFIG_DEFAULTS}"
            )
    if paths == (GAMEPLAY_DESIGN, WORLD_RULES):
        try:
            game = sync_api_registry.parse_yaml_subset(SCHEMAS["game_api"])
            combat = game["type_registry"]["scalar_types"]["CombatConfig"]["fields"]
            tools = game["mcp_tools"]["tools"]
            world_config = next(tool for tool in tools if tool["name"] == "swarm_get_world_config")
        except (KeyError, StopIteration, TypeError, sync_api_registry.YamlSubsetError) as exc:
            errors.append(
                f"specs/reference/game_api.idl.yaml: unable to validate CombatConfig: {exc}"
            )
        else:
            for key in REPAIR_CONFIG_DEFAULTS:
                if key not in combat:
                    errors.append(
                        f"specs/reference/game_api.idl.yaml: CombatConfig missing {key}"
                    )
            if world_config["output_schema"].get("combat") != "CombatConfig":
                errors.append(
                    "specs/reference/game_api.idl.yaml: swarm_get_world_config missing CombatConfig"
                )
    return errors


def check_snapshot_contract_alignment() -> list[str]:
    errors: list[str] = []
    try:
        game = sync_api_registry.parse_yaml_subset(SCHEMAS["game_api"])
        tools = game["mcp_tools"]["tools"]
        snapshot = next(tool for tool in tools if tool["name"] == "swarm_get_snapshot")
        fields = list(snapshot["output_schema"])
    except (KeyError, StopIteration, TypeError, sync_api_registry.YamlSubsetError) as exc:
        return [f"specs/reference/game_api.idl.yaml: unable to validate snapshot schema: {exc}"]

    expected_fields = [
        "tick",
        "player_id",
        "actor_context",
        "entities",
        "terrain",
        "resources",
        "events",
        "truncated",
        "over_budget",
        "messages",
        "omitted_categories",
        "omitted_messages",
    ]
    if fields != expected_fields:
        errors.append(
            "specs/reference/game_api.idl.yaml: swarm_get_snapshot fields "
            f"{fields} do not match canonical order {expected_fields}"
        )

    snapshot_text = SNAPSHOT_CONTRACT.read_text(encoding="utf-8")
    incremental_text = INCREMENTAL_SNAPSHOT.read_text(encoding="utf-8")
    visibility_text = VISIBILITY_CONTRACT.read_text(encoding="utf-8")
    engine_text = ENGINE_DESIGN.read_text(encoding="utf-8")
    tick_text = (ROOT / "specs/core/tick-protocol.md").read_text(encoding="utf-8")
    if "last_modified_tick DESC" in snapshot_text:
        errors.append(
            "specs/core/snapshot-contract.md: player-visible truncation must not use last_modified_tick"
        )
    for required in ("stable_item_key", "event_sequence", "over_budget=true"):
        if required not in snapshot_text:
            errors.append(f"specs/core/snapshot-contract.md: missing {required} contract")
    if "分桶、hash" in snapshot_text or "minimal snapshot hash" in snapshot_text:
        errors.append(
            "specs/core/snapshot-contract.md: minimal player snapshot must not publish a generic hash"
        )
    if (
        "last_modified_tick" not in incremental_text
        or "不影响玩家可见 snapshot" not in incremental_text
        or "(anchor_entity_id, kind_tag, local_key)" not in incremental_text
    ):
        errors.append(
            "specs/core/incremental-snapshot.md: missing canonical snapshot ordering/storage boundary"
        )
    for required in ("post-commit", "snapshot N+1", "broadcast_visibility"):
        if required not in visibility_text:
            errors.append(f"specs/security/visibility.md: missing {required} delta boundary")
    for forbidden in ("entity_id 字典序", "over_budget_rejected"):
        if forbidden in engine_text:
            errors.append(f"design/engine.md: stale snapshot contract {forbidden}")
    for required in (
        "actor_context: payload.actor_context",
        "events: payload.events",
        "messages: payload.messages",
        "omitted_messages: payload.omitted_categories.messages",
    ):
        if required not in tick_text:
            errors.append(f"specs/core/tick-protocol.md: missing snapshot field {required}")
    if "snapshot_len: payload.serialized_size" in tick_text:
        errors.append("specs/core/tick-protocol.md: snapshot_len is not a canonical wire field")
    return errors


COMMAND_HANDLER_OWNERSHIP = {
    "Move": "S01",
    "Harvest": "S01",
    "ClaimController": "S02",
    "UpgradeController": "S02",
    "Build": "S03",
    "Repair": "S03",
    "Recycle": "S04",
    "Transfer": "S05",
    "Withdraw": "S05",
    "TransferToGlobal": "S05",
    "TransferFromGlobal": "S05",
    "AlliedTransfer": "S05",
    "Spawn": "S06",
    "Action": "A01",
}


def check_command_handler_ownership() -> list[str]:
    errors: list[str] = []
    try:
        game = sync_api_registry.parse_yaml_subset(SCHEMAS["game_api"])
        variants = {variant["name"] for variant in game["command_action"]["variants"]}
    except (KeyError, TypeError, sync_api_registry.YamlSubsetError) as exc:
        return [f"specs/reference/game_api.idl.yaml: unable to validate command ownership: {exc}"]

    expected = set(COMMAND_HANDLER_OWNERSHIP)
    if variants != expected:
        errors.append(
            "specs/reference/game_api.idl.yaml: CommandAction variants "
            f"{sorted(variants)} do not match ownership map {sorted(expected)}"
        )

    manifest_path = ROOT / "specs/core/phase2b-system-manifest.md"
    manifest = manifest_path.read_text(encoding="utf-8")
    match = re.search(r"match cmd\.kind:(?P<body>.*?)└", manifest, re.DOTALL)
    if match is None:
        return errors + ["specs/core/phase2b-system-manifest.md: missing match cmd.kind schedule"]
    schedule = match.group("body")
    for variant in sorted(expected):
        occurrences = len(re.findall(rf"(?<!\w){re.escape(variant)}(?!\w)", schedule))
        if occurrences != 1:
            errors.append(
                "specs/core/phase2b-system-manifest.md: schedule must contain "
                f"{variant} exactly once, found {occurrences}"
            )

    for path in (GAMEPLAY_DESIGN, WORLD_RULES, TECH_CHOICES):
        if "add_systems(Update" in path.read_text(encoding="utf-8"):
            errors.append(
                f"{path.relative_to(ROOT)}: gameplay config must not dynamically register schedule nodes"
            )
    for required in (
        "system_manifest_hash = Blake3(",
        "A01 registry/handler identity 进入 `world_action_manifest_hash`",
        "A01 不增加 system entry",
    ):
        if required not in manifest:
            errors.append(
                f"specs/core/phase2b-system-manifest.md: missing A01/hash boundary {required}"
            )
    world_rules = WORLD_RULES.read_text(encoding="utf-8")
    for required in (
        "固定 S01-S29 schedule slots，以及独立的 A01 ActionRegistry dispatch hook",
        "S01-S29 进入 `system_manifest_hash`；A01/custom handlers 进入 `world_action_manifest_hash`",
    ):
        if required not in world_rules:
            errors.append(f"specs/core/world-rules.md: missing A01 fixed-hook boundary {required}")
    tick_protocol = (ROOT / "specs/core/tick-protocol.md").read_text(encoding="utf-8")
    if "plugin_schedule_graph_hash" in tick_protocol:
        errors.append(
            "specs/core/tick-protocol.md: plugin_schedule_graph_hash must not exist"
        )
    for required in ("system_manifest_hash", "world_action_manifest_hash", "mods_lock_hash"):
        if required not in tick_protocol:
            errors.append(f"specs/core/tick-protocol.md: replay identity missing {required}")
    return errors


def json_code_blocks(text: str) -> list[str]:
    return re.findall(r"^```json\s*\n(.*?)\n```$", text, re.MULTILINE | re.DOTALL)


def check_command_contract_examples(
    interface_path: Path = INTERFACE_DESIGN,
    gameplay_path: Path = GAMEPLAY_DESIGN,
    world_rules_path: Path = WORLD_RULES,
    commands_path: Path = COMMANDS_REFERENCE,
    command_validation_path: Path = COMMAND_VALIDATION,
) -> list[str]:
    errors: list[str] = []

    interface = interface_path.read_text(encoding="utf-8")
    if "CommandAction 必须包含 actor identity" in interface:
        errors.append(
            "design/interface.md: CommandAction must not own actor identity or CommandIntent envelope fields"
        )
    for required in (
        "`CommandIntent` envelope 包含 `sequence`、required `idempotency_key`、optional `client_trace_id`",
        "player identity、tick、source 与 auth context 由服务端注入 `RawCommand`",
        "closed `ActionPayload` concrete schema",
        "enabled signed-plugin World Action Manifest",
    ):
        if required not in interface:
            errors.append(f"design/interface.md: missing command ownership contract {required}")

    commands = commands_path.read_text(encoding="utf-8")
    command_list = commands.partition("## Action Dispatch")[0]
    command_blocks = json_code_blocks(command_list)
    documented_actions: set[str] = set()
    for index, block in enumerate(command_blocks, start=1):
        try:
            example = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"specs/reference/commands.md: JSON example {index} is invalid: {exc.msg}")
            continue
        if not isinstance(example, dict) or not isinstance(example.get("sequence"), int):
            errors.append(f"specs/reference/commands.md: example {index} missing integer sequence")
        key = example.get("idempotency_key") if isinstance(example, dict) else None
        if not isinstance(key, str) or not key:
            errors.append(f"specs/reference/commands.md: example {index} missing idempotency_key")
        if not isinstance(example, dict) or not isinstance(example.get("action"), dict):
            errors.append(f"specs/reference/commands.md: example {index} missing action object")
            continue
        action_type = example["action"].get("type")
        if isinstance(action_type, str):
            documented_actions.add(action_type)
    expected_reference_actions = set(COMMAND_HANDLER_OWNERSHIP) - {"Action"}
    if documented_actions != expected_reference_actions:
        errors.append(
            "specs/reference/commands.md: command examples "
            f"{sorted(documented_actions)} do not match {sorted(expected_reference_actions)}"
        )
    for required in (
        '{ "type": "Attack", "object_id": 1001, "target_id": 5005 }',
        "payload: ActionPayload::Attack { target_id: 5005 }",
    ):
        if required not in commands:
            errors.append(f"specs/reference/commands.md: missing typed Action dispatch example {required}")

    command_validation = command_validation_path.read_text(encoding="utf-8")
    special_section = command_validation.partition("### 10.5 Action 校验")[2]
    expected_special_actions = {
        "Debilitate",
        "Disrupt",
        "Drain",
        "Fabricate",
        "Fortify",
        "Hack",
        "Leech",
        "Overload",
    }
    found_special_actions: set[str] = set()
    for index, block in enumerate(json_code_blocks(special_section), start=1):
        try:
            example = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(
                f"specs/core/command-validation.md: special-action example {index} is invalid JSON: {exc.msg}"
            )
            continue
        action = example.get("action") if isinstance(example, dict) else None
        if not isinstance(example, dict) or not isinstance(example.get("sequence"), int):
            errors.append(
                f"specs/core/command-validation.md: special-action example {index} missing envelope sequence"
            )
        key = example.get("idempotency_key") if isinstance(example, dict) else None
        if not isinstance(key, str) or not key:
            errors.append(
                f"specs/core/command-validation.md: special-action example {index} missing idempotency_key"
            )
        if not isinstance(action, dict):
            errors.append(
                f"specs/core/command-validation.md: special-action example {index} missing action object"
            )
            continue
        if "sequence" in action or "idempotency_key" in action:
            errors.append(
                f"specs/core/command-validation.md: special-action example {index} nests envelope fields in action"
            )
        action_type = action.get("type")
        if isinstance(action_type, str):
            found_special_actions.add(action_type)
    if found_special_actions != expected_special_actions:
        errors.append(
            "specs/core/command-validation.md: special-action examples "
            f"{sorted(found_special_actions)} do not match {sorted(expected_special_actions)}"
        )

    gameplay = gameplay_path.read_text(encoding="utf-8")
    gameplay_custom_action = re.search(
        r"^\[\[actions\]\]\s*\n(?P<body>.*?)(?=^```)",
        gameplay,
        re.MULTILINE | re.DOTALL,
    )
    required_manifest_fields = ("body_parts = ", "handler = ", "payload_schema = ", "config_schema = ")
    gameplay_manifest = gameplay_custom_action.group("body") if gameplay_custom_action else ""
    for required in required_manifest_fields:
        if required not in gameplay_manifest:
            errors.append(f"design/gameplay.md: signed action manifest missing {required.strip()}")
    if "| `body_parts` | string[] | ✅ |" not in gameplay:
        errors.append("design/gameplay.md: action manifest field table missing required body_parts")
    for forbidden in (
        "绑定的 CommandAction",
        "[[custom_actions]]",
        "world.toml 中声明 [[custom_actions]]",
        "特殊效果可通过 world.toml 定义和扩展",
        "自定义特殊攻击只需 TOML 配置",
    ):
        if forbidden in gameplay:
            errors.append(f"design/gameplay.md: stale action/plugin trust contract {forbidden}")

    world_rules = world_rules_path.read_text(encoding="utf-8")
    world_custom_action = re.search(
        r"^\[\[actions\]\]\s*\n(?P<body>.*?)(?=^```)",
        world_rules,
        re.MULTILINE | re.DOTALL,
    )
    world_manifest = world_custom_action.group("body") if world_custom_action else ""
    for required in required_manifest_fields:
        if required not in world_manifest:
            errors.append(f"specs/core/world-rules.md: signed action manifest missing {required.strip()}")
    for forbidden in ("world.toml [[custom_actions]]", "[[custom_actions]]", "[[special_effects]]"):
        if forbidden in world_rules:
            errors.append(f"specs/core/world-rules.md: world config must not declare {forbidden}")

    return errors


def check_action_payload_contract(
    game_idl_path: Path = SCHEMAS["game_api"],
    registry_path: Path = REGISTRY,
    gameplay_idl_path: Path = GAMEPLAY_IDL,
) -> list[str]:
    errors: list[str] = []
    try:
        game = sync_api_registry.parse_yaml_subset(game_idl_path)
        action_payload = game["type_registry"]["scalar_types"]["ActionPayload"]
        action_variant = next(
            variant for variant in game["command_action"]["variants"] if variant["name"] == "Action"
        )
        overload = next(
            action
            for action in game["command_action"]["action_registry"]["vanilla_actions"]["actions"]
            if action["type"] == "Overload"
        )
    except (KeyError, StopIteration, TypeError, sync_api_registry.YamlSubsetError) as exc:
        return [f"specs/reference/game_api.idl.yaml: unable to validate ActionPayload: {exc}"]

    parameter_types = {
        parameter["name"]: parameter["type"] for parameter in action_variant["parameters"]
    }
    expected_parameter_types = {
        "action_type": "string",
        "object_id": "ObjectId",
        "payload": "ActionPayload",
    }
    if parameter_types != expected_parameter_types:
        errors.append(
            "specs/reference/game_api.idl.yaml: Action parameters "
            f"{parameter_types} do not match {expected_parameter_types}"
        )
    for key, expected in (
        ("type", "discriminated_payload"),
        ("selected_by", "CommandAction::Action.action_type"),
        ("wire_discriminator", "type"),
        ("flatten_wire", True),
        ("additional_properties", False),
    ):
        if action_payload.get(key) != expected:
            errors.append(
                f"specs/reference/game_api.idl.yaml: ActionPayload {key} must be {expected!r}"
            )
    schema_sources = action_payload.get("schema_sources", {})
    if schema_sources.get("custom") != "enabled signed-plugin WorldActionManifest.actions[].payload_schema":
        errors.append(
            "specs/reference/game_api.idl.yaml: custom ActionPayload schema source must be the enabled signed-plugin manifest payload_schema"
        )
    if "IDL-generated Swarm codec" not in str(action_payload.get("codec", "")):
        errors.append(
            "specs/reference/game_api.idl.yaml: ActionPayload must use the IDL-generated Swarm codec"
        )
    overload_parameters = {
        parameter["name"]: parameter["type"] for parameter in overload["parameters"]
    }
    if overload_parameters.get("target_id") != "PlayerId":
        errors.append("specs/reference/game_api.idl.yaml: Overload target_id must be PlayerId")

    registry = registry_path.read_text(encoding="utf-8")
    gameplay_idl = gameplay_idl_path.read_text(encoding="utf-8")
    for path, text in ((registry_path, registry), (gameplay_idl_path, gameplay_idl)):
        try:
            display_path = path.relative_to(ROOT)
        except ValueError:
            display_path = path.name
        for forbidden in (
            "Map<String, JsonValue>",
            "target_id?: EntityId, payload: ActionPayload",
            "target_id: ObjectId?, payload:",
            "world.toml [[custom_actions]]",
        ):
            if forbidden in text:
                errors.append(f"{display_path}: stale ActionPayload contract {forbidden}")
    for required in (
        "ActionPayload<action_type>",
        "IDL-generated Swarm codec",
        "enabled signed-plugin World Action Manifest",
    ):
        if required not in gameplay_idl:
            errors.append(f"specs/gameplay/api-idl.md: missing ActionPayload contract {required}")
    return errors


def check_special_attack_config_alignment() -> list[str]:
    errors: list[str] = []
    try:
        game = sync_api_registry.parse_yaml_subset(SCHEMAS["game_api"])
        scalar_types = game["type_registry"]["scalar_types"]
        tools = game["mcp_tools"]["tools"]
        actions = game["command_action"]["action_registry"]["vanilla_actions"]["actions"]
        world_config = next(tool for tool in tools if tool["name"] == "swarm_get_world_config")
        drone = next(tool for tool in tools if tool["name"] == "swarm_get_drone")
        efficiency = next(tool for tool in tools if tool["name"] == "swarm_get_drone_efficiency")
    except (KeyError, StopIteration, TypeError, sync_api_registry.YamlSubsetError) as exc:
        return [f"specs/reference/game_api.idl.yaml: unable to validate special config: {exc}"]

    action_config_types = (
        "HackActionConfig",
        "DrainActionConfig",
        "OverloadActionConfig",
        "DebilitateActionConfig",
        "DisruptActionConfig",
        "FortifyActionConfig",
        "LeechActionConfig",
        "FabricateActionConfig",
    )
    for type_name in (*action_config_types, "SpecialAttacksConfig"):
        if type_name not in scalar_types:
            errors.append(f"specs/reference/game_api.idl.yaml: missing {type_name}")
    required_action_fields = {
        "HackActionConfig": {"enabled", "body_parts", "player_global_cooldown", "range", "channel_time"},
        "DrainActionConfig": {"enabled", "body_parts", "source_drone_cooldown", "range", "channel_time"},
        "OverloadActionConfig": {"enabled", "body_parts", "source_drone_cooldown", "target_player_global_cooldown", "range", "channel_time"},
        "DebilitateActionConfig": {"enabled", "body_parts", "resistance_multiplier_bps", "duration", "channel_time"},
        "DisruptActionConfig": {"enabled", "body_parts", "interrupt_channel", "channel_time"},
        "FortifyActionConfig": {"enabled", "body_parts", "damage_type", "resistance", "source_drone_cooldown", "target_recipient_cooldown", "duration", "channel_time"},
        "LeechActionConfig": {"enabled", "body_parts", "base_damage", "heal_from_actual_hp_damage_bps", "channel_time"},
        "FabricateActionConfig": {"enabled", "body_parts", "source_drone_cooldown", "allowed_output_structures", "canonical_default", "channel_time"},
    }
    for type_name, required_fields in required_action_fields.items():
        actual_fields = set(scalar_types.get(type_name, {}).get("fields", {}))
        missing = required_fields - actual_fields
        if missing:
            errors.append(
                f"specs/reference/game_api.idl.yaml: {type_name} missing {sorted(missing)}"
            )
    hack_channel = scalar_types.get("HackActionConfig", {}).get("fields", {}).get("channel_time", "")
    if "Vanilla 5 ticks" not in hack_channel:
        errors.append(
            "specs/reference/game_api.idl.yaml: HackActionConfig channel_time must be Vanilla 5 ticks"
        )
    special_fields = scalar_types.get("SpecialAttacksConfig", {}).get("fields", {})
    expected_action_fields = {name.removesuffix("ActionConfig").lower() for name in action_config_types}
    if not expected_action_fields.issubset(special_fields):
        errors.append(
            "specs/reference/game_api.idl.yaml: SpecialAttacksConfig missing strict action fields"
        )
    if world_config["output_schema"].get("special_attacks") != "SpecialAttacksConfig":
        errors.append(
            "specs/reference/game_api.idl.yaml: swarm_get_world_config missing SpecialAttacksConfig"
        )
    if drone.get("visibility_filter") != "owner_or_visible_with_owner_fields":
        errors.append(
            "specs/reference/game_api.idl.yaml: swarm_get_drone missing owner-field visibility filter"
        )
    field_visibility = drone.get("field_visibility", "")
    for field in ("code_hash", "fuel_used"):
        if field not in field_visibility or "owner-only" not in field_visibility:
            errors.append(
                f"specs/reference/game_api.idl.yaml: swarm_get_drone {field} is not owner-only"
            )
    if efficiency.get("visibility_filter") != "owner":
        errors.append(
            "specs/reference/game_api.idl.yaml: swarm_get_drone_efficiency must be owner-only"
        )
    if efficiency["output_schema"].get("efficiency") != "EfficiencyBps":
        errors.append(
            "specs/reference/game_api.idl.yaml: swarm_get_drone_efficiency must use EfficiencyBps"
        )
    debilitate = next((action for action in actions if action.get("type") == "Debilitate"), None)
    debilitate_params = {
        parameter.get("name") for parameter in (debilitate or {}).get("parameters", [])
    }
    if not {"target_id", "damage_type"}.issubset(debilitate_params):
        errors.append(
            "specs/reference/game_api.idl.yaml: Debilitate wire requires target_id and damage_type"
        )

    attack_table = ACTION_TABLE.read_text(encoding="utf-8")
    if "target-player-global" not in attack_table:
        errors.append(
            "specs/reference/special-attack-table.md: missing Overload target-player-global cooldown"
        )
    interface = INTERFACE_DESIGN.read_text(encoding="utf-8")
    for field in ("code_hash", "fuel_used"):
        if field not in interface:
            errors.append(f"design/interface.md: missing owner-only {field} rule")
    world_rules = WORLD_RULES.read_text(encoding="utf-8")
    for forbidden in (
        "mut flags: Query",
        "register systems writing ECS flag",
        "手动控制追加",
        "resource_mut::<BodyPartRegistry>",
        "resource_mut::<ActionRegistry>",
        "通过 Bevy ECS systems",
    ):
        if forbidden in world_rules:
            errors.append(f"specs/core/world-rules.md: stale direct-mutation hook {forbidden}")
    for required in (
        "repair_hp_per_work_part == 0",
        "repair_energy_per_hp == 0",
        "只读 HookSnapshot，写 typed intent/buffer",
    ):
        if required not in world_rules:
            errors.append(f"specs/core/world-rules.md: missing fixed-hook validation {required}")
    phase = (ROOT / "specs/core/phase2b-system-manifest.md").read_text(encoding="utf-8")
    if "Entity.diligence" in phase or "apply diligence modifier" in phase:
        errors.append(
            "specs/core/phase2b-system-manifest.md: Debilitate must modify resistance vulnerability"
        )
    if "mitigated_damage × damage_multiplier" not in phase:
        errors.append(
            "specs/core/phase2b-system-manifest.md: Leech settlement missing damage_multiplier"
        )
    gameplay = GAMEPLAY_DESIGN.read_text(encoding="utf-8")
    for forbidden in ("future drone diligence query", "Plugin 注册 ECS system"):
        if forbidden in gameplay:
            errors.append(f"design/gameplay.md: stale target-state marker {forbidden}")
    for forbidden in (
        'name = "debilitate"\ndescription = "给目标附加易伤状态——指定伤害类型抗性×2"\nhandler = "debilitate"\ntarget = "enemy_any"\nduration = 50\nresistance = "Kinetic"',
        "Drain/Hack/Debilitate",
        'name = "leech"\ndescription = "吸血——造成伤害的 50% 治疗自身"\nhandler = "leech"\ntarget = "enemy_any"\nduration = 0\nresistance = "Corrosive"',
    ):
        if forbidden in gameplay:
            errors.append(f"design/gameplay.md: stale special-effect example {forbidden}")
    for path in (ENGINE_DESIGN, TECH_CHOICES):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("完全访问 ECS", "直接注册 system"):
            if forbidden in text:
                errors.append(
                    f"{path.relative_to(ROOT)}: stale plugin capability {forbidden}"
                )
    idl_text = SCHEMAS["game_api"].read_text(encoding="utf-8")
    if "world.toml [[action_registry]]" in idl_text or "world.toml [[custom_actions]]" in idl_text:
        errors.append(
            "specs/reference/game_api.idl.yaml: mod actions must come from enabled signed-plugin manifests"
        )
    gameplay_idl = (ROOT / "specs/gameplay/api-idl.md").read_text(encoding="utf-8")
    if "vanilla special attack 由默认 `[[custom_actions]]`" in gameplay_idl:
        errors.append(
            "specs/gameplay/api-idl.md: vanilla special actions must not load from custom_actions"
        )
    command_validation = (ROOT / "specs/core/command-validation.md").read_text(encoding="utf-8")
    if "仅含 sequence + action 两个字段" in command_validation:
        errors.append(
            "specs/core/command-validation.md: stale CommandIntent shape"
        )
    world_rules = WORLD_RULES.read_text(encoding="utf-8")
    if "`effect_handler` | string" in world_rules:
        errors.append("specs/core/world-rules.md: stale custom action field effect_handler")
    custom_action_match = re.search(
        r"^\[\[actions\]\]\s*\n(?P<body>.*?)(?=^```)",
        world_rules,
        re.MULTILINE | re.DOTALL,
    )
    action_manifest = custom_action_match.group("body") if custom_action_match else ""
    for required in ('description = ', 'handler = ', 'payload_schema = ', 'config_schema = '):
        if required not in action_manifest:
            errors.append(f"specs/core/world-rules.md: signed action manifest missing {required.strip()}")
    economy_text = SCHEMAS["economy"].read_text(encoding="utf-8")
    if "hunger (-50% diligence)" in economy_text:
        errors.append(
            "specs/reference/economy.idl.yaml: upkeep penalty must use efficiency, not PvE diligence"
        )
    return errors


def check_registry_sync() -> list[str]:
    try:
        changed, message = sync_api_registry.synchronize(
            registry=REGISTRY,
            game_idl=SCHEMAS["game_api"],
            auth_idl=SCHEMAS["auth_api"],
            economy_idl=SCHEMAS["economy"],
            engine_idl=None,
            check=True,
        )
    except (OSError, ValueError, sync_api_registry.YamlSubsetError, json.JSONDecodeError) as exc:
        return [f"specs/reference/api-registry.md: generated Registry metadata validation failed: {exc}"]
    if not changed:
        return []
    return ["specs/reference/api-registry.md: generated Registry metadata is stale; run scripts/sync_api_registry.py"]


def check_mcp_tool_count_reference() -> list[str]:
    try:
        metadata = sync_api_registry.collect_metadata(
            SCHEMAS["game_api"],
            SCHEMAS["auth_api"],
            SCHEMAS["economy"],
        )
    except (OSError, ValueError, sync_api_registry.YamlSubsetError, json.JSONDecodeError) as exc:
        return [f"specs/reference/mcp-tools.md: unable to validate Game MCP counts: {exc}"]

    text = MCP_TOOLS_REFERENCE.read_text(encoding="utf-8")
    match = MCP_TOOL_COUNT_RE.search(text)
    if match is None:
        return ["specs/reference/mcp-tools.md: missing canonical Game MCP subtotal"]

    actual = tuple(int(value) for value in match.groups())
    expected = (
        metadata.game_tools_all_declared,
        metadata.game_tools_active,
        metadata.game_tools_gated,
    )
    if actual == expected:
        return []
    return [
        "specs/reference/mcp-tools.md: Game MCP subtotal "
        f"{actual[0]}/{actual[1]}/{actual[2]} does not match IDL "
        f"{expected[0]}/{expected[1]}/{expected[2]}"
    ]


def main() -> int:
    markdown_files = sorted(path for path in ROOT.rglob("*.md") if not is_archive_path(path))
    inputs = markdown_files + list(SCHEMAS.values()) + [ECONOMY_IDL, ACTION_TABLE, *BODY_PART_DOCS]
    errors = check_input_paths(inputs)
    if not errors:
        errors.extend(check_links(markdown_files))
        errors.extend(check_mechanical_integrity(markdown_files))
        errors.extend(check_registry_metadata())
        errors.extend(check_registry_sync())
        errors.extend(check_mcp_tool_count_reference())
        errors.extend(check_gameplay_constants())
        errors.extend(check_economy_upkeep_defaults())
        errors.extend(check_repair_config_defaults())
        errors.extend(check_snapshot_contract_alignment())
    errors.extend(check_special_attack_config_alignment())
    errors.extend(check_command_handler_ownership())
    errors.extend(check_command_contract_examples())
    errors.extend(check_action_payload_contract())
    if errors:
        print(f"docs integrity check failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"docs integrity check passed: {len(markdown_files)} active Markdown files; "
        f"{len(SCHEMAS)} schema versions, {len(VANILLA_BODY_PARTS)} body-part costs, "
        f"and {len(CORE_ACTIONS)} core action profiles verified; "
        f"{len(economy_structure_costs())} structure costs verified; reviews/ excluded"
    )
    return 0


def check_mechanical_integrity(markdown_files: list[Path]) -> list[str]:
    errors: list[str] = []
    stale_ref_re = re.compile(r"specs/(core|security)/\d{2}")

    for path in markdown_files:
        relative = path.relative_to(ROOT)
        content = path.read_text(encoding="utf-8")

        lines = content.splitlines()
        fence_marker = None
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            marker_match = re.match(r"(`{3,}|~{3,})", stripped)
            if marker_match:
                marker = marker_match.group(1)
                if fence_marker is None:
                    fence_marker = (marker[0], len(marker), i)
                elif marker[0] == fence_marker[0] and len(marker) >= fence_marker[1]:
                    fence_marker = None
        if fence_marker:
            errors.append(f"{relative}:{fence_marker[2]}: unclosed fenced code block")

        stripped_content = without_code(content, strip_inline=True)
        stripped_lines = stripped_content.split("\n")
        errors.extend(check_forbidden_gap_markers(relative, stripped_lines))

        last_heading_line = -1
        # Use content to check for empty sections (including code blocks as content)
        for i, line in enumerate(lines, 1):
            stripped_line = stripped_lines[i-1]
            stale_match = stale_ref_re.search(stripped_line)
            if stale_match:
                errors.append(f"{relative}:{i}: stale numbered pseudo-path reference: {repr(stale_match.group(0))}")

            heading_match = HEADING_RE.match(stripped_line)
            if heading_match:
                if last_heading_line != -1 and last_heading_line == i - 1:
                    errors.append(f"{relative}:{last_heading_line}: immediately empty section")

                heading_text = heading_match.group(2).strip()
                if heading_text.startswith("#") or re.search(
                    r"[\(（,，—\s/]$|[\(（]\s*[\)）]$|,\s*[\)）]$|—\s*[\)）]$|[\(（]\s*,",
                    heading_text,
                ):
                    errors.append(f"{relative}:{i}: malformed or truncated heading: {repr(heading_text)}")

                last_heading_line = i
            elif line.strip():
                last_heading_line = -1

        if last_heading_line != -1:
            errors.append(f"{relative}:{last_heading_line}: immediately empty section")

    return errors


def check_forbidden_gap_markers(relative: Path, stripped_lines: list[str]) -> list[str]:
    errors: list[str] = []
    lowered_markers = [(marker, marker.lower()) for marker in FORBIDDEN_GAP_MARKERS]
    for line_number, line in enumerate(stripped_lines, 1):
        lower_line = line.lower()
        for marker, lower_marker in lowered_markers:
            if lower_marker in lower_line:
                errors.append(
                    f"{relative}:{line_number}: forbidden implementation-gap marker {marker!r}; "
                    "rephrase as target architecture, contract scope, or runtime state semantics"
                )
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
