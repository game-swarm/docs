# R5 最终检查 — rev-gpt-architect

Verdict: CONDITIONAL_APPROVE

本轮读取范围：
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/specs/p0/01-tick-protocol-spec.md
- /data/swarm/docs/specs/p0/02-command-validation-spec.md
- /data/swarm/docs/specs/p0/03-mcp-security-contract.md
- /data/swarm/docs/specs/p0/04-wasm-sandbox-baseline.md
- /data/swarm/docs/specs/p0/05-unified-visibility-policy.md
- /data/swarm/docs/specs/p0/06-mvp-feedback-loop.md
- /data/swarm/docs/specs/p0/07-world-rules-engine.md
- /data/swarm/docs/specs/p0/08-game-api-idl.md
- /data/swarm/docs/specs/p0/09-command-source-model.md

结论：主架构已经收敛，尤其是 MCP 非 gameplay channel、WASM 唯一执行器、Deferred Command Model、Command Source Model、Visibility Policy、Fuel Refund、Determinism Contract 这些核心 contract 已经基本闭合。没有发现会推翻设计方向的结构性问题。

但仍有少量“文档残留/合同边界未完全统一”的项。它们不阻断进入实现，但必须在 Phase 1/2 实现前清理，否则新人会按旧字段或旧示例写代码，导致 IDL、validator、SDK、docs 分叉。

Strengths

1. MCP contract 已经闭合
- DESIGN.md §4 明确：MCP 是 AI 的“屏幕和鼠标”，不做 move/attack/build。
- P0-3 §1/§4.5 同步说明 MCP 与 Web UI 同级，只部署/查询/调试，不直接操作游戏实体。
- P0-1 §2.1 明确唯一执行器是 WasmSandboxExecutor，没有 McpPlayerExecutor。
- P0-9 Source Gate 明确 MCP_Deploy/MCP_Query gameplay = false。

2. Deferred Command Model 已形成主线
- DESIGN.md §5、§8.5、P0-4 §3、P0-8 IDL 均指向 tick(snapshot) -> Command[] / JSON 的延迟模型。
- Mutating host functions 已被禁止，查询 host functions 只读且计入 fuel。

3. 确定性核心明显增强
- DESIGN.md §8.8 固定 PRNG=ChaCha12、Hash=Blake3、禁 std::hash、禁 std::HashMap 迭代、ECS .chain()、整数/定点数。
- Tick replay contract 有 checksum 与 full replay 验证方向。

4. Source/capability/visibility 分层已经比早期设计安全得多
- P0-9 把 WASM、MCP_Deploy、MCP_Query、Admin、Replay、TestHarness、Tutorial、Deploy、Rollback、RuleMod、Simulate、DryRun 全部显式列出。
- P0-5 给出统一可见性规则，避免 Web/MCP/WASM 输出面信息不一致。

5. World Rules Engine 方向正确
- “核心引擎不可变 + Rhai 规则模组 + 声明式配置”是合理的中间层：比 WASM mod 简单，比硬编码规则可扩展。
- DESIGN.md §8 与 P0-7 已明确模组不可访问文件/网络/时钟/随机数，并有执行预算。

Concerns

A1. RawCommand 仍残留客户端自报 player_id/tick 的旧 contract

位置：
- P0-2 §2 RawCommand 示例：
  - line 63: "player_id": 42
  - line 64: "tick": 4521
  - line 76: player_id 必须匹配已认证玩家
- P0-9 §3：
  - 明确禁止客户端在 Command body 中自报 player_id；auth context 由服务端注入。

问题：
P0-9 是更安全的新 contract，但 P0-2 还把 player_id/tick 写在 RawCommand body 中。这个残留会让实现者误以为 WASM tick 输出可以/应该携带 player_id，并在 validator 中“匹配认证玩家”，而不是由 Source Gate/Auth Verify 注入。

建议修正：
- P0-2 §2 改名为 ServerCommand 或 AuthenticatedCommand，明确它是“服务端包装后的内部结构”，不是 WASM 输出 schema。
- WASM 输出 Command body 只包含 sequence/action 或仅 Command[]；player_id、tick_target、source、module_version 全部来自 P0-9 auth context。
- P0-2 line 76 改为：“player_id: 服务端注入；客户端字段若出现则忽略/拒绝，按 P0-9 处理”。

A2. Command JSON 字段命名仍有 action/type 与 cmd 小写两套残留

位置：
- P0-2 §2 使用：
  - "action": { "type": "Move", ... }
- P0-2 §3 单条命令示例使用：
  - {"type": "Move", ...}
- DESIGN.md §8.5 TypeScript 示例使用：
  - commands.push({ cmd: "spawn", ... })
  - commands.push({ cmd: "harvest", ... })
- P0-4 §3.3 禁止 host function 示例使用：
  - { "cmd": "move", ... }
- DESIGN.md §5.2 禁止 host function 示例使用：
  - { "action": "Move", ... }
- P0-8 IDL 使用 commands: Move/Harvest/Transfer...，语义更接近 type/variant。

问题：
这不是审美问题，是生成器/validator/SDK 的单一真相问题。若不统一，TS SDK、JSON Schema、P0-2 validator、P0-8 IDL 会出现四种解释：cmd 小写、type 大写、action wrapper、IDL enum variant。

建议修正：
- 以 P0-8 IDL 为唯一来源，冻结一种 wire format。
- 推荐 wire format：
  {
    "sequence": 3,
    "type": "Move",
    "params": { "object_id": 1001, "direction": "TopRight" }
  }
  或保留 P0-2 当前 flat format，但必须全仓统一。
- 删除 DESIGN.md/P0-4 中所有 `{ "cmd": "..." }` 旧示例。

A3. 动态资源模型与 Energy 硬编码仍未完全清理

位置：
- DESIGN.md §8.4 明确核心引擎不硬编码 Energy，只操作 HashMap<ResourceName, Amount>。
- P0-7 §2/§3 同样定义 resource_types 与 actions.costs。
- 但 P0-2 仍有硬编码：
  - line 127: target.source.energy > 0
  - line 157: drone.carry[Energy] >= build_cost(structure)
  - line 175: drone.carry[Energy] >= repair_cost
  - line 223: body_cost(body) ≤ spawn.energy
  - line 304: SourceEmpty 语义也偏单资源。
- DESIGN.md §3.1 Structure 仍含 energy/energy_capacity 字段，而 Resource 已是 HashMap。

问题：
P0-2 是 validator spec，恰好是实现者最会照抄的文档。这里残留 Energy 会把动态资源模型打回 Screeps-style 单资源经济。

建议修正：
- P0-2 所有 Energy/energy 字段替换为 ResourceCost/ResourceName：
  - Source: `target.source.amounts[resource] > 0` 或 `produces` 中有 resource。
  - Build/Repair/Spawn: `registry.cost(action, detail)` 与 actor/local storage/carry 对账。
  - Structure: `resources: HashMap<ResourceName, Amount>` + capacity map，而不是 energy/energy_capacity。
- 保留 Energy 只能作为默认 world.toml 的示例资源名，不能作为 validator 字段。

A4. 定点数/禁 f64 contract 与配置示例仍矛盾

位置：
- DESIGN.md §8.8 line 1204：游戏引擎数值用整数 + 定点数，Rhai 模组脚本禁用浮点，所有模组参数必须 u32/i64/fixed。
- DESIGN.md §8.7 i18n 示例 line 1080：`type = "f64"`，default/min/max 也使用 0.1/0.0/10.0。
- P0-7 配置 schema 使用：
  - `decay_rate = 0.0`
  - `decay_rate = 0.001`
  - `transfer_to_global_cost = { Energy = 0.01 }`
  - `damage_multiplier = 1.0`
- DESIGN.md §8.3 也有 `source_regeneration = 1.0`、`build_cost = 1.0`、`drone_decay = 1.0`、`memory_spawn_cost = { Energy = 0.5 }` 等。

问题：
确定性 contract 已经冻结为 fixed<u32,N>，但配置示例仍用浮点字面量。实现者可能用 TOML float 解析，破坏 replay determinism。

建议修正：
- 所有配置示例统一用 fixed integer 表示：例如 `damage_multiplier = 10000`，`decay_rate = 10` 表示 0.001，`transfer_to_global_cost = { Energy = 100 }` 表示 1%。
- 文档中明确 scale：例如 `fixed<u32,4>`，scale=10000。
- DESIGN.md line 1080 的 `type = "f64"` 必须改为 `fixed<u32,4>` 或类似定点类型。

A5. Tick 持久化阶段描述有旧版残影

位置：
- DESIGN.md §3.2：EXECUTE 阶段 line 225 写 FDB 原子提交，BROADCAST 阶段只 Dragonfly/NATS。
- P0-1 状态机图 line 43 把 “FDB 原子提交” 放在 BROADCAST。
- P0-1 §3.4/§4.2 又修正为 EXECUTE commit，BROADCAST failure never rolls back committed tick。

问题：
正文已经收敛为“FDB commit in EXECUTE”，但状态机图仍会误导读者，把持久化当成广播阶段的一部分。

建议修正：
- P0-1 line 43 状态机图把 “FDB 原子提交” 移到 EXECUTE 框中。
- BROADCAST 框只保留 read committed result、Dragonfly update、NATS publish。

A6. P0-2 Tick 输出 JSON Schema 的 `additionalProperties: false` 放置错误/表述不严

位置：
- P0-2 §1.1 schema 顶层是 array，但 bullet 写 “additionalProperties: false — 拒绝未知顶层字段”。

问题：
array 顶层没有 properties/additionalProperties。真正需要限制的是 Command object 或 Action params。当前写法容易让 JSON Schema 实现无法表达预期。

建议修正：
- 在 `definitions.Command` 和每个 action variant schema 内设置 `additionalProperties: false`。
- 顶层 array 只限制 maxItems。
- 如果采用 discriminated union，需要明确 `oneOf` + `type` discriminator。

A7. RuleMod “不能绕过 Command Validation Pipeline” 与 actions 直接修改世界的边界需要更精确

位置：
- P0-7 line 15：模组通过 actions 请求引擎操作——不能绕过 Command Validation Pipeline。
- DESIGN.md §8.7 Rhai API：actions.deduct_resource/award_resource/modify_entity/emit_event。
- P0-9 §2.3：RuleMod 允许写入世界：仅 deduct/award/emit_event；但 DESIGN/P0-7 又列出 modify_entity。

问题：
这里不是大错，但边界语义不精确：RuleMod 显然不是普通玩家 gameplay command，它需要改世界；如果说“不绕过 Command Validation Pipeline”，那 modify_entity 应如何通过 validator？如果它是规则系统内部 actions.apply 校验，则不能称为同一 Command Validation Pipeline。

建议修正：
- 把 RuleMod 路径明确为 “RuleActions Validation Pipeline”，不是玩家 Command Validation Pipeline。
- P0-9 与 DESIGN/P0-7 对齐：如果允许 `modify_entity`，需限定字段白名单与 capability；如果不允许，则从 DESIGN/P0-7 删除。
- TickTrace 记录 RuleMod action 及校验结果。

A8. manual_control 已删除，但设计图/默认表仍残留

位置：
- DESIGN.md §8.1 图中仍有 `manual_control` / `ManualControlSystem`。
- DESIGN.md §8.2 写“手动控制不开放，manual_control 已删除”。
- DESIGN.md §8.6 默认规则表仍有 `manual_control | false | false`。

问题：
这是典型旧 contract 残留。虽然文字说已删除，但图和表会让实现者以为仍有一个 manual_control config key。

建议修正：
- 从 §8.1 图和 §8.6 表删除 manual_control。
- Tutorial 例外应放入 P0-9 Tutorial source，而不是 world config 的 manual_control。

A9. 文档状态/编号有少量不一致，影响“最终冻结”的可读性

位置：
- DESIGN.md §9 写 Phase 0 完成，但 P0-1/P0-6 状态仍为 “Phase 2 阻断项”，P0-7 为 “Phase 1 设计基础”。这未必错，但与“Phase 0 Architecture Freeze”表达不统一。
- P0-1 §6.3 下小标题又写 “### 6.1 记录”。
- DESIGN.md 有两个 “## 10”：World/Arena 与贡献指南。
- P0-9 从 “## 5 Replay 与审计” 跳到 “## 7 World/Arena 差异”。

问题：
不影响架构正确性，但 R5 最终检查阶段应清理，避免后续引用混乱。

建议修正：
- 每个 P0 spec 顶部统一写：`状态: Frozen for Phase 0 | 实现阶段: Phase N | 是否阻断: yes/no`。
- 修复重复/跳号标题。

Missing

M1. 缺少一个 “canonical wire format” 小节

当前 P0-8 是 IDL 真相源，但没有明确 JSON wire encoding 细节。建议在 P0-8 增加：
- Command JSON encoding
- Server-injected auth wrapper encoding
- Tick output schema 完整 definitions
- 命名规范：PascalCase variant vs snake_case JSON key vs SDK method name

这是 A1/A2 的根治点。

M2. 缺少 ResourceCost 定点数编码规范

动态资源与定点数都已经提出，但还缺少统一规则：
- ResourceAmount 是否永远整数？
- 百分比/倍率如何编码？
- `ResourceCost` 是否支持 fixed cost、percentage cost、per-byte cost？
- TOML 显示层是否允许人类写 0.01，然后编译成 fixed integer，还是源文件也禁止 float？

为了 replay determinism，建议源配置也禁止 float。

M3. RuleMod capability 白名单需要冻结

RuleMod 是后续最容易长成“上帝脚本”的入口。建议 P0-7/P0-9 增加：
- RuleActions enum
- 每个 action 的 allowed target/component field
- 是否允许 modify_entity；如果允许，哪些 component/field 可改
- 与 replay/checksum 的记录格式

M4. TickTrace write fail 与 replay guarantee 需要一句优先级裁决

P0-1 failure matrix 允许 TickTrace 写失败但 gameplay 继续，标记 tick 不可回放；DESIGN §8.8 又说每 tick 产出 checksum，CI full replay 验证。二者可以共存，但需要明确：
- TickTrace 是审计/解释数据，state_checksum 是最低必需 replay 数据？
- 如果 TickTrace 不完整，是否仍可从 `/tick/{N}/commands` + state checksum replay？
- 哪些写入失败会使 tick abandon，哪些只是 audit degraded？

Phase Ordering

1. Phase 0 文档清理（进入实现前，必须完成）
- 修 A1/A2：冻结 P0-8 canonical wire format，并同步 P0-2/P0-4/DESIGN 示例。
- 修 A3：清理 P0-2 validator 中 Energy/energy 硬编码。
- 修 A4：所有配置示例改为 fixed integer，无 TOML float。
- 修 A5/A8/A9：状态机图、manual_control 残留、标题/状态统一。

2. Phase 1 实现前置
- 先实现 IDL generator/schema generator，禁止手写 Command/host/MCP schema。
- 先实现 ResourceRegistry 与 fixed-value parser，再写 build/repair/spawn validator。
- 先实现 Source Gate/Auth wrapper，再接 WASM tick 输出。

3. Phase 1 MVP
- 单人垂直切片：Bevy ECS + WASM sandbox + tick(snapshot)->Command[] + validator + deterministic checksum。
- MCP 只做 deploy/query/docs，不接 gameplay action。

4. Phase 2 多人/MCP 完整
- Tick scheduler 多玩家并行 collect。
- Source Gate 全矩阵。
- MCP debug/replay/profile 工具。
- Refund/throttle 监控。

5. Phase 3+ 持久化/规则模组
- FDB/Dragonfly/ClickHouse 接入。
- RuleActions Validation Pipeline。
- replay + TickTrace 完整审计。

最终裁决

CONDITIONAL_APPROVE。

条件项：
1. 清理 P0-2 RawCommand 中客户端自报 player_id/tick 的残留，并与 P0-9 auth context 对齐。
2. 统一 Command JSON wire format，删除 cmd/action/type 混用。
3. 清理 P0-2/DESIGN 中 Energy/energy 硬编码，全部走 ResourceRegistry/ResourceCost。
4. 清理所有 float 配置示例，统一 fixed integer 表示。
5. 修正 P0-1 状态机图中 FDB commit 所在阶段。
6. 删除 manual_control 残留配置/图示。
7. 明确 RuleMod actions 与 Command Validation Pipeline 的边界。

这些条件是文档一致性与实现入口一致性问题，不是架构方向问题。完成后可以升级为 APPROVE。