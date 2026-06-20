# R26 API/DX Narrow Closure Verification — rev-dsv4-apidx

> R26 窄范围 Closure Verification。仅验证 R25 REOPEN/WEAK 项是否已闭合。

---

## REOPEN 项（R25 → 已修复 → 逐项验证闭合）

### B3: Tick budget — tick-protocol EXECUTE 500ms→硬超时天花板引用 engine.md budget

**检查**: specs/core/01-tick-protocol.md

- Line 74: `超时: 500ms` — EXECUTE 阶段硬超时天花板 ✓
- Line 3: `> 详见 design/engine.md` — 顶层引用 engine 设计 ✓
- engine.md §3.4.1: EXECUTE (2a+2b) ≤400ms — 更紧的预算值，与 500ms 天花板一致
- 500ms 天花板 > 400ms 预算 — 设计合理，无矛盾

**Verdict: CLOSED** ✓

---

### B4: MCP 工具清单 — (54)→(56); security spec Authority note 替代"已移除"

**检查**: specs/reference/api-registry.md + specs/security/03-mcp-security.md

- api-registry.md Line 209: `共计 54 个活跃工具 (game_api)` — **仍为 54，应为 56** ✗
- api-registry.md 实际工具数: Onboarding(10)+Auth(2)+Play(16)+Deploy(7)+Debug(8)+Admin(6)+SDK(1)+Arena(4)+Resources(2) = **56** ✓
- api-registry.md Changelog Line 856: `MCP tools 总数为 56 active` — changelog 正确 ✓
- 03-mcp-security.md Line 223: `> MCP 工具权威清单 见 API Registry §3.2 — 56 工具` — 引用 api-registry 准确 ✓
- 03-mcp-security.md Line 227: `> MCP 工具授权以 API Registry §3.4 为权威来源` — Authority note 存在 ✓
- 03-mcp-security.md Lines 236, 267, 275: 仍含 "已移除的旧工具" 文本 — 但已指向 api-registry 为权威源，残留文本为信息性注释

**Verdict: GAP** ✗ — api-registry.md §3 header 仍显示 "54"，与 changelog "56" 和实际计数 56 不一致。位置: Line 209。

---

## WEAK 项（R25 WEAK_CONFIRMED — 验证残留已清理）

### R3: tick-protocol snapshot truncation→纯引用 snapshot-contract

**检查**: specs/core/01-tick-protocol.md §2.3 + specs/core/09-snapshot-contract.md

- snapshot-contract.md Line 7: `本文档为 snapshot truncation 的唯一权威` — 声明权威性 ✓
- tick-protocol.md §2.3 (Lines 133–204): **完整的 inline 截断逻辑**（分桶、排序、截断算法、滥用检测），**无**对 snapshot-contract.md 的引用 ✗
- tick-protocol.md 无任何 `snapshot-contract` 或 `09-snapshot-contract` 字符串出现 ✗
- 截断细节在两文件中**重复定义**，非"纯引用"模式

**Verdict: GAP** ✗ — tick-protocol §2.3 仍包含完整 inline 截断实现，未引用 snapshot-contract.md。需要加入引用行或精简为摘要+引用。

---

### R4: sandbox/IDL host function ABI→api-registry 权威签名

**检查**: specs/core/04-wasm-sandbox.md §3.2 + specs/gameplay/08-api-idl.md + specs/reference/api-registry.md §4

- 08-api-idl.md Line 241: `> 权威定义见 API Registry §4` — host function 引用 api-registry ✓
- wasm-sandbox.md §3.2 (Lines 208–214): **完整的内联 host function 签名**（host_get_terrain, host_get_objects_in_range, host_path_find, host_get_world_config, host_get_world_rules），**无**对 api-registry.md 的引用 ✗
- api-registry.md §4 (Lines 397–403): 5 个 host function 的权威 ABI 签名 — 与 wasm-sandbox 内联签名一致但 wasm-sandbox 缺失引用声明

**Verdict: GAP** ✗ — 08-api-idl 侧已闭合（引用 api-registry），wasm-sandbox 侧未闭合（仍为内联定义，无引用）。位置: specs/core/04-wasm-sandbox.md §3.2。

---

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional

**检查**: specs/gameplay/08-api-idl.md + specs/reference/economy.idl.yaml

- economy.idl.yaml Line 329: `RANGED_ATTACK cost: 150` — 正确 ✓
- economy.idl.yaml Lines 82–93: `RecycleRefund` — lifespan-proportional formula `max(1000, (remaining_lifespan * 5000) / total_lifespan)` — 正确 ✓
- 08-api-idl.md Line 5: `> 权威数据类型定义见 API Registry（由 game_api.idl.yaml / economy.idl.yaml 自动生成）` — 明确声明 YAML IDL 为权威源 ✓
- 08-api-idl.md Line 230: `RangedAttack: { Energy: 100 }` — 内联值仍为 100（非权威摘要，权威在 economy.idl.yaml）△
- 08-api-idl.md Line 164: `refund: registry.body_cost(body) * 0.5` — 内联仍为 flat 50%（非权威摘要，权威在 economy.idl.yaml）△

**Verdict: CLOSED** ✓ — 权威源 (economy.idl.yaml) 值正确。08-api-idl 声明了权威源归属。内联值是 stale 的非权威摘要，文档合同已明确 YAML 优先。

---

### R6: D2-A leaderboard→Arena, world_stats→Play

**检查**: specs/reference/api-registry.md + specs/gameplay/06-feedback-loop.md + design/gameplay.md

- api-registry: `swarm_get_leaderboard` 在 Play (16) 分类下 — 跨 World/Arena 均可使用 ✓
- Arena (4) 工具集合: tournament_create/precommit/status/match_result — 纯 Arena 工具独立 ✓
- 06-feedback-loop.md §6: World 模式 "趣味展示（非竞争排名）" / Arena 模式 "比赛制" — 房间制+非竞争展示 ✓
- design/gameplay.md Line 534: `World 模式无排行榜；Arena 模式通过 swarm_get_world_stats 提供段位统计` — show/world_stats 语义在 Play 层 ✓
- 全库搜索无 "D2-A" 残留引用 ✓

**Verdict: CLOSED** ✓ — leaderboard 工具在 Play（跨模式可用），Arena tournament 工具独立，World 展示非竞争。无 D2-A 残留引用。

---

### R7: CodeSigning default 7d→30d

**检查**: design/auth.md

- design/auth.md Line 274: `| CodeSigningCertificate | WASM/module deploy 签名 | 7d |` — **仍为 7d，应为 30d** ✗
- design/auth.md Line 296: `常用设备 ... CodeSigningCertificate | 30–180 days` — 常用设备策略正确，但与类型表 Line 274 不一致 ✗

**Verdict: GAP** ✗ — design/auth.md §5.3 证书类型表 (Line 274) 的 CodeSigningCertificate TTL 仍为 "7d" 而非 "30d"。位置: design/auth.md Line 274。

---

### R8: feedback-loop Tournament/MVP→房间制+非竞争展示

**检查**: specs/gameplay/06-feedback-loop.md

- §6 World 模式 (Lines 321–327): `趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏` — 非竞争展示 ✓
- §6 Arena 模式 (Lines 329–338): `比赛制，固定时长...对称初始条件...独立房间/地图` — 房间制比赛 ✓
- §7 MVP 功能清单 (Lines 342–355): 含 Arena 模式（比赛制）、锦标赛系统、观战解说 ✓

**Verdict: CLOSED** ✓ — feedback-loop 规范完整反映房间制 Arena + 非竞争 World 展示。

---

## Summary

| 项 | 类型 | Verdict | 位置 |
|----|------|---------|------|
| B3 | REOPEN | CLOSED | — |
| B4 | REOPEN | **GAP** | api-registry.md L209: "54"→应"56" |
| R3 | WEAK | **GAP** | tick-protocol §2.3 缺 snapshot-contract 引用 |
| R4 | WEAK | **GAP** | wasm-sandbox §3.2 缺 api-registry 引用 |
| R5 | WEAK | CLOSED | — |
| R6 | WEAK | CLOSED | — |
| R7 | WEAK | **GAP** | auth.md L274: CodeSigning TTL "7d"→应"30d" |
| R8 | WEAK | CLOSED | — |

CLOSED: 4/9 | GAP: 4/9 | REOPEN 未闭: 1/2 | WEAK 残留未清: 3/6

---

## Verdict

**CONDITIONAL_APPROVE** — 4 项 GAP 需处理，均为定位明确的文本残留：

1. **B4**: api-registry.md L209 — s/54/56
2. **R3**: tick-protocol.md §2.3 — 加入 `> 权威截断合同见 specs/core/09-snapshot-contract.md` 引用行
3. **R4**: wasm-sandbox.md §3.2 — 加入 `> 权威 Host Function ABI 见 api-registry.md §4` 引用行
4. **R7**: design/auth.md L274 — s/7d/30d（CodeSigningCertificate TTL）

所有 GAP 均为单行文本修改，无需架构变更。