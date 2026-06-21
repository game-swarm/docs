# R34 闭合验证 — Design & Economy (DeepSeek V4 Pro)

## Overall Verdict: PARTIALLY_CLOSED

7 of 12 验证项已闭合。3 项未闭合（D5/D-H4: Arena API残留tournament工具引用；D10/D-H7: Terminal功能描述跨文档不一致；D-H5: PvE faucet tier映射缺失）。另有 2 项 Residual Gap（R33 B1结构成本不一致、R33 B2 `global_deposit_delay`缺失）虽不在本轮验证范围内但代表经济权威链路仍不完整。

---

## Pass Items (CLOSED)

### ✅ B5: 经济权威源统一

| 验证项 | 状态 | 证据 |
|--------|:----:|------|
| resource-ledger as math/execution authority | PASS | `08-resource-ledger.md`:7-9 明确声明"唯一设计/数学权威"+"数学/执行顺序权威"，§8 定义与所有文档的关系 |
| design docs reference resource-ledger | PASS | `economy-balance-sheet.md`:3 "所有费率、公式以 `specs/core/08-resource-ledger.md` §2 统一参数表为唯一权威源"；§5 逐项列出权威定义位置 |
| no duplicate cost tables | PASS | `economy-balance-sheet.md`:246 "不重新定义费率或公式"；`gameplay.md` §8 引用 resource-ledger；独立成本表无一式两份 |

**备注**: B5 是关于"哪个文档是权威源"的结构性问题，已闭合。但经济参数的具体值仍有不一致（见 GAP-1, GAP-2）。

---

### ✅ D4: Standard 经济中期自维持区间

| 验证项 | 状态 | 证据 |
|--------|:----:|------|
| 2-5 rooms self-sustaining | PASS | `economy-balance-sheet.md`:187-190 汇总表：2房优化 +18/tick，3房优化小幅盈余，5房优化收支平衡 |
| no "全阶段亏损" | PASS | 1房free_upkeep +77/tick（盈余），2-10房优化代码可达正流量；仅20+房转入亏损 |
| playtest-gated标记 | PASS | `economy-balance-sheet.md`:5, 192, 200 三处标记 playtest-gated；`PLAYTEST-GATED.md` PG-4 追踪 |

**备注**: Balance Sheet 数值已从R33的全负流量重算为2-10房优化可达正流量，设计意图和 playtest-gated 约定明确。

---

### ✅ D6: Deploy 反馈 polling-only

| 验证项 | 状态 | 证据 |
|--------|:----:|------|
| swarm_get_deploy_status polling | PASS | `06-feedback-loop.md`:133 明确定义 polling 工具；`game_api.idl.yaml` L1054-1069 注册 `swarm_get_deploy_status` |
| no active event push | PASS | `06-feedback-loop.md`:140 "不提供主动事件推送/MCP 事件订阅"；事件订阅列为 Out-of-Scope |

---

### ✅ D-H1: Economy curve (by D4)

**状态**: PASS — D4闭合后 D-H1 自动闭合。`PLAYTEST-GATED.md` PG-1 追踪早期经济曲线，`economy-balance-sheet.md` 提供 1/2/3/5/10/20/50房完整收支路径。

---

### ✅ D-H2: Allied transfer direct → restricted

**状态**: PASS — `08-resource-ledger.md`:33-34 "Allied Transfer (受限)"，§2.1 定义 fee=200bp, delay=200, cooldown=500, daily_cap=GCL-scaled，§2.5 附加4项约束。`economy-balance-sheet.md`:225 "Standard 默认启用 Restricted Allied Transfer"。无免延迟直转路径。

---

### ✅ D-H3: Event channel (by D6)

**状态**: PASS — D6 polling-only 闭合后 D-H3 自动闭合。用户选择 B（polling-only）而非 Speaker 推荐的 A（active push），文档已体现此决策。

---

### ✅ D-H6: Naming taxonomy

**状态**: PASS — `economy-balance-sheet.md`:203-204 模式对比表使用 "Vanilla (Novice)" 统一命名，消除了 Novice/Vanilla/Standard 混用。`gameplay.md` 使用 "Vanilla Ruleset" + "Novice" 上下文区分。

---

## Fail Items (NOT CLOSED)

### ❌ D5: Arena 轻量房间制 / D-H4: Arena leaderboard

| 验证项 | 状态 | 证据 |
|--------|:----:|------|
| "房间制测试场" 设计声明 | ✅ | `modes.md`:88 "轻量房间制测试场" |
| 无天梯/无赛季/无自动匹配 | ✅ | `modes.md`:341-342 |
| room match_result only | ⚠️ | `game_api.idl.yaml` L1442-1457: `swarm_match_result` active ✅；但 tournament 工具虽标RFC仍在active list |
| leaderboard/tournament不暴露为active API | ❌ | 跨文档残留引用（见下） |

**GAP 清单**:

| 文件 | 行号 | 问题 |
|------|------|------|
| `game_api.idl.yaml` | L1527-1528 | `arena` capability profile 角色为 "Arena host / **tournament admin**" — 与 "无天梯" 矛盾 |
| `design/interface.md` | 30 | `swarm_tournament_create`, `swarm_tournament_status`, `swarm_match_result` 列为主动能，无RFC标记 |
| `specs/reference/mcp-tools.md` | 64 | "Arena 工具包括 swarm_tournament_create...swarm_match_result" — 将tournament列为Arena核心工具 |
| `specs/gameplay/06-feedback-loop.md` | 337 | "排行榜按 league 分区：Human/WASM、AI-assisted、AI tournament" — 需 league/tournament 基础设施 |
| `specs/reference/api-registry.md` | 321-324 | `swarm_tournament_create/precommit/status` 注册为 active 工具（Arena profile），无RFC标记 |

**分析**: `game_api.idl.yaml` 已为 leaderboard/tournament 添加 RFC-LEADERBOARD/RFC-TOURNAMENT 标记和 "P0 不实现 / ERR_FEATURE_GATED" 注释，这是正确的方向。但 (1) design/interface.md, mcp-tools.md, api-registry.md, feedback-loop.md 仍将 tournament/leaderboard 列为 active 或 core Arena 功能；(2) game_api.idl.yaml 的 arena capability profile 仍将角色描述为 "tournament admin"。

**修复**: 
1. `design/interface.md`:30 将 tournament 工具标为 RFC 或移出核心功能表
2. `mcp-tools.md`:64 删除 tournament 引用，仅保留 `swarm_match_result`
3. `api-registry.md`:321-324 为 tournament 工具添加 `rfc_status: TOURNAMENT` 标记
4. `06-feedback-loop.md`:337 删除 league/tournament 引用
5. `game_api.idl.yaml` L1527-1528 将 "tournament admin" 改为 "Arena host" 或删除

---

### ❌ D10: Terminal identity/logistics / D-H7: Terminal function

| 验证项 | 状态 | 证据 |
|--------|:----:|------|
| Terminal = identity/logistics (gameplay.md structure def) | ✅ | `gameplay.md`:178 "跨世界身份同步与日志交换节点" |
| Terminal = identity/logistics (world-rules.md structure def) | ✅ | `world-rules.md`:760 "终端——跨世界身份同步与日志交换节点" |
| Terminal = identity/logistics (world-rules.md RCL table) | ✅ | `world-rules.md`:838 "跨世界身份同步/日志交换" |
| no market trading description | ❌ | 跨文档残留 "市场交易" 引用（见下） |

**GAP 清单**:

| 文件 | 行号 | 问题 |
|------|------|------|
| `design/gameplay.md` | 299 | "世界本地存储的资源可通过 Terminal **在市场交易**（需物流可达）" |
| `design/gameplay.md` | 291 | 全局存储模型图中标注 "可**市场交易**" |
| `design/engine.md` | 81 | RCL表中 Terminal 说明为 "**市场交易**" |
| `specs/core/07-world-rules.md` | 632-633 | 存在第二处 Terminal 定义为 "**终端——市场交易接口**" (与 line 760 "身份同步" 描述冲突) |

**分析**: R33 H3 的修复是**部分性**的——`gameplay.md` §2.2 和 `world-rules.md` §7.2 的结构定义已更新为 "身份同步/日志交换"，但四个位置仍保留 "市场交易" 描述。(gameplay.md L412 正确地将 "市场交易" 标记为 "RFC 占位 — 不在当前设计范围内"，但 L299 和 L291 未同步删除。)

**修复**:
1. `gameplay.md`:299 将 "可通过 Terminal 在市场交易" 改为 "可通过 Terminal 进行跨世界身份同步与日志交换"
2. `gameplay.md`:291 将 "可市场交易" 改为 "可跨世界同步"
3. `engine.md`:81 将 "市场交易" 改为 "跨世界身份同步/日志交换"
4. `world-rules.md`:632-633 将 "市场交易接口" 改为 "跨世界身份同步与日志交换节点"（同步 line 760）

---

### ❌ D-H5: PvE faucet table

**状态**: NOT CLOSED — Speaker R33 D-H5 标记为"直接修复：建立 NPC/entity_tier → PvEAward budget 映射"，但映射表未创建。

**当前状态**:
- `modes.md` §9.0: NPC类型（Creep/Guardian/Merchant/Swarmling）和掉落表独立存在
- `08-resource-ledger.md` §3: PvE Budget 4维账本（Global/Zone/Player/Event）独立存在
- 两处之间无显式映射表

**所需**: 建立如下形式的映射表:
```
| NPC Tier | NPC Types | PvEAward Budget Cap | Applies To |
|----------|-----------|---------------------|------------|
| Tier 1   | Creep, Swarmling | 50% of Zone cap | Zone budget |
| Tier 2   | Guardian | 30% of Global cap | Global budget |
| Tier 3   | Merchant | 10% of Event budget | Event budget |
```

建议放置位置: `08-resource-ledger.md` §3 末尾，或 `modes.md` §9.0 NPC掉落经济小节。

---

## Residual Gaps (源自R33，非本轮验证范围但阻止完全闭合)

### GAP-1: Structure Build Costs — Triple Inconsistency (R33 B1)

R33 Critical B1（结构建造成本三文档不一致）**未修复**：

| Structure | gameplay.md §2.2 | world-rules.md §7.2 | economy.idl.yaml / api-registry |
|-----------|:-----------:|:--------------:|:----------------:|
| Spawn | **300** | **200** | **300** |
| Extension | **200** | **50** | **200** |
| Tower | **800** | **200** | **800** |
| Link | **400** | **300** | **400** |
| Extractor | **600** | **800** | **600** |
| Terminal | **1200** | **500** | **1200** |
| Observer | **500** | **300** | **500** |

7/13结构在3文档中数值不一致。`gameplay.md` 与 `economy.idl.yaml` 多数对齐（仅 Extractor 例外），但 `world-rules.md` 为独立偏离源。

### GAP-2: `global_deposit_delay` Missing from Resource Ledger (R33 B2)

R33 Critical B2 **未修复**。`08-resource-ledger.md` §2.1 统一参数表仍仅定义单一的 `global_transfer_delay = 100 tick`（line 77），未区分 `global_deposit_delay = 10` 和 `global_withdraw_delay = 100`。

其他文档正确区分了双向延迟:
- `gameplay.md`:311 = 10, L313 = 100
- `economy-balance-sheet.md`:214-215 = 10/100

但"唯一经济权威"资源账本中 `deposit_delay = 10` 缺席，执行层若仅读取 resource-ledger 将使用 deposit_delay = 100（错误）。

---

## CrossCheck

| ID | 问题 | 目标方向 | 关注点 |
|----|------|----------|--------|
| CX-N1 | Structure costs triple-inconsistency + Terminal功能 + global_deposit_delay — 三文档分叉 → | **Architect/Governance** | 检查 R33 B1/B2/H3 是否进入下一轮修复优先队列；这三个R33 CRITICAL/HIGH发现至今未闭合 |
| CX-N2 | game_api.idl.yaml Arena capability profile 仍引用 "tournament admin" → | **API/DX** | 检查 Arena capability profile (L1526-1528) 的角色描述是否与 modes.md 设计一致 |
| CX-N3 | api-registry.md 中 tournament 工具缺少 rfc_status 标记 → | **API/DX** | 同步 api-registry.md L321-324 与 game_api.idl.yaml 的 RFC 标记状态 |
| CX-N4 | economy.idl.yaml missing `global_deposit_delay` → | **API/DX** | 若 resource-ledger 为经济权威，economy.idl.yaml 应同步增减字段（deposit 与 withdraw 分列） |
| CX-N5 | PvE faucet mapping 缺位 → | **Architect** | 检查 NPC spawn 系统是否在 PvE budget 裁决前查询 tier 映射；若无映射，PvE budget cap 无法正确裁决 per-NPC-type 产出 |

---

## 统计

| 状态 | 数量 | 项目 |
|------|:----:|------|
| CLOSED | 7 | B5, D4, D6, D-H1, D-H2, D-H3, D-H6 |
| NOT CLOSED | 3 | D5/D-H4, D10/D-H7, D-H5 |
| Residual Gap | 2 | R33 B1 (structure costs), R33 B2 (deposit_delay) |
| CrossCheck | 5 | CX-N1..CX-N5 |