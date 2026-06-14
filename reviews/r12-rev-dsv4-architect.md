# R12 — 架构评审 (rev-dsv4-architect)

> **评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + specs/p0/ (全部 9 份)
> **评审方向**: Architect (Primary)
> **评审焦点**: ECS 调度正确性 · Tick 生命周期完整性 · FDB/Dragonfly 数据一致性 · 算法复杂度
> **完成时间**: 2026-06-14

---

## Verdict: APPROVE_WITH_RESERVATIONS

整体架构质量很高。Tick 协议的三阶段模型（COLLECT → EXECUTE → BROADCAST）设计合理，WASM deferred command model 消除了 MCP 作为游戏控制器的安全隐患，FDB 严格可序列化事务 + Bevy ECS 确定性链的组合为回放提供了坚实保障。Blake3 单原语策略（Hash/PRNG/代码签名）在审计面和依赖简化上都是优秀选择。

发现 3 个 HIGH severity 问题需要 Phase 1 实现前澄清/修正，5 个 MEDIUM 问题涉及 spec 间矛盾或边缘情况，2 个 LOW 问题为 spec 完善建议。

---

## Strengths

1. **WASM Deferred Command Model (P0-4 §3, P0-8)** — 将 mutating 操作从 host function 中彻底剥离，所有状态变更通过 `tick() → JSON` 延迟模型提交。这完全消除了 MCP 作为游戏控制器的诱惑，AI 玩家和人类玩家走完全相同的 WASM 沙箱路径。设计干净。

2. **Tick 失败语义完整矩阵 (P0-1 §6.1)** — 覆盖了 WASM timeout/crash/invalid output、FDB commit fail、Dragonfly cache miss/stale、NATS publish fail、Broadcast partial、TickTrace write fail 共 8 种失败模式。每种都定义了影响范围、恢复策略、玩家影响。这是少见的高质量失败设计。

3. **Blake3 单原语策略 (tech-choices §8)** — Hash/PRNG XOF/代码签名统一为一个依赖，消除 ChaCha 依赖，纯软件 ~6 GB/s 无平台退化。`update_with_seek(seed, offset)` 一行代码替代整个 keystream 管理。审计面减半，与 Determinism Contract 完美契合。

4. **Seeded Shuffle 公平排序 (P0-1 §3.1)** — 每 tick 用 Blake3(tick_number || world_seed) 洗牌玩家顺序，长期期望均等，短期不可预测。解决了「固定排序被利用」的公平性问题。

5. **Refund 安全模型 (P0-2 §7)** — 三层防护：退还不进同 tick（防计算放大）、module_hash 绑定（防跨模块转移）、连续高退还率 throttle。Anti-Amplification 设计周全。

6. **ResourceRegistry 动态资源系统 (DESIGN §8, P0-7)** — 核心引擎不硬编码 Energy，操作 `HashMap<ResourceName, Amount>`。世界可定义 Crystal+Gas（星际争霸风格）、Food+Wood+Stone+Gold（帝国时代风格）、CPU+Memory+Bandwidth（赛博朋克）。扩展性极好。

7. **全局存储反制机制 (DESIGN §8.4)** — 累进存储税 + 本地隐匿性 + 运输时间不可为 0，三者共同防止富有玩家垄断经济。经济学设计有深度。

---

## Concerns

### D1 [HIGH] — Command Application vs ECS System 执行时序歧义

**位置**: P0-1 §3.2 vs P0-1 §3.3

P0-1 §3.2 描述 EXECUTE 阶段：
> 对每条指令...合法 → 通过 ECS system 应用变更
> 运行 tick 内 ECS systems（战斗、衰减、再生）

但 P0-1 §3.3 的 ECS `.chain()` 包含了 `build_system`、`harvest_system`、`movement_system`：
```
build_system → harvest_system → regeneration_system → movement_system → 
combat_system → decay_system → death_system → spawn_system
```

**矛盾点**: 如果 player commands 在命令循环中「通过 ECS system 应用」，那 build_system/harvest_system/movement_system 是在命令循环中逐条调用，还是在命令循环结束后统一运行？两种模式有根本性差异：

| 模式 | 行为 | 风险 |
|------|------|------|
| **逐条应用** (inline) | 每条命令立即调用对应 ECS system | Move 后目标实体位置改变，影响后续 Attack 的范围校验。越早的玩家优势越大（即使有种子洗牌） |
| **批量应用** (deferred) | 命令循环只做校验 + 入队，循环结束后统一运行 ECS chain | Spawn 命令在循环末尾才创建 drone（与 §3.10 一致），但 harvest/build 等也需要统一时机 |

**建议**: 明确区分两类 ECS system：
- **Command-triggered systems**: 命令循环中逐条执行（Move/Harvest/Build/Transfer/Attack/Heal/Recycle）。这些 system 只修改命令直接涉及的实体。
- **Tick-internal systems**: 命令循环结束后统一 `.chain()` 执行（regeneration/decay/death/spawn + 任何 tick 级规则 system）。

Move/MoveTo 的 TOCTOU 校验（P0-2 §3.7：「如果目标在快照和执行之间移动了」）暗示命令循环中存在中间状态变更——支持「逐条应用」模型。但这与 spawn 在末尾创建的声明矛盾。请在一份 spec 中澄清完整时序。

---

### D2 [HIGH] — Spawn 执行时机与 death_system 顺序矛盾

**位置**: P0-2 §3.10 vs P0-1 §3.3

P0-2 §3.10 明确声明：
> Drone 在 tick 末尾创建（death_system 之后，spawn 槽位已释放）

P0-1 §3.3 的 ECS `.chain()` 确实把 `spawn_system` 放在 `death_system` 之后——如果所有 ECS system 在命令循环后统一运行，这是正确的。

但如果命令循环中逐条应用命令（见 D1），那么 Spawn 命令会在循环中立即创建 drone → 该 drone 会在后续 `death_system` 中被处理 → 可能被立即杀死（例如 age >= lifespan 的极端情况，或者被战斗 system 的 AOE 波及）。

**另外**: 即使 spawn 在末尾，Spawn 命令的校验（P0-2 §3.10 中 `RoomDroneCapReached`）依赖「spawn 槽位已释放」——如果 death_system 在同一 tick 末尾才运行，那么在同一 tick 中死亡的 drone 的槽位还没有释放，`RoomDroneCapReached` 校验会错误地拒绝合法的 spawn。

**建议**: 
- 采用两阶段 EXECUTE：Phase 2a（命令循环，spawn 不入队只校验）→ Phase 2b（ECS systems 运行，death 先释放槽位）→ Phase 2c（spawn 入队执行）。或者
- 在命令循环前先运行 death_system（预处理），释放槽位，然后再处理命令。但这改变了 death_system 的语义（它应该在处理完所有 tick 事件后运行）。

---

### D3 [HIGH] — Code Update Window 的部署接受 vs 模块激活时序缺口

**位置**: P0-1 §2.4, P0-7 §3

P0-1 §2.4 定义部署模型：
> Tick N: AI 调用 swarm_deploy，上传 v2
> Tick N+1: 引擎自动切换到 v2

P0-7 §3 定义了 `code_update_window_system`，在窗口关闭时阻止代码更新。

P0-7 world.toml 示例：
```toml
update_window = { every = 1000, duration = 100 }
```

**缺口**: `swarm_deploy` 在 MCP/Gateway 层处理（P0-9 Source Gate），接受或拒绝部署请求。但 code_update_window 检查发生在 Engine 的 ECS system 层（`code_update_window_system`，P0-7 §3）。

**场景**:
1. Tick 900（窗口关闭）: 玩家调用 `swarm_deploy` → Gateway 接受，存储模块
2. Tick 901（窗口关闭）: Engine 加载模块时被 `code_update_window_system` 阻塞 → 模块处于「已部署但未激活」状态
3. Tick 1000（窗口打开）: 模块自动激活

但 P0-1 §2.4 说「引擎自动切换到 v2」——如果切换被窗口阻塞，是静默延迟还是返回错误给玩家？当前 spec 未定义此行为。

另外，`MCP_Deploy` 的限流是 10/h（P0-3 §5.1）——如果窗口关闭期间玩家反复部署（以为失败），第 11 次会被限流拒绝，但前 10 次都进入了 limbo 状态。

**建议**: 
- 在 MCP_Deploy Source Gate 增加窗口感知：窗口关闭时拒绝部署并返回 `next_window_opens_at: tick_N`。
- 或者：接受部署但明确返回 `status: "accepted_deferred"` + 预估激活 tick。
- 不管哪种方案，必须在 P0-3 `swarm_deploy` 响应 schema 中体现。

---

### D4 [MEDIUM] — Dragonfly Stale Read After NATS Publish Success

**位置**: P0-1 §4.2, P0-1 §6.1

BROADCAST 阶段执行顺序：
```
1. FDB commit ✓
2. Dragonfly.update(delta)  ← 可能失败
3. NATS.publish(...)        ← 可能成功
```

P0-1 §6.1 的失败矩阵中：
> Dragonfly cache stale: 旧数据给查询入口，不影响 tick

**场景**: Dragonfly update 失败但 NATS publish 成功。
1. WebSocket 客户端收到 delta → 显示正确状态
2. REST API 客户端请求 `/api/v1/world/rooms/5` → 走 Dragonfly → 返回 stale 数据

在 Dragonfly miss（无数据）时回退 FDB 直读是正确的。但在 Dragonfly stale（有过期数据命中）时没有版本校验机制——Dragonfly 不知道自己的数据是旧的。

**影响窗口**: 最长 3s（到下一 tick 的 Dragonfly update 重试成功）。对于 tick 级别的实时游戏，玩家看到「上一 tick 的地图但这一 tick 的 delta」会造成认知不一致。

**建议**: Dragonfly 缓存条目附加 `last_tick` 版本字段。REST API 读取时校验 `cached.last_tick >= current_tick - 1`，不满足则 fallback FDB。开销极小（一次整数比较）。

---

### D5 [MEDIUM] — Snapshot 构建时 Visibility 缓存与 EXECUTE 中间态交互

**位置**: P0-5 §5, P0-1 §2.3

P0-5 §5:
> 每 tick、每玩家可见性计算一次并缓存。缓存键: (tick, player_id)

P0-1 §2.3:
> all_entities 来自 Bevy World 内存（当前 tick 执行前的权威状态）

**前提**: COLLECT 阶段不修改 Bevy World（只读），所以快照中的可见性是正确的。✓

**但**: 如果未来 COLLECT 阶段引入任何状态写入（例如 logging、metrics 更新），可见性缓存可能在 COLLECT 中基于「半修改」的状态计算。

**更关键的是**: 当前设计中，MCP 工具 `swarm_get_snapshot`（P0-3 §4.2）限流为 1/tick——这意味着 MCP 查询和 WASM tick() 收到的 snapshot 应该一致。但如果 MCP 查询在 COLLECT 和 EXECUTE 之间到达，它应该返回 pre-EXECUTE 还是 post-EXECUTE 状态？

P0-3 没有指定 MCP 工具是在 COLLECT/EXECUTE/BROADCAST 的哪个阶段服务。如果 MCP 查询在 EXECUTE 中间到达（命令正在被应用），返回的状态可能是部分更新的——这是一个一致性 bug。

**建议**: 在 Tick 状态机中增加明确的阶段门控。COLLECT 和 EXECUTE 期间 MCP 查询应返回上一 tick 的已提交状态（从 Dragonfly/FDB），而非 Bevy World 的中间态。

---

### D6 [MEDIUM] — Rhai Mod Actions 与 Command Validation Pipeline 的关系不明确

**位置**: P0-7 §8, P0-9 §2.3

P0-7 §8 声明：
> 规则 System 只能...绝不可绕过 Command 校验管线

但 P0-7 §5 中 Rhai API 允许：
```rust
actions.deduct_resource(player_id, resource, amount)
actions.damage_entity(entity_id, amount, reason)
actions.set_entity_flag(entity_id, flag, value)
```

P0-9 §2.3 的能力矩阵中 `RuleMod` 标记为：
> 允许写入世界: ⚠️ deduct/award/emit_event

**问题**: `actions.damage_entity` 直接对实体造成伤害——它走的是 Command Validation Pipeline 还是直接修改 ECS component？

如果是直接修改，那么：
- 它绕过了 PvP 规则中的 `friendly_fire` 检查
- 它不触发 `damage_multiplier` 世界规则
- 它不会被 TickTrace 记录为 Command（只记录为 RuleAction）
- 它的结果是确定性的吗？（取决于 Rhai AST 执行，但 Rhai 本身是确定的——前提是 rules 脚本在所有引擎版本上行为一致）

实际上 Rhai 处于「服主信任」层——这是有意的设计（tech-choices §3）。但需要在 P0-7 或 P0-9 中明确：rules 的 `damage_entity` / `deduct_resource` 是否经过 mini-validator（P0-7 §5 提到了 "mini-validator" 但未定义其内容）。

**建议**: 在 P0-7 §5 中明确列出 Rhai `actions` 每条操作的 mini-validator 检查项。至少应包含：`player_id` 有效性、资源非负、伤害值上限。

---

### D7 [MEDIUM] — Wasmtime 版本锁定与回放窗口

**位置**: P0-1 §6.3.3, P0-4 §2.1

P0-1 §6.3.3:
> TickTrace 始终记录 Command[] 而非 WASM 输出。回放时引擎直接执行已记录的指令序列，不重新调用 WASM。Wasmtime 版本变更不影响回放。

这个设计是正确的——回放不需要重新执行 WASM。但：

> 仅当 tick 被标记为"降级模式"（WASM 执行异常）时，需匹配 Wasmtime 版本进行二次回放验证。

**缺口**: 降级模式下的回放需要匹配 Wasmtime 版本，但 P0-4 §2.1 锁定了 `wasmtime = "=30.0"`。如果升级到 31.0，旧降级 tick 的回放验证需要 30.0 版本。引擎需要能加载多个 Wasmtime 版本（或者保留旧版本 binary）。

这在实际运维中是显著的复杂度——要么永远不升级 Wasmtime（安全风险），要么接受降级 tick 无法回放验证（合规风险）。

**建议**: 
- 降级 tick 的二次回放验证标记为「best-effort」而非「必须」。
- 或者：对降级 tick，记录 WASM 的编译产物（cached compiled module），跨 Wasmtime 版本保留。但这受限于 Wasmtime 的 compiled module 兼容性保证。
- 优先方案：接受「降级 tick 在新 Wasmtime 版本下不保证回放」作为已知限制。

---

### D8 [MEDIUM] — FDB Tick Abandon 后 Bevy World 快照恢复的不变量

**位置**: P0-1 §3.4

> EXECUTE 开始时对 Bevy World 做内存快照——FDB rollback 不自动恢复 Bevy 状态，需显式 world.restore(snapshot)

**正确性确认**: COLLECT 阶段只读 Bevy World ✓。EXECUTE 修改 Bevy World → 如果 FDB commit 失败 → `world.restore(snapshot)` 恢复 → 重试 ✓。

**潜在问题**: `world.restore(snapshot)` 的快照是什么粒度？如果 Bevy World 包含大量实体（500 玩家 × 500 drones = 250,000 实体），deep copy 整个 World 的内存开销很大。Bevy 的 `World` 不支持廉价快照——需要自己实现。

P0-1 §3.4 提到「最多重试 3 次」——每次重试都需要恢复到快照状态。如果快照是 copy-on-write 或增量式的，开销可控。但如果是 full deep clone，250K 实体 × ~2KB/实体 ≈ 500MB 内存快照，3 次重试 = 1.5GB 分配/释放。

**建议**: 在 Phase 1 实现时评估快照策略的内存开销。考虑：
- 在 EXECUTE 阶段使用 Command 日志（记录每条成功的命令 → 重放来恢复状态）而非 full snapshot
- 或者在 FDB 事务中使用乐观并发控制，仅在 commit 失败时才需要快照恢复（正常路径无开销）

---

### D9 [LOW] — Body Part Extension 缺少默认 Damage Type 绑定

**位置**: DESIGN §8.2, P0-8

DESIGN §8.2 允许通过 `[[body_part_types]]` 定义新 body part，但 P0-8 IDL 的 `BodyPart` enum 是固定的：`[Move, Work, Carry, Attack, RangedAttack, Heal, Claim, Tough]`。

如果世界扩展了 body part（例如 `Leech`、`Scramble`），IDL 需要支持扩展。当前 IDL 没有扩展机制。

**建议**: 
- P0-8 IDL 中增加 `BodyPart` 的扩展点（例如 `Custom(String)` variant）。
- 或者在 world.toml 中定义新 body part 时，明确要求声明其绑定的 damage type（如 `Leech → Corrosive`）。无显式绑定的默认行为应在 spec 中定义。

---

### D10 [LOW] — Snapshot 序列化策略未明确（O(P × E) 风险）

**位置**: P0-1 §2.3

> 快照按房间序列化一次，再按玩家过滤——不是 O(P × E)。

这个声明正确但缺少细节。「按房间序列化一次」意味着对每个房间生成一份完整 entity 列表，然后每个玩家的快照从房间列表中过滤可见实体。复杂度约为 O(R × E + P × log(E))，其中 R 是房间数。

但序列化包含 JSON 序列化开销。如果房间有 10,000 实体，JSON 序列化一次（~5MB），然后按玩家过滤意味着：要么 (a) 先过滤再序列化（对每玩家重新序列化 → O(P × E))，要么 (b) 先序列化再过滤 JSON（需要对 JSON 做 entity-level 过滤 → 复杂）。

**建议**: 明确快照构建的内部格式——应该是结构化的 `Vec<EntitySnapshot>`（内存格式），而非 JSON。仅在交付给 WASM 时才序列化为 JSON。过滤在内存格式上做，O(E) per-room 完成。

---

## Consistency Gaps

以下为跨 spec 的矛盾或不一致：

| # | 文档 A | 文档 B | 不一致 |
|---|--------|--------|--------|
| C1 | P0-1 §3.2: FDB 原子提交在 EXECUTE 阶段 | P0-1 状态机图: FDB 原子提交在 BROADCAST 阶段 | 状态机图 §1 显示 FDB commit 在 BROADCAST（阶段三），但 §3.2/§3.4 描述它在 EXECUTE（阶段二）。**应当统一到 EXECUTE**——tick 结果必须先持久化再广播 |
| C2 | DESIGN §3.2: BROADCAST 阶段「FDB 原子提交」 | P0-1 §4.2: BROADCAST 阶段「Read committed tick result from FDB」 | DESIGN 描述 FDB commit 在 BROADCAST，P0-1 描述它在 EXECUTE 已经完成。**以 P0-1 为准**（更详细的 spec），DESIGN 需要更新 |
| C3 | P0-7 §3: `code_update_window_system` 在 ECS chain 中 | P0-1 §3.3 的 ECS chain 不包含 `code_update_window_system` | P0-7 将此 system 注册为可选，但 P0-1 的「基础 ECS 执行顺序」未列出所有可选 system。**建议 P0-1 增加可选 system 注入点说明** |
| C4 | P0-8 IDL: `harvest` 的 `resource` 参数标记为 `ResourceName?`（可选） | P0-2 §3.3: Harvest 校验中无 resource 字段 | 如果 resource 是可选的，harvest 行为（采集哪种资源？）需要定义默认行为 |
| C5 | P0-9 §2.1: `Simulate` 限流为 5/tick | P0-3 §4.4: `swarm_simulate` 限流为 5/tick（World）/ 3/tick（Arena） | 数字一致，但 P0-9 没有区分 World/Arena。**微小不一致**，P0-9 应引用 P0-3 的权威限流值 |
| C6 | P0-4 §2.3: WASI 配置中明确禁止 `random_get` | tech-choices §8: PRNG 使用 Blake3 XOF | 一致——WASM 不能调用 OS 随机源，必须用 host-provided PRNG。但 P0-4 未列出 host-provided PRNG 的 host function 签名。P0-8 IDL 也没有 `host_get_random`**

**→ C6 是新发现**: WASM 玩家代码如何获取随机数？如果所有随机性由引擎在 EXECUTE 阶段（种子洗牌）决定，WASM 代码本身不需要随机数——但这对策略多样性是重大限制。玩家可能需要随机探索（ε-greedy）。如果提供随机数，需要通过 host function 暴露 Blake3 XOF，且该 host function 必须被声明。

---

## Algorithmic Risks

### R1 — Seeded Shuffle 的 O(N²) 风险

P0-1 §3.1 的种子洗牌描述:
> shuffle = Blake3 XOF: for i in 0..N: position[i] = XOF.read_u64() % (N - i)

这是 Fisher-Yates shuffle 的标准实现，O(N) 时间。但在每 tick 对所有活跃玩家执行时，如果活跃玩家数达到 10,000（Phase 7 负载测试目标），Blake3 XOF 的 `read_u64()` 调用 10,000 次 ≈ 80KB XOF 输出，开销可忽略。✓ 无风险。

### R2 — Snapshot JSON 序列化开销

每个 WASM tick() 接收序列化为 JSON 的快照。P0-2 §1.1 限制输出（指令）为 256KB，但没有限制输入（快照）大小。在最大场景下（500 drones × 1KB JSON 每 drone + 地形 + 市场订单），快照可能达到 ~1MB。每个玩家每 tick 序列化/反序列化 1MB JSON，500 玩家 = 500MB/tick 的 JSON 吞吐。

**缓解**: 「按房间序列化一次，再按玩家过滤」策略将序列化次数从 O(P) 降为 O(R)。但 JSON 格式本身不是最高效的。如果快照使用二进制格式（Postcard/bincode），序列化开销降低 5-10×。Phase 7 负载测试应在真实 JSON 快照大小下进行。

### R3 — Bevy ECS .chain() 串行化瓶颈

P0-1 §3.3 和 P0-7 §3 的基础 ECS chain 包含 8+ 个 system。`.chain()` 强制所有 system 串行执行。在 250,000 实体的世界中，串行处理所有 system 可能超过 500ms 的 EXECUTE 时间预算。

**缓解**: ROADMAP Phase 7 明确计划「ECS 并行化——`.before()/.after()` 替代部分 `.chain()`」。当前 `.chain()` 是 Phase 0 保守选择，可接受。但 Phase 1 的 baseline benchmark 应建立 per-system 耗时数据，识别真正的并行化机会。

### R4 — Dragonfly 全量 Delta 更新

P0-1 §4.1:
> delta = compute_delta(world_state_before, world_state_after)
> delta 仅包含本 tick 变更的实体

`compute_delta` 需要比较 pre-EXECUTE 和 post-EXECUTE 的完整世界状态。O(E) 比较不可避免。在 250,000 实体下，即使是 O(E) 的哈希比较也需要 ~10ms。可接受。但需要确保 delta 计算在 BROADCAST 阶段（～即时）而非 EXECUTE 阶段（～500ms）执行。

### R5 — TickTrace 写入量与 FDB 存储

每个 tick 写入 FDB：
- `/tick/{N}/state` — 完整世界状态（可能 100MB+）
- `/tick/{N}/commands` — 所有玩家指令
- `/tick/{N}/rejections`
- `/tick/{N}/metrics`

在 3s tick 间隔下，每天 = 28,800 tick。如果每 tick 的 state 为 100MB，一天 = 2.88TB。这在 ROADMAP 未提及。但 DESIGN §3.2 提到「每隔 N tick 记录完整世界快照到 FDB（回放用）」——暗示不是每 tick 全量 state。

**但 P0-1 §6.3.1 明确说每 tick 写入 `/tick/{N}/state`。**

这是一致性缺口——DESIGN 暗示间隔快照，P0-1 要求每 tick。需要澄清。如果每 tick 全量，存储需求巨大；如果间隔快照，回放需要从最近快照 + 增量指令重放。

---

## 评审总结

| 类别 | 数量 | 说明 |
|------|------|------|
| HIGH | 3 | D1(时序歧义) D2(spawn时序) D3(code window缺口) — Phase 1 实现前必须解决 |
| MEDIUM | 5 | D4(Dragonfly stale) D5(MCP中间态) D6(Rhai validator) D7(Wasmtime回放) D8(snapshot内存) |
| LOW | 2 | D9(body part扩展) D10(snapshot策略) |
| Consistency Gaps | 6 | C1-C6, 其中 C6(PRNG host function缺失) 是新发现的功能缺口 |
| Algorithmic Risks | 5 | R1-R5, R5(每tick全量state存储) 是最显著的运维风险 |

**核心建议**: D1 和 D2 必须在 Phase 1 实现前通过一份明确的「EXECUTE Phase Internal Sequence」spec 解决。D3 影响 MCP 部署体验。C6（PRNG host function）如果在 Phase 1 被遗忘，会导致所有 starter bot 无法使用随机策略。

**方向判断**: 架构基础扎实。这些问题都是「spec 不够细」而非「架构错误」。修正后可以进入 Phase 1 实现。
