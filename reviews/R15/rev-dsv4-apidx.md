# R15 API/DX 评审报告 — rev-dsv4-apidx (DeepSeek V4 Pro)

**评审范围**: Phase 1 Clean-Slate，仅方向相关子集（7 个文件）。设计阶段评审，不考虑分阶段实现。

---

## 1. Verdict: REQUEST_MAJOR_CHANGES

理由：发现 2 个 Critical 类型不一致问题（Move 方向 4 vs 8、RejectionReason 三文档三种命名），且 MCP 工具普遍缺少 schema 定义，IDL 格式未在许可文档中指定。当前状态无法支撑 SDK 代码生成或 developer-facing API 稳定性承诺。

---

## 2. 发现的问题

### Critical

**D1: Move 方向语义三文档冲突 — interface.md=8方向，validation=4方向，engine=4方向**
- `design/interface.md` §5.4 定义 Move direction 为 `N/S/E/W/NE/NW/SE/SW`（8 方向）
- `specs/core/02-command-validation.md` §3.1 校验：`Direction 是合法四方向邻居 (N/S/E/W)`（仅 4 方向）
- `design/engine.md`: 连接仅支持 `N/S/E/W 四个方向`
- 结果：开发者按 interface.md 生成 NE/NW/SE/SW 方向的 Move 指令会被 validation pipeline 以 `InvalidDirection` 拒绝。整个 Move Command 的 type contract 破裂。

**D2: RejectionReason enum 三文档三种定义 — SDK 无法生成错误处理代码**
- `design/interface.md` §5.4: 10 种原因（`InvalidCommand`, `OutOfRange`, `InsufficientResources` 等）
- `specs/reference/commands.md`: 声明 45 种变体，列出 35 种（`ObjectNotFound`, `NotOwner`, `MissingBodyPart` 等）——命名体系完全不同
- `specs/core/02-command-validation.md`: 混合使用，且同一文件内 `InsufficientResources`（§3.3 校验表）和 `InsufficientResource`（§7.1 退款表）并存
- `specs/gameplay/08-api-idl.md`（搜索命中行 82）: 使用 `InsufficientResource`（单数）
- SDK 生成器无法知道该用哪个 enum 名称集合。开发者面对三个不同的错误码体系无法编写 switch/match/onError。

**D3: SendMessage Command 零校验定义 — 仅 interface.md 一行声明**
- `design/interface.md` §5.4 列出 `SendMessage | target_id, payload (max 256B) | drone 间消息`
- 在 `specs/reference/commands.md` 中完全不存在
- 在 `specs/core/02-command-validation.md` 中没有任何校验矩阵条目
- 在字段级穷举校验表（§6）中不存在
- 该指令无所有权校验、无范围校验、无 anti-spam 机制、无 payload 类型定义——安全后果严重

**D4: MCP 工具 schema 普遍缺失 — 违反 interface.md §4 的 Schema 完整性要求**
- `design/interface.md` §4 明确要求所有 MCP 工具必须具备 `inputSchema`、`outputSchema` 和 `error` schema
- `specs/reference/mcp-tools.md` 仅提供工具名和一行说明的表格——零 schema
- 明确要求完整的 10 个关键工具均无 schema：`swarm_sdk_fetch`, `swarm_get_schema`, `swarm_get_docs`, `swarm_get_player_status`, `swarm_deploy`, `swarm_validate_module`, `swarm_get_snapshot`, `swarm_get_available_actions`, `swarm_explain_last_tick`, `swarm_submit_csr`

### High

**D5: Command enum 跨文档条目不一致**
- `design/interface.md` §5.4: 列出 20 个 Command（含 SendMessage, Leech, Fabricate）
- `specs/reference/commands.md`: 声明 "15 Core + 1 Custom + 8 Special Attacks"，但列出 13 个 core（含 TransferToGlobal/TransferFromGlobal，不含 SendMessage）——自述与实际数量矛盾
- `specs/core/02-command-validation.md`: 校验矩阵覆盖 16 个命令（含 6 特殊攻击），但 Leech/Fabricate 仅散见于 §8 末尾且无完整校验矩阵
- TransferToGlobal/TransferFromGlobal 存在于 commands.md 和 IDL，但不存在于 interface.md §5.4 的 Command 表

**D6: MCP 工具清单三文档不一致**
- `design/interface.md` §4.1: 列出 swarm_get_economy, swarm_get_drone_efficiency, swarm_get_economy_trend（经济类）
- `specs/reference/mcp-tools.md`: 这三个工具完全缺失
- `design/interface.md` §4 要求 `swarm_get_player_status` 必须提供完整 schema
- `specs/reference/mcp-tools.md` 和 §4.1 工具分类表均无 `swarm_get_player_status`
- `swarm_sdk_fetch` 在 §5.3 详细定义，但 mcp-tools.md 和 §4.1 工具表中均不存在

**D7: Host function 返回值无类型化 enum — 全链路裸露 i32**
- `host_get_terrain`: 返回 terrain type (0=Plain, 1=Wall, 2=Swamp, 3=Lava)
- 错误码分散定义：-1=OOB, -2=range_too_large, -3=buffer_overflow, -4=timeout
- 设计文档定义了合法返回值和错误码，但未汇聚为 `TerrainType` enum + `HostFunctionError` enum
- SDK 代码生成器只能生成 `i32` 返回类型，开发者需手写 magic number 判断

**D8: IDL 格式未在许可文档中定义**
- `design/tech-choices.md` §10 声明 `game_api.idl → codegen → SDK` 自动生成路径
- `design/interface.md` §4 声明 MCP schema 由 `game_api.idl` 生成
- 但 IDL 格式（protobuf? JSON Schema? Smithy? 自研 DSL?）在 7 个许可文档中均未定义
- `specs/gameplay/08-api-idl.md` 存在但不在许可阅读范围内，且搜索结果显示它定义了自研 DSL 格式
- 无法评估 SDK 代码生成质量、类型保真度、跨语言映射准确性

### Medium

**D9: SwarmError JSON-RPC 错误码未注册标准化 registry**
- `design/interface.md` §5.6 定义了 JSON-RPC error envelope，但 `code` 字段统一使用 `-32000`
- 不同 SwarmError 类型共享同一 JSON-RPC code，客户端必须解析 `data.swarm_error` 字符串才能区分
- 不符合 JSON-RPC 2.0 最佳实践（应用级错误应使用 `-32000` 到 `-32099` 范围的不同 code）
- `data.details` 字段结构随 error 类型变化而不一致——有的含 `{required, available}`，有的含 `{resource, required, available}`，有的为 null

**D10: swarm_sdk_fetch 的 type_definitions 格式未指定**
- `design/interface.md` §5.3: Output 包含 `type_definitions: string`
- 但该字符串是 JSON Schema? TypeScript .d.ts? Rust .rs? 未指定
- 无 `schema_version` 字段——AI agent 无法判断 SDK 是否需要升级
- 无版本协商协议——仅有 `abi_version` 和 `min_engine_version`，缺少 SDK client 与 server 的握手

**D11: swarm_simulate 结果格式未定义**
- `design/interface.md` §5.7: swarm_simulate 返回 "deterministic replay"
- 但 replay 的数据结构未定义——是 TickTrace 格式？是 Command[] 列表？是状态 diff？
- 调用方无法编写 replay 解析代码

**D12: Capability Profile 缺少 version/timestamp**
- `design/interface.md` §4.1a 定义了 MCP capability profiles（onboarding/play/deploy/debug/admin）
- 但 profile 返回无 version 字段——AI agent 无法检测 profile 工具集是否变更
- `swarm_get_schema(profile=...)` 返回的最小集是否包含 schema 版本信息未说明

### Low

**D13: ClaimController 校验矩阵缺失**
- `design/interface.md` §5.4 列出 ClaimController（无参数）
- `specs/reference/commands.md` 有定义（需 CLAIM body part, 1 格内, target 是 Controller）
- 但 `specs/core/02-command-validation.md` 的逐指令校验矩阵（§3.1-3.16）未含 ClaimController
- 仅字段级穷举表（§6）最末行出现——缺少完整的 检查项|失败码 矩阵

**D14: Recycle 的 Command 示例 JSON 多文档不一致**
- `specs/reference/commands.md`: `{ "type": "Recycle", "object_id": "d1", "spawn_id": "s1" }`
- `specs/core/02-command-validation.md` §3.9: `{ "type": "Recycle", "object_id": 1001, "spawn_id": 2001 }`
- `specs/core/02-command-validation.md` §10.3: `{ "action": "Recycle", "object_id": "d1" }` —— 此处缺少 `spawn_id` 字段

**D15: Rate limit 策略分散于多文档，无统一 rate limit policy 文档**
- `specs/reference/mcp-tools.md`: 12 种 source 级 rate limit
- `design/interface.md` §5.3: swarm_sdk_fetch 单独 5/min
- Host functions: per-tick call limits（interface.md §5.5）
- MCP per-tool rate limits 未系统化定义

---

## 3. 亮点

1. **Deferred Command Model 设计优秀**：`tick(snapshot) → CommandIntent[] → RawCommand → ValidatedCommand → apply` 的管道清晰分离了不可信输入与可信执行，类型层级（CommandIntent/RawCommand/ValidatedCommand）渐进增强信任，是教科书级设计。

2. **统一校验管线**：所有入口（WASM tick、MCP tool、REST API、admin CLI）走同一 `validate_and_apply()` 路径，无绕过可能。Compile-time trait 设计确保 admin 不享独立代码路径。

3. **Fuel refund 机制设计周全**：anti-amplification 时序（退还不跨 tick 复用）、deploy-reset 规则（防跨模块预算转移）、同源重复失败仅首次退款、连续高退还率自动 throttle——这些细节展示了成熟的资源经济学思维。

4. **Overload 抗永久锁死证明**：形式化证明了多攻击者协调无法永久锁死目标 fuel budget，含最坏情况分析和恢复速率数学推导。这在游戏设计文档中极为罕见，展现工程严谨性。

5. **swarm_sdk_fetch 自举入口**：AI agent 首次接入无需预装 SDK——通过自举工具获取代码和类型定义。这是 MMO 场景中 AI-native 设计的典范。

6. **Idempotent deploy**：以 module_hash 作为 idempotency_key，同 module 重试只扣费一次。10 版本保留策略清晰。

7. **Host function 成本模型精确**：每函数定义 call limit、max output、CPU cost units、错误码——全部量化，无"酌情"判断。

8. **Capability profiles 降低 AI agent 认知负载**：onboarding/play/deploy/debug/admin 分层，agent 按需获取最小工具集——这是好的 MCP DX 设计。

---

## 4. CrossCheck — 需要跨方向检查

- **CX1**: Move 方向 4 vs 8 冲突 → 建议 **Architect** 确认最终方向语义：八方向涉及对角线移动的路径长度、疲劳计算、碰撞检测等——影响引擎、validation、SDK、UI 四个子系统。
- **CX2**: SendMessage 零校验定义 → 建议 **Security** 审查 payload 注入风险（虽限制 256B），以及缺少 ownership/range/anti-spam 校验的安全后果。
- **CX3**: TransferToGlobal/TransferFromGlobal 在 interface.md §5.4 缺失但在 commands.md 和 IDL 中存在 → 建议 **Architect** 决定这两个命令是否属于 Core IDL 还是 World Action Manifest 扩展，并保持文档一致。
- **CX4**: Leech 和 Fabricate 标记 "⏳ Tier 2" 且校验规则不完整 → 建议 **Architect** 确认其 Phase 1 状态（是否冻结？若冻结则从 Core IDL 移除；若保留则补齐校验矩阵）。
- **CX5**: RejectionReason enum 命名 convention 混乱（InsufficientResource vs InsufficientResources, ObjectNotFound vs TargetNotFound, RoomCapReached vs RoomDroneCapReached）→ 建议 **Architect** canonicalize 命名并统一所有文档引用。
- **CX6**: MCP 工具数量三文档不一致（~52 个 in interface.md vs ~45 个 in mcp-tools.md，经济类工具缺失）→ 建议 **Architect** 确认 MCP 工具完整清单并确保 mcp-tools.md 为 canonical reference。
- **CX7**: IDL 格式（自研 DSL）是否支持 Rust/TypeScript 双语言代码生成、类型保真度、可选字段语义 → 建议 **Architect** 验证 IDL 编译器的输出质量，特别关注 Optional 字段 -> Rust `Option<T>` vs TypeScript `T | undefined` 的正确映射。
- **CX8**: Host function 安全约束（WASM 内存上限 64MB、输出上限 256KB、禁止 WASI socket/fs）→ 建议 **Security** 审查 sandbox 实现是否 enforce 这些约束，以及 buffer overflow 保护（`out_ptr`/`out_len` 的 boundary re-check）。

---

*评审完成时间: 2026-06-18*
*评审员: rev-dsv4-apidx (DeepSeek V4 Pro) — API/DX Reviewer*
