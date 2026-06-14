# R4 架构评审 — DeepSeek V4 Pro (Architect)

**评审者**: rev-dsv4-architect (DeepSeek V4 Pro)
**回合**: Round 4 — Phase 0 Freeze Gate 终审
**日期**: 2026-06-14
**范围**: DESIGN.md (全 1339 行) + P0 规范 1-9 (全量) + R3 Speaker Verdict 对照

---

## 一、Verdict: CONDITIONAL_APPROVE

Phase 0 架构已具备冻结条件。6 项 R3 Freeze Blocker 中 4 项完全闭合，2 项存在残留冲突需修正后冻结。所有残留问题均为 **spec text cleanup**，不影响架构决策本身，不涉及重设计。

冻结建议：闭合 D1 和 D2 后立即宣布 Phase 0 Frozen，剩余项 D3-D5 可在 Phase 1 实现过程中消灭。

---

## 二、R3 Freeze Blocker 逐项闭合审计

### FB-1: Rhai f64 确定性闭合 → ⚠️ PARTIAL

| 检查点 | 状态 | 证据 |
|--------|------|------|
| Determinism Contract 声明 fixed-point-only | ✅ | DESIGN §8.8: "Rhai 模组脚本同样禁用浮点——所有模组参数必须声明为 u32/i64/fixed<u32,N> 定点类型，Rhai 引擎侧关闭浮点运算能力" |
| mod.toml 参数类型声明 | ✅ | DESIGN §8.7: `type = "fixed<u32,4>"` for room_superlinear |
| P0-7 config schema | ✅ | P0-7 §2: `room_superlinear = 2  # fixed<u32,4>: 0.0002` |
| tick_end.rhai 使用 FIXED_SCALE | ✅ | DESIGN §8.7: `config.room_superlinear / FIXED_SCALE` |
| **i18n 示例使用 f64** | ❌ | DESIGN §8.8 L1072-1076: `[config.room_superlinear]\ntype = \"f64\"\ndefault = 0.1` |
| 跨平台 CI 验证 | ❌ | 未在任何 spec 中找到 CI 验证计划（仅口头声明） |

**判定**: i18n 示例与 Determinism Contract 自相矛盾。**不是文字遗漏——是功能冲突**：如果模组参数声明为 f64，引擎侧关闭浮点的 Rhai 将无法处理。需将 i18n 示例统一为 `fixed<u32,4>`。

### FB-2: 全局存储反制 → ✅ CLOSED

三项内置反制全部实现：

| 反制机制 | 实现 |
|---------|------|
| 累进存储税 (Progressive Tax) | DESIGN §8 (Anti-Dominant-Strategy), `global_storage_tax_tiers` 四级累进税率表 |
| 本地存储隐匿性 (Stealth) | DESIGN §8: 全局部分公开/排行榜区间，本地完全私有 |
| 运输时间 (No Teleport) | DESIGN §8: `transfer_to_global_time=10 tick`, `transfer_from_global_time=5 tick`，运输期间可被拦截 |
| IDL 覆盖 | P0-8: TransferToGlobal / TransferFromGlobal commands with duration + cost |
| Source Gate 覆盖 | P0-9: WASM source 可读写全局存储 |

超出 R3 需求——实现了全部三项而非至少一项。

### FB-3: Fuel Refund 安全化 → ✅ CLOSED

| 检查点 | 状态 | 证据 |
|--------|------|------|
| 退还时序 (tick 间) | ✅ | P0-2 §7.2: "退还的 fuel 仅作用于下一 tick 的 fuel budget" |
| 退还上限 (绝对值+比例) | ✅ | P0-2 §7.3: 每人每 tick 上限 = MAX_FUEL × 10%, 同源重复仅首次退 50% |
| 滥用检测 (throttle) | ✅ | P0-2 §7.3: 连续 3 tick 退还率 > 80% → fuel budget 降为 0.5× |
| 监控指标 | ✅ | P0-2 §7.4: refund_abuse_rate, source_empty_refund_pct, consecutive_high_refund_ticks |

Anti-Amplification 设计完备：N tick 失败 → N+1 tick 可用增加（上限 1.1×）+ 同 tick 内不放大。无绕过路径。

### FB-4: IDL 补全与统一 → ⚠️ CLOSED with Inconsistency

| 检查点 | 状态 | 证据 |
|--------|------|------|
| Host function 签名完整 | ✅ | P0-8: tick, get_world_config, get_world_rules, get_terrain, get_objects_in_range, path_find |
| Query 类 host functions 新增 | ✅ | get_terrain, get_objects_in_range, path_find, get_world_config, get_world_rules |
| Auth context 注入统一 | ✅ | P0-9 §3: 服务端注入 player_id/session_id/module_version/tick，客户端不可自报 |
| RawCommand 入口统一 | ✅ | P0-2 §2: RawCommand 含 player_id/tick/sequence/action |
| IDL 为权威来源 | ✅ | P0-8 §1: "单一真相来源"; §4: "git diff --exit-code" 强制生成代码与 IDL 一致 |
| **DESIGN §5 与 P0-4 §3 不一致** | ❌ | 见下 Deep Dive D1 |
| **P0-4 §8 自相矛盾** | ❌ | 见下 Deep Dive D2 |

### FB-5: Tick 输出 Schema 校验 → ✅ CLOSED

| 检查点 | 状态 | 证据 |
|--------|------|------|
| JSON schema 定义 | ✅ | P0-2 §1.1: type=array, maxItems=100, ≤256KB, depth≤10, additionalProperties: false |
| 校验失败处理 | ✅ | P0-2 §1.1: 整个 tick 输出丢弃，不计入 refund，记录为 TickValidationFailed |
| 体积限制 | ✅ | P0-4 §6: 输出 JSON 体积 256 KB 硬限 |

### FB-6: Imperative vs Deferred 统一 → ⚠️ PARTIAL

| 检查点 | 状态 | 证据 |
|--------|------|------|
| P0-4 §3: Deferred model 明确 | ✅ | tick() 接收 snapshot JSON，返回 command JSON，禁止 mutating host functions |
| P0-4 §3.3: 禁止列表 | ✅ | host_move, host_harvest, host_transfer, host_build, host_attack, host_heal 明确禁止 |
| DESIGN §8.5: Deferred 示例 | ✅ | TypeScript tick(snapshot) → Command[] 完整示例 |
| **DESIGN §5 未清理** | ❌ | 仍列举 14 个 imperative host functions 含所有 mutating 操作 |
| **P0-4 §8 与 §3.3 矛盾** | ❌ | 成本表包含被 §3.3 禁止的函数 |

### Gap-1: P0-9 Source Gate 完整矩阵 → ✅ CLOSED

| 检查点 | 状态 |
|--------|------|
| 核心来源 7 个 + 扩展来源 6 个 (含 Deploy/Rollback/RuleMod/Simulate/DryRun) | ✅ |
| 能力矩阵 12 × 6 (写入世界/读写全局存储/部署代码/查询世界/触发战斗/审计) | ✅ |
| Tutorial 隔离约束 (独立 namespace, 仅 tutorial 世界) | ✅ |
| World/Arena 差异矩阵 | ✅ |

---

## 三、Deep Dive: Deferred Model 一致性缺口 (CRITICAL)

### D1 [CRITICAL]: DESIGN §5 与 Deferred Model 冲突

**位置**: `/data/swarm/docs/design/DESIGN.md`, L292-317

DESIGN §5 标题为 "游戏 API（WASM Host Function）"，列举了 14 个函数：

```
移动类: host_move, host_move_to
资源类: host_harvest, host_transfer, host_withdraw
建造类: host_build, host_repair
战斗类: host_attack, host_ranged_attack, host_heal
孵化类: host_spawn, host_recycle
查询类: host_get_terrain, host_get_objects_in_range, host_path_find
```

**但 P0-4 §3.3 明确声明**：

> 以下函数**不得作为 host function 暴露给 WASM**：host_move → 改为 JSON 指令, host_harvest → 改为 JSON 指令, host_transfer → 改为 JSON 指令, host_build → 改为 JSON 指令, host_attack → 改为 JSON 指令, host_heal → 改为 JSON 指令

这是 **R3 FB-6 闭合不彻底** 的残留。DESIGN §5 是开发者（人类和 AI）阅读 DESIGN.md 时首先接触的 host function 列表。如果它仍然描述 imperative model，将导致严重误导。

**影响**: 任何开发者在实现时若以 DESIGN §5 为准（而非 P0-4 §3.3），将在 WASM 中暴露 mutating host functions，直接破坏 deferred model 的安全性和确定性。

**修复建议**:
```
方案 A: 将 DESIGN §5 重写为 "WASM 只读查询 Host Function"，仅保留 get_terrain/get_objects_in_range/path_find/get_world_config/get_world_rules，并添加交叉引用指向 P0-4 §3 deferred model。
方案 B: 删除 DESIGN §5 现有内容，替换为 deferred model 说明 + 引用 P0-4 §3 和 P0-8 IDL。
推荐方案 A——保留 DESIGN 自足性，同时不重复 deferred model 细节。
```

### D2 [CRITICAL]: P0-4 §8 成本表与 §3.3 禁止列表自相矛盾

**位置**: `/data/swarm/docs/specs/p0/04-wasm-sandbox-baseline.md`, L277-294

P0-4 §8 "Host Function 单次调用成本表" 包含了所有被 §3.3 禁止的函数：

| 函数 | §3.3 状态 | §8 成本 |
|------|----------|---------|
| host_move | ❌ 禁止 | 1,000 fuel |
| host_harvest | ❌ 禁止 | 5,000 fuel |
| host_transfer | ❌ 禁止 | 5,000 fuel |
| host_build | ❌ 禁止 | 10,000 fuel |
| host_repair | ❌ 禁止 | 10,000 fuel |
| host_attack | ❌ 禁止 | 5,000 fuel |
| host_heal | ❌ 禁止 | 5,000 fuel |
| host_spawn | ❌ 禁止 | 20,000 fuel |
| host_recycle | ❌ 禁止 | 5,000 fuel |

**同一文件内 §3.3 说 "不得暴露" 而 §8 给出精确的 fuel 成本——这意味着 §8 仍然为 imperative model 的保留可能性留下后门。**

**修复**: 删除 P0-4 §8 中被禁止的 9 个函数行。成本表仅保留 4 个合法的只读查询函数。

---

## 四、Deferred Model 一致性全链路检查

| 文档 | 章节 | 模型 | 一致性 |
|------|------|------|--------|
| DESIGN | §3.2 Tick 生命周期 | instruction-collect → validate → apply | ✅ 隐含 deferred |
| DESIGN | §5 游戏 API | **Imperative** (14 host functions) | ❌ D1 |
| DESIGN | §8.5 WASM 侧感知 | Deferred (tick(snapshot) → Command[]) | ✅ |
| P0-1 | §2.1 玩家执行模型 | WasmSandboxExecutor 唯一执行器 | ✅ |
| P0-2 | §1 指令管线 | tick() JSON → validate → apply | ✅ |
| P0-4 | §3.1 模块导出 | tick(ptr, len) → i32 (command JSON ptr) | ✅ |
| P0-4 | §3.2 允许的 Host Function | 仅只读查询 | ✅ |
| P0-4 | §3.3 禁止的 Host Function | 所有 mutating 操作禁止 | ✅ |
| P0-4 | §8 成本表 | **Imperative** (含被禁函数) | ❌ D2 |
| P0-8 | host_functions section | 仅 tick + 5 个查询函数 | ✅ |
| P0-9 | Command Source Model | WASM source → gameplay = yes, Deploy source → gameplay = no | ✅ |

**结论**: 7/10 交界面一致，2 处冲突 (DESIGN §5, P0-4 §8) 均与 deferred model 矛盾，1 处 (DESIGN §3.2) 为中性描述。

---

## 五、IDL 完整性评审 (P0-8)

### 已覆盖 ✅

| 类别 | 条目 | 验证 |
|------|------|------|
| Types | PlayerId, RoomId, ObjectId, Tick, ResourceName, ResourceAmount, ResourceCost, Position | 8/8 |
| Enums | Direction (6), BodyPart (8), StructureType (12), RejectionReason (27 variants) | 完整 |
| Commands | Move, MoveTo, Harvest, Transfer, Withdraw, Build, Repair, Attack, RangedAttack, Heal, Spawn, Recycle | 12/12, 均含 validator + cost |
| Host functions | tick, get_world_config, get_world_rules, get_terrain, get_objects_in_range, path_find | 6/6 |
| Global Storage | TransferToGlobal, TransferFromGlobal | ✅ |
| Refund Policy | contention_lost=0.5, self_invalid=0.0 | ✅ |
| Codegen targets | Rust enum+stubs, TS types, MCP schemas, TickTrace, Docs | 5/5 |
| CI guard | `git diff --exit-code` | ✅ |

### 遗漏 ⚠️

| 项目 | 严重度 | 说明 |
|------|--------|------|
| **Snapshot schema** | Medium | tick() 输入 JSON 的 schema 未在 IDL 中定义。P0-1 §2.3 和 P0-5 §3.1 各自描述了 snapshot 结构但无统一 schema。这导致：Rust side 的序列化格式与 WASM SDK 的解析格式可能漂移。建议 IDL 新增 `snapshot` section。 |
| **TickTrace schema** | Medium | P0-8 §3 提及 "TickTrace schema — 冻结于 Phase 0；格式变更需递增 ABI 版本" 但 IDL 本身未包含 TickTrace 的结构定义。TickTrace 是回放的输入格式，必须与 Command 一样冻结。 |
| **ABI version bump rules** | Low | IDL 声明 `abi_version: 1` 和 "每次 host function 签名变更时递增"，但未定义什么算 "签名变更"：只算参数类型变化？还是连参数名变化也算？新增 host function 是否递增？ |

### IDL 跨文件一致性

| IDL 声明 | P0-2 | P0-4 | DESIGN | 一致性 |
|----------|------|------|--------|--------|
| Move.validator: [exists, owner, drone, fatigue, body_part(Move), passable, !spawning] | P0-2 §3.1: 8 项检查 | — | — | ✅ P0-2 更详细 (含 direction, body part 细节) |
| Harvest.validator: [body_part(Work,Carry), carry_space, is_source, source_not_empty, in_range(1)] | P0-2 §3.3: 9 项检查 | — | — | ✅ |
| Spawn.validator: [is_spawn, cooldown_zero, body_size(50)] | P0-2 §3.10: 6 项检查 | — | — | ⚠️ P0-2 有 "ExceedsRoomCapacity" 和 "RoomDroneCapReached" 两项额外的限制未在 IDL 的 validator 简写中列出 |
| RejectionReason enum | P0-2 §3 all checks 匹配 | — | — | ✅ 27 variants all accounted for |

IDL 的 validator 字段是简写表达（用于代码生成），P0-2 的检查矩阵是完整版——这是一个合理的设计：IDL 声明意图，P0-2 定义实现。但 Spawn 的简写缺少两个 room-level 检查项，建议补齐或添加注释说明 "IDL validator 字段为最小集合，完整检查见 P0-2 §3.10"。

---

## 六、Determinism Contract 完备性评审 (DESIGN §8.8)

### 已覆盖 ✅

| 组件 | 决策 | 评估 |
|------|------|------|
| PRNG | ChaCha12 (密码学安全 + 确定种子) | ✅ 优于 ChaCha8，抗 related-key |
| 种子 | world_seed = Blake3(32 random bytes), hex 编码 | ✅ 256-bit 熵足够，hex 编码避免二进制传输问题 |
| Hash | Blake3 (fixed impl, 不用 std::hash/SipHash) | ✅ 跨版本稳定，速度优于 SHA-256 |
| 种子洗牌 | Blake3(tick_number \|\| world_seed) | ✅ 确定性 + 不可预测 + 公平轮换 |
| ECS 顺序 | .chain() 严格串行 | ✅ 初版正确，后续可优化为 before/after graph |
| 数值类型 | 整数 + 定点数 (i64 × 精度因子)，禁 f64 | ✅ 跨平台确定性 |
| Rhai 数值 | 禁浮点，仅 u32/i64/fixed<u32,N> | ✅ (但 i18n 示例冲突，见 D3) |
| 排序 key | (shuffle_order, player_id, cmd_seq) | ✅ 三方稳定排序 |
| HashMap | IndexMap (不用 std::HashMap) | ✅ 迭代顺序确定 |
| 回放保证 | tick N-1 state + N RawCommands + seed → execute_deterministic == recorded_state | ✅ |
| State checksum | 每 tick 写入 TickTrace | ✅ |
| CI replay | 随机采样 tick 做 full replay 验证 | ✅ |

### 遗漏与模糊 ⚠️

#### D3 [HIGH]: i18n 示例使用 f64

DESIGN §8.8 L1072-1076:
```toml
[config.room_superlinear]
type = "f64"
default = 0.1
```

与同节 L1196-1197 的 Determinism Contract 声明直接矛盾：
> "Rhai 模组脚本同样禁用浮点——所有模组参数必须声明为 u32/i64/fixed<u32,N> 定点类型"

**修复**: 将 i18n 示例改为 `type = "fixed<u32,4>"`, `default = 1000` (表示 0.1000)。

#### D4 [MEDIUM]: P0-4 §3.2 缺少 host_get_world_rules

P0-4 §3.2 "允许的 Host Function" 列表:
```rust
fn host_get_terrain(...)
fn host_get_objects_in_range(...)
fn host_path_find(...)
fn host_get_world_config(...)
```

但 IDL P0-8 包含 5 个查询函数，多了 `get_world_rules`:
```yaml
host_functions:
  get_world_config: ...
  get_world_rules: ...       ← P0-4 遗漏
  get_terrain: ...
  get_objects_in_range: ...
  path_find: ...
```

**修复**: P0-4 §3.2 添加 `host_get_world_rules` 并标注调用限制（若有）。

#### D5 [LOW]: 模组依赖 semver 约束未定义 (R3 C-6)

mod.toml 声明 `dependencies = []` 但没有定义依赖 version 语法。Phase 1+ 模组市场启用后需要：

```toml
# 建议格式
dependencies = [
    { name = "resource-decay", version = ">=0.3.0, <1.0.0" },
]
```

#### D6 [LOW]: WASM 编译确定性未约定

Determinism Contract 声明 replay 需要 "相同 Wasmtime pinned 版本"，但未约定 WASM 二进制本身的确定性。同一源码用不同版本的 Rust toolchain 编译可能产生不同 WASM 二进制，影响 replay 的 hash 验证。

建议: replay 记录中存储 WASM 模块的 Blake3 hash，replay 时用完全相同的 WASM 二进制（从 FDB `/player/{id}/modules/` 读取历史版本），而非重新编译源码。

#### D7 [LOW]: Rhai 版本对确定性影响未约定

如果模组使用 Rhai 脚本，Rhai AST 解释器的版本变更可能改变脚本行为。Determinism Contract 应补充 "Rhai 版本固定（`rhai = "=1.x"`），升级需递增 world ABI version"。

---

## 七、数据一致性深度分析

### 7.1 FDB → Dragonfly → NATS 写入顺序

```
EXECUTE: FDB txn.commit()         [原子持久化]
    ↓
BROADCAST:
  dragonfly.update(delta)         [缓存更新，允许失败后从 FDB 重建]
  nats.publish("tick.{tick}", delta)  [消息发布，允许失败后客户端 pull]
```

**分析**: 持久化先于缓存先于消息——正确的 durability 顺序。FDB 为唯一权威源，Dragonfly 和 NATS 为尽力交付的缓存/通知层。NATS 失败时客户端通过 polling fallback 检测 gap，不会丢失 tick 数据。

**边缘情况验证**:
- Dragonfly 更新成功，NATS publish 失败：P0-1 §6 规定客户端 5s 未收到 delta → 主动 pull。✅
- FDB commit 成功，Dragonfly 更新失败：下次读取时从 FDB 重建缓存。✅
- FDB commit 失败：tick 放弃，tick_counter 不递增，fuel 退还。✅

### 7.2 Tick 原子性边界

P0-1 §3.4 将整个 EXECUTE 包裹在 FDB 事务中。这是正确的——所有 command validation + ECS system execution 必须在同一事务内，否则可能出现部分命令执行但其他命令回滚的不一致状态。

但需注意事务规模：
- 500 玩家 × 100 commands × ~200 bytes/command = ~10MB transactional write set
- 加上 ECS entity updates: 每玩家 500 drones + 100 structures + terrain deltas
- 估算: 500 × (500 + 100) × ~200 bytes = ~60MB

FDB 文档推荐事务 <10MB。引擎可能需要将 tick 提交拆分为多个子事务（如按房间 shard），但拆分会丢失全 tick 原子性。

**建议**: Phase 1 实现早期进行 FDB 事务规模基准测试（R3 C-10 建议），验证 500-玩家规模的可行性。若 FDB 无法承载，考虑分片策略。

### 7.3 并发安全性 (ECS Parallelization Risk)

当前 `.chain()` 是安全的，但 DESIGN 和 P0-1 §3.3 都提到未来用 `.before()/.after()` 实现部分并行。

**警告**: Bevy 的 `.before()/.after()` 构建的是 ordering graph，在同一 graph level 上的 systems 可能并行执行。如果两个 system 访问同一个 Archetype 的不同 component，Bevy 的 scheduler 能安全并行。但如果访问相同 component（如 movement_system 和 combat_system 都读取 Position），需要显式表达冲突。

建议: 在引入并行前，定义 component access matrix，确保没有未声明的读写冲突。

---

## 八、算法复杂度风险

### 8.1 快照构建: O(P × E) 瓶颈已避免

P0-1 §2.3: "快照按房间序列化一次，再按玩家过滤——不是 O(P × E)。"

分析: 每房间 E_room 个实体。每 tick 序列化 R 个房间 → O(R × E_room) = O(E_total) 序列化成本。然后对 P 个玩家做可见性过滤 → O(P × log(E_total)) 如果可见性缓存有效。

P0-5 §5 的可见性缓存（HashSet<EntityId> per player per tick）是关键优化。每 tick 计算的复杂度为 O(P × R × avg_entities_per_room) 用于构建缓存，但这对每个玩家的每个视野源做范围查询是瓶颈。对于 500 玩家、每玩家 10 个视野源、100 个实体在范围内：500 × 10 × 100 = 500K 操作。每 tick (<3s)，可承受。

### 8.2 指令排序: O(C log C) 可接受

C_max = 500 玩家 × 100 commands = 50,000 commands per tick。
排序复杂度: O(50K log 50K) ≈ 50K × 16 ≈ 800K 比较。在 500ms EXECUTE 预算内绰绰有余。

### 8.3 路径查找: 缓存策略有效

P0-2 §4.3: path_find 结果按 (from, to, terrain_hash) 缓存。地形不变则不重算。对于持久世界，缓存命中率极高（地形不变 + 常规巡逻路径重复）。但首次冷启动和新建建筑（地形变更 → hash 失效 → 缓存 miss）需要注意。每玩家每 tick 10 次限制保持安全。

### 8.4 Rhai 模组执行预算

DESIGN §8.7 定义了四级限制:
- AST 节点 10,000/tick
- actions 调用 100/tick
- state.players() 迭代 3,000 项
- 墙钟 100ms/tick

合理。连续 10 tick 超限自动禁用——安全熔断。

---

## 九、Strengths

1. **R3 闭合执行质量高**: 6 项 Freeze Blocker 中 4 项完全闭合，2 项仅剩 text cleanup。Gap-1 的 12-source 矩阵超出 R3 需求。

2. **Deferred Model 架构内聚性强**: tick() → JSON 的设计在 P0-2/P0-4/P0-8 之间形成了清晰的 contract 链路——snapshot in, commands out, validate in between。这是确定性回放和安全沙箱的共同基石。

3. **全局存储反制机制设计精深**: 累进税 + 隐匿性 + 运输时间三项形成立体约束，每个单独机制都可独立生效，组合产生乘数效应。运输时间为 "战斗中即时补给不可能" 提供了非人工的游戏内解释。

4. **Fuel Refund anti-amplification 安全性好**: 时序（N→N+1）+ 上限（10%）+ 去重（同源仅首次）+ 熔断（3 tick throttle）——四层防御，没有明显的博弈论利用路径。

5. **Determinism Contract 覆盖面广**: PRNG/Hash/Sort/ECS order/numerics/collections 全部有明确约定的算法和实现。Blake3 + ChaCha12 的组合在密码学安全性上优于大多数游戏引擎。

6. **IDL 代码生成管线设计正确**: `git diff --exit-code` 的 CI 守卫确保无人能手写偏离 IDL 的 Command 变体。这在多人协作项目中是防止 API drift 的唯一可靠手段。

7. **P0-9 Command Source Model 完备**: 12 个来源 × 5 维能力 × visibility/budget/rate_limit 矩阵，Tutorial 隔离的独立 namespace 约束——没有遗漏的来源或能力。

---

## 十、Remaining Concerns

| ID | 严重度 | 描述 | 修复位置 |
|----|--------|------|---------|
| D1 | **CRITICAL** | DESIGN §5 仍描述 imperative host functions (14个)，与 deferred model 冲突 | DESIGN.md §5 |
| D2 | **CRITICAL** | P0-4 §8 成本表包含被 §3.3 禁止的 9 个 host functions | P0-4 §8 |
| D3 | **HIGH** | DESIGN §8.8 i18n 示例使用 `type = "f64"` 与 fixed-point-only 声明矛盾 | DESIGN.md L1072-1076 |
| D4 | **MEDIUM** | P0-4 §3.2 允许的 host function 列表缺少 `host_get_world_rules` | P0-4 §3.2 |
| D5 | **LOW** | R3 C-6: 模组依赖 semver 约束语法未定义 | DESIGN §8.7 或 P0-7 |
| D6 | **LOW** | Determinism Contract 未约定 WASM 编译确定性 (source → binary) | DESIGN §8.8 |
| D7 | **LOW** | Determinism Contract 未约定 Rhai 版本确定性 | DESIGN §8.8 |
| D8 | **MEDIUM** | IDL 未定义 Snapshot JSON schema | P0-8 |
| D9 | **MEDIUM** | IDL 未定义 TickTrace schema 格式 (仅声明 "冻结") | P0-8 |
| D10 | **LOW** | IDL Spawn.validator 简写缺少 ExceedsRoomCapacity/RoomDroneCapReached | P0-8 |
| D11 | **INFO** | FDB 事务规模基准测试未执行 (R3 C-10)，500-玩家规模可能超出 10MB 限制 | Phase 1 |

---

## 十一、Fresh Ideas

### FI-1: Tick 压缩 (Idle World Optimization) ★★★

对于低活跃度世界（如仅 3 个在线玩家），tick interval 从 3s 动态扩展到 10s，有事件时（玩家部署新代码/drone 指令冲突）加速回 3s。

**实现**: 在 Tick 调度器中加入 active_player_count 检测。当 <10 活跃玩家且最近 100 tick 无 command rejection（无竞争），自动扩展 interval。保持 tick_counter 单调递增（空 tick 仍需记录，但无需完整 ECS 执行）。

### FI-2: ECS Ordering Graph — 从 .chain() 到显式约束 ★★★

将 P0-1 §3.3 的 .chain() 升级为显式 constraint graph：

```rust
app.add_systems(Update, (
    build_system,
    harvest_system.after(build_system),
    regeneration_system.after(harvest_system),
    movement_system.after(regeneration_system),
    combat_system.after(movement_system),
    decay_system.after(combat_system),
    death_system.after(decay_system).after(combat_system),
    spawn_system.after(death_system),
));
```

这会构建一个 DAG，Bevy 可以找到部分并行机会（如 regeneration 和 movement 可能无冲突），同时保持 ordering 正确性。与 blind .chain() 相比收益取决于 system 间 component 依赖，需 benchmark 验证。

### FI-3: replay 指令压缩存储 ★★☆

tick N 的 RawCommand 为完整 JSON。相邻 tick 之间大多数 drone 的行为模式相同（continue harvesting）。可以存储指令 delta：对每个 drone，如果本 tick 指令与上 tick 相同，存储 1-bit "same as last tick" 标志而非完整 JSON。

**节省**: 典型世界（80% drone 重复相同动作）→ ~5× 压缩。对 FDB 存储成本和回放传输带宽均有收益。

### FI-4: 确定性种子升级机制 ★★☆

当前 world_seed 从世界创建后不变。但若发现 ChaCha12 实现有 bug 需要升级，需要迁移机制：

```rust
struct WorldSeed {
    initial: Blake3Hash,          // 世界创建时的种子
    current: Blake3Hash,         // 当前活跃种子
    migration_tick: u64,         // 迁移发生的 tick
    migration_reason: String,    // 审计: "Upgrade ChaCha12 from v0.3 to v0.4"
}
```

允许在特定 tick 进行确定性种子切换，记录在 TickTrace 中。回放时按 migration_tick 使用正确的种子。

### FI-5: WASM 模块热图分析 ★☆☆

记录每个玩家 WASM 模块的 host function 调用频率热图，生成 `heatmap.json`：

```json
{
  "player_42": {
    "get_objects_in_range": 234,
    "path_find": 12,
    "get_terrain": 0,
    "fuel_used": 7_200_000
  }
}
```

用于：(a) SDK 优化决策（如果 90% 玩家从不调用 path_find，可以降低其实现优先级），(b) 反作弊（异常的 host function 调用模式），(c) 玩家自我分析（"我的代码为什么 fuel 这么高？"）。

---

## 十二、Phase 0 Freeze 条件

当前状态: **未满足冻结条件**

缺失项:
1. ✅ FB-1: Rhai f64 → 需闭合 D3 (i18n 示例修复)
2. ✅ FB-6: Deferred model → 需闭合 D1 (DESIGN §5 清理) + D2 (P0-4 §8 清理)

**冻结执行清单**:

```
[ ] D1: DESIGN §5 重写为只读查询 host function 列表 + 引用 deferred model
[ ] D2: P0-4 §8 删除被禁止的 9 个函数行
[ ] D3: DESIGN §8.8 i18n 示例 f64 → fixed<u32,4>
[ ] D4: P0-4 §3.2 添加 host_get_world_rules
```

闭合 D1-D4 后即可宣布 Phase 0 Architecture Frozen。D5-D11 可在 Phase 1-2 中处理。

---

*评审完成: 2026-06-14 22:30 UTC*
*深度推理链: 8 文件全量扫描 + R3 Verdict 逐项对照 + 数据流一致性分析*
*输出: /data/swarm/docs/reviews/r4-rev-dsv4-architect.md*
