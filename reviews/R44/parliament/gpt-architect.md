# R44 Architect Review — gpt-5.5

## Verdict

REQUEST_MAJOR_CHANGES

理由：整体架构方向（Rust/Bevy ECS + Wasmtime + redb + NATS + IDL/codegen 单一事实源）是成立的，但当前文档集存在多处“权威源”互相冲突，且集中在 API Registry、IDL、Host Function ABI、MCP tool surface、规则/模组接入与确定性合同这些跨层接口上。这些不是文字瑕疵，而是会直接导致 SDK/codegen、引擎调度、重放验证和安全边界实现分叉的阻塞问题。

---

## §1 Critical Findings (blockers)

### C1. RejectionReason 的 canonical 数量和来源三方分裂

Severity: Critical

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:86-90`：Registry 声称 `RejectionReason — 46 codes`，并声明 canonical wire code 总数为 46。
- `/data/swarm/docs/design/interface.md:137-140`：接口文档声明 `error.data.rejection_reason` 是 48 codes。
- `/data/swarm/docs/specs/reference/commands.md:147-151`：Command 参考同样声明 48 canonical code。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:326-335`：machine-readable IDL 声称 `35 canonical codes`，且 description 说只覆盖 Pipeline / Validation / MCP / Runtime，没有 Auth 层。
- `/data/swarm/docs/specs/reference/api-registry.md:178-191`：Auth 层表内还把 `RateLimited` 同名放入 Auth 层 index 44，而 MCP 层已有 `RateLimited` index 30（`api-registry.md:155-163`）。

问题描述：
文档同时存在 35 / 46 / 48 三套 canonical RejectionReason 数量，且 API Registry 自称由 IDL 生成，但 IDL YAML 的 count 和 description 明显落后于 Registry。Auth 层的 `RateLimited` 与 MCP 层同名也破坏了“canonical wire enum string 唯一”的直觉合同：客户端看到 `RateLimited` 无法仅从 enum 判断层级，除非再依赖额外上下文。

影响分析：
- SDK typed exception、JSON-RPC envelope、CI diff gate、validator 映射会生成不同枚举。
- Replay / TickTrace 中 `rejection_reason_registry_version` 的意义不稳定。
- 安全提示阶梯依赖 canonical code + debug_detail；枚举分叉会让 competitive/practice/training 三种 detail level 的行为无法一致实现。

修复建议：
1. 选定唯一 machine-readable 源：建议以 `specs/reference/game_api.idl.yaml` + `auth_api.idl.yaml` 为生成源，但必须把合并后的 canonical enum 明确写入一个生成产物。
2. 把所有文档统一到同一个数量；如果 Auth code 合并进同一 wire enum，则 Registry、IDL、commands、interface 全部同步。
3. 解决同名 `RateLimited`：若 wire enum 必须唯一，改为 `RateLimited` + `debug_detail.layer=auth|mcp`，或拆成 `AuthRateLimited` / `McpRateLimited`，二者择一并全局一致。
4. 增加 CI：扫描文档中 “35/46/48 canonical code” 这类硬编码计数，禁止漂移。

### C2. MCP tool registry / IDL / security 文档的权威边界不成立

Severity: Critical

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:248-260`：Registry 声明 Game API `all_declared=57` / `active_only=53` / `rfc_gated=4`，Auth API `all_declared=7` / `active_only=7`，但同一表中 Auth API 合计列写成 12，合计 all_declared=69、active_only=65。
- `/data/swarm/docs/specs/reference/api-registry.md:388-404`：Auth API 工具表实际列出 7 个 CSR lifecycle 工具。
- `/data/swarm/docs/specs/reference/mcp-tools.md:42-43`：MCP tools 文档声明 Auth API 是 7 个，和 Registry 合计列的 12 冲突。
- `/data/swarm/docs/specs/reference/mcp-tools.md:74`：又声称 Auth API 工具是 12 个完整 auth 工具。
- `/data/swarm/docs/specs/security/mcp-security.md:238-242`：引用 API Registry §3.4 Capability Profiles，但 `/data/swarm/docs/specs/reference/api-registry.md` 中不存在 §3.4；capability_profiles 实际在 `game_api.idl.yaml:1535-1553`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:524-528`：注释仍写 “46 tools”，字段 `total_tools: 57`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1038-1040`：Deploy 注释为 6 tools，但后续实际列出 7 个 deploy tools（`swarm_list_modules` 在 `1138-1149`）。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1151-1153`：Debug 注释为 7 tools，但后续实际列出 8 个 debug tools（含 `swarm_explain_last_tick`）。

问题描述：
MCP 工具面有三层漂移：计数漂移（57/53/4 与 46、Auth 7 与 12）、章节引用漂移（§3.4 不存在）、分类计数漂移（Deploy 6 vs 7、Debug 7 vs 8）。这破坏了“API Registry 是生成发布物、IDL 是 machine-readable source”的模型。

影响分析：
- SDK 和 MCP server 如果按 YAML 生成，会与人工 Registry 表不同。
- Capability profile / scope / rate limit 无法作为授权实现依据，安全配置可能漏工具或暴露 RFC-gated 工具。
- 文档明确说 CI gate 拒绝漂移，但当前设计文档本身已经处于漂移状态，说明 gate 的对象和权威链路不清晰。

修复建议：
1. 将 `game_api.idl.yaml` 中工具数组作为唯一 source，生成 Registry、mcp-tools.md、security/mcp-security.md 中的工具清单和计数。
2. Registry §3 的合计表重新计算：Auth API 若是 7，则合计应与 7 一致；若保留 Game API 中 3 个 auth alias，应明确 “Game API Auth alias=3，不计入 Auth API all_declared”。
3. 删除或生成所有手写 “46 tools / 6 tools / 7 tools / 12 auth tools” 注释。
4. 在 Registry 中补齐或改正 Capability Profiles 章节引用；不要让 security 文档指向不存在的 §3.4。

### C3. Host Function ABI 数量、签名、成本模型不一致

Severity: Critical

文件引用：
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1571-1577`：Host Functions 声明 `all 6` / `total_functions: 6`。
- `/data/swarm/docs/specs/reference/api-registry.md:448-458`：Registry 输出上限表列出 7 个函数，包括 `host_get_fuel_remaining`。
- `/data/swarm/docs/specs/reference/host-functions.md:73-80`：独立定义 `host_get_fuel_remaining() -> u64`。
- `/data/swarm/docs/specs/core/wasm-sandbox.md:212-227`：允许的 host function 也列出 7 个，包括 `host_get_fuel_remaining()`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1638-1644`：`host_get_random` 签名为 `(sequence: u32, out_ptr, out_len)`，seed 描述为 `(tick_seed, player_id, drone_id, sequence)`。
- `/data/swarm/docs/specs/reference/host-functions.md:63-70` 与 `/data/swarm/docs/specs/core/wasm-sandbox.md:221-238`：`host_get_random` 使用 `sequence: u64`，派生输入为 `(domain, world_seed, tick, actor_or_entity_id, sequence)`，length-delimited field encoding。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1645-1649`：`host_get_random` fuel 为 `100 + 1/output byte`。
- `/data/swarm/docs/specs/reference/api-registry.md:460-470` 与 `/data/swarm/docs/specs/reference/host-functions.md:69-71`：canonical fuel 为 `200 + 10/32 bytes`。

问题描述：
WASM ABI 这种必须精确一致的接口，在函数数量、签名宽度、随机派生语义、fuel 成本四个维度都存在冲突。尤其 `host_get_random(sequence: u32|u64)` 会直接改变 ABI、SDK binding、replay 输入和随机流域分离。

影响分析：
- WASM SDK 生成与引擎 ABI 不匹配，模块无法加载或产生隐性 replay drift。
- Fuel schedule 是 replay-critical 输入；成本表漂移会导致同一 WASM 在不同实现中 timeout/fuel_exhausted 边界不同。
- `host_get_fuel_remaining` 是否属于 ABI 的问题会影响 `abi_version` 递增和旧模块兼容策略。

修复建议：
1. 明确 Host Function 总数是 7 还是 6；若 `host_get_fuel_remaining` 是正式 ABI，必须进入 IDL `total_functions` 和 functions 列表。
2. 统一 `host_get_random` 为 `sequence: u64` 或 `u32`；架构上建议采用 `u64`，因为已被 sandbox/host-functions 文档用于 replay-safe domain separation。
3. 把随机派生规范只保留一处 canonical 文本，其他文档引用，不重复描述 seed tuple。
4. 将 fuel schedule 从 Registry/IDL 单源生成，并把 `fuel_schedule_version` 与 host cost table version 纳入 replay-critical 校验。

### C4. 规则/模组系统与 Tick Manifest 的抽象边界冲突

Severity: Critical

文件引用：
- `/data/swarm/docs/design/gameplay.md:1529`：Plugin systems 必须进入 Complete Tick Execution Manifest 的 R/W matrix，注册结果纳入 `world_action_manifest_hash` 和 replay 输入。
- `/data/swarm/docs/specs/core/world-rules.md:1019-1041`：规则 System 是外挂，可在执行前后附加逻辑、修改 ECS 资源/组件，且“不修改核心引擎代码”。
- `/data/swarm/docs/specs/core/phase2b-system-manifest.md:480-493`：Manifest hash 只覆盖固定 `system_id_1..system_id_31`；ActionRegistry handler set/hash 单独进入 world manifest，且 dispatch 边界不改变固定系统清单顺序。
- `/data/swarm/docs/specs/core/phase2b-system-manifest.md:497-507`：CI 验证只验证 31 systems 的 R/W 冲突、并行安全和 manifest 一致性。
- `/data/swarm/docs/specs/core/tick-protocol.md:1044-1047`：动态规则脚本已移除，扩展 action 必须通过 World Action Manifest + IDL 注册 schema。

问题描述：
文档同时表达了两种不可兼容的扩展模型：
1. 固定 31-system manifest，Plugin/ActionRegistry hash 单独记录，不改变 system schedule。
2. Plugin systems 作为 ECS systems 进入 Complete Tick Execution Manifest 的 R/W matrix，并可在执行前后附加逻辑。

这不是实现细节，而是核心架构边界问题：mod 到底只能注册 action handlers / rule data，由固定 reducer 执行；还是可以向 Bevy schedule 注入新 systems？如果可以注入，31-system 固定 manifest 和 CI 规则不完整；如果不能注入，world-rules 和 gameplay 中的 “Plugin systems” 表述过宽。

影响分析：
- Replay verifier 无法知道 mod system 是否参与 determinism hash。
- R/W matrix 无法覆盖 mod 写入，Unique Writer Contract（如 StatusState 仅 S22 写）可能被插件绕过。
- Mod API 的直觉性下降：服主/插件作者不知道该注册 handler、resource operation、还是 Bevy system。

修复建议：
1. 设计层明确二选一：
   - A：固定 schedule 模型。插件只能注册声明式 schema、ActionRegistry handler、SpecialEffect reducer、resource operation，由固定 systems 调用；不允许任意 Bevy system 注入。
   - B：可扩展 schedule 模型。World Manifest 必须包含 plugin system id、order constraints、component R/W set、version/hash，并扩展 CI R/W 检查到 plugin graph。
2. 若保留 B，`phase2b-system-manifest.md` 不能再称固定 31 systems 为完整权威调度，只能称 core systems；manifest_hash 需要纳入 plugin schedule graph。
3. 若采用 A，删除 `world-rules.md:1019-1041` 中“规则 System 外挂、前后附加逻辑”的泛化描述，改为“插件逻辑通过固定 hook points 执行”。

---

## §2 Design Tensions (inconsistencies, conflicts)

### T1. WorldConfig / world.toml 中经济费率类型仍混用浮点与 basis points

Severity: High

文件引用：
- `/data/swarm/docs/specs/core/resource-ledger.md:59-64`：Resource Ledger 声明为所有经济费率、公式、参数的唯一定义源，并要求全部使用 basis points，禁止浮点数。
- `/data/swarm/docs/design/gameplay.md:312-315`：配置表仍使用 `transfer_to_global_cost` / `transfer_from_global_cost` 的 ResourceCost `{Energy: 0.01}` / `{Energy: 0.05}`。
- `/data/swarm/docs/design/gameplay.md:1283-1286`：同一文件后文又使用 `transfer_to_global_cost_bps` / `transfer_from_global_cost_bps`。
- `/data/swarm/docs/specs/core/world-rules.md:101-109`：world.toml 示例使用 `transfer_to_global_cost = { Energy = 0.01 }`、`transfer_from_global_cost = { Energy = 0.05 }`、`damage_multiplier = 1.0`。
- `/data/swarm/docs/specs/core/world-rules.md:967-979`：mod config type 允许 `f64`。
- `/data/swarm/docs/design/gameplay.md:1608-1615`：确定性合同禁止 f64，要求所有模组参数为整数/定点，Plugin system 不得引入浮点状态转移。

问题描述：
经济和规则配置层仍残留浮点表达（0.01、0.05、1.0、f64），与确定性合同和 Resource Ledger 的 basis points 模型冲突。字段命名也在 `*_cost`、`*_cost_bps`、`global_deposit_fee` / `global_withdraw_fee` 之间漂移。

影响分析：
- world.toml parser 和 codegen 不知道哪个字段是 canonical。
- 浮点配置进入 plugin state 会破坏跨平台 determinism。
- 经济公式难以从 Resource Ledger 反向生成 schema。

修复建议：
统一所有费率字段为 Resource Ledger 名称：`global_deposit_fee`, `global_withdraw_fee`, `global_deposit_delay`, `global_withdraw_delay`，单位 bp/tick。world-rules 的 type registry 删除 `f64`，示例中的 `damage_multiplier` 改为 `damage_multiplier_bps = 10000` 或固定点类型。

### T2. Drone messaging 同时被定义为 active TickResult 字段和 Out-of-Scope RFC

Severity: High

文件引用：
- `/data/swarm/docs/specs/gameplay/api-idl.md:28-50`：`TickResult` 正式包含 `messages: Vec<DroneMessage>`，并定义 payload schema 与投递排序。
- `/data/swarm/docs/design/gameplay.md:1621-1663`：Drone 间消息机制作为设计正文，说明引擎在 EXECUTE 阶段处理 messages。
- `/data/swarm/docs/specs/reference/api-registry.md:317` 与 `/data/swarm/docs/specs/reference/game_api.idl.yaml:951-956`：MCP/Play 工具包含 `swarm_get_messages`。
- `/data/swarm/docs/design/interface.md:119`：声明 `SendMessage` 是 Out-of-Scope RFC，当前不在 Core CommandAction 中。
- `/data/swarm/docs/specs/reference/commands.md:145`：同样声明 drone 间消息传递为 Out-of-Scope RFC。

问题描述：
这里可能存在概念区分：`SendMessage` 作为 CommandAction 不存在，但 `TickResult.messages` 作为 side-channel active 存在。然而文档没有明确这个分层，导致读者会看到 “消息机制 active” 与 “drone 间消息传递 out-of-scope” 的表面冲突。

影响分析：
- SDK 生成者不知道是否应暴露 `messages` 字段。
- 引擎实现者不知道 EXECUTE 是否需要处理 PendingMessages。
- MCP `swarm_get_messages` 是否 active 也变得不稳定。

修复建议：
明确写成：`SendMessage` CommandAction 不存在；active 消息机制是 `TickResult.messages` side-channel，受独立 payload/visibility/size 规则约束。或者若消息确实 out-of-scope，则删除 TickResult.messages、gameplay §2.9 和 `swarm_get_messages` active 工具。

### T3. Command ordering 的排序键和 seed domain 在同一文档内不一致

Severity: High

文件引用：
- `/data/swarm/docs/specs/core/tick-protocol.md:243-250`：早期示例 seed 为 `Blake3(tick_number || world_seed)`，排序 tuple 为 `(order_index, player_id, cmd.sequence, cmd)`。
- `/data/swarm/docs/specs/core/tick-protocol.md:903-921`：权威排序键为 `(priority_class, shuffle_index, source_rank, sequence, command_hash)`，shuffle seed 为 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`。
- `/data/swarm/docs/design/gameplay.md:1611-1614`：排序写成 `(priority_class, shuffle_index, sequence, source)`，顺序和字段缺少 `command_hash`，且 source 在 sequence 后。
- `/data/swarm/docs/design/engine.md:347-352`：确定性要求引用 `interface.md §4` 作为 canonical order，但 `interface.md` 当前不承载完整排序规范。

问题描述：
排序合同是 replay determinism 的核心。当前一个文件内有简化示例与权威键不一致，另一个高层文档又给出第三种字段顺序。

影响分析：
- RawCommand 全局排序实现可能按旧示例落地，遗漏 source_rank / command_hash。
- 玩家 source 间的 sequence 空间与公平性、Admin/WASM/MCP 优先级边界会产生分叉。

修复建议：
只保留 `tick-protocol.md §9.1` 作为 canonical sorting key。早期 §3.1 示例改为伪代码并显式引用 §9.1，不再列不完整 tuple。`design/gameplay.md` 和 `design/engine.md` 改为引用 §9.1，不重复排序字段。

### T4. Deploy / Persistence 对 WASM module blob 的归属仍有残余冲突

Severity: Medium

文件引用：
- `/data/swarm/docs/specs/core/persistence-contract.md:80-127`：Deploy 完整状态机声明 deploy manifest + compiled artifact 足以激活，原始 WASM audit archive 异步，不阻塞激活。
- `/data/swarm/docs/specs/reference/api-registry.md:864-870`：声明 Persistence 层处理非 deploy 大型对象，Deploy payload 不走异步上传路径。
- `/data/swarm/docs/specs/reference/api-registry.md:882-888`：同一 Persistence 章节的 Blob Types 又包含 `wasm_module`，retention permanent。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1917-1949`：IDL persistence 同样把 `wasm_module` 作为 async object-store blob type，并说 completion_polling 使用 `swarm_get_deploy_status`。

问题描述：
文档试图表达“deploy activation 不依赖 object store”，但 Persistence/IDL 又把 `wasm_module` 放进 async_object_store_upload blob types，容易被理解为 deploy payload 也走对象存储完成状态。

影响分析：
- 实现者可能把 deploy binary 上传完成作为激活前置条件，违反 tick boundary 确定性。
- `swarm_get_deploy_status` 的语义会混合 deploy state 与 audit archive state。

修复建议：
将 blob type 改名/拆分为 `wasm_audit_archive`，并明确它不是 activation dependency。`swarm_get_deploy_status` 输出若包含 archive status，应命名为 `audit_archive_status`，与 deploy `status` 分离。

### T5. Snapshot truncation 输出字段在 API surfaces 中不统一

Severity: Medium

文件引用：
- `/data/swarm/docs/specs/core/snapshot-contract.md:32-57`：截断快照必须包含 `omitted_categories`，且每类键稳定存在。
- `/data/swarm/docs/specs/core/tick-protocol.md:157-170`：`stitch_player_snapshot` 返回 `omitted_count`，不是 `omitted_categories`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:556-567`：`swarm_get_snapshot` output schema 也是 `omitted_count`。
- `/data/swarm/docs/design/engine.md:515-523`：说明暴露 `omitted_count` 和 bucket 统计，但没有对齐 `omitted_categories` schema。

问题描述：
Snapshot Contract 把 `omitted_categories` 作为 schema 稳定性要求，但 API IDL 和 tick-protocol 使用单一 `omitted_count`。

影响分析：
- WASM `tick(snapshot)` 和 MCP `swarm_get_snapshot` 的结构不一致。
- 客户端无法按类别降级策略，尤其资源/事件/实体的截断处理不同。

修复建议：
统一 schema：建议保留 `omitted_categories` 为 canonical，并可额外提供 `omitted_count_total` 派生字段；IDL、tick-protocol、engine.md 全部同步。

### T6. Resource Ledger 与 snapshot-contract 中 GlobalWithdraw 延迟字段命名不一致

Severity: Medium

文件引用：
- `/data/swarm/docs/specs/core/resource-ledger.md:68-72`：字段为 `global_deposit_delay` 和 `global_withdraw_delay`。
- `/data/swarm/docs/specs/core/snapshot-contract.md:199-202`：`GlobalWithdraw` 描述使用 `global_transfer_delay`（100 tick）。
- `/data/swarm/docs/design/gameplay.md:351-352`：使用 `global_deposit_delay` / `global_withdraw_delay`。

问题描述：
`global_transfer_delay` 不是 Resource Ledger 参数表中的 canonical 字段，容易与 deposit/withdraw 两个方向混淆。

影响分析：
实现配置 schema 时会出现 alias 或缺字段，影响 transfer state machine。

修复建议：
将 snapshot-contract 中 `global_transfer_delay` 改为 `global_withdraw_delay`，并在所有 global transfer 文档中使用 Resource Ledger 字段名。

---

## §3 Suggestions (improvements, simplifications)

### S1. 建立“Authority Map”并删除重复硬编码表

Severity: Medium

文件引用：
- `/data/swarm/docs/AGENTS.md:44-57` 已有文档三层模型。
- `/data/swarm/docs/specs/reference/codegen.md:9-18` 已有输入到输出映射。

建议：
把 Authority Map 提升为 `specs/reference/README` 或 `codegen.md` 的第一张表，明确每类事实的唯一写入源：
- CommandAction / RejectionReason / MCP Tools / Host Functions：IDL YAML。
- Economy formulas：Resource Ledger + economy.idl.yaml。
- Tick schedule：phase2b manifest（或 core manifest + plugin manifest，取决于 C4 裁决）。
- Snapshot schema：snapshot-contract + IDL generated schema。

其他文档只引用，不重复列数量、字段、成本表。当前最大问题不是缺少细节，而是细节重复过多导致漂移。

### S2. 把“概念示例”和“canonical schema”视觉上分离

Severity: Low

文件引用：
- `/data/swarm/docs/specs/core/tick-protocol.md:243-260` 的排序示例容易被当作权威实现。
- `/data/swarm/docs/specs/core/world-rules.md:20-130` 的 world.toml 示例仍使用旧字段和浮点。

建议：
所有非权威示例加统一前缀：`Illustrative only — canonical schema is ...`。更好的做法是用 codegen 从 canonical schema 生成最小可运行 sample，避免示例陈旧。

### S3. Capability Profiles 应成为独立接口合同

Severity: Medium

文件引用：
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1535-1553` 有 capability_profiles。
- `/data/swarm/docs/specs/security/mcp-security.md:238-242` 依赖它但引用了不存在的 Registry §3.4。

建议：
Capability Profiles 不应埋在 YAML 尾部；它是 MCP 授权模型的核心接口。建议生成到 API Registry 的独立章节，并列出每个 profile 包含的 categories、默认 scope、rate limit aggregation、是否可用于 browser/agent/admin。

### S4. Mod API 建议收敛到“固定 hook surface”

Severity: Medium

文件引用：
- `/data/swarm/docs/design/gameplay.md:1455-1530` 定义 Rule Module System。
- `/data/swarm/docs/specs/core/world-rules.md:1019-1041` 描述外挂规则 System。

建议：
从接口直觉性看，任意 Bevy Plugin system 注入过强，容易破坏 determinism 和 R/W matrix。建议将 mod surface 收敛为固定 hook points：Action handler、SpecialEffect reducer、ResourceOperation formula、Structure/Body/Damage type schema、NPC behavior table。这样 World Action Manifest 可以完整描述 replay 输入，不需要让第三方系统进入核心 schedule。

### S5. Error envelope 和 RejectionReason 应提供 version negotiation

Severity: Low

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:698-732` 定义 SwarmError envelope。
- `/data/swarm/docs/specs/reference/api-registry.md:636` TickTrace 有 `rejection_reason_registry_version`。

建议：
MCP/REST error response 可附带 `registry_version` 或 `api_registry_version`，SDK 在 enum 不认识时能降级到 `UnknownCanonicalReason`，同时保留 raw string。这能降低未来 enum 扩展的破坏性。

---

## 亮点

- 分层架构主线清晰：`design/architecture.md:118-193` 的 COLLECT / EXECUTE / COMMIT 热路径与 `tick-protocol.md:187-207` 的快照时序边界相互呼应，整体目标状态明确。
- redb 的职责边界写得很好：`design/architecture.md:206-254` 与 `persistence-contract.md:131-199` 把 replay-critical subset 和 RichTraceBlob / Blob Store 分离，避免把对象存储变成权威状态。
- Deferred Command Model 是正确抽象：`design/interface.md:53-90` 与 `wasm-sandbox.md:177-251` 明确禁止 mutating host functions，降低 TOCTOU 与 sandbox escape 面。
- Snapshot Contract 的“关键实体永不截断 + deterministic minimal snapshot”很强：`snapshot-contract.md:86-102` 对用户体验、确定性和抗滥用三者做了清晰权衡。
- Resource Ledger 作为经济单一入口的方向正确：`resource-ledger.md:14-31` 把 Transfer Gateway / ledger / trace 归因统一，避免各 gameplay action 自行扣费。
- 安全设计中应用层证书、CSR、Server CA pinning 的边界清晰：`design/auth.md:100-147` 与 `command-source.md:57-132` 形成了较完整的身份链。

---

## §4 Cross-Reference Matrix

| ID | 问题 | 主要文件 | 影响方向 | 建议处理 |
|---|---|---|---|---|
| C1 | RejectionReason 35/46/48 分裂 | `api-registry.md`, `game_api.idl.yaml`, `interface.md`, `commands.md` | API / SDK / Validation / Security | 阻塞修复；统一 canonical enum 和生成链路 |
| C2 | MCP tool count、Auth count、Capability Profile 引用漂移 | `api-registry.md`, `game_api.idl.yaml`, `mcp-tools.md`, `mcp-security.md` | MCP / AuthZ / Codegen | 阻塞修复；单源生成 |
| C3 | Host Function ABI 数量、签名、fuel 成本冲突 | `game_api.idl.yaml`, `api-registry.md`, `host-functions.md`, `wasm-sandbox.md` | WASM ABI / Replay / SDK | 阻塞修复；统一 ABI 与 fuel schedule |
| C4 | Plugin systems 是否进入 Tick Manifest 不清楚 | `gameplay.md`, `world-rules.md`, `phase2b-system-manifest.md`, `tick-protocol.md` | Mod API / ECS Schedule / Determinism | 阻塞修复；需要架构裁决 A/B |
| T1 | world.toml 经济费率混用 float 与 bp | `resource-ledger.md`, `gameplay.md`, `world-rules.md` | Economy / Determinism | 高优先级修复；删除 f64 surface |
| T2 | Drone messaging active vs out-of-scope | `api-idl.md`, `gameplay.md`, `interface.md`, `commands.md` | Game API / SDK / UX | 高优先级澄清；区分 side-channel 与 CommandAction |
| T3 | Command sorting key 多版本 | `tick-protocol.md`, `gameplay.md`, `engine.md` | Replay / Fairness | 高优先级修复；只引用 §9.1 |
| T4 | Deploy audit blob vs activation dependency | `persistence-contract.md`, `api-registry.md`, `game_api.idl.yaml` | Persistence / Deploy | 中优先级修复；重命名 audit archive |
| T5 | Snapshot omitted_categories vs omitted_count | `snapshot-contract.md`, `tick-protocol.md`, `game_api.idl.yaml`, `engine.md` | Snapshot API / WASM / MCP | 中优先级修复；统一 schema |
| T6 | global_transfer_delay 字段漂移 | `resource-ledger.md`, `snapshot-contract.md`, `gameplay.md` | Economy / Transfer State | 中优先级修复；改为 `global_withdraw_delay` |

---

## CrossCheck

- CX-1: RejectionReason 中 `RateLimited` 同名复用可能导致 auth/MCP 安全审计归因不清 → 建议 Security Reviewer 检查 wire enum 唯一性、日志分类和 oracle 泄露影响。
- CX-2: Host function `host_get_random` 的 seed 派生和 sequence 宽度冲突可能隐藏 replay drift → 建议 Determinism Reviewer 检查 RNG domain separation、seed archive 与 replay verifier 输入。
- CX-3: Plugin system 是否可注入 Bevy schedule 会影响 R/W conflict 和 Unique Writer Contract → 建议 Engine/ECS Reviewer 检查 Bevy schedule graph、component access static analysis 和 mod hook 可验证性。
- CX-4: MCP tool counts 与 capability profile 漂移可能导致 RFC-gated 工具被 active SDK 暴露 → 建议 Security/API Reviewer 检查 tool generation、scope enforcement、feature-gated error path。
- CX-5: world.toml 允许 f64 与固定点合同冲突 → 建议 Determinism/Economy Reviewer 检查配置 parser、TOML number coercion、basis point codegen。
- CX-6: Drone messaging 作为 `TickResult.messages` side-channel 是否可能成为隐蔽信息通道或 oracle → 建议 Security/Gameplay Reviewer 检查 visibility、silent drop、payload size 和 rate limits。
