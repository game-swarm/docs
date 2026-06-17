# R7 Architect Review — rev-dsv4-architect (DeepSeek V4 Pro)

## 总体 Verdict

**CONDITIONAL_APPROVE** — 设计质量在 R6 基础上进一步提升，Tier Entry Gate 矩阵和统一预算模型填补了此前关键空白。发现 6 个 Findings（1 High / 2 Medium / 3 Low），3 处跨文档一致性缺口，2 项算法风险关注点。所有问题均为非阻塞级，可在 Phase 1 实现前修正。

相较于 R6，本轮新增的 **Tier Entry Gate 矩阵**（engine.md §3.2）、**统一 Tick 资源预算模型**（01-tick-protocol §8）、**Recycle lifespan 比例退还**（02-command-validation §3.18）、**Controller 续期硬上限公式**（gameplay.md §8.2）、**Seed 前向保密威胁模型**（01-tick-protocol §3.1）均是我在 R6 中指出的缺口，现已充分闭合。

---

## 亮点 (Strengths)

1. **Tier Entry Gate 矩阵**（engine.md §3.2）— 精确冻结了每个扩展层级的 feature flag 划分，`future-disabled` 机制从编译期排除未实现功能，彻底解决了此前"MVP 被未来 spec 污染"的风险。

2. **统一 Tick 资源预算模型**（01-tick-protocol §8）— 将分散在 core/04、security/09 的预算定义收束为单一真相来源，包含 COLLECT 缓存复用语义、Simulate 独立配额池、禁止跨重试 fuel 追加。

3. **Snapshot 两阶段架构优化**（engine.md §3.2）— 从每玩家独立序列化改为一次性快照 + 房间分片 + 按玩家拼接，复杂度从 O(P×E) 降至 O(E + P×R)，在 MVP 规模下消除冗余序列化开销。

4. **Phase 2a/2b 分类原则清晰**（engine.md §3.2）— Inline（玩家命令串行竞争）vs Deferred（被动系统串行/并行调度）的边界明确，Component 读写矩阵证明并行安全性。

5. **可见性 Oracle 防线**（05-visibility §10）— 跨接口信息泄露闭合做得极其系统：`omitted_count` 分桶、特殊攻击拒绝码等价策略、`player_view=full` + `fog_of_war=true` 禁止组合、MCP simulate/dry_run 脱敏。

6. **Seed 前向保密威胁模型**（01-tick-protocol §3.1）— 正式分析 seed 泄露影响面（Critical/3项），提供轮换+epoch bump 缓解措施，明确接受"不实现密码学完善前向保密"的设计决策并给出理由。

7. **Recycle lifespan 比例退还**（02-command-validation §3.18）— 从固定 50% 修改为 `max(0.1, 0.5 × remaining/total)`，闭合了"末期回收套利"的经济漏洞。

8. **COLLECT 跨重试缓存**（01-tick-protocol §3.5/§8.4）— FDB commit 失败重试时复用 COLLECT 结果，禁止 WASM 重执行，确保跨重试 fuel ≤ 1×MAX_FUEL。此设计直接回应了我 R6 中关于"FDB rollback 后是否重复扣费"的质疑。

---

## Findings (按严重度排序)

### HIGH — 1 项

**F1 — `omitted_count` 跨文档未同步（Oracle 防线缺口）**

| 项目 | 内容 |
|------|------|
| **位置** | specs/core/01-tick-protocol §2.3（第 147 行） vs specs/security/05-visibility §10.2（第 376-390 行） |
| **问题** | 05-visibility §10.2 已将 `omitted_count` 从精确整数改为分桶值（`0 / "few" / "some" / "many" / "extreme"`），以防止攻击者通过观察截断数量推断隐藏实体信息（oracle 攻击）。但 01-tick-protocol §2.3 的 `build_snapshot()` 仍返回 `omitted_count: total_visible - visible_in_snapshot`（精确整数）。两者矛盾——一个说分桶，一个说精确值。 |
| **影响** | 若按 01-tick-protocol 实现，`omitted_count` 将暴露精确的隐藏实体数量，形成 oracle 信道——攻击者可通过反复操控视野观察 `omitted_count` 变化来推断敌方部署规模。05-visibility 精心设计的 Oracle 防线将被此实现细节绕过。 |
| **修正建议** | 将 01-tick-protocol §2.3 的 `build_snapshot()` 中的 `omitted_count` 类型从 `u32` 改为枚举 `TruncationLevel`，枚举值与 05-visibility §10.2 的分桶表保持一致。同步更新 `total_visible_count` 分桶。 |

---

### MEDIUM — 2 项

**F2 — 多房间玩家的截断距离度量未定义（确定性缺口）**

| 项目 | 内容 |
|------|------|
| **位置** | specs/core/01-tick-protocol §2.3（第 156-157 行） |
| **问题** | 截断排序键使用 `(distance_to_drone, entity_id)`。文档说「距离以 drone 当前位置到实体的曼哈顿距离计算」。但当同一玩家在**不同房间**拥有多个 drone 时，文档未规定使用哪个 drone 的位置。两个合理的候选：(a) 离目标实体最近的 drone；(b) 该玩家在目标实体所在房间的 drone。两者在不同场景下产生不同的排序结果——关乎确定性。 |
| **影响** | 若两个实现在此分歧——一个选最近 drone，一个选同房间 drone——同一输入将产生不同的截断结果，破坏 replay determinism。 |
| **修正建议** | 明确定义：「距离 = 目标实体到该玩家在目标实体**同一房间**内最近的 drone 的曼哈顿距离。若目标实体所在房间无玩家 drone，则距离 = ∞（归入低优先桶）。」此定义保证距离计算与可见房间范围一致（默认 ≤9 房间）。

---

**F3 — Controller `repair_per_drone` 与硬上限公式的语义冲突**

| 项目 | 内容 |
|------|------|
| **位置** | design/engine.md §3.1（第 69 行，Controller 结构体） vs design/gameplay.md §8.2（第 77 行，Controller 续期硬上限） |
| **问题** | Controller 结构体定义了 `repair_per_drone: u32`（每 drone 回退的 age 量），同时 gameplay.md 定义了硬上限公式 `max(0, age + 1 - min(0.5, controller_count × 0.5))`。这两个值的关系不明确：(a) 硬上限公式中的 0.5 是 total cap，`repair_per_drone` 是每次的实际减少量——但 0.5 的 total cap 小于 1.0，意味着 `repair_per_drone` 只能取 0 或 1？(b) 如果 Controller RCL 的 `repair_capacity` 允许多个 drone 同时维修，硬上限是 per-drone 还是 global total？字段名 `repair_per_drone` 暗示 per-drone，但硬上限描述「每 tick 总 age 回退」暗示 global。 |
| **影响** | 实现者可能将硬上限理解为 per-drone（每个 drone 降 age 不超过 0.5），而不是 global（所有 drone 降 age 总合不超过 0.5）。两者差一个数量级（单 drone × N vs 全 room 总合）。 |
| **修正建议** | 统一表述：硬上限是 **per-drone per-tick**，即单个 drone 在单个 Controller 维修下 age 降幅上限为 `min(repair_per_drone, 0.5)`。总 age 降幅 = min(repair_capacity × repair_per_drone, 0.5 × repair_capacity)。此公式与 RCL 表中「维修容量」字段语义一致（容量限制服务 drone 数，硬上限限制每 drone 降幅）。或者：直接移除 `repair_per_drone` 字段，改为硬上限 = 0.5 per drone（简单且无歧义）。

---

### LOW — 3 项

**F4 — Tick 目标间隔 (3s) vs 硬截止 (4s) 的漂移累积语义未定义**

| 项目 | 内容 |
|------|------|
| **位置** | specs/core/01-tick-protocol §8.1 |
| **问题** | tick_interval_ms=3000 是目标值，hard_deadline=4000ms。若某 tick 因 COLLECT 超时而实际耗用 3500ms，下一 tick 应从 3500ms 之后立即开始（无漂移补偿），还是应该在 4000ms（= 目标间隔的 3000ms 后）开始？文档未定义漂移策略。 |
| **影响** | 若选"立即开始"，负载高峰后的 tick 累积无补偿，世界时间与墙钟时间漂移——Arena 比赛时长不可预测。若选"保持间隔"，单个慢 tick 不会累积，但硬截止 4000ms 意味着间隔 + 500ms 的 slack（3000ms 间隔 + 1000ms 缓冲 = 4000ms 硬截止）。需明确定义。 |
| **修正建议** | 增加 `tick_drift_policy` 字段：`"compensate"`（保持间隔——每个 tick 的 start_time = previous_start + tick_interval_ms）或 `"immediate"`（无补偿——连续执行）。默认 `"compensate"`（Arena 必须使用此模式以保证比赛时长可预测）。硬截止语义：若 `now >= start_time + hard_deadline` → tick 放弃。 |

**F5 — Exempting Transfer from main-action quota enables intra-tick resource teleport chains**

| 项目 | 内容 |
|------|------|
| **位置** | specs/core/02-command-validation §3.3（规则 3） |
| **问题** | Transfer/Withdraw 不计入 per-drone per-tick action quota（每 tick 最多 1 个 main action）。这在逻辑上合理——Transfer 是物流操作，不应与 Move/Attack 竞争。但 Transfer 无 per-tick 次数上限（仅受 carry capacity 约束），允许同 tick 内 drone A→B→C 的链式 Transfer。若 A/B/C 排列在同一条指令队列中（同一玩家），资源可在一个 tick 内从 A 房间瞬间传输到 C 房间——绕过 `transfer_to_global_time` 的物流延迟设计。 |
| **影响** | 绕过了物流系统的时间成本约束。实际上 Transfer 的 range=1 限制（drone 必须在目标 1 格内）提供了物理约束——链式 Transfer 需要所有 drone 物理相邻。但若玩家精心排列 drone（例如在一条线上排开），仍可实现跨房间的瞬移式资源传输。注意：Transfer chain 本身消耗多个 drone 的 action（每 drone 只能 Transfer 一次吗？）。不对——Transfer 不计入 main action 配额，所以一个 drone 可以做多次 Transfer。 |
| **修正建议** | 增加 Transfer 的 per-drone per-tick 上限 = `carry_capacity / avg_transfer_size`（例如 10 次）。或者：Transfer 计入 per-drone per-tick 的 secondary action quota（独立于 main action quota）。文档应明确 Transfer chain 是设计意图还是疏忽，并给出物流成本约束。 |

**F6 — RCL 房间 drone 上限未映射到 Controller 结构体**

| 项目 | 内容 |
|------|------|
| **位置** | design/engine.md §3.1（Controller 结构体 + RCL 表） |
| **问题** | RCL 表中「最大房间 drone」列定义了每 RCL 等级的房间 drone 数量上限（RCL1=50, RCL8=500），但 Controller 结构体中没有对应字段。结构体字段 `repair_capacity` 是维修容量（drone/ tick），不是 drone 上限。实现者需从 RCL 表反向查找上限值，而非直接从结构体读取。 |
| **影响** | 结构体定义与规则定义之间存在间接映射——容易在实现中遗漏或使用错误字段。 |
| **修正建议** | 在 Controller 结构体中增加 `room_drone_cap: u32` 字段，由 RCL 表派生填充。或者将 RCL 表的「最大房间 drone」列名改为与结构体字段匹配的标识符。 |

---

## 跨文档一致性缺口 (Consistency Gaps)

### CG1 — `omitted_count` 类型冲突（见 F1）

01-tick-protocol §2.3（精确 u32） ↔ 05-visibility §10.2（分桶枚举）。修正：统一为分桶枚举。

### CG2 — 截断桶划分在 core spec 与 visibility spec 中独立定义且存在差异

| 位置 | 桶定义 |
|------|--------|
| 01-tick-protocol §2.3 | 四个桶：关键/高优先/中优先/低优先。排序键 `(distance_to_drone, entity_id)` |
| 05-visibility §10.2 | 五个桶（用于 omitted_count 分桶）：0/few(1-10)/some(11-50)/many(51-200)/extreme(>200) |

这两个桶体系服务于不同目的（截断排序 vs 计数脱敏），各自定义合理。但两者共享 "truncation" 命名空间——新读者可能混淆。建议在 01-tick-protocol §2.3 中明确区分「排序桶 (sorting bucket)」和「计数桶 (count bucket)」，并交叉引用 05-visibility §10.2。

### CG3 — Controller repair 硬上限在两处文档中的公式不同

| 位置 | 公式 |
|------|------|
| design/engine.md §3.1（Controller 结构体注释） | `repair_per_drone: u32` — 无上限公式 |
| design/gameplay.md §8.2 | `max(0, age + 1 - min(0.5, controller_count × 0.5))` |

engine.md 的 Controller 结构体定义中引用了「硬上限规则详见 §8.2」但未重复公式本身。结构体注释应包含简版公式或至少明确 `repair_per_drone` 的最大有效值（0.5 per controller）。

---

## 算法风险关注点 (Algorithmic Risks)

### AR1 — Modification-Set 增量快照的 FDB 映射未定义

**位置**: specs/future/T2-incremental-snapshot.md §6

Tier 2 增量快照规范在「待定项」中声明 `modification-set 如何映射到 FDB 的 atomic mutation——需与 FDB 事务模型对齐`。这是一个架构级风险：Tier 1 的全量快照可以通过 `txn.set("/tick/{N}/state", full_snapshot)` 简单映射为 FDB key-value。Tier 2 的增量格式（added/removed/modified entities + resource changes）需要在 FDB 事务中表达「原子应用一组 mutation」——FDB 原生不支持这种批量的条件更新。候选方案（如 snapshot chain + validation）将影响 FDB 的 key schema 设计和事务边界。

**建议**: 在 Tier 2 spec 冻结前，先编写 prototype 验证 modification-set → FDB mutation 的可行性（特别是跨多个 key 的条件更新原子性）。

### AR2 — Cross-Shard Combat 两阶段协议的时间预算

**位置**: specs/future/T3-shard-protocol.md §4

Tier 3 的跨分片 combat 两阶段协议（意图广播 → 结算确认）在当前设计中跨越一个 tick 边界（"延迟: 1 tick"）。在 Tier 1 的 3000ms tick 间隔下，1 tick 延迟对目标意味着受伤后 3 秒才能看到 HP 更新——这在交互性上可接受。但在 Arena 的 300ms tick 间隔下，1 tick = 300ms，仍可接受。但两阶段协议的网络延迟（shard A → FDB/NATS → shard B → 结算 → 返回 → shard A）需要严格的时间预算。若总延迟接近或超过 tick_interval，将产生级联延迟。

**建议**: 在 T3 spec 中增加时间预算分析：Phase 1 广播 deadline、Phase 2 确认 deadline、超时回退策略。如果 Phase 2 确认超时，是放弃该 combat（attacker 退费）还是强制结算（基于 shard B 的当前状态）？当前 spec 未定义超时语义。

---

## 审查范围

审阅了以下 20 份文档（完整阅读，非抽样）：

**设计域** (6): design/README.md, design/engine.md, design/gameplay.md, design/modes.md, design/interface.md, design/tech-choices.md

**技术规范** (14): specs/core/01-tick-protocol.md, specs/core/02-command-validation.md, specs/core/04-wasm-sandbox.md, specs/core/07-world-rules.md, specs/security/03-mcp-security.md, specs/security/05-visibility.md, specs/security/09-command-source.md, specs/security/CVE-SLA.md, specs/gameplay/06-feedback-loop.md, specs/gameplay/08-api-idl.md, specs/future/T2-incremental-snapshot.md, specs/future/T3-shard-protocol.md, specs/12-gateway-protocol.md, specs/reference/*（参考浏览）

---

*审查时间: 2026-06-17 | 审查者: rev-dsv4-architect (DeepSeek V4 Pro)*
