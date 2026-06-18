# R15 架构评审 — Architect (DeepSeek V4 Pro)

> Phase 1 Clean-Slate 独立评审。仅读取方向相关子集：design/README.md, design/engine.md, design/tech-choices.md, specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md。

## Verdict: REQUEST_MAJOR_CHANGES

ECS 系统链在三个文档中存在不可调和的不一致——不同文档描述的 `regeneration_system` 位置互斥，`status_advance_system` 和 `aging_system` 在权威链中缺失，且 RoomCap 中间态访问约束被实际 chain 布局违反。这些问题在实现前必须统一为单一权威 ECS 调度表。

---

## 发现的问题

### D1 [Critical] ECS 链三文档不一致 — regeneration/combat 位置互斥

三个文档对 Phase 2b ECS 系统链给出了**互不兼容**的描述：

| 文档 | regeneration 位置 | combat 位置 | 并行模型 |
|------|------------------|-------------|---------|
| engine.md §3.2 Phase 2b | combat **之后**，平行于主线 | regeneration **之前** | regeneration∥decay 与主线并行 |
| 01-tick-protocol.md §3.4 | spawn **之后**，controller_repair **之前**，链内串行 | regeneration **之后**（第13位） | 链内串行 `.chain()` |
| 02-cmd-validation.md §3.19 | status_advance **之后**，decay 并行 | status_advance **之前** | regeneration∥decay 并行 |

**影响面**：regeneration 在 combat 前/后决定了"本 tick 战斗消耗的资源是否在同 tick 再生"——这是 gameplay 语义级差异。若 regeneration 在 combat 前，刚再生的资源立即可用于同 tick 后续 Transfer/Withdraw；若在 combat 后，则需等到下一 tick。501 个活跃玩家 × 10000+ drone 规模下，此差异会导致完全不同的资源经济模型。

**修复方向**：以 engine.md §3.2 Phase 2b 的"combat → regeneration∥decay → death_cleanup"为主线，将 01-tick-protocol.md §3.4 的 `.chain()` 重新排列，并将 regeneration/decay 移出 chain 改为 `.before(death_cleanup)` 并行调度。

---

### D2 [Critical] status_advance_system 和 aging_system 在权威链中缺失

- engine.md §3.2 Phase 2b 分类表明确列出 `status_advance` 和 `aging` 为主线 `.chain()` 成员
- 01-tick-protocol.md §9.6 声明：`death_mark → spawn → spawning_grace → combat → status_advance → aging → death_cleanup`
- **但** 01-tick-protocol.md §3.4 的 20 系统 `.chain()` 中既无 `status_advance_system` 也无 `aging_system`

这两个系统负责：
- `status_advance_system`：所有特殊攻击状态推进（Hack stage 递增、Overload fuel 恢复、Debilitate 计数递减、Fortify 护盾递减）
- `aging_system`：drone age 递增 → 触发 lifespan 死亡

缺失这两个系统意味着：特殊攻击状态永不过期（Hack 永不夺取、Overload 永不恢复、Fortify 永久护盾）、drone 永生不死——这是整个游戏经济的核心循环断裂。

---

### D3 [High] RoomCap 中间态约束被 pvp_block_system 实际位置违反

engine.md §3.2 明确约束：
> 在 `death_mark_system` 与 `spawn_system` 之间的任何 ECS system 不得读取 RoomCap 做准入决策——此时槽位已释放但尚未被新 drone 消费，RoomCap 值处于中间态。

但 01-tick-protocol.md §3.4 的 chain 中 `pvp_block_system` 精确地处于 `death_mark_system`（第2位）和 `spawn_system`（第4位）**之间**（第3位）。

如果 `pvp_block_system` 读取 RoomCap——在 PvP 封锁逻辑中，很可能需要检查房间是否满员来决定是否允许新玩家进入——则违反了文档自身的安全约束。

**修复方向**：要么将 `pvp_block_system` 移到 spawn_system 之后，要么在 manifest 中声明其对 RoomCap 的读写关系并证明其不使用 RoomCap 做准入决策。

---

### D4 [High] Component 读写矩阵仅覆盖 6/20 系统

01-tick-protocol.md §3.4 的读写矩阵：

| System | Position | HitPoints | Fatigue | Energy/Carry | Cooldown | RoomCap | DeathMark | Owner |
|--------|----------|-----------|---------|--------------|----------|---------|-----------|-------|
| death_mark | R | - | - | - | - | W | W | R |
| spawn | W | W | - | W | W | R | - | W |
| combat | R | W | - | - | - | - | - | R |
| regeneration | - | - | - | W | - | - | - | - |
| decay | - | - | W | - | W | - | - | - |
| death_cleanup | - | - | - | - | - | - | W | - |

仅覆盖 6 个系统，实际 chain 含 19 个系统（不含 conditionally scheduled 系统）。以下系统未声明数据访问：

- `controller_system`：写入 Controller progress/level/owner → 可能读写 Energy
- `controller_repair_system`：读取 drone age，写入 drone age → 可能冲突
- `depot_repair_system`：写入 Structure hits → 与 combat_system 的 HitPoints 冲突？
- `room_state_system`：读写 Room 状态 → 可能读写 RoomCap？
- `global_storage_system`：读写全局资源池
- `seed_rotation_system`：写入 WorldSeed
- `cargo_in_transit_system`：读写 Carry 组件
- `memory_upkeep_system` / `drone_env_var_system`：访问未知组件

每个缺失系统的读写模式需要在矩阵中声明，并行安全性才能被证明。

---

### D5 [Medium] 20 系统链仅有 19 个系统

01-tick-protocol.md §3.4 标题为 "ECS 系统执行顺序（Bevy — 20 系统链）"，但实际 `.chain()` 闭包内仅 19 个系统。加上 `status_advance_system` 和 `aging_system` 后变为 21 个——标题数字需要修正。

---

### D6 [Medium] Recycle 退还公式与定点整数策略冲突

02-cmd-validation.md §3.18：
```
refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))
```

engine.md §3.4.8 明确：
> 所有资源/年龄/伤害/进度使用 u64 或 i64 定点整数。舍入：一律 floor。

整数除法 `remaining_lifespan / total_lifespan` 对任何 `remaining < total` 的 drone 返回 0，导致 `0.5 × 0 = 0`，最终 clamped 到 0.1 —— 绕过了"剩余 lifespan 越多退还越高"的渐进设计意图，所有非满寿命 drone 统一退化到 10% 下限。

**修复**：使用 basis points (×10000) 定点运算，如 `refund_bps = max(1000, 5000 × remaining_lifespan / total_lifespan)`。

---

### D7 [Medium] spawn body_cost refund 在 Refund Strategy 表中缺失

02-cmd-validation §7.1（资源争用 Refund 策略表）仅覆盖 fuel refund，不包含 body_cost refund。但 §3.8 描述了 spawn body_cost 的复杂退还逻辑（回到 spawn.energy 优先 → 全局存储）。退款机制分散在 Spawn 章节而非统一退款表中，容易在实现时遗漏 spawn 失败退款路径。

---

### D8 [Low] FDB 事务大小未验证：500 玩家 × 500 命令 = 250,000 命令/事务

01-tick-protocol §9.4 要求 FDB 事务 < 10MB。但：
- `MAX_COMMANDS_PER_PLAYER = 500`
- 按 1000 活跃玩家计 → 500,000 条命令/tick
- 即使每条 command trace 压缩到 200 bytes（含 hash + truncation），仍为 100MB

要么 `MAX_COMMANDS_PER_PLAYER` 需要下调，要么 Trace 写入需要与状态提交分离（不在同一事务内）。当前 10MB 约束与每玩家 500 命令上限在满负载下不可兼得。

---

### D9 [Low] Seed rotation 前向保密窗口仅 ~8.3 小时

01-tick-protocol §3.1：10000 tick × 3s = 30000s ≈ 8.3 小时。一名运维人员在值班期间若 world_seed 泄露，攻击者可预测该班次剩余所有 tick 的玩家排序和 RNG 输出。文档将此定性为"已接受的风险"是合理的，但 8.3 小时窗口对竞技公平性而言偏长。建议在 risk analysis 中注明可配置更短的 rotation interval（如 1000 tick = 50 分钟）。

---

### D10 [Low] COLLECT 超时玩家在 FDB 重试中无二次机会

01-tick-protocol §8.4：FDB commit 失败 → 重试时复用 COLLECT 缓存。若某玩家在首次 COLLECT 中超时（0 指令、不退 fuel），缓存的结果就是 0 指令。FDB 重试时该玩家不会获得重新执行的机会。这本身是正确的——防止重试导致的不确定性——但"超时 + FDB 冲突"叠加场景下该玩家承受双重惩罚（fuel 全损 + 无指令 + 无重试机会），应该在失败语义文档中标注。

---

## 亮点

1. **快照架构**：两阶段快照（单次构建 × 玩家过滤）将复杂度从 O(P×E) 降至 O(E + P×visible)，是教科书级优化。快照在 COLLECT 开始时一次性构建并与 WASM/MCP 共享，消除了 per-player 序列化开销。

2. **CommandIntent 不可信输入模型**：WASM 仅能提供 `(sequence, action)`，所有身份/时序/来源由服务端注入。禁止字段检测（player_id/tick/auth 出现在 CommandIntent → 整批拒绝）是深度防御的正确设计。

3. **Blake3 单原语策略**：哈希 + PRNG(XOF) 统一为一个依赖，审计面减半，`update_with_seek` 的 seed+offset 模式天然适配 per-entity per-tick 确定性随机流。

4. **FDB 事务 + Bevy 快照恢复**：Phase 2a 前的 `world.snapshot()` + commit 失败后的 `world.restore(snapshot)` 是正确的事务语义——FDB 回滚不自动恢复 Bevy 内存状态，显式快照恢复避免了内存/FDB 状态分叉。

5. **Phase 2a/2b 分类哲学清晰**：Inline（玩家命令，先到先得竞争有意义）vs Deferred（被动系统，响应 2a 状态变化）的边界明确，Move-as-Main-Action 的设计理由（确定性优先、单 action slot 消除 Move+Attack 二义性）有说服力。

6. **WASM 沙箱深度**：seccomp + cgroup v2 + 命名空间隔离 + 仅暴露只读 host function + StartSection 显式拒绝，形成了从编译期到运行时的多层防护。

7. **TOCTOU 保护合同**：Spawn pending 不可见、Hack 状态下的所有权语义、同 tick 不跨 tick 指令携带——覆盖了 inline 执行模型的主要攻击面。

8. **Overload 抗永久锁死证明**：数学证明（全局冷却 + 恢复速率 + 下限）确保不存在多攻击者协同永久锁死目标 fuel budget 的攻击向量。

---

## CrossCheck — 需要跨方向检查

- **CX1**: `regeneration_system` 在 combat 前还是 combat 后？三种文档给出三种答案。 → 建议 Engine 评审员确定单一权威 ECS 调度表，以 engine.md §3.2 Phase 2b 的 "combat → regeneration∥decay" 为基准对齐所有文档。

- **CX2**: `pvp_block_system` 是否读取 RoomCap？它处于 death_mark 与 spawn 之间，违反了自己文档的安全约束。 → 建议 Security 评审员审计 pvp_block_system 的 RoomCap 访问模式，若读取则重新排位。

- **CX3**: `status_advance_system` 和 `aging_system` 的完整语义需要定义。特殊攻击的状态转换（Hack 5-stage 夺取、Overload fuel 恢复曲线、Fortify 递减）和 drone lifespan 老化逻辑分散在多个文档。 → 建议 Gameplay 评审员确认这两个系统的完整行为规范。

- **CX4**: `controller_repair_system` 降低 drone age 的硬上限 `global_cap = floor(active_drones × 0.5)` 是否与 `aging_system` 的 age 递增构成闭环？在 aging_system 缺失的现状下，controller repair 的经济模型无法验证。 → 建议 Gameplay 评审员建立 age/lifespan/repair 的完整经济闭环方程。

- **CX5**: Dragonfly 缓存在 BROADCAST 阶段更新，但 stale-read 窗口（FDB commit 到 Dragonfly update 之间的延迟）未在 SLO 中定义。 → 建议 Infrastructure 评审员定义 Dragonfly 写入延迟的 p99 目标和 cache-miss 降级路径。

- **CX6**: FDB 事务中 TickTrace 的 Command[] 序列化大小在 1000 玩家满负载下是否超过 10MB？ → 建议 Infrastructure 评审员验证事务大小预算。

- **CX7**: `Recycle` 退还公式的整数运算精度影响 `refund_pct` 的渐进性——当前整数除法将所有 `remaining < total` 的 drone 退化为 10% 下限。 → 建议 Gameplay 评审员确认这是否为设计意图，或修正为 basis points 计算。

- **CX8**: Rhai RuleMod 与 ECS 链的交互点——`rhai_rule_module_tick_start_system` 和 `rhai_rule_module_tick_end_system` 包装了整个 chain。若 Rhai 模组在此区间修改了任何 Component（通过注册的 hook），其读写模式未在矩阵中声明。→ 建议 Security 评审员建立 Rhai 模组的 Component 访问白名单。
