# Codegen Pipeline — IDL → API Registry / SDK / Docs

## 原则

1. **生成权威在 Engine**：当前可执行的生成逻辑在 `engine/src/idl.rs`（IDL extraction）和 `engine/src/sdk_gen.rs`（SDK text generation）。`*.idl.yaml` 是参考级机器规范，必须与 Engine extraction 保持一致。
2. **API Registry 是发布口径**：`api-registry.md` 是面向人的 canonical publication；表格、列表、计数必须与 Engine extraction 和 `*.idl.yaml` 保持一致。
3. **CI/check 口径**：当前仓库没有 `hermes codegen` CLI。可用检查是 Engine cargo tests；若新增独立 generator CLI，本文档必须与实际命令同步。

## 输入 → 输出映射

| 输入 (IDL) | 生成产物 | 不可手写区域 |
|------------|---------|-------------|
| `game_api.idl.yaml` | `api-registry.md` §1-8, §11-13 | CommandAction 表、RejectionReason 表、MCP Tools 表（三口径统计）、Host Functions 表、容量限制表、TickTrace、Direction、SwarmError、Deploy/Persistence/Security columns |
| `auth_api.idl.yaml` | `api-registry.md` §2-3, §5-6, §8-9, §13 | Auth RejectionReason、Auth 工具表、Auth 限制、Auth TickTrace events、SwarmError canonical enum、Certificate Envelope、Security columns |
| `economy.idl.yaml` | `api-registry.md` §5, §10 | Economy 限制、Economy Operations 表、Canonical Formulas 表 |
| 所有 IDL | SDK 类型定义 (`sdk-templates/`) | 类型定义、ABI 版本 |

## 禁止手写的数值

以下数值**只存在于 IDL 中**，API Registry 由 codegen 生成。任何手写副本为错误；本文档只引用 Registry，不重新声明计数：

> ⚠️ **本文档自身为手工维护**。CommandAction、MCP tool、RejectionReason、Host function 等计数以 [API Registry](api-registry.md)、`*.idl.yaml` 和 Engine extraction tests 为准。当前可用检查见下方 `cargo test` 命令；不要引用未提供的 generator CLI。

- CommandAction 数量（见 Registry §1）
- MCP tool 数量（见 Registry §3 三口径：`all_declared` / `active_only` / `rfc_gated`）
- RejectionReason 数量（见 Registry §2）
- Host function 数量（见 Registry §4）
- `MAX_DRONES_PER_PLAYER`（见 Registry §5）
- Body part costs（见 Registry §10）
- Storage tax anchors（见 Registry §10）
- Refund rates（见 Registry §10）
- Rate limits（见 Registry §3.1）

## CI Gate

```bash
# Engine extraction exposes the current generated command/rejection registries.
cargo test -p swarm-engine --lib extracted_idl_exposes_command_and_rejection_registries

# MCP docs/tutorial contract checks cover published API resources.
cargo test -p swarm-engine --lib basic_agent_tutorial_preserves_mcp_security_and_idl_contracts
```

## Codegen 命令

```bash
# 当前仓库没有 standalone codegen binary/CLI。
# 生成逻辑入口（library functions）：
#   engine::idl::extract_idl(...)
#   engine::sdk_gen::generate_typescript(&idl)
#   engine::sdk_gen::generate_rust(&idl)

# 可执行一致性检查：
cargo test -p swarm-engine --lib extracted_idl_exposes_command_and_rejection_registries
cargo test -p swarm-engine --lib basic_agent_tutorial_preserves_mcp_security_and_idl_contracts
```

## 版本同步

IDL 版本变更时自动更新 API Registry 头部 `api_version` 行。当前 `game_api` 版本为 `0.4.0`，`auth_api` 版本为 `0.2.0`。若 Registry 与 IDL 不一致，先修正 IDL 再运行生成器；不得把 Registry 版本单独推进。
