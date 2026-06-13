# R3 Speaker 共识裁决

**回合**: Round 3
**评审规模**: 9 人 (3 Architect × 3 Security × 3 Designer)
**模型分布**: DeepSeek V4 Pro × 3 / GPT-5.5 × 3 / Claude Opus 4.8 × 3
**日期**: 2026-06-14

---

## 一、总体裁决: CONDITIONAL_APPROVE

8/9 CONDITIONAL_APPROVE，1/9 REQUEST_MAJOR_CHANGES (gpt-security)。

gpt-security 的 MAJOR_CHANGES 经 Speaker 逐条审查后，**降级为 Phase 0 contract cleanup 范围内的修正项**——三项 concerns 均为 spec 一致性和 gap-filling 问题，不涉及架构重设计，与其他 8 位评审者的判断方向一致。

---

## 二、跨角色共识: 6 项 Freeze Blocker

以下 6 项被 ≥2 位评审者（且跨模型/角色）独立标记为 Critical/Freeze Blocker。**Phase 0 冻结前必须闭合。**

### 🔴 FB-1: Rhai f64 确定性闭合

| 支持者 | 标签 |
|---|---|
| dsv4-designer | G5 — Freeze Blocker |
| claude-designer | Freeze Blocker #2 |
| claude-architect | CA2 — Critical |
| gpt-designer | Concern |
| gpt-architect | Item 5 |

**决议**: 强制 fixed-point-only，禁用 Rhai 原生 f64。所有小数参数通过 `Fixed<u64, N>` 定点整数传递。需写入 Determinism Contract 并附带跨平台 CI 验证。

---

### 🔴 FB-2: 全局存储 dominant strategy 反制

| 支持者 | 标签 |
|---|---|
| dsv4-designer | G1 — Freeze Blocker |
| claude-designer | Freeze Blocker #1 |
| dsv4-security | H4 (refund abuse 相关) |

**决议**: 全局/本地存储之间必须存在非平凡策略权衡。可选方案：(a) 累进存储税，(b) 存储上限，(c) 本地存储独有的隐匿性/速度优势，(d) 全局↔本地转换需物流运输（非瞬移）。至少实现一项。全局/本地存储的操作 API 需进入 P0-8 IDL。

---

### 🔴 FB-3: Fuel Refund 模型安全化

| 支持者 | 标签 |
|---|---|
| dsv4-security | C1 — Critical |
| claude-security | C2 — Critical |
| claude-security | H4 — High |

**决议**: 定义退还时序（tick 内 vs tick 间）、退还上限（绝对值和比例双限）、滥用检测（连续失败率 >80% 触发 throttle）。需写入 P0-2 Command Validation Matrix。

---

### 🔴 FB-4: IDL 补全与统一

| 支持者 | 标签 |
|---|---|
| dsv4-architect | D2 — Critical (17 host function signatures) |
| claude-architect | CA3 — Critical (query funcs, snapshot JSON schema, ABI version) |
| gpt-security | Item 3 (P0-2/P0-8/9 冲突) |
| gpt-architect | Items 5, 8 (contract cleanup, API drift) |

**决议**: 
- P0-8 IDL 补全全部 host function 签名 + 返回值约定
- 新增 query 类 host functions (get_terrain, get_objects_in_range, path_find)
- 统一 P0-2/P0-4/P0-8/P0-9/DESIGN 的 auth context 注入、RawCommand 入口、player_id 来源
- 标注 IDL 为权威来源，手写列表加 "以 IDL 为准"

---

### 🔴 FB-5: Tick 输出 Schema 校验

| 支持者 | 标签 |
|---|---|
| claude-security | C1 — Critical |
| gpt-security | Item 1 (swarm_validate_plan) |

**决议**: 
- Tick() 输出 JSON 必须经过 schema 校验，拒绝超长/恶意 Command JSON
- `swarm_validate_plan` 改为 snapshot-bound non-authoritative dry-run，或删除并交由 Rhai `swarm_simulate` 替代

---

### 🔴 FB-6: IDL imperative vs deferred 一致性

| 支持者 | 标签 |
|---|---|
| claude-architect | CA1 — Critical |
| dsv4-architect | D3 (World Rules Engine unification) |

**决议**: 选择 deferred model (`tick() → JSON` 返回模式)，移除 DESIGN §5 中的 imperative 描述。DESIGN §5 和 P0-4 §3 统一为 deferred。

---

## 三、P0-9 Source Gate 矩阵缺口 (gpt-security 核心 concern)

gpt-security 标记 P0-9 未闭合为 Critical。Speaker 审查后确认：当前 P0-9 缺失 deploy/rollback/admin/tutorial/replay/test/rule-mod/simulate/dry-run 共 9 个 Source 的 capability/budget/visibility 约束。这不是架构重设计，而是 gap-filling。

**决议**: 新增 **Gap-1** — 完成 P0-9 Source Gate 完整矩阵。与其他评审者的相关标注合并（claude-security H4/H5/M4、dsv4-security H4-H5、gpt-architect Item 6）。

---

## 四、Phase 0 冻结前 Cleanup Checklist

以下为共识级 cleanup，非 blocker 但建议冻结前完成：

| # | 项目 | 来源 |
|---|---|---|
| C-1 | RejectionReason 命名统一 (SourceDepleted vs SourceEmpty) | claude-architect CA4 |
| C-2 | world_seed 长度/编码定义为 32 字节 | dsv4-security H1, claude-architect CA6 |
| C-3 | Phase 状态统一标记 (Freeze Candidate / Frozen / Superseded) | gpt-architect Item 7 |
| C-4 | Tick failure semantics 完整补全 (timeout/crash/commit fail/broadcast fail/cache 不一致) | gpt-architect Item 9 |
| C-5 | Rhai mod 执行预算 (CPU 时间/指令计数限制) | dsv4-designer Missing |
| C-6 | 模组依赖 semver 约束语法 | dsv4-designer Missing |
| C-7 | HashMap→IndexMap 代码级强制执行 | dsv4-security H2 |
| C-8 | WASM cache version-skew policy | dsv4-security H5 |
| C-9 | TickTrace schema 冻结 | claude-architect CA5 |
| C-10 | FDB 事务规模基准测试 (25K ops/500ms) | dsv4-architect R1 |

---

## 五、Fresh Ideas 精选 (Speaker 推荐纳入 Phase 1-2)

从 9 份评审的 ~30 条 Fresh Ideas 中，Speaker 选出以下高价值项：

| # | Idea | 来源 | 优先级 |
|---|---|---|---|
| I-1 | 物流税分成 — 领土控制者获物流税收份额 | dsv4-designer | ★★★ |
| I-2 | 模组 Tier 0/1/2 分级安全模型 | dsv4-designer, claude-designer | ★★★ |
| I-3 | World DNA (Blake3 哈希) — 世界实例可复现 | dsv4-designer | ★★☆ |
| I-4 | Seasonal World — World/Arena 之间的第三模式 | dsv4-designer | ★★☆ |
| I-5 | Link economics — 两点间付费传输 | claude-designer | ★★☆ |
| I-6 | Progression layers — 技术树/声望/赛季遗产替代 GCL 单维度 | claude-designer | ★★☆ |
| I-7 | 物流可视化 — 地图运输路线+资源流动 | gpt-designer F1 | ★★☆ |
| I-8 | 四类世界模板 (beginner/default/arena/hardcore) | gpt-designer F3 | ★☆☆ |
| I-9 | replay 解说生成 — AI 自动比赛叙事 | gpt-designer F6 | ★☆☆ |
| I-10 | i18n 翻译完整度 badge | claude-designer | ★☆☆ |

---

## 六、投票明细

| 评审者 | Verdict | Freeze Blockers |
|---|---|---|
| dsv4-architect | CONDITIONAL_APPROVE | D1, D2, D3 |
| gpt-architect | CONDITIONAL_APPROVE | (contract cleanup) |
| claude-architect | CONDITIONAL_APPROVE | CA1, CA2, CA3, CA4 |
| dsv4-security | CONDITIONAL_APPROVE | C1, C2, C3 |
| gpt-security | ~~REQUEST_MAJOR_CHANGES~~ → 降级 | (spec gaps, 已纳入 FB-4/FB-5/Gap-1) |
| claude-security | CONDITIONAL_APPROVE | C1, C2, H4, H5 |
| dsv4-designer | CONDITIONAL_APPROVE | G1, G5 |
| gpt-designer | CONDITIONAL_APPROVE | (concerns, 已纳入 FB-1/FB-2) |
| claude-designer | CONDITIONAL_APPROVE | 2 freeze blockers (→ FB-1, FB-2) |

**分歧**: 仅 gpt-security 提出 MAJOR_CHANGES。Speaker 逐条审查后确认三项 concerns 均为 spec 一致性问题，非架构重设计，已吸收到 FB-4/FB-5/Gap-1。

---

## 七、下一步

```
Phase 0 Freeze Gate: 闭合 6 项 Freeze Blocker + 1 项 Gap
                    ↓
             Speaker 复审 (Gate Check)
                    ↓
             Phase 0 FROZEN 声明
                    ↓
             Phase 1: 实现规划 (ralplan)
```

**Phase 0 冻结条件**: 6 FB + 1 Gap 全部闭合后，由 Speaker 复审确认，方可宣布 Phase 0 Architecture Freeze。

---

*Speaker: Hermes Agent (acting as Speaker)*
*评审记录: /data/swarm/docs/reviews/r3-rev-*.md (9 files)*
*输出: /data/swarm/docs/reviews/R3-SPEAKER-VERDICT.md*
