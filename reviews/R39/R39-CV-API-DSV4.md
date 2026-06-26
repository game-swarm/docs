# R39 Closure Verification — API/DX（DSv4）

**Reviewer**: DSv4 API/DX  
**范围**: `specs/reference/api-registry.md`, `specs/reference/commands.md`, `specs/reference/mcp-tools.md`, `specs/reference/codegen.md`, `design/interface.md`  
**目标**: 验证 API Registry / Command API / MCP 工具 / Codegen / Interface 之间是否仍存在 API/DX 层面的漂移、错误示例或开发者体验断点。

## 总体结论

**REQUEST_CHANGES**

API Registry 本身已建立较强的单事实源约束（IDL → Registry → SDK/Docs），但派生文档仍有多处残留：`commands.md` 中的 JSON 示例与 Registry schema 不一致，`design/interface.md` 的工具计数和认证迁移说明仍停留在旧 auth/token 模型，`mcp-tools.md` 版本标题落后于当前 Registry。这些问题会直接误导 SDK 使用者和 AI agent 接入流程，建议在进入下一轮前修正。

## Findings

### API-H1 — `commands.md` 的 CommandAction 示例与 Registry schema 不一致

**严重级别**: High  
**状态**: GAP

**证据**:
- `api-registry.md:43` 声明所有 11 个 CommandAction 变体 + Action dispatch 均包含共享字段 `object_id`。
- `api-registry.md:45` 明确 Spawn 语义：`object_id` / `actor_id` 是发起 Spawn 的 drone，`spawn_id` 是目标 Spawn 结构。
- `api-registry.md:58` 将 Build 参数定义为 `structure_type: StructureType`。
- `commands.md:60` 的 Spawn 示例缺少 `object_id`。
- `commands.md:69` 的 Build 示例使用 `structure` 而不是 `structure_type`。
- `commands.md:77` 与 `commands.md:85` 的 `TransferToGlobal` / `TransferFromGlobal` 示例缺少 `object_id`。

**影响**:
- SDK/示例代码按 `commands.md` 实现会生成不符合 IDL/Registry 的 payload。
- Spawn 的 actor/target 边界再次变模糊，容易回退到旧的 `spawn_id` 既是 actor 又是 target 的错误理解。

**建议修复**:
- 所有 CommandIntent 示例补齐 `object_id`。
- Build 示例字段改为 `structure_type`。
- Spawn 示例显式展示 `{ object_id: "d1", spawn_id: "s1" }` 的 actor/target 分离。

### API-H2 — `commands.md` 的 Global Storage 费用/延迟说明与 Registry 经济权威冲突

**严重级别**: High  
**状态**: GAP

**证据**:
- `api-registry.md:855` 将 AlliedTransfer 权威定义为 `200 bp (2.00%) fee`, `200 tick delay`, `500 tick cooldown`, `daily cap: 10,000`。
- `commands.md:80` 写 `TransferToGlobal` 默认 10 tick 到账、1% 手续费、可被拦截。
- `commands.md:88` 写 `TransferFromGlobal` 默认 5 tick 到账、5% 手续费。
- `api-registry.md:825` 声明经济费率/公式以 `resource-ledger.md` 为数学权威，IDL/Registry 禁止手写经济数值。

**影响**:
- 用户无法判断 Global Storage / AlliedTransfer 的实际费用模型。
- 示例文档重新引入手写经济数值，破坏 Registry/codegen 的单事实源原则。

**建议修复**:
- 删除 `commands.md` 中 1% / 5% / 默认 5/10 tick 的手写说明。
- 改为引用 Registry §10 与 Resource Ledger §2.1；如需说明 allied transfer，使用 200bp / 200 tick / 500 tick cooldown / 10000 daily cap。

### API-H3 — `design/interface.md` 的工具计数仍写成 57 game + 11 auth

**严重级别**: High  
**状态**: GAP

**证据**:
- `api-registry.md:261` 声明 `game_api.idl.yaml (57 tools), auth_api.idl.yaml (12 auth tools)`。
- `api-registry.md:389` 标题为 Auth API 工具 (12)。
- `api-registry.md:395` 说明 7 个 CSR/certificate lifecycle + 5 个 device/recovery/federation，总计 12。
- `design/interface.md:19` 仍写 `57 game tools + 11 auth tools`。

**影响**:
- Interface 是 AI agent 接入域文件，错误计数会误导 capability discovery、文档导航和验证脚本。

**建议修复**:
- 将 `design/interface.md:19` 改为 `57 game tools + 12 auth tools`。
- 如保持概念概述，可避免重复计数，直接写“以 Registry §3 为准”。

### API-M1 — `design/interface.md` 保留旧 token/auth 工具迁移说明

**严重级别**: Medium  
**状态**: GAP

**证据**:
- `api-registry.md:294`–`api-registry.md:300` 的 Game API Auth shortcut 为 `swarm_register_challenge`, `swarm_submit_csr`, `swarm_cert_check`。
- `api-registry.md:397`–`api-registry.md:419` 的 Auth API 12 工具中没有 `swarm_auth_refresh`。
- `design/interface.md:32` 写 `swarm_token_refresh` → `swarm_auth_refresh`。

**影响**:
- 文档暗示存在一个 Registry 中不存在的目标工具 `swarm_auth_refresh`。
- 证书链模型已经替代 bearer/refresh token 路径，此处会误导客户端迁移。

**建议修复**:
- 删除 `swarm_token_refresh` → `swarm_auth_refresh` 迁移项。
- 改为说明旧 refresh-token 工具已移除，认证入口为 CSR/certificate lifecycle，并引用 Registry §3.3。

### API-M2 — `design/interface.md` 的 SDK 错误名使用非 canonical RejectionReason

**严重级别**: Medium  
**状态**: GAP

**证据**:
- `api-registry.md:96` 与 `api-registry.md:738` 规定业务拒绝原因必须放入 `error.data.rejection_reason`，使用 canonical RejectionReason。
- `design/interface.md:109` 列出 `SDKNotFound`, `UnsupportedLanguage`, `RateLimited`。
- `design/interface.md:148`–`design/interface.md:149` 又列出 `ConflictRetry`, `InvalidCommand`。
- Registry §2 的 canonical codes 中有 `RateLimited`，但没有 `SDKNotFound`、`UnsupportedLanguage`、`ConflictRetry`、`InvalidCommand`。

**影响**:
- SDK 生成 typed exception 时会遇到文档中存在、Registry 中不存在的错误名。
- 开发者可能把非 canonical 字符串当作 wire enum 返回。

**建议修复**:
- 将 SDK fetch 错误改写为 canonical `RejectionReason` + `debug_detail` 示例。
- `UnsupportedLanguage` 可映射为 `SchemaViolation` 或 `InvalidResourceType` 等现有 canonical code（需按 IDL 决定）；若确需新 code，应先改 IDL。
- 删除 `ConflictRetry` / `InvalidCommand`，或明确它们只是非 wire 的 SDK 内部分类，不得出现在 `error.data.rejection_reason`。

### API-M3 — `mcp-tools.md` 标题版本仍同步自 Registry 0.4.0

**严重级别**: Medium  
**状态**: GAP

**证据**:
- `api-registry.md:7` 当前 Game API 版本为 `0.5.0`。
- `api-registry.md:966` 记录 0.5.0 已将 CommandAction 泛化为 11 core + Action dispatch。
- `mcp-tools.md:29` 标题仍写“同步自 API Registry 0.4.0”。

**影响**:
- `mcp-tools.md` 的工具数量内容基本已是 57/12，但标题版本会让读者误以为未包含 0.5.0 的 Action dispatch / auth shortcut 同步。

**建议修复**:
- 将标题改为“同步自 API Registry 0.5.0”或去掉具体版本，写“同步自当前 API Registry”。

### API-L1 — `codegen.md` 的 Auth 输出映射章节号已漂移

**严重级别**: Low  
**状态**: GAP

**证据**:
- `codegen.md:16` 写 `auth_api.idl.yaml` 生成 `api-registry.md` §6-9，包括 Auth 工具表、Auth Error Codes、Token Envelope。
- 当前 `api-registry.md:389` 的 Auth API 工具在 §3.3。
- 当前 `api-registry.md:699` 的 Auth Tick Trace Events 在 §6.2。
- 当前 `api-registry.md:776` 的证书 envelope 在 §9。

**影响**:
- codegen 文档作为维护者入口，章节号错误会降低修复/生成链路的可操作性。

**建议修复**:
- 将映射改成具体当前章节：Auth shortcuts/Full Auth tools → §3.2/§3.3；Auth trace events → §6.2；Certificate Envelope → §9；Auth limits → §5.8。

## 已通过项

- `api-registry.md` 已明确 IDL 是唯一机器可读权威源，并在 CommandAction、MCP Tools、Host Functions、容量限制等章节加入 CI Gate 说明。
- `mcp-tools.md` 正确保留“MCP 不做游戏动作”的边界，并明确禁止 `swarm_move` / `swarm_attack` / `swarm_build` / `swarm_spawn`。
- `design/interface.md` 的 host function 列表已包含 `host_get_random(sequence, ...)`，与 Registry §4.1 对齐。
- `codegen.md` 已明确 `hermes codegen generate --check` 用作 CI drift gate，方向正确。

## 建议收敛顺序

1. 先修 `commands.md` 示例 schema 与费用残留（API-H1/H2），这是最容易误导实际调用的部分。
2. 再修 `design/interface.md` 的 auth 工具计数、旧 token 迁移项与非 canonical 错误名（API-H3/M1/M2）。
3. 最后修 `mcp-tools.md` 版本标题与 `codegen.md` 章节映射（API-M3/L1）。

## Verdict

**REQUEST_CHANGES** — 存在 3 个 High、3 个 Medium、1 个 Low。问题主要集中在派生文档漂移，不需要推翻 Registry 设计；按上述顺序做一次文档同步即可进入下一轮 Closure Verification。
