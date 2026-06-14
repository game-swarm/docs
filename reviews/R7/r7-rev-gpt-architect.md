# R7 — rev-gpt-architect 架构评审

Reviewer: rev-gpt-architect (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `tech-choices.md`, `ROADMAP.md`, `/data/swarm/docs/specs/p0/*.md`

## Verdict

APPROVE_WITH_RESERVATIONS。

R7 版本已经从早期“AI 直接操作游戏”的危险形态，收敛到更正确的核心架构：世界只接受 WASM tick 输出；MCP 与 Web UI 同级，只做观察、部署、调试；Command Source、Visibility、IDL、Tick Protocol、Sandbox、MVP feedback loop 都有 P0 级契约。这是一个可实现、方向正确、抽象层次基本健康的架构。

但我不建议直接进入大规模 Phase 1 实现。当前仍有若干“文档看起来完整，但实现时会炸”的接口和阶段问题：P0 文档之间存在命名/时序/职责不一致；Rhai RuleMod 的权限边界过宽；per-tick fork + Wasmtime + 500 玩家 + 3s tick 的容量假设没有被 spike 验证；Phase 1 仍塞入 FDB/NATS/MCP 等会稀释单人垂直切片的组件。建议先做 1-2 周 Architecture Hardening + Spike，再进入 Phase 1。

## 问题（severity）

### A1 — HIGH — Tick 原子提交时序在文档间不一致，容易实现出“双提交/错位广播”

位置：DESIGN.md §3.2、P0-1 §1/§3.4/§4.2

DESIGN.md 的 tick 生命周期把 FDB 原子提交放在 EXECUTE 阶段；P0-1 状态机图则把 “FDB 原子提交”画在 BROADCAST 阶段；P0-1 §3.4 又说所有世界状态变更在一个 FDB transaction 内完成，commit 成功后 tick_counter 才推进。

这不是纯文字问题。实现者可能做出两种互相冲突的结构：
- EXECUTE 已提交一次，BROADCAST 再写缓存/trace 时又隐含提交；
- BROADCAST 前世界状态在内存中已改变，但 FDB commit 失败时广播/缓存已经基于未提交状态生成。

建议：冻结一个唯一顺序：Collect → Execute in-memory → Build TickResult → FDB atomic commit state+commands+rejections+metrics+trace → only after commit update Dragonfly/NATS/WS → tick_counter++。BROADCAST 只能读取 committed TickResult，不允许再修改权威状态。

### A2 — HIGH — `RawCommand.player_id` 与 “client 不可自报 player_id” 的契约冲突仍会误导实现者

位置：P0-2 §2、P0-9 §3.2/§3.3/§4

P0-2 的 RawCommand 表仍把 `player_id` 列为字段并写“必须匹配已认证玩家”；P0-9 又明确“客户端不可自报 player_id，如果提供则服务端覆盖”。这两个说法同时存在，会诱导 SDK/IDL/codegen 把 player_id 暴露给玩家代码或客户端。

建议将结构拆成：
- `PlayerCommandBody`: WASM/SDK 可构造，只含 sequence/action/args，不含 player_id/source/auth_context；
- `ServerStampedRawCommand`: 服务端注入 player_id/source/auth_context/tick/module_hash/signature 后进入 Source Gate；
- TickTrace 记录 ServerStampedRawCommand。

否则身份伪造不会来自“校验忘了做”，而是来自类型层把不该暴露的字段做成了公共 API。

### A3 — HIGH — RuleMod/Rhai 权限边界太宽，`modify_entity` 是绕过 Command Validation Pipeline 的后门形状

位置：DESIGN.md §8.7、P0-7 §1/§8、P0-9 §2.2/§2.3

P0-7 说模组不能绕过 Command Validation Pipeline；P0-9 将 RuleMod 限定为“仅经济 + 事件”；但 DESIGN.md 的 Rhai API 暴露了 `actions.modify_entity(entity_id, property, value)`，并且 `actions.apply(world)` 只笼统写“经校验后写入”。

这像很多插件系统失败案例：一开始说“可信服主”，后来社区模组市场、依赖、版本漂移、Arena allowlist 都出现后，通用写实体函数会变成规则、经济、战斗、可见性、确定性的统一后门。

建议：Phase 0/1 禁止通用 `modify_entity`。RuleActions 必须是强类型 capability：`deduct_resource`、`award_resource`、`emit_event`、可能还有 `set_rule_flag` 等；每个 action 有 schema、budget、determinism test、replay encoding。需要修改实体时，为具体规则新增显式 action，而不是开放 property string。

### A4 — HIGH — per-tick fork 生命周期与 3s / 500 玩家目标缺少容量证明

位置：P0-4 §1、ROADMAP Phase 2/7、P0-3 §5.2

P0-4 规定 sandbox worker “每 tick 新 fork，执行一个玩家，返回指令，然后 kill”；P0-3/P0-4 又设想每引擎实例 500 AI 玩家、3s tick、多 Wasmtime 实例、cgroup/seccomp、Unix socket/gRPC。这在安全上漂亮，但在性能上风险很高。

已知风险：
- fork/instantiate/IPC/cgroup bookkeeping 可能比 WASM 真实执行更贵；
- module cache “编译一次，多 tick 复用”与“每 tick fork kill”之间需要明确 cache 所在进程和预实例化策略；
- 500 玩家 x 2500ms collect timeout 不是问题，问题是同时调度/隔离开销、内存峰值、wasmtime Engine/Store 生命周期。

建议在 Phase 1 前加入强制 spike：100/500 synthetic modules，测 fork+instantiate+fuel+JSON snapshot 的 p50/p99、RSS、context switches。若失败，提前改成 warm worker pool + per-tick Store reset + hard kill fallback，而不是实现到 Phase 2 才发现 tick 打不满。

### A5 — MEDIUM — Phase 1 “单人垂直切片”仍引入过多分布式基础设施

位置：ROADMAP Phase 1 交付物 1.8/1.9，tech-choices.md §4/§5

Phase 1 目标是“一个玩家一个房间，采集→建造→扩张，可确定回放”。但交付物包含 MCP Server 脚手架、Docker Compose: engine + FDB + NATS。对单人 MVP 来说，FDB/NATS/MCP 都不是验证核心 gameplay loop 的必要条件。

这会造成经典失败模式：团队在第一个月调 FDB/NATS/auth/compose，而不是证明 WASM API、Command Validation、Replay Determinism 和 starter bot 真的好玩。

建议 Phase 1A 使用 in-memory/SQLite trace + local CLI deploy + no gateway/no NATS；Phase 1B 再接 FDB/NATS/MCP skeleton。FDB 是最终正确选择，但不应成为首个可玩切片的入口税。

### A6 — MEDIUM — IDL 与规范中的 command 命名不一致，会破坏“单一真相来源”承诺

位置：DESIGN.md §5/§8.5、P0-2、P0-8、P0-4 §3.3

文档中同时出现：
- `{ "action": "Move" }`
- `{ "cmd": "move" }`
- P0-2 逐指令标题 `Move`, `MoveTo`, `Harvest`
- P0-4 禁止 host function 示例说改为 `{ "cmd": "move" }`
- DESIGN.md §5 又说 `{ "action": "Move" }`

如果 P0-8 真的是单一真相来源，这些示例必须全部由 IDL 生成或至少与 IDL 固定 casing 对齐。否则 SDK、MCP schema、validator、文档四处 drift，后期会出现“示例可运行但 validator 拒绝”的新手灾难。

建议：选定 canonical wire format，例如 `{ "action": "move", "object_id": ... }` 或 enum PascalCase，并在 P0-8 中声明 casing 规则；所有文档示例引用生成片段，不手写。

### A7 — MEDIUM — `swarm_simulate` / dry-run 是信息侧信道与算力放大器，限制仍散落

位置：P0-3 §4.4/§5.1、P0-6、P0-9 §2.2/§6

P0-9 已经把 Simulate 定义为 snapshot-bound、0.5x MAX_FUEL、5/tick；P0-3 中仍有“按需”或不同限流描述。更重要的是，simulate 对隐藏状态、资源争用、PRNG、敌方未来行为的处理需要更硬的语义。

建议明确：simulate 只能基于调用者已可见 snapshot 的副本运行；不可见状态统一返回 `UnknownDueToVisibility` / conservative result；不暴露真实 tick shuffle order、seed、敌方未来 command；max ticks、max commands、wall time、per-IP/per-player budget 写入 P0-3 和 P0-9 同一张表。

### A8 — MEDIUM — WorldConfig / world.toml schema 在 DESIGN 与 P0-7 中字段漂移

位置：DESIGN.md §8.3/§8.6，P0-7 §2/§6/§7

例子：DESIGN 使用 `source_regeneration`、`build_cost`、`drone_decay`、`pvp`、`damage`；P0-7 使用 `source_regeneration_rate`、`build_cost_multiplier`、`drone_decay_rate`、`pvp_enabled`、`damage_multiplier`。可见性字段、global storage 字段也不是完全同一份 schema。

这类漂移会直接伤害“配置即规则”的可理解性。新人不知道哪份文档是准的，代码生成也无法落地。

建议把 `world.schema.toml/jsonschema` 作为 source of truth，DESIGN 只解释理念，P0-7 固定 schema，ROADMAP 验收引用 schema version。

### A9 — LOW — Bevy `.chain()` 作为确定性保证的表述过强

位置：tech-choices.md §1、DESIGN.md §3.3、ROADMAP Phase 7

`.chain()` 只能保证 system 顺序，不自动保证所有内部迭代顺序、HashMap 遍历、并行 query、浮点、Rhai map iteration、serialization order 都确定。当前文档提到了固定 PRNG，但 determinism contract 还需要更细。

建议补一份 Determinism Checklist：禁止 std HashMap 用于 replay-critical iteration 或统一排序；使用 fixed-point；serialization canonicalization；Bevy query ordering 显式排序；Rhai map iteration stable；跨平台 replay CI。

### A10 — LOW — P0 状态标签与 ROADMAP 阶段依赖不完全一致

位置：P0-1/P0-6 状态、ROADMAP Phase 1/2

P0-1 写“Phase 2 阻断项”，但 ROADMAP Phase 1 依赖 P0-1 并要求 Tick 调度器；P0-6 写“Phase 2 阻断项”，但 Phase 1 starter bot 和教程反馈已经引用它。状态标签会让执行者误判哪些规范必须先完成。

建议用两维状态替代单标签：`Design status: Frozen/Draft` + `Implementation gate: Phase 1/2/3`，并列出各 Phase 必须满足的 subsection。

## 亮点

1. MCP 定位修正正确：MCP 是 AI 的观察/部署/调试界面，不是 gameplay action 通道。所有玩家同走 WASM，是公平性与安全性的核心胜利。

2. Deferred Command Model 是正确抽象：WASM 只返回 Command[]，引擎统一校验与执行。它天然支持回放、反作弊、冲突解决、审计和 SDK 多语言。

3. P0-5 Unified Visibility Policy 很有价值：把 snapshot、MCP、WebSocket、REST、Replay、Spectator 全部纳入同一个 `is_visible_to` 不变量，避免常见的信息泄漏裂缝。

4. P0-9 Command Source Model 抓住了权限本质：source、auth_context、capability、scope、rate_limit、visibility、budget 的矩阵化建模，比“到处 if admin/player”健康很多。

5. P0-8 IDL 方向正确：host functions / Command / Validator / SDK / MCP schema / docs / tests 从同一 IDL 生成，是控制 API drift 的必要机制。

6. ROADMAP 的纵向切片意识强：每个阶段有目标、交付物、锚定规范和验收标准，比单纯功能清单更可执行。

7. 安全基线明显比常见 UGC/WASM 游戏强：Wasmtime pinned version、fuel、epoch interruption、WASI 禁用、seccomp、cgroup、恶意样本库、CVE SLA 都已进入设计视野。

8. MVP feedback loop 明确覆盖 Learn / Decide / Act / Understand，说明设计没有只停留在引擎层，也考虑了“为什么失败、如何迭代”的玩家体验。

## Missing / 建议补齐

- `game_api.idl` 的真实文件与生成物目录约定：现在 P0-8 是规范，不是可执行 source of truth。
- `world.schema` 的真实 source of truth：统一 DESIGN 与 P0-7 的 world.toml 字段。
- Sandbox performance spike 报告：per-tick fork 与 worker pool 的实测对比。
- RuleMod capability registry：列出每个 action 的输入 schema、权限、预算、replay encoding、determinism tests。
- Determinism checklist：覆盖 HashMap/order/fixed-point/Rhai/serialization/Bevy query ordering。
- Simulate/dry-run security contract：隐藏状态、PRNG、敌方行为、CPU budget 的精确定义。
- Tick commit protocol：明确 TickResult、FDB commit、cache update、NATS publish、tick_counter 推进的单一顺序。

## Phase Ordering 建议

1. Phase 0.5（1-2 周，进入实现前）
   - 修 A1/A2/A3/A6/A8 文档契约漂移。
   - 写出 `game_api.idl` 和 `world.schema` 的最小真实文件。
   - 做 sandbox fork/instantiate/fuel spike。

2. Phase 1A（最小可玩单人切片）
   - Bevy ECS + WASM sandbox + Command Validation + replay trace + TS starter bot。
   - 允许 in-memory/SQLite trace；不强制 FDB/NATS/Gateway/MCP。

3. Phase 1B（接入架构骨架）
   - FDB atomic tick commit。
   - 最小 MCP: get_snapshot/deploy/get_world_rules，但只服务单人世界。
   - Docker compose 再加入 FDB/NATS。

4. Phase 2
   - 多玩家 collect、source gate、visibility 全输出面、WebSocket/NATS、MCP auth/rate limit。
   - 在进入多人前必须完成 A7 simulate/dry-run 合同。

5. Phase 3+
   - Rhai/RuleMod 在 capability registry 完成后再接入；不要带 `modify_entity` 进入实现。

## 最终建议

可以继续推进，但先做“契约收敛 + 性能 spike”，不要直接按当前 ROADMAP Phase 1 全量开工。架构主干是正确的；剩余风险主要是边界定义与阶段切片，而不是方向性错误。
