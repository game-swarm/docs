# R10 架构评审报告 — Architect Reviewer (DeepSeek V4 Pro)

**评审日期**: 2026-06-14
**评审范围**: DESIGN.md (1463L) + tech-choices.md (223L) + ROADMAP.md (212L) + PLANNER-OUTPUT.md (98L) + specs/p0/*（9份，2422L）
**评审维度**: ECS调度正确性 | Tick生命周期完整性 | 数据一致性(FDB+Dragonfly) | 算法复杂度
**上轮参考**: R9 rev-dsv4-architect (340L) — 追踪3个D1、4个D2、3个D3的修复状态

---

## Verdict: REQUEST_MAJOR_CHANGES

R9 的 3 个 D1 中，1 个已修复 (D1-1 FDB回滚与内存快照)、1 个未修复 (D1-2 COLLECT读取源)、1 个未修复 (D1-3 Wasmtime版本策略)。本轮新发现 1 个 D1、4 个 D2、2 个 D3、2 个一致性缺口和 2 个算法风险。Phase 1 不能开始，直到 D1-1 (本轮)、D1-2 (R9遗留) 和 D1-3 (R9遗留) 全部解决。

---

## R9 问题修复状态

| R9 ID | 描述 | 状态 | R10 追踪 |
|-------|------|------|---------|
| D1-1 | FDB commit失败时 Bevy ECS 无回滚 | ✅ 已修复 | P0-1 §3.4 新增 "EXECUTE 开始时对 Bevy World 做内存快照——FDB rollback 不自动恢复 Bevy 状态，需显式 world.restore(snapshot)" |
| D1-2 | COLLECT 读取源未定义 | ❌ 未修复 | → R10 D1-1（降级为 D1） |
| D1-3 | Wasmtime 版本锁定 vs 安全SLA | ❌ 未修复 | → R10 D1-2 |
| D2-1 | 种子洗牌 modulo bias | ❌ 未修复 | P0-1 §3.1 代码无变化 |
| D2-2 | Resource.amounts 用 HashMap | ⚠️ 部分修复 | Resource.amounts → IndexMap ✅，但 Source.produces 仍为 HashMap ❌ → R10 D2-1 |
| D2-3 | EXECUTE 超时无处理策略 | ❌ 未修复 | → R10 D2-2 |
| D2-4 | Dragonfly 重建流程缺失 | ❌ 未修复 | P0-1 §4.2 无变化 |
| D3-1 | Transfer cost 语义模糊 | ❌ 未修复 | → R10 D3-1 |
| D3-2 | 可见性计算 O(P×E) 爆炸 | ❌ 未修复 | → R10 AR-1 |
| D3-3 | host_get_world_rules 在 P0-4 缺失 | ❌ 未修复 | → R10 CG-1 |

**修复率**: 1/10 完全修复，1/10 部分修复，8/10 未修复。

---

## D1 (阻断级 — 必须在 Phase 1 前修复)

### D1-1: Source.produces 使用 HashMap — 确定性合同破裂

**位置**: DESIGN.md §3.1 (Source struct) + DESIGN.md §8.8 (Determinism Contract)

**问题描述**:

R9 D2-2 指出 `Resource.amounts: HashMap<String, u32>` 违反确定性合同。修复后 Resource.amounts 已改为 IndexMap。但**同一模式在 Source struct 中仍然存在**：

```rust
// DESIGN.md §3.1 — Resource ✓ 已修复
struct Resource {
    amounts: IndexMap<String, u32>,    // IndexMap 保证迭代顺序确定
}

// DESIGN.md §3.1 — Source ✗ 仍为 HashMap
struct Source {
    produces: HashMap<String, u32>,   // { "Energy": 1 } 或 { "Energy": 1, "Matter": 1 }
    capacity: u32,
    ticks_to_regeneration: u32,
}
```

`Source.produces` 在多资源世界中会被迭代——regeneration_system 遍历所有产出资源类型决定每 tick 恢复多少。HashMap 的迭代顺序在不同 Rust 版本/构建间可变 → 多资源 Source 的再生顺序不确定 → state_checksum 偏离 → 回放失败。

**影响面**: 任何定义了 >1 种资源产出的世界（如 `{Energy: 1, Matter: 1}`）都无法保证回放确定性。

**修复建议**: `produces: IndexMap<String, u32>`。同时用 grep 全量扫描所有 HashMap 使用点，确保没有遗漏的迭代。

---

### D1-2: Wasmtime 安全升级必然破坏回放保证 — 无缓解方案

**位置**: P0-4 §2.1 + DESIGN.md §8.8 + ROADMAP §7.6

**问题描述**:

R9 D1-3 指出的矛盾仍然存在：
- `wasmtime = "=30.0"` 锁定精确版本（甚至不允许 patch）
- 回放保证: "相同 Wasmtime pinned 版本下 execute_deterministic == recorded_state"
- 安全 SLA: "严重 CVE (CVSS ≥ 9.0): 72 小时内评估 + 补丁"

ROADMAP §7.6 进一步承诺 "Wasmtime 安全补丁 SLA: CVE 响应 < 7 天；版本迁移脚本"，但没有说明迁移脚本如何不破坏回放。

**根本问题**: 仅记录 wasmtime 版本号不够——即使知道 tick N 用了 wasmtime 30.0，在 30.1 安全升级后如何重新执行 tick N 的 WASM？需要多版本 Wasmtime 共存，或 R9 推荐的方案 C（记录 Command[] 回放时跳过 WASM 执行）。

**修复建议**: 必须在 Phase 1 前做出架构决策。R9 方案 C（Trace 中记录 Command[] 允许不回放 WASM 执行的降级回放模式）是长期解，但需要与方案 A（多版本 Wasmtime）的成本做权衡。至少文档化风险并在 P0-4 中增加一节 "回放兼容性策略"。

---

### D1-3: COLLECT 阶段世界状态读取源仍未明确

**位置**: P0-1 §2.3 + P0-5 §5

**问题描述**（R9 D1-2 遗留）:

P0-1 §2.3 的 `build_snapshot()` 伪代码仍然没有指定数据来源：
```
fn build_snapshot(player_id, tick) -> Snapshot:
    entities = visibility_filter(all_entities, player_id, tick)
```

`all_entities` 从哪里来？设计上有三个候选：
- **Bevy World 内存** — 正确且快速。Bevy World 反映了上次 EXECUTE FDB-committed 后的状态。
- **Dragonfly** — 异步缓存，可能落后于 FDB。会导致 snapshot 读到旧数据。
- **FDB** — 最权威但最慢。2.5s COLLECT 窗口内 500 次 FDB 读取不可行。

P0-5 §5 的可见性缓存 (`HashSet<EntityId>`) 暗示从 Bevy World 读取，但未显式声明。

**修复建议**: 在 P0-1 §2.3 中显式写出：
```
// COLLECT 始终从 in-memory Bevy World 读取
// Bevy World 反映已完成 tick 的 FDB-committed 状态
entities = visibility_filter(bevy_world, player_id, tick)
```
并添加启动时断言：`assert_eq!(bevy_world.tick_counter, last_committed_tick)`。

---

## D2 (高优先级 — Phase 1-2 修复)

### D2-1: Rhai "mini-validator" 概念未在任何规范中定义

**位置**: DESIGN.md §8.7 (Rhai API) + P0-7 §1

**问题描述**:

DESIGN.md §8.7 将 Rhai actions 描述为：
> "世界修改（通过 actions，不进命令管线但经 mini-validator）"

P0-7 §1 重复了相同的表述。但 "mini-validator" 在整个文档库中**从未被定义**：

- 它检查什么？资源余额？实体存在性？数值边界？
- 它与 P0-2 的完整 Command Validation Pipeline 的区别和边界在哪？
- 如果 mini-validator 允许一个动作但该动作与 WASM 指令冲突怎么办？
- 如果 mini-validator 拒绝了 action，Rhai 脚本如何感知？（错误码？静默丢弃？panic？）
- Rhai 的 `set_entity_flag` 没有任何 validator——白名单 flag 名在哪里定义？

**影响面**: Rhai 模组是"服主信任"的（DESIGN.md §8.7），但信任边界模糊。没有定义 mini-validator 意味着模组可以绕过所有校验写入任意值。这破坏了"惟 WASM 指令进入 Command Validation Pipeline"的架构原则。

**修复建议**: 在 P0-7 中新增一节 "Mini-Validator Specification"，定义：
1. 每个 action 的校验规则表（类比 P0-2 §3）
2. 拒绝时的错误传播机制
3. 与 WASM Command Pipeline 的执行顺序和优先级
4. `set_entity_flag` 的白名单 flag 枚举

---

### D2-2: Drone lifespan reset 无冷却 — 可被滥用建立永久 drone

**位置**: DESIGN.md §8 (Drone 生命周期)

**问题描述**:

> "续期机制: 占领新 Controller 房间时，该玩家全部 drone 的 age 重置为 0——鼓励扩张而非龟缩"

此机制存在可滥用路径：

1. 玩家 A 拥有 500 架 drone（接近 lifespan 上限，age ≈ 1400/1500）
2. 玩家 A 故意让一个弱 Controller 房间被友方玩家 B 短暂占领
3. 玩家 A 再重新占领该 Controller → 全部 drone age 重置为 0
4. 重复此循环 → drone 永不过期

或者更简单的：两个玩家合作 ping-pong 一个 Controller 房间。

**影响面**: drone_lifespan 机制形同虚设。帝国维护费（empire-upkeep）模组的设计目标是限制帝国规模，但 lifespan reset 让玩家可以无限维持最大 drone 数量。两个设计目标互相矛盾。

**修复建议**:
方案 A：占领新 Controller 时仅重置**在该房间内**的 drone 的 age（非全局），提供扩张激励但限制滥用面。
方案 B：每次 Controller 占领事件有 5000 tick 冷却（同一 Controller 不能频繁触发 reset）。
方案 C：改为 "占领新 Controller 时，每个 drone 获得 +500 tick lifespan bonus"（有上限，不可无限刷）。

---

### D2-3: EXECUTE 超时处理缺失 — 部分执行无策略

**位置**: P0-1 §3.4 + DESIGN.md §3.2

**问题描述**（R9 D2-3 遗留）:

P0-1 §3.4 描述了 FDB 事务提交失败的恢复策略，但 EXECUTE 自己超时（500ms 预算用尽）怎么办？

场景：500 玩家 × 50 指令平均 = 25,000 条指令。在 500ms 内串行 validate_and_apply。如果只处理了 20,000 条就超时了：

- FDB 事务超时 → 回滚 → 整个 tick 丢失 → 已处理指令的 CPU fuel 退还
- 如果 EXECUTE 连续 3 tick 超时 → 降级模式 → 服务中断

但 COLLECT 的超时处理是优雅的："未响应玩家 → 空指令列表"。EXECUTE 缺少对应的部分完成策略。

**修复建议**:
EXECUTE 内维护 wall-clock timer。剩余 <50ms 时：
1. 停止处理新指令
2. 待处理指令全部标记为 `RejectionReason::TickTimeout`（新 rejection reason）
3. 只 commit 已处理的指令
4. `TickTimeout` rejection 计入 TickMetrics
5. 被 timeout 的指令 fuel 全额退还

---

### D2-4: PLANNER-OUTPUT.md 包含已被 P0 规范推翻的过时内容

**位置**: PLANNER-OUTPUT.md（98行）

**问题描述**:

PLANNER-OUTPUT.md 明确标注为 "评审前草案"，但多处内容与 P0 规范矛盾：

| PLANNER-OUTPUT | P0 规范 | 矛盾 |
|---------------|---------|------|
| "SandboxExecutor trait 抽象为 PlayerExecutor，含 McpPlayerExecutor" | P0-1 §2.1 "唯一执行器：WasmSandboxExecutor" | McpPlayerExecutor 已删除 |
| "实现全部游戏动作 MCP 工具（11 个工具，镜像 Command 枚举）" | P0-3 §4.5 "MCP 不做游戏动作" | 不应存在的工具 |
| "AI 玩家需要 WASM 吗？→ 不需要，仅 MCP" | DESIGN.md §4 "AI agent 必须编写 WASM 代码来实现策略" | 相反结论 |
| "MCP 内嵌还是独立 sidecar？→ MVP 阶段内嵌" | P0-3 §2 "MCP Server ← 引擎内嵌 (Phase 1-2)" | 一致但已过时（Phase 0 后是独立服务） |

尽管文件有免责声明，但保留包含已被推翻内容的文档会造成新贡献者的混淆。文件包含的代码路径引用（/data/swarm/engine/）可能引导开发者走向错误的实现方向。

**修复建议**: 
方案 A：删除 PLANNER-OUTPUT.md（最佳——已被 P0 规范完全替代）。
方案 B：将文件改为仅包含历史参考指针（链接到 P0 规范），清除所有过时内容。

---

## D3 (低优先级 — 可延后)

### D3-1: 特殊攻击 + 伤害类型体系仅存在于 DESIGN.md，无 P0 规范

**位置**: DESIGN.md §8（特殊攻击方式 §8.7，伤害类型 §8.4.5）vs P0-8 IDL

**问题描述**:

DESIGN.md 定义了丰富的游戏机制——6 种伤害类型（Kinetic/Thermal/EMP/Sonic/Corrosive/Psionic）、6 种特殊攻击（Hack/Drain/Overload/Debilitate/Disrupt/Fortify）、抗性叠加规则（组件×属性）——但这些**均未出现在 P0-8 IDL 或任何 P0 规范中**。

P0-8 IDL 的 Attack/RangedAttack commands 没有任何 damage_type 字段，RejectionReason 枚举也没有特殊攻击相关的拒绝原因。这是 Phase 6 功能，但在 Phase 0 架构冻结时就应至少占位——否则 IDL（"单一真相来源"）与 DESIGN.md（"完整设计"）之间出现鸿沟。

**建议**: 在 P0-8 IDL 中预留 `damage_type` 字段（`default: Kinetic`）和特殊攻击 command 占位符（标注 `status: phase6`）。

---

### D3-2: Transfer/Withdraw 的 IDL `cost` 字段语义歧义

**位置**: P0-8 §2 (commands section)

**问题描述**（R9 D3-1 遗留）:

```yaml
Transfer:
    cost: { transfer_amount: amount }
Withdraw:
    cost: { withdraw_amount: amount }
```

`cost: { transfer_amount: amount }` 的语义不明：
- 解读 A：cost 是"传输的资源离开 carry"（资源流动，非额外 fee）→ `amount` 就是传输量
- 解读 B：cost 是"传输手续费 = amount 单位" + 传输的资源本身也是 amount → 双倍消耗

P0-2 §3.4 的 Transfer 校验没有提到任何额外 cost——只有 `drone.carry[resource] >= amount`。这意味着解读 A 正确。但 `transfer_amount` 的命名暗示这是 cost 的**键名**而非资源流动——名称为 `resource_consumed: amount` 或直接用 `{}`（像 Move/Harvest）会更清晰。

**建议**: 
- 如果 Transfer 没有额外手续费：`cost: {}`
- 如果有手续费待定：`cost: registry.transfer_cost()`（同 Build 模式）
- 在上述决定前至少添加注释说明当前语义

---

## Consistency Gaps (跨文档一致性)

### CG-1: Host function 列表三处不一致

**位置**: P0-4 §3.2 vs DESIGN.md §5.1 vs P0-8 IDL

| 函数 | P0-4 §3.2 | DESIGN.md §5.1 | P0-8 IDL |
|------|-----------|----------------|----------|
| `host_get_terrain` | ✅ | ✅ | ✅ |
| `host_get_objects_in_range` | ✅ | ✅ | ✅ |
| `host_path_find` | ✅ | ✅ | ✅ |
| `host_get_world_config` | ✅ | ✅ | ✅ |
| `host_get_world_rules` | ❌ 缺失 | ✅ | ✅ |

P0-4 是 WASM 沙箱的权威安全文档——它定义了什么是允许的、什么是禁止的。如果 `host_get_world_rules` 不在 P0-4 的白名单中，按照 P0-4 §2.4 的模块校验逻辑，任何导入 `host_get_world_rules` 的 WASM 模块将被拒绝为 `IllegalImport`。

**修复**: 在 P0-4 §3.2 中补充 `host_get_world_rules`。同时在 P0-8 IDL 开头添加 "本文件是 host functions + commands + validators 的权威注册表"。

---

### CG-2: TickTrace 写入失败作为独立场景的文档矛盾

**位置**: P0-1 §6.1 vs P0-1 §3.4 vs P0-1 §6.3.1

P0-1 §6.1 将 "TickTrace write fail (磁盘满)" 列为独立失败模式，与 "FDB commit fail" 分开。但：

- §6.3.1 规定 TickTrace 数据写入 FDB（`/tick/{N}/commands, /tick/{N}/state, ...`）
- §3.4 规定整个 EXECUTE 包裹在单个 FDB 事务中

→ 如果 FDB 磁盘满，**整个事务失败**（包括 TickTrace 写入）→ tick 被放弃。不存在 "tick 执行完成但 TickTrace 写入失败" 的独立场景——它们是同一个 FDB 事务的组成部分。

**修复**: 合并 "TickTrace write fail" 到 "FDB commit fail" 条目，或说明如果 TickTrace 额外写 ClickHouse 则 ClickHouse 失败是独立的。

---

## Algorithmic Risks (算法风险评估)

### AR-1: 批量 Snapshot 序列化的内存-时间乘积

**位置**: P0-1 §2.3

COLLECT 阶段需为所有活跃玩家并行生成 snapshot。假设：
- 500 玩家 × 200KB snapshot（中型世界） = 100MB 序列化数据
- serde_json 序列化速度 ~50-100MB/s → 单线程需 1-2s
- 500 次并行 WASM 调用 + 500 次 JSON 序列化 → 内存峰值可能 > 500MB（每个 snapshot 在传输给 WASM 前需在内存中）

COLLECT 的 2500ms 预算内，必须并行序列化。但文档未指定并行策略（tokio::spawn? rayon? 线程池？）。如果串行处理，仅序列化就消耗 >50% 的 COLLECT 预算。

**建议**: 在 P0-1 中明确 snapshot 构建使用并行任务池，并标注线程数和内存预算。

---

### AR-2: Tick 放弃后的延迟重试可能导致雪崩

**位置**: P0-1 §3.4 + §6.2

当 tick 因 FDB 冲突放弃：等待 1s → 重试。问题：如果 FDB 正在经历高负载（例如因为 500 玩家在同一 tick 产生大量写入冲突），1s 重试间隔意味着每隔 1s 再向 FDB 施加相同负载。连续 3 次放弃进入降级模式是正确的，但降级后没有定义如何退出——"连续 10 tick 正常"的恢复条件在降级负载下可能永远达不到。

**建议**: 放弃后使用指数退避（1s → 2s → 4s），给 FDB 恢复窗口。

---

## Strengths (设计亮点 — 不应改动)

1. **Deferred Command Model 一致性**: DESIGN.md + P0-2 + P0-4 三处对 "WASM → tick() → JSON → 引擎校验执行" 的约束完全一致。没有一个 mutating host function 的例外。

2. **MCP 不作为游戏控制器**: P0-3 §4.5 明确定义 MCP 不包含任何游戏动作工具——AI 必须写 WASM。与人类完全同权。架构公平性无懈可击。

3. **Fuel Refund 防滥用三层防护**: 退还时序（下 tick 生效）+ Deploy-reset 绑定（模块变更作废）+ 同源重复不退——堵住了所有退款循环利用路径。P0-2 §7.2 的 "Deploy-reset 规则" 是新增内容（R9 时期不存在），设计精妙。

4. **Blake3 统一原语**: 哈希/PRNG/代码签名统一为 Blake3，依赖栈减 30%，审计面减半。

5. **三层信任模型清晰**: WASM(不可信, 进程隔离) → Rhai(服主信任, AST 解释) → Rust(不可变, 引擎核心)。权限边界无歧义。

6. **P0-8 IDL 作为单一真相来源**: 一个 YAML → 生成 Rust/TS/MCP schema/文档/test。`git diff --exit-code` 强制一致性。这是真正的 "design by contract"。

7. **P0-9 Command Source Model 完整**: 12 来源 × 完整能力矩阵，auth context 服务端注入不可伪造。Source Gate 在 Command Validation Pipeline 之前过滤——防御纵深正确。

---

## 总结

| 类别 | 本轮 | 累计(R9未修复+本轮新) |
|------|------|---------------------|
| D1 阻断 | 3 (1 新 + 2 R9遗留) | 5 需要解决 |
| D2 高优 | 4 (3 新 + 1 R9遗留) | 7 需要解决 |
| D3 低优 | 2 (1 新 + 1 R9遗留) | 4 可延后 |
| 一致性缺口 | 2 (1 新 + 1 R9遗留) | 3 文档修整 |
| 算法风险 | 2 (新) | 4 监控+优化 |

**Phase 1 可开始的最低条件**:
1. D1-1 (Source.produces → IndexMap) — 全量 HashMap 审计完成
2. D1-2 (Wasmtime 版本策略) — 架构决策做出，P0-4 补充"回放兼容性策略"节
3. D1-3 (COLLECT 读取源) — P0-1 §2.3 显式声明数据来源
4. D2-1 (Rhai mini-validator) — P0-7 补充完整规范
5. CG-1 (host function 列表统一) — P0-4 补充 host_get_world_rules

满足以上 5 项后，架构从 REQUEST_MAJOR_CHANGES 升级为 APPROVE_WITH_RESERVATIONS。

---

*评审完成于 2026-06-14 | DeepSeek V4 Pro | rev-dsv4-architect profile*
