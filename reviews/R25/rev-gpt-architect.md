# R25 Closure Verification — GPT Architect

## Verdict

**CONDITIONAL_APPROVE**

R24 的大部分合同清理已经向正确方向收敛：经济公式、Recycle、Arena 房间制、World 非竞争统计、CodeSigningCertificate TTL 等核心决策已落到文档中。但闭环仍未完成，主要残留是典型的“权威表已修、旁路 spec 未同步”失败模式：Host Function ABI、Tick budget、MCP 工具状态、World leaderboard、snapshot budget 仍存在跨文档冲突。

## Strengths

- Canonical-source 思路已建立：`api-registry.md`、`economy.idl.yaml`、`09-snapshot-contract.md` 开始承担权威表角色。
- 经济层从绝对阈值/固定退款转向 basis-points 与 lifespan-proportional，方向正确。
- Arena 已明确 Room Match 优先，Tournament/传播能力降为扩展/RFC，抽象层次更合理。
- Auth 的 CSR replay class 与 CodeSigningCertificate TTL 语义已基本闭合。

## Concerns

### A1 — B1 Host Function ABI: GAP

`specs/reference/api-registry.md:389` 明确 Host Functions 权威签名共 5 个，`host_get_terrain(room_id, out_ptr, out_len)`、`host_path_find(..., opts_ptr, opts_len, out_ptr, out_len)`、`host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len)`。

但 `specs/core/04-wasm-sandbox.md:202` 仍保留旧 ABI：`host_get_terrain(x, y) -> i32`、`host_path_find(..., out_ptr, out_len)` 缺少 opts、`host_get_world_rules(out_ptr, out_len)` 缺少 rule_id。并且同文件 `specs/core/04-wasm-sandbox.md:347` 的成本表仍写 `host_get_terrain` 输出 4 bytes，而 registry/host-functions/IDL 是 8 KB。

这不是表述小错，而是 WASM sandbox 实现者会直接照抄的 ABI 合同，属于闭环失败。

### A2 — B2 经济数值对齐: PARTIAL

`specs/reference/economy.idl.yaml:57` 已定义 RecycleRefund 为 remaining-lifespan proportional，10%–50%；`specs/core/08-resource-ledger.md:159` 与 `design/gameplay.md:106` 也对齐。storage tax、global transfer delay、drone cap 也大体对齐到 percentage tiers / 100 tick / per-player 50。

但 `specs/gameplay/08-api-idl.md:162` 仍有旧 `refund: registry.body_cost(body) * 0.5`，与同文件稍后 `specs/gameplay/08-api-idl.md:318` 的 lifespan-proportional 描述冲突。经济 B2 不是全 GAP，但仍有旧字段会误导代码生成或 schema 作者。

### A3 — B3 Tick budget 对齐: GAP

`design/engine.md:290` 已给出 World/Arena 分模式 budget：World SNAPSHOT ≤200ms p95、Arena ≤50ms p99、EXECUTE ≤400ms/≤50ms。

但 `specs/core/01-tick-protocol.md:73` 仍画出 EXECUTE 超时 500ms；同文件 `specs/core/01-tick-protocol.md:690` 又把 EXECUTE 写成“由 COLLECT+EXECUTE 总预算控制，不单独超时”。这和 design 的 400ms/50ms phase budget 不是同一模型。`specs/core/09-snapshot-contract.md:390` 只保留 snapshot build <200ms p95 / hard 500ms，未体现 Arena 50ms p99。

架构上这是“预算表多源化”旧问题复发：实时性、admission、benchmark gate 会各自实现一套口径。

### A4 — B4 MCP 工具清单 54→56: GAP

`specs/reference/api-registry.md:207` 写“共计 56 个活跃工具”，但 `specs/reference/api-registry.md:226` 标题仍是 “Game API 工具清单 (54)”。这正是 R24 B4 指出的 count drift。

更严重的是 `specs/security/03-mcp-security.md:267` 仍把 `swarm_explain_last_tick` 标为“已移除”，`specs/security/03-mcp-security.md:275` 仍把 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 标为“已移除”；而 `specs/reference/api-registry.md:240`、`specs/reference/api-registry.md:271`、`specs/reference/api-registry.md:298` 明确这些仍是 active tools。新人会直接困惑：安全 spec 说删了，registry 说可用。

### A5 — B5 Snapshot truncation 权威化: PARTIAL

`design/engine.md:412` 已引用 Snapshot Contract，并写出距离桶与 stable entity_id sort；这是正确方向。

但 `specs/core/09-snapshot-contract.md:390` 的 capacity section 仍以 World 侧 200ms p95 为主，未反映 D4 的 Arena 50ms p99 / World 200ms p95 分模式预算。`specs/security/05-visibility.md:91` 仍包含 `leaderboard_snapshot`，也把 snapshot contract、visibility、World 非竞争模型搅在一起。

截断算法本身基本收敛，但预算和可见字段仍未完全统一到 snapshot-contract 权威。

### A6 — B6 Auth CSR Replay + CodeSigning TTL: CLOSED

`design/auth.md:312` 将 `swarm_submit_csr` 归为 `non_idempotent_mutation`，并要求 FDB 事务内消费 PoW challenge；`design/auth.md:340` 的方法矩阵同样标注 `swarm_submit_csr` 为 non_idempotent_mutation。

`specs/security/09-command-source.md:118` 将常用设备证书 TTL 统一为 30–180 天，并说明 deploy 提交时校验证书有效、自然过期不影响已部署模块。这一项从架构角度已闭合。

### A7 — D1 Arena 房间制优先: CLOSED

`design/modes.md:100` 以后以 Create → Configure → Ready → Play → Finish → Replay 的 Room Match 流程描述 Arena；Tournament/社区 replay 排行榜被放在 RFC/传播能力中。P0 房间制优先已落实。

### A8 — D2 World 非竞争统计: PARTIAL

`design/gameplay.md:530` 明确 World 无公开排行榜，仅提供非竞争统计 `swarm_get_world_stats`，Arena 用 stats 提供段位统计。

但 `specs/security/05-visibility.md:68` 仍定义公开 `LEADERBOARD`，指标含 GCL、房间数、drone 数；`specs/security/05-visibility.md:91` 仍在 snapshot 里给 `leaderboard_snapshot`。这会把竞争型排名重新带回 World 可见性合同。D2 未完全闭合。

### A9 — D3 Recycle lifespan-proportional: PARTIAL

资源账本与 economy IDL 已闭合：`specs/reference/economy.idl.yaml:57`、`specs/core/08-resource-ledger.md:159`、`design/gameplay.md:106` 都是一致的 10%–50% lifespan-proportional。

残留是 `specs/gameplay/08-api-idl.md:162` 的旧固定 50% refund 字段。若该文档被 codegen 或 SDK 示例读取，会重新引入旧行为。

### A10 — D4 Snapshot budget 分模式: GAP

`design/engine.md:290` 有 Arena 50ms p99 / World 200ms p95，但 `specs/core/09-snapshot-contract.md:390` 仍只有 World-like 200ms p95 / hard 500ms；`specs/core/01-tick-protocol.md:690` 也没有分模式 snapshot budget。D4 要求的是“分模式预算落地”，目前只在 design 层落地，核心 spec 未闭合。

## Missing

- 缺少一个自动 drift check：Host Function ABI、MCP tool count、snapshot budget、Recycle refund 这种表格不应再靠 reviewer 人肉发现。
- 缺少“权威源引用但不重复签名”的清理策略：sandbox/security/gameplay spec 仍复制了 registry/ledger 的旧值。
- 缺少 Arena/World capability profile 的统一引用：World leaderboard/stats 边界仍散落在 gameplay、visibility、registry 中。

## Phase Ordering

1. 先修 B1/B4：这两个是接口面，最容易被实现者照错；把 sandbox/security 中的旧 ABI 与 removed-tools 文案改为引用 registry。
2. 再修 B3/D4：把 `01-tick-protocol.md` 与 `09-snapshot-contract.md` 合并到同一 World/Arena budget 表，去掉 500ms EXECUTE 残留。
3. 再修 D2/D3/B2 残留：清理 `08-api-idl.md` 的固定 50% refund，清理 visibility 的公开 leaderboard/snapshot 字段。
4. 最后补 drift check：至少 grep/check 56 vs 54、old host ABI、`* 0.5` recycle、`leaderboard_snapshot`、EXECUTE 500ms。

## Item Matrix

| Item | Status | Note |
|---|---|---|
| B1 Host Function ABI | GAP | sandbox ABI 与 api-registry 权威签名冲突 |
| B2 Economy values | PARTIAL | 主体闭合，08-api-idl 仍有 fixed 50% refund |
| B3 Tick budget | GAP | 400ms/50ms vs 500ms/soft-deadline 多口径 |
| B4 MCP tools 54→56 | GAP | registry 自身 56/54 矛盾，security 仍标 active tools removed |
| B5 Snapshot truncation | PARTIAL | 算法收敛，budget/visibility 字段仍漂移 |
| B6 Auth CSR + TTL | CLOSED | non_idempotent CSR 与 30–180d TTL 已对齐 |
| D1 Arena room-first | CLOSED | Room Match 流程已是 P0 |
| D2 World non-competitive stats | PARTIAL | gameplay 对，visibility 仍有 public leaderboard |
| D3 Recycle proportional | PARTIAL | ledger/IDL 对，08-api-idl 旧 refund 残留 |
| D4 Snapshot split budget | GAP | design 有，core spec 未落实 |
