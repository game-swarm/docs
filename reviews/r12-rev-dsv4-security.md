# R12 — Security Review (rev-dsv4-security)

**Reviewer**: DeepSeek V4 Pro (Security Direction, Primary)
**Date**: 2026-06-14
**Scope**: DESIGN.md §1–11, tech-choices.md, specs/p0/ (01–09), PLANNER-OUTPUT.md
**Profile**: Tick protocol consistency verification, data flow tracing, race condition detection
**Context**: R12 follows R11 (previous round). Issues are tracked as RESOLVED / UNRESOLVED / NEW.

---

## Verdict: REQUEST_MAJOR_CHANGES

R11 提出的 2 个 Critical + 4 个 High 问题中，仅 C1（host function 可见性过滤）得到完整修正。其余 1 个 Critical、3 个 High 未变。此外，本轮发现 1 个新 Critical、4 个新 High、4 个新 Medium。

核心问题仍未解决：R11-gpt 指出的 **player_id auth-confusion (C1)** 和 **tick 原子性 (C2)** 是两个设计级别的安全隐患，在当前文档中一字未改。R12 追加发现 **Rhai actions 绕过 Command Validation Pipeline** 的第三条设计级问题。Phase 2 实现前必须修正这三项。

---

## R11 Issue Resolution Matrix

| R11 ID | Severity | Source | Description | R12 Status |
|--------|----------|--------|-------------|------------|
| C1-dsv4 | Critical | dsv4 | Host function 可见性过滤缺失 | ✅ **RESOLVED** — P0-4 §3.2 显式标注"结果经 `is_visible_to` 过滤"，P0-5 §3.0 新增 Host Functions 输出面 |
| C2-dsv4 | Critical | dsv4 | Rhai state API 暴露完整世界状态 | ❌ **UNRESOLVED** — DESIGN §8.7 / P0-7 §4 未变 |
| C1-gpt | Critical | gpt | player_id 在 Command body 中导致 auth-confusion | ❌ **UNRESOLVED** — P0-2 §2 未变 |
| C2-gpt | Critical | gpt | Tick FDB+Bevy+RuleMod 原子性 | ❌ **UNRESOLVED** — P0-1 §3.4 未变 |
| C3-gpt | Critical | gpt | WASM tick() ABI 不安全 | ❌ **UNRESOLVED** — P0-4 §3.1 / P0-8 未变 |
| H1-dsv4 | High | dsv4 | Pathfinding 计算量无服务端预算 | ❌ **UNRESOLVED** |
| H2-dsv4 | High | dsv4 | swarm_simulate 聚合 DoS | ❌ **UNRESOLVED** |
| H3-dsv4 | High | dsv4 | PLANNER-OUTPUT 矛盾 | ❌ **UNRESOLVED** — Phase 1.6/2.2/2.5 仍含错误设计 |
| H4-dsv4 | High | dsv4 | 快照与 host fn 可见性不同步 | ❌ **UNRESOLVED** — P0-1 §2.3 未显式声明不可变视图 |

---

## Critical

### C1 (UNRESOLVED from R11-gpt): RawCommand body 含 `player_id` — auth-confusion / IDOR

**影响范围**: 整个指令系统

P0-2 §2 的 RawCommand schema 含 `player_id` 字段，校验规则为"必须匹配已认证玩家"。P0-9 §3.3 要求"客户端不可自报 player_id，服务端覆盖"。两个文档描述不同的实现路径，若实现者照 P0-2 读取 body 中的 player_id，则：

- WASM 模块可输出 `{"player_id": victim_id, "action": ...}` 并以受害者身份提交指令
- MCP/REST/Tutorial/TestHarness 复用同一 JSON schema 时出现双源身份
- 审计日志记录 `auth.player_id` 但 validator 使用 `command.player_id` → 审计盲区

**修复**: P0-2 §2 RawCommand 中删除 `player_id` 字段。引入 `AuthenticatedCommand { auth: AuthContext, raw: RawCommand }` 类型。Validator 所有 ownership 判断只读 `auth.player_id`。JSON schema 拒收 `player_id`、`source`、`scope`、`auth` 保留字段。

---

### C2 (UNRESOLVED from R11-gpt): Tick 原子性 — FDB 事务不覆盖 Bevy World + RuleMod + 副作用

**影响范围**: 世界状态完整性、回放可验证性、反作弊基础

P0-1 §3.4 将整个 EXECUTE 包裹在 FDB 事务中，但 FDB 事务仅覆盖 FDB 写入，不覆盖：

1. **Bevy World 内存突变** — FDB rollback 需 `world.restore(snapshot)`，但 snapshot 的开销和时机未定义
2. **RuleMod actions 副作用** — `actions.apply(world)` 直接修改 ECS 组件，不受 FDB 事务保护
3. **TickTrace / metrics / refund credit** — 这些副作用在 FDB 事务内部产生，但 rollback 时如何撤销未定义
4. **FDB commit unknown**（网络断开）— 无幂等键设计，可能同一 tick 被重复提交
5. **TickTrace write fail** — P0-1 §6 允许"tick 完成但审计日志不完整"，与"可回放/反作弊"核心目标冲突

**修复**: EXECUTE 改为纯函数式 staging：`(WorldBefore, Commands, Rules, Seed) → ExecutionPlan { world_after, tick_trace, metrics, cache_delta }`。FDB 单事务写入 staged result，含幂等键 `/tick/{N}/commit_id`。事务提交成功前禁止任何外部副作用。FDB commit unknown 时先查询是否已提交。TickTrace 必须与 state 同事务——若不可写，本 tick abandon。

---

### C3 (NEW): Rhai RuleMod actions 绕过 Command Validation Pipeline

**影响范围**: 所有安装了模组的世界；经济公平性

P0-7 §8 声明 RuleMod "绝不可绕过 Command 校验管线"，但 DESIGN §8.7 / P0-7 §4 提供的 API 直接规避了这一约束：

```rust
actions.deduct_resource(player_id, resource, amount)   // 直接扣资源
actions.award_resource(player_id, resource, amount)    // 直接加资源
actions.damage_entity(entity_id, amount, reason)       // 直接伤害
actions.set_entity_flag(entity_id, flag, value)        // 直接设标记
```

这些 actions 通过 `actions.apply(world)` 写入世界——走的是 ECS System 内路径，完全不经过 P0-2 Command Validation Pipeline 的任何环节（Schema 校验、预校验、Source Gate、所有权检查、范围检查）。

**攻击场景**：
- 恶意模组在 `tick_end.rhai` 中：`actions.award_resource(attacker_id, "Energy", 999999)` — 无限刷资源
- `actions.damage_entity(victim_drone, 999999, "模组后门")` — 秒杀任何单位
- `actions.set_entity_flag(enemy_drone, "stunned", true)` — 跨玩家修改状态

P0-7 提到"mini-validator"但未定义其检查项。当前描述 `actions` 的能力与完整的 Command Validation 覆盖范围之间存在巨大缺口。

**修复**：
- RuleMod actions 必须进入 ExecutionPlan（见 C2），与其他指令一同在校验管线中处理
- `deduct_resource` / `award_resource` 必须校验：资源存在、不超过容量上限、受世界规则约束
- `damage_entity` 必须校验：目标存在、伤害量不超过世界规则上限、不跨所有权（除非 PvP 启用且为敌对）
- `set_entity_flag` 的白名单必须穷举且不可由模组扩展——当前"白名单标记"未定义
- 所有 RuleMod actions 写入 TickTrace，纳入回放和审计

---

## High

### H1 (NEW): `player_view="full"` 导致 AI MCP 获得超过 WASM snapshot 的信息优势

**影响范围**: 启用 `player_view="full"` 的世界中的 AI 玩家公平性

P0-5 §3.5 表格中 `player_view = "full"` 行显示：MCP 查询返回"全地图（无视 fog）"。P0-3 §4.2 说 `swarm_get_snapshot` 返回"同 WASM tick() 接收的输入"。两者不可同时成立：

- 若 MCP `swarm_get_snapshot` 与 WASM `tick()` 输入相同 → WASM snapshot 也是全地图 → fog-of-war 无效
- 若 MCP `swarm_get_snapshot` 返回全地图但 WASM `tick()` 受限 → AI 可通过 MCP 获取全图信息后生成/部署代码，获得信息优势

P0-5 §3.5 的注释说"WASM `tick()` 收到的 snapshot 始终按 `is_visible_to(player)` 过滤"，但未约束 MCP 查询层。AI 玩家每 tick 可通过 `swarm_get_snapshot`（或任何 MCP read tool）获取全图，然后在其 WASM tick() 代码内基于全图信息做决策——信息已通过 prompt 注入 WASM 的环境变量/策略中。

**修复**：
- 在公平竞争模式下，MCP `swarm_get_snapshot` 和所有 MCP read tools 必须与 WASM tick() snapshot 使用完全相同的可见性过滤器
- 新增 `swarm_get_player_view` 工具用于 UI/观战视图，标记为"不应用于 AI 决策"
- `swarm_get_available_actions`、`swarm_dry_run_commands`、`swarm_simulate` 也必须绑定 snapshot_id 且使用相同的可见性约束
- P0-5 §3.5 表格中 MCP 列修正为 `is_visible_to` 过滤（与 WASM 一致）

---

### H2 (NEW): `damage_multiplier` 类型矛盾 — 浮点 vs 定点，违反 Determinism Contract

**影响范围**: 确定性保证

DESIGN §8.8 Determinism Contract 明确要求"禁 f64（跨平台/编译器非确定），游戏引擎数值用 `i64 × 精度因子`"。DESIGN §8.2 战斗规则中 `damage_multiplier` 定义为 `fixed<u32,4>`（定点数，默认 10000 = 1.0）。

但 P0-7 §2 (world.toml schema) 和 P0-7 §7 (validate_config) 中存在矛盾：

```toml
# P0-7 §2
[combat]
damage_multiplier = 1.0     # ← 这是 TOML float，不是 fixed<u32,4>
```

```rust
// P0-7 §7
if config.combat.damage_multiplier < 1 {  // ← 整数比较，对 fixed<u32,4>=10000 恒为 false
    errors.push("damage_multiplier must be positive");
}
```

若 `damage_multiplier` 是 f64，违反 Determinism Contract。若它是 `fixed<u32,4>`：TOML 中应写 10000（而非 1.0），validate_config 中应比较 0（而非 < 1），且所有使用处需做定点数运算。

同样的矛盾出现在 `source_regeneration_rate`、`build_cost_multiplier`、`drone_decay_rate`、Rhai mod `room_superlinear`、`decay_rate` 等所有标记为 `fixed<u32,4>` 的字段。

**修复**：
- 所有 `fixed<u32,N>` 字段在 world.toml 示例中写整数表示（如 `damage_multiplier = 10000` 表示 1.0）
- validate_config 中所有比较使用定点数值
- CI 中添加 TOML schema 校验，拒绝浮点值出现在 fixed 字段中
- P0-8 IDL 中为所有定点字段标注实际精度因子

---

### H3 (UNRESOLVED from R11-dsv4): Rhai state API 完整世界暴露 — 可见性边界缺口

**影响范围**: 所有安装了模组的世界；与 P0-9 能力矩阵矛盾

同 R11-dsv4 C2。P0-7 §4 的 `state.players()` / `player.drones()` / `player.rooms()` / `player.resources()` API 不经 `is_visible_to` 过滤。P0-9 §2.3 中 RuleMod 的"允许查询世界" = ❌，但 Rhai API 提供了完整状态访问。

本轮新增关注：`actions.emit_event` 产出的事件无可见性标注（DESIGN §8.7），若事件对玩家可见则构成信息泄露侧信道。

---

### H4 (NEW): 全局存储反制机制可被多账户分拆绕过

**影响范围**: 经济公平性

DESIGN §8.2 的累进存储税通过账户聚合抑制垄断，但缺少防御**多账户分拆**的机制：

```
玩家 A（主账户）: 全局存储 30%（免税）
玩家 B（小号1）:  全局存储 30%（免税）
玩家 C（小号2）:  全局存储 30%（免税）
...
```

分拆后合计 90% 存储但全部免税。小号之间通过市场交易（低价卖给主账户）或 drone 物理转运实现资源汇集。P0-3 §1.1 的 OAuth2 (GitHub/Google) 认证不防一人多账号。

**修复**：
- 多人共享同一 IP/设备指纹的账户间累进税合并计算（需权衡隐私）
- 市场交易对手方为同 IP 账户时增加审查标记
- Phase 6 Arena 模式天然免疫（固定参赛者）；World 模式需配合社区举报机制
- 至少在设计文档中标注此限制，作为"已知残留风险"

---

## Medium

### M1 (NEW): Sandbox fork-per-tick 与编译模块缓存共存 — 父进程含 JIT 编译器

**影响范围**: 沙箱隔离完整性

P0-4 §1 声明 sandbox worker "每 tick fork → 执行 → kill"。P0-4 §7 声明"模块缓存按 (module_hash, wasmtime_version) 缓存，编译一次多 tick 复用"。

若模块缓存在**父进程**中：父进程必须嵌入 Wasmtime Engine（含 Cranelift JIT）。恶意 WASM 在编译阶段（模块校验 + JIT 编译）触发编译器 bug 时，受影响的是父进程而非 sandbox worker。编译阶段在 seccomp 锁定前执行，具有更宽的系统调用面。

若模块缓存在**worker 进程**中：每 tick fork 的 worker 是新进程，无法从已 kill 的前一个 worker 继承缓存。要么每 tick 重新编译（DoS），要么缓存必须驻留在父进程。

**修复**：
- 编译阶段使用独立的、一次性 sandbox worker（`compile_worker`），编译完成后即 kill
- 编译后的 `Module` (serialized) 由父进程缓存，但不执行
- 执行阶段的 worker 仅 deserialize 已编译模块并执行（无需 JIT），seccomp 锁定在 deserialize 后
- 或：编译服务独立进程，通过 Unix socket 交付编译产物

---

### M2 (NEW): TransferToGlobal / TransferFromGlobal 命令不在 P0-2 校验矩阵中

**影响范围**: 全局存储安全

P0-8 IDL §global_storage_commands 定义了 `TransferToGlobal` 和 `TransferFromGlobal` 命令及其验证规则：

```
validator: [global_storage_enabled, has_local_resource, under_capacity, transfer_time_remaining(0)]
```

但 P0-2 Command Validation Spec 的逐指令校验矩阵（§3.1–3.11）中不包括这两个命令。P0-2 §4 的范围说明是"查询指令（只读）"，而 TransferToGlobal 是 mutating 操作。全局存储作为攻击面（资源复制、时间窗口绕过），其指令验证需求不应被遗漏。

**修复**：
- P0-2 §3 新增 §3.12 TransferToGlobal、§3.13 TransferFromGlobal，完整定义与 Move/Harvest 同级别的校验矩阵
- 包含：全局存储启用检查、资源充足、容量上限、运输冷却、amount > 0、resource 类型有效

---

### M3 (NEW): 三重命名冲突 — MCP tool / host function / pipeline query 混淆

**影响范围**: 实现正确性

以下三个不同层级的接口共享相似名称，容易导致实现混淆：

| 层级 | 名称 | 位置 | 性质 |
|------|------|------|------|
| MCP tool | `swarm_get_objects_in_range` | P0-3 §4.2 | 外部 API，经 `is_visible_to` 过滤 |
| WASM host fn | `host_get_objects_in_range` | P0-4 §3.2 | 内部 ABI，经 `is_visible_to` 过滤 |
| Pipeline query | `GetObjectsInRange` | P0-2 §4.2 | "不进指令管线，快照生成阶段处理" |

三者都执行"范围查询"但时机和调用方不同。P0-2 §4.2 说 GetObjectsInRange "在快照生成阶段（阶段一）处理"，但 MCP tool 和 WASM host fn 的调用时机不同：MCP tool 可任意时刻调用，host fn 在 COLLECT 阶段的 WASM tick() 内调用。

若实现时将 MCP tool 直接路由到 pipeline query 路径，可能绕过每 tick 调用上限（5/tick vs unlimited MCP reads）；若误将 host fn 路由到 MCP tool 路径，可能绕过 fuel 计费。

**修复**：
- 在 P0-4 / P0-3 / P0-2 交汇处添加交叉引用表，明确每个接口的调用方、时机、计费方式、过滤规则
- CI 集成测试：验证同一玩家的 MCP query、host fn query、pipeline query 返回结果一致性（可见性层面）

---

### M4 (NEW): Tick 放弃时的 COLLECT 数据有效性

**影响范围**: 回放一致性、fuel refund 准确性

P0-1 §3.4 描述了 FDB commit 失败后 tick 放弃：世界状态不变，tick_counter 不递增，CPU fuel 退还。但 COLLECT 阶段已完成的工作（WASM 执行、host fn 调用、fuel 消耗）基于即将被放弃的 Bevy World 状态。

若 tick N 放弃后重试同一 tick（"等待 1s 重试同一 tick"），COLLECT 阶段重新执行时：
- 快照基于回滚后的 Bevy World（与第一次 COLLECT 相同状态）
- 但 WASM 模块可能已在第一次执行中消耗了随机序列位置（若使用 Deterministic PRNG）
- Blake3 XOF `update_with_seek(seed, offset)` 的 offset 推进需要显式管理

P0-1 §3.4 未定义 retry 时 PRNG 序列是否重置。

**修复**：
- 明确定义：tick 放弃 → 所有 per-tick 状态重置（PRNG offset、fuel counters、command queues、visibility caches）
- tick retry 时的 snapshot 必须与首次尝试完全相同
- 或：放弃 tick 不立即 retry，跳过该 tick_number（tick_counter 递增但不记录状态）

---

## Informational

### I1: PLANNER-OUTPUT.md 过时内容仍可导致实现错误

R11-dsv4 H3 标记的 PLANNER-OUTPUT.md 矛盾点（Phase 1.6 McpPlayerExecutor stub、Phase 2.2 "11 个 MCP 游戏动作工具"、Phase 2.5 McpPlayerExecutor tick 集成）至今未修正。虽然文档顶部有更正声明，但实施者可能只看 Phase 计划而不注意顶部的更正。建议将受影响的 Phase 行直接删除或用 `~~删除线~~` 标记，而非仅顶部文字警告。

### I2: 技术选型一致性良好 — 正面发现

- Wasmtime fuel metering + epoch interruption + 独立进程 fork-per-tick：纵深防御 ✓
- Blake3 统一哈希/PRNG/MAC：审计面最小化 ✓
- FoundationDB 严格可序列化：每 tick 原子提交 ✓
- Ed25519 短期证书 + 服务端签发：吊销可控 ✓
- Deferred Command Model：杜绝 WASM 直接 mutating ✓
- Source Gate 单一入口 + 12 来源能力矩阵：不可绕过 ✓
- Seeded Shuffle：确定且公平的资源竞争 ✓
- Fuel refund anti-amplification（同 tick 不可放大、deploy-reset 作废）：防计算预算滥用 ✓
- JSON Schema 输入校验（深度/大小/类型/坐标/字符集）：全面覆盖 ✓

### I3: R11-dsv4 C1 (host fn visibility) 修正验证

P0-4 §3.2 现在为所有 host function 标注"返回结果经 `is_visible_to` 过滤"。P0-5 §3.0 新增 "Host Functions（WASM 查询）" 章节，与 Snapshot/MCP/WS/REST/Spectator 并列。两条修正形成完整闭环——这是 P0 规范迭代的正面案例。

### I4: `sequence` 字段语义未闭合

P0-2 §2 RawCommand 含 `sequence`（"每玩家每 tick 单调递增"）。R11-gpt M2 指出缺口/重复/溢出行为未定义。R12 补充：若玩家提交 `[{seq:1, cmd:A}, {seq:1, cmd:B}]`（重复 sequence），validator 是拒绝全部、保留第一条还是按某规则选择？这些选择影响 determinism——必须在 P0-2 中明确定义。

### I5: Sandbox worker 编译超时进程隔离不清晰

P0-4 §7 "编译超时 30s — 独立超时进程"。该"独立超时进程"与 §1 sandbox worker 的关系未定义。是编译阶段有独立于执行阶段的超时看门狗，还是编译在 sandbox worker 内执行但有 30s 上限？

---

## Data Flow Trace (Updated for R12)

```
COLLECT:
  Bevy World (authoritative) → visibility_filter() → Snapshot JSON → WASM tick()
  WASM tick() → host_*() calls [✅ is_visible_to filtered — RESOLVED R11-C1-dsv4]
  WASM tick() → Command[] JSON → schema validation [✅ depth/size/type checks]
  ⚠️ WASM tick() → Command[] 仍含 player_id 字段 [❌ R11-gpt C1]
  ⚠️ Command[] 中无 TransferToGlobal/FromGlobal 校验 [NEW M2]

EXECUTE:
  Command[] → seeded_shuffle() [✅ deterministic]
  Command[] → validate against Bevy World [✅ TOCTOU per-command]
  Command[] → apply() in FDB transaction [❌ R11-gpt C2: 不覆盖 Bevy/RuleMod/副作用]
  ❌ RuleMod actions.* → 直接 apply(world)，绕过 Command Validation [NEW C3]
  ❌ FDB commit unknown → 无幂等键 [R11-gpt C2]

BROADCAST:
  FDB commit → Dragonfly cache [✅ stale reads documented]
  Dragonfly → NATS → WebSocket [✅ gap detection]

Rhai mod hooks:
  state API → full world access [❌ R11-dsv4 C2: no visibility filter]
  actions.* → mini-validator → world [❌ NEW C3: bypasses Command Validation Pipeline]
  ⚠️ actions.emit_event → 无可见性标注 [NEW H3]

MCP:
  tools → is_visible_to() filter [✅]
  ⚠️ player_view=full → MCP 可超 WASM snapshot [NEW H1]
  deploy → WASM module queue → next tick atomic switch [✅]

WASM sandbox:
  ✅ host fn visibility filtering added
  ❌ tick() ABI 不安全 (return ptr without len) [R11-gpt C3]
  ❌ fork-per-tick + module cache = JIT in parent [NEW M1]
  ✅ Wasmtime config → 需真实可编译版本验证 [R11-gpt H3]
```

---

## Review Summary

| Severity | Count | Must-Fix Phase | New in R12 |
|----------|-------|----------------|------------|
| Critical | 3 | Phase 2 | C3 (1 new) |
| High | 4 | Phase 3 | H1, H2, H4 (3 new) |
| Medium | 4 | Phase 4 | M1, M2, M3, M4 (4 new) |
| Informational | 5 | — | I4, I5 (2 new) |

### R11→R12 进展

- **1 个 Critical 解决**（host fn 可见性过滤）—— 规范级修正，闭环完整
- **5 个 Critical 未变**（合并 R11-dsv4 C2 + R11-gpt C1/C2/C3 + 新增 C3 = 当前 3 Critical）
- **PLANNER-OUTPUT.md 仍未修正**——持续的实现风险
- **新问题集中在三个领域**: (1) RuleMod 权限过大绕过校验管线, (2) MCP 可见性不对称, (3) 定点数/浮点数类型矛盾破坏 Determinism Contract

### 核心建议

三项 Critical 形成连锁依赖：**C2 (tick 原子性 staging) → C3 (RuleMod 进入 ExecutionPlan) → C1 (AuthenticatedCommand 类型消除 player_id)**。建议按此顺序修正：先设计 ExecutionPlan 数据结构，再将 RuleMod actions 纳入其中，最后统一 Command 类型。
