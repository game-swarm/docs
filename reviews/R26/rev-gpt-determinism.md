# R26 Determinism Closure Verification — GPT-5.5

## Verdict

**CONDITIONAL_APPROVE**

R26 指定的 R25 REOPEN/WEAK 项中，B3、B4、R3、R5、R7、R8 已按窄范围验证闭合；但 R4 与 R6 仍存在会影响确定性/生成链闭包的残留：Host Function ABI 的 signedness 在多处旁路文档仍与 API Registry 不一致，且 `game_api.idl.yaml` 仍把 `swarm_get_leaderboard` 定义在 Play/none visibility，与生成后的 registry Arena-only 口径冲突。

---

## 逐项检查

### B3 — Tick budget：CLOSED

证据：
- `specs/core/01-tick-protocol.md:73-77` 将 EXECUTE 写为“硬超时天花板: 500ms”，并明确 `budget target` 见 `design/engine.md §3.4.1`。
- `design/engine.md:288-299` 的预算表仍将 EXECUTE budget 定为 World ≤400ms、Arena ≤50ms。

确定性判断：500ms 已不再作为预算目标，而是硬超时天花板；预算目标由 engine.md 单一表承载。tick 超时合同与性能预算合同可区分，不再构成 replay/tick closure 的双口径。

### B4 — MCP 工具清单与 security Authority note：CLOSED

证据：
- `specs/reference/api-registry.md:209-226` 声明 game_api 为 56 个活跃工具，并将清单标题写为 `Game API 工具清单 (56)`。
- `specs/security/03-mcp-security.md:223-227` 将 MCP 工具权威清单、认证定义、authz/capability profiles 指向 API Registry / IDL。
- `specs/security/03-mcp-security.md:264` 与 `03-mcp-security.md:272` 使用 Authority note，声明本文档不再自行声明移除状态，active/removed 状态以 API Registry 为准。
- `specs/security/03-mcp-security.md:270` 明确 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 为 active onboarding/play 工具。

确定性判断：工具 active set 现由 registry 统一承载，安全文档不再产生“active 工具已移除”的旁路状态机。B4 闭合。

### R3 — tick-protocol snapshot truncation → 纯引用 snapshot-contract：CLOSED

证据：
- `specs/core/01-tick-protocol.md:157-161` 声明超限截断策略见 Snapshot Contract，且 **snapshot-contract 是 snapshot truncation 的唯一权威源**；tick-protocol 不定义独立截断算法。
- `specs/core/09-snapshot-contract.md:52-80` 定义确定性截断顺序：距离桶、`entity_id` 字典序、从最远桶末尾移除。
- `specs/core/09-snapshot-contract.md:80-103` 定义 critical entity 永不截断与 competitive degraded 标记。

注意：`specs/core/01-tick-protocol.md:138-155` 仍保留 `sort_and_truncate(entities, 256_000)` 级别的伪代码，但未展开独立排序/截断算法，并在紧随其后的规范文本中把算法权威交给 snapshot-contract。按本轮“验证残留是否已清理”的窄范围，旧的多算法口径已关闭。

### R4 — sandbox/IDL host function ABI → api-registry 权威签名：GAP

证据：
- `specs/reference/api-registry.md:390-404` 声明 Host Functions 为权威签名，`host_get_objects_in_range` 为 `(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32`。
- 但 `specs/core/04-wasm-sandbox.md:206-215` 仍内联 ABI，且 `host_get_objects_in_range` 为 `range: i32`。
- `design/interface.md:72-83` 仍内联概念签名，`host_get_objects_in_range` 为 `range: i32`，虽随后说明权威定义见 API Registry。
- `specs/reference/host-functions.md:29-32` 仍写 `range: i32`。
- `specs/gameplay/08-api-idl.md:239-264` 的概念 IDL host_functions 块仍写 `get_objects_in_range params: [x: i32, y: i32, range: i32, ...]`。

确定性影响：WASM host ABI 是 replay/tick 闭包的一部分。即使运行时可将非负 i32 解释为 u32，SDK/codegen、IDL 绑定、ABI 校验与跨语言 stub 会从不同文档得到不同 signedness。`tick(seed, state, commands) -> new_state` 的闭包依赖所有节点使用同一 ABI schema；当前仍有旁路 schema 可导致生成物漂移。因此 R4 未闭合。

建议闭合条件：删除旁路文档中的本地签名，或将所有 `host_get_objects_in_range` 的 `range` 统一为 API Registry 的 `u32`，并明确 codegen 只从 API Registry / `game_api.idl.yaml` 读取 ABI。

### R5 — 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional：CLOSED

证据：
- `specs/gameplay/08-api-idl.md:225-231` 将 `RangedAttack` body cost 写为 `{ Energy: 150 }`。
- `specs/gameplay/08-api-idl.md:161-164` 将 Recycle refund 写为 `RecycleRefund(body_cost, remaining_lifespan, total_lifespan)`，并标注 lifespan-proportional 10%–50%，权威公式见 `economy.idl.yaml`。
- `specs/reference/economy.idl.yaml:60-85` 定义 RecycleRefund 参数与公式：`max(1000, (remaining_lifespan * 5000) / total_lifespan)`，refund amount 为 `(refund_rate_bp * body_cost) / 10000`。

确定性判断：经济数值与回收公式已从固定/旧值转为单一 lifespan-proportional 公式。R5 闭合。

### R6 — D2-A leaderboard→Arena, world_stats→Play：GAP

证据：
- `specs/reference/api-registry.md:252-271` 将 `swarm_get_world_stats` 放在 Play，并标注 World 非竞争统计所需字段。
- `specs/reference/api-registry.md:317-325` 将 `swarm_get_leaderboard` 放在 Arena，visibility filter 为 `arena_only`。
- `specs/reference/api-registry.md:361-374` 的 capability profiles 将 `play` 描述为包含 `swarm_get_world_stats`，将 `arena` 描述为包含 `swarm_get_leaderboard`。
- 但 `specs/reference/game_api.idl.yaml:677-692` 仍在 `# Play (14 tools)` 下定义 `swarm_get_leaderboard`，`category: Play`，`visibility_filter: none`。

确定性影响：API Registry 的展示稿已经正确，但其声明来源为 IDL；机器权威/生成源仍保留旧分类会导致 registry 重新生成后回滚。对跨节点一致性而言，capability profile、visibility filter 与 replay-safe read surface 都是节点必须一致执行的访问控制合同；IDL 与 registry 冲突意味着同一工具在不同生成链上可能被分配到 Play 或 Arena，破坏“同一 tick/同一 principal 在所有节点看到同一可见输出”的合同。因此 R6 未闭合。

建议闭合条件：在 `game_api.idl.yaml` 中将 `swarm_get_leaderboard` 移至 Arena category/profile，并将 visibility filter 改为 `arena_only`；确认 `swarm_get_world_stats` 作为 Play/World 非竞争统计保留；重新生成 `api-registry.md`。

### R7 — CodeSigning default 7d→30d：CLOSED

证据：
- `design/auth.md:267-275` 的用途隔离证书表将 `CodeSigningCertificate` TTL 写为 `30–180 days（默认 30d，world.toml 可配）`。
- `design/auth.md:280-288` 描述代码签名证书过期语义，不再把 7d 作为代码签名默认值。

确定性判断：CodeSigning 的默认 TTL 已统一为 30d。文档中其它 7d（如 refresh token 或 TickTrace retention）不属于 CodeSigning 默认 TTL，本项闭合。

### R8 — feedback-loop Tournament/MVP → 房间制 + 非竞争展示：CLOSED

证据：
- `specs/gameplay/06-feedback-loop.md:327-338` 将 World 统计定义为趣味展示/非竞争排名，将 Arena 定义为房间制比赛，并声明无自动匹配、无天梯排名、无赛季；Tournament/League 为 P1+ 上层编排，不在 P0 MVP 范围。
- `specs/gameplay/06-feedback-loop.md:340-355` 的 MVP 功能清单包括 Arena 房间制比赛与回放排行榜（非竞争展示）。
- `design/modes.md:86-88` 同样定义 Arena P0 以房间制比赛为核心，Tournament/League 为 P1+。

确定性判断：P0 状态机不再被 Tournament-first 口径污染；World 非竞争展示与 Arena 房间制边界清晰。R8 闭合。

---

## State Machine Gaps

- **R4 Host ABI schema gap**：WASM host import ABI 仍有 `range: i32` / `range: u32` 双口径。ABI 是 replay-critical schema，必须从单一权威生成，否则 SDK stub、ABI validation、fuel/visibility host-call wrapper 可能在不同节点或语言绑定中分叉。
- **R6 capability/visibility source gap**：`game_api.idl.yaml` 与 `api-registry.md` 对 `swarm_get_leaderboard` 的 category/profile/visibility 不一致。若 registry 由 IDL 生成，当前正确 registry 不是稳定闭包。

## Non-Determinism Sources

- **隐式 schema 非确定性**：不同实现者若选择 API Registry 或旁路文档生成 host bindings，会得到不同 signedness。该问题不一定立即导致运行时随机性，但会导致跨 SDK/跨节点 ABI 合同不闭包。
- **访问面生成链非确定性**：leaderboard 在 IDL 中仍为 Play/none，在 registry 中为 Arena/arena_only。不同节点若基于不同 artifact 执行 authz/visibility，将产生不同输出集合。

## Final Verdict

**CONDITIONAL_APPROVE**

阻塞残留仅限两项：
1. `R4` — `host_get_objects_in_range.range` signedness 仍在 `04-wasm-sandbox.md`、`design/interface.md`、`host-functions.md`、`08-api-idl.md` 与 API Registry 不一致。
2. `R6` — `game_api.idl.yaml` 仍将 `swarm_get_leaderboard` 放在 Play 且 `visibility_filter: none`，与 `api-registry.md` Arena/`arena_only` 冲突。
