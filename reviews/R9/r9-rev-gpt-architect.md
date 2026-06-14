# R9 终审 — rev-gpt-architect

Reviewer: GPT-5.5 Architect
Date: 2026-06-14
Scope: `/data/swarm/docs/design/DESIGN.md` + `/data/swarm/docs/design/tech-choices.md` + `/data/swarm/docs/design/ROADMAP.md` + `/data/swarm/docs/specs/p0/`

## Verdict

APPROVE_WITH_RESERVATIONS

R9 已经可以进入 Phase 1 实现准备，但我不建议标成无条件 APPROVE。当前设计的核心架构已经稳定：AI 与人类统一走 WASM；MCP 只做 deploy/query/debug；mutating gameplay 统一进入 command validation；P0-1/P0-2/P0-4/P0-5/P0-8/P0-9 已形成 tick、sandbox、visibility、IDL、source gate 的闭环。相比 R8，本轮至少修正了 RuleMod API 中 `modify_entity` 的最危险表述，DESIGN 现在明确删除 `modify_entity`，改为 `deduct_resource` / `award_resource` / `damage_entity` / `set_entity_flag` 等较窄 action，并标注 mini-validator。

保留意见来自 4 个实现前容易分叉的合同问题，其中 A1/A2/A3 建议作为 Phase 1 开工前文档 patch；A4-A8 可进入 Phase 1/2/3 gate checklist。

## Strengths

1. 最大架构风险已避开：不存在 AI 专用 gameplay executor。MCP 是 AI 的屏幕、编辑器和调试器，不是 `move/attack/build` 控制器。世界只认 WASM，这使 fairness、metering、replay、anti-cheat 的边界简单且可解释。

2. Deferred Command Model 是正确的中心抽象。WASM 产出 command，engine 统一 validate/apply，避免 imperative host function 直接改世界导致权限绕过、TOCTOU 和 replay 分叉。

3. Source Gate 已把「谁能提交 gameplay 指令」建模出来。P0-9 的 source/capability 矩阵比常见游戏服务器设计更明确，尤其是把 MCP_Deploy、MCP_Query、Admin、Replay、TestHarness、Tutorial、RuleMod、Simulate、DryRun 分开，减少 confused deputy 风险。

4. Determinism Contract 覆盖了已知炸点：固定 PRNG/hash、禁 f64、禁 std::HashMap、IndexMap、ECS `.chain()`、Wasmtime version 进入 cache/replay 语义、state_checksum/replay 验证。这对可编程 MMO 是底层生命线。

5. P0-8 IDL single source of truth 是正确方向。Command enum、validator、SDK、MCP schema、docs、property tests 都从 IDL 派生，是防止 API drift 的唯一可持续方式。

6. Unified Visibility Policy 成熟度高。snapshot、MCP、WebSocket、REST、replay/spectator 都收敛到同一可见性策略，且区分 drone snapshot 与 player/spectator camera，这是信息泄漏类 bug 的关键防线。

7. ROADMAP 的总体顺序合理：先单人 deterministic vertical slice，再多人/MCP/source/visibility hardening，再 FDB/Dragonfly/ClickHouse/Rhai/global storage，再教程/Web/Arena/生产化。风险高的东西没有一开始就全上。

## Concerns

### A1 — HIGH — Phase 1 与 Phase 3 的 FoundationDB/持久化边界仍不一致

证据：
- ROADMAP Phase 1 依赖 P0-1/P0-2/P0-4/P0-8，并要求 TickTrace + replay 验证；Phase 1 Docker Compose 还包含 FDB + NATS。
- P0-1 §3.4 明确整个 EXECUTE 包在 FoundationDB transaction 中，commit 失败会 abandon tick。
- P0-1 §6.3 仍要求每 tick 写 FDB `/tick/{N}/commands|state|rejections|metrics`。
- ROADMAP Phase 3 又把「FoundationDB 持久化」作为 3.1，目标写成「世界状态持久化到 FoundationDB」。

风险：实现团队会分成两派：一派 Phase 1 就把 FDB 当权威存储，另一派 Phase 1 用内存/本地日志、Phase 3 才接 FDB。两种都可以，但文档现在同时暗示二者。最坏结果是 Phase 1 replay/tick atomicity 按内存实现，Phase 3 接 FDB 时重写 tick lifecycle。

建议修正（二选一）：
1. 明确 Phase 1 就使用 FDB authoritative TickStore；Phase 3 的 3.1 改为「FDB production hardening / multi-room schema / operational tuning」。
2. 或明确 Phase 1 使用 `TickStore` abstraction，可选 in-memory/local append log；P0-1 中 FoundationDB 事务语义在 Phase 1 映射为 single-process atomic commit，Phase 3 才切 FDB backend。

我更推荐第 2 个：Phase 1 先冻结 `TickStore` interface + replay checksum，避免一开始被 FDB 运维复杂度拖慢。

### A2 — HIGH — P0-2 的 `RawCommand.player_id` 仍与 P0-9 身份注入原则冲突

证据：
- P0-2 §2 `RawCommand` JSON 示例仍包含 `player_id`，字段规则是「必须匹配已认证玩家」。
- P0-9 §1/§3 明确「默认 gameplay 指令只来自 WASM；actor/capability/scope 由服务端注入；客户端不可自报 player_id」。
- P0-8 commands 本身没有 player_id，这是正确方向，但 P0-2 示例会影响 SDK/schema/codegen 实现。

风险：这是一类经典 IDOR/confused-deputy 失败模式。只要某个入口把 `RawCommand.player_id` 当成客户端字段生成 schema，validator 就可能从 body 读身份。即使有「匹配已认证玩家」检查，一旦任一入口漏绑定 auth，就会变成伪造身份字段。

建议修正：
- 玩家/WASM 输出 schema 改名为 `ClientCommand`: `{ tick, sequence, action }`，禁止 `player_id/source/auth/scope`。
- 内部 tick trace schema 才是 `AuthenticatedCommand`: `{ command: ClientCommand, auth: AuthContext }`，auth 完全由服务端注入。
- P0-2/P0-8 JSON Schema 增加 `additionalProperties: false`，并把 `player_id` 标成 forbidden property。
- Validator API 明确为 `validate(auth: &AuthContext, cmd: &ClientCommand, world: &World)`，禁止 `validate(raw: RawCommand)` 从 body 取身份。

### A3 — HIGH — Tick commit 所属阶段虽在 P0-1 正文清楚，但 DESIGN/ROADMAP 仍需单一表述

证据：
- P0-1 §3.4 正确写法：EXECUTE 阶段 FoundationDB commit，失败 abandon。
- P0-1 §4.2 正确写法：BROADCAST 读取 committed result，写 Dragonfly/NATS，失败不回滚。
- DESIGN §3.2 tick 生命周期也把 `FDB 原子提交` 放在 EXECUTE 阶段末尾，这是正确的。
- ROADMAP Phase 3 又把 FDB 持久化作为后置目标，使读者不确定 Phase 1 的 commit 语义到底是否执行。

风险不是概念错误，而是 phase contract 漂移。若有人把「Phase 3 才 FDB」误读为 Phase 1 BROADCAST 或 replay 写入可以是 best-effort，会破坏 P0-1 的 tick atomicity 和 replay 可信度。

建议：在 ROADMAP Phase 1 加一句 gate invariant：无论 backend 是 FDB、in-memory 还是 append log，`EXECUTE commit` 必须先于 `BROADCAST`，且 `BROADCAST` 永远不得写权威状态。

### A4 — MEDIUM — RuleMod 边界已改善，但 P0-7 与 DESIGN/P0-9 仍有语义残留

R9 正向变化：DESIGN §8.7 已删除 `modify_entity`，并改为「通过 actions，不进命令管线但经 mini-validator」。这是比 R8 安全得多的模型。

残留问题：
- P0-7 §8 仍写「规则 System 只能在 Command 执行前拦截、执行后补充、修改 ECS 资源/组件、绝不可绕过 Command 校验管线」。这和 DESIGN 的 mini-validator / RuleAction 模型不是同一套语言。
- P0-7 §8 还保留「手动控制追加」示例，而当前设计已明确 manual control 不开放。
- P0-9 说 RuleMod 仅 economy + event，但 DESIGN 允许 `damage_entity` / `set_entity_flag`，这已经超出纯 economy/event，属于 status/combat-adjacent capability。

风险：实现者可能回到两种错误之一：要么让 RuleMod 走玩家 CommandValidationPipeline，导致规则表达力不足；要么把 RuleMod 作为 privileged ECS mutation channel，绕过所有 validator。

建议：冻结 `RuleActionPipeline` 名称和边界：
- 独立于玩家 `CommandValidationPipeline`。
- 有自己的 typed action schema、capability manifest、budget、audit、deterministic ordering、replay record、before/after diff。
- Phase 3 默认 capability：`economy.deduct`、`economy.award`、`event.emit`、可选 `status.set_flag`；`damage_entity` 作为 high-risk capability，必须显式声明并默认不进官方首个模组。

### A5 — MEDIUM — IDL 与手写规范仍存在 drift，Phase 1 前需要以真实 `game_api.idl` 收敛

例子：
- P0-2 仍是手写 RawCommand/validation matrix，P0-8 是 IDL 示例；两者若都被实现者引用，会分叉。
- P0-2 部分失败码如 `InsufficientResources` 与 P0-8 `InsufficientResource { resource, required, available }` 风格不完全一致。
- P0-8 `tick` return 仍写 `i32`，注释为「0 = success, pointer to command JSON in WASM memory」，返回码/指针/长度/错误语义需要 ABI 级明确。
- ROADMAP Phase 1.7 写 TS SDK codegen，但没有把 `game_api.idl` 真文件、generator、generated docs/examples 作为 Phase 1.0 前置。

建议：Phase 1 开工第一步不是写 validator，而是提交真实 `game_api.idl` + generator stub + generated JSON schema/docs，并用 CI 禁止手写示例漂移。

### A6 — MEDIUM — Sandbox per-tick fork 是可行假设，但必须用 spike 验证成本

设计选择本身合理：每 tick fork/execute/kill 隔离强，状态清理简单，和 epoch interruption/cgroup/seccomp 配合清楚。

风险在吞吐：500 玩家、3s tick、每 tick snapshot serialization + worker fork + Wasmtime instantiate + IPC，空 tick 成本可能大于玩家代码执行成本。文档说 module cache 以 `(module_hash, wasmtime_version)` 缓存，但需要明确缓存在哪一层：engine、sandbox supervisor、compiled artifact mmap，还是每 worker 重新 instantiate。

建议：Phase 1 必须包含性能 spike：100/500 fake players、空 tick、path_find-heavy tick、不同 snapshot size，测 p50/p99。若 p99 接近预算，提前切 long-lived sandbox worker + per-tick store reset + epoch hard kill 模型。

### A7 — LOW — Blake3「代码签名」表述仍容易误导

tech-choices §8 仍把 Blake3 MAC 放在「代码签名」表中，并写「Blake3 全覆盖：哈希、PRNG、代码签名」。但 P0-3/P0-9 的身份信任链实际是 Ed25519 证书 + 部署签名，module_hash 才是 Blake3。

风险：新人可能把 keyed Blake3 MAC 当成客户端可证明身份的签名。MAC 是对称认证，不是第三方可验证签名。

建议改为：
- Blake3: content hash / XOF deterministic randomness / optional server-side MAC。
- Ed25519: all client-authenticated signatures and certificates。

### A8 — LOW — `player_view=full` 的公平性标签需要更明确

DESIGN/P0-5 已正确区分 `fog_of_war`（WASM snapshot）与 `player_view`（人类屏幕 / AI MCP 查看）。但 `player_view=full` 使 AI 可通过 MCP 全图观察再生成 WASM，人类也可通过屏幕全图改代码；它是「UI 同级」，不是 WASM 同级。

建议：世界配置中增加 `competitive_fair = true/false` 或在 World/Arena default 中明确：Arena 与默认 PvP World 禁用 `player_view=full`；Tutorial/PvE 可启用并显著标注非竞技公平。

## Missing

1. `TickStore` abstraction 或 Phase 1 FDB authoritative 选择（二选一）。
2. `ClientCommand` vs `AuthenticatedCommand` schema 分层，以及 forbidden auth fields。
3. `RuleActionPipeline` 规范：typed actions、capability manifest、mini-validator、audit/replay/diff。
4. 真实 `game_api.idl` 文件、codegen 命令、generated schema/docs/examples，以及 CI drift gate。
5. WASM ABI 返回协议：command buffer pointer/len/error code/free function 的明确约定。
6. Sandbox throughput spike 数据。
7. MCP/rmcp HTTP security contract 的 regression tests：Host/Origin/CORS/SSE/Bearer-only。P0-3 已有 HTTP 安全合同雏形，但建议补成测试矩阵。
8. Dragonfly stale detection 的 versionstamp/tick_number invariant：所有缓存读必须能检测过时并回退权威 store。

## Phase Ordering

### Phase 1 开工前文档 patch（建议 1 天内完成）

1. 解决 A1/A3：ROADMAP 明确 Phase 1 存储模型。推荐引入 `TickStore` abstraction；Phase 1 可 in-memory/local append log，Phase 3 切 FDB backend。但无论 backend，EXECUTE commit 永远先于 BROADCAST。
2. 解决 A2：P0-2 改 `ClientCommand`，删除客户端侧 `player_id`。
3. 解决 A5：提交真实 `game_api.idl` 和最小 codegen/CI gate。

### Phase 1 — 单人 deterministic vertical slice

必须交付：
- Bevy ECS minimal world。
- WASM sandbox baseline + malicious sample tests。
- IDL-generated Move/Harvest/Build/Spawn/Transfer。
- TickStore + TickTrace + state_checksum。
- Fresh-process replay determinism test。
- Starter bot 跑 1000 tick。
- Sandbox throughput spike 报告。

可暂缓：完整 OAuth、完整 MCP、多人 shuffle、Dragonfly、ClickHouse、Rhai、global storage。

### Phase 2 — 多人 + MCP + visibility/source hardening

必须交付：
- seeded shuffle + conflict/refund。
- Source Gate 全来源覆盖。
- MCP deploy/query/debug 工具 + Host/Origin/CORS/SSE/Bearer-only regression tests。
- OAuth2/Ed25519 certificate/deploy signature。
- Unified visibility 覆盖 snapshot/MCP/WS/REST/replay。
- `player_view` fairness policy。

### Phase 3 — Persistence + Rhai + global storage

必须交付：
- FDB production backend 或 FDB hardening（取决于 Phase 1 选择）。
- Dragonfly stale detection + versionstamp invariant。
- ClickHouse audit/metrics。
- RuleActionPipeline。
- global storage pending transfer/tax/visibility semantics。
- multi-room movement and visibility complexity budget。

## Final Call

APPROVE_WITH_RESERVATIONS。

架构方向已经足够好，且没有发现需要推翻的核心设计。剩下的问题不是「要不要做」，而是「实现合同必须再钉牢」。只要 Phase 1 前先修 A1/A2/A3/A5，进入实现是合理的。