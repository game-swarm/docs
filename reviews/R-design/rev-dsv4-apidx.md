# R-design: API/DX Clean-Slate Review — DeepSeek V4 Pro

**Reviewer**: rev-dsv4-apidx (API/DX specialist, DeepSeek V4 Pro reasoning chain)
**Date**: 2026-06-18
**Documents reviewed**: README.md, auth.md, engine.md, gameplay.md, interface.md, modes.md, tech-choices.md

---

## Verdict: CONDITIONAL_APPROVE

API/DX 设计方向正确——deferred command model 保证人类/AI 同路径、SDK 自动生成是强 DX 模式、证书模型完善。但存在 2 个 Critical 问题和 6 个 High 问题阻塞 Phase 1 实现。所有 Critical/High 必须在实现前解决。

**综合评分**: 7 Critical/High 问题需要修复；16 个发现问题总计。

---

## Findings

### Critical

**C1. `swarm_sdk_fetch` MCP 工具缺少完整定义** (interface.md + gameplay.md)

interface.md §4 的 Schema 完整性要求明确列出 `swarm_sdk_fetch` 为首个必须有 inputSchema/outputSchema/error schema 和 rate limit 的工具，但 MCP 工具表中没有它的条目。gameplay.md §SDK生成与分发 描述了 SDK 下载端点（MCP: `swarm_sdk_fetch(world_id)`）和工作流，但这是 MCP 侧 AI agent 首次接入的唯一入口——没有正确的 SDK，agent 无法编译部署。缺少 schema 定义意味着实现时没有合同。

**修复**: 在 interface.md MCP 工具表添加 `swarm_sdk_fetch` 条目，定义:
- `inputSchema`: `{ world_id: string, target?: "rust" | "ts" | "json" }`
- `outputSchema`: `{ manifest_hash: string, sdk_package: base64, abi_version: u32 }`
- `error`: `world_not_found`, `target_unsupported`
- rate limit: 60/min per player

**C2. Deferred Command 模型的 Command 类型 schema 未定义** (interface.md + engine.md)

这是 WASM 玩家代码与引擎之间的核心 API 合同。design 描述了 `tick(snapshot) → Command[]` 的概念模型，但 Command 类型的完整 schema——有效 command 枚举、每个 command 的字段、验证规则、rejection reason 枚举——在整个设计文档中不存在。interface.md §5.2 列出了禁止的 host function 并说"通过 tick() → JSON"，但没有说明 JSON 里有什么。注：gameplay.md 多处引用 Command（如 "Hack"、"Overload" 等特殊攻击），但这些都是 gameplay 概念，不是 API schema。

**修复**: 创建 `specs/reference/command-schema.md`，定义完整的 Command 枚举（Move/Harvest/Build/Transfer/Attack/RangedAttack/Heal/Recycle/Spawn/ClaimController/Withdraw + 6种特殊攻击）, 每个 command 的必需/可选字段及其类型、验证规则矩阵、和 RejectionReason 枚举。在 interface.md §5 引用此 spec。

### High

**H1. MCP 游戏工具缺少 rate limit 文档** (interface.md §4)

Schema 完整性要求明确说 "特别是以下工具必须进入工具目录并提供完整的 request/response/error 定义和 rate limit"，但 interface.md 的 MCP 工具表仅列出了工具名和用途——没有 rate limit。Auth 工具有详细的限速模型（auth.md §10.7），游戏工具也应该有。高频工具如 `swarm_get_snapshot`（每 tick 调用）、`swarm_deploy`（代码更新）、`swarm_explain_last_tick`（调试）的 rate limit 直接影响 agent 的行为模式。

**修复**: 在 interface.md MCP 工具表中添加 rate limit 列。建议:
- 世界查看工具 (snapshot/terrain/objects): 1/tick per player, burst 10
- deploy/validate: 1/5s per player (code_update_cooldown 约束)
- 调试工具 (explain/inspect/profile): 10/tick per player
- 学习工具 (docs/schema/simulate): 60/min per player
- 经济工具: 1/tick per player

**H2. Canonical 请求签名格式定义在 auth.md，SDK 开发者不易发现** (auth.md §5.6)

Canonical serialization 规范（SWARM-REQUEST-V1 格式、字段顺序、body_hash 计算规则）是所有 SDK 实现请求签名的基础——不仅 auth 相关请求，所有 deploy/admin 请求都用同一格式。这个规范埋在 auth.md 的 §5.6，对 TypeScript SDK 开发者、Rust SDK 开发者来说是意料之外的依赖。interface.md 应该有引用。

**修复**: 在 interface.md §4 或 §5 添加 "请求签名" 节引用 auth.md §5.6，或提取 `specs/security/request-signing.md` 作为独立 spec。同时在 SDK 文档中显著链接。

**H3. `swarm_simulate` 工具语义未定义** (interface.md §4.1)

该工具被描述为 "离线模拟：给定快照预测未来 N tick"，这是一个极其强大但危险的 DX 原语。关键问题未回答:
- 模拟是否使用相同的 ECS pipeline（保证确定性）？
- 模拟期间是否执行其他玩家的 WASM？（如果不执行，NPC 行为如何处理？）
- 输入格式是什么——完整的 TickSnapshot？还是简化版？
- 模拟消耗什么配额？tick 内的 fuel budget 还是独立配额？
- 模拟结果是否可复现（同输入 → 同输出）？

如果 AI agent 依赖 `swarm_simulate` 做决策但引擎的模拟语义与实际 tick 不同，会导致系统性策略偏差。

**修复**: 完整定义模拟语义。建议: 模拟运行在隔离的 Bevy World 副本上，不执行其他玩家 WASM（仅 NPC AI 和 ECS Systems），同输入确定同输出。消耗独立模拟配额（如 10 次/分钟），每次最多 100 tick。明确标注 "模拟不含其他玩家行为 —— 仅用于 NPC 场景和基础资源预测"。

**H4. Host function binary ABI 未指定** (interface.md §5.1, engine.md §3.4)

interface.md 定义了 5 个 host function: `host_get_terrain`, `host_get_objects_in_range`, `host_path_find`, `host_get_world_config`, `host_get_world_rules`，全部使用 `out_ptr`/`out_len` 的缓冲区模式。但输出缓冲区的二进制布局没有定义。engine.md §3.4 说 "tick 内 snapshot 和 CommandIntent 的实时传输使用 binary canonical encoding（FlatBuffers）"，但 host function 输出也用 FlatBuffers 吗？还是 JSON 兼容格式？

这直接影响 SDK 实现——TypeScript SDK 需要知道如何解析 `out_ptr` 指向的内存。

**修复**: 在 interface.md §5.1 或独立 spec 中指定 host function ABI。明确每个函数的输出格式（FlatBuffers schema 或规范化的二进制布局）、字节序（little-endian）、对齐规则。提供 C 结构体等价定义供 SDK 实现者参考。

**H5. MCP 错误响应格式未标准化** (interface.md + auth.md)

auth.md §10.6 定义了完善的错误码体系（`invalid_credentials` → 401, `username_taken` → 409 等），但这仅是 auth 域。游戏 MCP 工具的错误格式没有定义——`swarm_deploy` 失败时返回什么？JSON-RPC error object？还是 Swarm 自定义错误？字段名是 `code`/`message`/`data`（JSON-RPC 标准）还是 `error_code`/`error_message`（自定义）？

**修复**: interface.md 应定义统一的 MCP 错误格式。建议采用 JSON-RPC 2.0 标准错误格式（`code`, `message`, `data`），其中 `code` 使用整数，`data` 包含 Swarm 特有的 `error_code` 字符串和机器可读的 `details`。所有 MCP 工具跨域一致。

**H6. WASM 部署 API 的 `module_hash` 计算规范未定义** (interface.md §4.1, gameplay.md §SDK生成与分发)

`swarm_deploy` 接受 WASM 模块，引擎用 `module_hash` 索引和缓存。gameplay.md 说模块编译时嵌入 `target_manifest_hash`，部署时引擎校验。但 `module_hash` 是 hash of what？WASM 字节的 Blake3？包含 metadata section 吗？和 `target_manifest_hash` 是什么关系？如果 agent 用 `swarm_validate_module` 预检通过但 `swarm_deploy` 的 hash 不匹配（因为网络传输或 metadata 剥离），错误信息对 agent 来说很难排查。

**修复**: 在 interface.md 或 specs/reference/ 定义 `module_hash` 的精确计算: `Blake3(raw_wasm_bytes)`（包含所有 custom sections），在 `swarm_deploy` 输入中必须由客户端提供 hash（服务端验证），防止传输损坏和重放。

### Medium

**M1. Snapshot 结构没有从 WASM 玩家视角的定义** (engine.md §3.2, interface.md §5)

engine.md §3.2 说 "快照格式为结构化数据（非纯文本 JSON）"，interface.md §5 说 "SDK 侧通过 `WorldSnapshot` 类型访问"。但 `WorldSnapshot` 的具体字段和结构在哪里？它包括哪些实体类型？可见性过滤如何体现？builder/economy 状态？这对 SDK 开发者来说是每日使用的最核心类型。

**修复**: 在 specs/reference/ 定义 WorldSnapshot 的 schema——可用 FlatBuffers schema 定义，SDK 从此生成。至少包含: 房间列表（每房间地形/实体/建筑/资源点）、玩家经济状态、世界规则快照、可见性过滤说明。

**M2. SDK 缓存失效没有主动通知** (gameplay.md §SDK生成与分发)

gameplay.md 描述了部署时如果 `target_manifest_hash` 不匹配返回错误消息 `"Run \`swarm sdk fetch\` to update."`，但这是被动通知——agent 尝试部署时才发现。如果 agent 持有 stale SDK 编译了代码但没有立即部署（比如在 World 模式 `code_update_window` 等待窗口期），到窗口开放时部署失败才知道 SDK 过期，浪费了等待时间。

**修复**: 在 MCP 工具中添加 `swarm_sdk_hash_changed` SSE 事件，引擎重启或 mods 变更时主动推送 manifest_hash 变更通知给所有已认证连接。或在 `swarm_get_snapshot` 响应中包含当前 `world_manifest_hash`，agent 可在每 tick snapshot 中检测不一致。

**M3. `swarm_explain_last_tick` 输出结构未定** (interface.md §4.1)

调试工具 "解释上 tick 发生了什么" 的输出——是自然语言文本还是结构化数据？如果是结构化（JSON），AI agent 可以程序化解析；如果是文本，就只能人工阅读。当前设计倾向于给 AI agent 用的 MCP 工具应该是结构化输出。

**修复**: 定义为结构化输出: `{ commands_issued: [...], commands_accepted: [...], commands_rejected: [{command, reason}], events: [...], state_changes: [...] }`。同时提供可选的人类可读 summary 字段。

**M4. SDK release 版本与 engine 版本耦合关系不明确** (tech-choices.md §10, gameplay.md §SDK生成与分发)

Rust SDK 和 TS SDK 是独立仓库（`sdk-rust/`, `sdk-ts/`），但 engine ABI 升级会导致旧 SDK 编译的 WASM 不兼容。当前的 `engine_abi_version` 字段在 WASM metadata 中，但 SDK 自身的版本管理与 engine 版本的关系没有明确定义。`swarm_sdk_fetch` 返回的 SDK 如何映射到 `engine_abi_version`？

**修复**: 定义 SDK ↔ Engine 版本兼容性矩阵。建议: `engine_abi_version` 在 engine 编译期硬编码；`swarm_sdk_fetch` 返回的 SDK 包包含其对应的 `engine_abi_version`。`swarm_deploy` 检查 WASM 嵌入的 `engine_abi_version == world.current_abi_version`。

**M5. `swarm_deploy` 的幂等性语义** (engine.md §3.4, interface.md §4.1)

如果 agent 因网络问题重试 `swarm_deploy`（同一个 module_hash），引擎如何处理？auth.md 定义 deploy 使用 FDB version_counter 防重放，但只保证 per-player sequential ordering——不保证幂等。如果第一次 deploy 实际上成功了但响应丢失，agent 重试会消耗 version_counter 并创建一个 redundant deploy record。WASM 预编译缓存可以复用，但 deploy event 的副作用（如 code_update_cost 扣费）是否会重复？

**修复**: 明确 `swarm_deploy` 的幂等性合同: 通过 `idempotency_key` (Blake3(module_hash || version_counter)) 或服务端对同一 module_hash 的幂等检测（同一 tick 内拒绝重复 hash 的 deploy）。费用只扣一次。

**M6. 联邦登录的 MCP flow 对 AI agent 复杂度高** (auth.md §15.2)

跨世界登录需要 9 个步骤，其中步骤 3 "客户端用 World A 证书对应私钥签名 World B 的 federation challenge" 要求 agent 在第一个世界的私钥上下文中签名第二个世界的 challenge。这需要 agent 同时管理两个世界的证书链和私钥引用，并在正确的上下文中执行签名。auth.md 提供了 `swarm_federated_login` MCP 工具，但没有提供 SDK 辅助函数来简化这个多步流程。

**修复**: 在 TS SDK 和 Rust SDK 中提供 `federated_login` 辅助函数，封装 challenge 获取、签名、CSR 提交流程。一个函数调用完成全部 9 步。

### Low

**L1. `swarm_get_server_trust` 与 `swarm_get_schema` 功能边界模糊** (interface.md §4.1)

两个工具都提供 server metadata——前者返回 server_id + CA fingerprint，后者返回 API JSON Schema。对首次接入的 AI agent，不清楚该先调用哪个。可以在 `swarm_get_server_trust` 中同时返回指向 schema/docs 的 URI。

**L2. Arena PvE Challenge 缺少 MCP 查询排行榜的接口** (modes.md §9.1.5, interface.md §4.1)

modes.md 定义了完整的 PvE 评分公式和排行榜机制，但 interface.md 的 MCP 工具表中没有查询 PvE 排行榜的工具。AI agent 在测试算法后无法查询自己排名的提升。

**L3. 证书过期通知依赖 polling** (auth.md §10.9)

certificate 到期通知通过 MCP 响应头 `Swarm-Cert-Expires-In` 和 SSE 事件 `certificate_expiring_soon`（距到期 ≤7 天）传递。但对短期证书（如 AdminCertificate 1h TTL），agent 需要主动 polling 响应头，而 SSE 可能在非 WebSocket 的 MCP 传输中不可用。建议提供 MCP notification 机制或工具 `swarm_check_certificate_status`。

**L4. `swarm_token_refresh` 需要 `client_public_key` 参数但注册流程没有明确说明如何持久化** (auth.md §10.1, §4.2)

第一节注册流程说 "持久化 (username, private_key reference, certificate chain, recovery material)"，但 §14.2 定义 session 绑定 `(player_id, client_public_key)`，`swarm_token_refresh` 需要 `client_public_key` 参数。注册流程的持久化清单应该显式包含 `client_public_key`，否则 agent 在需要 refresh 时会发现缺参数。

---

## Strengths

1. **Deferred Command Model**: `tick(snapshot) → Command[]` 是 API 设计的核心亮点。人类和 AI agent 走完全相同的路径——引擎不关心代码是谁写的。消除了传统 RTS 中 "AI 玩家走特殊 API" 的不公平性。

2. **SDK 自动生成**: 从 world.toml + mods 自动生成 world-specific SDK（含 manifest_hash 校验）是强 DX 模式。防止玩家用错误 SDK 编译的 WASM 部署到不兼容世界，错误信息清晰可操作。

3. **Blake3 单原语**: 哈希、PRNG、代码签名统一为一个原语，审计面最小化，跨平台性能一致（~6 GB/s），无 AES-NI 退化风险。`update_with_seek(seed, offset)` 一行代码替代整个 ChaCha keystream。

4. **三层扩展模型**: Core IDL 冻结（Layer 1）→ world.toml 参数化（Layer 2）→ 自定义类型/Action（Layer 3）——清晰定义了 SDK break 的边界。90% 服主只需要调参（不触动 SDK），深度模组才需要 world-specific SDK。

5. **应用层证书模型**: 不依赖 TLS client certificate，支持 HTTP 不安全传输认证。PoW 防注册滥用，用途隔离证书（ClientAuth/CodeSigning/Admin），设备级吊销。Federation 跨世界信任模型完整。

6. **Canonical Request Signature**: 标准化签名格式（SWARM-REQUEST-V1）覆盖所有敏感操作。字段顺序、body_hash 计算规则、nonce/timestamp 防重放都有精确定义。

7. **i18n 支持**: mod 系统的多语言描述完整（zh/en/ja），Accept-Language 驱动。对全球部署的 MMO 来说是必需的基础设施。

8. **Arena PvE Challenge 评分系统**: 基于 par_time 的效率倍率 + difficulty 倍率的评分公式透明且可复现。相同 (scenario, difficulty, map_seed, player_commands) → 相同结果，支持回放验证。

---

## Consistency Gaps

以下跨文档不一致在 Phase 1 实现前需要对齐:

| # | 不一致 | 位置 A | 位置 B | 影响 |
|---|--------|--------|--------|------|
| G1 | `PlayerId` 在 ECS 中是 `struct Owner(PlayerId)` 但在 auth.md 中是 `u64` | engine.md §3.1 | auth.md §7.1 | SDK 类型定义选择哪个？ |
| G2 | TLS 证书与 Swarm CA 隔离声明: auth.md §5.1 说 "Swarm CA 只用于应用层证书" 但 auth.md §10.5a WebSocket 握手中未提及 TLS 层 | auth.md §5.1 | auth.md §10.5a | WebSocket 升级是否在 HTTPS-only 之上？ |
| G3 | `swarm_register_challenge` 在 interface.md 返回 `PoWChallenge`，在 auth.md §10.2 有完整 response 格式——两者一致但 interface.md 缺少详细 schema 引用 | interface.md §4.1 | auth.md §10.2 | AI agent 函数调用需要完整 schema，interface.md 应提供 ref |
| G4 | "MANUAL_CONTROL 不开放" 在 gameplay.md §8.2 Drone 控制中声明，但 engine.md 和 interface.md 没有对应 API 限制文档 | gameplay.md §8.2 | engine.md, interface.md | 实现者可能漏掉此约束，需要 API contract 中显式拒绝 manual control Command |
| G5 | `code_update_cooldown` 默认 5 tick (gameplay.md §8.2) 但 World 默认值表格说是 0（免费）| gameplay.md §8.2 | gameplay.md §8.6 | World 模式 deploy 频率该用哪个？ |

---

## Algorithmic / Data-Flow Risks

**R1. Tick 内 Snapshot 构建与 WASM 执行的竞态**: engine.md §3.2 定义快照在阶段一构建（一次性），然后并行分发。但快照构建包含 "序列化完整世界状态"——如果 500 player × ~64KB 分片 × 序列化 = 32MB 数据序列化，在 2500ms COLLECT budget 内需要 <50ms 构建。如果世界状态有 50,000 entity，序列化瓶颈在单线程？设计说 "按房间分片"，但首次构建仍是全量。Tier 1 的深拷贝全量快照性能需要基准测试验证。

**R2. WASM 预编译缓存失效**: engine.md §3.4 说 "编译后模块按 (module_hash, wasmtime_version) 缓存"。如果 500 玩家频繁部署新代码，每次新 module_hash 触发编译——Wasmtime Cranelift 编译延迟 ~50-200ms，在 2500ms per-player budget 外。需要明确编译是同步还是异步、是否计入 player budget。

**R3. Phase 2a inline 命令循环的复杂度**: engine.md §3.2 说 Phase 2a "对每条指令（按洗牌后顺序 + 玩家内 sequence 排序）" 逐条 inline 应用。如果 500 player × 100 drone = 50,000 drone，每个 drone 返回 ~5 command = 250,000 commands/tick。逐条校验+应用到 Bevy World 的延迟在 Rust 中可能可控，但需要基准测试。如果 250,000 × (validate + apply) > EXECUTE budget，需要批量优化。

**R4. Dragonfly 非权威缓存与 FDB 权威源的滞后窗口**: engine.md §3.2 说 Dragonfly 缓存 "允许 ≤2 tick 滞后"。但 interface.md 中 `swarm_get_snapshot`（世界查看工具）如果从 Dragonfly 读缓存可能拿到 stale 数据——AI agent 基于过时 snapshot 做出决策再 deploy，产生"看到 A 但实际是 A-2 tick" 的不一致。需要明确 `swarm_get_snapshot` 的 freshness guarantee。

---

## Recommendations

1. **优先级排序**: C1 (`swarm_sdk_fetch` 定义) 和 C2 (Command schema) 必须在任何 SDK 实现前解决。两者是全部 API 面的地基。

2. **统一错误格式**: 在 interface.md 中定义一个全局 MCP 错误格式节，所有工具引用它。auth.md 的错误码体系可以保留但需要映射到统一格式。

3. **创建 specs/reference/command-schema.md**: Command 枚举 + 字段定义 + 验证规则 + rejection reasons。这是所有 SDK codegen 的输入。

4. **创建 specs/reference/snapshot-schema.md**: WorldSnapshot 的 FlatBuffers schema 定义。SDK 类型从此生成。

5. **MCP 工具目录化**: 将 interface.md 的工具表升级为工具目录（类似 auth.md §10.1），每个工具有 inputSchema/outputSchema/errors/rate_limit 四要素。

6. **为 AI agent 提供 onboarding 脚本**: 基于 auth.md 附录 A 的 Python PoW 示例，提供一个完整的 `swarm_agent_onboard.py` 脚本——challenge → PoW → CSR → deploy test WASM → verify。降低 AI agent 接入门槛。

7. **SDK 辅助函数**: TS SDK 和 Rust SDK 应提供 `sign_request(method, path, body, certificate, private_key)`、`federated_login(remote_cert, remote_key, target_world)` 等封装 canonical serialization 的高级 API。当前所有 SDK 开发者需要自己实现 canonical format（见 R4 风险）。

---

## Summary

16 个发现 (2 Critical, 6 High, 6 Medium, 2 Low) + 5 个跨文档一致性缺口 + 4 个算法/数据流风险。

核心问题: API 合同（Command schema、host function ABI）定义不足——这是 SDK 实现者每天面对的核心接口，必须在 Phase 1 实现前冻结为正式 spec。SDK 自动生成管线（world.toml → IDL → codegen → SDK）的 DX 方向正确，但管线输入端（IDL）的 schema 需要先补全。

Canonical request signing 格式完善但位置不当——SDK 开发者不应在 auth.md 中寻找签名规范。MCP 错误格式需要跨域统一（目前仅 auth 域有定义）。
