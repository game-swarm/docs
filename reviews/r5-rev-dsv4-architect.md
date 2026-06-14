# R5 最终检查 — Architect 评审 (rev-dsv4-architect)

> **评审人**: DeepSeek V4 Pro — Architect Reviewer
> **评审日期**: 2026-06-14
> **评审范围**: /data/swarm/docs/design/DESIGN.md + /data/swarm/docs/specs/p0/ (全部 9 份)
> **评审方法**: 全量交叉比对 — 算法验证、数据流一致性分析、合同对齐

---

## Verdict: CONDITIONAL_APPROVE

设计整体已达可实施状态。核心合同（deferred command model, source gate, determinism contract, MCP 不作为 gameplay channel）跨文档一致。未发现设计级架构缺陷或残留旧合同。以下 8 项为文档层面的修正项，全部为非阻断性。

---

## Strengths

1. **Deferred Command Model 统一锁定**: P0-4 §3、P0-8 IDL、DESIGN §5 三处一致——`tick() → Command[]` JSON 延迟模型，禁止 imperative host function。无旧 `host_move` 残留。

2. **Source Gate 完整**: P0-9 的 12 来源矩阵 (WASM/MCP_Deploy/MCP_Query/Admin/Replay/TestHarness/Tutorial/Deploy/Rollback/RuleMod/Simulate/DryRun) 覆盖所有入口，auth context 服务端注入不可伪造。Phase 0 checklist 已标记完成。

3. **MCP 定位清晰**: P0-3 §1 明确 "MCP 与 Web UI 同级"，DESIGN §4.2 明确 "MCP 不做游戏动作"。全文无 `swarm_move`/`swarm_attack` 等旧游戏动词。McpPlayerExecutor 痕迹已彻底清除。

4. **Determinism Contract 严密**: DESIGN §8.8 锁定 ChaCha12 PRNG、Blake3 hash、禁 f64、IndexMap、ECS .chain()。P0-7 §8 重申 Rhai 禁用浮点。种子洗牌算法 (P0-1 §3.1) 同时满足确定性与公平性。

5. **Fuel Refund 安全模型**: P0-2 §7 的退还时序 (同 tick 不放大)、退还上限 (MAX_FUEL × 10%)、滥用检测 (连续 3 tick > 80% 触发 throttle) 设计完整。

---

## Concerns — 修正清单

### D1 [Contradiction] FDB 快照频率不一致

| 位置 | 内容 |
|------|------|
| DESIGN §3.2 Broadcast | "每隔 N tick 记录完整世界快照到 FDB（回放用）" |
| P0-1 §6.1 | 每 tick 写入 `/tick/{N}/state` |

**分析**: P0-1 是 Phase 0 冻结规范，每 tick 持久化世界状态是回放和确定性的前提。DESIGN 的"每隔 N tick"与 P0-1 直接矛盾。若采用"每 tick"，则 DESIGN 错误；若采用"每 N tick"，则回放无法逐 tick 验证。

**修正**: DESIGN §3.2 Broadcast 行改为与 P0-1 一致——每 tick 提交完整状态。可保留"额外每 N tick 快照"作为优化点标注，但主记录必须是每 tick。

---

### D2 [Inconsistency] P0-4 host function 列表缺失 `host_get_world_rules`

| 位置 | 内容 |
|------|------|
| P0-4 §3.2 | 列出 4 个 host function: `get_terrain`, `get_objects_in_range`, `path_find`, `get_world_config` |
| P0-4 §8 成本表 | 包含第 5 个: `host_get_world_rules` (cost: 1,000 fuel) |
| P0-8 IDL | 同时定义 `get_world_config` 和 `get_world_rules` |
| DESIGN §5.1 | 列出 5 个 host function（含 `host_get_world_rules`） |

**分析**: P0-4 §3.2 的函数声明列表与自身的成本表 (§8)、P0-8 IDL、DESIGN §5.1 均不一致。`host_get_world_rules` 是 AI 玩家和 WASM 代码查询世界规则的关键入口，不应遗漏。

**修正**: P0-4 §3.2 追加:
```rust
fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;
```

---

### D3 [Contradiction] DESIGN §8.7 i18n 示例使用 f64 违反确定性合同

| 位置 | 内容 |
|------|------|
| DESIGN §8.7 mod.toml (line 890) | `room_superlinear = { type = "fixed<u32,4>", ... }` |
| DESIGN §8.8 Determinism Contract | "数值: 整数 + 定点数。禁 f64。Rhai 模组脚本同样禁用浮点" |
| DESIGN §8.7 i18n 示例 (line 1080) | `[config.room_superlinear]\ntype = "f64"\ndefault = 0.1` |

**分析**: 同一参数 `room_superlinear` 在 mod.toml 示例中用 `fixed<u32,4>`（正确），在 i18n 示例中用 `f64`（违反 §8.8 确定性合同）。浮点类型跨 wasmtime/CPU 架构不可重现。

**修正**: Line 1080 的 i18n 示例改为 `type = "fixed<u32,4>"`，`default` 改为定点数表示（如 `default = 1000` = 0.1000）。

---

### S1 [Structure] DESIGN.md 重复 §10

| 位置 | 标题 |
|------|------|
| Line 1288 | `## 10. World 模式 vs Arena 模式` |
| Line 1305 | `## 10. 贡献指南` |

**修正**: 将 Line 1305 改为 `## 11. 贡献指南`。Line 1288 之后的所有子章节无需调整。

---

### S2 [Structure] P0-1 Tick 协议 §6 子节编号错乱

| 位置 | 编号 |
|------|------|
| Line 261 | `### 6.3 回放协议` |
| Line 262 | `### 6.1 记录` |
| Line 274 | `### 6.2 回放执行` |

**修正**: 重新编号为 §6.1 回放协议(概述) → §6.2 记录 → §6.3 回放执行。

---

### S3 [Structure] P0-9 缺失 §6

P0-9 从 §5 直接跳到 §7。无内容缺失（§5→§7 逻辑连续），仅编号跳号。

**修正**: 将 §7 改为 §6，或插入占位章节。

---

### G1 [Gap] DESIGN §4.1 MCP 工具表不完整

DESIGN §4.1 列出的 MCP 工具与 P0-3 相比缺少:

| 缺失工具 | P0-3 位置 |
|---------|----------|
| `swarm_list_modules` | §4.1 |
| `swarm_inspect_room` | §4.3 |
| `swarm_get_replay` | §4.3 |
| `swarm_get_world_rules` | §4.4 |
| `swarm_simulate` | §4.4 |

**分析**: DESIGN 声明 "详见 specs/p0/03-mcp-security-contract.md"，所以 P0-3 是权威源。但 DESIGN 作为架构全景图，MCP 工具表应保持与 P0-3 一致以避免读者困惑。

**修正**: DESIGN §4.1 表格追加上述 5 个工具，或添加注释 "完整列表见 P0-3"。

---

### G2 [Gap] DESIGN §8.7 WASM 侧 host function 列举遗漏

| 位置 | 内容 |
|------|------|
| DESIGN §8.7 (line 791-792) | "通过查询 host function（get_terrain、get_objects_in_range、path_find、get_world_config）读取世界状态" |
| DESIGN §5.1 | 列出全部 5 个 host function（含 `host_get_world_rules`） |

**分析**: Line 791-792 仅列 4 个函数，遗漏 `get_world_rules`。这与其他所有引用点（DESIGN §5.1、P0-8、P0-4 §8）不一致。`get_world_rules` 是 AI 玩家和 WASM 模块查询世界规则（mods、配置）的唯一入口——遗漏此函数意味着玩家人代码和 AI 无法感知世界级规则变化。

**修正**: Line 792 追加 "、get_world_rules"。

---

## Consistency Gaps — 数据流追踪

### 已验证一致（无问题）:

| 合同 | DESIGN | P0-1 | P0-2 | P0-3 | P0-4 | P0-5 | P0-7 | P0-8 | P0-9 |
|------|--------|------|------|------|------|------|------|------|------|
| Tick 三阶段 (COLLECT→EXECUTE→BROADCAST) | ✅ §3.2 | ✅ §1 | — | — | — | — | — | — | — |
| 种子洗牌算法 | ✅ §3.2 | ✅ §3.1 | — | — | — | — | — | — | — |
| Deferred Command Model | ✅ §5 | — | — | — | ✅ §3 | — | — | ✅ | — |
| 禁 mutating host func | ✅ §5.2 | — | — | — | ✅ §3.3 | — | — | ✅ | — |
| Fuel metering (10M) | — | — | ✅ §7.3 | — | ✅ §6 | — | — | — | — |
| 可见性 is_visible_to | — | — | — | ✅ §3 | — | ✅ §1 | — | — | — |
| Rhai 禁浮点 | ✅ §8.8 | — | — | — | — | — | ✅ §8 | — | — |
| Source Gate auth 注入 | — | — | — | — | — | — | — | — | ✅ §3 |
| Command Validation Pipeline | — | — | ✅ §1 | — | — | — | — | ✅ | — |
| Resource dynamic (HashMap) | ✅ §3.1 | — | — | — | — | — | ✅ §3 | — | — |
| FDB commit in EXECUTE | ✅ §3.2 | ✅ §3.4 | — | — | — | — | — | — | — |
| BROADCAST failure no rollback | — | ✅ §4.2 | — | — | — | — | — | — | — |
| TickFailure degraded mode | — | ✅ §6.2 | — | — | — | — | — | — | — |

### 已验证不符（上文 D1-D3, G1-G2 已覆盖）:

- D1: FDB 快照频率 (DESIGN vs P0-1)
- D2: P0-4 host functions (内部 §3.2 vs §8)
- D3: f64 类型 (DESIGN §8.7 i18n vs §8.8)
- G1: MCP 工具表 (DESIGN §4.1 vs P0-3)
- G2: WASM host func 列举 (DESIGN §8.7 vs §5.1)

---

## Algorithmic Risks — 大规模下计算爆炸评估

| 组件 | 风险 | 缓解 |
|------|------|------|
| 可见性计算 O(P × E) | 🟡 中等 | P0-5 §5: 每 tick 每玩家缓存一次 HashSet<EntityId>。快照按房间序列化再按玩家过滤——非 O(P×E) |
| 种子洗牌 O(P log P) | 🟢 低 | Fisher-Yates shuffle over player count (~10K max)，远小于 tick budget 500ms |
| 寻路缓存 (path_find) | 🟢 低 | P0-2 §4.3: 按 (from, to, 地形hash) 缓存，地形不变不重算。每玩家每 tick 限 10 次 |
| FDB 每 tick 全量提交 | 🟡 中等 | 500 drone × 1000 players = 500K entities。P0-1 §3.4 已设计 3 次重试 + 降级模式。Phase 3 需做 sharding 性能验证 |
| Rhai AST 执行 | 🟢 低 | P0-7 已设硬限制: 10K AST nodes/tick, 100 actions/tick, 100ms wall time。连续超限自动禁用 |

**结论**: 设计层面已对核心计算路径做了预算约束。FDB 提交的扩展性是 Phase 3 实现级问题，不在 Phase 0 合同层面。

---

## 最终裁决

**CONDITIONAL_APPROVE** — 8 项修正建议，全部为文档级：

| ID | 类型 | 严重度 | 修正目标 |
|----|------|--------|---------|
| D1 | Contradiction | ⚠️ 中 | DESIGN §3.2 → 对齐 P0-1（每 tick 记录状态） |
| D2 | Inconsistency | ⚠️ 中 | P0-4 §3.2 → 补充 `host_get_world_rules` |
| D3 | Contradiction | ⚠️ 中 | DESIGN §8.7 line 1080 → f64 改 fixed<u32,4> |
| S1 | Structure | 🔹 低 | DESIGN line 1305 → §11 |
| S2 | Structure | 🔹 低 | P0-1 §6 子节重编号 |
| S3 | Structure | 🔹 低 | P0-9 补 §6 或重编号 §7 |
| G1 | Gap | 🔹 低 | DESIGN §4.1 → 补全 MCP 工具表 |
| G2 | Gap | 🔹 低 | DESIGN §8.7 line 792 → 补充 get_world_rules |

**无架构级阻断项。修正后可直接进入 Phase 1 实现。**

---

## 审查轨迹

| 步骤 | 操作 |
|------|------|
| 1 | 全量读取 DESIGN.md (1346 行) |
| 2 | 全量读取 9 份 P0 规范 |
| 3 | 交叉比对: 12 项核心合同逐文档验证 |
| 4 | 结构审计: 章节编号、重复内容 |
| 5 | 旧合同扫描: McpPlayerExecutor, host_move 等残留 |
| 6 | gap 分析: DESIGN vs P0 覆盖度 |
| 7 | 算法风险评估: 大规模路径 |

---

*reviewed by rev-dsv4-architect (DeepSeek V4 Pro — Architect Reviewer)*
*2026-06-14*
