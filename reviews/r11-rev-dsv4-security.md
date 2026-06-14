# R11 — Security Review (rev-dsv4-security)

**Reviewer**: DeepSeek V4 Pro (Security Direction, Primary)
**Date**: 2026-06-14
**Scope**: DESIGN.md, tech-choices.md, PLANNER-OUTPUT.md, specs/p0/ (01–09)
**Profile**: Tick protocol consistency verification, data flow tracing, race condition detection

---

## Verdict: APPROVE_WITH_RESERVATIONS

设计在安全层面整体严谨——deferred command model、单一 Source Gate、燃料计量、可见性契约形成了一条连贯的信任边界。发现 2 个 Critical、4 个 High、4 个 Medium 问题。Critical 项必须在 Phase 2 实现前修正；High 项需在 Phase 3 前解决。

---

## Critical

### C1: Host Function 可见性过滤缺失 — WASM 可绕过 Fog-of-War

**影响范围**: 所有启用 `fog_of_war=true` 的世界

P0-4 §3.2 定义了 WASM 可调用的查询类 host function：

```rust
fn host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32;
```

该函数描述为 "信息查询（只读，不改变世界状态）"，**未提及可见性过滤**。

P0-5 详细定义了每个输出面的可见性执行点（Snapshot §3.1, MCP §3.2, WebSocket §3.3, REST §3.4, Spectator §3.5），但 **host function 不在列表中**。P0-5 §5 的可见性缓存仅提及 "所有输出面"，而 host function 未被归类为输出面。

**攻击场景**：
1. 玩家 drone 在房间 W1N1，fog-of-war 限制其只能看到半径 3 内的实体
2. WASM 模块调用 `host_get_objects_in_range(50, 50, 10, ...)` 查询远处坐标
3. 若无可见性过滤，返回 W1N1 全地图实体——完全绕过 fog-of-war

**P0-2 §4.2 的矛盾**：P0-2 §4.2 描述 `GetObjectsInRange` 查询指令时说 "仅返回玩家可见的实体（遵循 fog-of-war）"，但 P0-2 §4 的范围说明是 "查询不进指令管线。它们在快照生成阶段（阶段一）处理。" —— 这是 validator 行为描述，不直接约束 host function 实现。

**修复建议**：
- 每个 host function 调用时强制应用 `is_visible_to(caller_player_id, target_entity, tick)` 过滤
- 在 P0-4 §3.2 的每个 host function 描述中显式标注 "结果经 is_visible_to 过滤"
- 在 P0-5 §3 新增 "Host Functions" 小节，与 Snapshot/MCP/WS/REST/Spectator 并列
- 集成测试：fog-of-war 世界中，WASM 调用 host_get_objects_in_range 查询视野外坐标，断言返回空

---

### C2: Rhai 模组 State API 暴露完整世界状态 — 违反可见性边界

**影响范围**: 所有安装了模组的世界；潜在侧信道泄露

P0-7 §4 提供 Rhai 模组的 state API：

```rust
state.players()          → Iterator<Player>     // 所有玩家
player.drones()          → Iterator<Drone>      // 该玩家所有 drone
player.rooms()           → Iterator<Room>       // 该玩家所有房间
player.resources()       → Map<String, u64>     // 资源
```

这些 API **不经 `is_visible_to` 过滤**。虽然 P0-7 §8 声明 Rhai 处于 "服主信任" 层，但存在两个风险向量：

**攻击场景 A — 恶意模组**：
- 服主安装社区模组（模组市场），模组在 `tick_end.rhai` 中读取所有玩家的隐藏信息
- 通过 `actions.emit_event(...)` 将数据编码进事件
- 若事件对玩家可见（P0-5 未定义事件可见性），造成信息泄露

**攻击场景 B — 模组依赖链**：
- 模组 A（可信）依赖模组 B（被入侵的依赖）
- 模组 B 通过 Rhai API 读取全局状态，泄露给外部

**设计矛盾**：P0-9 §2.3 Source Capability 矩阵显示 `RuleMod` 的 "允许查询世界" = ❌，但 Rhai API 明确提供了完整的状态查询能力。能力矩阵与 API 设计不一致。

**修复建议**：
- Rhai state API 必须经过 `is_visible_to(mod_owner_id, ...)` 过滤，或限制为聚合统计（计数、求和），不暴露逐实体数据
- 在 P0-5 §3 新增 "Rhai Mod Hook" 输出面，定义其可见性范围
- `actions.emit_event` 产出的事件必须标注可见性级别，默认仅模组自身可见
- 模组市场的审核流程中加入 "状态泄露检测"

---

## High

### H1: Pathfinding 计算量不受服务器端预算约束

P0-4 §8 定义了 `host_path_find` 的 fuel 成本（10,000 + 50/tile）和调用上限（10/tick）。单次最大 15,000 fuel，10 次 = 150,000 fuel，占 MAX_FUEL (10M) 的 1.5%——在 WASM 侧可控。

但服务器端的实际计算量取决于**缓存命中率**。P0-2 §4.3 说结果以 `(from, to, 地形hash)` 缓存。若玩家故意每次查询不同的坐标对，缓存命中率为 0：

- 10 calls × A* on 100×100 hex grid ≈ 10 × 10,000 node expansions = 100,000 ops per player per tick
- 500 活跃玩家 × 100,000 = 50M A* node expansions per tick
- 在 COLLECT 阶段 2.5s 窗口内，这可能导致 CPU 争用

**地形 hash 碰撞攻击**：若玩家在路径起点/终点附近建造/拆除建筑改变 terrain hash，可以使之前的缓存全部失效，强制重算。

**修复建议**：
- 服务端 pathfinding 加入独立于 WASM fuel 的 CPU 时间预算（如 50ms/player/tick）
- 超限则当前 path_find 调用返回错误，后续调用返回缓存结果或空路径
- 在 COLLECT 阶段监控 pathfinding 总耗时，超过阈值时对低优先级玩家限流

---

### H2: `swarm_simulate` 聚合预算可致 DoS

P0-3 §4.4: `swarm_simulate` 限制 5/tick（World）/ 3/tick（Arena）
P0-9 §2.3: Simulate budget = `0.5 × MAX_FUEL` = 5M fuel per call

单个玩家可通过全部 5 个模拟槽位消耗 25M fuel 当量的服务器计算资源：
- 每次模拟运行完整的 snapshot → WASM execution → commands pipeline（不写回世界，但有完整计算开销）
- 5 次 × 5M fuel = 等同于 2.5 个玩家 tick 的计算量
- 若 100 个 AI 玩家同时调用 swarm_simulate，等于额外 250 个玩家 tick 的负载

P0-3 §5.1 对该工具的限流仅为 5/tick，未考虑模拟的**计算深度**。

**修复建议**：
- `swarm_simulate` 加入独立的**全局并发槽位**（如 10 个），超出排队或拒绝
- 每个 simulate 调用的 max ticks 限制（如 50 tick 上限），防止深度模拟
- Arena 模式下进一步收紧至 1/tick 或赛前禁用

---

### H3: PLANNER-OUTPUT.md 与 P0 规范矛盾 — 实现风险

PLANNER-OUTPUT.md（评审前草案）包含已被 P0-3 修正的错误设计：

| PLANNER-OUTPUT 内容 | P0-3 修正 |
|---|---|
| Phase 1.6: SandboxExecutor → PlayerExecutor, 新增 McpPlayerExecutor stub | McpPlayerExecutor 已移除，统一为 WasmSandboxExecutor |
| Phase 2.2: 实现全部游戏动作 MCP 工具（11 个工具，镜像 Command 枚举） | MCP 不做游戏动作——move/attack/build 等绝不出现在 MCP |
| Phase 2.5: 实现 McpPlayerExecutor tick 集成 | 不存在 McpPlayerExecutor |

虽然文档顶部有更正声明，但这些矛盾点在实现阶段可能被遗漏。特别危险的是 **Phase 1.6 计划创建 McpPlayerExecutor stub**——即使后续移除，若实现时忘记清理，会在代码库中留下"可通过 MCP 直接提交游戏指令"的死代码路径。

**修复建议**：
- PLANNER-OUTPUT.md 中受影响的 Phase 1.6、2.2、2.5 标记为 `OBSOLETE — superseded by P0-3` 并在 CI 中强制检查
- Phase 1 实现时，代码审查 checklist 包含 "确认无 McpPlayerExecutor 残留"
- 自动化测试：验证所有指令来源非 WASM 的 gameplay command 被 Source Gate 拒绝

---

### H4: 数据流一致性 — 快照与 Host Function 返回的可见性可能不同步

P0-5 §5 定义了可见性缓存：`(tick, player_id) → HashSet<EntityId>`，每 tick 计算一次。该缓存被所有输出面共享。

但存在时序问题：
1. COLLECT 阶段：为玩家 A 构建快照（使用 `tick=N, player=A` 缓存）
2. COLLECT 阶段：玩家 A 的 WASM 调用 `host_get_objects_in_range(10, 10, 3, ...)`
3. 若快照构建和 host function 调用之间，另一个 sandbox 的执行导致实体移动（不应发生，因为 COLLECT 是只读的），产生不一致

当前设计中 COLLECT 阶段所有 WASM 执行应基于同一份 Bevy World 内存快照，但该约束未在规范中显式说明。

**修复建议**：
- P0-1 §2.3 显式声明 "同一 tick 的 COLLECT 阶段，所有玩家的快照和 host function 调用共享同一份不可变 Bevy World 视图"
- 集成测试：两个并行 WASM 执行中，验证 host function 结果与快照一致

---

## Medium

### M1: WASM 模块缓存与 Auth 吊销的 TOCTOU

P0-4 §7: "每次 tick 执行前校验 player 的 auth token 仍有效——ban/revoke 时清除缓存条目"

存在一 tick 窗口：
1. Tick N COLLECT 开始 → 验证 token 有效 → 从缓存加载模块
2. Tick N COLLECT 进行中 → 管理员 ban 玩家 → 清除缓存条目
3. Tick N EXECUTE → 已加载的模块仍执行，ban 在 tick N+1 才生效

**影响**: 一 tick 延迟（3s），低影响。但有违 "即时 ban" 的用户预期。
**修复建议**: 缓存加载后、执行前做二次检查；或在 Source Gate 前增加快速吊销检查（<1μs）。

---

### M2: Code Update Cost=0 时 Deploy-Reset Refund 规则可被绕过

P0-2 §7.2: 若玩家在 tick N+1 部署了**不同**模块（`module_hash` 变更），tick N 的 refund credit 作废。

当 `code_update_cost = 0`（World 模式默认），玩家可以：
1. Tick N: 使用 v1 → 生成 refund credit
2. Tick N+1: 部署 v2（hash 不同，cost=0）→ v1 的 refund 作废
3. Tick N+1: 部署 v1（hash 相同，cost=0）→ 重新获得 v1 的 refund？

规则说 credit "与产生它的 WASM 模块绑定"，当 hash 再次匹配时 credit 是否恢复？规范未定义此行为。

**修复建议**: 明确 "refund credit 一经作废不可恢复，即使重新部署原模块"。

---

### M3: MCP Rate Limiting 未明确 per-player 跨连接执行

P0-3 §5.1 定义每玩家限制，P0-3 §5.2 定义全局限制（最大并发连接 1000）。

若 AI 玩家使用同一 token 打开多个 MCP 连接，限流是 per-token（同 player_id 共享计数）还是 per-connection？规范未定义。若为 per-connection，则可通过多连接绕过限流。

**修复建议**: P0-3 §5.1 显式声明 "所有 per-player 限制基于 `player_id` 聚合，跨所有活跃连接"。

---

### M4: TickTrace 无完整性保护链

P0-1 §6.3 将每个 tick 的 commands/state/rejections/metrics 写入 FDB，但 TickTrace 条目之间没有哈希链（类似区块链的 prev_hash）。这意味着具有 FDB 直接访问权限的管理员可以修改历史 tick 数据而不留痕迹。

虽然管理员是可信角色，但在 Arena 比赛争议仲裁场景中，可验证的不可篡改审计链是强需求。

**修复建议（Phase 6+）**: 为 TickTrace 添加 `prev_state_checksum` 字段，形成哈希链。在比赛结束后发布链尾哈希供公众验证。

---

## Informational

### I1: Snapshot-Command TOCTOU 正确但值得测试覆盖

P0-2 §3.7 Attack 校验中的 TOCTOU 处理：目标移动后按当前位置检查 → `OutOfRange`。设计正确。但所有 command 类型的 TOCTOU 行为需统一测试覆盖——不是每个 command 都有显式的 TOCTOU 声明。

### I2: Dual-Signature Rollback 未指定验证协议

P0-9 §2.2 要求 Rollback 需双人 Ed25519 签名，但未指定签名聚合格式、验证顺序、签名有效期。Phase 3 前需补充协议细节。

### I3: World Seed 泄露风险评估

world_seed 在 P0-5 §4 中标记为始终隐藏，Blake3 256-bit 抗暴力破解。但长期观察玩家排序模式可能泄露部分 seed 信息（与观察到的 shuffle 序列对比）。虽然 256-bit 空间使得实际攻击不可行，但应在确定性测试中验证 "观测 N tick shuffle 不能以 >50% 概率预测 tick N+1 顺序"。

### I4: Tutorial Source 的 "受限引导操作" 能力未完全定义

P0-9 §2.4 说 Tutorial 来源仅在 tutorial 世界接受，但 DESIGN §8 提到 "教程专用世界中的受限引导操作"。这些操作的完整能力和限制未在 P0 规范中展开。Phase 1 实现前需有完整的 Tutorial Source 能力规范。

### I5: 技术选型安全评审正面发现

- Wasmtime fuel metering + epoch interruption + 独立进程 sandbox：三层纵深防御 ✓
- Blake3 统一哈希/PRNG/代码签名：减少审计面 ✓
- FoundationDB 严格可序列化 + 每 tick 原子提交：状态一致性 ✓
- Ed25519 短期证书 + 服务端签发：吊销可控 ✓
- JSON Schema 校验 + 深度/大小限制：输入验证充分 ✓
- Deferred Command Model：杜绝 WASM 内直接 mutating 操作 ✓
- Seeded Shuffle：确定且公平的资源竞争 ✓
- Source Gate 单一路径：无绕过 ✓
- Fuel refund anti-amplification（同 tick 不可放大、deploy-reset 作废）：防止计算预算滥用 ✓

### I6: 文档交叉引用一致性良好

P0-1 ↔ P0-2 ↔ P0-4 ↔ P0-5 ↔ P0-8 ↔ P0-9 之间的引用链（Tick Protocol → Command Validation → WASM Sandbox → Visibility → IDL → Source Model）均一致，无"引用不存在章节"或"定义漂移"。唯一的不一致点是 PLANNER-OUTPUT.md（见 H3）。

---

## Review Summary

| Severity | Count | Must-Fix Phase |
|----------|-------|----------------|
| Critical | 2 | Phase 2 |
| High | 4 | Phase 3 |
| Medium | 4 | Phase 4 |
| Informational | 6 | — |

### Data Flow Trace Summary

```
COLLECT:
  Bevy World (authoritative) → visibility_filter() → Snapshot JSON → WASM tick() [sandbox, fuel-metered]
  WASM tick() → host_*() calls [⚠️ C1: no visibility filter on host functions]
  WASM tick() → Command[] JSON → schema validation [✓ depth/size/type checks]

EXECUTE:
  Command[] → seeded_shuffle() [✓ deterministic, world_seed hidden]
  Command[] → validate against current Bevy World [✓ TOCTOU handled per-command]
  Command[] → apply() in FDB transaction [✓ atomic, rollback on failure]

BROADCAST:
  FDB commit → Dragonfly cache [⚠️ stale reads possible, documented]
  Dragonfly → NATS → WebSocket [✓ gap detection, client-side fetch fallback]

Rhai mod hooks:
  state API → full world access [⚠️ C2: no visibility filter, contradicts P0-9 capability matrix]
  actions.* → mini-validator → world state [✓ cannot bypass Command Validation]

MCP:
  tools → is_visible_to() filter [✓ all read tools]
  deploy → WASM module queue → next tick atomic switch [✓]
```

### 安全架构成熟度评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 纵深防御 | ★★★★☆ | Sandbox (OS+Wasmtime) → Schema → Validator → Source Gate，缺少 host fn 可见性层 |
| 最小权限 | ★★★★☆ | Source Capability 矩阵清晰，Rhai 权限过大（C2） |
| 纵深审计 | ★★★★☆ | TickTrace + MCP audit + ClickHouse，缺完整性链（M4） |
| 确定性保证 | ★★★★★ | Blake3 XOF + .chain() + IndexMap + 禁 f64，设计严密 |
| 输入验证 | ★★★★★ | JSON Schema + 深度/大小/坐标范围/字符集，全面覆盖 |
| 资源计量 | ★★★★★ | Fuel metering + epoch interruption + cgroup + refund anti-abuse |

**总体**: 设计成熟度高于同阶段项目平均水平。两个 Critical 问题均为"规范遗漏"而非"架构缺陷"——修复不改变核心设计。
