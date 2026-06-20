# R24 Architecture Review — rev-dsv4-architect

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Direction**: Architecture — 设计文档与规范文档之间的接口一致性、预算对齐、签名验证
**Review Type**: Clean Slate — spec ↔ design 全量对齐检查
**Documents Reviewed**: design/ (README, engine, interface, tech-choices) + specs/ (core/01-tick-protocol, core/04-wasm-sandbox, core/05-persistence-contract, reference/api-registry, reference/host-functions, reference/mcp-tools) — 共 10 份核心文档

---

## Verdict: REQUEST_MAJOR_CHANGES

发现 **3 Critical**（签名矛盾、预算冲突、存储层错位）、**3 High**（工具计数矛盾、参数缺失、签名不一致）、**4 Medium**、**3 Low**。Critical 项必须在合并前修正——签名矛盾和预算冲突直接影响实现路径选择；High 项导致 API 规范权威性受损。架构层面的核心设计（ECS 系统链、两阶段快照、Deferred Command Model）正确，问题集中在跨文档数值/签名/命名的一致性上。

---

## Critical

### C1 — `host_get_terrain` 签名矛盾：Authority (api-registry) 与所有其他文档不一致

**位置**: `design/interface.md` §5.1 L74 vs `specs/reference/api-registry.md` §4.1 L399（权威源）

**冲突描述**:

| 文档 | 签名 |
|------|------|
| `design/interface.md` §5.1 L74 | `fn host_get_terrain(x: i32, y: i32) -> i32` |
| `specs/reference/host-functions.md` L23 | `i32 host_get_terrain(x: i32, y: i32) -> i32` |
| `specs/core/04-wasm-sandbox.md` §3.2 L208 | `fn host_get_terrain(x: i32, y: i32) -> i32` |
| `specs/reference/api-registry.md` §4.1 L399 **(权威源)** | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |

**影响**:

两种签名的语义完全不同：
- 版本 A (`x, y`)：查询**单个坐标**的地形类型，返回值为地形类型（i32 直接编码 0=Plain/1=Wall/2=Swamp/3=Lava）。`host-functions.md` L25 明确注释 "返回指定坐标的地形类型"。
- 版本 B (`room_id, out_ptr, out_len`)：查询**整个房间**的地形数据，写入 `out_ptr` 缓冲区。输出上限为 8KB（`api-registry.md` §4.3 L423），暗示返回的是房间级地形网格而非单格。

`api-registry.md` 是 **单一权威源**（Single Source of Truth, §原则 D1/A），其签名以 `game_api.idl.yaml` 为原始事实源。但 design/interface.md、host-functions.md、wasm-sandbox.md 三份文档一致的 `(x, y)` 签名暗示这可能是原始设计意图，而 api-registry 的 `(room_id, out_ptr, out_len)` 可能是 IDL 生成过程中的偏差。

**修正建议**:

1. 确认 `game_api.idl.yaml` 中 `host_get_terrain` 的权威签名。
2. 若 IDL 中签名为 `(room_id, out_ptr, out_len)` → 更新 design/interface.md、host-functions.md、wasm-sandbox.md 中的签名（这三份文档均应引用 api-registry）。
3. 若 IDL 中签名为 `(x, y)` → api-registry.md 的生成逻辑需修复，并检查输出上限（8KB 对于单格 `i32` 返回不合理）。
4. 不论哪种结果，`host-functions.md` §输出上限（L76）中 `host_get_terrain` 的 8KB 与 `wasm-sandbox.md` §8（L353）中的 4 bytes 同为冲突点，需一并解决。

---

### C2 — EXECUTE 阶段预算：400ms (design) vs 500ms (spec)

**位置**: `design/engine.md` §3.4.1 L295 vs `specs/core/01-tick-protocol.md` §1.4 L74

**冲突描述**:

- `design/engine.md` §3.4.1 Tick Pipeline 预算表：`EXECUTE (2a+2b) ≤400ms`
- `specs/core/01-tick-protocol.md` §1.4 Tick 状态机图：`阶段二：执行 (EXECUTE) 超时: 500ms`

**影响**:

100ms 的差异在 3000ms tick 周期中占比约 3.3%，但关系到以下实现决策：

1. **EXECUTE 阶段内部子预算分配**：design §3.4.1 将 400ms 分配给 `2a (inline apply) + 2b (ECS systems)`，spec 的 500ms 为整体超时。若按 spec 的 500ms 实现，Phase 2a 的 inline apply 超时可放宽，可能影响指令处理的吞吐量目标（100k commands/tick, p99 < 100ms）。
2. **与 COLLECT 和 COMMIT 的接口**：Tick 阶段三预算总和 `COLLECT + EXECUTE + COMMIT = 2500 + 400 + 50 = 2950ms`（design）vs `2500 + 500 + 50 = 3050ms`（spec）——后者已超出 3000ms tick interval 目标。这意味着 spec 的 500ms 在实际运行时必然与 COLLECT 或 COMMIT 争抢时间。
3. **容量推导依赖**：design §3.4.2 的 500-player capacity derivation 使用 `Execute phase = 400ms` 作为硬假设。若 EXECUTE 放宽到 500ms，容量公式需要重新校准。

`specs/core/01-tick-protocol.md` 的 §8.2 统一预算表（L692-700）中 COLLECT wall-clock per player 为 2500ms，但**未单独列出 EXECUTE 阶段预算**——仅给出 COLLECT 预算。这使得 500ms 超时值的来源不明：是整体 EXECUTE 超时还是仅 Phase 2a 超时？

**修正建议**:

1. 以 `design/engine.md` §3.4.1 的 `EXECUTE ≤400ms` 为权威性能合同（该表是 "deadline-driven 硬性能合同"），更新 `specs/core/01-tick-protocol.md` §1.4 的状态机超时为 400ms。
2. 在 `specs/core/01-tick-protocol.md` §8.2 统一预算表中增加 EXECUTE 阶段行：`EXECUTE Phase 2a+2b | wall-clock overall | 400ms | 超限 → 当前命令丢弃并 abort EXECUTE 阶段 | ❌`。
3. 重新验证 500-player capacity derivation 在 400ms EXECUTE 预算下的正确性（当前公式已使用 400ms，只需确认 spec 同步）。

---

### C3 — Keyframe 存储层归属：FDB vs Keyframe Store

**位置**: `design/engine.md` §3.2 Phase 3 L218 vs `specs/core/05-persistence-contract.md` §1 L26

**冲突描述**:

- `design/engine.md` §3.2 Tick 生命周期 Phase 3（L218）：`持久化：每 tick 存储 delta，每 K tick 存储 keyframe 到 FDB（回放用）`
- `specs/core/05-persistence-contract.md` §1 存储层职责表（L26）：`Keyframe Store | 每 K tick 的完整世界状态快照 | < 100MB | 7d hot / 30d cold` — Keyframe Store 作为**独立存储层**，与 FDB（L23）、Object Store（L24）、WAL（L25）并列

**影响**:

1. **存储架构分歧**：design 将 keyframe 存入 FDB，persistence-contract 定义独立的 Keyframe Store。FDB 的事务模型适合小对象（<1KB/row, "FDB 只写小对象"），而 keyframe 为完整世界状态快照（<100MB/object）——这**直接违反了 persistence-contract §原则 1-2**："FDB 只写小对象"、"大 BLOB 进对象存储"。

2. **GC 策略差异**：若 keyframe 在 FDB 中，GC 策略需在 FDB 事务层实现（FDB 不原生支持 TTL）。persistence-contract 的 Keyframe Store 有独立的 hot/cold GC 策略（§6.2 L251-253）。

3. **回放路径不同**：
   - design/engine.md 模型：回放时从 FDB 直接读取 keyframe + delta chain
   - persistence-contract 模型：从 Keyframe Store 读取 keyframe，再从 FDB manifest 验证完整性（§5.1 L206-214）

`specs/core/05-persistence-contract.md` 是持久化权威合同（§9 L394 明确声明 "本文件为权威持久化合同，engine.md 描述架构意图"），因此 Keyframe Store 为正确目标。但 `design/README.md` §3 数据模型表（L170-175）也将 keyframe 相关数据（TickTrace）列为 FDB 不可变追加，可能进一步混淆。

**修正建议**:

1. 将 `design/engine.md` §3.2 Phase 3 L218 的 "存储 keyframe 到 FDB" 修正为 "存储 keyframe 到 Keyframe Store（回放用）"，并添加引用指针指向 `specs/core/05-persistence-contract.md` §1。
2. 在 `design/engine.md` §3.4.7 "FDB 写入策略" 中删除 keyframe 写入条目（L451 "每 K=100 tick 写入一次 keyframe" 与 FDB 写入策略的 context 不匹配），改为 "每 K=100 tick 写入一次 keyframe 到 Keyframe Store（详见 05-persistence-contract）"。
3. 在 `design/README.md` §3 数据模型表中确认 TickTrace 与 keyframe 的归属分离：TickTrace 不可变记录 → FDB；keyframe 快照 → Keyframe Store。

---

## High

### H1 — MCP 工具计数矛盾：56 vs 54

**位置**: `design/interface.md` §4.1 L19 vs `specs/reference/mcp-tools.md` L26 vs `specs/reference/api-registry.md` §3 L209（权威源）

**冲突描述**:

| 文档 | Game API 工具计数 |
|------|:----------------:|
| `design/interface.md` §4.1 L19 | **56** game tools + 11 auth tools |
| `specs/reference/mcp-tools.md` §工具总览 L26 | Game API 小计 **56** |
| `specs/reference/api-registry.md` §3 L209（权威源） | 共计 **54** 个活跃工具 (game_api) |

进一步分析 `api-registry.md` §3.2 中各分组子项之和：Onboarding(10) + Auth(2) + Play(16) + Deploy(7) + Debug(8) + Admin(6) + SDK(1) + Arena(4) + Resources(2) = **56**——与头部声明的 "54" 不一致。

**影响**:

`api-registry.md` 作为 "单一权威来源"，其自身内部存在分组计数之和与头部声明值的矛盾（56 ≠ 54）。外部文档（design/interface.md、mcp-tools.md）均以 56 为准。这使得 "54" 的来源可疑——可能是 (a) 过期的旧值未更新，(b) 错误计算，或 (c) 有意排除了 2 个工具但未在头部注明排除逻辑。

specs/reference/mcp-tools.md 显式声明 "同步自 API Registry 0.4.0"，但其引用的值（56）与 api-registry 头部（54）矛盾——引用链已断裂。

**修正建议**:

1. 确认 `game_api.idl.yaml` 中的实际活跃工具数。若为 56 → 将 `api-registry.md` §3 头部 "54" 修正为 "56"。
2. 若确为 54，需在 api-registry.md 中标注哪两个工具被排除及排除原因（如 "含 2 个 deprecated 工具不计入活跃计数"），并通知 design/interface.md 和 mcp-tools.md 同步更新。
3. 在 CI 中增加自动化校验：`IDL YAML 工具计数 == api-registry.md 头部声明计数 == 分组子项之和`。

---

### H2 — Worker Pool 参数在核心 spec 中缺失

**位置**: `design/engine.md` §3.4.2 L337-360 → `specs/core/01-tick-protocol.md` GAP, `specs/core/04-wasm-sandbox.md` GAP

**描述**:

`design/engine.md` §3.4.2 "Worker Pool 推导" 定义了完整的 worker pool 动态伸缩模型：

```
worker_pool_size = min(worker_pool_max, active_players)
worker_pool_size = clamp(worker_pool_size, 0, worker_pool_hard_cap)

其中:
  worker_pool_max = 256（运行期默认，见 game_api.idl.yaml §limits.worker_pool）
  worker_pool_hard_cap = 1000（编译期硬上限）
```

然而：

- `specs/core/01-tick-protocol.md`（Tick 协议核心规范）：§8 统一预算表仅覆盖 COLLECT/EXECUTE 阶段的 per-player 资源预算，**无 worker pool 配置或推导逻辑**。
- `specs/core/04-wasm-sandbox.md`（WASM 沙箱基线）：§1（L41）描述 "long-lived worker pool" 模型但**未指定 pool size 参数或伸缩公式**。§4 OS 隔离提及 cgroup 约束但未关联 pool 规模。
- `specs/reference/api-registry.md` §5.5（L528-531）包含 worker pool 容量值（max 默认 256, hard cap 1000），但仅作为静态容量限制，**不含动态伸缩公式与 admission 逻辑**。

**影响**:

实现者仅阅读 `specs/core/04-wasm-sandbox.md` 将知道需要 worker pool 但不知道 pool 大小如何确定——可能硬编码固定值（如 256）而错过 `min(256, active_players)` 的动态伸缩逻辑。sandbox pool 的 lifecycle（空闲回收 5min、worker 1000-tick 替换）在 design §3.4.3 中定义但 spec 中仅在 api-registry 作为容量限制提及，未作为行为规范。

此外，`api-registry.md` 声明 worker_pool_max 定义在 `game_api.idl.yaml §limits.worker_pool`，但 §5.5（L529）的 "max_pool 默认 256，World 模式" 是否与 design 的 `min(256, active_players)` 等价不明确——前者是静态上限，后者是动态公式。

**修正建议**:

1. 在 `specs/core/04-wasm-sandbox.md` §1 末尾增加 "Worker Pool 配置" 段落，包含：动态伸缩公式、`worker_pool_max` / `worker_pool_hard_cap` / idle timeout / 1000-tick 强制替换，并引用 `api-registry.md` §5.5 为权威值源。
2. 在 `specs/core/01-tick-protocol.md` §2.1（玩家执行模型）附近增加 worker pool admission 逻辑描述（如何将玩家分配到 worker、pool 满时的排队策略）。
3. 确认 `api-registry.md` §5.5 "Worker pool size = min(max_pool, active_players)" 与 design §3.4.2 的 `clamp` 公式一致，确保 `0` 下限和 `hard_cap` 上限被列入。

---

### H3 — `host_get_world_rules` 签名矛盾：rule_id 参数存在性不一致

**位置**: `design/interface.md` §5.1 L80 vs `specs/reference/api-registry.md` §4.1 L403（权威源）

**冲突描述**:

| 文档 | 签名 |
|------|------|
| `design/interface.md` §5.1 L80 | `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` |
| `specs/reference/host-functions.md` L52 | `i32 host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` |
| `specs/core/04-wasm-sandbox.md` §3.2 L214 | `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` |
| `specs/reference/api-registry.md` §4.1 L403 **(权威源)** | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` |

**影响**:

`api-registry.md`（权威源）的签名多出 `rule_id_ptr` / `rule_id_len` 参数，允许按 `rule_id` 查询**特定规则模块**而非整个规则集。而 design、host-functions、wasm-sandbox 三份文档一致的 `(out_ptr, out_len)` 签名表示**返回全部规则集**。

两种语义的差异：
- 无 `rule_id` 版本：一次调用返回完整规则 JSON，host-functions.md L53 注释 "返回当前世界规则集的 JSON"。
- 有 `rule_id` 版本：允许逐模块查询，更精细但增加了 API 复杂度。`api-registry.md` §4.2 L413 限制 `host_get_world_rules` 为 1/tick —— 若是逐模块查询，则需要多次调用，1/tick 限制太严格。

`design/interface.md` 是架构师的主要参考文档，三份非权威文档的一致性暗示 `rule_id` 可能是 IDL 后期的添加但设计文档未同步。

**修正建议**:

1. 确认 `game_api.idl.yaml` 中的权威签名。
2. 若 IDL 确实包含 `rule_id` → 更新 design/interface.md §5.1、host-functions.md、wasm-sandbox.md §3.2 中的签名，并更新 `host_get_world_rules` 的 per-tick 调用上限（当前 1/tick 在 rule_id 场景下可能需要放宽）。
3. 若 IDL 不含 `rule_id` → api-registry.md 的生成逻辑需修复。
4. 在 design/interface.md §5.5 增加注释说明调用预算（当前 host_get_world_rules 在 design 中未单独列预算，仅在 api-registry §4.2 中）。

---

## Medium

### M1 — `host_path_find` 签名不一致：opts 参数存在性

**位置**: `design/interface.md` §5.1 L76 vs `specs/reference/api-registry.md` §4.1 L401（权威源）

**冲突描述**:

| 文档 | 签名 |
|------|------|
| `design/interface.md` §5.1 L76 | `(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32`（6 参数） |
| `specs/reference/host-functions.md` L38 | 同上 6 参数 |
| `specs/reference/api-registry.md` §4.1 L401（权威源） | `(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32`（8 参数） |

**影响**:

`api-registry.md` 多出 `opts_ptr` / `opts_len` 参数，允许传入寻路选项（如 cost 类型、avoid 区域、algorithm 选择）。design 和 host-functions 未提及此参数。`host-functions.md` §注意事项 仅提到 "Pathfinding 确定性要求：固定 neighbor order（NESW 顺时针）、cost type（均一 1）、tie-break"——这些属于引擎内部行为而非调用者可控的 opts。若 `opts` 参数为 IDL 中的正式参数，则需要在 host-functions 和 design 中同步文档化其 schema。

**修正建议**: 与 C1 类同——确认 IDL 权威签名后同步所有引用文档。

---

### M2 — `host_get_terrain` 输出大小：4 bytes vs 8 KB

**位置**: `specs/core/04-wasm-sandbox.md` §8 L353 vs `specs/reference/api-registry.md` §4.3 L423

**冲突描述**:

- `specs/core/04-wasm-sandbox.md` §8 成本表（L353）：`host_get_terrain | 500 (fuel) | 4 bytes（响应大小上限）`
- `specs/reference/api-registry.md` §4.3 输出上限表（L423）：`host_get_terrain | 8 KB`
- `specs/reference/host-functions.md` §输出上限（L76）：`host_get_terrain | 8 KB`

**影响**:

4 bytes = 单个 `i32` 返回值（与 `(x, y) -> i32` 签名一致）。8 KB = 整个房间地形网格的 JSON 或二进制输出（与 `(room_id, out_ptr, out_len)` 签名一致）。此差异与 C1（签名矛盾）是同一个根源问题的两个表现。

不论 C1 如何裁决，两处输出上限必须一致。若最终签名为 `(room_id, out_ptr, out_len)` → 8KB 合理（50×50 格的房间地形数据）。若最终签名为 `(x, y) -> i32` → 4 bytes 正确。

**修正建议**: 与 C1 一并解决。

---

### M3 — Tick 统一预算表缺少 SNAPSHOT 分项

**位置**: `design/engine.md` §3.4.1 L293 vs `specs/core/01-tick-protocol.md` §8.2 L692

**描述**:

`design/engine.md` §3.4.1 将 **SNAPSHOT build** 作为独立的预算阶段（≤50ms p99），与 COLLECT/EXECUTE/COMMIT/BROADCAST 并列。而 `specs/core/01-tick-protocol.md` §8.2 "统一预算表" 从 COLLECT 的 wall-clock per player 开始，**未单独列出 SNAPSHOT build 预算**。SNAPSHOT 构建是 COLLECT 的前置步骤（COLLECT 开始 → [1] 构建完整世界快照 → [2] 按房间分片 → [3] 视野过滤）——spec 将其隐式归入 COLLECT 阶段但未显式分配预算。

`design/engine.md` §3.4.5（500-player capacity derivation）也提到 "Snapshot build per player = ~0.5ms"，此值在 spec 中无对应约束。

**影响**: 实现者若仅阅读 spec，可能将 SNAPSHOT 的 50ms 预算划入 COLLECT 的 2500ms —— 表面上看合理，但无独立监控意味着 SNAPSHOT 延迟异常无法被独立告警。

**修正建议**: 在 `specs/core/01-tick-protocol.md` §8.2 统一预算表中增加 `SNAPSHOT build | wall-clock | ≤50ms (p99) | 超限 → tick 放弃 | ❌` 行，并标注 "COLLECT 阶段的 2500ms 预算不包含 SNAPSHOT build，SNAPSHOT 为独立前置步骤"。

---

### M4 — `api-registry.md` 内部工具计数自相矛盾（54 vs 56）

**位置**: `specs/reference/api-registry.md` §3 L209 vs §3.2 分组子项之和

**描述**:

`api-registry.md` §3 头部声明 "共计 54 个活跃工具 (game_api)"。但 §3.2 各组子项：Onboarding(10) + Auth(2) + Play(16) + Deploy(7) + Debug(8) + Admin(6) + SDK(1) + Arena(4) + Resources(2) = **56**。这是同一份文档的内部矛盾——作为 "单一权威来源" 的文档自身不一致，动摇了整个引用链的可靠性。

两个可能原因：
1. 头部值 "54" 为过期残留——工具清单已增至 56 但头部未更新。
2. 2 个工具被排除出 "活跃" 计数但未在头部注明（如 Tier 2 标记的 `Leech` 和 `Fabricate` 虽在 §1.3 中注册但可能不计入 MCP 工具）。

修正建议见 H1。

---

## Low

### L1 — Keyframe K 值在 design/engine.md 内部不同步

**位置**: `design/engine.md` §3.2 Phase 3 L218 vs §3.4.7 L451

**描述**:

- §3.2 Phase 3（Tick 生命周期图, L218）：`每 K tick 存储 keyframe 到 FDB（回放用）` — K 未指定
- §3.4.7（FDB 写入策略, L451）：`每 K=100 tick 写入一次 keyframe` — K 明确为 100

同一文档内，前文用占位符 K，后文才给出具体值 K=100。实现者快速浏览 §3.2 可能错过 §3.4.7 的具体值。

**修正建议**: 在 §3.2 L218 中替换 "每 K tick" 为 "每 100 tick (K=100)"，或添加脚注引用 §3.4.7。

---

### L2 — SNAPSHOT build 预算在 spec 中不独立追踪

**位置**: `design/engine.md` §3.4.1 L293 → `specs/core/01-tick-protocol.md` §8.2

**描述**:

`design/engine.md` 将 SNAPSHOT build 列为独立预算项（≤50ms p99），但 `specs/core/01-tick-protocol.md` §8.2 统一预算表以 COLLECT 为第一个条目，SNAPSHOT 被隐式合并。spec §2.3 描述了快照构建的时序（[1] 构建完整世界快照 → [2] 按房间分片 → [3] 视野过滤）但未将步骤 [1]-[2] 的耗时从 COLLECT 的 2500ms 中单独拆分。

这属于 Low（非 Critical）因为 spec §2.3 的时序描述已暗示了构建步骤，只是缺少独立的预算监控项。

**修正建议**: 见 M3。

---

### L3 — COLLECT budget 语义：≤2500ms (design) vs =2500ms (spec)

**位置**: `design/engine.md` §3.4.1 L294 vs `specs/core/01-tick-protocol.md` §2.2 L123

**描述**:

- `design/engine.md` §3.4.1：`COLLECT (sandbox dispatch) ≤2500ms` — 使用 `≤`（上限/预算）
- `specs/core/01-tick-protocol.md` §2.2：`collect_timeout_ms = 2500` — 使用 `=`（硬截止值）

语义差异：
- `≤2500ms` 暗示 COLLECT 应在 2500ms **之前**完成，2500ms 是 budget 上限。
- `collect_timeout_ms = 2500` 暗示在**恰好** 2500ms 时触发超时动作（跳过未完成玩家）。

spec 的 §8.1（L686）引入 `tick_soft_deadline_ms = 2500ms` 概念——"超过此值触发告警并跳过剩余玩家 COLLECT（0 指令）"。这澄清了 2500ms 是软截止而非预算。但 spec §2.2 的命名 `collect_timeout_ms` 与 §8.1 的 `tick_soft_deadline_ms` 语义有细微差异——前者暗示 per-player timeout，后者暗示 overall soft deadline。

**修正建议**: 统一命名：将 spec §2.2 的 `collect_timeout_ms` 改为 `collect_soft_deadline_ms` 以与 §8.1 对齐，并添加注释 "此值为软截止非预算上限——COLLECT 应在 2500ms 前完成，超时后未完成的玩家输出丢弃"。

---

## Cross-Check Items for Other Reviewers

以下是与架构域交叉但更适合其他方向裁决的发现，提交 cross-check：

| # | 发现 | 建议方向 |
|---|------|---------|
| X1 | `host_get_objects_in_range` 签名同样存在多参数差异：design（L75）与 host-functions（L29）为 5 参数 `(x, y, range, out_ptr, out_len)`，api-registry（L400）为 `(x, y, range, out_ptr, out_len)` 一致。但 wasm-sandbox §3.2（L209）注释 "仅返回 `is_visible_to(caller)` 为 true 的实体" 在 api-registry 中未体现。 | **API/DX** |
| X2 | Pathfinding 全局预算 `100,000 explored nodes/tick` 在 design §3.4.2（L312）、api-registry §5.2（L498）、api-registry §5.6（L539）三处一致。但 per-player fair-share `floor(100,000 / active_players)` 仅 design 定义，不在 api-registry 的 fair-share 条目中（§5.6 L539 仅说 "per-player 份额" 未给公式）。 | **Performance** |
| X3 | `design/engine.md` §3.4.2 容量合同声明 "权威容量定义以 api-registry §5 为准"，但 api-registry §5.5 worker pool max 为 256、hard cap 为 1000——这些值与 design §3.4.2 的 worker pool 推导一致。但 api-registry 将 worker_pool_max 引用到 `game_api.idl.yaml §limits.worker_pool`，design 引用到同一 IDL——需确认 IDL 中确实有此节。 | **API/DX** |

---

## Review Statistics

| Metric | Value |
|--------|-------|
| Documents reviewed | 10 (4 design + 6 spec) |
| Critical findings | 3 |
| High findings | 3 |
| Medium findings | 4 |
| Low findings | 3 |
| Cross-check items | 3 |
| Architecture-level concerns | 0 |

---

*Review completed 2026-06-20. 下一轮 Closure Verification 建议重点关注 C1 (host_get_terrain signature)、C2 (EXECUTE budget)、C3 (keyframe storage)。这三个 Critical 项均涉及跨文档的权威源同步——建议以 api-registry.md（API 域）和 05-persistence-contract.md（持久化域）为各自领域的权威，逐项回溯 design 文档的引用并修正。*