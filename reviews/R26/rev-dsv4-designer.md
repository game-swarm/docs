# Swarm 设计评审 R26 — Closure Verification (Game Designer)

## Verdict

**APPROVE**

8 项验证全部 CLOSED — REOPEN 项（B3/B4）已闭合，WEAK 项（R3-R8）残留已清理。

---

## 逐项验证

### B3: Tick budget 交叉引用 — REOPEN

**状态**: CLOSED ✅

**证据**:
- `specs/core/01-tick-protocol.md` §1.4 EXECUTE 阶段明确标注 "硬超时天花板: 500ms"，并在下一行括号中引用 `design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms`
- `design/engine.md` §3.4.1 表: EXECUTE budget World ≤400ms / Arena ≤50ms
- tick-protocol 不再残留"超时 500ms"的孤立声明——已显式关联预算目标与超时天花板的关系

**策略深度评估**: 预算（400ms）与超时（500ms）100ms余量现已文档化——这是合理的工程安全裕度，不是设计缺陷。

---

### B4: MCP 工具清单 (54)→(56) + security spec Authority note — REOPEN

**状态**: CLOSED ✅

**证据**:
- `specs/reference/api-registry.md` §3 抬头: "共计 56 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)"
- `specs/reference/api-registry.md` §3.2 子标题: "Game API 工具清单 (56)" — 原 "(54)" 残留已修正
- `specs/security/03-mcp-security.md` §4.4: "`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 为 active onboarding/play 工具" — 原 "已移除" 标签已清理
- `specs/security/03-mcp-security.md` §4.3 & §4.4 末尾: 两处 Authority note 声明 "所有 active 工具以 API Registry 为准。本文档不自行声明工具的移除状态"
- `specs/security/03-mcp-security.md` §4: 工具清单引用已指向 api-registry.md

**策略深度评估**: AI onboarding 三件套（docs/schema/available_actions）现确认为 active MCP 工具——通过 scope/rate/detail-level 限制。AI agent 的自助学习路径完整保留。

---

### R3: tick-protocol snapshot truncation → 纯引用 snapshot-contract (WEAK)

**状态**: CLOSED ✅

**证据**:
- `specs/core/01-tick-protocol.md` §2.3 快照构建: "snapshot-contract 是 snapshot truncation 的唯一权威源。tick-protocol 不定义独立截断算法，只引用该权威源"
- 截断细节（距离桶 + entity_id 字典序 + farthest-first + critical 不可截断）全部指向 `specs/core/09-snapshot-contract.md`
- `specs/core/09-snapshot-contract.md` §1: 完整截断合同（触发条件、标记字段、确定性顺序、关键实体、竞技降级）
- tick-protocol 中不存在任何独立截断算法声明

**策略深度评估**: tick-protocol 作为引擎主文件，正确地将截断行为委派给 snapshot-contract——消除了"两个文件定义同一算法"的文档分叉风险。

---

### R4: sandbox/IDL host function ABI → api-registry 权威签名 (WEAK)

**状态**: CLOSED ✅

**证据**:
- `specs/reference/host-functions.md` 行 3-5: 明确声明 "权威定义见 API Registry §4。本文档提供实现指南"
- `specs/reference/api-registry.md` §4: 定义 5 个 host function 的 canonical ABI 签名（含参数类型、返回值、只读标记）
- api-registry §4.2-4.5: 调用预算、输出上限、per-call fuel、错误优先级全部以 registry 为权威
- host-functions.md 不包含独立签名声明——所有具体数值（预算、上限、燃料成本）引用 registry

**策略深度评估**: host function ABI 的单事实源消除了 WASM 沙箱合同不确定性——所有 5 个只读 host function 按确定性合同执行。

---

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional (WEAK)

**状态**: CLOSED ✅

**证据**:
- `specs/gameplay/08-api-idl.md` §2 body_cost 表: `RangedAttack: { Energy: 150 }` — 原 100 已修正
- `specs/gameplay/08-api-idl.md` §2 Recycle 指令: `refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan) # lifespan-proportional 10%-50% (权威公式见 economy.idl.yaml §RecycleRefund)`
- `specs/reference/economy.idl.yaml` §2.1 RecycleRefund: 公式 `max(1000, (remaining_lifespan × 5000) / total_lifespan)` — 10%-50% lifespan-proportional
- 验证交叉一致性: 08-api-idl body_cost 声明 150 = economy.idl.yaml spawn_cost RANGED_ATTACK cost 150 ✅

**策略深度评估**: RangedAttack 150 的成本创造了与非 Ranged body part（Attack 80）之间的有意义的策略权衡——专用化 vs 通用化的经济选择。Recycle lifespan-proportional 消除了固定 50% 的套利风险。

---

### R6: D2-A leaderboard→Arena, world_stats→Play (WEAK)

**状态**: CLOSED ✅

**证据**:
- `specs/reference/api-registry.md` §3.2 Play (15): `swarm_get_world_stats` 在 Play 分类
- `specs/reference/api-registry.md` §3.2 Arena (5): `swarm_get_leaderboard` 在 Arena 分类，visibility filter=`arena_only`
- `specs/reference/api-registry.md` §3.4 Capability Profiles: `play` 含 "`swarm_get_world_stats` — World 非竞争统计"; `arena` 含 "`swarm_get_leaderboard` — Arena 竞争排行"
- `design/modes.md` §9 World 行: "World 不设竞争榜单" — 一致
- `design/modes.md` §9.1: Arena 房间制模型 — 一致

**策略深度评估**: leaderboard 的 capability profile 已从 `play` 移至 `arena`，World 玩家不再暴露竞争排行 API。World 的非竞争统计（world_stats）独立于 Arena 的竞争排行（leaderboard）——两个模式的设计承诺均得到维护。

---

### R7: CodeSigning default 7d→30d (WEAK)

**状态**: CLOSED ✅

**证据**:
- `design/auth.md` §5.3 用途隔离证书表: CodeSigningCertificate TTL = "30–180 days（默认 30d，world.toml 可配）"
- 不再存在 7d 默认值冲突
- TTL 窗口通过 world.toml 可配置，满足不同部署场景需求

**策略深度评估**: 30d 默认值在安全性与运维便利间取得合理平衡——AI agent 不必每 7d 续签，但窗口足够短以限制泄露后的影响范围。

---

### R8: feedback-loop Tournament/MVP→房间制+非竞争展示 (WEAK)

**状态**: CLOSED ✅

**证据**:
- `specs/gameplay/06-feedback-loop.md` §6 World 模式: "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏"
- `specs/gameplay/06-feedback-loop.md` §6 Arena 模式: "房间制，玩家创建比赛房间，设定参数，自己或他人加入"；"无自动匹配、无天梯排名、无赛季"；"Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现（不在 P0 MVP 范围）"
- `design/modes.md` §9.1: "Arena P0 以房间制比赛为核心...无自动匹配、无天梯排名、无赛季。Tournament/League 为 P1+ 上层编排"
- 两个文件一致 — 不存在 Tournament/MVP=房间制+非竞争展示的旧冲突

**策略深度评估**: 反馈循环文档正确反映了 P0 范围——World 非竞争统计（creativity-first）、Arena 房间制比赛（algorithm-vs-algorithm）。Tournament/League 确认为 P1+ 扩展路径，不阻塞 P0。

---

## 评审统计

| 类别 | CLOSED | GAP |
|------|--------|-----|
| REOPEN (B3, B4) | 2 | 0 |
| WEAK (R3-R8) | 6 | 0 |
| **总计** | **8** | **0** |

---

*评审日期: 2026-06-20*
*评审员: rev-dsv4-designer (DeepSeek V4 Pro)*
*角色: Game Designer Reviewer*
*轮次: R26 Closure Verification*