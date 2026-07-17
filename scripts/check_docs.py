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
ECONOMY_IDL = ROOT / "specs/reference/economy.idl.yaml"
ACTION_TABLE = ROOT / "specs/reference/special-attack-table.md"
RESOURCE_LEDGER = ROOT / "specs/core/resource-ledger.md"
ECONOMY_BALANCE = ROOT / "design/economy-balance-sheet.md"
GAMEPLAY_DESIGN = ROOT / "design/gameplay.md"
BODY_PART_DOCS = [ROOT / "design/gameplay.md", ROOT / "specs/core/world-rules.md"]
CORE_ACTIONS = {
    "Attack": "ATTACK",
    "RangedAttack": "RANGED_ATTACK",
    "Heal": "HEAL",
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
    return {
        name: int(cost)
        for name, cost in re.findall(
            r"- part:\s*(ATTACK|RANGED_ATTACK|HEAL)\s*\n\s+cost:\s*(\d+)", text
        )
    }


def economy_structure_costs() -> dict[str, int]:
    text = ECONOMY_IDL.read_text(encoding="utf-8")
    section_match = re.search(
        r"^\s+structures:\s*$\n(?P<section>.*?)(?=^\s+computation:)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return {}
    return {
        name: int(cost)
        for name, cost in re.findall(
            r"- type:\s*(\w+)\s*\n\s+cost:\s*(\d+)", section_match.group("section")
        )
    }


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
    ranges = canonical_action_ranges()
    expected_names = set(CORE_ACTIONS)
    if set(costs) != set(CORE_ACTIONS.values()):
        errors.append("specs/reference/economy.idl.yaml: missing core action body-part costs")
    if set(ranges) != expected_names:
        errors.append("specs/reference/special-attack-table.md: missing core action ranges")
    if not structure_costs:
        errors.append("specs/reference/economy.idl.yaml: missing structure cost schedule")

    registry_text = REGISTRY.read_text(encoding="utf-8")
    for action, economy_name in CORE_ACTIONS.items():
        expected_cost = costs.get(economy_name)
        if expected_cost is not None and not re.search(
            rf"\b{economy_name}={expected_cost}\b", registry_text
        ):
            errors.append(
                f"specs/reference/api-registry.md: SpawnCost for {economy_name} "
                f"does not match economy.idl.yaml ({expected_cost})"
            )

    for path in BODY_PART_DOCS:
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


def main() -> int:
    markdown_files = sorted(path for path in ROOT.rglob("*.md") if not is_archive_path(path))
    inputs = markdown_files + list(SCHEMAS.values()) + [ECONOMY_IDL, ACTION_TABLE, *BODY_PART_DOCS]
    errors = check_input_paths(inputs)
    if not errors:
        errors.extend(check_links(markdown_files))
        errors.extend(check_mechanical_integrity(markdown_files))
        errors.extend(check_registry_metadata())
        errors.extend(check_registry_sync())
        errors.extend(check_gameplay_constants())
        errors.extend(check_economy_upkeep_defaults())
    if errors:
        print(f"docs integrity check failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"docs integrity check passed: {len(markdown_files)} active Markdown files; "
        f"{len(SCHEMAS)} schema versions and {len(CORE_ACTIONS)} core action profiles verified; "
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
