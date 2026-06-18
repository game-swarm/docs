# R-appcert-R2 — API/DX Clean-Slate Review (rev-gpt-apidx)

## Verdict

CONDITIONAL_APPROVE

R2 的 API/DX 架构方向是正确的：IDL 单一真相、CommandIntent/RawCommand 分层、MCP 不直接执行游戏动作、应用层证书与 canonical request、Gateway transport auth matrix、AI agent 与人类同走 WASM 路径，这些都是已知成功系统里能降低长期分叉风险的设计。当前不需要推倒重来；但在进入实现前，必须先冻结“玩家可见 API 合同”和“生成物合同”，否则 SDK、MCP schema、教程、示例和服务端校验会出现各自正确但互相不兼容的失败模式。

## Strengths

- IDL 单一真相方向很强：`game_api.idl → Rust/TS SDK/MCP schema/Docs/Test` 是避免 API 腐化的正确中枢，且明确禁止手写 Command 变体与 host function。
- MCP 定位清晰：AI agent 通过 MCP 看世界、部署 WASM、调试，不通过 `swarm_move/swarm_attack` 等直接动作工具绕过公平性；这避免了“AI 玩家拥有第二套控制面”的典型失败案例。
- CommandIntent → RawCommand → ValidatedCommand 分层合理：`player_id/source/tick` 由 Source Gate 注入，客户端不可自报，接口安全边界直观。
- Canonical request 与应用层证书模型足够具体：字段顺序、LF、domain separator、body_hash、nonce/timestamp、audience 都有明确合同，适合 SDK 实现互操作测试。
- Gateway auth matrix 把 Browser/REST/MCP/Replay/Admin 的认证材料和失败码集中成权威表，这是降低跨 transport 混淆的好模式。
- 可见性优先的拒绝响应、`NotVisibleOrNotFound`、admin/player trace 分离，说明 API 设计考虑到了信息泄漏，而不仅是功能可用性。
- 动态 SDK/manifest hash 设计能支持 mod 世界：`target_manifest_hash` + `engine_abi_version` 对 SDK mismatch 的错误提示对开发者友好。

## Concerns

### A1 — High — 新手路径与权威 IDL 不一致，会导致第一段代码不可运行

`GETTING-STARTED.md` 的第一个 TypeScript bot 使用：

- `cmds.push({ action: "SpawnDrone", object_id: spawn.id, body: ["MOVE", "WORK", "CARRY"], seq: 1 })`
- `cmds.push({ action: "Harvest", object_id: drone.id, target_id: source.id, seq: 2 })`

但 `08-api-idl.md` 和 `commands.md` 的权威形态是：

- 顶层字段为 `sequence` 与 `action`
- action 内有 `type`
- Spawn 参数是 `spawn_id`
- BodyPart 枚举是 `Move/Work/Carry`，不是 `MOVE/WORK/CARRY`
- 不存在顶层 `seq` 或顶层 `action: "Harvest"`

这不是文档小瑕疵，而是 DX 入口炸点：新人、AI agent 和 SDK 生成器都会从示例学习。如果第一个 bot 无法通过 schema，开发者会认为 SDK 或服务端坏了。

Recommendation: 以 IDL 为准重写 GETTING-STARTED 的 bot 示例，并把它纳入 generated example 或 doc-test：示例必须由 `cargo run -- gen-api` 或 SDK test fixture 验证。

### A2 — High — Command/错误码/枚举存在多处漂移，IDL “单一真相”尚未真正落地

多个文档在同一概念上出现不一致：

- `08-api-idl.md` 的 `Direction` 为 `North/South/East/West`，`commands.md` 示例使用 `TopRight`。
- `commands.md` 说 “15 Core + 1 Custom + 8 Special Attacks”，但正文又把特殊攻击作为直接 `type`，IDL 同时列出内置特殊攻击和动态 `custom_actions`。
- `commands.md` 标题写 `SpawnDrone`，示例 action type 是 `Spawn`。
- `02-command-validation.md` 前段 tick output 上限为 256KB，后段批级校验又写整批 1MB。
- `RejectionReason` 在 IDL、commands 参考和 command-validation 中数量与命名不一致，如 `InsufficientResource/InsufficientResources/InsufficientEnergy`、`ObjectNotFound` 与可见性优先后的 `NotVisibleOrNotFound`、`OnCooldown/TargetFortifyCooldown` 是否在枚举中。
- `Recycle` 退还比例在部分文档仍是固定 50%，而 command-validation 后段已修正为 lifespan 加权。

这类漂移是“看起来都有文档，但实现时每个人选自己那份”的典型失败模式。

Recommendation: 在 R2 冻结一个 machine-readable `api-contract.json` 或 `game_api.idl` 作为唯一源，并要求 reference docs、GETTING-STARTED、MCP schema、SDK examples 全部生成或至少 schema-test。人工手写参考只能作为解释，不得承载权威字段名。

### A3 — High — MCP 工具只有目录级说明，缺少可执行 JSON Schema 与错误模型

`mcp-tools.md` 工具清单覆盖面较完整，但多数工具只有一句用途说明，缺少：

- 每个 tool 的 input schema / output schema
- required/optional 字段
- 分页、范围、大小限制
- stable error codes
- rate-limit error 格式
- replay/simulate/debug 返回对象的 canonical 结构
- tool schema 与 IDL/manifest hash 的绑定规则

对 AI agent 来说，“工具名列表”不足以端到端执行；function calling/MCP client 需要精确 schema。否则 agent 会发出似是而非的 payload，失败后无法自我修复。

Recommendation: 把 MCP tool schema 纳入 IDL 生成物，至少先冻结 `swarm_deploy`、`swarm_validate_module`、`swarm_get_snapshot`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_submit_csr` 的完整 request/response/error schema。

### A4 — Medium — Deploy payload 形状在文档间不一致，容易造成 SDK 与网关互操作失败

`09-command-source.md` 定义部署签名载荷包含 `domain/module_hash/metadata_hash/player_id/world_id/module_slot/version_counter/signed_at/signature`，且服务端接收 WASM bytes + mod.toml + DeployPayload + 证书。

但 `03-mcp-security.md` 的 `swarm_deploy` 示例仍是：

```json
{
  "wasm_bytes": "<base64>",
  "language": "rust",
  "version_tag": "v1.2.0",
  "room_id": 5
}
```

这会让 MCP client 和 Gateway 对 deploy 请求的 canonical body 产生不同理解。部署是 AI agent 端到端路径的核心动作，不能只在安全文档中严谨、在工具文档中简化到另一套协议。

Recommendation: 统一 `swarm_deploy` 为 signed DeployPayload 合同；`language/version_tag` 可进入 metadata，但不能替代 `module_hash/metadata_hash/version_counter/module_slot/signed_at`。

### A5 — Medium — Snapshot/host function 的序列化格式边界还不够确定

文档同时出现：

- `interface.md`: 快照格式为结构化数据，非纯文本 JSON。
- `03-mcp-security.md`: AI 通过 `swarm_get_snapshot` 接收类型化结构化 JSON，与 WASM `tick()` 输入完全相同。
- `host-functions.md`: `host_get_objects_in_range` 返回实体 JSON 列表写入 WASM memory。
- `08-api-idl.md`: `tick(snapshot_ptr, snapshot_len)` 返回 command JSON pointer。

这不是方向错误，但需要更精确：WASM ABI 看到的是 canonical binary、canonical JSON、还是 SDK 层抽象后的 JSON？AI/MCP snapshot 与 WASM snapshot “完全相同”是语义相同还是字节相同？如果不冻结，会影响 canonical hash、replay、SDK bindings、内存边界检查和 doc examples。

Recommendation: 明确三层格式：wire/canonical snapshot、WASM ABI buffer、SDK object model。规定哪些层参与 hash，哪些层允许 SDK 友好转换。

### A6 — Medium — Dynamic world SDK 与长期兼容性策略还缺少开发者工作流细节

`08-api-idl.md` 提出按 `mod_manifest_hash` 动态生成 SDK，这是合理的，但还缺少几个 DX 必需合同：

- SDK artifact 的版本命名和依赖解析方式（npm/crate/local cache）
- `swarm sdk fetch` 的输出结构与 lockfile 格式
- 多世界/多 hash 同时开发时的 import 路径策略
- manifest hash 变化时，已部署模块、CI、local cache 如何提示与迁移
- AI agent 如何从 `swarm_get_schema` 到生成代码、编译、部署形成闭环

缺这些不会推翻架构，但会让 SDK 可用性从“理论上生成”退化为“每个项目自己拼路径”。

Recommendation: 增加 `sdk.lock` / `swarm-sdk.json` 合同和最小端到端示例：fetch → generate project → build wasm → sign deploy → explain first tick。

### A7 — Low — Transport audience 字符串格式在文档间有轻微不一致

Gateway 权威表使用 `mcp:{server_id}:{world_id}:{player_id}`、`ws:...`、`rest:...`。部分安全文档使用 `{server_id, world_id, "cli"}` 或 `transport:server_id:world_id:player_id` 的泛化描述。

这类差异在实现 canonical signature 时会变成验签失败。

Recommendation: 只保留一种 ABNF/grammar，例如 `audience = transport ":" server_id ":" world_id ":" subject_id`，transport 枚举为 `mcp/ws/rest/replay/admin`，所有文档引用该 grammar。

### A8 — Low — 部分限流数字与分类重复定义，未来会产生配置漂移

`mcp-tools.md`、`03-mcp-security.md`、`12-gateway-protocol.md`、`09-command-source.md` 都定义了 MCP/query/deploy/simulate/dry-run 的限流，但数字和维度不完全一致，例如 MCP query 是 50/tick、Gateway 写 50 MCP requests/tick、工具表中 docs/schema 有无限制或 20/tick。

Recommendation: 把 rate limit 作为 generated config/reference 表，工具文档引用同一表；错误响应统一为 `RateLimited { scope, retry_after_tick? | retry_after_ms? }`。

## Missing

- 缺少 “可执行 API 契约包”：`game_api.idl`、MCP JSON Schemas、OpenAPI/JSON-RPC schema、error schema、generated examples 的单一版本包。
- 缺少 SDK 最小项目模板：TypeScript 与 Rust 至少各一个能编译为 WASM、通过 `swarm_validate_module`、部署并执行首 tick 的模板。
- 缺少 AI agent 端到端 golden path：从 `swarm_get_server_trust` 到 CSR、fetch SDK、生成 bot、build、sign deploy、`swarm_explain_last_tick` 的完整机器可读流程。
- 缺少 canonical body hash 对 JSON 的规范：当前 request signature 定义了 payload 行格式，但没有完全说明 JSON body canonicalization（key order、number format、unicode escaping、base64 padding、unknown fields）。
- 缺少 schema evolution 策略：新增 optional 字段、弃用字段、manifest hash 与 ABI version 如何协同，哪些变更是 breaking。
- 缺少错误恢复 UX 合同：尤其是 schema mismatch、SDK mismatch、certificate expired/revoked、stale version_counter、rate limited、module validation failed 的 SDK-level typed errors。

## Phase Ordering

1. 先冻结权威 API contract：以 `08-api-idl.md` 为基础收敛 CommandIntent、Action、RejectionReason、BodyPart、Direction、host functions、MCP tool schemas、rate limit、deploy payload。
2. 再生成 SDK 与文档：commands reference、GETTING-STARTED、MCP schemas、TS/Rust types、example bot 不再手写字段名。
3. 然后补齐端到端 golden path：AI agent 与人类 Web/CLI 共享同一 deploy/sign/validate/explain 流程，至少覆盖 vanilla world。
4. 接着定义 canonical serialization test vectors：request signature、DeployPayload、CommandIntent、snapshot hash、manifest hash 都要有跨语言测试向量。
5. 最后再扩展动态 world SDK：manifest hash、mod actions、custom effects、multi-world cache 和 SDK lockfile 在核心 vanilla API 稳定后纳入。

## Bottom Line

R2 的抽象层次总体合理：MCP 是操作界面，不是游戏控制器；WASM 是唯一执行路径；IDL 是 API 中枢。这套方向值得保留并推进。阻塞点不是架构方向，而是 API 合同尚未真正“单一真相化”：示例、参考、MCP schema、deploy payload、错误码和枚举必须在实现前统一，否则最先爆炸的一定是 SDK 和 AI agent 端到端体验。
