# R33 API/DX Review — DeepSeek V4 Pro

## Verdict

**REQUEST_MAJOR_CHANGES** — 3 Critical issues: (B1) host_get_random 在 api-registry.md 中存在但不在源 IDL 中，(B2) MCP 工具计数跨 4 个文档三处不一致，(B3) MainActionQuotaExceeded 非 canonical 拒绝码。3 High 项涉及 codegen 计数漂移、mcp-tools.md 计数陈旧、SwarmError envelope 格式 IDL/Registry 冲突。修复后方可 APPROVE。

---

## Critical (必须修复，否则 BLOCK) (B1..B3)

### B1 — host_get_random: Registry 有但 IDL 无 (单事实源破坏)

- **文件/行号**: api-registry.md §4.1 L464 vs game_api.idl.yaml §4 (host_functions L1508-1571)
- **问题**: `host_get_random` 出现在 api-registry.md §4.1 的函数签名表中（第 6 号函数），但**不在** game_api.idl.yaml 的 `host_functions` 段中。IDL 声明 `total_functions: 5`（L1510），实际列出 5 个函数（不含 host_get_random）。api-registry.md 是 IDL 的生成产物，不应包含 IDL 中没有的数据。同时 interface.md §5.1（L72-85）和 host-functions.md（L11-18）也仅列出 5 个函数，不含 host_get_random。
- **影响**: api-registry.md 作为「IDL 自动生成产物」声明的原则被打破——有 6 个 host function 的 registry 和 5 个的 IDL 源无法共存。SDK codegen 会从 IDL 生成 stub，缺失 host_get_random → 玩家无法获得确定性随机数。这直接违反「IDL 是单一事实源」的核心原则。
- **修复建议**: 二选一——(a) 将 host_get_random 完整定义（含 ABI signature、budget 10/tick、max output 256 bytes、per-call fuel 200+10/32 bytes）写回 game_api.idl.yaml 的 `host_functions` 段，然后重新生成 api-registry.md；(b) 如果 host_get_random 尚未确定设计，从 api-registry.md 中移除。

### B2 — MCP 工具计数：跨 4 个文档三处不一致

- **文件/行号**: 
  - api-registry.md §3.2 L277 header: "57" vs 实际计数 59（含 swarm_auth_check alias）
  - game_api.idl.yaml §3: 多个 section header 错误 + total_tools: 57 vs 实际 58
  - mcp-tools.md L15-25: 多个分组计数与 registry 不一致
  - codegen.md L27: "当前 56 active"
- **问题**: 
  - **game_api.idl.yaml section headers 未更新**: Play header "14 tools" (L734) 实际有 16 个（v0.4.0 +2: swarm_profile + swarm_get_available_actions 后未更新 header）；Deploy header "6 tools" (L977) 实际有 7 个（swarm_list_modules 新增后未更新）；Debug header "7 tools" (L1092) 实际有 8 个（swarm_explain_last_tick 新增后未更新）。
  - game_api.idl.yaml 实际活跃工具数: 11(Onboarding) + 2(Auth) + 16(Play) + 7(Deploy) + 8(Debug) + 6(Admin) + 1(SDK) + 5(Arena) + 2(Resources) = **58**。但 `total_tools` 声明为 **57**（L502）。
  - api-registry.md Game API 表实际工具数: 11+3(含 swarm_auth_check)+16(Play)+7+8+6+1+5+2 = **59**。但 header 声明为 **57**（L277）。
  - mcp-tools.md: Onboarding 10(实际 11)、Arena 4(实际 5，v0.4.1 移入 swarm_get_leaderboard)、Game API subtotal 56(应为 57+)。Auth 2(实际 api-registry 含 alias=3)。
  - codegen.md L27: "MCP tool 数量 (当前 56 active)"。
- **影响**: 4 个文档各有不同的工具计数声明。CI diff check 无法通过——codegen 产物与源 IDL 的不一致会导致 PR 被阻塞。开发者无法确定准确的 API surface。
- **修复建议**: (a) 更新 game_api.idl.yaml 所有 section header 和 total_tools 为实际计数；(b) 重新生成 api-registry.md 并更新 header 计数；(c) 更新 mcp-tools.md 各分组计数与实际一致；(d) 更新 codegen.md L27 为正确的 active 工具数；(e) 在 CI 中添加计数一致性 lint（检测 header 声明与实际列表长度的偏差）。

### B3 — MainActionQuotaExceeded: 非 canonical 拒绝码

- **文件/行号**: 02-command-validation.md §5.1 L547 vs api-registry.md §2 (RejectionReason)
- **问题**: 02-command-validation.md §5.1「拒绝码」表中使用 `MainActionQuotaExceeded` 作为正式拒绝码：`"本 tick main action 配额已用尽 | 每 drone 每 tick 最多 1 个 main action；第 2 个及以后返回此码"`。但此码**不在** api-registry.md §2 的 47 canonical RejectionReason 中——不在 game_api.idl.yaml 的 rejection_reason variants 中。根据 D2/B 设计决策，详细上下文应通过 debug_detail 传递而非新增 wire enum 变体。此码要么应映射到 canonical RejectionReason（如 CooldownActive 或 NotEnoughBodyParts），要么应正式注册为 canonical code。
- **影响**: 实现者在 command-validation 层看到 `MainActionQuotaExceeded` 作为拒绝码，但该码不在 wire enum 中——无法被 SDK 生成的 typed exception 捕获。要么引擎必须映射到 canonical code，要么客户端收到非规范错误码。
- **修复建议**: 二选一——(a) 将 `MainActionQuotaExceeded` 映射到 canonical `CooldownActive`（最接近语义：drone 已耗尽其 "main action slot"）+ 通过 debug_detail 传递具体信息；(b) 将 `MainActionQuotaExceeded` 注册为 game_api.idl.yaml rejection_reason variants 的第 36 个 canonical code。

---

## High (强烈建议修复) (H1..H3)

### H1 — mcp-tools.md 多处计数陈旧

- **文件/行号**: mcp-tools.md L15-25 vs api-registry.md §3
- **问题**: (a) L15 Onboarding: 10 → 应为 11（新增 swarm_get_objectives 后未更新）；(b) L18 Auth: 2 → api-registry.md 含 swarm_auth_check alias 共 3；(c) L24 Arena: 4 → 应为 5（v0.4.1 将 swarm_get_leaderboard 从 Play 移至 Arena）；(d) L26 Game API subtotal: 56 → api-registry.md header 为 57、实际 58-59。
- **影响**: mcp-tools.md 是开发者快速查阅的工具概述，计数错误导致信任度下降。
- **修复建议**: 统一从 api-registry.md 同步所有计数。或更好的方案——在 mcp-tools.md 中不声明硬编码计数，改为链接到 registry 的动态计数。

### H2 — codegen.md 硬编码计数漂移

- **文件/行号**: codegen.md L27-L29 vs api-registry.md
- **问题**: codegen.md 声明「禁止手写的数值」但自身包含三个硬编码计数：(a) L27 "MCP tool 数量 (当前 56 active)" → api-registry.md 为 57；(b) L29 "Host function 数量 (当前 5)" → api-registry.md §4.1 实际为 6；(c) L26 注释承认「本文档自身为手工维护」但未给出自动校验这些计数的方案。
- **影响**: codegen.md 作为 codegen pipeline 规范文档，自身计数与生成产物不一致——损害 codegen 链的信任链。
- **修复建议**: (a) 更新所有计数为当前值；(b) 将 codegen.md 中的硬编码计数替换为 CI 自动注入的占位符（类似 api-registry.md 的 IDL YAML 自动生成机制）；(c) 在 CI check 中加入 codegen.md 计数与 IDL 源的一致性校验。

### H3 — SwarmError Envelope: IDL vs Registry 格式冲突

- **文件/行号**: game_api.idl.yaml §8 (L1744-1761) vs api-registry.md §8 (L727-761)
- **问题**: 两个文档对 SwarmError JSON-RPC envelope 的定义**显著不同**：
  - **error.code**: IDL 定义 `code: "RejectionReason (string)"` —— 即 error.code **就是** rejection reason。Registry 定义 `code: -32000`（固定数值）+ `data.rejection_reason` 承载 canonical enum。
  - **error.data 字段**: IDL 含 `rejection_detail`（max 512 bytes）+ `debug_detail`。Registry 含 `rejection_reason` + `debug_detail` + `retry_allowed` + `idempotency_key` + `retry_after_tick` —— 多出 3 个机器可读字段，且没有 `rejection_detail`。
  - 这两套格式**不兼容**——SDK 根据哪一版生成 typed exception？
- **影响**: SDK codegen 若按 IDL 生成，客户端解析 error.code 为 string RejectionReason；若按 Registry 生成，客户端解析 error.data.rejection_reason 并忽略 fixed error.code=-32000。两者不能同时存在。
- **修复建议**: 以 IDL 为源统一——将 api-registry.md §8 的 envelope 结构更新为与 game_api.idl.yaml §8 一致。若 `retry_allowed`/`idempotency_key`/`retry_after_tick` 是必须保留的字段，将其添加到 IDL 的 error.data schema 中。确保 error.code 语义只有一种权威定义。

---

## Medium (建议关注) (M1..M5)

### M1 — interface.md host function 列表缺少 host_get_random

- **文件/行号**: interface.md §5.1 L72-85 vs api-registry.md §4.1 L457-466
- **问题**: interface.md 列出 5 个 host function（不含 host_get_random），但 api-registry.md 列出 6 个（含 host_get_random）。若 B1 选择方案 (a)（添加 host_get_random 到 IDL），interface.md 也需更新。
- **修复建议**: 与 B1 修复联动——B1 选 (a) 则同步更新 interface.md；选 (b) 则忽略此项。

### M2 — game_api.idl.yaml section header 计数错误蔓延

- **文件/行号**: game_api.idl.yaml L734 (Play:14→16), L977 (Deploy:6→7), L1092 (Debug:7→8), L502 (total_tools:57→58)
- **问题**: 三个 category 的 section header 手动声明计数与实际列表长度不一致（见 B2）。这些 header 是 codegen 和人工检查的依据——错误会持续蔓延到所有引用文档。
- **修复建议**: 在 CI 中增加 IDL section header 一致性校验：检查每个 `category` 对应的 section header 中声明的数字是否与实际 YAML 列表条目数一致。若 codegen 自动生成这些 header，则改为自动填入。

### M3 — api-registry.md Play 分组 header 与实际列表不一致

- **文件/行号**: api-registry.md §3.2 L305 header "(15)" vs 实际 16 tools
- **问题**: Play 分组实际列出了 16 个工具（含 v0.4.0 新增的 swarm_profile 和 swarm_get_available_actions），但 section header 声明为 "(15)"。这导致 header 级合计 (57) 与实际合计 (59) 存在 2 的偏差。
- **修复建议**: 重新生成 api-registry.md 并验证所有 section header 计数与对应的 YAML 列表长度一致。

### M4 — 09-snapshot-contract.md 使用非 canonical 错误分类名

- **文件/行号**: 09-snapshot-contract.md §4.2 L310-311 vs api-registry.md §2
- **问题**: 09-snapshot-contract.md 在 safe hint ladder 中使用 `PermissionDenied` 和 `InvalidTarget` 作为错误类别名。这两个名称不在 canonical RejectionReason enum 中。虽然它们在该文档中用作概念性错误分类（非 wire enum），但名称与 canonical `NotOwner`/`NotAuthorized`（权限）和 `ObjectNotFound`/`NotStructure`/`NotController`（无效目标）重叠，可能造成混淆。
- **修复建议**: 将 snapshot-contract 中的错误类别名与 canonical RejectionReason 对齐——例如 `PermissionDenied` → `NotOwner`/`NotAuthorized`，`InvalidTarget` → `ObjectNotFound`。

### M5 — MilliUnits 跨 IDL 类型注册不一致

- **文件/行号**: economy.idl.yaml §1 types (L37-45) vs game_api.idl.yaml §0 type_registry (L13-53) vs api-registry.md §0 (L20-34)
- **问题**: `MilliUnits` 类型仅在 economy.idl.yaml 和 api-registry.md 中定义，不在 game_api.idl.yaml 的 `type_registry` 中。如果 Fixed-Point Type Registry 旨在成为跨 IDL 的综合类型注册表，则 MilliUnits 也应在 game_api.idl.yaml 中注册。
- **影响**: SDK codegen 可能无法从 game_api.idl.yaml 中推导出 MilliUnits 类型。
- **修复建议**: 将 MilliUnits 添加到 game_api.idl.yaml 的 type_registry.fixed_point_types 中，或明确 game_api.idl.yaml 的 type_registry 仅覆盖自身使用的类型（并文档化这种分工）。

---

## Low / Nits (可选改进) (L1..L4)

### L1 — 02-command-validation.md 拒绝响应表使用混合标记风格

- **文件/行号**: 02-command-validation.md §5.1 L541-548
- **问题**: §5.1 拒绝码表中混合使用 canonical code（NotVisibleOrNotFound, OutOfRange）、`(debug_detail)` 占位符、和非 canonical 的 MainActionQuotaExceeded。风格不一致——`(debug_detail)` 标记在表中作为「失败码」出现但实际不是错误码而是 meta 指示符。应统一：所有失败码要么是 canonical RejectionReason，要么通过 debug_detail 传递。
- **修复建议**: 在 B3 修复后，将所有 `(debug_detail)` 占位符替换为对应的 canonical RejectionReason + 在表外附注中说明 debug_detail 的具体内容。

### L2 — commands.md Recycle 校验与 registry 不一致

- **文件/行号**: commands.md L116-120 vs api-registry.md §1.1 L63 vs game_api.idl.yaml L179-186
- **问题**: commands.md Recycle 校验规则说「drone 在 Spawn 1 格内」——但 game_api.idl.yaml Recycle 描述为 "self-action — no spawn proximity required"，api-registry.md 也说 "self-action"。commands.md 可能保留了旧版设计。
- **修复建议**: 更新 commands.md Recycle 校验规则为「self-action — 无 Spawn 距离要求」，与 IDL 和 registry 一致。

### L3 — game_api.idl.yaml swarm_auth_login/refresh 缺少 device_id/device_name 输入字段

- **文件/行号**: game_api.idl.yaml §§ swarm_auth_login (L702-718), swarm_auth_refresh (L719-731) vs auth_api.idl.yaml §§ swarm_auth_login (L30-56), swarm_auth_refresh (L58-78)
- **问题**: game_api.idl.yaml 中的 swarm_auth_login 简化版 input_schema 缺少 `device_id` 和 `device_name` 字段（auth_api.idl.yaml canonical 版有），且 output_schema 缺少 `refresh_token`, `session_id`。game_api.idl.yaml swarm_auth_refresh 使用 `token` 作为输入参数名，但 auth_api.idl.yaml canonical 版使用 `refresh_token`——语义不同。简化版与 canonical 版的 schema 差异在 IDL 中被标注为 `schema_source=auth_api` + `alias_of` 但实际 schema 字段仍不一致——codegen 如何从 canonical source 生成而忽略简化版的错误字段？
- **修复建议**: 明确标注 game_api IDL 中的 auth tools 为 `schema_derived_from: auth_api.<tool>` 并完全复刻 canonical schema，或在 game_api IDL 中移除 auth tools 的内联 schema 改为 pure alias reference。

### L4 — 02-command-validation.md §7.1 退还表有重复行

- **文件/行号**: 02-command-validation.md §7.1 L626-637
- **问题**: 退还表中 `InsufficientResource` 出现两次：(a) L628 "退 50% fuel — 竞争导致"；(b) L634 "不退 — 玩家应计算资源"。相同 RejectionReason 有两种不同 refund 策略——语义冲突。第二条应指不同的条件（如玩家自身 InsufficientResource vs 目标资源不足），但表格式未区分这两者。
- **修复建议**: 拆分 InsufficientResource 的两个语义——(a) 竞争型退款（目标资源被他人抢走 → 50% refund）；(b) 自检型不退（玩家自身资源不足 → 0% refund）。用不同行清晰表述。

---

## Strengths (设计亮点)

1. **D2/B debug_detail 机制**：47 canonical wire enum + 512 bytes debug_detail 的设计在 wire 稳定性与调试丰富性之间取得了优秀平衡。detail_level（competitive/practice/training）三级控制防止竞技信息泄露——这是 MMO RTS 领域少见的深思熟虑。

2. **Security Columns 体系**：5 个安全列（required_scope, subject_source, replay_class, visibility_filter, rate_limit_key）对每个 MCP 工具提供完整的访问控制、重放确定性、可见性过滤——这是 API 设计的典范，SDK codegen 可据此生成 type-safe 的权限检查。

3. **CommandAction 枚举 21 变体**：11 core + 2 economy_operation + 8 special_attack 的分层设计清晰，CustomActionRegistry 为扩展留下了正确路径（不做 enum explosion）。

4. **Rhai Mod ABI**：rhai-mod-abi.md 是本次评审中**最完整的合同文档**——9 个 hook、8 个 query、5 个 action、12 个 capability、6 级错误降级、Semver 兼容性、Ed25519 签名验证、实现清单 10 条。每条都是可直接实现的合同。这是 Swarm 文档中最值得其他文档学习的范例。

5. **host-functions.md 设计合同清晰**："所有游戏状态变更必须通过 tick() → Command[] JSON 延迟模型提交。Host function 只提供只读查询。"——这条合同在整个文档体系中一致贯彻（interface.md、host-functions.md、commands.md 无一违反）。

---

## CrossCheck — 需要跨方向检查

- **CX-1**: host_get_random 作为确定性随机源——其 domain separation `(tick_seed, player_id, drone_id, sequence)` 是否正确覆盖所有 replay 场景？→ 建议 **Engine/Determinism 方向** 检查 [host_get_random seed derivation 与 snapshot contract 的 replay 兼容性]

- **CX-2**: api-registry.md §4.1 的 host_get_random 输出上限 256 bytes，per-call fuel 200+10/32 bytes——这些数值是否与 game_api.idl.yaml 和 wasm-sandbox spec 一致（后者可能未包含这些预算值）？→ 建议 **Sandbox 方向** 检查 [WASM host function 预算枚举是否覆盖 host_get_random]

- **CX-3**: swarm_auth_check 在 game_api.idl.yaml 中不存在但在 api-registry.md 中以 alias 形式出现——auth_api.idl.yaml 的 canonical swarm_auth_check 是否被 MCP gateway 正确路由？→ 建议 **Auth/Gateway 方向** 检查 [swarm_auth_check 的 MCP 路由是否从 auth_api 还是 game_api 注册]

- **CX-4**: MainActionQuotaExceeded 作为 main action 配额限制——这是 gameplay 层的设计决策，「每 drone 每 tick 最多 1 main action」。→ 建议 **Gameplay 方向** 检查 [main action quota 机制是否在 gameplay spec 中有完整定义，以及其与 special_attack 的互斥性]

- **CX-5**: economy.idl.yaml 和 api-registry.md 中 AlliedTransfer 拦截窗口（tick 150-200）及拦截成功率公式（60% base + part bonus - escort penalty）——09-snapshot-contract.md 记录了这些规则，但 API contract 是否需要暴露拦截相关的 MCP 事件？→ 建议 **Security 方向** 检查 [拦截事件的可见性约束——发送/接收/攻击三方收到的通知是否存在信息泄露]