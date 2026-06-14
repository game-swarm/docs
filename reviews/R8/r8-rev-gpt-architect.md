# R8 终审 — rev-gpt-architect

Reviewer: GPT-5.5 Architect
Scope: `DESIGN.md` + `tech-choices.md` + `ROADMAP.md` + `specs/p0/`
Date: 2026-06-14

## Verdict

CONDITIONAL_APPROVE

设计已经达到可以冻结 Phase 0、进入 Phase 1 实现准备的程度。核心架构方向是正确的：

- AI 与人类统一走 WASM，不存在 MCP gameplay shortcut。
- Deferred Command Model 把 mutating 操作集中到单一校验/执行管线。
- P0-1/P0-2/P0-4/P0-8/P0-9 形成了 tick、sandbox、command、IDL、source gate 的闭环。
- P0-5 把可见性统一为一个中心策略，避免 snapshot/WS/MCP/replay 各自泄露。
- ROADMAP 的阶段拆分基本符合「先确定性单人垂直切片，再多人/MCP，再持久化/模组，再产品体验」的工程顺序。

条件：下列 A1-A3 必须在 Phase 1 开工前以文档 patch 方式消除；A4-A7 可作为 Phase 1 implementation checklist 的约束项，不阻断架构冻结。

## Strengths

1. 已避免最大架构坑：MCP 没有被设计成游戏动作通道。AI 玩家必须编写 WASM，与人类玩家同源、同沙箱、同 fuel metering。这一点决定了公平性和反作弊边界是可解释的。

2. Deferred Command Model 是正确抽象。WASM 只产出 JSON commands，engine 在统一 pipeline 中校验并应用，避免 host function 直接改世界导致 TOCTOU、权限绕过和 replay 不一致。

3. Tick lifecycle 已具备可实现性：Collect 并行、Execute 串行、Broadcast 不回滚 committed tick；失败语义、tick abandon、degraded mode 都有明确描述。

4. Determinism Contract 覆盖到了常见炸点：PRNG、hash、ECS order、数值类型、HashMap iteration、Rhai float 禁用、state_checksum/replay 验证。比多数 MMO/RTS 设计文档更接近可验证系统。

5. P0-8 IDL 作为 single source of truth 是必要且正确的。Command enum、validator、SDK、MCP schema、docs、property tests 全部从 IDL 派生，可以显著降低 API drift。

6. P0-5 对输出面统一过滤是正确方向。尤其是明确「debug/replay 不是例外」以及 spectator 与 player snapshot 分层，这能防止最常见的信息泄漏。

7. ROADMAP 把 Web/UI/Arena/生产化推迟，先做 engine + sandbox + replay vertical slice，符合高风险系统的落地顺序。

## Concerns

### A1 — HIGH — Phase 1/Phase 3 的 FoundationDB 边界不一致

现状：

- P0-1 §3.4 把整个 EXECUTE 包在 FoundationDB transaction 中，tick commit 失败会 abandon。
- P0-1 §6.3 要求每 tick 写 `/tick/{N}/state|commands|rejections|metrics`。
- ROADMAP Phase 1 要求 TickTrace + replay 验证，并在 Docker Compose 中启动 FDB。
- ROADMAP Phase 3 又把「FoundationDB 持久化」列为 3.1，像是 Phase 1/2 之前没有 FDB 权威持久化。

风险：实现团队会产生两种解释：

1. Phase 1 就接 FDB transaction；那 Phase 3 的 FDB 持久化重复。
2. Phase 1 用内存状态，Phase 3 才接 FDB；那 P0-1 的 tick atomicity、abandon、TickTrace replay 在 Phase 1 无法按合同实现。

建议：把持久化分层明确写入 ROADMAP：

- Phase 1: 单进程 authoritative store + TickTrace abstraction；可用 in-memory 或 local append log，但必须实现 `TickStore` interface 与 replay checksum。
- Phase 2: 多玩家仍可同一 store abstraction。
- Phase 3: `TickStore` backend 切到 FoundationDB，启用真实 distributed transaction、Dragonfly、ClickHouse。

或者反过来：明确 Phase 1 就必须接 FDB，Phase 3 只是 multi-room/sharding/operational hardening。两者必须选一个，否则实现合同会漂移。

### A2 — HIGH — Rhai RuleMod 是否经过 Command Validation Pipeline 存在冲突

现状：

- P0-7 §1/§8 说模组通过 actions 请求引擎操作，不能绕过 Command Validation Pipeline，绝不可绕过 Command 校验管线。
- DESIGN §8.7 Rhai API 说 `actions.deduct_resource/award_resource/modify_entity/emit_event` 是「世界修改（通过 actions，不进命令管线）」。
- P0-9 把 `RuleMod` source 标为「仅经济 + 事件」，允许 `deduct/award/emit_event`。

风险：这里是权限边界，不是文字问题。如果 RuleMod 的 `modify_entity` 可以不走 command validator，它等价于 privileged world mutation channel；如果它必须走 validator，则很多 tick_start/tick_end 规则无法表达。

建议：拆成两层并冻结命名：

- `RuleAction` pipeline：专供 Rhai，独立于 player `Command` pipeline，但有 schema、capability、budget、audit、deterministic ordering、replay record。
- Player `CommandValidationPipeline`：只处理玩家 gameplay commands。

同时限制 Rhai API：Phase 3 只允许 `deduct_resource`、`award_resource`、`emit_event`；`modify_entity` 推迟或改成白名单 patch，例如只允许修改规则拥有的 component，不能改 position/owner/hits 等核心物理状态。

### A3 — MEDIUM — P0 文档状态与 ROADMAP 阻断关系不一致

现状：

- P0-1 状态是「Phase 2 阻断项」，但 ROADMAP Phase 1 已依赖 P0-1 §3/§6.3 并实现 tick scheduler/replay。
- P0-2 状态是 Phase 2 实现，但 Phase 1 交付物 1.3/1.4 已要求基础 commands 走 P0-2 pipeline。
- P0-4 状态是 Phase 2 实现，但 Phase 1 交付物 1.2 已要求 WASM sandbox。
- P0-6 写「Phase 2 阻断项」，但 ROADMAP 把人类教程房间列为 Phase 1 P0。

风险：新成员会误读「Phase 2 阻断项」为 Phase 1 不需要遵守，导致 Phase 1 做出临时 API/sandbox/tick 行为，Phase 2 再返工。

建议：统一状态字段，改成：

- `Architecture status`: Frozen / Draft / Open
- `First implementation phase`: Phase 1 / Phase 2 / Phase 3
- `Blocks`: Phase N gate

例如 P0-4 应是 `Frozen; first implementation: Phase 1 subset; full gate: Phase 2`。这比单个「状态」字段清楚。

### A4 — MEDIUM — IDL 与手写规范存在细节 drift，需在 Phase 1 前收敛

观察到的例子：

- P0-2 `RejectionResponse.detail` 示例是 string，但文字说 `detail` 是机器可读 JSON。
- P0-2 失败码出现 `InsufficientResources`，P0-8 IDL 是 `InsufficientResource { resource, required, available }`。
- P0-8 `host_functions.tick.returns: i32` 注释写 `0 = success, pointer to command JSON in WASM memory`，返回语义不清：0 到底是 success code 还是 pointer？长度如何返回？错误码如何表达？
- DESIGN 示例 command 使用 `{ cmd: "harvest" }`，P0-2/P0-8 使用 `{ action: { type: "Harvest" } }` 或 typed Command enum。

风险：如果不以 IDL 为权威，SDK、validator、MCP schema 会迅速分叉。

建议：Phase 1 开工前建立 `game_api.idl` 真文件，并用 generated docs 替换或校验 P0-2/P0-8 示例。所有示例统一使用 generated JSON shape。

### A5 — MEDIUM — Sandbox 生命周期「per-tick fork」与 Wasmtime compile/cache 成本需要 spike

设计选择是合理的，但风险高：每玩家每 tick fork worker、实例化 module、写入 snapshot、执行、kill。500 玩家、3s tick 下，fork/instantiate/IPC/snapshot serialization 可能比 fuel execution 更贵。

当前文档说 module cache 按 `(module_hash, wasmtime_version)` 缓存，但又说每 tick fork → execute → kill。这里需要明确缓存在哪一层：

- engine process 持有 compiled module cache？
- sandbox supervisor 持有 compiled artifact，fork child 只 instantiate？
- compiled module 是否可安全跨进程 mmap/reuse？

建议：Phase 1 加一个 mandatory spike：100/500 fake players、固定 snapshot size、空 tick + path_find-heavy tick，测 fork/instantiate/IPC 成本。若 p99 超过预算，需切换到 long-lived sandbox worker + per-tick store reset/epoch hard kill 模型。

### A6 — LOW — Blake3「代码签名」表述容易误导

tech-choices §8 把 Blake3 MAC 归入代码签名选择，但 P0-3/P0-9 的部署安全模型实际是 Ed25519 证书 + 签名/验签 + module_hash = Blake3(WASM bytes)。

风险：实现者可能把 keyed Blake3 MAC 当成客户端可证明身份的签名使用。MAC 是对称认证，不等价于第三方可验证签名；适合 server-side token/MAC，不适合玩家部署身份签名。

建议：改写为：

- Blake3: content hash / deterministic PRNG / optional server-side keyed MAC。
- Ed25519: all client-authenticated signatures and certificates。

### A7 — LOW — Bevy 确定性需要版本/feature 级约束

文档已要求 `.chain()`、禁 std::HashMap、定点数，但 Bevy 本身仍可能通过 scheduler、time/resource、parallel features、entity allocation order 引入非预期差异。

建议在 Phase 1 checklist 增加：

- pin Bevy minor version；
- 禁用/封装所有 wall-clock `Time` usage；
- entity spawn order 必须来自 sorted command/event queue；
- replay test 覆盖 different process / fresh run，而不是同进程重复执行。

## Missing

1. 明确的 `TickStore`/persistence abstraction：需要解决 A1。

2. 明确的 `RuleAction` schema：需要解决 A2。尤其是 RuleMod action ordering、audit record、replay input、capability whitelist。

3. `game_api.idl` 的真实文件位置与 CI gate：文档说明了原则，但 ROADMAP 应把「IDL file + codegen + generated examples」列为 Phase 1.0 或 1.3 的前置。

4. Sandbox performance spike：per-tick fork 是关键架构假设，必须用数据验证。

5. Snapshot serialization contract：P0-4/P0-5/P0-8 都依赖 snapshot，但 snapshot schema 没有像 command IDL 一样冻结。建议纳入 IDL 或单独 `snapshot.idl`。

6. Gateway/Auth 与 Engine 的 trust boundary：P0-3 描述 nginx/gateway 携带校验通过证书到 MCP Server，但 engine 如何验证 gateway-injected identity、如何防 internal spoofing，还需要一页边界说明。Phase 2 前补齐即可。

## Phase Ordering

建议调整为以下 gate，而不是大改路线图：

### Phase 1 前置修正文档

- Fix A1: 确定 Phase 1 是否真实使用 FDB；若否，定义 `TickStore` abstraction。
- Fix A2: 定义 RuleMod `RuleAction` pipeline，不再混用「Command Validation Pipeline」。
- Fix A3/A4: 统一 P0 状态字段与 IDL/generated JSON shape。

### Phase 1 — 单人 deterministic vertical slice

必须交付：

- Bevy ECS minimal world。
- WASM sandbox minimal execution。
- IDL-generated Move/Harvest/Build/Spawn/Transfer。
- TickStore + TickTrace + state_checksum。
- Replay test fresh-process deterministic。
- Starter bot 跑 1000 tick。

可暂缓：真实 OAuth、完整 MCP、安全证书、多玩家、公平 shuffle 的全部边界。

### Phase 2 — 多人 + MCP + source/visibility hardening

必须交付：

- seeded shuffle + conflict/refund。
- Source Gate 12 sources。
- MCP deploy/query/debug 完整工具。
- OAuth2/Ed25519/signature verification。
- Unified visibility across snapshot/MCP/WS/REST/replay。

### Phase 3 — Persistence + Rhai + global storage

必须交付：

- FDB production backend if Phase 1 used abstraction。
- Dragonfly/ClickHouse。
- Rhai RuleAction pipeline。
- global storage transfer/tax/pending transfer semantics。
- multi-room movement and visibility.

## Final Call

CONDITIONAL_APPROVE。

这不是「还不能做」的设计；相反，它已经足够清晰，值得进入实现。但必须先修掉 A1/A2/A3 这三个会导致团队实现方向分叉的问题。修完后，我会给 APPROVE。
