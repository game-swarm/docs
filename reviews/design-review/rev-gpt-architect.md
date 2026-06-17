# R7 Architect Review — rev-gpt-architect

## Verdict

REQUEST_MAJOR_CHANGES

R7 的方向比早期版本成熟很多：MCP 不再是 gameplay 控制面、WASM 单执行器、公平 fuel、可见性 oracle、TickTrace、Tier 1/2/3 路线都已经有明确设计。但从架构合同角度看，当前文档仍有几处“看起来能实现、实际会在实现期炸”的断层：最严重的是 mutating source/单一管线合同互相矛盾、Command/IDL/schema 多处不一致、以及沙箱/预算/性能边界出现硬数值冲突。它还不能直接进入实现冻结；建议先做一次合同归一化补丁，再进入编码。

## Strengths

1. MCP 定位正确：design/interface.md:5-12、specs/security/03-mcp-security.md:35-40、specs/core/01-tick-protocol.md:106-115 都明确 AI 与人类同走 WASM，避免了“AI 有旁路控制器”的经典公平性失败。
2. Tick 生命周期的主干清晰：COLLECT/EXECUTE/BROADCAST、Phase 2a inline apply、Phase 2b ECS systems、FDB commit/rollback、Bevy snapshot restore 在 specs/core/01-tick-protocol.md:50-102、345-385、410-480 中基本闭合。
3. 可见性作为统一 oracle 被反复约束：specs/security/05-visibility.md:7-15、77-99、195-217、360-410 把 WASM/MCP/WS/REST/replay 的过滤函数和 tick 基准拉到同一模型，这一点非常关键。
4. Tier 路线比“未来再说”更具体：design/engine.md:263-298 与 specs/future/T2-incremental-snapshot.md、specs/future/T3-shard-protocol.md 已给出 entry gate 与候选协议。
5. Sandbox 设计有真实工程感：specs/core/04-wasm-sandbox.md:43-160、228-340 覆盖 Wasmtime 配置、WASI 禁用、OS 隔离、恶意样本、编译缓存 key。
6. 回放与 Wasmtime CVE 的耦合处理得好：specs/core/01-tick-protocol.md:608-633 明确 TickTrace 记录 Command 而非重跑 WASM，降低运行时升级对历史 replay 的破坏。

## Concerns

### A1 — High — “单一 mutating 管线”合同与 Source Model / MCP 非 gameplay 合同冲突

位置：
- specs/core/02-command-validation.md:35
- specs/security/09-command-source.md:15-34、40-53
- specs/security/03-mcp-security.md:37-40、247-255
- design/interface.md:48-50

问题：
specs/core/02-command-validation.md:35 写“所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一 校验→应用 路径”。但其他文档同时声明 MCP 不做 gameplay 动作，Source Model 中 MCP_Deploy/MCP_Query/Deploy/DryRun/Simulate/Replay 多数为 non-gameplay，Admin/Rollback/RuleMod/TestHarness 又可能 mutate。这里把“所有入口”写成统一 validate/apply，会让实现者误把 MCP tool/REST API 也设计成可提交 gameplay Command 的入口，正好破坏 R7 最重要的公平合同。

这类模式在系统里很危险：安全文档说“不能做”，核心管线说“所有入口都走这条路”，最后实现者会为了复用而开一条 admin/REST/MCP 的命令注入通道，后续再靠权限补丁补洞。

修正建议：
把合同拆成两层并显式命名：
1. `GameplayMutationPipeline`：只接受 Source Gate 标记为 gameplay-mutating 的 source，默认仅 `WASM`，另加明确隔离的 `TestHarness/Tutorial/Admin/Rollback/RuleMod` 特权来源；`MCP_Query`、`MCP_Deploy`、普通 REST 永远不能进入。
2. `ManagementPipeline`：部署、查询、模拟、dry-run、schema/docs 等非 gameplay 工具，各自走限流/审计/可见性，不产生权威世界状态 mutation。
并在 specs/security/09-command-source.md 的来源矩阵增加一列 `enters_gameplay_pipeline: bool`，让实现者不能靠解释。

### A2 — High — CommandIntent schema/IDL/示例仍未收敛，无法作为代码生成单一真相

位置：
- specs/core/02-command-validation.md:41-52、81-101、687-847
- specs/gameplay/08-api-idl.md:26-30、102-216、302-345
- specs/reference/commands.md:130-203
- design/interface.md:63-67

问题：
同一个 Command 合同在不同段落出现三种形态：
- 新合同：`{sequence, action: {type, ...}}`（specs/core/02-command-validation.md:81-91，specs/gameplay/08-api-idl.md:26-30）。
- 旧合同残留：`{ "action": "RangedAttack", ..., "seq": N }`、`{ "action": "Recycle", ... }`（specs/core/02-command-validation.md:691-847）。
- API reference 又使用 `controller_id` 等字段（specs/reference/commands.md:130-133），而 command-validation 的 ClaimController 表只在字段级矩阵中说 `target_id`（specs/core/02-command-validation.md:635），IDL 中也未清楚展示最终 JSON 字段名。

此外 specs/core/02-command-validation.md:45 schema 写 `maxItems: 100`，同文件 51 行又写 MAX_COMMANDS_PER_PLAYER=500，604/639 也写 500/tick。这个不是格式问题，而是生成器/validator 会写出不同限制。

修正建议：
1. 以 specs/gameplay/08-api-idl.md 为唯一权威，把 specs/core/02-command-validation.md:687-847 的旧示例删除或改为新 envelope。
2. 对每个 CommandAction 在 IDL 中给出字段级 schema：字段名、类型、required、additionalProperties=false。
3. CI 增加 doc/schema diff：IDL 生成的 JSON schema 与 specs/reference/commands.md 示例逐条校验；示例不能手写漂移。
4. 统一 `maxItems` 与 MAX_COMMANDS_PER_PLAYER；若要 schema 100、服务端 500，需要解释两层限额，否则必须单值。

### A3 — High — Tier 1 性能预算存在“500 玩家 × 每玩家 2500ms”不可调度模型

位置：
- design/engine.md:166-172、263-268
- specs/core/01-tick-protocol.md:60-75、117-128、713-735
- specs/core/04-wasm-sandbox.md:32-38、41、252-257、291-301

问题：
文档目标是 MVP 500 活跃玩家（design/engine.md:170）和 3s tick。但 specs/core/01-tick-protocol.md:60-75 表示 COLLECT 超时 2500ms，EXECUTE 500ms；04-wasm-sandbox.md:37-41 又写“每 tick fork → 执行 → kill”，且每玩家独立 worker。若理解为每玩家最多 2500ms，这需要巨大并发池；若理解为全局 collect deadline，则必须定义并发上限、排队策略、未调度玩家如何 0 指令、worker 预热/模块实例缓存等。现在合同只写了“对每个活跃玩家”，没有 worker pool 尺寸、调度公平性或背压。

这会在实现期变成两种失败之一：要么为每玩家 fork/kill 导致 500 个进程风暴和 JIT/instantiation 抖动；要么为了赶 3s tick 临时改成长驻 worker/缓存 instance，违反“tick 之间无状态保留”的安全假设。

修正建议：
补一个 `WasmExecutorPool` 合同：
- Tier 1 目标并发 worker 数、最大 active players、排队 deadline、未调度玩家语义。
- `precompiled module`、`instance lifecycle`、`process lifecycle` 分开：可缓存 compiled module，但每 tick new Store/Instance 或 worker reset；不要用“每 tick fork”一刀切表达所有安全属性。
- 给出容量公式：`active_players × p95_wasm_ms / collect_deadline <= worker_count`，并声明 500 玩家目标依赖玩家平均 fuel/耗时分布，而非每人都可跑满 2500ms。

### A4 — High — Sandbox OS 边界的硬数值和 syscall 合同自相矛盾

位置：
- specs/core/04-wasm-sandbox.md:230-257
- specs/core/04-wasm-sandbox.md:360-388
- specs/security/CVE-SLA.md:12-21
- specs/core/04-wasm-sandbox.md:54-58

问题：
同一沙箱 spec 内部有硬冲突：
- seccomp 示例允许 `clone (仅 CLONE_VM | CLONE_VFORK)`（04:236-240），checklist 又写 `clone`/fork 全禁（04:375）。Wasmtime/Cranelift/线程限制会直接受影响，实现者无法知道能否允许 clone/futex 线程相关 syscall。
- cgroup CPU：04:255 写 `cpu.max = 250000 3000000`（每 3s 0.25 CPU 秒），04:386 写 `50000 100000`（50% CPU）。两者含义不同，也与 2500ms wall-clock/fuel 预算未对齐。
- pids：04:256 写 32，04:387 写 16。
- CVE SLA：04:55 写 Critical 72h，高危 7d；specs/security/CVE-SLA.md:16-18 写 Critical 24h，High 72h，Medium 1w。

修正建议：
把 04 §9 checklist 作为权威 hardening baseline，§4 只引用它，不重复数值。为 seccomp 增加“Wasmtime runtime required syscalls profile”和“strict no-thread profile”两套可选 profile，且明确 Tier 1 默认哪套。CVE SLA 只保留 specs/security/CVE-SLA.md，04 中改为引用。

### A5 — Medium — World Rules Engine 的 ECS 系统链与 core tick 系统链漂移，说明“规则系统可插拔”还没有调度合同

位置：
- specs/core/01-tick-protocol.md:361-408
- design/engine.md:226-259
- specs/core/07-world-rules.md:135-203、313-346
- design/gameplay.md:1330-1431

问题：
specs/core/01 定义主线 `.chain()` 为 `death_mark → spawn → spawning_grace → combat → status_advance`，regeneration/decay 并行并在 death_cleanup 前完成。design/engine.md:257-259 也补了 spawning_grace 和 status_advance。可是 specs/core/07-world-rules.md:157-165 示例注册的是 `death_mark, spawn, regeneration, combat, decay, death_cleanup` 串行链，缺失 spawning_grace/status_advance，也把 regeneration 放在 combat 前。Rhai action buffer 又在 07:313-346 另有“统一 apply”，但没有说明插入 Phase 2a 前、Phase 2a 后、combat 前还是 status_advance 后。

这不是文档重复小错，而是插件系统最容易炸的地方：模组一旦能改调度顺序，确定性和玩法语义会分叉；如果不能改，Rhai 的 actions 能力必须被约束到某些 hook points。

修正建议：
定义唯一 `TickSchedule` ABI：固定 hook 点如 `PreValidate`, `PostInlineApply`, `PreCombat`, `PostCombat`, `PostStatusAdvance`, `PostRegen`；每个 hook 声明可读写 component/resource 集合、排序键、失败回滚边界。specs/core/07 中的注册示例必须改为引用 core tick schedule，不应重新列一条不同 system chain。

### A6 — Medium — Tier 2/Tier 3 spec 已有轮廓，但 entry gate 仍有“候选值未冻结”与“已冻结要求”并存

位置：
- design/engine.md:263-298
- design/tech-choices.md:227-257
- specs/future/T2-incremental-snapshot.md:37-83
- specs/future/T3-shard-protocol.md:15-83

问题：
design/engine.md:271 写 Tier 2/3 完整 spec 必须在 Phase 1 实现前完成，且 entry gate 矩阵中 Tier 2/3 有冻结项。但 T2/T3 文档仍大量使用“候选值/需基准测试确认/待定项”：CoW page size、keyframe 间隔、FDB atomic mutation 映射、hash 算法、动态重平衡、全局 TickTrace 合并等。作为远期方向可以接受；作为“实现前必须冻结”的 entry gate，还缺少可执行准入清单。

修正建议：
把 future specs 分成两层：
- `Current contract`: Tier 1 实现现在必须遵守的前向兼容约束（ID 格式、room_id/shard_id 预留、snapshot abstraction trait）。
- `Pre-Tier implementation gate`: 到 Tier 2/3 真正实现前必须冻结的待定项清单。
避免在 Tier 1 阶段要求“完整冻结”所有 future spec，否则会阻塞无关实现。

### A7 — Medium — Gateway/REST 路径命名把文档路径混进 API URL，接口直觉性差且易误实现

位置：
- specs/12-gateway-protocol.md:76、99-107
- specs/gameplay/06-feedback-loop.md:208
- specs/security/05-visibility.md:215

问题：
REST API 示例使用 `/specs/reference/v1/world/rooms/:id`、`/specs/reference/v1/world/ticks`、`GET /specs/reference/v1/ticks/4521/explanation`。这看起来像文档目录路径，不像产品 API 路径。新人会误以为 Gateway 静态暴露 docs/specs/reference 下的文件，或者把 OpenAPI 路由生成到错误前缀。

修正建议：
将运行时 API 前缀改成 `/api/v1/...` 或 `/worlds/{world_id}/...`；文档引用仍写 `specs/reference/...`。明确“specs/reference 是文档，不是 URL namespace”。

### A8 — Medium — Gameplay custom action / special attack 的 core-vs-manifest 边界仍混杂

位置：
- design/engine.md:279-284
- design/gameplay.md:612-623、727-835
- specs/gameplay/08-api-idl.md:11-16、312-345
- specs/core/02-command-validation.md:437-477、822-847

问题：
design/engine.md:280 把“8 种特殊攻击”列为 Tier 1 冻结；同表 283 又把 Dynamic CommandAction future-disabled。可是 Leech/Fabricate 在 gameplay/IDL 中经常被标成 custom / `[[custom_actions]]`，command-validation 却在 core spec 中写入 Leech/Fabricate 的优先级/反制窗口/示例。结果是：它们到底是 Core IDL 内置变体、Vanilla manifest 内置但非 Core、还是 future dynamic custom action？三种说法同时存在。

修正建议：
为动作分三类并固定术语：
1. `CoreCommandAction`: 永远在基础 SDK 中，如 Move/Harvest/Build/Attack/Heal/Spawn/Recycle/Transfer/Withdraw/ClaimController。
2. `VanillaManifestAction`: 标准世界默认启用、由 manifest 生成 SDK，如 Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate。
3. `WorldCustomAction`: 非官方/Layer 3，需要 world-specific SDK。
然后 specs/core/02 只保留 Core + 通用验证框架；VanillaManifestAction 的具体 schema/优先级放到 gameplay/08 或 world rules，并由生成器导入。

### A9 — Low — 文档仍保留 status/phase/P0 风格措辞，虽非架构 blocker，但会污染目标态设计合同

位置：
- specs/future/T2-incremental-snapshot.md:5
- specs/future/T3-shard-protocol.md:5
- design/engine.md:271
- design/tech-choices.md:229
- design/modes.md:12

问题：
本轮评审约束是评审设计合同，不评措辞；但这些 status/Phase 语言不只是风格问题，它会影响实现优先级理解。例如 “Phase 1+ entry gate” 与 Tier 1/Tier 2 entry gate 并存，容易被实现者误读成项目阶段，而不是 capability tier。

修正建议：
用 `Tier implementation gate`、`Before enabling Tier 2`、`MVP core` 等能力维度替代项目阶段/status 语言。保留 “Phase 2a/2b” 作为 tick-internal execution phase，因为那是合法架构术语。

## Missing

1. `Source Gate` 的可执行接口定义：输入、输出、允许进入 gameplay pipeline 的 source 白名单、每个 source 的 audit fields、failure mode。
2. `TickSchedule` / plugin hook ABI：Rhai/WorldRules 如何插入 ECS 链、读写集合、排序、回滚边界。
3. Wasm executor capacity model：worker pool、module/instance/process 生命周期、active player admission、collect deadline 下的调度公平。
4. Generated schema governance：IDL 到 SDK/MCP/REST/docs 的生成产物、CI drift 检测、示例校验。
5. Tier 1 forward-compat subset：哪些 Tier 2/3 预留约束现在必须实现，哪些只是未来 gate，不要混在一起。
6. Gateway API namespace 与 OpenAPI/JSON-RPC contract：运行时 URL、MCP tool schema、REST schema 的最终路径与版本策略。

## Phase Ordering

1. 先修 A1/A2/A4：统一 mutating source/pipeline、CommandIntent/IDL/schema、sandbox 数值/CVE SLA。这些是实现前必须冻结的合同；不修会导致代码生成、安全边界和测试基线全部漂移。
2. 然后修 A5/A8：定义 TickSchedule hook ABI，并拆清 CoreCommandAction / VanillaManifestAction / WorldCustomAction。这样才能安全实现规则引擎和特殊攻击。
3. 再修 A3：补 WasmExecutorPool capacity model，用基准测试验证 3s tick / 500 active players 的现实边界。没有容量模型不要承诺 500 活跃玩家。
4. 最后修 A6/A7/A9：future tier 文档分层、Gateway API 路径命名、去除项目阶段/status 语言。这些不一定阻塞 Tier 1 编码，但会影响长期可维护性和新人理解。
