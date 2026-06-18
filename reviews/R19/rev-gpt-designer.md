# R19 游戏设计闭合验证（GPT）

## Verdict

REQUEST_MAJOR_CHANGES

原因：R19 已显著补强 API Registry、deploy/persistence、soft_launch、storage tax、worker pool 等机器可读合同；但从“AI 玩家仅靠 MCP/API 文档能否稳定学会并调试游戏”的游戏设计视角看，仍存在多处闭合失败：API Registry 与 interface/08-api-idl 的重复定义仍漂移，MCP 工具命名空间仍不一致，Recycle refund 未按用户裁决改为 lifespan 10–50%，以及 f64→定点裁决仍被 special_param 浮点示例破坏。GAP 数量超过 2，且 B1/B2/B3 属于会直接影响 AI onboarding 的 consensus blocker。

## 逐项判定表

| ID | 状态 | 证据 |
|---|---|---|
| B1: YAML vs Markdown 双写不一致 | GAP | `specs/reference/api-registry.md:3-5,11` 声明 registry 由 `game_api.idl.yaml` 生成且为单一权威；但 `design/interface.md:9,21-67,69-79` 仍手写一套 MCP 工具/Capability Profile，且包含 registry 未列出的旧工具名；`specs/gameplay/08-api-idl.md:65-111` 也手写 RejectionReason 列表并包含非 canonical 旧变体。 |
| B2: RejectionReason 未闭合 | GAP | 正向证据：`api-registry.md:69-89,100-155,487-507` 已定义 35 canonical code、`debug_detail`、`detail_level` 与 SwarmError envelope。反向证据：`design/interface.md:164-187` 示例仍使用 `InsufficientResources` 复数与旧 `swarm_error/details/retry_allowed` 结构；`08-api-idl.md:65-111` 仍列出 `NotMovable`、`Fatigued`、`MissingBodyPart` 等非 registry canonical code。 |
| B3: MCP Tool 三套名称空间 | GAP | `api-registry.md:158-261` 注册 46 个 active tools，且包含 `resources/list`、`resources/read` 非 `swarm_*` 命名；`design/interface.md:9` 要求 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status`、`swarm_get_available_actions`、`swarm_explain_last_tick` 等进入目录，但这些名称不在 registry active tools 中；`design/interface.md:21-67` 还保留另一套旧分类表。AI 玩家会从不同文档读到不同工具名。 |
| B4: Tick/Trace/Persistence 分叉 | CLOSED | `api-registry.md:427-468` 定义 TickTrace Envelope 22 字段并将 `wasm_status` 替换为 `terminal_state`；`api-registry.md:526-587` 定义 deploy_mutation、`fdb_version_counter` 与 async object-store manifest；`design/gameplay.md:1965-1968` 将 replay 保证绑定到 state_checksum、world_config 与 mods_lock。 |
| B5: 安全字段未入机器源 | CLOSED | `api-registry.md:177-261` 每个 MCP tool 表含 Required Scope、Subject Source、Replay Class、Visibility Filter、Rate Limit Key；`api-registry.md:285-293` 明确 Agent WS seq+MAC、Browser/Replay WS 只读安全模型。游戏设计方向不再发现会影响 AI onboarding 的安全字段缺口。 |
| B6: 经济单源未闭合 | CLOSED | `design/gameplay.md:336-373` 给出全局存储税、物流转换成本/时间；`design/gameplay.md:403-422` 给出 Vanilla 经济分类账并统一 Faucet/Sink/Transfer/Lockup/Unlock 术语；Market 在 `design/gameplay.md:390-392` 明确为 RFC，占位边界清晰。D3 的 refund 数值漂移另列 GAP。 |
| B7: 容量合同不可证明 | GAP | 正向证据：`api-registry.md:360-423` 已列全局容量、WASM 限制、worker pool、fair-share admission。反向证据：`design/gameplay.md:437-439` 说全局实体数超过 50,000 时新 Spawn 被拒为 `WorldEntityCapReached`，但 `api-registry.md:100-147` 的 canonical RejectionReason 未注册该 code，仅有 `RoomDroneCapReached`/`ServerOverloaded` 等；容量上限到可验证拒绝原因仍未完全闭合。 |
| D1: api-registry.md 全量生成 | CLOSED | `api-registry.md:3,7,11` 明确“由 game_api.idl.yaml 自动生成”“冲突时以 YAML 为准”“手写修改将被覆盖”；`api-registry.md:158-261,297-357,360-423,427-468` 覆盖 MCP Tools、Host Functions、容量限制、TickTrace 等主要 API 合同。未读取未列入允许清单的 YAML 原文。 |
| D2: RejectionReason canonical+debug_detail | CLOSED | `api-registry.md:71-89` 定义 35 canonical wire enum、`debug_detail` 最大 512 bytes、`detail_level` 三档；`api-registry.md:487-507` 将 `debug_detail` 放入统一 JSON-RPC error envelope。跨文档漂移已在 B1/B2 记录。 |
| D3: Recycle refund lifespan 10-50% | GAP | 用户裁决要求 lifespan 10–50%；但 `design/gameplay.md:106-108` 仍写标准世界 `Recycle` 固定退还 50%，Tutorial 前 500 tick 100%；`08-api-idl.md:159-162` 也仍是 `refund: registry.body_cost(body) * 0.5`。未看到 lifespan-based 10–50% 公式或 machine-readable policy。 |
| D4: Storage tax tiered 0/1/5/20bp | CLOSED | `design/gameplay.md:340-351` 定义 0–30%=0bp、30–60%=1bp、60–85%=5bp、85–100%=20bp；`design/gameplay.md:368-371` 给出 `global_storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`；`design/gameplay.md:394-401` 给出默认值与安全下限。 |
| D5: blob 异步上传 | CLOSED | `api-registry.md:561-587` 定义 `async_object_store_upload`：异步、不阻塞 FDB 提交路径、FDB 只存 blob hash pointer manifest；`api-registry.md:540-547` deploy flow 也明确 Upload Blob 与 Commit Manifest 分离。 |
| D6: soft_launch 3阶段 PvP | CLOSED | `design/gameplay.md:547-598` 定义 Phase 1 First-Attack Insurance、Phase 2 Soft PvP、Phase 3 Full PvP，并列出 shield/cooldown/damage_multiplier 配置参数。 |
| DA1: deploy_mutation replay_class | CLOSED | `api-registry.md:218-225` 将 `swarm_deploy` 标为 `idempotent_mutation`，输出含 `fdb_version_counter`/`object_store_key`；`api-registry.md:526-558` 说明 deploy events 必须按 `fdb_version_counter` 升序重放。 |
| DA2: f64→定点 | GAP | 正向证据：`design/gameplay.md:1950-1963` Determinism Contract 声明游戏引擎数值用整数+定点，禁 f64，Rhai 模组也禁浮点。反向证据：`design/gameplay.md:1018,1059,1213,1239` 仍使用 `special_param = 0.5` / `2.0` 和 `special_param: float`；`08-api-idl.md:196` 也保留效果描述但未给定定点字段。裁决未全局闭合。 |
| DA3: worker pool 256 default | CLOSED | `api-registry.md:407-415` 定义 Target active players 500、Hard cap 1000、Worker pool size=`min(max_pool, active_players)`、`max_pool` 默认 256 且 world.toml 可调。 |

## GAP 详情

### G1 — 单一事实源仍被 Markdown 重复表破坏

位置：
- `design/interface.md:9,21-67,69-79`
- `specs/gameplay/08-api-idl.md:65-111`
- `specs/reference/api-registry.md:3-5,11`

内容：
`api-registry.md` 已宣称是由 YAML 生成的权威源，但 `interface.md` 与 `08-api-idl.md` 仍保留旧版工具表、Capability Profile、RejectionReason enum 和 error envelope 示例。这会导致 AI 玩家从 MCP docs 学到不存在的工具名或旧错误码，直接破坏首小时调试体验。

建议闭合方式：非权威 Markdown 不再展开完整工具/错误码表，只保留“见 api-registry.md §x”的短引用；若必须保留示例，示例也必须从同一 YAML 生成。

### G2 — RejectionReason registry 正向闭合，但旧文档仍泄漏旧 wire codes

位置：
- `api-registry.md:69-89,100-155,487-507`
- `design/interface.md:164-187`
- `08-api-idl.md:65-111`

内容：
Registry 的 canonical+debug_detail 设计是正确的，但 interface 示例仍使用 `InsufficientResources`，08-api-idl 仍列出 `NotMovable`、`Fatigued`、`MissingBodyPart` 等旧变体。对 AI agent 来说，这不是纯文案问题：它会把错误处理分支写错。

### G3 — MCP 工具命名空间仍漂移

位置：
- `api-registry.md:158-261`
- `design/interface.md:9,21-79`

内容：
Registry active tools 与 interface 工具清单不一致；尤其 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status`、`swarm_get_available_actions`、`swarm_explain_last_tick` 在 interface 中被列为必须进入目录，但 registry active tools 未注册。另有 `resources/list` / `resources/read` 使用非 `swarm_*` namespace。若这是最终裁决，应在 interface 中同步；若不是，应从 registry 移除或改名。

### G4 — D3 Recycle refund 未按 lifespan 10–50% 改写

位置：
- `design/gameplay.md:106-108`
- `08-api-idl.md:159-162`

内容：
当前仍是标准世界固定 50% refund，Tutorial 100%。未体现“随 lifespan 剩余/消耗在 10–50% 区间变化”的用户裁决，也没有公式、边界或 machine-readable policy。

### G5 — DA2 定点化被 special_param 浮点示例破坏

位置：
- `design/gameplay.md:1950-1963`
- `design/gameplay.md:1018,1059,1213,1239`

内容：
Determinism Contract 已写“禁 f64、用 fixed”，但 custom action / special effect 的参数仍写 `float`、`0.5`、`2.0`。这会让模组作者和 codegen 对参数类型产生分叉。

### G6 — 容量上限到拒绝原因的合同未完全可证明

位置：
- `api-registry.md:360-423`
- `design/gameplay.md:437-439`
- `api-registry.md:100-147`

内容：
容量数字已经集中到 registry，但 gameplay 使用的 `WorldEntityCapReached` 未在 canonical RejectionReason 中注册。AI 玩家无法可靠判断 Spawn 被拒时应处理哪个 code。

## CrossCheck

1. 架构/工具链方向：请验证 `game_api.idl.yaml → api-registry.md → interface.md/08-api-idl.md` 是否真的全链路生成；当前只看到 registry 自称生成，未看到非权威 Markdown 消除双写。
2. 安全方向：请重点复核 `resources/list` / `resources/read` 这类非 `swarm_*` MCP namespace 是否符合签名、scope、rate-limit、visibility filter 的统一网关策略。
3. 经济/模拟方向：请复核 Recycle lifespan 10–50% refund 公式与 storage tax/empire-upkeep 是否会形成可被 re-deploy/recycle 利用的资源套利。