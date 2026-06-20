# R25 Closure Verification — Security Review (GPT-5.5)

## Verdict

**CONDITIONAL_APPROVE**

R24 的部分修复已经落入权威文档：`api-registry.md` 声明 IDL/API Registry 为 API 合同权威源，`economy.idl.yaml` 已采用 fixed-point 与 lifespan-proportional recycle，`design/auth.md` 已把 CSR replay class 与 CodeSigningCertificate TTL 主线修正到可实现状态。

但 R25 指定的 B-items / D-items 尚未全部正确闭合。安全视角下，残留问题集中在 Host Function ABI 权威分叉、MCP active tool 状态冲突、snapshot truncation 双口径，以及 tick/snapshot budget 分模式闭合不足。这些残留会导致实现者在安全边界、DoS 预算、可见性截断和 API 能力面上继续分叉。

## Critical

### B1 — Host Function ABI 统一到 api-registry.md 权威签名

**Status: GAP**

- `specs/reference/api-registry.md` 已声明为 API 合同权威源，并给出 5 个 host function 的 canonical ABI：`host_get_terrain(room_id, out_ptr, out_len)`、`host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`、`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)` 等。
- `design/interface.md` 与 `specs/reference/host-functions.md` 基本对齐 API Registry。
- 但 `specs/core/04-wasm-sandbox.md` 仍保留旧签名：`host_get_terrain(x, y) -> i32`、`host_path_find(..., out_ptr, out_len)` 缺少 `opts_ptr/opts_len`、`host_get_world_rules(out_ptr, out_len)` 缺少 `rule_id_ptr/rule_id_len`。
- 同一文件还把 `host_get_terrain` 输出上限写成 `4 bytes`，而 API Registry / host-functions 权威表为 `8 KB`。

安全影响：WASM sandbox ABI 是内存边界、输出上限、可见性过滤和 DoS budget 的共同入口。若 core sandbox spec 继续保留旧签名，SDK/engine 可按不同 ABI 实现，造成越界检查、路径搜索选项、rule 读取授权和 replay 行为分叉。

### B4 — MCP 工具清单 54→56

**Status: GAP**

- `specs/reference/api-registry.md` 顶部声明 `共计 56 个活跃工具`，IDL changelog 也声明 MCP tools 总数为 56 active。
- 但同一文件 §3.2 标题仍写 `Game API 工具清单 (54)`，与 56 active 直接冲突。
- 更严重的是 `specs/security/03-mcp-security.md` 仍把 active tools 标为“已移除”：`swarm_explain_last_tick`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`。这些工具在 API Registry 与 gameplay feedback loop 中仍被作为 active onboarding/debug 工具使用。

安全影响：MCP 工具 active/removed 状态冲突会破坏能力面最小化、scope/rate-limit 绑定和网关 allowlist。安全实现若按 security spec 移除工具，AI onboarding 断裂；若按 registry 暴露工具，则 security spec 的 removed 声明会误导审计与策略生成。

### B5 — Snapshot 截断统一到 snapshot-contract 权威

**Status: GAP**

- `specs/core/09-snapshot-contract.md` 已声明自己是 snapshot truncation 的唯一权威，并定义距离桶 → `entity_id` 字典序 → 从最远桶末尾移除的确定性算法。
- `design/engine.md` 已引用 Snapshot Contract，并复述同一距离桶顺序。
- 但 `specs/core/01-tick-protocol.md` 仍保留旧 `sort_and_truncate` 策略：关键桶 / 高优先桶 / 中优先桶 / 低优先桶，排序键为 `(distance_to_drone, entity_id)`，并返回精确 `omitted_count`。
- `specs/security/05-visibility.md` 还指出 `omitted_count` 精确值构成 oracle，要求分桶脱敏；而 API Registry / tick-protocol 仍有 `{truncated, omitted_count}` 或精确 omitted 描述。

安全影响：snapshot truncation 是 fog-of-war、防信息泄露、replay determinism 和 DoS 降级的交界。距离桶算法、优先桶算法和 omitted_count 精确/脱敏策略并存，会导致不同实现泄露不同隐藏实体数量，并可能产生 replay divergence。

## High

### B3 — Tick budget 对齐

**Status: PARTIAL**

- `specs/core/01-tick-protocol.md` 已建立统一 tick budget table：World `tick_interval_ms=3000ms`，Arena 可配置默认 `300ms`，`tick_soft_deadline_ms=2500ms`，COLLECT/EXECUTE/BROADCAST/COMPILE 预算集中描述。
- 但 `design/engine.md` 的预算表仍写 `EXECUTE (2a+2b) ≤400ms / ≤50ms`，而 tick-protocol 表述为 EXECUTE 不单独超时、需在 `tick_soft_deadline_ms` 内完成。
- R24 D4 要求 Snapshot budget 分模式：Arena 50ms / World 200ms。当前只在 `snapshot-contract.md` capacity SLO 中看到 `Snapshot build time < 200ms p95`，没有 Arena 50ms 的分模式 gate；`Worker reset bandwidth < 50ms p99` 不是 snapshot build budget。

安全影响：预算合同不一致会直接影响 DoS 防护和 admission control。攻击者可寻找最宽松文档实现路径，用小请求触发大 snapshot/EXECUTE 开销，而监控 gate 按另一套阈值验收。

### B6 — Auth CSR Replay Class + CodeSigning TTL 30–180d

**Status: CLOSED**

- `design/auth.md` 将 `swarm_submit_csr` 标为 `non_idempotent_mutation`，明确 FDB 事务内消费 PoW challenge，一次性语义。
- `design/auth.md` §5.6a 说明 Dragonfly nonce 只用于 read/idempotent mutation，non-idempotent/admin-critical 必须使用 FDB version counter、idempotency key 或一次性 challenge。
- `design/auth.md` 将 `CodeSigningCertificate` 常用设备策略写为 `30–180 days`，临时设备更短，AdminCertificate `15 min–1h`；`specs/security/09-command-source.md` 也同步为常用设备 `30–180 天`。
- 残留注意：`design/auth.md` 同一行仍写 `30–180 days（默认 7d，world.toml 可配）`，默认值与区间语义略显含混，但不再构成 R24 中的多组 TTL 冲突。

## Medium

### B2 — 经济数值对齐 economy.idl.yaml

**Status: PARTIAL**

- `specs/reference/economy.idl.yaml` 已集中定义 BuildCost、SpawnCost、StorageTax、UpkeepDeduction、RecycleRefund、AlliedTransfer，并采用 fixed-point / BasisPoints。
- `api-registry.md` §10 与 IDL 基本同步，RangedAttack cost 为 150，RecycleRefund 为 lifespan-proportional 10%–50%，storage tax 为 30/60/85% capacity tiers。
- 但 `specs/gameplay/08-api-idl.md` 仍写 `RangedAttack: { Energy: 100 }`，与 economy IDL 的 `RANGED_ATTACK=150` 冲突。
- `specs/core/09-snapshot-contract.md` 的 MVP Economy Boundaries 仍写旧口径：`global_transfer_delay（100 tick）`、`RecycleRefund` 按 `recycle_refund_base（50%）`、`StorageTax` 为 `0.1%/tick`，未对齐 economy.idl.yaml 的 AlliedTransfer 200 tick / cooldown / daily cap、lifespan-proportional 公式、percentage tier tax。

安全影响：经济数值残留会影响滥用检测与经济 exploit 建模。固定 50% recycle 与 0.1% flat storage tax 仍可被实现者误用，导致套利路径与资源 sink/source 不一致。

### D1 — Arena 房间制优先

**Status: CLOSED**

- `design/modes.md` 明确 Arena P0 以房间制比赛为核心，玩家创建比赛房间、设定参数、加入槽位、开始比赛。
- 同段明确 Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现，不在 P0 交付范围。

### D2 — World 非竞争统计

**Status: PARTIAL**

- `design/modes.md` 已写明 World 不设竞争榜单。
- `design/gameplay.md` 已将 World 描述为无公开排行榜，仅提供非竞争统计，Arena 才提供段位/统计。
- 但 API Registry 仍保留 `swarm_get_leaderboard`，scope/输出仍以 `world` 为 subject source，未将其重命名或限定到 Arena / non-competitive stats profile。

安全影响：World leaderboard 暴露会把非公平持久世界重新导向竞争排名，并可能扩大公开状态面。若该工具继续按 `world` 暴露，需要能力 profile 明确限定为 Arena competitive 或 World stats/analytics 非排名语义。

### D3 — Recycle lifespan-proportional

**Status: CLOSED**

- `economy.idl.yaml`、`api-registry.md`、`design/gameplay.md`、`specs/core/02-command-validation.md` 均采用 lifespan-proportional 10%–50% refund。
- `specs/reference/commands.md` 也引用 API Registry canonical formula。
- 旧 fixed 50% 主要残留在 `specs/core/09-snapshot-contract.md` 的经济边界段，已计入 B2 的经济对齐 GAP；Recycle 主合同本身已闭合。

### D4 — Snapshot budget 分模式 Arena 50ms / World 200ms

**Status: GAP**

- `snapshot-contract.md` 仅定义 `Snapshot build time < 200ms p95`，没有 Arena 50ms budget。
- `tick-protocol.md` 没有按 Arena/World 对 snapshot build budget 分模式，只给统一 tick/collect 预算。
- `design/engine.md` 的预算表有 Arena `≤50ms`，但行名为 `EXECUTE (2a+2b)`，不是 Snapshot build；不能作为 D4 的闭合证据。

## Informational

- `api-registry.md` 顶部包含生成日期、版本和 changelog。按仓库 AGENTS 约定，设计文档应避免日期/状态/变更标记；这不是 R25 指定安全闭合项，但会继续制造“目标规格 vs 历史记录”的噪声。
- `execute_code` 在当前 headless/cron 安全策略下被拒绝，验证改用只读 `terminal`/`rg`、`read_file` 和手工交叉核对完成。

## Item Summary

| Item | Result | Reason |
|---|---|---|
| B1 Host Function ABI | GAP | `specs/core/04-wasm-sandbox.md` 仍有旧 ABI / 输出上限 |
| B2 Economy values | PARTIAL | economy IDL 已修，但 gameplay IDL 与 snapshot-contract 仍有旧经济值 |
| B3 Tick budget | PARTIAL | tick-protocol 集中化，但 design/engine 与 D4 分模式预算仍未对齐 |
| B4 MCP 54→56 | GAP | registry 小节标题仍 54；security spec 仍把 active tools 标为 removed |
| B5 Snapshot truncation | GAP | snapshot-contract 与 tick-protocol/security visibility 仍双/三口径 |
| B6 Auth CSR replay + TTL | CLOSED | CSR replay class 与 TTL 主线已闭合，仅有默认值措辞残留 |
| D1 Arena room-first | CLOSED | modes 明确 P0 房间制、Tournament P1+ |
| D2 World non-competitive stats | PARTIAL | design 已闭合，API Registry 仍暴露 world leaderboard |
| D3 Recycle lifespan-proportional | CLOSED | 主合同闭合，旧 fixed 50% 残留并入 B2 |
| D4 Snapshot Arena 50ms / World 200ms | GAP | 未找到 Arena 50ms snapshot build gate 的权威闭合 |

## Required Closure Before APPROVE

1. 以 `api-registry.md` 为准修正 `specs/core/04-wasm-sandbox.md` 的 host function ABI、参数、输出上限与 budget 表。
2. 修正 MCP 工具总数标题为 56，并删除 `specs/security/03-mcp-security.md` 对 active onboarding/debug tools 的“已移除”声明，改为 scope/rate/detail-level 限制。
3. 将 `specs/core/01-tick-protocol.md` snapshot 截断段改为引用 `snapshot-contract.md`，移除旧关键桶/高优先桶算法；统一 `omitted_count` 脱敏/分桶策略。
4. 清理 `specs/gameplay/08-api-idl.md` 和 `specs/core/09-snapshot-contract.md` 的旧经济值，使其只引用 `economy.idl.yaml` / Resource Ledger。
5. 为 snapshot build budget 建立分模式权威表：Arena 50ms、World 200ms，并同步 design/engine、tick-protocol、snapshot-contract。
6. 将 `swarm_get_leaderboard` 限定到 Arena competitive profile，或改名/降级为 World non-competitive stats/analytics。