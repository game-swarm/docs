# R26 Economy Closure Verification — rev-dsv4-economy

Date: 2026-06-20 | Reviewer: Economy (DeepSeek V4 Pro) | Round: R26 (窄闭包验证)

## Scope

仅验证 R25 REOPEN/WEAK 项是否已闭合。不做全量设计评审。

---

## 逐项检查

### REOPEN 项 (R25 已修复 → 验证闭合)

#### B3: Tick Budget — EXECUTE 500ms 硬超时天花板引用 engine.md budget

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| 硬超时天花板 500ms | `specs/core/01-tick-protocol.md` | L74 | 明确: "硬超时天花板: 500ms" |
| 引用 engine.md budget | `specs/core/01-tick-protocol.md` | L75-77 | "(budget target 见 design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms)" |
| engine.md §3.4.1 权威 budget | `design/engine.md` | L292-298 | EXECUTE (2a+2b): World ≤400ms, Arena ≤50ms |
| Arena 独立 budget | `design/engine.md` | L398 | "Arena 使用独立的 tick/collect/simulate budget" |

Verdict: **CLOSED** — tick-protocol 500ms 硬天花板 + 显式引用 engine.md §3.4.1 budget targets，World/Arena split 已落实。

---

#### B4: MCP 工具清单 — (54)→(56); security spec Authority note 替代"已移除"

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| MCP 工具数 56 | `specs/reference/mcp-tools.md` | L5 | "56 个 Game API 活跃工具 + 11 个 Auth API 工具" |
| API Registry 工具数 56 | `specs/reference/api-registry.md` | L209 | "共计 56 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)" |
| Authority note | `specs/security/03-mcp-security.md` | L264 | "本文档不再声明移除状态——所有 active 工具以 API Registry 为准" |
| Authority note 完整 | `specs/security/03-mcp-security.md` | L272 | "所有工具的 canonical definition 与 active/removed 状态以 API Registry §3.2 为唯一权威源。本文档不自行声明工具的移除状态" |

Verdict: **CLOSED** — MCP 工具清单 54→56，security spec 以 Authority note 替代自声明"已移除"，权威指向 API Registry。

---

### WEAK 项 (R25 WEAK_CONFIRMED → 验证残留已清理)

#### R3: Tick-protocol snapshot truncation → 纯引用 snapshot-contract

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| tick-protocol 纯引用 | `specs/core/01-tick-protocol.md` | L158 | "snapshot-contract 是 snapshot truncation 的唯一权威源。tick-protocol 不定义独立截断算法，只引用该权威源。" |
| 截断算法归属 | `specs/core/01-tick-protocol.md` | L159 | "截断算法（距离桶 + entity_id 字典序 + farthest-first + critical 不可截断）全部由 snapshot-contract 定义。" |
| engine.md 引用 | `design/engine.md` | L419 | "权威截断合同见 Snapshot Contract §1" |
| snapshot-contract 声明 | `specs/core/09-snapshot-contract.md` | L7 | "本文档为 snapshot truncation 的唯一权威" |

Verdict: **CLOSED** — tick-protocol 和 engine.md 均纯引用 snapshot-contract，不重复声明截断算法。R22 B5 标记已体现在 snapshot-contract 中。

---

#### R4: Sandbox/IDL host function ABI → api-registry 权威签名

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| host-functions.md 引用 api-registry | `specs/reference/host-functions.md` | L1, L5 | "权威源: game_api.idl.yaml → api-registry.md (生成)" / "权威定义见 API Registry §4" |
| api-registry ABI 签名 | `specs/reference/api-registry.md` | L398-404 | 全部 5 个 host function 的精确 C-ABI 签名 |
| api-registry 调用预算 | `specs/reference/api-registry.md` | L408-414 | 全量 budget 表 |
| api-registry 输出上限 | `specs/reference/api-registry.md` | L419-425 | 全量 output cap 表 |
| api-registry fuel 成本 | `specs/reference/api-registry.md` | L429-435 | 全量 per-call fuel 成本 |
| api-registry 错误优先级 | `specs/reference/api-registry.md` | L443-453 | 完整错误优先级链 (-1 ~ -9) |

Verdict: **CLOSED** — host-functions.md 和 08-api-idl.md 均明确指向 api-registry §4 为唯一权威签名源。api-registry 包含完整的 ABI 签名、budget、output cap、fuel cost 和 error priority。

---

#### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| RangedAttack body_cost 150 | `specs/gameplay/08-api-idl.md` | L230 | `RangedAttack: { Energy: 150 }` (原 100) |
| body_cost 表格一致 | `specs/gameplay/08-api-idl.md` | L225-233 | 全局 body_cost 表: RangedAttack=150 |
| economy.idl.yaml spawn_cost | `specs/reference/economy.idl.yaml` | L328-329 | `RANGED_ATTACK cost: 150` |
| Recycle lifespan-proportional | `specs/gameplay/08-api-idl.md` | L164 | `refund: RecycleRefund(body_cost, remaining_lifespan, total_lifespan)  # lifespan-proportional 10%-50% (权威公式见 economy.idl.yaml §RecycleRefund)` |
| RecycleRefund 权威公式 | `specs/reference/economy.idl.yaml` | L81-93 | `refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)` — clamp [10%, 50%] |
| Formulas 块一致 | `specs/reference/economy.idl.yaml` | L411-421 | §3 recycle_refund 与 §2.1 RecycleRefund computation 一致 |

Verdict: **CLOSED** — RangedAttack body_cost 100→150 在 body_cost 表和 economy.idl 中一致。Recycle 从固定退还改为 lifespan-proportional，公式在 economy.idl.yaml 中唯一定义，08-api-idl.md 显式引用权威源。

---

#### R6: D2-A leaderboard→Arena, world_stats→Play

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| leaderboard 在 Arena group | `specs/reference/api-registry.md` | L317-325 | `swarm_get_leaderboard` — Arena (5), visibility_filter: `arena_only` |
| world_stats 在 Play group | `specs/reference/api-registry.md` | L252-270 | `swarm_get_world_stats` — Play (15), visibility_filter: `none` (World 非竞争统计) |
| Arena 房间制 | `design/modes.md` | L86-87 | "Arena P0 以房间制比赛为核心——玩家创建比赛房间... 无自动匹配、无天梯排名、无赛季" |
| World 非竞争排名 | `design/modes.md` | L22 | World: "无——类似 MMO 持续沙盒" |
| World 趣味展示 | `specs/gameplay/06-feedback-loop.md` | L327 | "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏" |

Verdict: **CLOSED** — leaderboard 正确归属 Arena (`arena_only` visibility)，world_stats 正确归属 Play（非 World 竞争排行）。Arena 为房间制，World 为非竞争展示。

---

#### R7: CodeSigning default 7d→30d

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| CodeSigningCertificate TTL | `design/auth.md` | L274 | `30–180 days（默认 30d，world.toml 可配）` |

Verdict: **CLOSED** — CodeSigningCertificate 默认 TTL 从 7d 改为 30d，范围 30–180d，world.toml 可配。

---

#### R8: Feedback-loop Tournament/MVP→房间制+非竞争展示

| 检查点 | 文件 | 位置 | 结果 |
|--------|------|------|------|
| Arena 房间制 | `specs/gameplay/06-feedback-loop.md` | L329-338 | "房间制，玩家创建比赛房间，设定参数，自己或他人加入... 无自动匹配、无天梯排名、无赛季" |
| Tournament P1+ | `specs/gameplay/06-feedback-loop.md` | L338 | "Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现（不在 P0 MVP 范围）" |
| World 非竞争展示 | `specs/gameplay/06-feedback-loop.md` | L327 | "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏" |
| Arena 房间制独立确认 | `design/modes.md` | L86-88 | "房间制比赛为核心" + 与 feedback-loop 一致 |

Verdict: **CLOSED** — Tournament 已退场（P1+），MVP 回归房间制比赛 + 非竞争展示。feedback-loop 与 modes.md 一致性确认。

---

## Verdict: APPROVE

全部 8 项（2 REOPEN + 6 WEAK）均已闭合。无残余 GAP。

### 闭合汇总

| ID | 项 | 状态 |
|----|----|------|
| B3 | Tick budget EXECUTE 500ms→engine.md budget | CLOSED |
| B4 | MCP 工具清单 54→56, Authority note | CLOSED |
| R3 | Snapshot truncation→纯引用 snapshot-contract | CLOSED |
| R4 | Host function ABI→api-registry 权威签名 | CLOSED |
| R5 | RangedAttack 100→150, Recycle→lifespan-proportional | CLOSED |
| R6 | Leaderboard→Arena, world_stats→Play | CLOSED |
| R7 | CodeSigning default 7d→30d | CLOSED |
| R8 | Tournament/MVP→房间制+非竞争展示 | CLOSED |

### 权威源一致性

- 所有指定项均通过引用链指向单一权威源（api-registry / economy.idl.yaml / snapshot-contract / engine.md §3.4.1）
- 未发现跨文件口径冲突
- 旧口径已从引用文件中清除

### 方法论

经济评审员职责范围内的验证：反雪球机制、博弈论均衡、资源流数学在本次窄闭包验证中不适用——REOPEN/WEAK 项的修复均涉及文档间引用一致性而非经济模型变更。各经济模型变更（storage tax tiers, recycle lifespan-proportional, starting resources）已在 R23-D1/R23-D4/R25 中完成独立验证并通过。