# R4 Review: Game Designer — DeepSeek V4 Pro

**回合**: Round 4
**评审对象**: `/data/swarm/docs/design/DESIGN.md` + `/data/swarm/docs/specs/p0/` 全部
**评审人**: DeepSeek V4 Pro (Game Designer Reviewer)
**日期**: 2026-06-14
**前次评审**: R3 — CONDITIONAL_APPROVE, 2 Freeze Blockers (G1, G5)

---

## Verdict: CONDITIONAL_APPROVE → 转向 APPROVE

★★★★☆ → 两个 R3 Freeze Blocker 已实质闭合。文档一致性缺陷（i18n 示例仍含 f64）为 cosmetic，不阻碍 Phase 0 冻结。物流模型深度令人满意，模组系统设计 space 明确但 Tier 安全模型未落纸。5 项 Fresh Ideas 供 Phase 1-2 参考。

---

## Strengths

### S1 — G1 全局存储反制机制完整且有策略深度

R3 时 G1 是头号 Freeze Blocker：全局存储可被垄断玩家用于市场操纵。当前 DESIGN §8 实现了**三层反制**，每一层都创造非平凡策略权衡：

1. **累进存储税** (Progressive Storage Tax): 0-30% 免税 / 30-60% 0.01% / 60-85% 0.05% / 85-100% 0.20% per tick。在 100K 容量上限下，满仓持有者每 tick 损失 200 单位——约 6000/分钟。这不是禁止囤积（那会消除策略），而是让囤积有**价格**。玩家需要权衡「为了市场影响力囤积」vs「持有成本侵蚀利润」。

2. **本地存储隐匿性** (Stealth Advantage): 本地存储完全私有——敌方无法获知你的建筑中存了多少资源。结合全局存储的「排行榜区间可见 + 市场挂单暴露部分余额」，创造了一个信息博弈层：你把资源放在 hide-in-plain-sight（本地建筑，物理可被摧毁）还是公开但安全的全局存储？当 PvP 允许袭掠建筑时，这种权衡是真实的。

3. **转换运输时间** (No Teleport): local→global 默认 10 tick (30s)，global→local 默认 5 tick (15s)。关键设计决策：`transfer_to_global_time` 和 `transfer_from_global_time` 不可为 0——防止瞬移补给使全局存储成为战斗中的即时弹药库。运输中的资源处于「运输中」状态，可被敌方巡逻 drone 拦截（PvP 启用时）。

**P0-8 IDL 覆盖**: `TransferToGlobal` 和 `TransferFromGlobal` 已作为一等指令进入 IDL，含 validator、cost、duration。`global_storage_tax_tiers` 进入世界配置。这不再是 «missing from IDL» 的状态。

**策略深度分析**: 当前设计下，不存在 dominant strategy。纯囤积全局 → 累进税消耗利润。纯本地存储 → 无法跨房间灵活调配、无法市场交易（除非通过 Terminal）。混合模式需要玩家在每个 tick 做出物流决策：多少转全局用于部署费/市场？多少留本地用于建造+隐匿？

### S2 — G5 Rhai f64 已闭合

DESIGN §8.8 Determinism Contract 明确：

> "禁 f64（跨平台/编译器非确定）。游戏引擎数值用 `i64 × 精度因子`。**Rhai 模组脚本同样禁用浮点**——所有模组参数必须声明为 `u32`/`i64`/`fixed<u32,N>` 定点类型，Rhai 引擎侧关闭浮点运算能力。"

模组配置示例中 `room_superlinear` 类型已从 R3 的隐式 f64 转换为 `fixed<u32,4>`。Rhai tick_end.rhai 示例中使用 `FIXED_SCALE` 进行定点数除法。

跨平台确定性保证：定点整数运算在所有平台（x86-64/ARM64/RISC-V）上产生相同结果——满足回放要求。

### S3 — 物流模式三态递进设计成熟

三种物流模式覆盖了从新手到硬核的完整光谱：

| 模式 | 核心体验 | 目标玩家 |
|------|---------|---------|
| A: 无物流 | drone 采集→即时全局可用 | 新手、Arena 快节奏 |
| B: 轻物流 (默认) | 采集→本地→1%税转全局→5%返还 | 标准 World 体验 |
| C: 硬核物流 | 全部物理存在，Carry drone 运输 | Factorio 爱好者 |

模式之间的切换不是连续的数值调整而是**质变**——C 模式下整个游戏的经济维度从「管理数值」变为「管理物理流」。这是正确的设计：不是给玩家一个滑条让他们自己找平衡点，而是提供三条差异化的体验路径。

**本地/全局双向转换**的成本不对称（1% vs 5%）也有博弈意义：鼓励玩家保持资源在本地（降低系统通胀压力），同时对「紧急调拨」设置溢价。

### S4 — 模组系统设计 space 定义清晰

Rhai 模组系统构成完整的设计 space：

- **Hook 点**: `init` (加载一次), `tick_start`, `tick_end` (每 tick)
- **能力边界**: `deduct_resource`, `award_resource`, `modify_entity`, `emit_event`——经济操作+事件，不触及核心战斗/移动管线
- **预算约束**: AST 节点 10K/tick, actions 100/tick, state.players() 3K 迭代, 墙钟 100ms
- **故障模式**: 连续 10 tick 超限 → 自动禁用
- **配置可发现性**: `swarm mod config` + i18n 多语言描述 + WASM 侧 `Game.world.rules()` 查询
- **发布渠道**: 模组市场 + fork/PR 社区模型

**设计 space 的边界感好**：模组不触碰核心 ECS pipeline，actions 经引擎校验后应用，记录到 TickTrace 保证可审计性。这避免了 Minecraft 模组生态中「一个模组崩溃拖垮整个服务器」的问题。

### S5 — P0-9 Source Gate 矩阵完整闭合

R3 时 gpt-security 标记 P0-9 为未闭合 (仅 WASM/MCP_Deploy/MCP_Query 三个 source)。现在 12 个 source 的 capability/budget/visibility 矩阵完整定义，Tutorial source 有独立 namespace 隔离约束。这是设计完整度显著提升的信号。

---

## Concerns

### C1 — 模组系统 Tier 安全模型未落纸 (Medium)

我的 R3 Fresh Idea I2 提出 Tier 0/1/2 分级安全模型，Speaker 评为 ★★★ 优先级。当前 mod.toml 格式仅包含 `dependencies` 和 `conflicts` 字段，缺乏 `tier` 声明和对应的安装门槛：

```
Tier 0 (Economy): deduct/award_resource, emit_event — 任何服主
Tier 1 (Mechanics): modify_entity — Tier 0 + 代码审查签名
Tier 2 (World Gen): 注册新 ECS component — 引擎版本白名单 + 核心签名
```

没有 tier 机制，服主可能无意中安装一个「声称只扣资源」实际 `modify_entity` 大量实体的模组。虽然 actions 有校验，但 `modify_entity` 本身的破坏半径远大于 `deduct_resource`。建议在 Phase 1 实现时纳入 grading。

### C2 — 运输中资源拦截机制未定义 (Low-Medium)

DESIGN 描述 "运输期间资源处于「运输中」状态——可被敌方巡逻 drone 拦截（需 PvP 启用）"，但拦截的机制未定义：

- 是自动（巡逻 drone 经过运输路线即触发）还是主动（需 `intercept` 命令）？
- 拦截成功率如何计算？涉及哪些 body parts (Attack? Scout?)？
- 拦截结果是全部获取还是部分？
- 拦截事件是否通知双方？

这不是 Phase 0 阻断项——运输拦截在 PvP 启用时才相关，Phase 6 才实现战斗。但若运输时间被配置为 0（虽然文档说 "不可为 0"，但校验在实现层面），拦截机制也需要 fallback 定义。

### C3 — 文档内部 f64 残留 (Cosmetic)

DESIGN §8.7 的 i18n 示例中，`room_superlinear` 仍声明为 `type = "f64"` 且 `default = 0.1` (line 1072-1076)：

```toml
[config.room_superlinear]
type = "f64"
default = 0.1
min = 0.0
max = 10.0
```

而同一节的早期 mod.toml 示例使用 `type = "fixed<u32,4>", default = 1` (line 883)。这是 i18n 示例未随 Determinism Contract 同步更新。非功能问题，但在 Phase 0 Frozen 之前应统一，防止实现者混淆。

### C4 — 多房间物流路径未定义 (Low)

当资源在房间 A 的本地存储中，房间 B 需要这些资源时：
- 是否必须经过全局存储中转（local A → global → local B，承受两次转换损耗）？
- 是否可以直接 Carry drone 跨房间运输（物理移动，无需转换损耗但需要物理路径 + 防御）？
- 市场交易是否 per-world 还是 per-room？

DESIGN §8 的物流模式部分未涉及多房间场景。这可以在 Phase 3（多房间实现）时补充，但设计层面提前明确可避免实现时的返工。

### C5 — `swarm_validate_plan` 与 `swarm_simulate` 的语义重叠 (Low)

P0-6 §3.1 列出 `swarm_validate_plan` 为 MCP 发现型 verb（"如果我提交这些指令，会成功吗？"），而 P0-3 §4.4 列出了 `swarm_simulate`（离线模拟）。两者功能边界模糊——`validate_plan` 是 snapshot-bound dry-run，`simulate` 是多 tick 预测。R3 Speaker FB-5 决议中建议将 `validate_plan` 改为 "snapshot-bound non-authoritative dry-run" 或删除并交由 `swarm_simulate` 替代。当前文档中两者并存但未明确关系。

---

## Missing (设计缺口)

1. **运输拦截机制**: 见 C2。Phase 6 实现前需完整设计。
2. **多房间物流路径**: 见 C4。Phase 3 前需明确 global↔local 在多房间下的行为。
3. **模组 Tier 声明格式**: 见 C1。mod.toml 缺少 `tier` 字段和对应的能力约束定义。
4. **tick_start 钩子示例**: mod system 声明了 `tick_start.rhai` 存在但未给示例，仅展示了 tick_end。
5. **模组间通信**: 两个模组能共享状态吗？能读取其他模组 emit 的事件吗？当前设计未涉及。
6. **市场 per-room vs per-world**: 市场的作用域未在物流章节中明确。

---

## Strategy Depth Analysis

### 策略空间维度

| 维度 | 深度 | 说明 |
|------|------|------|
| **时序** | ★★★★ | 种子洗牌 + 先到先得 + 每 tick 重新评估局势 |
| **物流** | ★★★★★ | 三模式递进 + 累进税 + 隐匿性 + 运输时间四层权衡 |
| **信息** | ★★★★ | fog-of-war 分层 + 本地存储隐匿 + Arena 延迟公开回放 |
| **经济** | ★★★★ | 多资源类型 + 资产配置（本地/全局）+ 市场交易 |
| **构建** | ★★★ | body part 组合 + 建筑布局，深度来自资源约束 |
| **战斗** | ★★★ | PvP/PvE 基础完备，战术深度待 Phase 6 细化 |

### Dominant Strategy 检查

在默认 World 模式（物流模式 B、PvP 启用）下，检查潜在 dominant strategy：

- **纯囤积全局存储**: ❌ 累进税 + 运输损耗使长期囤积无利可图
- **纯本地存储分散囤积**: ❌ 市场交易受限 + 跨房间调配困难 + 物理可被摧毁
- **快速扩张殖民地**: ❌ Rhai `empire-upkeep` 模组的超线性维护费创造软天花板
- **高频代码更新**: ❌ `code_update_cost` + `code_update_cooldown` + `code_update_window` 三约束
- **种子洗牌利用**: ❌ 每 tick 不可预测洗牌使玩家无法针对排序优化

**结论**: 当前设计下不存在明显的 dominant strategy——每个策略维度都有有意义的权衡。

### 纳什均衡分析 (World 模式 PvE + PvP)

在混合人类+AI 玩家的 World 模式中：
- PvE 内容（Source 采集、建造）是正和博弈——所有玩家可同时受益
- PvP 内容（领土争夺、资源袭掠）是零和/负和博弈
- 持久世界中，纳什均衡倾向于**领土稳定 + 经济优化**而非无限军备竞赛——因为维护费超线性增长使大帝国天然不稳定
- AI 玩家与人类玩家的纳什均衡相同——两者共享 WASM 执行模型，无信息优势差异

---

## Fresh Ideas

### FI-1 — 模组 Tier 声明 + 能力门 (延续 R3 I2)

```toml
# mod.toml
[meta]
tier = 0  # 0=Economy, 1=Mechanics, 2=WorldGen

[capabilities]
deduct_resource = true
award_resource = true
emit_event = true
modify_entity = false  # 需要 tier ≥ 1
register_component = false  # 需要 tier ≥ 2
```

引擎在加载模组时对比声明能力与实际调用——声明 `modify_entity = false` 但脚本中调用 `actions.modify_entity()` → 运行时拒绝+记录。

### FI-2 — 物流热度地图 (Map Overlay)

房间地图上的可视化叠加层：运输路线粗细表示物资流量，节点颜色表示资源类型占比。对玩家：理解自身后勤瓶颈。对观战者：理解帝国经济结构。数据已在引擎侧（运输中资源有起点/终点/类型），只需渲染层。

### FI-3 — 本地存储「仓库 raid」事件

当 PvP 启用且敌方 drone 进入己方房间时，如果敌方 drone 在 Storage 建筑范围内且拥有 Attack body parts，可发起「仓库 raid」——部分本地存储资源被掠夺。这使本地存储的隐匿性 -> 被发现 -> 被掠夺形成一个完整的风险链条，让「公开的安全 vs 隐匿的风险」权衡更加真实。

### FI-4 — 模组效果预览 (Sandbox Mode)

`swarm mod try empire-upkeep --ticks=100` — 在当前世界快照上模拟安装新模组，运行 100 tick 预览经济影响。降低服主安装模组的风险感知，促进模组生态。

### FI-5 — Rhai mod 间事件总线

模组通过 `actions.emit_event("upkeep_charged", {...})` 发出事件。第二个模组可在 `tick_end.rhai` 中通过 `events.of_type("upkeep_charged")` 读取上游事件。这使模组可组合——empire-upkeep 发出维护费事件，resource-decay 收到后调整衰减速率。事件格式由发出模组的 mod.toml 声明。

---

## Verdict Summary

| 维度 | R3 | R4 | 变化 |
|------|-----|-----|------|
| G1 全局存储反制 | ❌ Freeze Blocker | ✅ 三层反制完整 | 闭合 |
| G5 Rhai f64 | ❌ Freeze Blocker | ✅ fixed-point only | 闭合 |
| 物流设计完整度 | ★★★★ | ★★★★★ | +多模式递进+转移时间 |
| 模组设计 space | ★★★★ | ★★★★☆ | +完整预算+P0-8 覆盖 |
| P0-9 Source Gate | — (缺 9 source) | ★★★★★ (12 source) | 完整闭合 |
| 文档一致性 | — | ⚠️ f64 残留 | cosmetic |

**Phase 0 冻结建议**: 修正 C3 (i18n f64 残留) 后即可宣布 Phase 0 Architecture Freeze。C1/C2/C4/C5 均为 Phase 1+ 实现期问题，不影响冻结决策。

---

*评审人: DeepSeek V4 Pro (Game Designer Reviewer)*
*输出: /data/swarm/docs/reviews/r4-rev-dsv4-designer.md*
