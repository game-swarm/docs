# R14 确定性评审报告 — rev-dsv4-determinism

**评审员**: Determinism Reviewer (DeepSeek V4 Pro)
**评审日期**: 2026-06-18
**评审范围**: 设计阶段，仅方向相关子集（5 文档）
**评审原则**: 设计阶段评审，不考虑分阶段实现；有合适方案直接采用，不考虑实现难度

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在一个 **Critical** 级别的排序键矛盾，直接威胁 replay determinism 的一致性。若此矛盾不解决，不同阅读者（或不同实现阶段）会产出排序行为不一致的引擎，导致"同一输入不同世界状态"——这正是确定性引擎最根本的失败模式。

其余发现需在实现前矫正。整体确定性设计思路优秀，基础扎实。

---

## 2. 发现的问题

### D1 [Critical] 命令排序键矛盾：shuffle 顺序 vs 字典序

**位置**: `specs/core/01-tick-protocol.md` §3.1 vs §9.1

**证据**:

§3.1 (L239-252) 明确定义了 seeded shuffle 执行顺序:
```
let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);
let player_order: Vec<PlayerId> = seeded_shuffle(&active_players, &seed);
// global_queue.push((order_index, player_id, cmd.sequence, cmd));
```
执行队列键为 `(shuffle_order_index, player_id, sequence, cmd)`。

§9.1 (L785-797) 却定义了完全不同的排序键:
```
RawCommand 的全局排序键为 (player_id, sequence, source)
不同 player 间按 player_id 字典序。
此排序键同时用于 Phase 2a inline apply 顺序和 TickTrace 记录。
```
这里 **没有 shuffle**，使用 `(player_id, sequence, source)` 字典序。

**严重性分析**:

| 如果遵循... | Phase 2a 执行 | TickTrace 记录 | Replay 结果 |
|------------|-------------|--------------|-----------|
| §3.1 (shuffle) | 按 shuffle 顺序 | 需记录 shuffle 顺序 | replay 按 shuffle 重排 → 匹配 |
| §9.1 (plain) | 按 player_id 字典序 | 按 player_id 字典序 | replay 按字典序 → 匹配 |
| 混用 (§3.1 执行 + §9.1 记录) | shuffle 顺序 | player_id 字典序 | replay 读字典序记录但执行用 shuffle → **分叉** |

**第三种场景就是确定性灾难**: 如果 TickTrace 按 §9.1 记录 `(player_id, sequence, source)` 字典序，但实际执行按 §3.1 的 shuffle 顺序，回放时遵循 TickTrace 的字典序记录会导致完全不同的 Phase 2a 结果（资源竞争先到先得、Attack 命中与否等全部改变）。

**建议**: 统一排序键定义。鉴于设计明确讨论公平性（"公平性：每个 tick 玩家顺序随机轮换，长期期望均等"），应以 §3.1 的 shuffle 方案为准。需要:
1. 修正 §9.1 将排序键改为 `(shuffle_order, player_id, sequence, source)`
2. 明确 TickTrace 记录包含 `shuffle_order` 字段
3. 明确 `TickInputEnvelope.commands_hash` 对 shuffle 后的 canonical order 计算

---

### D2 [Critical] f64 禁用 vs WASM SIMD 启用 — 跨平台确定性冲突

**位置**: `design/engine.md` §7.1 vs `specs/core/04-wasm-sandbox.md` §2.2

**证据**:

engine.md §7.1 确定性合同 (L673):
> 数值：整数 + 定点数，禁用 `f64`（跨平台/编译器非确定）

wasm-sandbox.md §2.2 (L90):
```rust
config.wasm_simd(true);  // 允许 SIMD（性能）
```

WASM SIMD 指令集包含 `f64x2` 操作（如 `f64x2.add`, `f64x2.mul`, `f64x2.sqrt` 等）。虽然引擎自身 ECS 代码不使用 f64，但 WASM 模块可利用 SIMD 执行 f64 运算。

**风险**:
- 不同 CPU 架构（x86_64 vs ARM64）的 SIMD f64 实现可能有不同的 NaN 传播行为、非规格化数处理、舍入细微差异
- 同一玩家代码在不同架构的 worker 上执行可能产出不同精度的数值结果，进而影响 Command 输出（如资源计算、路径评估）
- Player A 在 x86 节点和 ARM 节点上编译的 WASM，若使用 f64 SIMD，其 tick() 输出可能不同 → 破坏确定性

**建议**:
- 方案 A: 禁用 WASM SIMD（`wasm_simd(false)`），代价是性能
- 方案 B: 保持 SIMD 启用，但在 WASM 模块校验阶段添加 f64 SIMD 指令检测，拒绝使用 `f64x2.*` 操作的模块。SDK 侧强制所有数值 API 使用 `i32`/`i64`
- 方案 C: 在 wasmparser 预校验阶段扫描并拒绝包含任何 f64 相关 SIMD opcode 的模块

推荐方案 B 或 C——保留整数 SIMD 性能，阻断 f64 入口。

---

### D3 [High] IndexMap 使用范围未穷举 — 非确定性集合的风险敞口

**位置**: `design/engine.md` §3.1, `specs/core/01-tick-protocol.md` §7.1

**证据**:

engine.md 明确对 `Resource.amounts` 和 `Source.produces` 使用 `IndexMap`:
```rust
struct Resource {
    amounts: IndexMap<String, u32>,
}
struct Source {
    produces: IndexMap<String, u32>,
}
```

确定性合同 §7.1 (L674):
> HashMap：`indexmap`，不用 `std::HashMap`（迭代顺序非确定）

**缺口**: 合同仅提及 `HashMap`。但 ECS 设计中存在大量其他集合类型，其迭代顺序是否确定未明确声明:

| 集合类型 | 确定？ | 文档是否声明 |
|---------|:-----:|:----------:|
| `Vec` | ✅ | 隐式 |
| `HashMap` | ❌ (std) → ✅ (indexmap) | 已声明 |
| `BTreeMap` | ✅ | 未声明 |
| `HashSet` | ❌ (std) | 未提及 |
| `BTreeSet` | ✅ | 未提及 |
| `BinaryHeap` | ❌ (非稳定排序) | 未提及 |
| `VecDeque` | ✅ | 未提及 |
| Bevy `Query` 迭代 | ⚠️ 依赖内部 archetype 布局 | 提及但归因于 `.chain()` |

**建议**: 确定性合同 §7.1 应穷举所有可用集合类型，标注是否允许及其确定性前提:
```
- Vec/VecDeque: 允许（迭代顺序确定）
- IndexMap: 允许（替代 std::HashMap）
- BTreeMap/BTreeSet: 允许（迭代顺序确定）
- std::HashMap/std::HashSet: 禁止
- BinaryHeap: 禁止（非稳定排序）
- Bevy Query 迭代: 仅限 .chain() 调度内使用
```

---

### D4 [High] TickInputEnvelope 冗余字段 — 误导回放契约

**位置**: `design/engine.md` §3.3 (L275-280)

**证据**: TickInputEnvelope 记录:
```
- module_hash, wasmtime_version, effective_tick
- wasm_status（ok/timeout/trap/fuel_exhausted）
```

但回放协议 (§6.3.3) 明确声明:
> TickTrace 始终记录 Command[] 而非 WASM 输出。回放时引擎直接执行已记录的指令序列，不重新调用 WASM。Wasmtime 版本变更不影响回放。

**矛盾**: 如果回放不调用 WASM，为何 TickInputEnvelope 需要 `module_hash`、`wasmtime_version`、`wasm_status`？

**风险**: 
- 实现者可能误读为"回放时需验证 module_hash 匹配"——引入不必要的耦合
- 增加 TickInputEnvelope 体积，与 FDB 小事务设计目标冲突
- `wasm_status` 在回放时无用——回放不产生新的 wasm_status

**建议**: 
- 将 `module_hash`、`wasmtime_version`、`wasm_status` 从 replay-critical TickInputEnvelope 中移除
- 如需审计，放入独立的 audit log（非 replay 输入）
- 仅保留 replay 实际需要的字段：`effective_tick`、`snapshot_hash`、`commands_hash`、`deploy_events`、`rollback_events`、`admin_events`、`world_config_hash`、`mods_lock_hash`、`engine_abi_version`

---

### D5 [Medium] entity_id 生成确定性未声明

**位置**: `specs/core/01-tick-protocol.md` §2.3 截断排序，`design/engine.md` §3.1

**证据**: 快照截断使用 `entity_id` 作为确定性排序键 (L157):
> 同一桶内按确定性排序键 `(distance_to_drone, entity_id)` 升序排列，保证同输入同截断结果。

但 `entity_id` 的分配策略未在确定性合同中声明。在 Bevy ECS 中，entity ID 包含 `index`（顺序分配）和 `generation`（复用计数）。若 spawn 顺序确定，entity_id 分配确定；但此前提未写入合同。

**建议**: 在确定性合同 §9 中补充:
> entity_id 分配确定性：Bevy Entities 使用确定性 reserve/generation。相同初始状态 + 相同 Command 序列 → 相同 entity_id 分配序列。

---

### D6 [Medium] seed 派生公式中的编码不一致

**位置**: `specs/core/01-tick-protocol.md` §3.1 vs §3.1 种子轮换

**证据**:

Shuffle seed (L241-243):
```rust
let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);
```
— 使用 `to_le_bytes()`。

Seed rotation (L267):
```
new_seed = Blake3(old_seed || current_tick)
```
— 未指定 `current_tick` 的编码格式（是 u64 原始字节还是 to_le_bytes？）。

PRNG per-entity stream (engine.md L273):
```
Blake3(stream_name || world_seed || entity_id.to_le_bytes() || tick.to_le_bytes())
```
— 使用 `to_le_bytes()`。

**风险**: 中等。三个位置的 tick 编码若不一致（如一处用 native byte order，一处用 LE），在 big-endian 平台上可能分叉。当前 Rust 生态主要运行在 LE 平台，但确定性合同不应依赖此假设。

**建议**: 统一所有 seed 派生使用 `to_le_bytes()`，并写入确定性合同 §9.5 作为权威公式。

---

### D7 [Medium] refund throttle 状态是否纳入 replay 状态？

**位置**: `specs/core/02-command-validation.md` §7.3

**证据**: 退还滥用检测依赖"连续 3 tick"的历史状态:
> 连续高退还率 throttle | 退还率 > 80% 连续 3 tick | 触发 throttle

对于 replay 确定性，throttle 状态（连续高退还计数、当前 throttle 级别）必须是 replayable 世界状态的一部分。但文档未声明 throttle state 是否存储在 TickTrace 或 WorldState 中。

**建议**: 
- 明确 throttle state 是 WorldState 的 Resource（如 `RefundThrottleState`），纳入 Bevy snapshot 范围
- 补充到 §3.5 "必须捕获的 Resource 类型" 列表中
- 或在 TickTrace 中记录各玩家 throttle 状态

---

### D8 [Medium] ECS 并行系统数据独立性需要形式化验证

**位置**: `specs/core/01-tick-protocol.md` §3.4, §3.4 并行安全证明

**证据**: 声称 regeneration 和 decay 与主线系统无数据竞争，但仅有自然语言论证:
> regeneration 只写 Energy/Carry（资源总量），与其并行的主线系统不读/写此字段 → 无数据竞争

**风险**: Bevy 并行调度器在 `.before()/.after()` 约束下保证执行顺序，但两个无依赖的并行系统（如 code_propagation_system 和 regeneration_system）之间的调度顺序是**非确定**的。如果它们之间存在未声明的隐含数据依赖（如通过 Resource 而非 Component），就可能在特定并行调度下触发非确定行为。

当前文档有读写矩阵（§3.4），但仅覆盖 6 个核心系统。完整的 20 系统链中，`code_propagation_system`、`spawning_grace_system`、`stronghold_production_system`、`npc_ai_system` 等与 `regeneration`/`decay` 并行的系统，其读写矩阵未穷举。

**建议**: 
- 补齐所有 20 个系统的完整 Component/Resource 读写矩阵
- 对每个并行系统对，证明数据独立性的充分条件（不共享可写 Component/Resource，或通过 Bevy 的 `Without<>` filter 互斥）
- 将此矩阵纳入 CI 回归测试（如通过 Bevy 的 schedule graph 静态分析）

---

### D9 [Low] Replay 时 player_id 不可变但文档未明确

**位置**: `specs/core/01-tick-protocol.md` §6.3

**证据**: 回放协议使用记录的 RawCommand，其中 `player_id` 是服务端注入的。但若玩家 ID 在系统重启后重新分配（如 UUID 重新生成），回放会与记录不一致。

**建议**: 确定性合同补充: `player_id` 是稳定的 64 位标识符，在 world 生命周期内不变。回放时使用记录中的原始 player_id，不重新映射。

---

### D10 [Low] `host_path_find` 缓存键中 visibility_fingerprint 未定义

**位置**: `specs/core/04-wasm-sandbox.md` §8

**证据**: 寻路缓存键为 `(from, to, terrain_hash, player_visibility_fingerprint)`。`player_visibility_fingerprint` 是一个未出现在其他文档中的概念。如果指 fog_of_war 状态哈希，需明确其计算方式（完全由世界状态 + player 位置决定，无随机成分）。

**建议**: 定义 `player_visibility_fingerprint` 为 `Blake3(caller_player_id || visible_entity_ids_sorted || visible_terrain_hash)`。

---

## 3. 亮点

1. **确定性优先的设计哲学贯穿始终**。设计原则 #2 将确定性作为核心目标，而非事后修补。`f64` 禁用、`indexmap` 替代 `HashMap`、定点整数运算、PRNG 种子隔离——这些决策显示出对确定性陷阱的深刻理解。

2. **Replay 不重执行 WASM** 是正确的关键架构决策。避免 Wasmtime 版本耦合，消除了一大类跨版本回放中断风险。TickTrace 记录排序后的 Command 而非 WASM 输出，确保回放输入的精确定义。

3. **Blake3 XOF 种子体系**设计精良。per-namespace RNG 隔离（combat/loot/npc_spawn/event）防止了跨系统随机数污染。`Blake3(stream_name || world_seed || entity_id || tick)` 的派生方案安全且可验证。

4. **快照截断的确定性排序**设计到位。关键桶/高优先/中优先/低优先的分桶 + `(distance, entity_id)` 排序键保证了同输入同截断结果。`omitted_count` 让 WASM 代码可感知截断状态。

5. **FDB 事务原子性与 Bevy snapshot 恢复**的配合确保了 tick 原子性。Phase 2a 前深拷贝 → FDB commit 失败时 `world.restore(snapshot)` → 复用 COLLECT 缓存重试。完整的故障—恢复闭环。

6. **Inline 执行 + TOCTOU 合同**在 Phase 2a 中解决了"基于快照校验但世界已变化"的时间窗口问题。Spawn pending 不可见、Hack 下所有权不变、单 drone 单 action 配额——这些规则共同闭合了 inline 执行的竞争条件。

7. **WASM 预编译 + per-tick 实例化**在不对确定性让步的前提下最大化了性能。编译后的模块按 `(module_hash, wasmtime_version)` 缓存，避免了 tick 时的 JIT 开销。

---

## 4. CrossCheck — 需要跨方向检查

- **CX1**: §3.1 vs §9.1 排序键矛盾 → 建议 **Architect** 检查并统一权威排序键定义。同时确认 `TickInputEnvelope.commands_hash` 的输入范围（shuffle 前还是后？）。此问题同时影响公平性（Fairness）方向——若采用 §9.1 的字典序排序，固定排序将破坏 shuffle 的公平性保证。

- **CX2**: WASM SIMD 启用 (`wasm_simd(true)`) + f64 禁用 → 建议 **Security Reviewer** 检查 WASM 模块是否可以通过 SIMD f64 指令（`f64x2.*`）绕过确定性约束。同时在 wasmparser 预校验中应增加 f64 SIMD opcode 检测。

- **CX3**: Recycle 退还比例递减（§3.18）+ Controller repair 延长 lifespan（engine.md §4.8）→ 建议 **Gameplay/Economy Reviewer** 验证是否存在 repair→Recycle 套利路径：drone 接近 lifespan 末期 → Controller repair 降低 age → 回到高 refund_pct 区间 → Recycle 获利。当前 refund 公式 `refund_pct = max(0.1, 0.5 × remaining/total)` 中 `remaining` 应是 repair 后的值——确认 repair 是否在 Recycle 前结算。

- **CX4**: TickInputEnvelope 冗余字段 → 建议 **Architect** 审查 replay-critical vs audit-only 字段的边界。将与 replay 无关的字段移入独立审计结构，降低 TickInputEnvelope 体积并消除实现歧义。

- **CX5**: Rhai RuleMod 的"固定点数，禁止 f64"约束（§9.8）→ 建议 **Security Reviewer** 验证 Rhai 引擎是否在编译期强制禁止 f64 字面量和 f64 操作，而非运行时捕获。并与 WASM SIMD 的 f64 入口点形成一致的禁止面。

---

## 5. 评审总结

整体确定性设计质量很高，基础架构选择（Bevy ECS `.chain()`、Blake3 PRNG、定点整数、IndexMap、Replay 不重执行 WASM）都是正确的。**D1（排序键矛盾）是唯一的阻断项**——它直接导致"遵循不同文档章节的读者产出的引擎具有不同的执行行为"，且 TickTrace 记录格式依赖此决策。

建议在 D1-D4 解决后进入 CONDITIONAL_APPROVE 状态。D5-D10 可在实现阶段逐步闭合。

---

*End of report. 5 文档审查完毕。*
