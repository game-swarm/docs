# R6 Review — rev-gpt-architect

Reviewer: GPT-5.5 / Architect
Scope:
- `/data/swarm/docs/design/DESIGN.md`
- `/data/swarm/docs/specs/p0/01-tick-protocol-spec.md` ~ `09-command-source-model.md`

## Verdict

CONDITIONAL_APPROVE

P0 文档已经从“概念设计”进入了可实现的架构冻结状态：AI 与人类同走 WASM、MCP 不直接下游戏动作、Command Source 显式建模、统一可见性、确定性合同、IDL 单一真相等关键方向都正确，且避免了 Screeps-like 系统常见的公平性与沙箱漏洞。

但仍有若干会在实现早期炸开的规格不一致与边界缺失。它们不推翻架构方向，但应在 Phase 1 开工前修正为一致的冻结合同，否则会导致生成代码、校验器、SDK、沙箱和调试工具各自理解不同。

## Strengths / 亮点

1. AI 公平性模型正确
   - MCP 被定位为 AI 的“屏幕和鼠标”，不是 gameplay controller。
   - AI agent 必须生成/部署 WASM，与人类玩家同路径进入 `WasmSandboxExecutor`。
   - 这是本架构最重要的成功模式：避免了 AI 专属 API 导致的信息、延迟、预算与反作弊不对称。

2. Deferred Command Model 是正确抽象
   - `tick(snapshot) -> Command[]` 把“决策”和“世界变更”解耦。
   - 所有 mutating 操作统一进入验证/排序/应用管线，利于 replay、审计、冲突解释和反作弊。

3. P0-8 IDL 单一真相方向非常好
   - host functions、Command、Validator、SDK、MCP schema、Docs、property tests 从 IDL 生成，是避免协议漂移的正确机制。
   - 对多人长期项目尤其关键，新人也更容易理解系统边界。

4. Command Source Model 解决了常见权限洞
   - Source Gate + server-injected auth context 明确禁止客户端自报 `player_id`。
   - MCP_Query、MCP_Deploy、WASM、Admin、Replay、RuleMod、Tutorial 等来源拆开建模，方向正确。

5. 可见性策略足够工程化
   - “一个 `is_visible_to(entity, player_id, tick)` 函数回答所有输出面”的原则很好。
   - 明确覆盖 snapshot、MCP、WebSocket、REST、replay，可有效防止“调试接口泄密”。

6. 确定性合同意识强
   - 固定 PRNG/hash、禁 f64、禁 `std::HashMap` 迭代顺序、`.chain()` 串行、Replay checksum 都是正确的硬约束。

7. MVP feedback loop 不只关注引擎
   - Learn / Decide / Act / Understand 闭环写得好。
   - 对编程游戏而言，debug/explain/replay 不是锦上添花，而是可玩性的核心。

## Concerns / 发现的问题

### A1 — BLOCKER — Tick 持久化阶段在 DESIGN 与 P0-1 中不一致

DESIGN §3.2 写的是：EXECUTE 阶段中 `FDB 原子提交`，BROADCAST 只做 Dragonfly/NATS 发布。

P0-1 状态机图却把 “FDB 原子提交” 放在 BROADCAST 阶段；后文 §4.2 又说 BROADCAST failure never rolls back committed tick，tick 已在 EXECUTE 阶段持久化。

影响：
- 实现者会不确定 authoritative commit 到底属于 EXECUTE 还是 BROADCAST。
- 如果有人按状态机图实现，BROADCAST 失败语义会被破坏：发布失败可能和 commit 混在一起，导致回滚边界不清。
- Replay / TickTrace / NATS gap recovery 都依赖这个边界。

建议：
- 修正 P0-1 状态机图：EXECUTE = validate/apply/ECS/FDB commit/TickTrace immutable write；BROADCAST = read committed result -> Dragonfly -> NATS/WS。
- 明确 `tick_counter` 只在 FDB commit 成功后推进。

### A2 — BLOCKER — RawCommand 的 `player_id` 与 P0-9 “客户端不可自报 player_id”冲突

P0-2 RawCommand 示例和字段表包含 `player_id`，并要求“必须匹配已认证玩家”。

P0-9 明确说：
- 默认 gameplay 指令只来自 WASM。
- actor/capability/scope 由服务端注入。
- 禁止客户端在 Command body 中自报 `player_id`；如果提供，服务端覆盖。

影响：
- IDL、SDK 和校验器生成时会不确定 `player_id` 是玩家可提交字段还是 server envelope 字段。
- 这是典型 auth confusion 入口：未来某个入口可能忘记覆盖客户端字段。

建议：
- 将 P0-2 RawCommand 改为两层模型：
  - `CommandBody`：玩家/WASM 返回，只含 `sequence` + `action`，不含 `player_id`。
  - `AuthenticatedCommand` / `RawCommandEnvelope`：服务端注入 `auth.source/player_id/session_id/module_version/tick_submitted/tick_target`。
- P0-8 IDL 中也应区分 player-auth envelope 与 command body。

### A3 — HIGH — IDL 与 P0-2/04/DESIGN 的 command JSON 命名不一致

不同文档中同一命令格式出现三种风格：
- P0-2: `{ "action": { "type": "Move", ... } }`
- P0-4 禁止 host function 示例: `{ "cmd": "move", ... }`
- DESIGN §8.5 TypeScript 示例: `{ cmd: "spawn", body: [...] }`
- P0-8 IDL: `commands: Move`, 参数为 typed fields。

影响：
- 这会直接破坏 “IDL 单一真相”目标。
- SDK、JSON Schema、validator、MCP docs 可能生成/手写出不同 shape。
- AI agent 会被文档中的多个命令格式误导。

建议：
- 以 P0-8 IDL 为唯一来源，冻结 wire JSON canonical shape。
- 所有示例统一为同一种：例如 `{ "sequence": 3, "action": { "type": "Move", "object_id": 1001, "direction": "TopRight" } }`。
- 删除或标注 P0-4/DESIGN 中的 `{cmd: ...}` 旧示例。

### A4 — HIGH — 动态资源模型与 Energy 硬编码仍混杂

DESIGN §8 强调核心引擎不硬编码 Energy，资源名来自配置。

但 P0-2 多处仍硬编码：
- `target.source.energy > 0`
- `drone.carry[Energy] >= build_cost(structure)`
- `spawn.energy`
- `InsufficientEnergy`
- `Recycle` 返还“能量给 spawn”

P0-5 snapshot 示例也使用 `resources: { "energy": 5000, "minerals": ... }`，与 `ResourceName` 字符串注册表不完全一致。

影响：
- Validator 会把默认世界假设写死进 P0。
- 自定义资源世界、Arena 规则和 RuleMod 的可配置性会被削弱。
- IDL 中已有 `ResourceName` / `ResourceCost`，但具体校验矩阵还没有完全迁移。

建议：
- P0-2 全部改为 `registry.cost(action)` / `ResourceCost` / `InsufficientResource { resource, required, available }`。
- `Source` 应为 `amounts[resource] > 0` 或明确 Harvest 未指定 resource 时的默认选择规则。
- 保留 Energy 仅作为默认世界配置示例，不作为 validator 语义。

### A5 — HIGH — Rhai RuleMod 的权限边界仍不够硬

DESIGN §8.7 / P0-7 说 RuleMod 是可信服主安装，actions 可 `deduct_resource/award_resource/modify_entity/emit_event`，并且“不能绕过 Command Validation Pipeline”。

但同时 P0-7 §8 又允许规则 System 修改 ECS 资源/组件，`actions.apply(world)` 经校验后写入。这里缺少明确 capability schema：
- 哪些组件可改？
- `modify_entity` 是否可改 `Owner`、`Position`、`hits`、`CodeVersion`？
- 是否能生成/删除实体？
- 是否能绕过 visibility、economy、combat invariants？
- RuleMod 的 action 是否进入 TickTrace 并可 replay？DESIGN 说记录，但 P0-7 没有给 schema。

影响：
- 这是 mod/plugin 系统常见爆点：一句 “可信” 容易演变成任意状态修改，最后 replay 和确定性不可维护。
- 也会让服主安装第三方 mod 的风险不可评估。

建议：
- 为 RuleMod 定义最小 capability manifest，例如 `can_award_resource`, `can_deduct_resource`, `can_emit_event`, `can_set_component(fields whitelist)`。
- 禁止通用 `modify_entity(property, value)`，改为 typed actions。
- RuleMod actions 必须生成确定性的 `RuleModCommand` 并进入与 replay 兼容的 TickTrace。

### A6 — HIGH — Wasmtime 配置和沙箱生命周期存在实现风险，需要 spike 验证

P0-4 写“每 tick fork -> 执行 -> kill”，同时又写模块缓存按 `(module_hash, wasmtime_version)` 缓存，编译一次多 tick 复用。

潜在冲突：
- 每玩家每 tick fork/kill 在 500 玩家、3s tick 下可能开销很大。
- Wasmtime compiled module cache 跨进程共享、预热、内存占用和 fork 后 copy-on-write 行为需要实测。
- `consume_fuel` + host function 成本 + epoch interruption 的组合语义要验证。
- seccomp 白名单中允许 `clone (CLONE_VM | CLONE_VFORK)`、`nanosleep`，但禁 `clock_gettime`，需要确认 Wasmtime/stdlib/allocator 在目标平台不会触发未列 syscall。

影响：
- 这不是架构方向错误，但如果不早测，Phase 2 才发现 fork 模型或 seccomp 不可行会返工。

建议：
- Phase 1 加一个 sandbox spike：50/100/500 modules，测 fork-per-tick vs warm worker pool。
- 把 spike 结果作为是否保留 “每 tick fork” 的 gate。
- 文档中将 “每 tick fork” 标为安全优先 baseline，而非未经验证的最终性能模型。

### A7 — MEDIUM — WASM ABI 返回值描述不完整

P0-8 写 `tick` returns `i32`：0 = success, pointer to command JSON in WASM memory。
P0-4 写返回值是指令 JSON 指针，引擎读取后释放。

缺失：
- 长度在哪里？
- 失败码如何表达？
- 内存所有权如何释放？是否需要 `alloc/dealloc` export？
- 指针和长度的边界校验、UTF-8/JSON decoding 顺序。

影响：
- SDK ABI 与 sandbox host 会无法稳定实现。
- 多语言 WASM SDK 会各自发明返回约定。

建议：
- 冻结 ABI：例如 `tick(ptr,len) -> i64`，高 32 位 len、低 32 位 ptr；或返回指向 `{ptr,len,status}` 的 struct。
- 明确 `alloc/dealloc` 或 canonical ABI 方案。
- P0-8 IDL 应生成 ABI tests。

### A8 — MEDIUM — “查询不进指令管线”与 host function / MCP query 的预算归属需要统一

P0-2 §4 说查询在快照生成阶段处理，不进指令管线。
P0-4 §8 又给 host query function 成本表，计入 fuel。
P0-3 MCP query 有 per-tick rate limit。

这些都合理，但术语需要分层：
- WASM 内 host query：发生在玩家 `tick()` 执行期间，计入 WASM fuel + host call limits。
- MCP_Query：发生在 tick 外的观察/调试通道，计入 MCP rate limit，不产生命令。
- 快照构建：服务端为 tick 输入准备数据，不是玩家可调用 query。

影响：
- 现在 P0-2 的“查询在快照生成阶段处理”容易让人误以为 WASM host query 也在 tick 前预处理。

建议：
- 新增 “Read Path Taxonomy”：Snapshot build / WASM host query / MCP query / REST read。
- 每条路径标明 visibility、budget、audit、cache 策略。

### A9 — MEDIUM — World Rules 中仍有浮点 TOML 示例，与确定性合同冲突

DESIGN §8.8 禁 f64，游戏数值使用整数 + 定点数，Rhai 也禁浮点。

但 P0-7 配置示例中仍有：
- `decay_rate = 0.0`
- `transfer_to_global_cost = { Energy = 0.01 }`
- `damage_multiplier = 1.0`
- `decay_rate = 0.001`

DESIGN 也有 `{Energy: 0.01}` 示例。

影响：
- TOML parse 后如果进入 float，会破坏跨平台确定性合同。
- 即使实现时转换为 fixed，文档也会误导 mod 作者和配置工具。

建议：
- 所有比例统一用 fixed encoding，例如 `10000 = 1.0` 或 `{ value = 100, scale = 10000 }`。
- 文档允许显示层展示 0.01，但配置 wire/storage 只接受整数定点。

### A10 — MEDIUM — Phase ordering 仍有“Phase 2 阻断项”与 Phase 1 任务混排

P0-1、P0-6 标为 Phase 2 阻断项，但 DESIGN roadmap 把部分依赖项放到 Phase 1：
- Phase 1: 基础游戏 API、MCP server scaffold、Deterministic replay hash 验证。
- P0-1 tick protocol、P0-2 validation、P0-8 IDL 实际上是 Phase 1 开始前必须冻结并被代码生成消费的基础。

影响：
- 团队可能误以为 Phase 1 可以先手写基础 API，Phase 2 再补统一协议。
- 这会违反用户偏好的“设计→评审→共识→实现”。

建议：
- 增加 Phase 0.5 / Implementation Gate：IDL canonical JSON、Command envelope、Tick commit boundary、fixed numeric encoding、WASM ABI 必须先修正。
- Phase 1 不应手写 command/validator；应先实现 IDL generator 的最小闭环。

### A11 — LOW — 文档编号和小瑕疵会影响新人理解

示例：
- DESIGN 有两个 “## 10”：World/Arena 与 贡献指南。
- P0-1 有两个 “### 3.3”。
- P0-9 heading 顺序为 `## 6` 后 `## 5`。
- P0-2 Schema 片段引用 `#/definitions/Command`，但没有给 definitions 片段，容易让人误以为这是完整 schema。

影响：
- 不影响架构，但会降低新人 onboarding 与自动文档生成质量。

建议：
- 在 Phase 0.5 做一次 doc lint：heading sequence、duplicate heading、schema completeness、示例格式一致性。

## Missing / 缺失项

1. Canonical wire format
   - 缺一个明确的 `CommandBody` / `AuthenticatedCommandEnvelope` / `TickOutput` JSON Schema 全量定义。

2. WASM ABI 完整规范
   - 缺 ptr/len/status/free 的稳定 ABI，必须在 SDK 前冻结。

3. RuleMod capability schema
   - 需要 typed action whitelist、manifest、replay schema、determinism tests。

4. Numeric encoding policy
   - 需要统一说明：所有配置、IDL、TickTrace 中的比例/倍率如何以定点整数表达。

5. Sandbox performance spike result
   - fork-per-tick 是否可接受必须有数据，而不是只凭安全直觉。

6. Replay/TickTrace schema
   - P0-8 提到生成 TickTrace schema，但 P0 文档未给足够字段定义；这会影响 replay、audit、debug explanation。

## Phase Ordering / 建议阶段顺序

建议插入 Phase 0.5：Spec hardening before implementation。

Phase 0.5 必须完成：
1. 修正 Tick commit boundary：EXECUTE commit，BROADCAST never rollback。
2. 冻结 canonical command JSON：删除客户端 `player_id`，引入 server-injected auth envelope。
3. 用 P0-8 IDL 生成最小 Command enum + JSON Schema + validator skeleton。
4. 统一所有示例命令格式。
5. 将所有资源/成本校验从 Energy 硬编码迁移到 ResourceRegistry。
6. 冻结 WASM ABI：tick return、alloc/dealloc、error code、output size。
7. 将所有 float 配置改为 fixed integer encoding。
8. 为 RuleMod actions 定义 typed capability whitelist。
9. 做 sandbox spike：fork-per-tick vs worker pool，输出数据后再定 baseline。

然后再进入 Phase 1：
- ECS world minimal slice。
- IDL-generated command validation。
- WASM sandbox prototype。
- Minimal MCP read/deploy scaffold。
- Deterministic replay checksum CI。

## Final Assessment

架构主方向可批准，尤其是 “MCP 不是 gameplay channel，WASM 是唯一执行路径” 这一点非常正确。当前不建议直接进入实现主干；建议先用 1 个短 Phase 0.5 清理规格冲突。清理后可进入 Phase 1 MVP vertical slice。
