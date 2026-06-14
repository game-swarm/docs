# R10 终审 — rev-dsv4-security (DeepSeek V4 Pro, Security Primary)

> **评审范围**: DESIGN.md + tech-choices.md + specs/p0/ (全部 9 篇)
> **评审日期**: 2026-06-14
> **方法论**: 协议一致性验证、数据流追踪、竞态条件检测、信任边界分析、R8/R9 发现追踪

---

## Verdict: APPROVE_WITH_RESERVATIONS

Phase 0 架构冻结的质量持续提升。自 R8 以来，多项安全问题已被修复：prompt injection 分隔符改为 Unicode `‖‖‖`（R8 H-1）、`public_spectate + spectate_delay ≥ 50` 约束（R8 H-2）、refund deploy-reset 规则（R8 H-3）、`modify_entity` 已从 Rhai API 中移除（R8 H-4）。这些修复体现了设计团队对安全评审的响应。

然而，R9 提出的 1 Critical + 3 High 均未落地修复，且本轮发现 2 个新 High + 5 个新 Medium。三层信任模型（WASM → Rhai → Rust）和单一指令管线仍然稳固，但 WASM 沙箱的模块校验存在一个遗留的高危绕过路径，路径规划（pathfinding）的计费模型和阶段归属在两个维度上均有缺陷。

---

## Critical

### C1: WASM start section 绕过 `_start` 导出检查 — 模块预执行向量 (R9-C1, 未修复)

**位置**: P0-4 §2.4

**描述**:

P0-4 §2.4 的模块校验代码已从 R8 版本改进——新增了 `__wasm_call_ctors` 导出检查和 `InitFunctionForbidden` 拒绝码。但核心问题未修复：

```rust
// P0-4 §2.4 当前代码 —— 仍只检查导出
if module.export("_start").is_some() {
    return Err(Rejection::StartFunctionForbidden);
}
if module.export("__wasm_call_ctors").is_some() {
    return Err(Rejection::InitFunctionForbidden);
}
```

WASM 二进制格式的 **start section**（非导出函数，是模块二进制头中的一个独立 section）指定一个函数在模块实例化后自动调用。这个函数**不需要被导出**即可执行。Wasmtime 提供 `Module::start_function()` API 来检查这个 section，当前代码未使用此 API。

**数据流**: `WASM module deploy → validate_module() → Module::from_binary() → Instance::new() [start section 在此执行] → tick()`

**影响**: 恶意 WASM 模块可以在 `tick()` 被调用之前通过 start section 执行任意代码。虽然 seccomp + cgroup 提供 OS 级隔离，但在 Wasmtime 沙箱内可能消耗 fuel budget、通过 host function 查询世界状态。

**修复建议** (同 R9-C1):

```rust
// 检查 start section（WASM 二进制格式，非导出函数）
if module.start_function().is_some() {
    return Err(Rejection::StartFunctionForbidden);
}

// 检查全局初始化器是否为 const-only（防止非 const 全局初始化器预执行）
for global in module.globals() {
    if !is_const_initializer(global) {
        return Err(Rejection::NonConstGlobalInit);
    }
}
```

需要在恶意 WASM 样本库（P0-4 §5.1）中添加 start section 测试用例。

---

## High

### H1: `host_path_find` fuel 计费模型严重低估 — 服务器端计算 DoS (R9-H1, 未修复)

**位置**: P0-4 §8, P0-2 §4.3

**描述**:

P0-4 §8 定义 path_find 的 fuel 成本为 `10,000 + 50/tile`，其中 `50/tile` 是**返回路径的 tile 数**（上限 100 → 最大 15,000 fuel），不是 A* 算法实际探索的节点数。

在 256×256 房间地图上，如果两点间无 ≤100 步路径或存在迷宫地形，A* 可能探索 10,000–50,000 个节点后才确定结果。玩家支付 15,000 fuel，引擎消耗相当于 500,000+ fuel 的计算量。

缓存键 `(from, to, terrain_hash)` 在以下场景被绕过：
- 攻击者在 10 次调用配额内使用不同坐标组合
- 地势频繁变化的世界（玩家建造/拆除墙壁）
- 多个玩家同时查询不同坐标对

**影响**: 引擎端实际 CPU 消耗可达 WASM fuel 体现的 100–1000 倍。高并发下可能拖垮 COLLECT 阶段的 sandbox worker 或 EXECUTE 阶段的串行校验。

**修复建议**:

1. fuel 成本公式改为 `10,000 + cost_per_explored_node × nodes_explored`，由引擎在执行后追加扣费
2. 或在 `host_path_find` 内部设置独立探索节点上限（如 50,000 nodes），超限返回 `PathTooComplex`
3. 增加全局 MAX_PATH_FIND_ATTEMPTS_PER_TICK 限制，防止多玩家同时触发高昂寻路

### H2: path_find 在 COLLECT 和 EXECUTE 两个阶段均执行 — 双倍计算 + 燃料计费缺口

**位置**: P0-1 §2, P0-1 §3, P0-2 §3.2, P0-4 §8

**描述**:

path_find 在 tick 生命周期中出现了两次：

1. **COLLECT 阶段**：WASM 模块通过 `host_path_find` 调用寻路——受 10 次/tick 配额 + fuel 计费限制（P0-4 §8）
2. **EXECUTE 阶段**：MoveTo 指令的校验矩阵要求 `path_exists`（P0-2 §3.2），这在 EXECUTE 阶段执行——不受 per-WASM 限制

关键问题：EXECUTE 阶段的 `path_exists` **不计入 player fuel**。这是一个免费计算通道。攻击者提交 100 条 MoveTo 指令（MAX_COMMANDS_PER_PLAYER），每条指向不同坐标。COLLECT 阶段的 10 次 `host_path_find` 配额被完全绕过——EXECUTE 阶段仍会为所有 100 条 MoveTo 指令执行 path_exists。

**数据流**: `WASM tick() → Command[] with 100 MoveTo → EXECUTE phase → per-command path_exists × 100 → serial execution`

**影响**: EXECUTE 阶段有 500ms 硬超时（P0-1 §3）。100 条 MoveTo 指令的 path_exists 在串行 EXECUTE 阶段执行，每次可能耗时 5–50ms → 总耗时 500ms–5s。单玩家即可使 EXECUTE 阶段超时。500 玩家 × 即使每个只有 10 条 MoveTo = 5,000 次寻路在 500ms 串行窗口中。

**根本原因**: path_find / path_exists 的执行时机归属不明确。如果它属于 COLLECT 阶段（作为 WASM host function），则 EXECUTE 阶段不应重复计算；如果它属于 EXECUTE 阶段（作为校验步骤），则 COLLECT 阶段的 `host_path_find` 只是"预查"——两次计算之间地形可能已变化（其他玩家的指令先执行），导致预查结果无效。

**修复建议**:

1. 明确 path_find 的归属阶段。建议：COLLECT 阶段做 path_find（WASM 决定目的地），EXECUTE 阶段仅验证路径长度 ≤ MAX_PATH_LENGTH（便宜操作），不重做 path_exists
2. 或者：EXECUTE 阶段的 path_exists 复用 COLLECT 阶段的缓存结果（接受短暂不一致——MoveTo 可能因地形变化而失败，计入 `PathChanged` 拒绝码，退 50% fuel）
3. 对 EXECUTE 阶段的 path_exists 强制执行同样的配额限制（10 次/玩家/tick）
4. 对 MoveTo 指令数量设置独立上限（如 10 条/玩家/tick，而非共用 100 条全局配额）

### H3: `swarm_simulate` 缺少 MAX_SIMULATE_TICKS 上限 (R9-H3, 未修复)

**位置**: P0-3 §4.4, P0-9 §2.3

**描述**:

P0-3 §4.4 定义 `swarm_simulate` 为"离线模拟：给定世界快照，预测未来 N tick"，但**没有定义 N 的上限**。P0-9 §2.3 给出 budget = `0.5 × MAX_FUEL`（5M fuel），但这只在每个 simulated tick 内部消耗 fuel。如果 N=1,000,000，即使每 tick 只消耗少量 fuel，模拟循环本身的计算量也会非常巨大。

虽然 P0-3 限制为 5/tick (World) / 3/tick (Arena)，但单次 simulate 可以运行任意长时间。

**当前保护不足**: 0.5 × MAX_FUEL 是 per-simulated-tick 的 WASM fuel 限制，不是对模拟 tick 总数的限制。没有墙钟超时保护。

**修复建议**:

1. 在 P0-3 中显式定义 `MAX_SIMULATE_TICKS`（建议 100–200 tick）
2. Simulate 执行需设置独立墙钟超时（如 500ms）
3. Simulate 操作的是快照副本——失败不应影响正常 tick 的 FDB 事务

---

## Medium

### M1: JSON 数组宽度攻击 — 合法但必失败的指令消耗 FDB 资源 (R9-H2 降级)

**位置**: P0-2 §1.1, P0-2 §3

**描述**:

P0-2 §1.1 限制 JSON 深度 ≤ 10 层，MAX_COMMANDS_PER_PLAYER=100。但没有对指令的"有效性密度"设限。攻击者可构造 100 条合法但必失败的指令（如全部 Move 到 Wall 格），每条指令在预校验阶段触发 world state 查询（FDB read per entity check）。100 条指令 × 3–5 个 FDB key = 300–500 次数据库读取，全部产生 RejectionReason + TickTrace 日志。

**与 H2 的交互**: 如果 100 条全部是 MoveTo（路径校验在 EXECUTE 阶段），则所有 100 条 path_exists 在 EXECUTE 串行阶段执行。组合攻击面显著。

**修复建议**:

1. 在预校验阶段增加快速短路：对明显必失败的指令（Move 到 Wall）在读取 world state 前通过 terrain cache 快速判断
2. 同一 tick 内同一玩家的拒绝率 > 80% → early abort，该玩家剩余指令直接丢弃
3. MoveTo 的 path_find 明确归属到 COLLECT 阶段，利用 sandbox worker 的并行性

### M2: `amount=0` 指令未被显式拒绝 — 浪费管线资源

**位置**: P0-2 §3.4

**描述**:

Transfer/Withdraw 指令的 `amount` 字段没有显式校验 `amount > 0`。`amount=0` 的 Transfer 会通过所有校验（has_resource: 0 ≤ carry_amount 为真，target_has_space: true），消耗一个指令槽位，走完整校验管线，产生无意义的 TickTrace 日志。虽然不造成经济损害，但可作为填充攻击的一部分——100 条 amount=0 的 Transfer 指令消耗与 100 条合法指令相同的校验资源。

**修复**: 在校验矩阵中添加 `amount > 0` 检查，失败码 `InvalidAmount`。

### M3: `host_get_world_rules` 在 P0-4 §3.2 允许列表和 §8 成本表之间的不一致

**位置**: P0-4 §3.2, P0-4 §8, DESIGN §5.1

**描述**:

P0-4 §3.2 "允许的 Host Function" 仅列出 4 个函数（get_terrain, get_objects_in_range, path_find, get_world_config）。但 P0-4 §8 成本表包含了第 5 个函数 `host_get_world_rules`（1,000 fuel, 16 KB）。DESIGN §5.1 也列出了 `host_get_world_rules`。

此不一致可能导致：
- 如果 P0-4 §3.2 是规范权威来源 → `host_get_world_rules` 不应被允许，但 WASM 模块可能期望它可用（SDK 已生成调用代码）
- 如果 P0-4 §8 和 DESIGN §5.1 是权威来源 → 则在实现时需确认函数签名，且在 P0-4 §2.4 的导入白名单中必须包含此函数

**修复**: 在 P0-4 §3.2 中补充 `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;` 的签名声明。在 P0-4 §2.4 的 ALLOWED_HOST_FUNCTIONS 白名单中确认包含此函数。

### M4: FDB 事务重试无指数退避 — 可能放大冲突

**位置**: P0-1 §3.4

**描述**:

> `txn.commit()` 失败 → 最多重试 3 次 → 全部失败则 tick 放弃。

如果 FDB 冲突源于高竞争（多个 shard 修改同一 key），用相同数据重试 3 次大概率继续冲突。每次重试都会重新读取并重新验证所有指令。在降级模式触发前已经浪费了 3+ tick 的计算资源。

**修复**: 在重试间隔中加入指数退避（1s, 2s, 4s），并在第 2 次重试时设置 `join_lock = true`（提前阻止更多写入竞争）。

### M5: Controller `downgrade_timer` 在 safe_mode 期间的行为未定义

**位置**: DESIGN §3.1

**描述**:

Controller 的 `downgrade_timer`（默认 5000 tick）在失去 owner 后开始递减。`safe_mode`（默认 0 tick 剩余时不激活）阻止攻击。但规范未定义：
- `downgrade_timer` 在 `safe_mode` 期间是否暂停？
- `downgrade_timer` 在新 owner 认领时是否重置？
- 房间有活跃防守 drone 但无 Controller owner 时，timer 是否继续递减？

攻击者可以在 safe_mode 期间集结兵力，在 safe_mode 结束后立即攻击——如果 timer 在 safe_mode 期间持续递减，Controller 可能在安全结束后立即降级。

**修复**:

1. `downgrade_timer` 在 `safe_mode` 期间暂停
2. `downgrade_timer` 在新 owner 认领时重置为 5000
3. `downgrade_timer` 仅在 Controller 无 owner **且** 房间内无该玩家的任意 drone/viewer 时递减（真正被遗弃）

### M6: 沙箱 worker 进程清理机制不明确 — tmpfs 泄漏风险

**位置**: P0-4 §1

**描述**:

> 生命周期: sandbox worker 进程每 tick 新 fork，执行一个玩家，返回指令，然后 kill。

`kill` 是 SIGKILL 还是 SIGTERM？P0-4 §4.1 的 seccomp 允许列表中包含 `exit` 和 `exit_group`，但未说明引擎使用什么信号终止 worker。如果是 SIGKILL：
- 子进程无法清理资源（独立 /tmp tmpfs 16MB 不会自动释放）
- cgroup 的 `memory.max` 和 `pids.max` 提供硬限制，但 tmpfs 残留是内核级资源泄漏

**修复**: 在 P0-4 §1 中明确：
1. kill 使用 SIGKILL（确保终止）
2. sandbox 使用独立的 mount namespace + tmpfs（进程终止 = 内核自动清理）
3. 引擎侧增加 worker 超时看门狗：fork 后 3000ms 未返回 → force kill + 清理 mount namespace

### M7: `spawn_policy = "Inherit"` 缺少房间所有权验证规范 (R8-H5, 未修复)

**位置**: DESIGN §8.2

**描述**:

DESIGN §8.2 定义 `Inherit` 为 "从已有殖民地出生——需该房间存在玩家的 Controller 且 level ≥ 1"。但验证规则不精确：
- "存在玩家的 Controller" 是指**当前**归属于该玩家，还是**曾经**归属于该玩家？
- 如果 Controller 被敌方占领但未拆除，旧 owner 能否继续 Inherit spawn？
- P0-7 §6 World/Arena 默认值表中 Inherit 甚至不在表中（仅有 RandomRoom 和 FixedSpawn）

**攻击场景**: 玩家 A 短暂占领 W1N1 后失去。Controller 仍存在（归属 B）。A 通过 Inherit 继续在 W1N1 spawn drone → 在 B 的领土内凭空出现单位。

**修复**: 明确定义 Inherit 验证规则：spawn 仅允许在玩家**当前**拥有 Controller（owner == player_id）**且**该房间存在活跃 Spawn 建筑的房间。非历史所有权。

---

## Informational

### I1: `world_seed` 未在 P0-5 §2.4 显式列出

P0-5 §2.4 "隐藏信息" 表中提到 "RNG 种子 ❌ 始终隐藏"，但未单独列出 `world_seed`。虽然它属于 Admin-only 级别，但显式列出可防止实现时意外将其暴露在 snapshots 或日志中。

### I2: Tutorial 来源隔离依赖单点 `world.mode` 检查

P0-9 §2.4: "Tutorial 来源的指令仅可在 `world.mode = 'tutorial'` 的世界中接受。" 这是 Source Gate 中的一个 if 语句。如果将来添加新 world.mode 且忘记更新此检查，Tutorial 指令可能泄漏到非教程世界。建议改为白名单模式：Tutorial 来源在明确的 tutorial world ID 列表中有效。

### I3: MoveTo 的 path_exists 在 EXECUTE 阶段串行执行 — 与 COLLECT 阶段的 WASM path_find 不是同一调用

已在 H2 中详述。此 I3 仅记录：两个阶段的 path_find 使用相同缓存键但可能返回不同结果（COLLECT 和 EXECUTE 之间的地形可能因其他玩家的指令而改变）。

### I4: Body part 成本表权威来源不明确

P0-8 §2 `body_cost` 声明为 "权威来源"（IDL → codegen → SDK → docs）。但 DESIGN §8.4 的 `[actions.costs]` 示例中也包含 `body_part.*` 值。DESIGN 中缺少指向 P0-8 为权威来源的注释。如有人在设计讨论中引用 DESIGN.md 的值而非 IDL，可能导致实现偏差。

### I5: Global Storage 指令 (TransferToGlobal/TransferFromGlobal) 未纳入 P0-2 校验矩阵

P0-8 §2 定义了 `global_storage_commands` 的 validator 字段，但 P0-2 §3 的逐指令校验矩阵仅覆盖 Move 到 Recycle。Global storage commands 有安全关键属性（transport 期间不可用、敌方拦截风险、double-spend），需要纳入 P0-2 的正式校验矩阵。

### I6: `resource_types` 重复 `name` 无校验 — 静默覆盖

P0-7 §2 允许 `[[resource_types]]` 使用任意 `name`，但 `validate_config`（§7）未检查重复 name。HashMap 插入重复键 → 后者静默覆盖前者。如果定义第二个 `Energy` 且 `starting_amount = 0`，新玩家将获得 0 起始能量——这是一个静默的破坏性配置错误。

### I7: `DamageTypes` 抗性乘积累积 — `default_resistance = 0` 导致零伤害

DESIGN §8.4 的抗性系统使用乘法（`final = body_resistance × attribute_resistance × default_resistance`）。如果服主设置 `default_resistance = 0.0`（无论有意或笔误），所有该类型伤害归零。虽然没有直接安全影响（服主可信），但缺少配置校验（`validate_config` 未检查 damage_types 的 default_resistance > 0）。

---

## R8/R9 Finding Status — 追踪表

| ID | Round | Severity | 描述 | Status |
|----|-------|----------|------|--------|
| R8-H-1 | R8 | High | Player-name delimiter collision | **RESOLVED** — P0-3 §6.3 改用 Unicode `‖‖‖` |
| R8-H-2 | R8 | High | Spectator bypass replay_privacy | **RESOLVED** — P0-5 §3.5 新增 `spectate_delay ≥ 50` 约束 |
| R8-H-3 | R8 | High | Refund carryover exploit | **RESOLVED** — P0-2 §7.2 deploy-reset 规则 |
| R8-H-4 | R8 | High | RuleMod modify_entity no whitelist | **RESOLVED** — DESIGN §8.7 `modify_entity` 已删除 |
| R8-H-5 | R8 | High | Inherit spawn validation | **UNRESOLVED** → R10 M7 |
| R9-C1 | R9 | Critical | WASM start section bypass | **UNRESOLVED** → R10 C1 |
| R9-H1 | R9 | High | path_find fuel underestimation | **UNRESOLVED** → R10 H1 |
| R9-H2 | R9 | High | JSON width attack | **UNRESOLVED** → R10 M1 (降级) |
| R9-H3 | R9 | High | swarm_simulate N cap missing | **UNRESOLVED** → R10 H3 |
| R9-M1 | R9 | Medium | amount=0 not rejected | **UNRESOLVED** → R10 M2 |
| R9-M2 | R9 | Medium | FDB retry amplification | **UNRESOLVED** → R10 M4 |
| R9-M3 | R9 | Medium | sandbox worker cleanup | **UNRESOLVED** → R10 M6 |
| R9-M4 | R9 | Medium | visibility filter cost | **UNRESOLVED** — P0-4 §8 未修改 |
| R9-M5 | R9 | Medium | HTTP/2 multiplexing | **UNRESOLVED** — P0-3 §5.3 未提及 |
| R9-I1 | R9 | Info | world_seed in P0-5 | **UNRESOLVED** → R10 I1 |
| R9-I2 | R9 | Info | Tutorial source isolation | **UNRESOLVED** → R10 I2 |
| R9-I3 | R9 | Info | path_find timing ambiguity | **ESCALATED** → R10 H2 (升级为 High) |
| R9-I4 | R9 | Info | body_cost authority | **UNRESOLVED** → R10 I4 |

---

## 数据流完整度追踪

| 阶段 | 校验点 | 规范 | 状态 |
|------|--------|------|------|
| World State → Snapshot JSON | `is_visible_to()` 过滤 | P0-5 §3.1 | ✅ 完整 |
| Snapshot → WASM linear memory | seccomp + cgroup 隔离 | P0-4 §4 | ✅ 完整 |
| WASM `tick()` execution | fuel metering + epoch interruption | P0-4 §2 | ✅ 完整 |
| WASM → Command JSON | JSON Schema validation | P0-2 §1.1 | ✅ 完整 |
| Command JSON → RawCommand | Schema + bounds + auth injection | P0-9 §3 | ✅ 完整 |
| RawCommand → Validation | Source Gate + Auth Verify | P0-9 §4 | ✅ 完整 |
| Validation → Application | Per-command matrix | P0-2 §3 | ⚠️ path_exists 归属不清 (H2) |
| Application → FDB commit | FDB transaction | P0-1 §3.4 | ⚠️ 重试无退避 (M4) |
| FDB → Delta → NATS → Client | Visibility filter on delta | P0-5 §3.3 | ✅ 完整 |

**无「信任下游会校验」的假设**——每个阶段独立执行校验。Source Gate (P0-9) + Command Validation (P0-2) + Visibility Filter (P0-5) 构成三道防线。

---

## 算法边界审查

| 算法 | 最大计算量 | 限制机制 | 风险 |
|------|-----------|---------|------|
| Pathfinding (A*) | MAX_PATH_LENGTH=100, 10 calls/tick (WASM) + 100 MoveTo validations (EXECUTE) | fuel 10,000+50/tile, 缓存 (from,to,terrain_hash) | **CRITICAL**: H1 燃料低估 + H2 双阶段执行。总计算量可达 WASM 体现的 1000× |
| Visibility filter | O(vision_sources × entities_in_range) | per-tick cache (tick, player_id) | LOW: 缓存有效 |
| Seeded shuffle | O(N active players) | N ≤ 500 | LOW: 线性 |
| `get_objects_in_range` | range ≤ 10, hex grid ≤ ~330 cells | 5 calls/tick | LOW: fuel 适当 |
| WASM compilation | 30s timeout, 512MB | 5 concurrent, per-deploy cache | LOW: 独立进程 |
| Simulate | **无上限** | 5/tick rate limit 但无 tick 数上限 | **HIGH**: H3 |

---

## 并发模型一致性验证

Tick 协议的三阶段模型（COLLECT 并行 → EXECUTE 串行 → BROADCAST 即时）在并发层面是自洽的：
- 某玩家超时 → 空指令列表，不阻塞其他玩家 ✅
- EXECUTE 阶段串行保证了先到先得的竞争解决 ✅
- FDB 原子提交保证全或无 ✅

**发现的并发缺陷**: path_find 在 COLLECT（并行）和 EXECUTE（串行）两个阶段均执行。COLLECT 阶段的结果在 EXECUTE 阶段可能过期（地形变更），但 EXECUTE 仍重新计算而不利用缓存。这是性能浪费而非正确性 bug——但浪费量在 500 玩家规模下不可接受。

---

## 与 R9 其他 Security Reviewer 的交叉对比

*等待 Phase 2 交叉评审后填写。若 rev-claude-security 或 rev-gpt-security 发现同向问题，在此记录。*

---

*reviewer: rev-dsv4-security | model: deepseek-v4-pro | direction: Security (Primary)*
