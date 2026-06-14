# R10 终审 — rev-gpt-architect

Reviewer: GPT-5.5 Architect
Date: 2026-06-14
Scope: `/data/swarm/docs/design/DESIGN.md` + `/data/swarm/docs/design/tech-choices.md` + `/data/swarm/docs/design/ROADMAP.md` + `/data/swarm/docs/specs/p0/`

## Verdict

CONDITIONAL_APPROVE

R10 可以进入 Phase 1，但我仍不建议给无条件 APPROVE。整体架构已经越过最危险的早期分叉：AI 与人类统一写 WASM，MCP 不承载 gameplay action；Deferred Command Model、Source Gate、Unified Visibility、IDL single source of truth、Determinism Contract 都已经形成闭环。R9 中若干 blocker 已有明显修复，例如 P0-1 现在明确 FDB rollback 失败时必须 `world.restore(snapshot)`，DESIGN 也把特殊攻击补上冷却/成本，并把 drone lifespan/body 不可逆的玩法问题纳入规则。

但 R10 的主要问题不再是「大方向错」，而是「冻结文档里仍残留多套语义」。这些残留如果不在 Phase 1 开工前收敛，会导致实现团队各自解释合同，最后在 TickStore、身份注入、RuleMod、IDL/ABI、数值确定性上返工。

结论：CONDITIONAL_APPROVE；允许 Phase 1 启动 prerequisite spikes / scaffolding，但 A1-A5 应作为 Phase 1 coding gate 前的文档 patch 和测试 gate。

## Strengths

1. AI fairness 的核心抽象正确：世界只认 WASM。MCP 是观察、部署、调试界面，不是 `swarm_move` / `swarm_attack` 的动作控制器。这一点比大多数「AI-native game」设计更清晰。

2. Tick lifecycle 已经接近可实现合同。P0-1 明确 COLLECT 超时宽容、EXECUTE 原子提交、BROADCAST 不回滚 committed tick、NATS/Dragonfly 失败不影响权威状态；这避免了实时系统里常见的「广播成功才算 tick 成功」错误。

3. Source Gate 是非常重要的安全边界。P0-9 把 WASM、MCP_Deploy、MCP_Query、Admin、Replay、TestHarness、Tutorial、Deploy、Rollback、RuleMod、Simulate、DryRun 分开建模，避免所有入口都伪装成“command”。

4. Determinism Contract 覆盖面较好：Blake3、禁 f64、禁 std::hash、IndexMap、固定 ECS 顺序、state_checksum、replay validation 都已写入设计。这是可编程 MMO 的地基。

5. Unified Visibility Policy 把 snapshot、MCP、WebSocket、REST、replay/spectator 统一到 `is_visible_to`，并明确区分 drone 感知与玩家/观众视角，信息泄露面比早期版本小很多。

6. ROADMAP 的总体风险顺序合理：先单人 deterministic vertical slice，再多人/source/visibility/MCP，再 FDB/Rhai/多房间，再 Web/Arena/生产化。没有试图第一阶段就做完整 MMO。

7. 技术选型整体务实：Rust+Bevy、Wasmtime、NATS、Dragonfly、ClickHouse、TS/Rust SDK 都有明确取舍理由；没有为“现代化”而引入不必要的链路。

## Concerns

### A1 — HIGH — Phase 1 / Phase 3 的权威 TickStore 边界仍未冻结

证据：
- ROADMAP Phase 1 要求 TickTrace + replay 验证、docker-compose 包含 FDB + NATS。
- P0-1 §3.4 写整个 EXECUTE 包在 FoundationDB transaction 内，commit fail 则 tick abandon。
- P0-1 §6.3 写每 tick 写入 FDB `/tick/{N}/commands|state|rejections|metrics`。
- ROADMAP Phase 3 又把 “FoundationDB 持久化”列为 3.1，目标是世界状态持久化到 FDB。

风险：实现者会分裂成两种路线：Phase 1 就把 FDB 当 authoritative store，或 Phase 1 只做 in-memory/local log、Phase 3 才接 FDB。两者都可以，但合同必须唯一。否则 Phase 1 的 replay、abandon、rollback、broadcast 顺序到 Phase 3 会重写。

建议：在 ROADMAP 和 P0-1 增加 `TickStore` 冻结条款：
- Phase 1 可以使用 `InMemoryTickStore` / `AppendLogTickStore`，但必须暴露与 FDB backend 相同的 atomic `commit_tick()` 语义。
- `EXECUTE commit before BROADCAST` 是不随 backend 改变的 invariant。
- Phase 3 的 FDB 交付物改名为 “FDB TickStore backend + production schema/hardening”，而不是首次引入持久化语义。

### A2 — HIGH — ClientCommand 与 AuthenticatedCommand 仍未在所有文档中彻底分离

证据：
- P0-9 原则正确：actor/capability/scope 由服务端注入，客户端不可自报 `player_id`。
- 但 P0-2 §2 `RawCommand` 示例仍包含 `player_id`，字段规则是“必须匹配已认证玩家”。
- P0-8 commands 本身没有 `player_id`，这与 P0-9 一致，但 P0-2 的手写 schema 会误导实现。

风险：这是经典 IDOR/confused deputy 入口。只要某个 SDK、MCP、REST、test harness 复用了 P0-2 的 RawCommand body，就会把身份作为可提交字段。即使 validator 做“匹配认证玩家”，一旦某个 source 漏绑定 auth，就会产生跨玩家 command 注入。

建议：冻结两层类型：
- `ClientCommand = { tick, sequence, action }`，来自 WASM/客户端，不允许 `player_id/source/auth/scope/module_hash`。
- `AuthenticatedCommand = { command: ClientCommand, auth: AuthContext }`，仅服务端内部和 TickTrace 使用。
- Validator 签名必须是 `validate(auth, command, world)`，禁止从 command body 读取 actor。
- P0-2 JSON schema 明确 forbidden properties，并 `additionalProperties: false`。

### A3 — HIGH — P0-8 的 WASM ABI 返回语义仍不够可实现

证据：
- P0-8 `tick` host/export 描述为 `returns: i32  # 0 = success, pointer to command JSON in WASM memory`。
- P0-4/P0-8 说明 snapshot 写入 linear memory、tick 返回 command JSON，但没有冻结返回 pointer/length/error 的 ABI 结构。

风险：`i32` 同时表达状态码和 pointer 是 ABI 级歧义。实现者可能产生三套不兼容约定：返回 ptr、返回 errno、返回 packed ptr/len，或者通过 host callback 取输出。ABI 一旦进入 SDK codegen 和玩家样例，后续变更会破坏所有 bot。

建议：Phase 1 前冻结最小 ABI，例如：
- `tick(snapshot_ptr: i32, snapshot_len: i32) -> i64`，高 32 位 len、低 32 位 ptr，0 表示空 command list，负值/独立 `last_error` 表示 trap 前错误；或
- `tick(...) -> i32` 返回 status，输出通过 `swarm_alloc_output()` / `swarm_output_ptr()` / `swarm_output_len()` 查询；或
- guest export `get_commands_ptr/len`。

无论选哪种，都要进入 `game_api.idl`，生成 TS/Rust SDK shim，并用恶意/畸形 ABI 样本测试。

### A4 — MEDIUM — RuleMod capability 语言仍在三处漂移

证据：
- DESIGN §8.7 允许 Rhai actions：`deduct_resource`、`award_resource`、`damage_entity`、`set_entity_flag`、`emit_event`，并说经 mini-validator。
- P0-9 §2.3 把 RuleMod 写成“仅 economy + event”。
- P0-7 §8 仍说规则 System 可“修改 ECS 资源/组件”，又说“绝不可绕过 Command 校验管线”，还残留“手动控制追加”表述；而 DESIGN 已删除 manual_control。

风险：RuleMod 是第二条高权限写路径。如果它既不走玩家 CommandValidationPipeline，又没有独立 RuleActionPipeline，就会演化成 privileged arbitrary ECS mutation。反过来，如果强行走玩家 command pipeline，规则模组表达力又不足。

建议：冻结 `RuleActionPipeline`：typed schema + capability manifest + mini-validator + deterministic ordering + budget + audit + replay record + before/after diff。
- Phase 3 默认 capability 只开放 `economy.deduct`、`economy.award`、`event.emit`。
- `status.set_flag` 作为 explicit opt-in。
- `damage_entity` 属 combat/high-risk capability，Phase 6 前不要进默认官方模组。
- 删除 P0-7 的“手动控制追加”和“修改 ECS 资源/组件”泛化表述。

### A5 — MEDIUM — IDL single source 仍停留在文档示例，Phase 1 前缺真实 artifact gate

证据：
- P0-8 是 `game_api.idl` 示例和 codegen 规则，但仓库文档未明确真实 `game_api.idl` 文件路径、generator crate、generated schema/docs 的提交策略。
- P0-2 仍维护手写 validation matrix；P0-8 也维护 command/rejection/cost。两份权威会 drift。
- ROADMAP Phase 1.7 才写 TS SDK codegen，但 validator、schema、MCP schema、docs 都依赖它，实际应是 Phase 1.0 前置。

风险：实现会先手写 Rust enum/validator，再补 generator，最后 IDL 变成文档而非 source of truth。Screeps-like API 一旦玩家开始使用，迁移成本极高。

建议：Phase 1 第一项改为 `1.0 game_api.idl + generator skeleton`：
- 提交真实 IDL 文件。
- 生成 Rust command enum、JSON schema、TS types、MCP schema stub、markdown docs。
- CI `gen-api && git diff --exit-code`。
- P0-2 从“权威手写矩阵”降级为“解释性说明”，字段名/失败码引用 IDL。

### A6 — MEDIUM — 固定点数值合同与 TOML 示例冲突

证据：
- DESIGN §8.8 明确禁 f64，游戏数值用整数 + fixed，Rhai 关闭浮点。
- 但 DESIGN/P0-7 示例仍有 `transfer_to_global_cost = { Energy = 0.01 }`、`damage_multiplier = 1.0`、`decay_rate = 0.001`、`source_regeneration = 1.0` 等浮点字面量。
- P0-7 也有 `fixed<u32,4>` 的整数写法，如 `source_regeneration_rate = 10000`。

风险：配置解析器如果接受 TOML float，就把非确定性和跨语言序列化问题重新引入。即使内部转 fixed，四舍五入规则、精度、非法小数处理都需要冻结。

建议：所有 world.toml 示例统一为 fixed integer 或 string decimal with exact parser，二选一：
- 推荐 `transfer_to_global_cost = { Energy = 100 }  # fixed<u32,4> = 0.01`。
- `damage_multiplier = 10000`，`decay_rate = 10`。
- 配置校验拒绝 TOML float；docs 明确“浮点字面量仅说明文本，不是配置格式”。

### A7 — MEDIUM — Wasmtime per-tick fork 是最大性能假设，ROADMAP 缺早期 spike gate

证据：
- tech-choices 选择 Wasmtime 的理由包含 per-tick fork 生命周期、epoch interruption、fuel metering。
- P0-4 架构是 sandbox worker 独立进程；ROADMAP Phase 1 要 3s tick、starter bot 1000 tick。

风险：per-tick fork + module instantiate + snapshot serialization 可能在单人 MVP 没问题，但多人 Phase 2 会变成 tick p99 主因。若 Phase 1 不测 50/100 bots 的 instantiate/cache/fuel 开销，Phase 2 可能发现需要 warm pool 或 persistent worker protocol，影响 sandbox API。

建议：Phase 1 增加 spike gate：
- 1/10/50/100 bot，64MB memory，256KB snapshot，10M fuel，测 collect p50/p95/p99。
- 对比 cold instantiate、precompiled module cache、worker pool 三种模式。
- 冻结 module cache key：`player_id + module_hash + wasmtime_version + abi_version + world_rules_hash`。

### A8 — LOW — 文档状态标签与冻结叙事不一致

证据：
- DESIGN §9 写 Phase 0 架构冻结完成。
- P0-2/P0-3/P0-4/P0-5/P0-8/P0-9 多数标注 Frozen/Architecture Freeze。
- P0-1 和 P0-6 仍标注 “Phase 2 阻断项”。

风险：不是架构 bug，但会让执行者不知道哪些文档是 Phase 0 frozen contract，哪些是 Phase 2 backlog。

建议：统一 frontmatter/status：`status: Frozen for Phase 0` + `implementation_phase: Phase 1/2/...`。阻断项应进入 ROADMAP gate，而不是让规范状态看起来未冻结。

## Missing

1. 真实 `game_api.idl` artifact、generator skeleton、CI gate。
2. `TickStore` interface 和 backend strategy（Phase 1 in-memory/log vs Phase 3 FDB）。
3. WASM ABI output convention：ptr/len/error/free 的精确定义。
4. `RuleActionPipeline` 的正式 spec：schema、capability、budget、audit、replay、diff。
5. 配置 fixed-point 编码规范：TOML 是否允许 float、如何精确解析、如何显示。
6. Wasmtime performance spike 报告和 module cache key 规范。
7. Multi-room/sharding 的 transaction boundary 草案：Phase 7 才做 sharding 可以，但跨房间移动在 Phase 3 出现，至少需要早期接口约束。
8. Admin/Rollback 双人审计的具体 protocol：P0-9 写了策略，但还缺 nonce、expiry、two-signature payload、replay protection。

## Phase Ordering

建议调整为：

0. Phase 1.0 — Contract hardening（开工前 2-4 天）
   - Patch A1-A6 文档。
   - 提交真实 `game_api.idl` + generator skeleton。
   - 冻结 `ClientCommand` / `AuthenticatedCommand` / `TickStore` / WASM ABI。

1. Phase 1.1 — Deterministic single-player core
   - InMemory/AppendLog TickStore 也可以，但必须实现 commit-before-broadcast 和 replay checksum。
   - Bevy ECS `.chain()`、state_checksum、TickTrace 最小闭环。

2. Phase 1.2 — Sandbox spike before full SDK
   - Wasmtime fuel、epoch、memory cap、host query、ABI output。
   - 跑 1/10/50/100 bot benchmark，再决定 cold fork、precompiled cache、worker pool。

3. Phase 1.3 — IDL-driven API and starter bot
   - Rust/TS/MCP schema/docs 从 IDL 生成。
   - Starter bot 只依赖 generated SDK，不手写临时 API。

4. Phase 2 — Multiplayer + Source Gate + visibility
   - 先把 AuthContext/source/capability 贯穿所有入口，再开放 MCP full toolset。
   - 统一 visibility cache 后再做 WebSocket delta。

5. Phase 3 — FDB backend + Rhai under constrained RuleActionPipeline
   - FDB 是 TickStore backend hardening，不改变 tick semantics。
   - Rhai 默认只开放 economy/event，combat/status capability 延后或显式 opt-in。

6. Phase 4+ — Tutorial/Web/Arena/Production
   - 保持原 ROADMAP 大体顺序。
   - Arena 前必须完成 config fixed-point、visibility/spectator/replay privacy、rollback/admin audit 的测试。

