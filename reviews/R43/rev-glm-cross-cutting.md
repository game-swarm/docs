# R43 独立评审报告 — 跨领域评审员 (glm)

**评审范围**: design/ (README, auth, engine, architecture, interface, tech-choices) + specs/reference/ (api-registry, auth_api.idl, codegen, commands, economy.idl, game_api.idl, host-functions, mcp-tools, special-attack-table)

**评审视角**: 跨模块数据流一致性、接口契约对齐、术语/概念跨文档漂移、抽象分层合理性、API 边界直觉性。

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在多个 Critical 级别的 IDL 与 Registry/Design 之间的直接数值冲突和 schema 分叉。这些不是风格问题——是 codegen CI 必然失败或产出错误 SDK 的硬性矛盾。在 IDL（机器可读源）与 Registry（设计权威源）之间存在系统性漂移，表明 codegen 单事实源契约已断裂。

---

## 2. 发现的问题

### Critical

**C1: Host Function 数量冲突 — IDL 缺失 host_get_fuel_remaining**

- 文件: `game_api.idl.yaml` §4 (line 1578: `total_functions: 6`) vs `api-registry.md` §4 (7 函数) vs `host-functions.md` (7 函数)
- 问题: `game_api.idl.yaml` 声明 `total_functions: 6` 且函数列表中缺失 `host_get_fuel_remaining`。Registry 和 host-functions.md 均列出 7 个函数（含 `host_get_fuel_remaining`）。
- 影响: codegen 从 IDL 生成 SDK 时不会生成 `host_get_fuel_remaining` 绑定，但 Registry 和 reference 文档引用了该函数。玩家 SDK 缺少 fuel 查询能力。
- 修复: 在 `game_api.idl.yaml` §4 `host_functions.functions` 中补充 `host_get_fuel_remaining` 条目（index 7, return type u64, base fuel 20），并更新 `total_functions: 7`。

**C2: RejectionReason canonical code 总数冲突 — IDL 35 vs Registry 48**

- 文件: `game_api.idl.yaml` §2 (line 335: `total_canonical_codes: 35`) vs `api-registry.md` §2 ("48 codes") vs `auth_api.idl.yaml` §5 (`total_canonical_codes: 12`)
- 问题: IDL 声明 35 个 game 侧 codes；auth IDL 声明 12 个 auth codes。35+12=47，但 Registry 声明 48。Registry §2.5 的 Auth 层列出 11 个 codes（#39–#48），但 #48 `NotEligible` 的来源 IDL 标注为 `game_api` 而非 `auth_api`——归类与计数自相矛盾。
- 影响: CI codegen `--check` 必然失败。Replay 确定性依赖 RejectionReason registry version 对齐，计数不一致意味着 wire enum 不稳定。
- 修复: 统一三方计数。明确 `NotEligible` 归属（game_api 还是 auth_api），修正 IDL `total_canonical_codes` 使 35（或修正后的 game 数）+ 12 = Registry 声明数。

**C3: Per-player drone cap 数值冲突 — IDL 500 vs Registry/Engine 50**

- 文件: `game_api.idl.yaml` §5 (line 1684: `per_player_drone_cap: 500`) vs `api-registry.md` §5.1 ("50 (per-room per-player baseline)") vs `design/engine.md` §3.4.2 ("50 (per-room per-player baseline)")
- 问题: IDL 写 500，Registry 和 engine.md 均写 50。差 10 倍。
- 影响: 容量合同和房间 drone cap 的核心数值。IDL 驱动 SDK 生成和 CI 校验，500 会直接进入代码和 world.toml 默认值。
- 修复: IDL 改为 `per_player_drone_cap: 50`，添加 `scope: per_room_per_player` 注释。

**C4: Deploy 输入 schema 分叉 — Registry 声明 deploy_mutation 完整字段，IDL 仅有 wasm_bytes**

- 文件: `api-registry.md` §3.2 Deploy (`swarm_deploy` input: `{player_id, drone_id, deploy_payload, code_signature, certificate_id, version_counter, metadata}`) vs `game_api.idl.yaml` §3 (input_schema: `{player_id, drone_id, wasm_bytes, metadata}`)
- 问题: IDL 缺失 `deploy_payload`、`code_signature`、`certificate_id`、`version_counter` 四个字段。Registry §11 描述 deploy_mutation 同步提交语义需要这些字段，`auth_api.idl.yaml` §4a 定义了 SWARM-DEPLOY-V1 签名 payload 绑定 `certificate_id` 和 `redb_version_counter_predicted`。IDL 不提供这些字段意味着 codegen 生成的 SDK deploy 函数签名不匹配实际协议。
- 影响: 部署安全链条断裂——CodeSigningCertificate 绑定、replay 防重放 counter、签名验证均无法通过 SDK 执行。
- 修复: IDL `swarm_deploy.input_schema` 补齐 Registry 声明的字段，与 `auth_api.idl.yaml` §4a SWARM-DEPLOY-V1 payload 字段对齐。

### High

**H1: SwarmError error.code 类型冲突 — IDL 写 string vs Registry/Interface 写 numeric**

- 文件: `game_api.idl.yaml` §8 (line 1834: `code: "RejectionReason (string)"`, reserved_code usage: "specific errors use error.code string") vs `api-registry.md` §8 ("error.code 为 numeric code；Swarm application error 固定使用 -32000") vs `design/interface.md` §5.6 vs `mcp-tools.md` (均对齐 Registry: numeric -32000 + rejection_reason in error.data)
- 问题: IDL 定义的 error.code 是 RejectionReason 字符串；Registry 和所有设计文档定义为 numeric -32000 + 字符串放入 `error.data.rejection_reason`。这是根本性的 wire format 分叉。
- 影响: SDK 生成的 error 解析逻辑完全不同——SDK 期望 string code 还是 numeric code？JSON-RPC 2.0 合规性也受影响（JSON-RPC 标准要求 error.code 为 number）。
- 修复: IDL §8 改为 `code: i32 (numeric, -32000 for Swarm errors)`，将 rejection_reason 移入 `error.data.rejection_reason`。

**H2: Cert 类型与 auth.md 设计冲突 — IDL 定义 3 个 cert type 条目含 admin 独立类型**

- 文件: `auth_api.idl.yaml` §3 `certificate_types.types`（3 条目：2× ClientAuthCertificate + 1× CodeSigningCertificate，第三条 ClientAuthCertificate 带 admin audience）vs `design/auth.md` §4.2（"Admin 操作 = ClientAuthCertificate + admin scope flag（不需要独立证书类型）"）
- 问题: IDL 将 admin 证书列为独立的 `ClientAuthCertificate` 条目（audience 含 admin_id，TTL 15min-1h，renewal manual only），但 auth.md 明确裁定 admin 不需要独立证书类型。ID L 还在 description 中提到 "Intermediate CA"，而 auth.md §4.1 明确规定单层 CA（不分 Root/Intermediate）。
- 影响: 认证模型分层与设计裁决冲突。codegen 会生成 admin 证书类型，增加协议复杂度。
- 修复: IDL 移除第三个 admin ClientAuthCertificate 条目；description 中删除 "Intermediate CA" 引用，改为 "Server CA"。

**H3: ClientAuthCertificate TTL 冲突 — auth.md 24h vs IDL/Registry 15min-180d**

- 文件: `design/auth.md` §4.2 (ClientAuthCertificate TTL: "24h") vs `auth_api.idl.yaml` §3 ("15 min–180 days") vs `api-registry.md` §5.8/§9 ("15 min–180 days")
- 问题: auth.md 写 24h，但 IDL 和 Registry 写 15min-180d。这是最常见的认证证书类型——TTL 差异影响安全模型和 renew 频率。
- 影响: 24h 是单一值，15min-180d 是范围。auth.md 作为设计权威源应在 IDL 中反映。180 天 TTL 的 ClientAuthCertificate 在安全上值得质疑。
- 修复: 统一为范围表达式并明确默认值。如果设计意图是 24h 默认但 world.toml 可配，auth.md 应写 "默认 24h，world.toml 可配范围"。D-item 需用户裁决：ClientAuthCertificate 的合理 TTL 上限是多少？

**H4: host_get_random sequence 参数类型冲突 — IDL u32 vs Registry u64**

- 文件: `game_api.idl.yaml` §4 (line 1642: `abi_signature: "(sequence: u32, ...)"`) vs `api-registry.md` §4.1 (`(sequence: u64, ...)`) vs `host-functions.md` (`(sequence: u64, ...)`)
- 问题: IDL 用 u32，Registry 和 reference 用 u64。u32 sequence 在高 tick 数场景下溢出风险（4G 调用上限）。
- 影响: WASM ABI 直接暴露给玩家代码——类型不匹配导致跨语言 SDK 生成错误 binding。
- 修复: IDL 改为 `u64`，与 Registry 对齐。

### Medium

**M1: ActionRegistry index 与 CommandAction::Action index 冲突 — 均为 22**

- 文件: `game_api.idl.yaml` §1 (CommandAction `Action` index: 22) vs §1 `action_registry.vanilla_actions` (`Fortify` index: 22) vs `special-attack-table.md` (Fortify IDL Index: 22)
- 问题: 虽然分属不同命名空间（CommandAction vs ActionRegistry），index 22 同时被 `Action`（dispatch 入口）和 `Fortify`（vanilla action）占用。`api-registry.md` §1.3 列 Action #22，§1.4 引用 Fortify index 22。
- 影响: 实现中若用单一 enum 或 lookup table 索引，22 会碰撞。跨文档引用时 "index 22" 歧义。低概率但高后果的 bug 源。
- 修复: CommandAction `Action` 的 index 应在非 ActionRegistry 范围（如保持 22 但明确它是 CommandAction namespace），或将 ActionRegistry vanilla action index 偏移到独立区间。建议文档中明确标注 namespace 前缀（如 `CA-22` vs `AR-22`）。

**M2: Auth IDL 内部 device cap 自相矛盾 — per_player_limits 5 vs device_limits 10**

- 文件: `auth_api.idl.yaml` §3 `per_player_limits` (max_active_devices: 5) vs §7 `auth_rate_limits.device_limits` (max_devices_per_player: 10)
- 问题: 同一 IDL 文件内两处声明设备上限：5 vs 10。`api-registry.md` §5.8 取 5（"Max active devices per player: 5"）。
- 影响: codegen 生成两个不同的常量值。设备注册拒绝逻辑不确定。
- 修复: 统一为 5（与 Registry 对齐），或明确区分 "registered devices" (10) vs "active certificates" (5/10) 的语义。

**M3: CSR challenge difficulty 默认值冲突 — IDL 20 vs Registry 24**

- 文件: `auth_api.idl.yaml` §7 (`csr_challenge_default_difficulty: 20`) vs `api-registry.md` §5.8 ("CSR challenge default difficulty: 24 bits") vs §3.3 ("默认 24 bits")
- 问题: IDL 默认难度 20 bits，Registry 说 24 bits。min/max (20/32) 一致但默认值不同。
- 影响: PoW 难度直接影响注册延迟和反滥用效果。20 vs 24 bits 差 16 倍计算量。
- 修复: IDL 改为 `csr_challenge_default_difficulty: 24`。

**M4: Game API IDL 版本号落后于 Registry — IDL 0.4.0 vs Registry 0.5.0**

- 文件: `game_api.idl.yaml` (line 8: `api_version: "0.4.0"`) vs `api-registry.md` (line 7: `0.5.0 (game_api)`)
- 问题: Registry 声明 0.5.0（R35 D3 CommandAction 泛化），但 IDL 仍在 0.4.0（changelog 最新到 0.4.2）。Registry changelog 的 0.5.0 条目描述的变更（combat action 移入 ActionRegistry）在 IDL 中已有体现，说明 IDL 内容已更新但版本号未 bump。
- 影响: 版本号不匹配导致 TickTrace `api_version` 字段歧义——replay 时无法确定规则集版本。
- 修复: IDL `api_version` 更新为 `"0.5.0"`，添加 0.5.0 changelog 条目。

**M5: Auth API 版本号在 Registry 中落后 — Registry 0.1.0 vs IDL 0.2.0**

- 文件: `api-registry.md` (line 7: `0.1.0 (auth_api)`) vs `auth_api.idl.yaml` (line 13: `api_version: "0.2.0"`)
- 问题: IDL 已 bump 到 0.2.0（R33 B4 证书链重写），但 Registry header 仍写 0.1.0。Registry §3.3 内容已经是证书链模型的 12 个工具（与 0.2.0 匹配），说明是 header 遗漏。
- 影响: 版本号不一致破坏 codegen 版本同步。
- 修复: Registry header 更新为 `0.2.0 (auth_api)`。

**M6: host_get_random fuel 成本冲突 — IDL 100+1/byte vs Registry 200+10/32bytes**

- 文件: `game_api.idl.yaml` §4 (`host_get_random` base: 100, incremental: "+1/output byte") vs `api-registry.md` §4.4 (base: 200, incremental: "+10/32 bytes")
- 问题: 基础 fuel 差 2 倍（100 vs 200），增量计算方式完全不同（1/byte vs 10/32bytes≈0.31/byte）。
- 影响: fuel 计量直接影响玩家 WASM 执行预算。不匹配导致同一模块在不同实现下消耗不同 fuel，破坏确定性。
- 修复: IDL 改为 base 200, incremental "+10/32 bytes"，与 Registry 对齐。

**M7: WebSocket 安全模型字段集冲突**

- 文件: `game_api.idl.yaml` §3 `websocket_security.agent_ws_signature` (covers: `(method, uri, timestamp, seq, body_hash)`, header: `Swarm-Request-Signature`) vs `api-registry.md` §3.5 (signature covers: `direction, session_id, seq, tick, body_hash, audience`, canonical payload: `SWARM-WS-MSG-V1`)
- 问题: IDL 和 Registry 对 Agent WS 消息签名的覆盖字段完全不同。IDL 用 `(method, uri, timestamp, seq, body_hash)`，Registry 用 `(direction, session_id, seq, tick, body_hash, audience)`。连 header 名称都不同（`Swarm-Request-Signature` vs Registry 的 `SWARM-WS-MSG-V1` canonical payload）。
- 影响: WS 消息认证实现无法同时满足两个规范。重放检测的 seq 语义一致，但签名 payload 不一致导致验签失败。
- 修复: 统一为 Registry 的 `SWARM-WS-MSG-V1` canonical payload，更新 IDL websocket_security 节。

**M8: visibility_filter 可选值跨文档不一致**

- 文件: `api-registry.md` §13 (canonical values: `none, owner, admin_scope, fog_of_war, owner_or_visible`) vs `game_api.idl.yaml` §3 (`swarm_get_leaderboard` uses `arena_only` — 不在 canonical 列表) vs `auth_api.idl.yaml` §8 (values: `none, owner, admin_scope` — 缺 fog_of_war, owner_or_visible)
- 问题: Registry 定义 5 个 canonical visibility filter 值；IDL 使用了不在列表中的 `arena_only`；auth IDL 只列了 3 个。
- 影响: 可见性过滤是安全边界的关键——不一致导致权限泄漏或过度限制。
- 修复: 要么将 `arena_only` 加入 canonical 列表；要么 `swarm_get_leaderboard` 改用 `none`（因为 RFC-gated 不实际暴露）。auth IDL 补齐完整列表。

**M9: replay_class 可选值跨文档不一致 — IDL 使用 non_idempotent_mutation 不在 Registry canonical 列表**

- 文件: `api-registry.md` §13 (canonical values: `non_replayable, read_replay_safe, idempotent_mutation, admin_critical, deploy_mutation`) vs `game_api.idl.yaml` / `auth_api.idl.yaml` (均使用 `non_idempotent_mutation` for `swarm_submit_csr`)
- 问题: `non_idempotent_mutation` 在两个 IDL 中使用但不在 Registry canonical 列表中。Registry 的 5 个值中没有它。
- 影响: replay class 分类不完整——submit_csr 是非幂等的 redb 事务消费，需要与 idempotent_mutation 区分。如果 Registry 是权威，IDL 使用的值非法；如果 IDL 正确，Registry 需要补项。
- 修复: Registry §13 canonical values 补充 `non_idempotent_mutation`。

**M10: Recycle spawn 邻近性校验冲突**

- 文件: `game_api.idl.yaml` §1 (Recycle description: "self-action — no spawn proximity required") vs `commands.md` §Recycle ("校验：drone 在 Spawn 1 格内")
- 问题: IDL 说不需要 spawn 邻近；commands.md 说需要在 Spawn 1 格内。
- 影响: Recycle 是 drone 生命周期终止路径——校验规则直接影响资源退还策略。如果无需邻近，drone 可在任何位置回收；如果需要邻近，玩家必须移动 drone 到 spawn 旁。
- 修复: 明确 Recycle 是否需要 Spawn 邻近。考虑设计意图（self-action 意味着无外部依赖），commands.md 应移除 Spawn 邻近校验。D-item 需用户裁决。

**M11: TransferToGlobal/TransferFromGlobal 费率与 AlliedTransfer 费率关系不清**

- 文件: `commands.md` (TransferToGlobal: "1% 手续费"; TransferFromGlobal: "5% 手续费") vs `economy.idl.yaml` §2.7 (AlliedTransfer fee_bp: 200 = 2%) vs `api-registry.md` §10.2 (AlliedTransfer: 200 bp = 2%)
- 问题: commands.md 对 TransferToGlobal/FromGlobal 声明 1%/5% 费率，但 economy IDL 对 AlliedTransfer 声明 2%。commands.md 未区分普通转移和盟友转移——如果 1%/5% 是普通转移费率，它与 AlliedTransfer 2% 是不同操作；但 commands.md 未标注这种区分，读者会认为矛盾。
- 影响: 经济模型费率在玩家可见文档（commands.md）和机器可读 IDL 之间表述不一致，容易导致实现混淆。
- 修复: commands.md 明确区分 "本地存储 ↔ 全局存储" 转换费率 vs "盟友间全局存储转移" (AlliedTransfer) 费率，或对齐数值。

### Low

**L1: SWARM-DEPLOY-V1 path 在 auth IDL 内部不一致**

- 文件: `auth_api.idl.yaml` §4a (line 453: `path: /deploy`) vs §4.5 (line 501: `path: /mcp`)
- 问题: 同一 IDL 文件两个 section 对 deploy signature payload 的 path 字段不一致。
- 影响: 签名验证时 path 字段影响签名 payload——不一致导致客户端和服务端签名不匹配。
- 修复: 统一 path 值（建议 `/deploy` 因为是 deploy 专用签名）。

**L2: "远期方向" / "future" / "deferred" 违反设计即终态原则**

- 文件: `design/engine.md` §3.4.7 ("水平分片为远期方向"), §3.1a ("未来可通过模组扩展"), line 506 ("SIMD deterministic subset deferred — non-blocking"), `game_api.idl.yaml` §7 ("future RFC")
- 问题: AGENTS.md 明确禁止 "远期方向"、"future"、"deferred"、"以后再说" 等延期词。这些出现违反了"设计即终态"原则。
- 影响: 设计文档不应包含延期表述——要么裁定，要么不提。SIMD subset 的 "deferred" 标记暗示存在未决设计，违反原则。
- 修复: 移除所有延期词。SIMD：要么裁定"禁用"（确定性优先），要么裁定"opt-in deterministic subset"并完整描述。水平分片：engine.md §3.4.7 已有分片模型描述，"远期方向"那句多余——删除。

**L3: Deploy flow 同步 vs 异步语义在 IDL 内部矛盾**

- 文件: `game_api.idl.yaml` §10 `deploy.flow` (step_2_upload_blob: "WASM blob uploaded to object store via async_object_store_upload") vs `api-registry.md` §11 ("Deploy 子系统使用 deploy_mutation 模式：同步提交")
- 问题: IDL flow 描述 blob 上传为 async，但 Registry §11 说 deploy 同步提交。虽然两者的 "同步" 指的是 redb 事务而非 blob 上传，但 IDL 的描述容易误解为整个 deploy 是异步的。
- 影响: 实现者可能误解 deploy 语义——redb manifest 同步提交是 replay 权威点，blob 上传异步但不影响 deploy 确认。
- 修复: IDL flow step_2 明确标注 "blob upload async, but deploy call returns synchronously after redb commit"。

**L4: CommandAction numbering gaps 未说明**

- 文件: `api-registry.md` §1.1 (Core 指令编号: 1,2,3,4,5,9,10,11 — 跳过 6,7,8) vs `game_api.idl.yaml` §1 (同样跳号)
- 问题: CommandAction 编号有 gap（5→9），但无任何说明为何跳过 6,7,8。ActionRegistry vanilla actions 占用 14-24，但 6,7,8 依然空缺。
- 影响: 编号 gap 本身无害但降低可读性，且读者会猜测是否存在已删除的变体。
- 修复: 添加注释说明 "indices 6-8 reserved for future core actions" 或重新连续编号。

---

## 3. 亮点

**S1: 三层文档模型与 codegen 单事实源架构设计优秀**

design/ → specs/ → specs/reference/ 的三层模型，配合 IDL YAML → codegen → API Registry 的自动生成链，是确保跨文档一致性的正确架构。Registry 声明为设计权威、IDL 为机器可读源、CI `--check` 模式拒绝漂移——这个设计本身是健全的。当前发现的大量 IDL↔Registry 漂移恰恰说明 codegen CI 尚未运行或未严格执行，而非架构缺陷。

**S2: CommandAction → ActionRegistry dispatch 模式干净利落**

将 11 个 combat/effect action 从 CommandAction enum 移入 ActionRegistry，通过 `Action { type, payload }` 统一 dispatch，是优秀的接口设计。它保持了 CommandAction enum 稳定（仅 11 个非战斗变体），同时允许 mod 通过 `world.toml [[action_registry]]` 扩展而不触碰核心 enum。`special-attack-table.md` 作为 canonical 参数表的单一引用源，有效避免了参数重复声明。

**S3: deploy_mutation + redb_version_counter 的 replay 确定性设计成熟**

deploy 的同步 redb 事务提交 + redb_version_counter 全序 replay，配合 SWARM-DEPLOY-V1 canonical 签名 payload 绑定 `module_hash` 和 `redb_version_counter_predicted`，形成了完整的防重放 + 确定性 replay 链条。async blob 上传与 redb manifest 解耦的设计正确地将 I/O 延迟排除在确定性边界外。

**S4: SwarmError envelope 的 canonical code + debug_detail 分离设计稳健**

48 个 canonical RejectionReason 作为 stable wire enum，所有上下文细节通过 `debug_detail` 模板参数化传递，`detail_level` 控制信息暴露——这避免了 wire enum 膨胀同时保留丰富调试数据。condition → canonical code → debug_detail template 的映射表（Registry §2.6）是可直接指导实现的优秀规范。

**S5: 两阶段快照架构消除了 per-player 重复序列化的 O(n²) 开销**

从 per-player 独立序列化改为 tick 开始时一次性构建全量快照 + per-player 可见分片拼接，复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`——这是正确的架构优化，与确定性要求一致（快照构建在 WASM 执行前完成）。

**S6: 固定点类型注册表消除了 f64 确定性隐患**

`api-registry.md` §0 Fixed-Point Type Registry 统一定义 `BasisPoints`、`ResourceRate_i64`、`milli_distance` 等定点类型替换所有 f64，是确定性系统的正确选择。economy IDL 全程使用整数运算 + floor rounding，公式明确定义中间结果类型（u128/checked math），避免了跨平台浮点漂移。

---

## 4. CrossCheck — 需要跨方向检查

- CX1: [game_api.idl.yaml 0.4.0 → 0.5.0 版本 bump 遗漏，CommandAction 泛化到 ActionRegistry 的迁移是否完整] → 建议 [游戏机制方向] 检查 [gameplay.md 中 combat/special attack 描述是否与 ActionRegistry dispatch 模式一致，有无残留的 CommandAction::Attack 等直接引用]
- CX2: [Recycle spawn 邻近性校验冲突：IDL 说不需要 vs commands.md 说需要] → 建议 [游戏机制方向] 检查 [death_mark → death_cleanup 路径中 Recycle 是否真为 self-action，以及 Recycle 退还公式是否依赖 Spawn 邻近性]
- CX3: [TransferToGlobal 1% / TransferFromGlobal 5% vs AlliedTransfer 2% 费率关系未理清] → 建议 [经济方向] 检查 [resource-ledger.md 中本地↔全局转换费率与盟友转移费率的完整定义，是否存在三层费率体系（本地转换/全局转移/盟友转移）]
- CX4: [ClientAuthCertificate TTL 15min-180d 范围是否安全合理] → 建议 [安全方向] 检查 [180 天 TTL 的 ClientAuthCertificate 在私钥泄露场景下的风险窗口，以及 cert revocation 机制是否足以覆盖长 TTL 证书]
- CX5: [Per-room drone cap 500（Registry §5.1）与 RCL 表中的 "最大房间 drone" 列（RCL1=50 → RCL8=500）的关系] → 建议 [架构方向] 检查 [per-room drone cap 是否等于 RCL8 的 500，以及 per-player 50 cap 与 per-room 500 cap 的取较小值逻辑是否在 engine.md 和 IDL 中一致表述]
- CX6: [Auth IDL §3 certificate_types description 提到 "Intermediate CA"，可能是 0.1.0 bearer token 时代的残留] → 建议 [安全方向] 检查 [auth_api.idl.yaml 全文是否有其他 0.1.0 时代残留（bearer token、refresh token、JWT 等引用），确保证书链重写彻底]
- CX7: [visibility_filter `arena_only` 不在 canonical 列表，`swarm_get_leaderboard` 是 RFC-gated 工具] → 建议 [安全方向] 检查 [RFC-gated 工具的 visibility_filter 是否应使用 canonical 值，还是 RFC-gated 工具允许使用非标准值]
- CX8: [game_api.idl.yaml §3 mcp_tools 声明 `total_tools: 57` 但 rfc_tools 中还列了 swarm_list_market_orders] → 建议 [架构方向] 检查 [57 是否包含 rfc_tools，还是仅含 active + rfc_gated；all_declared=57 的口径是否与 IDL list 实际条目数匹配]
