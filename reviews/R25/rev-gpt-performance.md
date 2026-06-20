# R25 Closure Verification — GPT-5.5 Performance Reviewer

## Verdict

**CONDITIONAL_APPROVE**

大多数 R24 B-items 与 D-items 已闭合到可实现的性能合同：Host Function ABI、经济公式、tick budget、snapshot 权威截断、Arena/World 模式裁决、lifespan-proportional recycle 与分模式 snapshot budget 均有清晰权威源。仍有两个残留会影响实现者信任权威表：B4 MCP 工具 active/removed 状态仍在 security spec 中与 API Registry 冲突；B6 的证书 TTL 上限在 auth registry 仍保留 365d，与 Closure item 要求的 CodeSigning TTL 30–180d 未完全对齐。

---

## 逐项检查结果

| Item | Status | 性能评审结论 |
|---|---|---|
| B1 Host Function ABI 统一到 api-registry.md 权威签名 | CLOSED | API Registry 明确声明为 Host Functions 单一权威，5 个 host function 的签名、预算、输出上限与 fuel 成本集中在 `specs/reference/api-registry.md` §4；`specs/reference/host-functions.md` 与 `design/interface.md` 对核心签名基本同步。 |
| B2 经济数值对齐 economy.idl.yaml | CLOSED | `economy.idl.yaml` 与 Resource Ledger 对 RecycleRefund、StorageTax、AlliedTransfer、BuildCost、SpawnCost 等关键数值已对齐；RANGED_ATTACK=150、storage tax 30/60/85%、lifespan-proportional refund 均闭合。 |
| B3 Tick budget 对齐 | CLOSED | `specs/core/01-tick-protocol.md` §8 给出统一 tick budget；`design/engine.md` 使用 World/Arena 分表，EXECUTE 400ms、snapshot World 200ms p95 / Arena 50ms p99 口径一致。 |
| B4 MCP 工具清单 54→56 | **PARTIAL** | Registry 已显示 56 game tools + 11 auth tools，但 `specs/security/03-mcp-security.md` 仍把 `swarm_list_modules`、`swarm_explain_last_tick`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 标为“已移除/已整合”，而这些在 API Registry 中仍是 active tools。 |
| B5 Snapshot 截断统一到 snapshot-contract 权威 | CLOSED | `specs/core/09-snapshot-contract.md` 明确为唯一权威；`design/engine.md` 已引用相同 distance bucket → entity_id 字典序，并声明关键实体不可截断。 |
| B6 Auth CSR Replay Class + CodeSigning TTL 30–180d | **PARTIAL** | CSR/deploy replay 语义已基本闭合：deploy 使用 `version_counter` 和 `deploy_mutation`，auth/device idempotent 与 non_replayable 分类清晰。但 `specs/reference/api-registry.md` §5.8 仍写 `Cert validity max = 365d`，`auth_api.idl.yaml` 的 `validity_days` 未体现 CodeSigning 30–180d profile 限制。 |
| D1 Arena 房间制优先 | CLOSED | `design/modes.md` 明确 Arena P0 以 Room Match 为核心，Tournament/League 是 P1+ 上层编排。 |
| D2 World 非竞争统计 | CLOSED | `design/gameplay.md` 明确 World 无公开排行榜，仅非竞争统计；Arena 才提供竞技统计/榜。 |
| D3 Recycle lifespan-proportional | CLOSED | Resource Ledger §2.5、`economy.idl.yaml` RecycleRefund 与 API Registry §10 均使用 remaining_lifespan × 5000bp / total_lifespan，clamp 10%–50%。 |
| D4 Snapshot budget 分模式 Arena 50ms / World 200ms | CLOSED | `design/engine.md` tick budget 表明确 World Snapshot build ≤200ms p95、Arena ≤50ms p99；`snapshot-contract.md` capacity SLO 仍保留 World-oriented 200ms p95，未与 Arena 冲突。 |

---

## Strengths

1. **关键路径预算已收敛**：World 3s tick 与 Arena 300ms tick 已分模，避免用单一 snapshot SLO 同时约束持久世界与竞技房间。
2. **ECS 调度可分析**：`06-phase2b-system-manifest.md` 将 29 systems 拆为 serial spine + parallel sets，并声明 R/W matrix，利于 Bevy 调度和 CI 竞争检测。
3. **WASM 开销边界明确**：per-player 10M fuel、host call 1000/tick、path_find 10/tick + 100k explored nodes 全局 fair-share，可防无界 host function 放大。
4. **FDB 热点有所控制**：deploy blob 异步对象存储、FDB 仅提交 manifest/hash/pointer；tick 事务限定为 delta + TickTrace manifest + fuel 记录，避免大对象写入事务热路径。
5. **1000-player admission 不再硬承诺**：measured admission + degraded mode 使 1000 players 是 hard cap/admission target，而不是无条件 SLA。

---

## Concerns

### P1 — B4 MCP active/removed 残留会误导实现者

`specs/security/03-mcp-security.md` §4 仍声明若干工具已移除：

- `swarm_list_modules` 被说成替换为 `swarm_list_deployments`，但 API Registry §3.2 Deploy active list 中仍有 `swarm_list_modules`。
- `swarm_explain_last_tick` 被说成替换为 `swarm_get_tick_trace`，但 Registry §3.2 Debug active list 中仍有 `swarm_explain_last_tick`。
- `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 被说成“已整合”，但 Registry §3.2 中它们仍是 56 active tools 的组成部分。

性能影响：gateway/MCP server 如果按 security spec 实现，会少暴露 onboarding/debug 工具；如果按 registry 实现，则 security 审计与限流策略会漏配 active tools。该问题不是 tick 热路径瓶颈，但会造成 API surface drift 和测试矩阵不稳定。

### P1 — B6 CodeSigning TTL 30–180d 未在机器权威中闭合

`specs/security/09-command-source.md` 已写常用设备 30–180 天、临时设备 15min–24h、管理员 15min–1h；但 `specs/reference/api-registry.md` §5.8 仍写 `Cert validity max = 365d`，`auth_api.idl.yaml` 只有通用 `validity_days: u32` 字段和证书签发工具，没有 profile-level max。

性能/运维影响：证书 TTL 不直接影响 tick latency，但影响 deploy admission、CRL 保留窗口、revocation cache 大小与认证热路径缓存策略。365d 上限会扩大 CRL retention 与 revocation set，和 30–180d CodeSigning closure item 不一致。

### P2 — Snapshot contract 与 tick-protocol 仍有旧截断描述残留，但已被权威引用覆盖

`specs/core/01-tick-protocol.md` §2.3 仍保留“分桶权重”旧描述；不过同文件 §8 与 `design/engine.md` 已引用 Snapshot Contract 权威算法。当前判定为 CLOSED，因为实现者有明确权威源，但建议后续删除旧算法段或改成纯引用，降低 reviewer 噪声。

### P2 — 1000 players 的吞吐叙述仍偏乐观

`design/engine.md` 中 1000 players × 5ms 的估算依赖 40 cores/1000 workers 并行化与 snapshot stitching ≈500ms。该估算可作为目标直觉，但应由 benchmark gate 验证；目前 measured admission 能兜底，不构成 closure gap。

---

## Bottleneck Analysis

### Tick 关键路径

- **COLLECT**：per-player WASM 执行仍是最大成本项。World 使用 2500ms per-player timeout + worker pool；1000 active players 时必须依赖 fuel throttling、worker pool 和 admission control，否则平均 5ms/player 会超出单线程预算。
- **Snapshot stitching**：World snapshot 200ms p95 与 Arena 50ms p99 分模合理；per-player 256KB cap 和 deterministic truncation 防止单玩家可见实体爆炸。
- **EXECUTE**：Phase 2a inline command loop 是串行公平/确定性瓶颈；Phase 2b 只开放 combat/status 部分并行。若 1000 players × 100 commands/tick 达上限，EXECUTE 400ms 可能成为瓶颈，应依赖 command cap 与 rejection fast path。
- **FDB COMMIT**：事务设计为 delta + manifests，理论上可控；真正风险是单 tick mutation count 与 hot key contention。Snapshot Contract 中 Per-tick FDB mutation count <5000 SLO / 10000 hard budget 是必要门槛。

### ECS 并行调度

- Serial spine 保守但可证明 determinism，适合设计冻结阶段。
- Parallel Set A/B 的 R/W matrix 有利于 Bevy schedule 静态验证。
- 主要剩余性能风险不是 data race，而是 Phase 2a inline command loop 和 resource_ledger last-stage serialization。

### WASM fuel metering

- Fuel 与 host call budget 都有明确上限；`host_path_find` 使用 per-player call cap + global explored_nodes fair-share，避免无界 A*。
- Cache hit 仍消耗相同 fuel，保持 replay determinism，牺牲部分性能但避免 cache-state side channel。
- `swarm_simulate` / `swarm_dry_run` 使用独立预算池，避免调试工具挤占实际 tick。

### FDB / Database Hotspots

- Deploy 路径已将 large blob 移出 FDB，降低事务大小风险。
- TickTrace 与 state/fuel 同事务保证审计一致性，但需要控制 mutation count；否则 1000 players 场景下 trace rows 可能成为写放大热点。
- ResourceLedger last-stage 汇总若按全局 key 写入，会形成热点；文档强调 per-operation attribution，但实现阶段应按 player/room/tick 分区 key。

---

## Throughput Estimates

| 场景 | 估算 | 风险 |
|---|---:|---|
| Arena 1v1 / 小房间 | ≤100ms tick 可达 | Snapshot 50ms p99 + EXECUTE 50ms 目标合理，实体数小。 |
| World 500 active players | 3s tick 可达，100ms 不适用 | 500 × 5ms avg 正好吃满 2500ms COLLECT；需要 worker pool 与 snapshot sharing。 |
| World 1000 active players | 需要 admission/fuel throttle | 文档已承认每玩家可用约 2ms；应视为 degraded/admission hard cap，不是稳定 SLA。 |
| 1000 drones 单房间 | Arena ≤100ms 取决于 command density | 如果每 drone 都输出 command，Phase 2a serial apply 与 RoomCap/resource ledger 会成为主瓶颈。 |
| Host pathfinding heavy load | 有界但会降级 | 100k explored_nodes/tick 全局 fair-share 下，1000 players 仅约 100 nodes/player，复杂路径会 deterministic fail。 |

---

## Closure Summary

- **CLOSED**: B1, B2, B3, B5, D1, D2, D3, D4
- **PARTIAL**: B4, B6
- **GAP**: none severe enough to reopen tick/snapshot/economy performance architecture, but B4/B6 must be corrected before final APPROVE.

Final Verdict: **CONDITIONAL_APPROVE**
