#!/usr/bin/env python3
"""Tests for sync_api_registry.py."""

from __future__ import annotations

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
  gated_tools:
    - name: swarm_tournament_create
      status: rfc_gated
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
csr_lifecycle_tools:
  total_tools: 1
  tools:
    - name: swarm_register_challenge
      index: 1
rejection_reason:
  total_canonical_codes: 1
  variants:
    - code: InvalidCertificate
      index: 1001
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

### 3.2 Game API 工具清单 (`all_declared={all_game}`, `active_only={active_game}`, `rfc_gated={gated_game}`)
""".lstrip()


class SyncApiRegistryTests(unittest.TestCase):
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
            auth_tools=1,
            all_total=4,
            active_total=3,
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
            ("auth", "total_tools: 1", "auth_api.csr_lifecycle_tools.total_tools"),
            ("auth", "total_canonical_codes: 1", "auth_api.rejection_reason.total_canonical_codes"),
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
            auth.write_text(AUTH_IDL.replace("total_tools: 1", "total_tools: 99"), encoding="utf-8")
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
            self.assertIn("auth_api.csr_lifecycle_tools.total_tools declares 99", result.stderr)

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
