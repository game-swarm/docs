# R6: Architect Review — DeepSeek V4 Pro

> **评审日期**: 2026-06-14
> **评审范围**: `/data/swarm/docs/design/DESIGN.md` (全 1346 行) + `/data/swarm/docs/specs/p0/` 全部 9 个规范文件
> **评审方法**: 深度推理链分析 — 算法验证 / ECS 调度正确性 / Tick 生命周期完整性 / FDB+Dragonfly 数据一致性 / 大规模计算复杂度
> **评审维度**: 架构评审员视角 — ECS system 调度并行安全性、Tick 生命周期逻辑完整性、FDB+Dragonfly 读写路径一致性、算法复杂度

---

## VERDICT: CONDITIONAL_APPROVE

条件：修复下述 D1-D3 问题，解决文档间不一致性 (G1-G4) 后即可 APPROVE。

---

## STRENGTHS (亮点)

### S1. 确定性合同 (Determinism Contract) — 教科书级完整

ChaCha12 PRNG (种子不可推导) + Blake3 hash (固定实现) + IndexMap (迭代顺序确定) + ECS `.chain()` (严格串行) + 禁 f64 浮点 (全部定点数) — 四条腿完整支撑确定性回放。特别值得称赞的是 Rhai 模组侧同样关闭浮点运算能力，`fixed<u32,N>` 定点类型全栈覆盖。每 tick 产出 `state_checksum` 并 CI 随机采样完整回放验证 — 闭环完整。

### S2. Source Gate 模型 (P0-9) — 防御纵深典范

12 种指令来源显式建模，每来源有独立的 `auth_context` / capability / budget / visibility 矩阵。auth_context 由服务端注入，客户端不可自报 player_id。Source Gate 在 Command Validation Pipeline 入口做第一道检查 — WASM 可提交 gameplay，MCP_Deploy 不可。Tutorial 来源仅在 tutorial_mode 世界有效，非 tutorial 世界静默丢弃。Rollback 要求双人审计。这是一份可以直接拿去给安全团队做 threat model 的文档。

### S3. Deferred Command Model — 干净分离

`tick(snapshot_json) → Command[]` 设计优雅。WASM 模块不得直接调用 mutating host function — 所有状态变更以 JSON 指令返回，引擎统一校验后应用。这消除了 Screeps 的 API 表面积爆炸问题（moveTo/harvest/transfer/build 各有一套校验逻辑散落在引擎各处）。单一指令管线 (P0-2) 对所有来源统一 `校验 → 应用`，无绕过路径。

### S4. WASM 沙箱隔离 — 纵深防御

双层隔离：OS 层 (seccomp + cgroup v2 + 无网络命名空间 + 只读根文件系统 + 独立 tmpfs) + Wasmtime 层 (fuel metering + 64MB 线性内存 + 禁 WASI 文件/网络/时钟/随机数)。每 tick fork → 执行 → kill 生命周期杜绝跨 tick 内存泄漏和持久化恶意模块。恶意 WASM 样本库 + CI 集成回归测试 — 这在游戏引擎中极为罕见。

### S5. 全局存储反制机制 (Anti-Dominant-Strategy) — 经济深度

累进存储税 (0–30% 免税 → 85–100% 0.20% 高税) + 本地存储隐匿性 (敌方无法探查真实经济实力) + 全局↔本地转换物流延迟 (10 tick / 5 tick，运输中可被拦截) — 三管齐下防止富玩家垄断。不是简单粗暴的硬上限，而是创造策略权衡：「囤积全局有税但灵活，囤积本地隐匿但需物流」。这是经济系统设计的成熟标志。

### S6. 统一可见性策略 (P0-5) — 防止信息泄露

单一函数 `is_visible_to(entity, player_id, tick)` 控制所有输出面 (WASM 快照、MCP、WebSocket 增量、REST API、回放)。每 tick 每玩家可见性缓存一次，所有输出面读取同一缓存 — 杜绝「快照说隐藏但 WebSocket 增量泄露」的经典 bug。双模式 (World fog-of-war vs Arena 全局可见) 定义清晰。

### S7. IDL 驱动代码生成 (P0-8) — 单一真相来源

`game_api.idl` → Rust Command enum / Validator trait / TS SDK types / MCP tool schemas / Docs / Test generators。CI 强制 `git diff --exit-code` 确保生成代码与 IDL 同步 — 不允许手写 Command 变体。这是编译器级别的契约执行。

### S8. 资源不硬编码 — 引擎核心动态化

核心引擎只操作 `HashMap<ResourceName, Amount>`，资源名由 world.toml 配置决定。动作成本通过 `ResourceRegistry::cost(action, detail)` 查询。从单资源 (Energy) 到多资源 (Crystal+Gas 星际争霸风格, Food+Wood+Stone+Gold 帝国时代风格) 不需要改引擎代码 — 改配置即可。

---

## CONCERNS (问题清单)

### D1 — Tick EXECUTE 阶段 FDB 事务规模未量化 [Severity: HIGH]

**位置**: P0-1 §3.4, DESIGN §3.2

整个 EXECUTE 阶段（所有指令校验 + ECS System 执行 + 状态写入）包裹在单个 FoundationDB 事务中：

```
txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
txn.set("/tick/{tick}/complete", true)
txn.commit()
```

FDB 事务有 5 秒上限和 ~10MB 写入上限。500 drone/玩家 × 100+ 玩家 × 每指令多 key 读写 = 可能超过单事务限制。

**分析**:
- DESIGN §7.2 提到 "每 shard 一个 engine 实例"，暗示按房间 sharding
- 但 P0-1 未描述 shard 边界与事务边界的关系
- 当前文档中事务范围是 "整个 tick 的世界状态" — 如果是单 shard 的世界切片则可行，如果是全局状态则不可扩展

**建议**: P0-1 §3.4 中明确 FDB 事务的 key 范围边界与 shard 划分的关系。添加单个事务的 key 数量估算和预算检查。如果 shard 按房间划分，每个 engine 实例的 FDB 事务应只覆盖其 shard 内的房间。

---

### D2 — 快照序列化无输入大小上限 [Severity: MEDIUM]

**位置**: P0-1 §2.3, P0-4 §6

P0-2 §1.1 定义了 WASM 输出上限 (256KB, 深度≤10)。P0-4 §6 定义了 WASM 线性内存上限 (64MB)。但 WASM 的 `tick()` 函数输入——快照 JSON ——没有定义输入大小上限。

**场景**: 一个有 100 玩家的世界，每个玩家 500 drone + 200 建筑。单房间快照可能包含 ~5000 个实体。序列化为 JSON 后可能达到数 MB。如果多个房间可见，快照大小会进一步膨胀。64MB 线性内存可能被快照 JSON 大量占用，留给实际计算的空间不足。

**建议**: 定义快照 JSON 的输入大小上限 (建议 8-16MB)，超出时引擎拒绝该 tick 并降级该玩家。在 P0-4 §6 的资源预算总表中添加 "快照输入上限" 行。

---

### D3 — Rhai Mod Actions 校验逻辑未文档化 [Severity: MEDIUM]

**位置**: DESIGN §8.7, P0-7 §3

Rhai 模组通过 `actions.deduct_resource()` / `actions.award_resource()` / `actions.modify_entity()` 修改世界状态。DESIGN §8.7 说 `actions.apply(world)` 是 "经校验后写入"，但校验的具体规则未定义。

**风险**:
- 如果 Rhai 脚本中出现整数溢出 (在 `fixed<u32,N>` 定点运算中多步乘法累积)，可能产生错误值
- `modify_entity()` 的合法修改范围未定义——能改什么 component？能改到什么值？
- Rhai 预算是 100 actions/tick + 100ms 墙钟 — 限制了破坏规模但未防止数据损坏

**同时存在文档不一致**: DESIGN §8.7 的预算表包含 "AST 节点数 10,000/tick"，但 P0-7 全文未提及 AST 节点限制。

**建议**:
1. 在 P0-7 中补充 Rhai `actions` 的校验规则文档 (每个 action 的 pre-condition 检查)
2. 将 AST 节点限制从 DESIGN 同步到 P0-7
3. 定义 `modify_entity()` 允许修改的 component 白名单和值域约束
4. 考虑为 Rhai 模组添加 `state_checksum` 校验——模组执行前后的世界 checksum 变更必须可归因

---

### D4 — 玩家资源竞争中的信息不对称 [Severity: LOW]

**位置**: P0-1 §3.2

先到先得的资源竞争规则中，"先到" 由种子洗牌决定，玩家无法预测本 tick 的排序位置。但 `Resource Contention` 文档未讨论：玩家是否有 API 可以查询 "本 tick 我的排序位置"？

如果玩家**不能**查询，则竞争纯粹是随机的——策略深度被削弱。如果玩家**能**查询，则他们可以在排序靠前时选择竞争性指令，靠后时选择非竞争性指令——这创造了一个有趣的元游戏层次。

当前文档暗示不可预测性是设计目标 ("玩家无法提前知道自己在当前 tick 的排序位置")。这本身是有效设计选择，但应明确说明这是刻意为之，并评估其对策略深度的影响。

---

### D5 — Tick Abandon 后 fuel 退还的完整性 [Severity: LOW]

**位置**: P0-1 §3.4, §6.1

tick abandon 时 "消耗的 CPU fuel 退还玩家"。但如果 tick 内部已部分执行了一些 host function 调用 (如 path_find 消耗了 fuel)，这些消耗是在 FDB 事务内部的。FDB 事务回滚时，Wasmtime 的 fuel 计数器是否也回滚？

**分析**: Wasmtime fuel metering 是进程内状态，不在 FDB 事务范围内。如果 10 个玩家各消耗了 1M fuel 做了 path_find，然后 FDB commit 失败，fuel 退还必须通过显式逻辑实现 (记录每个玩家的 fuel_consumed，abandon 时写回)。P0-1 §6.1 表格说 "CPU fuel 退还" 但未描述退还机制。

**建议**: 在 P0-1 §6.1 中补充 fuel 退还的实现机制——是 per-player fuel counter 在 tick 开始前快照、结束时 commit、abandon 时恢复？

---

## CONSISTENCY GAPS (文档间不一致)

### G1 — host_get_world_rules 在不同文档中的存在不一致

| 文档 | 是否包含 host_get_world_rules |
|------|---------------------------|
| P0-4 §3.2 (允许的 Host Function 列表) | ❌ 不包含 |
| P0-4 §8 (Query Host Function 成本表) | ✅ 包含, 1,000 fuel |
| P0-8 IDL | ✅ 包含 |
| DESIGN §5.1 | ❌ 只有 `host_get_world_config` |

**修复**: P0-4 §3.2 和 DESIGN §5.1 应添加 `host_get_world_rules`。

---

### G2 — Rhai 预算表的不一致

| 预算项 | DESIGN §8.7 | P0-7 |
|--------|------------|------|
| AST 节点数 | 10,000/tick | 未提及 |
| actions 调用次数 | 100/tick | 100/tick ✅ |
| 墙钟时间 | 100ms/tick | 未提及 |
| state.players() 迭代 | 3,000 项 | 未提及 |

**修复**: 将 DESIGN §8.7 的完整预算表同步到 P0-7，作为 Rhai 模组规范的一部分。

---

### G3 — P0-9 §7 Arena MCP_Deploy 行的歧义

P0-9 §7 表格中 MCP_Deploy 在 Arena 列显示 "❌ 赛后不可"。这表示 "赛后不可部署" 而非 "赛前可部署"——行文过于简洁。建议改为 "✅ 赛前 / ❌ 赛中+赛后"。

---

### G4 — P0-9 章节编号错误

P0-9 的章节编号序列为: §1, §2, §3, §6, §5, §7。缺少 §4。§6 "校验管线" 出现在 §3 之后, §5 "Replay 与审计" 出现在 §6 之后。应重新编号为连续的 §1-§7。

---

## ALGORITHMIC RISKS (算法风险)

### A1 — 种子洗牌的碰撞概率

P0-1 §3.1 使用 `blake3(tick_number || world_seed)` 生成洗牌种子。Blake3 输出 256-bit，碰撞概率可忽略。但种子洗牌的具体算法未指定——使用 Fisher-Yates？确定性排序网络？不同实现产生不同洗牌结果，破坏确定性。建议在 P0-1 中指定洗牌算法为 Fisher-Yates (确定性变体，基于种子生成器的序列值排序)。

### A2 — 寻路缓存失效策略

P0-2 §4.3 提到寻路结果以 `(from, to, 地形hash)` 缓存。当地形改变时 (建筑放置/拆除)，缓存中的路径可能仍在地图上存在但实际被新建筑阻挡。地形 hash 必须包含路径沿线所有格的地形状态，而不仅是起点和终点。当前文档说 "地形不变不重算"，需明确 "地形 hash" 的计算范围。

### A3 — 定点数溢出链

DESIGN §8.8 禁止 f64，全部使用 `fixed<u32,4>` (4 位小数精度, 有效范围: 0 到 429,496.7295)。多步乘法累积时：
- `room_superlinear` 应用: `rooms * (base + rooms * superlinear / FIXED_SCALE)`。rooms = 50, base = 10, superlinear = 100: 50 * (10 + 50*100/10000) = 50 * (10 + 0) = 500 — 正常。但 rooms = 500, superlinear = 10000: 500 * (10 + 500*10000/10000) = 500 * 510 = 255,000 — 仍在 u32 范围内。世界配置校验应包含定点数运算的边界检查。

---

## TICK LIFECYCLE LOGIC VERIFICATION

对 P0-1 Tick 生命周期的逐阶段逻辑验证：

| 阶段 | 边界条件 | 验证结果 |
|------|---------|---------|
| COLLECT 超时 | 2500ms 后未响应 → commands = [] | ✅ 宽容失败，不阻塞 |
| COLLECT WASM crash | crash/OOM → commands = []，连续 3 次 degraded | ✅ 有降级路径 |
| EXECUTE 排序 | 种子洗牌 + player_id + cmd_seq | ✅ 确定且公平 |
| EXECUTE 资源竞争 | 先到先得，耗尽后 SourceEmpty + 部分 refund | ✅ 规则明确 |
| EXECUTE FDB 失败 | 重试 3 次 → abandon → 1s 后重试 → 连续 3 次降级 | ✅ 有渐进降级 |
| BROADCAST 失败 | 不影响已提交 tick，客户端 detect gap → fetch | ✅ 解耦正确 |
| BROADCAST partial | 客户端状态暂时不一致，last_tick 检测 gap | ✅ 最终一致 |
| TickTrace 写入失败 | tick 执行完成但审计不完整 → 标记不可回放 | ✅ 不影响 gameplay |
| 降级模式退出 | 连续 10 tick 正常 → 自动退出 | ✅ 自动恢复 |

**阶段间状态一致性**: EXECUTE 阶段 FDB commit 成功后世界状态已变更，BROADCAST 阶段的任何失败不回滚。正确。

**并行安全性**: COLLECT 阶段各玩家 WASM 并行执行 (独立进程)，EXECUTE 阶段串行 (`.chain()` ECS + FDB 事务)——数据竞争隔离正确。

---

## DATA CONSISTENCY: FDB + Dragonfly 读写路径

```
写路径 (权威): EXECUTE → FDB 原子提交 → Dragonfly 缓存更新 → NATS 发布
读路径 (快取): Gateway WS → Dragonfly (热) → 未命中 → FDB (权威)
```

**一致性保证**:
- FDB 是权威源。Dragonfly 是允许滞后的非权威缓存。
- BROADCAST 阶段 Dragonfly 写入失败 → 客户端回退到 FDB 直读。正确。
- Dragonfly 缓存 stale → P0-1 §6.1 明确 "下次写入时自动刷新"。但需要确认写入时是 invalidate 还是 update——建议明确为 write-through update (写 FDB 成功后同步更新 Dragonfly，失败则 invalidate key)。

**潜在风险**: 如果 BROADCAST 阶段 Dragonfly 更新成功但 NATS 发布失败，部分客户端通过 Dragonfly 读到了新数据，部分客户端因未收到 delta 而通过 FDB polling 读到了新数据——两者一致 (都是新数据)。如果 Dragonfly 更新失败，部分客户端读到旧数据——通过 last_tick gap detection 触发主动 fetch 解决。无不一致窗口。✅

---

## REVIEW SUMMARY

| 类别 | 数量 |
|------|------|
| HIGH severity concerns | 1 (D1) |
| MEDIUM severity concerns | 2 (D2, D3) |
| LOW severity concerns | 2 (D4, D5) |
| Consistency gaps | 4 (G1-G4) |
| Algorithmic risks | 3 (A1-A3) |
| Strengths | 8 (S1-S8) |

**整体评价**: 这是我在游戏引擎领域见过的最完整的架构设计文档之一。确定性合同、Source Gate 模型、Deferred Command Model 三根支柱支撑起了整个系统的正确性。文档间的少量不一致 (G1-G4) 属于 Phase 0 冻结后各 P0 规范独立迭代的自然产物，修复成本低。D1 (FDB 事务规模) 是唯一需要在 Phase 1 前解决的架构级问题。

**建议的修复优先级**:
1. D1 — 明确 FDB 事务的 shard 边界 (Phase 1 设计前)
2. G1, G2 — 同步 host function 列表和 Rhai 预算表 (即时)
3. D3 — 文档化 Rhai actions 校验规则 (Phase 1)
4. D2 — 定义快照输入上限 (Phase 1)
5. G3, G4 — 修复 P0-9 措辞和编号 (即时)
6. A1-A3 — 算法细节补充 (Phase 1 实现前)
7. D4, D5 — 低优先级澄清 (可延后)
