# R26 GPT-5.5 Performance Closure Verification

## Verdict

**CONDITIONAL_APPROVE**

R26 的 R25 REOPEN/WEAK 残留大多已闭合：tick budget 语义、MCP 工具计数、snapshot truncation、IDL 经济数值、CodeSigning TTL、World/Arena 展示边界均已对齐。唯一仍需收口的是 **R4 sandbox host function ABI**：`04-wasm-sandbox.md` 仍内联 5 个 host function 签名，虽与 `api-registry.md §4.1` 当前一致，但未像 `08-api-idl.md` 那样把 ABI 签名完全委托给权威源；这会保留未来签名漂移风险。

## Strengths

- B3 已把 `tick-protocol` 的 EXECUTE 语义拆清：500ms 是硬超时天花板，`design/engine.md §3.4.1` 的 World ≤400ms / Arena ≤50ms 是 budget target；性能合同没有再把 target 与 hard cap 混为同一值。
- B4 已统一为 56 个 active Game API tools，security spec 改为 Authority note，不再把 active 工具描述成移除状态。
- R3 已从 `tick-protocol` 清除自有 snapshot truncation 算法，改为引用 `snapshot-contract` 的唯一权威源，避免双算法导致 replay drift。
- R5/R7/R8 的数值与模式边界已闭合：RangedAttack=150、Recycle=lifespan-proportional、CodeSigning 默认 30d、World 非竞争展示 + Arena 房间制。

## Concerns

### P1 — R4 GAP: sandbox 仍内联 host function ABI 签名

- 位置：`specs/core/04-wasm-sandbox.md:202`
- 证据：`04-wasm-sandbox.md §3.2` 仍直接列出：
  - `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`
  - `host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32`
  - `host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32`
  - `host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32`
  - `host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32`
- 对照：`specs/reference/api-registry.md:390` 起定义 5 个 host function 的权威 ABI 与调用预算；`specs/gameplay/08-api-idl.md:239` 已声明“所有签名的权威定义见 API Registry §4”。
- 性能影响：当前不是运行时瓶颈，但这是性能/沙箱合同的 drift 风险。若未来 Registry 调整 `range` 类型、输出上限或 host call fuel 成本，sandbox 文档可能继续诱导实现者按旧签名或旧成本估算，导致 fuel metering 与 host-call hot path 估算失真。
- 建议修复：将 `04-wasm-sandbox.md §3.2` 的签名块改为“允许的 host function 名称 + 可见性/只读语义”，ABI 签名、输出上限、per-call fuel 全部引用 `api-registry.md §4`，避免在 sandbox spec 中二次定义 ABI。

### P2 — 无新增阻塞性能项

- B3 的 500ms hard cap 保留是可接受的：它高于 engine target，代表 watchdog ceiling，不等同目标 tick budget。
- R3 现在由 snapshot-contract 独占 truncation 排序规则，能避免 `1000 drones` 场景下 snapshot 截断路径出现文档双轨。
- MCP 工具数量/分类对 tick critical path 无直接负担；rate limit 与 capability profile 已集中在 API Registry，可避免 security spec 重复枚举造成管理面 drift。

## Bottleneck Analysis

### B3 Tick Budget — CLOSED

- `specs/core/01-tick-protocol.md:73`：EXECUTE 阶段写为“硬超时天花板: 500ms”，并明确引用 `design/engine.md §3.4.1: World ≤400ms, Arena ≤50ms`。
- `design/engine.md:288`：Tick Pipeline 预算表定义 EXECUTE (2a+2b) 为 World ≤400ms / Arena ≤50ms。
- 性能判断：这是合理的 “target + watchdog ceiling” 双层约束。只要 CI/bench 以 engine.md 的 ≤400ms 作为性能回归门槛，500ms ceiling 不会放宽目标 tick budget。

### B4 MCP Tool List — CLOSED

- `specs/reference/api-registry.md:209`：总数为 56 个 active game_api tools + 11 Auth API tools。
- `specs/reference/api-registry.md:226`：Game API 工具清单标题为 `(56)`。
- `specs/security/03-mcp-security.md:223`：MCP 工具权威清单引用 API Registry §3.2 — 56 工具。
- 性能判断：工具清单统一后，限流、capability profile、debug/admin 面不再因旧 “removed” 文案产生实现歧义；这降低管理面争用和不必要兼容分支。

### R3 Snapshot Truncation — CLOSED

- `specs/core/01-tick-protocol.md:157`：超限截断策略见 Snapshot Contract §4，声明 snapshot-contract 是 snapshot truncation 的唯一权威源。
- `specs/core/09-snapshot-contract.md:52`：定义确定性截断顺序：距离桶、`entity_id` 字典序、从最远桶末尾移除、critical 不可截断。
- 性能判断：截断算法单源化后，实现可把 snapshot hot path 固定为 `O(visible_entities log visible_entities)` 或桶化后的近似线性流程，不再需要支持 tick-protocol 旧分桶权重算法。

### R4 Host Function ABI — GAP

- `specs/core/04-wasm-sandbox.md:202` 仍内联 ABI 签名；其中部分行有“权威签名见 api-registry.md §4.1”尾注，但不是纯委托。
- `specs/reference/api-registry.md:396` 是 5 个 host functions 的 canonical ABI；`api-registry.md:406` 起还定义 host call budget、输出上限、per-call fuel。
- 性能判断：host call 是 WASM tick 内最容易变成热点的路径，ABI/输出上限/fuel 成本必须单源。当前内联签名虽然一致，但保留 drift 面，不宜视为完全闭合。

### R5 IDL Economy Values — CLOSED

- `specs/gameplay/08-api-idl.md:230`：`RangedAttack: { Energy: 150 }`。
- `specs/reference/economy.idl.yaml:328`：`RANGED_ATTACK cost: 150`。
- `specs/gameplay/08-api-idl.md:164`：Recycle refund 为 `RecycleRefund(...) # lifespan-proportional 10%-50%`。
- `specs/reference/economy.idl.yaml:57`：RecycleRefund 定义为 lifespan-based partial refund，`refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)`。
- 性能判断：RangedAttack cost 与 Recycle formula 已统一，经济模拟不再需要旧 100/flat 50% 兼容分支。

### R6 Leaderboard / world_stats — CLOSED

- `specs/reference/api-registry.md:256`：`swarm_get_world_stats` 在 Play category，用于 World 非竞争统计。
- `specs/reference/api-registry.md:321`：`swarm_get_leaderboard` 在 Arena category，visibility 为 `arena_only`。
- `design/modes.md:24`：World 不设竞争榜单。
- `specs/gameplay/06-feedback-loop.md:327`：World 为趣味展示（非竞争排名）。
- 性能判断：World 统计与 Arena leaderboard 分离，可避免 World tick critical path 被竞争榜单排序/赛季逻辑绑死。

### R7 CodeSigning TTL — CLOSED

- `design/auth.md:274`：`CodeSigningCertificate` TTL 为 `30–180 days（默认 30d，world.toml 可配）`。
- `design/auth.md:296`：常用设备证书推荐 TTL 同为 `30–180 days`。
- 性能判断：这不是 tick hot path，但闭合后可减少 deploy/auth 管理面异常重签和证书轮换频率，降低非 tick 路径的 FDB/auth 写入噪声。

### R8 Tournament/MVP → 房间制 + 非竞争展示 — CLOSED

- `design/modes.md:88`：Arena P0 以房间制比赛为核心，无自动匹配、无天梯排名、无赛季；Tournament/League 为 P1+ 上层编排。
- `specs/gameplay/06-feedback-loop.md:331`：Arena 为房间制比赛。
- `specs/gameplay/06-feedback-loop.md:327`：World 仅趣味展示（非竞争排名）。
- 性能判断：P0 不引入全局赛季/天梯维护，Arena 房间可按独立 tick loop 隔离，避免把 leaderboard/tournament 聚合写入塞进 World tick critical path。

## Throughput Estimates

- **World 1000 active players / 10000 drones cap**：若实现严格遵守 `engine.md §3.4.1`，EXECUTE target 为 ≤400ms、tick interval 为 3000ms；R26 文档闭合项不会新增 tick critical path 负担。
- **Arena ≤100ms 目标风险**：`engine.md` 当前 Arena EXECUTE 预算为 ≤50ms，COMMIT ≤20ms，BROADCAST ≤10ms，合计在 100ms 内有余量；但这依赖 host call budget 与 fuel metering 统一执行，因此 R4 的 ABI/fuel 单源化仍应修。
- **WASM fuel overhead**：API Registry 已集中 host call 总预算、单函数上限、输出上限与 per-call fuel；只要 sandbox 实现引用 Registry 生成/校验，metering overhead 可被上界化。R4 残留的内联 ABI 是主要 drift 风险，不是当前已知无界操作。
- **FDB 热点**：本轮验证项未发现新增 FDB 热点。B3/B8 的闭合有利于保持 FDB commit 为小事务，避免 tournament/leaderboard 或 deploy 管理逻辑进入权威 tick commit 热点。

## Item Checklist

| Item | Status | Evidence |
|------|--------|----------|
| B3 Tick budget | CLOSED | `tick-protocol.md` 500ms hard cap 明确引用 `engine.md` World ≤400ms / Arena ≤50ms budget target |
| B4 MCP tool list | CLOSED | `api-registry.md` intro + §3.2 均为 56；`03-mcp-security.md` 使用 Authority note |
| R3 snapshot truncation | CLOSED | `tick-protocol.md` 改为引用 `snapshot-contract` 唯一权威源 |
| R4 sandbox/IDL host ABI | GAP | `08-api-idl.md` 已委托 API Registry；`04-wasm-sandbox.md §3.2` 仍内联 ABI 签名 |
| R5 RangedAttack/Recycle | CLOSED | `08-api-idl.md` 与 `economy.idl.yaml` 均为 RangedAttack 150 + lifespan-proportional Recycle |
| R6 leaderboard/world_stats | CLOSED | `world_stats` 属 Play；`leaderboard` 属 Arena；World 明确非竞争展示 |
| R7 CodeSigning TTL | CLOSED | `auth.md` 证书表与设备生命周期均为 30–180 days，默认 30d |
| R8 Tournament/MVP | CLOSED | Arena P0 房间制；Tournament/League P1+；World 非竞争展示 |

## Final Verdict

**CONDITIONAL_APPROVE** — 7/8 项 CLOSED，1/8 项 GAP。建议在 R27 前仅修复 R4：把 `specs/core/04-wasm-sandbox.md §3.2` 的 host function ABI 签名改为引用 `specs/reference/api-registry.md §4` 的权威签名、预算、输出上限与 per-call fuel。修复后从性能角度可 APPROVE。
