# Codegen Pipeline - Current Sources and Validation

## 当前事实

1. **文档 YAML 与 Registry 是手工同步的参考发布物**：`game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 和 `api-registry.md` 都位于本仓库，用于发布机器可读参考与人类可读参考。修改 schema 时必须在同一变更中更新相应 YAML、Registry 表格和 Registry 生成元数据。
2. **当前文档检查执行有界生成校验**：`scripts/check_docs.py` 验证仓库相对链接、GitHub-style heading anchors、Schema input 链接、生成的 Registry metadata/tool counts/API 版本和关键 gameplay 常量；它不从 YAML 生成完整 Markdown Registry、SDK 或其他文件，也不声称验证 Registry 表格逐项相等。
3. **Engine extraction 是另一条独立生成管线**：Engine 仓库的 `src/idl.rs` 从 Rust 维护的 extraction tables 和运行时 mod registries 构造 JSON `IdlDoc`。它不读取本仓库的 `*.idl.yaml`，也不生成本仓库的 Markdown Registry。
4. **Engine SDK 生成器消费运行时 IDL**：Engine 仓库的 `src/sdk_gen.rs` 通过 `generate_typescript(&idl)` 和 `generate_rust(&idl)` 从 `IdlDoc` 生成 SDK 文本。
5. **Frontend 合同由 Engine Rust 类型生成**：Engine 仓库的 `src/contract_exports.rs` 使用 `schemars` 与 `ts-rs` 从 `CommandIntent`、`CommandAction`、`RealtimeEnvelope`、`VisibleWorldSnapshot` 等 Rust 类型导出 `swarm-contracts.ts`、`command-intent.schema.json`、`realtime.schema.json` 和 `visible-snapshot.schema.json`。Frontend `contracts:check` 比较这些生成物，防止手写 schema 漂移。

因此，文档 YAML、Registry 和 Engine `IdlDoc` 是需要协调维护的不同表示；当前 docs-side CLI 只覆盖 Registry metadata/count/version 同步，不应把正文表格或 SDK 描述为可由当前 Engine extraction 或文档检查完整重建的生成产物。

## 来源与产物

| 来源 | 当前产物 | 维护/验证方式 |
|------|----------|---------------|
| 文档 `game_api.idl.yaml` + Registry | Game API 参考发布 | `scripts/sync_api_registry.py` 同步生成 metadata/count/version；正文表格手工维护 |
| 文档 `auth_api.idl.yaml` + Registry | Auth API 参考发布 | `scripts/sync_api_registry.py` 同步生成 metadata/count/version；正文表格手工维护 |
| 文档 `economy.idl.yaml` + Registry | Economy API 参考发布 | `scripts/sync_api_registry.py` 同步生成 metadata/count/version；正文表格手工维护 |
| Engine Rust 类型 + runtime registries | JSON `IdlDoc` | Engine `extract_idl(...)` 和 Engine tests |
| Engine JSON `IdlDoc` | TypeScript/Rust SDK 文本 | Engine `generate_typescript(...)` / `generate_rust(...)` 和 Engine tests |
| Engine Rust contract types | Frontend generated contracts/schema | Engine `export-contracts` + Frontend `contracts:check` |

## 文档仓库检查

从本仓库根目录运行：

```bash
python3 scripts/check_docs.py
```

该命令仅使用 Python 标准库，并执行以下检查：

- Markdown 相对链接的目标文件或目录存在。
- Markdown 相对链接中的 heading anchor 存在。
- Registry 的三个 schema input 链接完整。
- Registry 生成 metadata block、工具计数和 Game/Auth/Economy API 版本与对应 IDL 一致。
- Attack/RangedAttack/Heal 的 body cost 在 Economy IDL、Registry、World Rules 与 Gameplay 中一致；range 在 canonical action table、World Rules 与 Gameplay 中一致。
- Economy IDL、Registry、World Rules 与 Gameplay 中的完整 structure cost schedule 一致。

这项检查解析 docs IDL YAML 的结构化 metadata，但不比较 Registry 的全部表格内容。表格变化仍需评审；把这项轻量检查描述为完整 codegen drift 检测是不准确的。

## Engine 检查

以下命令必须从 Engine 仓库根目录运行。它们验证 Engine 自己的 runtime IDL extraction 和发布教程合同，不验证本仓库 YAML 与 Registry 的逐项一致性：

```bash
cargo test -p swarm-engine --lib extracted_idl_exposes_command_and_rejection_registries
cargo test -p swarm-engine --lib basic_agent_tutorial_preserves_mcp_security_and_idl_contracts
```

docs-side Registry metadata/count/version 同步命令为：

```bash
python3 scripts/sync_api_registry.py --check
python3 scripts/sync_api_registry.py
```

可选传入 Engine extraction JSON 以在生成 metadata 中记录 Engine 侧计数摘要：

```bash
python3 scripts/sync_api_registry.py --engine-idl /path/to/engine-idl.json --check
```

Engine 二进制提供的是 runtime IDL/SDK 命令，它们不读取本仓库 YAML，也不生成 Registry 正文表格：

```bash
cargo run -p swarm-engine -- dump-idl [world.toml]
cargo run -p swarm-engine -- generate-sdk [world.toml] [out_dir]
cargo run -p swarm-engine -- export-contracts [frontend/src/generated]
```

对应的 library 入口为：

```text
engine::idl::extract_idl(...)
engine::sdk_gen::generate_typescript(&idl)
engine::sdk_gen::generate_rust(&idl)
engine::contract_exports::export_contract_artifacts(...)
```

### Command Schema Branch Contract

Engine command schemas share a single Rust branch source. The generated SDK command-intent schema and MCP action schema expose 45 `oneOf` branches: 44 concrete command/action branches plus one custom-action wildcard. The wildcard rejects reserved built-in names so a concrete command matches exactly one branch. Canonical v1 clients that emit bare `CommandIntent[]` remain valid; richer realtime recovery uses the generated `swarm.realtime.v1` envelope contracts.

## 版本同步

IDL 版本变更时，运行 `python3 scripts/sync_api_registry.py` 更新 `api-registry.md` 的 `API 版本` 行和 generated metadata block。`scripts/check_docs.py` 会在声明与 `game_api.idl.yaml`、`auth_api.idl.yaml` 或 `economy.idl.yaml` 不一致时失败。
