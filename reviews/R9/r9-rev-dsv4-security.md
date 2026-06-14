# R9 终审 — rev-dsv4-security (DeepSeek V4 Pro, Security Primary)

> **评审范围**: DESIGN.md + tech-choices.md + specs/p0/ (全部 9 篇)
> **评审日期**: 2026-06-14
> **方法论**: 协议一致性验证、数据流追踪、竞态条件检测、信任边界分析

---

## Verdict: APPROVE_WITH_RESERVATIONS

设计整体在安全架构层面是自洽的——三层信任模型 (WASM untrusted → Rhai trusted → Rust immutable)、单一指令管线 (所有来源走同一校验路径)、per-tick fork 进程隔离、fuel metering 资源计费——构成了深度防御。P0 规范覆盖面广，Phase 0 冻结范围内无架构级安全缺陷。

但以下 4 个问题 (1 Critical + 3 High) 必须在 Phase 2 实现前解决。其余 Medium / Informational 项建议在开发过程中逐步修正。

---

## Critical

### C1: WASM start section 绕过 `_start` 检查 — 模块预执行向量

**位置**: P0-4 §2.4, DESIGN §3.2

**描述**:

P0-4 §2.4 的模块校验代码检查了 `module.export("_start")`:

```rust
if module.export("_start").is_some() {
    return Err(Rejection::StartFunctionForbidden);
}
```

但 WASM 规范中存在两种"预执行"路径:

1. **Module start section** — WASM 二进制格式的 start section 指定一个函数在模块实例化后自动调用。这个函数**不需要也不一定被导出**。`module.export("_start")` 只检查导出的 `_start`，不检查 start section。
2. **Global initializers with `global.get`/`global.set`** — 在 WASM 2.0 / GC 提案之后，global initializer 可以使用非 const 指令。当前 Wasmtime 30.0 的默认行为需要确认。

**影响**: 恶意 WASM 模块可以在 `tick()` 被调用之前通过 start section 执行任意代码。虽然 seccomp + cgroup 提供 OS 级隔离，但在 Wasmtime 沙箱内可能:
- 消耗 fuel budget 在 `tick()` 被调用前（fuel metering 在实例化时是否生效？）
- 通过 host function 查询世界状态（如果 host function 在实例化阶段可用）

**数据流**: `WASM module deploy → validate_module() → Module::from_binary() → Instance::new() [start section 在此执行] → tick()`

**修复建议**:

```rust
// 检查 start section（非导出函数）
if module.start_function().is_some() {
    return Err(Rejection::StartFunctionForbidden);
}

// 检查全局初始化器是否为 const-only
for global in module.globals() {
    if !is_const_initializer(global) {
        return Err(Rejection::NonConstGlobalInit);
    }
}
```

需要在恶意 WASM 样本库中添加 start section 测试用例。

---

## High

### H1: `host_path_find` fuel 计费模型严重低估 — 服务器端计算 DoS

**位置**: P0-4 §8, P0-2 §4.3

**描述**:

P0-4 §8 定义 path_find 的 fuel 成本:

| 函数 | fuel 成本 | 响应大小上限 |
|------|----------|------------|
| `host_path_find` | 10,000 + 50/tile | 8 KB |

这里 `50/tile` 是**返回路径的 tile 数**，不是 A* 算法实际探索的节点数。

在以下场景中，实际计算量与 fuel 成本严重不匹配:

- **大地图 + 短路径上限**: 房间地图 256×256 = 65,536 格。P0-2 限制 path_length ≤ 100，但 A* 在开放地形上从 (0,0) 到 (127,127) 会探索数千个节点后才确定"无 ≤100 路径"或找到一条 ≤100 的路径。
- **恶意构造**: 玩家可以故意查询两点之间极远但恰好有路径 ≤ 100 的情况（如迷宫地图），迫使引擎探索大量节点。
- **缓存绕过**: P0-2 §4.3 提到 `(from, to, 地形hash)` 缓存。但攻击者可以用 10 次调用 × 10 种不同坐标组合（100 种组合）绕过缓存，配合地势频繁变化的世界。

**影响**: 10 次 path_find 调用，每次探索 50,000 节点，总计算量远超 WASM 端消耗的 10 × (10,000 + 50×100) = 150,000 fuel。服务器端实际消耗的 CPU 时间是 WASM fuel 体现的 100-1000 倍。在高玩家并发下可能导致 tick 超时。

**修复建议**:

1. path_find fuel 成本公式改为 `10,000 + cost_per_explored_node × nodes_explored`，由引擎在执行后向 WASM fuel counter 追加扣费
2. 或者: 在 path_find 内部设置独立的探索节点上限（如 50,000 nodes），超限则返回 `PathTooComplex` 错误码
3. 增加 MAX_PATH_FIND_ATTEMPTS 全局限制（非 per-player），防止多玩家同时触发高昂寻路

### H2: JSON Schema 校验深度限制可被宽度攻击绕过

**位置**: P0-2 §1.1

**描述**:

P0-2 §1.1 规定 tick 输出 JSON 的深度限制为 ≤ 10 层。但没有对数组宽度（元素数量）设置二级约束。攻击者可以构造:

```json
[
  {"player_id":1,"tick":1,"sequence":1,"action":{"type":"Move","object_id":1,"direction":"TopRight"}},
  ... x100 条合法但无用的指令
]
```

每条指令都通过 schema 校验和反序列化，然后在预校验阶段逐一进行 world state 查询（FDB read per entity check）。100 条指令 × 每个需要查 3-5 个 FDB key = 300-500 次数据库读取。

**影响**: 100 条合法但必失败的指令（如全部 Move 到 Wall 格）会在 EXECUTE 阶段造成大量无效 FDB 读取和日志写入。P0-2 MAX_COMMANDS_PER_PLAYER=100 是上限，但未区分"有用指令"和"垃圾指令"。虽然最终全部指令都会被拒绝（`TileBlocked`），但每条仍然走了完整校验管线——FDB 读取、坐标校验、归属校验。

**与 H1 组合**: 100 个 MoveTo(path_find) 指令会触发 100 次寻路，即使最终因 `NoPath` 被拒绝。需确认 path_find 发生在哪个阶段——如果在预校验 (阶段一)，则 100 次寻路全部在收集阶段执行，直接拖垮单个玩家的 sandbox worker。

**修复建议**:

1. 在预校验阶段增加快速短路: 对明显必失败的指令（如 Move 到 Wall）在读取 world state 前先通过 terrain cache 快速判断
2. 对同一 tick 内同一玩家的高拒绝率 (>80%) 触发 early abort: 该玩家剩余指令直接丢弃
3. 对 MoveTo 指令的 path_find 延迟到执行阶段（而非预校验阶段），利用执行阶段的 seed shuffle 保证公平

### H3: `swarm_simulate` 缺少 N tick 上限 — 服务器端计算 DoS

**位置**: P0-3 §4.4, P0-9 §2.2

**描述**:

P0-3 §4.4 定义 `swarm_simulate` 工具:

> 离线模拟：给定世界快照，预测未来 N tick

但**没有定义 N 的上限**。P0-9 §2.2 给出 budget = `0.5 × MAX_FUEL`，但这只在每个 simulated tick 内部消耗 fuel。如果 N=10,000，即使每 tick 消耗 0.5 × 10M fuel，实际计算量也会非常巨大。

**影响**: 攻击者可以提交 `swarm_simulate(snapshot, ticks=999999)` 来消耗引擎大量 CPU 时间。虽然 P0-3 限制为 5/tick (World) / 3/tick (Arena)，但单次 simulate 可以运行很长时间。

**修复建议**:

1. 在 P0-3 和 P0-9 中显式定义 `MAX_SIMULATE_TICKS`（建议 100-200 tick）
2. Simulate 执行需设置独立的墙钟超时 (如 500ms)
3. Simulate 失败不计入正常 tick 的 FDB 事务——它操作的是快照副本

---

## Medium

### M1: Command `amount=0` 未被显式拒绝

**位置**: P0-2 §3.4

Transfer/Withdraw 指令的 `amount` 字段没有显式校验 `amount > 0`。虽然 `amount=0` 不会造成经济损害，但它消耗一个指令槽位，走完整校验管线，产生无意义的 TickTrace 日志。建议在校验矩阵中添加 `amount > 0` 检查，失败码 `InvalidAmount`。

### M2: FDB 事务重试可能放大竞争

**位置**: P0-1 §3.4

> `txn.commit()` 失败 → 最多重试 3 次 → 全部失败则 tick 放弃。

如果 FDB 冲突是由于高竞争（多个 shard 修改同一 key），重试 3 次用相同数据大概率继续冲突。每次重试都会重新读取并重新验证所有指令。在降级模式下（暂停新玩家加入），系统可以恢复，但在进入降级之前已经浪费了 3+ tick 的计算资源。

建议: 在重试间隔中加入指数退避 (1s, 2s, 4s)，并在第 2 次重试时 `join_lock = true`（提前阻止更多写入竞争）。

### M3: 沙箱 worker 进程泄漏风险

**位置**: P0-4 §1

> 生命周期: sandbox worker 进程每 tick 新 fork，执行一个玩家，返回指令，然后 kill。

`kill` 是 SIGKILL 还是 SIGTERM？如果是 SIGKILL，子进程无法清理资源（临时文件、共享内存段）。cgroup 的 `memory.max` 和 `pids.max` 提供硬限制，但 tmpfs `/tmp` (16MB) 不会在 SIGKILL 后自动清理。需要确认 sandbox worker 在 fork 时挂载独立的 tmpfs namespace，或引擎进程在 kill 后主动清理。

建议在 P0-4 中明确:
1. kill 使用 SIGKILL（确保终止）
2. sandbox 使用独立的 mount namespace + tmpfs（进程终止 = 自动清理）
3. 引擎侧增加 worker 超时看门狗：fork 后超过 3000ms 未返回 → force kill

### M4: `host_get_objects_in_range` 可见性过滤成本与 fuel 不匹配

**位置**: P0-4 §8, P0-2 §4.2

fuel 成本 2,000 + 100/entity 覆盖序列化成本，但可见性过滤 `is_visible_to()` 需要检查该玩家所有的视野源（drones, towers, observers），然后对范围内每个实体调用。如果玩家有 100 个 drone 且查询一个大范围，过滤计算量是 O(vision_sources × entities_in_range)，而非 O(entities_in_range)。

建议: 将可见性过滤成本从"包含在 100/entity 中"改为"100/entity + 10/vision_source"，或限制 range 参数不能超过玩家实际拥有的最大视野范围。

### M5: MCP HTTP/2 multiplexing 未在安全合同中涉及

**位置**: P0-3 §5.3

P0-3 §5.3 禁用了 JSON-RPC batch，但未提及 HTTP/2 的 multiplexing 特性。HTTP/2 允许在单个 TCP 连接上并发发送多个请求，效果类似 batch。虽然逐请求的 rate limiter 仍然工作，但并发度可能超过预期。

建议: 在 HTTP 安全合同中增加 `max_concurrent_streams` 限制。

---

## Informational

### I1: `world_seed` 未在 P0-5 可见性表中显式列出

**位置**: P0-5 §2.4

P0-5 §2.4 列出 "RNG 种子 ❌ 始终隐藏"，但这仅指 per-tick 的 RNG 状态。`world_seed`（用于确定种子洗牌和全局 PRNG 的根种子）没有被单独列出。虽然它属于 "Admin-only" 级别数据（P0-5 §3 数据分级表），但 DESIGN §8.8 明确说 world_seed 是 32 字节熵。建议在 P0-5 §2.4 中显式加入 `world_seed → Admin-only`。

### I2: Tutorial 来源隔离依赖单点检查

**位置**: P0-9 §2.4

> `Tutorial` 来源的指令仅可在 `world.mode = "tutorial"` 的世界中接受。

这是 Source Gate 中的一个 if 语句。如果将来有人添加新的 world.mode 且忘记更新这个检查，Tutorial 指令可能泄漏到非教程世界。建议改为白名单模式：Tutorial 来源仅在明确的 tutorial world ID 列表中有效，而非依赖 `mode` 枚举。

### I3: MoveTo 的 path_find 发生在预校验阶段但计入 EXECUTE 阶段超时

**位置**: P0-2 §3.2

P0-2 §3.2 MoveTo 的校验项包括 `path_exists`（"从当前位置到 (x, y) 存在路径"）。这意味着寻路发生在指令校验阶段。但 P0-1 §3.1 将指令排序和校验放在 EXECUTE 阶段（§3 阶段二）。如果 path_find 在 EXECUTE 阶段串行执行（而非在 COLLECT 阶段并行），会显著增加 EXECUTE 阶段的 500ms 超时压力。

建议在 P0-1 §3.1 中明确 `path_find` 的执行时机。如果预校验包含 path_find，应在 COLLECT 阶段完成（利用 WASM sandbox worker 的并行性），而非移到 EXECUTE 阶段。

### I4: Body part 成本表在 IDL 和 DESIGN.md 之间有不一致风险

**位置**: P0-8 §2 (body_cost), DESIGN.md §8 (actions.costs)

P0-8 IDL 中 body_cost 是权威来源（IDL → codegen → SDK → docs）。但 DESIGN.md §8 也有示例 body_part.* 成本。如果有人在设计讨论中引用 DESIGN.md 的值而非 IDL，可能导致实现偏差。建议在 DESIGN.md 的 body_part 成本部分添加注释指向 P0-8 为权威来源。

---

## 数据流追踪完整度

| 数据流阶段 | 校验点 | 状态 |
|-----------|--------|------|
| World State → Snapshot JSON | `is_visible_to()` 过滤, P0-5 | ✅ 完整 |
| Snapshot → WASM linear memory | seccomp + cgroup 隔离, P0-4 | ✅ 完整 |
| WASM `tick()` execution | fuel metering + epoch interruption, P0-4 | ✅ 完整 |
| WASM → Command JSON | JSON Schema validation, P0-2 §1.1 | ✅ 完整 |
| Command JSON → RawCommand | Schema + bounds + auth injection, P0-9 | ✅ 完整 |
| RawCommand → Validation | Source Gate + Auth Verify, P0-9 | ✅ 完整 |
| Validation → Application | Per-command matrix, P0-2 §3 | ✅ 完整 |
| Application → FDB commit | FDB transaction, P0-1 §3.4 | ✅ 完整 |
| FDB → Delta → NATS → Client | Visibility filter on delta, P0-5 §3.3 | ✅ 完整 |

**无「信任下游会校验」的假设**——每个阶段独立执行自己的校验。Source Gate (P0-9) + Command Validation (P0-2) + Visibility Filter (P0-5) 构成三道防线。

## 算法边界审查

| 算法 | 最大计算量 | 限制机制 | 风险 |
|------|-----------|---------|------|
| Pathfinding (A*) | MAX_PATH_LENGTH=100, 10 calls/tick | fuel 10,000+50/tile, 缓存 (from,to,terrain_hash) | **HIGH**: 探索节点数 ≫ 路径长度, fuel 低估 |
| Visibility filter | O(vision_sources × entities) | per-tick cache (tick, player_id) | **LOW**: 缓存有效 |
| Seeded shuffle | O(N players) | N ≤ 500 active | **LOW**: 线性 |
| `get_objects_in_range` | range ≤ 10, hex grid ≤ ~330 cells | 5 calls/tick | **LOW**: fuel 适当 |
| WASM compilation | 30s timeout, 512MB | 5 concurrent, per-deploy cache | **LOW**: 独立进程 |

---

## 与其他 Reviewer 发现对比（如已知）

_等待 Phase 2 交叉评审后填写。若其他 Security reviewer (rev-claude-security, rev-gpt-security) 发现同向问题，在此记录。_

---

*reviewer: rev-dsv4-security | model: deepseek-v4-pro | direction: Security (Primary)*
