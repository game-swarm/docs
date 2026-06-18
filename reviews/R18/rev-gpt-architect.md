# R18 架构评审（GPT-5.5）

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

R18 的核心进展是明确把 `game_api.idl.yaml` 作为机器事实源，并且 `api-registry.md` 在关键 API 表面上已经基本呈现“由 YAML 生成”的闭合状态。我做了 YAML ↔ Markdown 的机械交叉检查：`api_version=0.3.0`、CommandAction 19/19、RejectionReason canonical 35/35、MCP tools 46/46、Host Functions 5/5 均能在 `api-registry.md` 中闭合，无明显表格漂移。

但从架构闭合角度看，当前还不能批准进入实现：**YAML 与生成的 Markdown 闭合了，不等于整个设计合同闭合了**。多个核心 spec 仍在重复声明 API enum、Host ABI、tick/persistence 失败语义、Phase 2b 调度与容量上限，并且与 YAML/registry 或 manifest 冲突。这是典型“单源生成看起来成功，但周边手写规范继续分叉”的失败模式；新人或实现者按不同文档实现，会得到不兼容的 engine、SDK、replay verifier 与运维语义。

---

## 2. 发现问题（severity）

### A1 — BLOCKER — RejectionReason 仍未真正收敛到 YAML 的 35 canonical code

`game_api.idl.yaml` 明确声明：35 个 canonical code 是 wire enum；`NotMovable`、`Fatigued`、`PathBlocked` 等上下文信息应进入 `debug_detail`，不能成为额外 RejectionReason enum。`api-registry.md` 与 YAML 在 35 个 canonical code 上闭合。

但 `specs/core/02-command-validation.md` 仍大量把非 canonical 名称作为“失败码”使用，例如：

- `NotMovable`
- `Fatigued`
- `MissingBodyPart(...)`
- `TileBlocked`
- `StillSpawning`
- `SourceEmpty`
- `CarryFull`
- `NotSource`
- `TargetFull` / `TargetEmpty`
- `NotYourRoom`
- `InvalidTerrain`
- `TooManyConstructionSites`
- `FriendlyTarget`
- `AlreadyFullHealth`
- `AlreadyHacked`
- `InvalidDamageType`
- `AlreadyDebilitated(...)`
- `MainActionQuotaExceeded`

这些名称不在 YAML 的 35 canonical code 中。结果是：

1. engine validation 很容易直接实现这些“失败码”；
2. SDK / MCP error schema 只生成 35 canonical code；
3. replay / TickTrace 中的 rejection registry version 无法判断这些额外值是否合法；
4. 安全上 `NotVisibleOrNotFound` 的 opaque 策略会被 `ObjectNotFound`、`NotSource`、`TargetEmpty` 等细分码绕开。

建议：`02-command-validation.md` 的逐指令矩阵不要再写 wire-level failure code。应改为：

- `canonical_code`: 只能从 YAML 35 code 中选择；
- `debug_detail`: 放 `NotMovable: ...` / `Fatigued: ...` 等细节；
- 若确实需要新增 canonical code，必须先改 YAML，然后生成 registry，再让 spec 引用。

这是当前最大阻塞，因为它直接破坏 R15-R17 试图修复的“错误码权威源”。

---

### A2 — BLOCKER — TickTrace `terminal_state` 存在两个不兼容枚举语义

YAML / generated registry 中的 TickTrace Envelope 定义了 `terminal_state` 为 WASM 执行终态：

- `Success`
- `FuelExhausted`
- `TimeoutExceeded`
- `SnapshotOverBudget`
- `CommandBufferFull`
- `InternalError`
- `NotExecuted`

但 `specs/core/05-persistence-contract.md` §6.2 又把 blob 损坏 / replay 完整性状态称为“终端状态”：

- `verified`
- `audit_gap`
- `unreplayable`
- `reconstructable`

这不是同一个域。一个是 sandbox execution terminal state，一个是 persistence/replay artifact integrity state。若两者都叫 `terminal_state`，实现者会面临三种错误选择：扩展 YAML enum、覆盖 YAML enum、或在不同上下文里复用同名字段。三者都会导致 replay verifier 和 SDK schema 分叉。

建议：持久化层字段改名，例如：

- `artifact_integrity_state`
- `trace_blob_state`
- `replay_artifact_state`

并且作为独立 enum 写入 YAML（如果需要机器可读），不要复用 `tick_trace_envelope.terminal_state`。

---

### A3 — HIGH — Host Function ABI 在 registry 与 WASM sandbox spec 之间仍然漂移

YAML / `api-registry.md` 的 Host Functions 定义为：

- `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32`
- `host_get_objects_in_range(x, y, range, out_ptr, out_len) -> i32`
- `host_path_find(from_x, from_y, to_x, to_y, opts_ptr, opts_len, out_ptr, out_len) -> i32`
- `host_get_world_config(key_ptr, key_len, out_ptr, out_len) -> i32`
- `host_get_world_rules(rule_id_ptr, rule_id_len, out_ptr, out_len) -> i32`

但 `specs/core/04-wasm-sandbox.md` §3.2 手写的 host function 列表仍是另一套 ABI：

- `host_get_terrain(x: i32, y: i32) -> i32`
- `host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32`
- `host_get_world_rules(out_ptr, out_len) -> i32`

这会直接影响 SDK codegen、玩家 WASM import、engine host linker 与 ABI error priority。它不是文档细节，而是二进制接口不兼容。

建议：`04-wasm-sandbox.md` 不再手写 ABI signature，只引用 `game_api.idl.yaml.host_functions`；若需要解释调用协议，只解释指针安全、可见性过滤、budget，不重复函数参数表。

---

### A4 — HIGH — Persistence 原子性语义在 01 与 05 之间冲突

`specs/core/01-tick-protocol.md` 多处坚持：

- TickTrace 与世界状态写入同一 FDB 事务；
- TickTrace 写入失败应导致 tick 回滚 / 放弃；
- 不允许“状态成功但审计缺失”；
- “TickTrace 写入失败 = tick 放弃”。

但 `specs/core/05-persistence-contract.md` 采用 D5/B async object-store 模型：

- FDB commit 先成功；
- TickTrace blob 后台异步上传；
- blob 上传失败时 world state 仍完整；
- replay 不可用或产生 audit gap。

这两个模型不能同时为真。当前文档把“TickTrace manifest/hash 与状态同事务”与“完整 TickTrace blob 异步上传”混在一起，但 01 的文字仍把 TickTrace 当作完整审计记录同事务写入。这会让实现者在失败语义上分叉：是牺牲 tick 可用性保证审计原子性，还是允许 state-first + replay gap？

建议明确三层：

1. FDB 同事务强制写入：`tick_head`、`state_checksum`、`trace_manifest`、`content_hash`、`chain_hash`、`fuel ledger`。
2. Object Store 异步写入：完整 trace blob / snapshot blob。
3. Replay 语义：FDB manifest 缺失 = tick 不存在；blob 缺失 = tick 存在但 artifact incomplete。

然后删除 01 中“TickTrace blob 写失败导致 tick 放弃”的旧语义，或反过来废弃 async blob 模型。不能并存。

---

### A5 — HIGH — Phase 2b 调度在 02 与 manifest 之间仍有旧顺序残留

`specs/core/06-phase2b-system-manifest.md` 是权威调度：

`death_marker → spawn → spawning_grace → regeneration → combat → special_attack_reducer → damage_application → status effects/status_advance → aging → decay → death_cleanup → ...`

但 `specs/core/02-command-validation.md` §3.19 仍写：

`death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`

这与 manifest 冲突：

- manifest 中 `regeneration` 在 combat/damage 前；02 中在 combat/status 后；
- manifest 中 `status_advance` 在 S16-S22 status set；02 中放在 combat 后、regen 前；
- manifest 中 `damage_application` 是独立阶段；02 的简图没有表达；
- manifest 已将 `decay` 作为 S24 serial within C；02 说 regen/decay 并行。

调度顺序是 determinism 的核心合同，不应在 validation spec 里有第二套旧图。建议 02 删除 §3.19 的顺序图，只引用 manifest 中 S07-S29 的 stable IDs。

---

### A6 — HIGH — 容量与限制仍存在多处“手写权威值”分叉

`api-registry.md` §5 / YAML `limits` 声明容量为权威。但其他文档继续写可冲突数字：

- `engine.md` Worker Pool 推导写 `MAX_POOL = 1000`，而 YAML/registry 的 `worker_pool_max = 256`。
- `02-command-validation.md` 硬性边界写 `MAX_DRONES_PER_PLAYER = 50`，而 YAML/registry 的 per-player drone cap 是 500。
- `02-command-validation.md` 同时出现“整批 tick 输出 ≤ 1MB”，而 `01-tick-protocol.md`、`04-wasm-sandbox.md` 与 registry 均把 WASM 输出 / snapshot 相关上限写成 256KB 语义。
- `04-wasm-sandbox.md` 模块体积上限为 5MB；YAML persistence blob type `wasm_module` max size 为 64MB。两者可能分别代表“上传模块最大体积”和“对象存储 blob 最大体积”，但当前命名不清，会被实现成两个互相打架的限制。

建议：所有数值限制只在 YAML 中保留；其他文档写 `$ref` 式引用名，例如 `limits.hardware_baseline.worker_pool_max`，不要再写裸数字。需要推导时也引用变量，不重复常量。

---

### A7 — MEDIUM — YAML→Markdown 生成闭合可见，但缺少可审计的 generator provenance

我对 `game_api.idl.yaml` 与 `api-registry.md` 做了机械 spot-check，结果如下：

```json
{
  "api_version_yaml": "0.3.0",
  "api_version_md_present": true,
  "command_yaml_count": 19,
  "command_declared_total": 19,
  "command_md_count_first_section": 19,
  "command_name_diff": {"yaml_not_md": [], "md_not_yaml": []},
  "rejection_yaml_count": 35,
  "rejection_declared_total": 35,
  "rejection_md_known_count": 35,
  "rejection_name_diff": {"yaml_not_md": [], "md_not_yaml_known_extra": []},
  "mcp_yaml_count": 46,
  "mcp_declared_total": 46,
  "mcp_missing_in_md": [],
  "host_yaml_count": 5,
  "host_declared_total": 5,
  "host_missing_in_md": []
}
```

这说明核心表面已闭合。但 `api-registry.md` 目前只写“生成日期”和“权威源”，没有看到：

- YAML content hash；
- generator version；
- generation command；
- CI drift-check 命令；
- “Markdown 禁止手改”的可执行 enforcement 说明。

对于单事实源架构，建议生成文件头包含：

```text
Generated from: game_api.idl.yaml
IDL hash: blake3:...
Generator: swarm-api-docgen x.y.z
Command: cargo run -p api-docgen -- specs/reference/game_api.idl.yaml
Do not edit: CI verifies generated output byte-for-byte
```

否则“生成式单源”仍依赖人工信任，不是可审计闭环。

---

### A8 — MEDIUM — 快照截断策略存在多版本描述，容易影响玩家可预期性与 replay

`engine.md` 的 WASM Snapshot Truncation 写 priority bucket 顺序为：

`自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源`

`01-tick-protocol.md` §2.3 写另一套：

1. 关键桶：Spawn、Controller、玩家拥有 depot/storage
2. 高优先：己方 drone、己方建筑
3. 中优先：敌方可见实体、资源点
4. 低优先：友方实体、中立实体

两者都声称确定性，但保留对象不同。截断策略会改变玩家输入 snapshot，进而改变 WASM 输出和 replay。它必须像 system manifest 一样成为可 hash 的机器合同。

建议把 snapshot truncation algorithm 移入 YAML 或独立 `visibility_truncation_manifest`，TickTrace 中记录 `visibility_truncation_version` / hash；其他文档只引用。

---

## 3. 亮点

### S1 — YAML ↔ api-registry 的关键 API 表面已经基本闭合

这次 R18 最值得肯定的是：`game_api.idl.yaml` 与 `api-registry.md` 在核心枚举与工具表上已能机械对应。相比早期“registry、IDL、interface/spec 各写一遍”的状态，这是正确方向。

### S2 — TickTrace Envelope 开始把实现版本纳入 replay 合同

YAML 中的 `system_manifest_hash`、`limits_manifest_hash`、`host_abi_version`、`canonical_codec_version`、`visibility_truncation_version` 是非常关键的架构设计。它把 replay 从“相信当前代码”推进到“记录当时合同版本”。这是长期可维护 MMO simulation 的必要条件。

### S3 — Phase 2b system manifest 的形态是对的

`06-phase2b-system-manifest.md` 用 stable system IDs、R/W matrix、parallel set、RoomCap 中间态保护来约束 Bevy 调度，方向正确。这个文档像真正的 engine manifest，而不是普通说明文。问题主要是其他文档还在重复声明旧顺序。

### S4 — Persistence 分层的目标方向正确

FDB 存小对象与 manifest/hash，大 blob 入 object store，hash chain 贯穿，这是现实可落地的 MMO/replay 存储方案。它避免了“每 tick 全量塞进 FDB”的失败模式。当前需要修的是失败语义和字段命名，而不是整体方向。

### S5 — Debug detail 与 competitive/practice/training 的分层设计合理

把 wire enum 固定为 35 个 canonical code，同时用 `debug_detail` 和 `detail_level` 控制信息泄露，是比无限扩展错误码更稳的 API 设计。这个模式适合竞技游戏：比赛模式少泄露，训练模式多反馈。

---

## 4. CrossCheck

### 4.1 YAML ↔ api-registry.md 机械核查结论

结果：**通过（核心表面）**。

核查范围：

- API version：YAML `0.3.0`，Markdown 有 `0.3.0`。
- CommandAction：YAML 声明 19，Markdown section 1 列出 19；名称集合一致。
- RejectionReason：YAML canonical indexed codes 35，Markdown 列出 35；名称集合一致。
- MCP tools：YAML tools 46，Markdown active tools 46；未发现 YAML tool 在 Markdown 中缺失。
- Host functions：YAML 5，Markdown 5；名称集合一致。

这说明 `api-registry.md` 很可能确实由 YAML 生成，至少关键 API 列表没有漂移。

### 4.2 YAML/registry ↔ 其他核心 specs 核查结论

结果：**未通过（架构合同未闭合）**。

主要漂移点：

1. `02-command-validation.md` 仍使用大量非 canonical RejectionReason。
2. `04-wasm-sandbox.md` 手写 Host ABI 与 YAML 不一致。
3. `01-tick-protocol.md` 与 `05-persistence-contract.md` 的 TickTrace / object-store 失败语义冲突。
4. `02-command-validation.md` 的 status_advance 调度与 `06-phase2b-system-manifest.md` 冲突。
5. 容量限制在 YAML、engine.md、02、04 之间仍有多版本数字。
6. `terminal_state` 字段名在 YAML WASM execution domain 与 persistence blob integrity domain 发生语义碰撞。

### 4.3 架构模式判断

当前状态像很多大型系统在“单源化改造”的中间阶段：

- 中心 schema 已经建立；
- generated doc 也能生成；
- 但旧手写规范仍在周边保留“局部真相”；
- 实现团队最终会按最熟悉的那份文档写代码，而不是按 schema 写。

这类系统上线后最常见的爆点不是 YAML 与 generated Markdown 漂，而是：engine 按 core spec 实现、SDK 按 registry 生成、replay verifier 按 persistence contract 验证，三者各自“正确”，组合起来不兼容。

### 4.4 建议的 Phase Ordering（修复顺序）

1. **先收敛 wire contracts**：RejectionReason、Host ABI、TickTrace field names。否则 SDK/engine 无法对齐。
2. **再收敛 execution contracts**：Phase 2b 调度、snapshot truncation、capacity limits 全部改为 manifest/YAML 引用。
3. **再收敛 persistence failure semantics**：明确 FDB manifest 原子性 vs object-store blob eventual consistency，改掉 01/05 冲突。
4. **最后补 CI enforcement**：生成 `api-registry.md` 的 byte-for-byte drift check、禁止手改 generated file、检查 docs 中禁止出现裸 enum/list/limit 的重复声明。

---

## Missing

- 缺少可审计 generator provenance：IDL hash、generator version、生成命令、CI drift-check。
- 缺少“文档不得重复声明 YAML 字段”的 lint 规则。
- 缺少 RejectionReason 从 spec matrix 到 canonical code + debug_detail 的映射表。
- 缺少独立命名的 replay artifact integrity enum，避免污染 WASM `terminal_state`。
- 缺少机器可读的 snapshot truncation manifest。

---

## Phase Ordering

本次不能只修 `api-registry.md`，因为它已经基本没漂。下一阶段应优先做“去手写权威化”：把 `02-command-validation.md`、`04-wasm-sandbox.md`、`01-tick-protocol.md` 中与 YAML/manifest 重复的 enum、ABI、limits、system order 删除或改为引用。只有当周边 specs 不再拥有第二套真相，R18 的“生成式单源闭环”才真正成立。
