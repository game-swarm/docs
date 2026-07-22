#!/usr/bin/env python3
"""Tests for sync_api_registry.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check_docs
import sync_api_registry


GAME_IDL = """
api_version: "1.2.3"
command_action:
  total_variants: 2
  variants:
    - name: Move
      index: 1
    - name: Action
      index: 2
  action_registry:
    total_vanilla: 1
    vanilla_actions:
      actions:
        - type: Attack
          index: 14
rejection_reason:
  total_canonical_codes: 2
  variants:
    - code: InvalidJson
      layer: pipeline
    - code: NotOwner
      layer: validation
mcp_tools:
  total_tools: 2
  tools:
    - name: swarm_get_info
      category: Onboarding
    - name: swarm_get_snapshot
      category: Onboarding
  gated:
    - name: swarm_tournament_create
      status: rfc
host_functions:
  total_functions: 1
  functions:
    - name: host_get_terrain
      index: 1
tick_trace_envelope:
  total_fields: 2
  fields:
    - name: api_version
      type: u32
    - name: module_hash
      type: bytes
"""

AUTH_IDL = """
api_version: "2.0.0"
auth_control_plane:
  total_operations: 1
  operations:
    - operation_id: auth_register_challenge
      method: POST
      route: /auth/register/challenge
errors:
  total_canonical_codes: 1
  canonical:
    - code: InvalidCertificate
      http_status: 401
auth_trace_events:
  total_event_types: 1
  events:
    - name: auth_csr_submit
      index: 1
"""

ECONOMY_IDL = """
api_version: "0.9.0"
resource_operation:
  operations:
    - name: RecycleRefund
      category: lifecycle
    - name: BuildCost
      category: structure
"""

REGISTRY_TEMPLATE = """
# Registry

**API 版本**: `{game_version}` (game_api) / `{auth_version}` (auth_api) / `{economy_version}` (economy)
**Schema inputs**: [game_api.idl.yaml](game_api.idl.yaml), [auth_api.idl.yaml](auth_api.idl.yaml), [economy.idl.yaml](economy.idl.yaml)
**维护与校验**: [codegen.md](codegen.md)

{generated_block}

## 3. MCP Tools

> **同步要求**: 工具计数必须与 IDL YAML 一致。`scripts/sync_api_registry.py --check` 会验证本节生成的版本与计数；修改工具定义时必须在同一变更中同步 IDL、本表和相关引用。

| 口径 | Game API | Auth API | 合计 | 用途 |
|------|---------:|---------:|-----:|------|
| `all_declared` | {all_game} | {auth_tools} | {all_total} | Registry/IDL 全声明口径 |
| `active_only` | {active_game} | {auth_tools} | {active_total} | 运行时与 SDK 默认暴露口径 |
| `gated` | {gated_game} | 0 | {gated_game} | IDL 保留但不作为 active 工具暴露 |

### 3.2 Game API 工具清单 (`all_declared={all_game}`, `active_only={active_game}`, `gated={gated_game}`)
""".lstrip()


class SyncApiRegistryTests(unittest.TestCase):
    def test_check_docs_validates_repair_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = root / "valid.md"
            stale = root / "stale.md"
            valid.write_text(
                "[combat]\nrepair_hp_per_work_part = 5\nrepair_energy_per_hp = 1\n",
                encoding="utf-8",
            )
            stale.write_text(
                "[combat]\nrepair_hp_per_work_part = 5\nrepair_energy_per_hp = 0\n",
                encoding="utf-8",
            )

            self.assertEqual(check_docs.documented_repair_config(valid), {"repair_hp_per_work_part": 5, "repair_energy_per_hp": 1})
            errors = check_docs.check_repair_config_defaults((valid, stale))

        self.assertEqual(len(errors), 1)
        self.assertIn("repair_energy_per_hp", errors[0])

    def test_check_docs_validates_mcp_tool_count_reference(self) -> None:
        original_reference = check_docs.MCP_TOOLS_REFERENCE
        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "mcp-tools.md"
            reference.write_text(
                "| **Game MCP 小计** | **`all_declared=47`, `active_only=47`, `gated=0`** | source |\n",
                encoding="utf-8",
            )
            check_docs.MCP_TOOLS_REFERENCE = reference
            try:
                self.assertEqual(check_docs.check_mcp_tool_count_reference(), [])
                reference.write_text(
                    "| **Game MCP 小计** | **`all_declared=48`, `active_only=47`, `gated=1`** | source |\n",
                    encoding="utf-8",
                )
                errors = check_docs.check_mcp_tool_count_reference()
            finally:
                check_docs.MCP_TOOLS_REFERENCE = original_reference

        self.assertEqual(len(errors), 1)
        self.assertIn("48/47/1 does not match IDL 47/47/0", errors[0])

    def test_check_docs_rejects_forbidden_gap_markers(self) -> None:
        errors = check_docs.check_forbidden_gap_markers(
            Path("specs/example.md"),
            ["This feature is not implemented in the active contract."],
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("forbidden implementation-gap marker", errors[0])

    def test_check_docs_allows_runtime_state_not_yet_written(self) -> None:
        errors = check_docs.check_forbidden_gap_markers(
            Path("specs/example.md"),
            ["The object blob is not yet written until commit succeeds."],
        )

        self.assertEqual(errors, [])

    def test_check_docs_validates_command_contract_examples(self) -> None:
        reference_actions = tuple(
            action
            for action in check_docs.COMMAND_HANDLER_OWNERSHIP
            if action != "Action"
        )
        reference_examples = "\n".join(
            "```json\n"
            + json.dumps(
                {
                    "sequence": index,
                    "idempotency_key": f"{action.lower()}-{index}",
                    "action": {"type": action},
                }
            )
            + "\n```"
            for index, action in enumerate(reference_actions, start=1)
        )
        valid_files = {
            "interface.md": (
                "`CommandIntent` envelope 包含 `sequence`、required `idempotency_key`、optional "
                "`client_trace_id` 与嵌套的 `action`。player identity、tick、source 与 auth context "
                "由服务端注入 `RawCommand`。closed `ActionPayload` concrete schema 来自 "
                "enabled signed-plugin World Action Manifest。\n"
            ),
            "gameplay.md": (
                "signed Plugin package manifest\n"
                "combat/effect 引用 `ActionRegistry` action type\n"
                "```toml\n[[actions]]\nname = \"Scramble\"\nbody_parts = [\"Work\"]\n"
                "handler = \"scramble\"\npayload_schema = \"scramble.idl.yaml\"\n"
                "config_schema = \"scramble-config.toml\"\n```\n"
                "| `body_parts` | string[] | ✅ | required |\n"
            ),
            "world-rules.md": (
                "```toml\n[[actions]]\nname = \"Scramble\"\ndescription = \"test\"\n"
                "body_parts = [\"Work\"]\nhandler = \"scramble\"\n"
                "payload_schema = \"scramble.idl.yaml\"\n"
                "config_schema = \"scramble-config.toml\"\n```\n"
            ),
            "commands.md": (
                reference_examples
                + "\n## Action Dispatch\n"
                + '{ "type": "Attack", "object_id": 1001, "target_id": 5005 }\n'
                + "payload: ActionPayload::Attack { target_id: 5005 }\n"
            ),
            "command-validation.md": "### 10.5 Action 校验\n"
            + "\n".join(
                "```json\n"
                + json.dumps(
                    {
                        "sequence": index,
                        "idempotency_key": f"{action.lower()}-{index}",
                        "action": {"type": action},
                    }
                )
                + "\n```"
                for index, action in enumerate(
                    (
                        "Debilitate",
                        "Disrupt",
                        "Drain",
                        "Fabricate",
                        "Fortify",
                        "Hack",
                        "Leech",
                        "Overload",
                    ),
                    start=1,
                )
            ),
        }
        mutations = (
            (
                "interface.md",
                "`CommandIntent` envelope 包含",
                "CommandAction 必须包含 actor identity。`CommandIntent` envelope 包含",
                "must not own actor identity",
            ),
            (
                "commands.md",
                '"idempotency_key": "move-1",',
                "",
                "missing idempotency_key",
            ),
            (
                "commands.md",
                '"type": "AlliedTransfer"',
                '"type": "UnknownAction"',
                "do not match",
            ),
            (
                "command-validation.md",
                '"sequence": 1, ',
                "",
                "missing envelope sequence",
            ),
            (
                "gameplay.md",
                'body_parts = ["Work"]\n',
                "",
                "signed action manifest missing body_parts",
            ),
            (
                "world-rules.md",
                'handler = "scramble"\n',
                "",
                "signed action manifest missing handler",
            ),
            (
                "gameplay.md",
                "signed Plugin package manifest\n",
                "world.toml 中声明 [[custom_actions]]\n",
                "stale action/plugin trust contract",
            ),
        )

        def check_fixture(root: Path, files: dict[str, str]) -> list[str]:
            paths = {name: root / name for name in files}
            for name, text in files.items():
                paths[name].write_text(text, encoding="utf-8")
            return check_docs.check_command_contract_examples(
                interface_path=paths["interface.md"],
                gameplay_path=paths["gameplay.md"],
                world_rules_path=paths["world-rules.md"],
                commands_path=paths["commands.md"],
                command_validation_path=paths["command-validation.md"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(check_fixture(Path(temp_dir), valid_files), [])

        for filename, original, replacement, expected_error in mutations:
            with self.subTest(filename=filename, expected_error=expected_error):
                mutated_files = dict(valid_files)
                self.assertIn(original, mutated_files[filename])
                mutated_files[filename] = mutated_files[filename].replace(
                    original, replacement, 1
                )
                with tempfile.TemporaryDirectory() as temp_dir:
                    errors = check_fixture(Path(temp_dir), mutated_files)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    f"missing {expected_error!r} in {errors}",
                )

    def test_check_docs_validates_action_payload_contract(self) -> None:
        game_idl = """
type_registry:
  scalar_types:
    ActionPayload:
      type: discriminated_payload
      selected_by: CommandAction::Action.action_type
      wire_discriminator: type
      flatten_wire: true
      additional_properties: false
      schema_sources:
        custom: enabled signed-plugin WorldActionManifest.actions[].payload_schema
      codec: IDL-generated Swarm codec
command_action:
  variants:
    - name: Action
      parameters:
        - name: action_type
          type: string
        - name: object_id
          type: ObjectId
        - name: payload
          type: ActionPayload
  action_registry:
    vanilla_actions:
      actions:
        - type: Overload
          parameters:
            - name: target_id
              type: PlayerId
""".lstrip()
        valid_files = {
            "game_api.idl.yaml": game_idl,
            "api-registry.md": "ActionPayload<action_type> selected payload\n",
            "api-idl.md": (
                "ActionPayload<action_type> uses the IDL-generated Swarm codec and an "
                "enabled signed-plugin World Action Manifest.\n"
            ),
        }
        mutations = (
            (
                "game_api.idl.yaml",
                "        - name: payload\n",
                "        - name: target_id\n          type: EntityId\n        - name: payload\n",
                "Action parameters",
            ),
            (
                "game_api.idl.yaml",
                "              type: PlayerId\n",
                "              type: EntityId\n",
                "Overload target_id must be PlayerId",
            ),
            (
                "api-idl.md",
                "ActionPayload<action_type>",
                "Map<String, JsonValue>",
                "stale ActionPayload contract",
            ),
        )

        def check_fixture(root: Path, files: dict[str, str]) -> list[str]:
            paths = {name: root / name for name in files}
            for name, text in files.items():
                paths[name].write_text(text, encoding="utf-8")
            return check_docs.check_action_payload_contract(
                game_idl_path=paths["game_api.idl.yaml"],
                registry_path=paths["api-registry.md"],
                gameplay_idl_path=paths["api-idl.md"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(check_fixture(Path(temp_dir), valid_files), [])

        for filename, original, replacement, expected_error in mutations:
            with self.subTest(filename=filename, expected_error=expected_error):
                mutated_files = dict(valid_files)
                self.assertIn(original, mutated_files[filename])
                mutated_files[filename] = mutated_files[filename].replace(
                    original, replacement, 1
                )
                with tempfile.TemporaryDirectory() as temp_dir:
                    errors = check_fixture(Path(temp_dir), mutated_files)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    f"missing {expected_error!r} in {errors}",
                )

    def write_inputs(self, root: Path) -> tuple[Path, Path, Path]:
        game = root / "game_api.idl.yaml"
        auth = root / "auth_api.idl.yaml"
        economy = root / "economy.idl.yaml"
        game.write_text(GAME_IDL, encoding="utf-8")
        auth.write_text(AUTH_IDL, encoding="utf-8")
        economy.write_text(ECONOMY_IDL, encoding="utf-8")
        return game, auth, economy

    def expected_registry(self, root: Path) -> str:
        game, auth, economy = self.write_inputs(root)
        metadata = sync_api_registry.collect_metadata(game, auth, economy)
        return REGISTRY_TEMPLATE.format(
            game_version="1.2.3",
            auth_version="2.0.0",
            economy_version="0.9.0",
            generated_block=sync_api_registry.generated_block(metadata),
            all_game=3,
            active_game=2,
            gated_game=1,
            auth_tools=0,
            all_total=3,
            active_total=2,
        )

    def test_check_is_stable_when_registry_matches_generated_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, auth, economy = self.write_inputs(root)
            registry = root / "api-registry.md"
            registry.write_text(self.expected_registry(root), encoding="utf-8")

            changed, message = sync_api_registry.synchronize(
                registry, game, auth, economy, engine_idl=None, check=True
            )

            self.assertFalse(changed)
            self.assertEqual(message, "API Registry metadata is in sync")
            self.assertEqual(registry.read_text(encoding="utf-8"), self.expected_registry(root))

    def test_check_reports_drift_and_does_not_modify_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, auth, economy = self.write_inputs(root)
            registry = root / "api-registry.md"
            stale = REGISTRY_TEMPLATE.format(
                game_version="old",
                auth_version="2.0.0",
                economy_version="0.9.0",
                generated_block="",
                all_game=99,
                active_game=98,
                gated_game=1,
                auth_tools=1,
                all_total=100,
                active_total=99,
            )
            registry.write_text(stale, encoding="utf-8")

            changed, diff = sync_api_registry.synchronize(
                registry, game, auth, economy, engine_idl=None, check=True
            )

            self.assertTrue(changed)
            self.assertIn("-**API 版本**: `old`", diff)
            self.assertIn("+**API 版本**: `1.2.3`", diff)
            self.assertIn("+<!-- BEGIN GENERATED API REGISTRY METADATA -->", diff)
            self.assertEqual(registry.read_text(encoding="utf-8"), stale)

    def test_declared_total_mismatch_is_rejected(self) -> None:
        cases = [
            ("game", "total_variants: 2", "game_api.command_action.total_variants"),
            ("game", "total_vanilla: 1", "game_api.command_action.action_registry.total_vanilla"),
            ("game", "total_canonical_codes: 2", "game_api.rejection_reason.total_canonical_codes"),
            ("game", "total_tools: 2", "game_api.mcp_tools.total_tools"),
            ("game", "total_functions: 1", "game_api.host_functions.total_functions"),
            ("game", "total_fields: 2", "game_api.tick_trace_envelope.total_fields"),
            ("auth", "total_operations: 1", "auth_api.auth_control_plane.total_operations"),
            ("auth", "total_canonical_codes: 1", "auth_api.errors.total_canonical_codes"),
            ("auth", "total_event_types: 1", "auth_api.auth_trace_events.total_event_types"),
        ]
        for target, old, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                game, auth, economy = self.write_inputs(root)
                path = game if target == "game" else auth
                path.write_text(path.read_text(encoding="utf-8").replace(old, old.split(":", 1)[0] + ": 99", 1), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, expected + " declares 99"):
                    sync_api_registry.collect_metadata(game, auth, economy)

    def test_cli_check_reports_declared_total_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, auth, economy = self.write_inputs(root)
            registry = root / "api-registry.md"
            registry.write_text(self.expected_registry(root), encoding="utf-8")
            auth.write_text(
                AUTH_IDL.replace("total_operations: 1", "total_operations: 99"),
                encoding="utf-8",
            )
            script = Path(sync_api_registry.__file__).resolve()

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--check",
                    "--registry",
                    str(registry),
                    "--game-idl",
                    str(game),
                    "--auth-idl",
                    str(auth),
                    "--economy-idl",
                    str(economy),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("auth_api.auth_control_plane.total_operations declares 99", result.stderr)

    def test_check_docs_reports_declared_total_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = root / "specs" / "reference"
            specs.mkdir(parents=True)
            game, auth, economy = self.write_inputs(specs)
            registry = specs / "api-registry.md"
            registry.write_text(self.expected_registry(specs), encoding="utf-8")
            game.write_text(GAME_IDL.replace("total_functions: 1", "total_functions: 99"), encoding="utf-8")

            original_registry = check_docs.REGISTRY
            original_schemas = check_docs.SCHEMAS
            try:
                check_docs.REGISTRY = registry
                check_docs.SCHEMAS = {
                    "game_api": game,
                    "auth_api": auth,
                    "economy": economy,
                }
                errors = check_docs.check_registry_sync()
            finally:
                check_docs.REGISTRY = original_registry
                check_docs.SCHEMAS = original_schemas

            self.assertEqual(len(errors), 1)
            self.assertIn("generated Registry metadata validation failed", errors[0])
            self.assertIn("game_api.host_functions.total_functions declares 99", errors[0])


if __name__ == "__main__":
    unittest.main()
