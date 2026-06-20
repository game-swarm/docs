# R25 Closure Verification — rev-gpt-economy

## Verdict

**CONDITIONAL_APPROVE**

B2 与 D3 的经济数值主线已基本闭合，但本轮指定 closure 项仍存在多处残留：B3 tick budget、B4 MCP 工具清单、B5 snapshot truncation、D1 Arena 房间制边界未完全统一。因此不能 APPROVE。

## Strengths

- B1 Host Function ABI 已统一到 `specs/reference/api-registry.md` §4；`specs/reference/host-functions.md` 明确只作为实现指南并引用 Registry。
- B2 经济数值主线已对齐 `economy.idl.yaml`：RANGED_ATTACK=150、RecycleRefund lifespan-proportional、AlliedTransfer 200 tick/2%/500 cooldown/10000 cap、StorageTax 百分比 tier、UpkeepDeduction 超线性公式均有权威来源。
- D3 Recycle 已落实为 lifespan-proportional 10%–50%，并在 `economy.idl.yaml`、`api-registry.md`、`resource-ledger.md`、`design/gameplay.md` 中形成一致主线。
- D2 World 非竞争统计方向在 `design/gameplay.md` 与 `specs/gameplay/08-api-idl.md` 中已有“无公开排行榜，仅非竞争统计”的表述。

## Concerns

### E1 — B3 Tick budget 仍有核心 spec 残留

**Status: GAP**

证据：
- `design/engine.md` §3.4.1 已给出分模式预算：World SNAPSHOT ≤200ms p95、Arena ≤50ms p99；World EXECUTE ≤400ms、Arena ≤50ms。
- `specs/core/01-tick-protocol.md` 状态机仍写 EXECUTE `超时: 500ms`。
- `specs/core/01-tick-protocol.md` §8.2 又写 EXECUTE 不单独超时、必须在 `tick_soft_deadline_ms=2500ms` 内完成。

问题：同一个 EXECUTE budget 同时存在 500ms、400ms/50ms、无独立超时三种口径。R24 B3 要求“Tick budget 对齐”，此项未闭合。

### E2 — B4 MCP 工具清单 54→56 未完全闭合

**Status: PARTIAL**

证据：
- `api-registry.md` §3 顶部声明 56 个 Game API active tools，但 §3.2 标题仍为 `Game API 工具清单 (54)`。
- `specs/security/03-mcp-security.md` 的链接锚点仍多处使用旧 `#32-工具清单-46`。
- 同一 security spec 仍声称 `swarm_list_modules`、`swarm_explain_last_tick`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 是“已移除/整合”工具；但这些工具在 `api-registry.md` 仍为 active 工具或 active capability 的一部分。

问题：工具总数主声明已修到 56，但标题、锚点和 removed/active 状态仍冲突。B4 未完全闭合。

### E3 — B5 Snapshot truncation 未统一到 snapshot-contract 权威算法

**Status: GAP**

证据：
- `specs/core/09-snapshot-contract.md` 声明自己是 snapshot truncation 唯一权威，并定义 distance bucket 0–6、entity_id 字典序、从最远桶末尾移除、critical 不可截断。
- `specs/core/01-tick-protocol.md` §2.3 仍内联另一套“关键桶/高优先桶/中优先桶/低优先桶 + distance_to_drone/entity_id”截断策略。

问题：核心 tick spec 没有引用 snapshot-contract 的权威算法，仍保留三套口径中的旧口径之一。B5 未闭合。

### E4 — D1 Arena 房间制优先仍被 feedback-loop MVP 表述稀释

**Status: PARTIAL**

证据：
- `design/modes.md` 已明确 Arena P0 以 Room Match 为核心，Tournament/League 为 P1+ 上层编排。
- 但 `specs/gameplay/06-feedback-loop.md` MVP 功能清单仍列出“锦标赛系统”，前文也保留“排行榜按 league 分区”“锦标赛分组、赛季”等 P0 语境。

问题：D1 的 design 层已落地，但 gameplay spec 仍把 Tournament/League 放在 MVP 功能清单中，削弱“房间制优先、Tournament P1+”的闭合性。

### E5 — D2 World 非竞争统计存在命名/API 残留

**Status: PARTIAL**

证据：
- design/spec 已写 World 无公开排行榜、仅非竞争统计。
- `api-registry.md` 仍有通用 `swarm_get_leaderboard`，Output 为 `{player, gcl, rooms, drones}`，未在 Registry 层显式限定 Arena competitive 或 World non-competitive stats profile。

问题：产品语义已修，但 API capability 层仍容易把 World stats 与 leaderboard 混用。D2 接近闭合但仍有 API 命名残留。

### E6 — B6 Auth CSR replay + CodeSigning TTL 基本闭合，但 Registry 上限残留

**Status: PARTIAL**

证据：
- `specs/security/09-command-source.md` 已用 per-player/per-slot `version_counter` 定义 Deploy replay 防护，并写明 CodeSigningCertificate 常用设备 30–180 天。
- `api-registry.md` §5.8 仍写 `Cert validity max = 365d`，没有区分 CodeSigningCertificate 30–180d 与其他证书 profile。

问题：B6 的 replay class 语义基本闭合，但 TTL 在 registry 限制表中仍可能被解读为 CodeSigningCertificate 可 365d。建议补充 profile-specific TTL 表或把 §5.8 改为“general certificate upper bound; CodeSigningCertificate 30–180d”。

## Economy Balance Issues

- **Maintenance curve**: CLOSED。`economy-balance-sheet.md` 与 `resource-ledger.md` 均使用 `base_upkeep × rooms × (1 + rooms / room_soft_cap)`，小/中/大帝国压力曲线清晰。
- **Recycle exploit**: CLOSED。固定 50% 已替换为 lifespan-proportional 10%–50%，可抑制临时建造/回收套利。
- **MCP/API economic observability**: PARTIAL。`swarm_get_economy` 与 `swarm_get_economy_trend` 存在，但 World leaderboard/stats 命名残留会影响非竞争经济展示边界。
- **Inflation controls**: CLOSED。PvE budget、global resource cap、storage tax、allied transfer fee/cap/cooldown 构成闭环抑制。

## Resource Loop Gaps

- **B2: CLOSED** — economy IDL 与 Resource Ledger 主线闭合；未发现 RangedAttack=100、flat recycle 50%、per-player drone cap=500 这类旧 blocker 的实质残留。
- **D3: CLOSED** — RecycleRefund 生命周期比例公式闭合。
- **B3: GAP** — tick budget 三口径并存。
- **B4: PARTIAL** — 56 active 主声明已修，但旧 54/46 heading/anchor/removed 状态残留。
- **B5: GAP** — tick-protocol 仍定义旧截断算法，未统一到 snapshot-contract。
- **D1/D2/B6: PARTIAL** — 设计方向已落地，但 specs/reference 层仍有残留语义。

## Item-by-item Closure

| Item | Status | Result |
|---|---|---|
| B1 Host Function ABI | CLOSED | Registry/host-functions 基本统一 |
| B2 Economy numeric alignment | CLOSED | 经济数值主线已对齐 economy.idl.yaml |
| B3 Tick budget alignment | GAP | 500ms / 400ms+50ms / no standalone timeout 冲突 |
| B4 MCP tools 54→56 | PARTIAL | 总数声明 56，但 54/46/removed 状态残留 |
| B5 Snapshot truncation authority | GAP | tick-protocol 仍保留旧截断算法 |
| B6 Auth CSR replay + CodeSigning TTL | PARTIAL | replay 闭合，TTL registry 365d 残留 |
| D1 Arena room-first | PARTIAL | modes 已修，feedback-loop 仍把 tournament 放 MVP |
| D2 World non-competitive stats | PARTIAL | design 已修，leaderboard API 命名残留 |
| D3 Recycle lifespan-proportional | CLOSED | 10%–50% 生命周期比例公式一致 |
| D4 Snapshot budget split | PARTIAL | design 分模预算已修，但 tick/snapshot specs 未完全同步 |

## Final Verdict

**CONDITIONAL_APPROVE** — B2/D3 可视为闭合；但 B3、B4、B5 至少三项仍有明确文档残留，D1/D2/D4/B6 也存在 reference/spec 层未同步。下一步应直接修复这些 closure residues，而不是开启新 D-item。