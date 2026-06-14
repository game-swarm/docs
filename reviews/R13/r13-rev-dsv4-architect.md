# R13 — 架构评审 (rev-dsv4-architect)

> **评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + specs/p0/01-09
> **评审方向**: Architect (Primary) — ECS 调度正确性 · Tick 生命周期完整性 · FDB/Dragonfly 数据一致性 · 算法复杂度
> **R12 跟踪**: 逐项比对 R12 发现的状态变更
> **完成时间**: 2026-06-14

---

## Verdict: REQUEST_MAJOR_CHANGES

R12 判 APPROVE_WITH_RESERVATIONS，期望 spec 矛盾在 Phase 1 前澄清。本回合重新审查发现：R12 标记的 3 个 HIGH severity 问题 **无一解决**（D1/D2/D3 的 spec 文本完全未动），且新发现 3 个 HIGH 问题涉及 refund 公平性、FDB commit 三处矛盾、Rhai 确定性不变量被 wall-clock 安全网击穿。累计 6 个 HIGH severity 未闭合 issue，不宜进入 Phase 1 实现。

从 R12 到 R13 的积极变化：
- P0-4 §8 PathFind 缓存键加入 `player_visibility_fingerprint`（关闭 R12 sec C1）
- DESIGN §8.7 墙钟注释增加了「非确定性安全网，不参与 state_checksum」说明（半关闭 R12 arch A1）

但核心架构时序问题原地踏步。

---

## Strengths（承继 R12，无变化）

1. **WASM Deferred Command Model** — mutating 操作从 host function 彻底剥离。AI/人类同走 WASM 沙箱。干净。
2. **Tick 失败语义矩阵 (P0-1 §6.1)** — 8 种失败模式 × 影响/恢复/玩家影响完整定义。
3. **Blake3 单原语策略** — Hash/PRNG XOF/代码签名统一依赖。审计面减半。
4. **Seeded Shuffle** — Blake3(tick||world_seed) 每 tick 洗牌，长期公平短期不可预测。
5. **Refund 安全模型** — 同 tick 退还不可消费 + module_hash 绑定 + 连续高退还 throttle。
6. **ResourceRegistry 动态资源** — 引擎不硬编码 Energy，`IndexMap<String, u32>` 可扩展任意资源类型。
7. **全局存储三层反制** — 累进税 + 本地隐匿 + 运输时间不可为 0。

---

## Concerns

### D1 [HIGH] [R12 D1 — 未解决] — Command Application vs ECS System 执行时序歧义

DESIGN §3.2 仍写：
> 合法 → 通过 ECS system 应用变更
> 运行 tick 内 ECS systems（战斗、衰减、再生）

P0-1 §3.3 的 `.chain()` 仍列出 build_system → harvest_system → ... → spawn_system。

**核心矛盾未变**: 玩家命令是逐条立即调用对应 ECS system（inline），还是仅入队、命令循环结束后统一跑 ECS chain（deferred）？

两种模式的行为差异：

| | Inline 逐条 | Deferred 批量 |
|---|---|---|
| Move 后 Attack 的范围校验 | 基于新位置（移动已生效） | 基于旧快照位置 |
| Spawn + 同 tick 使用新 drone | 可能（spawn 在循环中执行） | 不可能（spawn 在最后） |
| 资源竞争「先到先得」 | 洗牌前列玩家实质优势更大（其命令改变的状态影响后续校验） | 洗牌仅影响同资源争用，不影响跨实体交互 |
| TOCTOU 风险 | 高——命令间状态已变 | 低——校验基于快照一致性 |

P0-2 §3.7 的 TOCTOU 描述（「如果目标在快照和执行之间移动了」）暗示 inline 模型，但 P0-2 §3.10 spawn 末尾创建的声明暗示 deferred 模型。**两份 spec 描述了两种不可共存的世界。**

**严重性升级理由**: R12 将此标记为 HIGH 但 13 轮未解决。Phase 1 实现者必须选择一个模型——无论选哪个，另一半 spec 的文本将成为 bug 来源。

**建议**: 写一份独立的 `specs/p0/execute-internal-sequence.md`（50 行即可），明确：
1. EXECUTE Phase 2a: 命令循环——逐条校验 + 逐条应用（inline）。校验基于当前 Bevy World 状态（非快照）。Move/Harvest/Build/Transfer/Attack/Heal/Recycle 在循环中执行。
2. EXECUTE Phase 2b: ECS Systems 统一运行——regeneration/combat/decay/death/spawn `.chain()`。这些 system 不处理玩家命令，处理 tick 级被动效果。
3. Spawn 命令在 Phase 2a 中只校验不入队，在 Phase 2b spawn_system 中统一创建。

---

### D2 [HIGH] [R12 D2 — 未解决] — Spawn 执行时机与 death_system/room cap 竞态

P0-2 §3.10 仍写：
> Drone 在 tick 末尾创建（death_system 之后，spawn 槽位已释放）

P0-1 §3.3 的 `.chain()` 仍把 spawn_system 放在 death_system 之后。

**问题仍在**: 如果 death 在同一 tick 的 death_system 中运行，而 spawn 校验中的 `RoomDroneCapReached` 检查发生在命令循环中（death 尚未执行），则本 tick 死亡的 drone 的槽位尚未释放，校验会**错误拒绝**合法的 spawn。

**场景复现**:
```
Tick N 开始: room drone count = 50 (cap = 50)
命令循环: Player 提交 Spawn 命令 → 校验 RoomDroneCapReached → 50 >= 50 → 拒绝
death_system 运行: 5 个 drone 死亡 → room drone count = 45
spawn_system 运行: 无 spawn 命令（已在命令循环被拒绝）
结果: 玩家被错误拒绝，房间实际有 5 个空余槽位
```

**严重性升级理由**: R12 已指出此问题但 spec 未更新。这是实现时一定会踩到的 bug——任何 spawn + 同 tick death 场景都会触发。

**建议**: 将 death_system 拆分为两个阶段：
- `death_mark_system` — 命令循环前运行，标记待死亡 entity，立即释放 room cap 槽位
- `death_cleanup_system` — 命令循环后运行，实际 despawn entity
- Spawn 校验在命令循环中检查的是「当前 room count - marked_for_death」而非原始 room count

---

### D3 [HIGH] [R12 D3 — 未解决] — Code Update Window: 部署接受 vs 模块激活时序缺口

P0-1 §2.4 仍写：
> Tick N+1: 引擎自动切换到 v2

P0-7 §3 的 `code_update_window_system` 仍无 Gateway 层交互。

**场景仍在**: 窗口关闭期间，Gateway 接受 `swarm_deploy`（10 次/小时限制内），Engine 在加载时被 `code_update_window_system` 阻塞 → 模块进入 limbo。玩家无反馈。多次重试消耗 `MCP_Deploy` 配额。

**严重性升级理由**: 影响 MCP 部署体验——AI agent 在窗口关闭时调用 `swarm_deploy` 会得到成功响应（Gateway 接受了），但实际上模块要等窗口打开才激活。agent 会在下一 tick 观察到「代码未生效」→ 重新部署 → 消耗配额 → 进入 limbo 队列堆积。

**建议**: 在 P0-3 `swarm_deploy` 响应 schema 中增加：
```json
{
  "status": "accepted_deferred" | "active",
  "activates_at_tick": 1000,
  "reason": "code_update_window_closed"
}
```
或者：在 Gateway/Source Gate 层增加窗口感知，窗口关闭时直接拒绝部署。

---

### D4 [HIGH] [新增] — Rhai 墙钟终止与 Determinism Contract 不可调和

DESIGN §8.7 仍保留：
> 墙钟执行时间: 100ms/tick | 强制终止，模组标记为 "degraded"。非确定性安全网——不参与 state_checksum

注释称「不参与 state_checksum」——但这在技术上不可行：

```rust
// tick_end.rhai — 每 tick 结束时执行
fn on_tick_end(state, events, config, actions) {
    for player in state.players() {
        let total_cost = drones * config.drone_cost + room_penalty;
        actions.deduct_resource(player.id, "Energy", total_cost);  // ← 修改世界状态
        actions.emit_event("upkeep_charged", #{...});
    }
}
```

如果墙钟在遍历到第 47 个玩家时超时终止：
- 前 46 个玩家的 `deduct_resource` 已执行 → 世界状态已变更
- 后 N-46 个玩家未被处理 → 世界状态不一致
- 「不参与 state_checksum」意味着 checksum 不算这些变更——但变更**已经写入 ECS components**

**这是比 R12 A1 更严重的发现**: 墙钟终止不仅破坏确定性（已知），而且「不参与 state_checksum」不能隔离其对世界状态的副作用。`deduct_resource` 直接修改 `PlayerResources` component，无法被 checksum 过滤。

**建议**: 
- 方案 A（激进）: 删除墙钟预算，仅保留 AST 节点数 + actions 调用次数作为终止条件。这两个是确定量。
- 方案 B（保守）: Rhai 钩子以事务方式执行——所有 `actions` 先缓存在内存 buffer，钩子完全执行完毕后统一 apply。墙钟超时 → buffer 丢弃，世界状态不变。
- 方案 B 是唯一在保留墙钟预算下保证确定性的方案。

---

### D5 [HIGH] [新增] — Refund module_hash 绑定对合法迭代的惩罚

P0-2 §7.2:
> refund credit 与产生它的 WASM 模块绑定。若玩家在 tick N+1 重新部署了不同模块（module_hash 变更），tick N 的 refund credit 作废。

**场景**:
1. Tick N: Player 用 module_v1 执行 → SourceEmpty 退还 50% fuel → credit 绑定到 v1
2. Tick N 与 N+1 之间: Player 部署 v2（正常迭代）
3. Tick N+1: module_hash 变更 → refund credit 作废

**结果**: 合法迭代代码的玩家**必然**丢失上一 tick 的资源竞争退款。这不是 edge case——任何同时进行「代码迭代 + 资源竞争」的玩家都会触发。策略迭代越频繁（这正是游戏鼓励的），丢失的 refund 越多。

**设计意图**（防跨模块预算转移）是合理的，但实现过激——它惩罚了合法行为。

**建议**: 
- 将 credit 绑定到 `player_id` 而非 `module_hash`
- 跨模块转移风险通过以下替代方案缓解：限制 refund credit 上限（已有的 `MAX_FUEL × 10%`）+ 延续 credit 仅在一次部署内有效（玩家部署后 credit 清零）
- 或者：credit 绑定到 `player_id` 但在部署事件时清零（而非绑定 module_hash）

---

### D6 [HIGH] [新增] — FDB Commit 在 EXECUTE vs BROADCAST 三处文本矛盾

DESIGN §3.2 Phase Three (BROADCAST) 写:
> FDB 原子提交（全或无）

P0-1 §3.4 写:
> 整个阶段二包裹在 FoundationDB 事务中

P0-1 §1 状态机图:
> 阶段三：广播 → FDB 原子提交 → Dragonfly 缓存更新 → NATS 发布

**三份文档描述了 FDB commit 的三种不同时序**。这在实现时意味着：
- 如果按 P0-1 §3.4（EXECUTE 中 commit）→ BROADCAST 失败不回滚 tick ✓
- 如果按状态机图（BROADCAST 中 commit）→ BROADCAST 失败 = tick 未持久化 → 需要重试机制
- 如果按 DESIGN §3.2 → 同状态机图

**P0-1 §3.4 是正确的设计**（tick 必须先持久化再广播），但状态机图和 DESIGN 指向相反的语义。

**建议**: 以 P0-1 §3.4 为准，更新状态机图和 DESIGN §3.2。同时确保 P0-1 §4.2 的「Read committed tick result from FDB」在 EXECUTE commit 后语义正确。

---

### D7 [MEDIUM] [R12 D5 — 部分解决] — MCP 查询在 EXECUTE 中间态的一致性

R12 建议「MCP 查询在 COLLECT/EXECUTE 期间返回上一 tick 已提交状态」。P0-1 仍未定义阶段门控。

但 P0-5 §5 的 visibility cache 设计（每 tick 一次，缓存在 COLLECT 前计算）暗示快照数据来自 pre-EXECUTE Bevy World。这与「MCP 查询返回上一 tick FDB 状态」的语义不同——pre-EXECUTE Bevy World 已经包含了上一 tick 的所有变更。

**实际一致性窗口**: 如果 MCP `swarm_get_snapshot` 查询在 COLLECT 和 EXECUTE 之间到达，返回的是「上一 tick 的完整结果（已提交到 FDB）」，这是正确的。如果它在 COLLECT 期间到达（Bevy World 正在被读取以构建快照），返回的是半构建状态——这是 bug。

**建议**: P0-1 状态机增加阶段门控语义——所有外部查询（MCP/REST）在 COLLECT + EXECUTE 期间返回 tick N-1 的 FDB 已提交状态（从 Dragonfly/FDB 读），仅在 BROADCAST 完成后切换到 tick N 状态。

---

### D8 [MEDIUM] [R12 D6 — 未解决] — Rhai Actions mini-validator 内容未定义

P0-7 §5 仍写「经 mini-validator」，但 mini-validator 的检查项列表仍为空。

当前 Rhai API 可以：
- `deduct_resource(player_id, resource, amount)` — 无上限校验
- `damage_entity(entity_id, amount, reason)` — 无上限校验
- `set_entity_flag(entity_id, flag, value)` — 无白名单校验

**在 P0-9 §2.3 中 RuleMod 标记为「允许写入世界: ⚠️」——但没说什么被限制、被什么限制。**

**建议**: P0-7 §5 增加 mini-validator 检查项表：

| actions 函数 | mini-validator 检查 |
|---|---|
| `deduct_resource` | player 存在、resource 类型存在、amount ≤ 当前持有量（不借债）、amount ≤ MAX_DEDUCT_PER_TICK (10000) |
| `award_resource` | player 存在、resource 类型存在、amount ≤ MAX_AWARD_PER_TICK (10000) |
| `damage_entity` | entity 存在、amount ≤ MAX_DAMAGE_PER_ACTION (500)、entity 非无敌标记 |
| `set_entity_flag` | flag 在 `ALLOWED_FLAGS` 白名单中（slow/empowered/shielded 等） |
| `emit_event` | event_type 长度 ≤ 64、data 体积 ≤ 4KB |

---

### D9 [MEDIUM] [新增] — P0-9 Deploy 来源与 MCP_Deploy 限流不一致

P0-9 §2.2:
> `Deploy` (非 MCP 入口): rate_limit = 1/tick

P0-3 §5.1:
> `deploy` 调用: 10/小时

1/tick = 28,800/天 ≈ 1,200/小时。MCP_Deploy = 10/小时。

**人类玩家通过 CLI/Web UI 部署的速率限制是 AI 玩家的 120 倍**。这不对称未在任何设计文档中说明理由。如果是有意设计（人类部署是低频操作，不需要限流），应在 P0-9 中注明。如果是疏忽，应统一限流值。

---

### D10 [MEDIUM] [新增] — P0-4 fork-per-tick 生命周期与编译缓存的不可能三角

P0-4 §1:
> 生命周期: 每 tick fork → 执行 → kill

P0-4 §7:
> 模块缓存: 按 (module_hash, wasmtime_version) 缓存...编译一次，多 tick 复用

P0-4 §4.3:
> 与引擎通过 Unix domain socket 通信

**三者不能同时成立**:
- fork-per-tick 的子进程在 tick 结束后被 kill → compiled module 对象随之销毁
- 编译缓存必须在**持久进程**中持有（Engine 父进程或独立 compile service）
- §7 的「每次 tick 执行前校验 player auth token」也需要持久状态

**实际可行的架构**: Engine 父进程持有 compiled module cache（`HashMap<ModuleHash, Module>`）。Per-tick fork 的子进程通过 IPC（shared memory handle 或 gRPC over Unix socket）接收 compiled module 引用。子进程不持有缓存，不维持连接——每次 fork 后重新建立 gRPC channel（Unix socket 重建开销 ~100μs，可接受）。

**建议**: P0-4 §1 的架构图将「模块缓存」从 sandbox worker 框移到 Engine 进程框内。

---

### D11 [LOW] [R12 D10 — 未解决] — Snapshot 序列化策略缺少内存格式约定

P0-1 §2.3 仍写「按房间序列化一次，再按玩家过滤」，仍无内部格式说明。

**建议不变**: 明确快照在内存中为 `Vec<EntitySnapshot>` 结构体（非 JSON），过滤在结构体层面做，JSON 序列化在交付给 WASM 的前一步执行。

---

### D12 [LOW] [新发现] — P0-5 visibility cache 键缺少 player_view 维度

P0-5 §5:
> 缓存键: (tick, player_id)

但 P0-5 §3.5 定义了三种 player_view 模式（drone/full/allied），同一玩家在不同模式下产生不同的可见实体集。如果 world.toml 在运行时修改 `player_view`（当前 spec 未禁止），缓存返回过期结果。

**建议**: 缓存键改为 `(tick, player_id, player_view)`。

---

## R12 问题跟踪表

| R12 ID | Severity | 描述 | R13 状态 | 备注 |
|--------|----------|------|---------|------|
| D1 | HIGH | Command vs ECS 时序歧义 | **未解决** → R13 D1 | spec 文本完全未动 |
| D2 | HIGH | Spawn/death 执行顺序 | **未解决** → R13 D2 | spec 文本完全未动 |
| D3 | HIGH | Code update window 缺口 | **未解决** → R13 D3 | spec 文本完全未动 |
| D4 | MEDIUM | Dragonfly stale read | **未解决** | 无版本校验机制 |
| D5 | MEDIUM | MCP 中间态一致性 | **部分解决** | visibility cache 提供部分隔离，阶段门控仍未定义 |
| D6 | MEDIUM | Rhai validator undefined | **未解决** → R13 D8 | mini-validator 仍为空 |
| D7 | MEDIUM | Wasmtime 版本回放 | **未解决** | 降级 tick 回放策略未更新 |
| D8 | MEDIUM | Bevy snapshot 开销 | **未解决** | 无评估 |
| D9 | LOW | Body part 扩展缺 damage type | **未解决** | IDL 无扩展点 |
| D10 | LOW | Snapshot 序列化策略 | **未解决** → R13 D11 | 无内存格式约定 |
| C1 | — | FDB commit EXECUTE vs BROADCAST | **未解决** → R13 D6 | 三处文本矛盾 |
| C2 | — | DESIGN vs P0-1 FDB commit | **未解决** → R13 D6 | 同上 |
| C3 | — | code_update_window_system 不在基础 chain | **未解决** | P0-1 未列可选 system |
| C4 | — | harvest resource 参数可选 | **未解决** | 默认行为未定义 |
| C5 | — | Simulate 限流 World/Arena | **未解决** | P0-9 未区分 |
| C6 | — | PRNG host function 缺失 | **未解决** | 仍无 `host_get_random` |
| A1 | HIGH | Rhai 墙钟破坏确定性 | **半解决** → R13 D4 | 注释改进但不可行 |
| A2 | HIGH | ResourceRegistry HashMap | **部分解决** | DESIGN §8.4 改为 IndexMap，但 P0-8 IDL 仍用 Map |

**汇总**: 20 个 R12 发现，0 个完全关闭，3 个部分改进，17 个未解决。新增 6 个发现（D4/D5/D6/D9/D10/D12）。

---

## Consistency Gaps（新增/延续）

### CG1 [延续 R12 C5] — P0-9 vs P0-3 Simulate 限流

P0-9 §2.1: `Simulate` = 5/tick
P0-3 §4.4: World = 5/tick, Arena = 3/tick

P0-9 不区分模式。应以 P0-3 为权威源。

### CG2 [延续 R12 C4] — Harvest resource 参数可选但无默认语义

P0-8 IDL: `harvest.params.resource: ResourceName?`
P0-2 §3.3: Harvest 校验无 resource 字段

如果 resource 未指定，是否采集 source 产出的第一种资源？所有资源均分？行为未定义。

### CG3 [新增] — P0-8 IDL BodyPart enum 固定 vs DESIGN §8.2 body part 扩展

P0-8 IDL `BodyPart` enum: `[Move, Work, Carry, Attack, RangedAttack, Heal, Claim, Tough]`
DESIGN §8.2: 允许 `[[body_part_types]]` 定义 Leech/Scramble/Fabricate 等

IDL 需要支持 `Custom(String)` variant 或运行时扩展机制。

### CG4 [新增] — P0-4 §8 PathFind 缓存键更新未同步到 P0-2 §4.3

P0-4 §8 已正确更新缓存键含 `player_visibility_fingerprint`。但 P0-2 §4.3 仍写旧缓存键 `(from, to, 地形hash)`。两份 spec 描述同一缓存但键不同。

### CG5 [新增] — DESIGN §3.2 Tick Lifecycle 与 P0-1 §1 状态机图结构差异

DESIGN 的 Phase Three (BROADCAST) 包含 4 步：增量计算 → Dragonfly 更新 → FDB 原子提交 → tick_counter 推进
P0-1 §1 状态机 BROADCAST 包含：增量计算 → FDB 原子提交 → Dragonfly 更新 → NATS 发布 → tick_counter 推进

**执行顺序不同**: DESIGN 先 Dragonfly 后 FDB，P0-1 先 FDB 后 Dragonfly。P0-1 的顺序正确（先持久化权威源，再更新缓存）。

---

## Algorithmic Risks

### R1 [延续 R12 R5] — 每 tick 全量 state 存储

P0-1 §6.3.1 要求每 tick 写入 `/tick/{N}/state`（完整世界状态）。DESIGN §3.2 暗示「每隔 N tick 记录完整世界快照」。

3s tick × 28,800 tick/天。若每 tick state = 100MB → 2.88TB/天。未在 ROADMAP 或运维计划中处理。

**建议**: 明确 state 快照策略——每 tick commands+rejections+metrics（轻量），每 K tick（如 100）full state snapshot。回放由最近 snapshot + commands 增量重建。

### R2 [延续 R12 R2] — Snapshot JSON 序列化吞吐

500 玩家 × ~500KB JSON snapshot = 250MB/tick 序列化输出。按房间序列化一次策略将此项降为 O(R) 次序列化（~50 房间 × 500KB = 25MB/tick）。可接受但需在 Phase 1 benchmark 验证。

### R3 [延续 R12 R3] — Bevy ECS .chain() 串行瓶颈

`.chain()` 在 250K 实体下可能超 500ms EXECUTE 预算。Phase 7 计划解决。当前风险可接受但 Phase 1 应建立 per-system 耗时 baseline。

### R4 [新增] — seeded_shuffle 中 Blake3 XOF for 10K 玩家

Fisher-Yates 需要 N 次 XOF read。10K 玩家 → 80KB XOF 输出。Blake3 ~6 GB/s → ~13μs。可忽略。

---

## 评审总结

| 类别 | 数量 | 说明 |
|------|------|------|
| HIGH | 6 | D1(时序歧义) D2(spawn时序) D3(code window) D4(Rhai墙钟) D5(refund公平性) D6(FDB commit三处矛盾) |
| MEDIUM | 4 | D7(MCP中间态) D8(Rhai validator) D9(Deploy限流不对称) D10(fork vs cache) |
| LOW | 2 | D11(snapshot策略) D12(visibility cache键) |
| Consistency Gaps | 5 | CG1-CG5 |
| Algorithmic Risks | 4 | R1-R4 |
| R12 关闭率 | 0/20 | 3 项部分改进，17 项未解决 |

**核心判断**: R12 → R13 的增量改善局限在 PathFind 缓存键和 Rhai 墙钟注释两个点。3 个 HIGH severity 架构歧义原封不动。新发现 D4（Rhai 墙钟的副作用隔离不可行）和 D6（FDB commit 三处矛盾）各自足以独立阻断 Phase 1。

**方向判断**: 架构基础仍然扎实——问题在「spec 不够细」而非「架构错误」。但 R12→R13 零进展的事实表明需要更强力的修正机制（如单一 spec 优先原则：P0-1 为 tick 协议权威源，DESIGN 为愿景文档非规范源）。

**建议下一步**: 
1. 写 `specs/p0/execute-internal-sequence.md` 解决 D1+D2
2. DESIGN §3.2 同步到 P0-1 §3.4（FDB commit in EXECUTE）解决 D6+CG1+CG5
3. P0-7 §5 填写 mini-validator 表解决 D8
4. P0-3 `swarm_deploy` 响应增加窗口状态字段解决 D3
5. 决定 Rhai 方案 A/B 解决 D4

