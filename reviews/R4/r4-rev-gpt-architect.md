# Round 4 评审 — rev-gpt-architect

Reviewer: GPT-5.5 / Architect
Scope: `/data/swarm/docs/design/DESIGN.md` + `/data/swarm/docs/specs/p0/` 全部 9 份 P0 specs
Focus: contract cleanup 是否完成、IDL 是否完整、Phase 0 completion criteria 是否可验证

## Verdict

APPROVE_WITH_RESERVATIONS — Phase 0 已经基本具备“架构冻结”的形态，但还不能算 clean freeze。

结论分三层：

1. Contract cleanup：大方向完成，尤其是 MCP 不再作为 gameplay channel、WASM 是唯一 gameplay executor、deferred command model、Command Source Model、visibility policy 都已经形成闭环。但文档里仍有几处旧 contract 残留，会误导 Phase 1 实现：DESIGN §5 仍列出 mutating host functions；P0-4 §8 仍给 `host_move`/`host_harvest` 等禁止函数标成本；DESIGN §8 的架构图/默认值表仍残留 `manual_control`；部分配置仍用 `f64`/浮点写法，和 determinism contract 冲突。

2. IDL 完整性：P0-8 已经从“散落 API 列表”进化为可生成 Command、Validator、SDK、MCP schema、Docs、Test 的单一真相来源，这是 Round 4 最大进展。但 IDL 还不是完整可执行 contract：缺 Snapshot schema、Entity/Component schema、MCP tool schema 细节、Error/Result ABI、memory ownership/free ABI、Command JSON discriminant 与文档样例的命名一致性、global storage commands 的 source/capability/visibility 映射，以及 IDL 自身文件落地路径与 CI artifact list。

3. Phase 0 completion criteria：当前 DESIGN §9 把 Phase 0 标成 ✅ 完成，并列出 10 个完成项；这些项多数可追溯到 P0-1/P0-2/P0-4/P0-7/P0-8/P0-9。但“可验证”仍不足：缺一份机器可检查的 freeze checklist，缺每项对应的 acceptance test、schema generation target、lint rule、negative tests、trace/replay fixture。现在的完成标准更像“评审共识已写入文档”，还不是“实现团队可用 CI 验收”。

我的建议：允许进入 Phase 1 spike/prototype，但在第一行代码落地前安排一个 very small “P0-final cleanup” commit，把下面 Remaining Concerns A1-A5 修掉。否则 Phase 1 会在旧 host function、新 deferred command、source gate、IDL generator 四套合同之间来回打架。

## Strengths

S1. 最大风险点已经被正确收敛：AI 和人类同路径。

P0-1 §2.1 明确“唯一执行器：WasmSandboxExecutor”，P0-3 §1/§4.5 明确 MCP 是屏幕和鼠标、不直接操控实体，P0-4 §3 明确 `tick() -> JSON` deferred model。这是本架构最关键的安全/公平/可解释性选择。它像成功系统里的“single write path”：所有真正改变世界的动作都进入同一管线，而不是为 AI 特开后门。

S2. Command Source Model 是 Round 4 质量提升的核心。

P0-9 把 `WASM`、`MCP_Deploy`、`MCP_Query`、`Admin`、`Replay`、`TestHarness`、`Tutorial`、`Deploy`、`Rollback`、`RuleMod`、`Simulate`、`DryRun` 全部显式建模，并强调 actor/capability/scope 由服务端注入、客户端不可自报。这解决了很多“看起来只是内部调用，实际会绕过权限”的经典失败模式。

S3. Visibility policy 已从散点规则变成统一函数。

P0-5 的 `is_visible_to(entity, player_id, tick)` 是很好的架构锚点。它覆盖 snapshot、MCP、WebSocket、REST、replay，并要求 visibility cache 防止不同输出面泄露不一致。这个设计很像成熟多人游戏后端里的 policy gate，值得保留为 hard boundary。

S4. Determinism contract 比上一轮更具体。

DESIGN §8.8 固定了 ChaCha12、Blake3、禁 f64/Rhai 浮点、IndexMap、ECS `.chain()`、state checksum、CI replay sampling。这些不是“愿景”，而是可翻译成 lint/test 的实现约束。尤其是禁 `std::hash` 和禁浮点，是容易被新人忽视但上线后很难排查的 determinism 雷点。

S5. P0-8 IDL 的方向正确。

“game_api.idl 生成 Rust Command enum + Validator trait + host function stubs + TS SDK + MCP schemas + docs + property tests”是正确抽象。它把之前最容易漂移的层：host ABI、Command JSON、SDK 类型、MCP docs、validator matrix，拉到一个 source of truth 下面。这个方向明显优于手写多份 schema。

S6. Tick failure semantics 开始像生产系统。

P0-1 §6 覆盖 WASM timeout/crash/invalid output、FDB commit fail、Dragonfly stale/miss、NATS publish fail、Broadcast partial、TickTrace write fail。特别是 tick abandon 不递增 tick_counter、退还 fuel、降级模式，这些是持久世界里必须提前定义的“灾难时钟语义”。

S7. MVP feedback loop 没丢。

P0-6 把 Learn / Decide / Act / Understand 作为 MVP 闭环，这是对“可编程游戏”非常实用的约束。很多类似项目失败不是因为模拟器不够强，而是玩家完全不知道为什么自己的代码没动。`swarm_explain_last_tick`、starter bot、本地模拟、回放查看器都是正确方向。

## Remaining Concerns

A1. Contract cleanup 未完全完成：mutating host functions 仍在顶层 DESIGN 中作为“唯一可调用函数”出现。

证据：DESIGN §5 仍写着“以下是在 WASM 沙箱中唯一可调用的函数”，并列出 `host_move`、`host_move_to`、`host_harvest`、`host_transfer`、`host_build`、`host_attack`、`host_spawn` 等 mutating host functions。与此同时 DESIGN §8.5 和 P0-4 §3 又明确“不得通过 host function 直接修改世界状态”。

这不是小文案问题。新人实现时很可能优先读 DESIGN §5，然后真的暴露 `host_move`。一旦这样做，deferred command model、validator pipeline、refund、TickTrace、replay、source gate 全都会被绕开或重复实现。

建议：
- 删除 DESIGN §5 的 mutating host function 列表，替换为：
  - WASM module export ABI：`tick(snapshot_ptr, snapshot_len) -> result_ptr`
  - 只读 host functions：`get_terrain`、`get_objects_in_range`、`path_find`、`get_world_config`、`get_world_rules`
  - Mutating API 只存在于 returned Command JSON / IDL commands 中
- P0-4 §8 的 host function cost table 只保留查询函数；mutating commands 的成本应迁移到 IDL command budget/cost/refund 语义中。

A2. IDL 仍不完整：现在是 command IDL，不是完整 Game API IDL。

P0-8 很好，但覆盖面还差几个必须项：

- Snapshot schema：WASM `tick()` 输入和 MCP `swarm_get_snapshot` 声称一致，但 IDL 没定义 `WorldSnapshot`、`VisibleEntity`、`TerrainTile`、`PlayerResources`、`MarketOrder`、`WorldRules`。
- Entity/Component schema：DESIGN §3 有 ECS 组件草图，P0-5 有可见性输出字段，P0-8 没把它们并入生成 schema。
- Result ABI：host functions 全部 `i32` 返回，但没有统一 `OK/ERR_BUFFER_TOO_SMALL/ERR_OUT_OF_BOUNDS/ERR_NOT_VISIBLE` 等错误码表。
- Memory ABI：`tick()` 返回 pointer，但谁分配、长度如何返回、谁释放、是否需要 `alloc/free` exports、返回 JSON pointer 如何防悬挂，都未冻结。
- Command discriminant 不一致：P0-2 JSON 用 `action.type = "Move"`，P0-4 禁止函数示例写 `{ "cmd": "move" }`，DESIGN §8.5 TypeScript 示例写 `{ cmd: "spawn" }`。IDL 需要决定 canonical wire format。
- MCP schema 只说“生成 MCP tool schemas JSON”，但没有列出每个 tool 的 params/result/error/rate limit/audit category。
- Global storage commands 在 P0-8 出现，但 P0-2 validation matrix 没覆盖，P0-9 source capability 表里 WASM 可读写全局存储，RuleMod 不可读写全局存储；具体如何从 WASM 触发 TransferToGlobal/TransferFromGlobal 还不够清晰。

建议：把 P0-8 分成 `game_api.idl` 的四块：types/entities/snapshot、commands、readonly_host_functions、mcp_tools。Phase 1 只实现 subset 也可以，但 IDL 必须先声明完整边界。

A3. Phase 0 “完成”目前可追溯，但不可验证。

DESIGN §9 的 Phase 0 checklist 是人类可读的完成声明，不是工程可验收标准。缺少：

- 每个冻结项的 file/section anchor 和 test name。
- “contract cleanup complete”的 grep/lint 规则。例如禁止 `host_move` 作为允许 host function 出现；禁止 `manual_control` 出现在正式世界配置；禁止 `f64` 出现在 rules config 示例；禁止 MCP gameplay tools。
- IDL generation CI 的实际 artifact list。P0-8 §4 有 `cargo run -- gen-api && git diff --exit-code`，但还没有声明生成文件路径、schema golden files、docs golden files。
- Replay/determinism acceptance fixture。DESIGN §8.8 提到 CI 随机采样 tick 做 full replay，但 Phase 0 没定义最小 fixture：固定 world_seed、固定 commands、固定 expected state_checksum。
- Source Gate negative tests。P0-9 很关键，但 Phase 0 completion criteria 没要求测试 `MCP_Deploy` 提交 gameplay command 必须 403、客户端自报 `player_id` 必须被覆盖、Tutorial source 在非 tutorial world 必须丢弃。

建议新增 `/data/swarm/docs/specs/p0/10-phase0-freeze-checklist.md` 或在 DESIGN §9 下补 “Verification Matrix”：每一项包含 Contract、Source of Truth、Must Not Exist、Acceptance Tests、CI Gate。

A4. Determinism contract 仍被浮点和示例配置破坏。

DESIGN §8.8 明确禁 f64/Rhai 浮点，但文档仍出现：

- DESIGN §8.7 i18n 示例中 `room_superlinear type = "f64"`、`default = 0.1`。
- P0-7 world.toml 示例中 `decay_rate = 0.001`、`damage_multiplier = 1.0`，validate_config 里还有 `damage_multiplier < 0.0`。
- DESIGN §8.3 中 `source_regeneration = 1.0`、`build_cost = 1.0`、`drone_decay = 1.0`。

这些看似只是示例，但实现者会照抄成 TOML parser + Rust f64。确定性 bug 往往就从“配置只是浮点，模拟内部再转换”开始。

建议：全部改为 fixed integer 表达：`fixed<u32,4>` 写作 `10000`，展示层再格式化为 `1.0000`。并给 config linter 规则：world.toml 和 mod.toml 禁止 float token，除非字段标记为 display-only 且不进入 simulation。

A5. World Rules Engine 的 capability 边界还不够硬。

P0-7 §1 说“模组通过 actions 请求引擎操作——不能绕过 Command Validation Pipeline”，但 DESIGN §8.7 / P0-7 又列出 `actions.deduct_resource`、`award_resource`、`modify_entity`，并在 P0-9 把 RuleMod capability 写成“仅经济 + 事件”。这里有潜在冲突：`modify_entity` 过宽，几乎可以改任何组件，从而绕过游戏规则。

经典失败模式：mod API 一开始为了方便给了 `modify_entity(entity_id, property, value)`，半年后所有 server rules 都依赖它，validator pipeline 形同虚设。

建议：RuleMod actions 使用 capability-specific verbs，不要给 generic property mutation：
- `deduct_resource(player_id, resource, amount)`
- `award_resource(player_id, resource, amount)`
- `apply_status_effect(entity_id, effect, duration)`
- `emit_event(event_type, data)`
- 如需 entity mutation，必须通过 typed action + validator，例如 `damage_entity`, `heal_entity`, `set_cooldown`，每个 action 有 schema、scope、audit、determinism test。

A6. Tick commit 语义仍有一处文档异味。

P0-1 §3.4 说 FDB commit 在 EXECUTE 阶段末尾，§4.2 又列 `1. FDB.commit()`，再用注释解释 BROADCAST 不访问 FDB、这里是空操作/文档一致性标记。这个写法会让实现者困惑：到底有没有第二次 commit？

建议：把 BROADCAST §4.2 改成：
1. Read committed tick result from in-memory post-commit state or FDB versionstamp
2. Dragonfly.update(delta)
3. NATS.publish(...)
并明确 BROADCAST failure never rolls back committed tick。

A7. P0 docs 的状态标签和 DESIGN §9 不一致。

多份 P0 spec 顶部仍写“Phase 2 阻断项”，但 DESIGN §9 把 Phase 0 标成完成，并引用这些 P0 规范作为 Architecture Freeze 成果。状态语义会混乱：它们到底是 P0 freeze contracts，还是 Phase 2 blockers？

建议统一状态字段：
- `Status: Frozen for Phase 0`
- `Implementation phase: Phase 1/2/...`
- `Blocks: Phase 2 MCP / Phase 1 Engine / etc.`

A8. MVP feedback loop 引入了 `swarm_validate_plan`，但它和“没有直接提交指令通道”之间需要更明确的边界。

P0-6 §3.1 把 `swarm_validate_plan` 定义为“如果我提交这些指令，会成功吗？”，但 §4 又说没有直接提交指令通道，所有动作必须经过 WASM。这个工具容易被误实现成 MCP gameplay pre-submit channel。

建议改名或限义：`swarm_validate_commands_offline` / `swarm_simulate_commands`，输入必须是 snapshot-bound Command[]，source 为 `Simulate`，只在副本上跑 validator，不产生 RawCommand、不进入 TickTrace gameplay queue、不允许用当前隐藏状态补全。

## Fresh Ideas

F1. 增加 “Contract Linter” 作为 Phase 0 最小工具。

写一个很小的脚本扫 docs：
- 禁止 allowed host function 列表中出现 `host_move|host_attack|host_build|host_spawn`。
- 禁止 MCP tools 出现 `swarm_move|swarm_attack|swarm_build|swarm_spawn`。
- 禁止正式世界配置出现 `manual_control`。
- 禁止 simulation config 示例出现 float literal。
- 要求所有 P0 specs 顶部有统一 status metadata。

这比人工评审可靠，且能防 Round 5 又回归旧合同。

F2. 把 Phase 0 checklist 做成 “traceability matrix”。

格式建议：

| Freeze Item | Source of Truth | Must Not Exist | Generated Artifacts | Required Tests | Owner Phase |
|---|---|---|---|---|---|
| Deferred Command Model | P0-4 §3, P0-8 commands | mutating host functions | Command enum, SDK commands | schema reject + no host import | Phase 1 |
| Source Gate | P0-9 | client player_id trusted | source enum | MCP gameplay 403 | Phase 1 |
| Visibility | P0-5 | unfiltered debug outputs | snapshot schema | leak tests | Phase 2 |

这样 Phase 0 completion 才从“文档勾选”变成“实现前验收协议”。

F3. 给 IDL 加 “negative generation”。

除了生成 happy-path SDK，也生成攻击样本：
- unknown fields
- wrong source
- hidden entity inspect
- out-of-bounds buffer
- illegal import
- float config
- replay checksum mismatch

这些可以直接喂 Phase 1/2 CI。安全和确定性靠 negative tests 最稳。

F4. 对 `WorldSnapshot` 做版本化 envelope。

建议所有 snapshot 都包一层：

```json
{
  "schema_version": 1,
  "abi_version": 1,
  "tick": 4521,
  "visibility_hash": "...",
  "world_rules_hash": "...",
  "entities": []
}
```

`visibility_hash` 和 `world_rules_hash` 能帮助 replay/debug：玩家说“我当时看不到”，系统可以证明该 tick 的视野和规则版本。

F5. 把 RuleMod actions 设计成 “mini command bus”。

RuleMod 不应直接改 ECS，而是提交 typed `RuleAction`，进入一个独立但可审计的 rule action validator：

`Rhai -> RuleAction[] -> RuleActionValidator -> apply after command systems -> TickTrace`

这保留 mod 能力，同时不会污染玩家 Command pipeline。也更容易 replay。

F6. 建一个 “P0 Golden World” fixture。

一个 2 玩家、1 房间、固定 seed、固定 commands 的最小世界：
- Player A/B 同采一个 source，测试 seeded shuffle + refund。
- 一个 hidden enemy，测试 visibility。
- 一个 rejected command，测试 explain/rejection detail。
- 一个 rule mod 扣资源，测试 RuleAction trace。
- 一个 deploy at tick N，测试 N+1 生效。

这比抽象 spec 更能保护 Phase 1 实现。

F7. 把 “MCP is screen/mouse, not controller” 放进 docs banner。

这个约束太关键，建议每份相关 spec 顶部都加短句：

“Gameplay commands are produced only by WASM tick output. MCP may deploy/query/debug/simulate, but never directly enqueue gameplay commands.”

重复是值得的，因为这是最容易被后续贡献者破坏的边界。

## Final Recommendation

进入 Phase 1 前做一次 P0-final cleanup，不需要大改架构，只需要收紧合同：

1. 删除/替换 DESIGN §5 mutating host functions。
2. 删除 P0-4 §8 mutating host function cost table entries。
3. 全文清理 `manual_control` 正式世界残留。
4. 全文清理 simulation config 浮点示例，统一 fixed integer。
5. 扩展 P0-8 IDL：Snapshot、Entity、Result ABI、Memory ABI、MCP tool schema、canonical Command JSON。
6. 新增 Phase 0 verification matrix + contract linter。
7. 明确 RuleMod actions 的 typed capability boundary。

完成这些后，我会把 Verdict 提升到 APPROVE。当前版本适合“有保留通过”，但不适合直接宣称 Phase 0 彻底完成。