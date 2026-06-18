# R17 Phase 1 Clean-Slate 架构评审（GPT-5.5）

Reviewer: rev-gpt-architect
Role: Architect
Scope: 指定 R17 子集；未读取代码仓库、旧评审或 reviews/ 下既有材料。

## Verdict

REQUEST_MAJOR_CHANGES

R17 已经明显比早期轮次更接近“可实现的游戏引擎规格”：WASM-only 执行模型、Phase 2a/2b 分层、持久化分层、sandbox 边界和 Phase 2b manifest 都具备工程落地形态。但本轮的核心验收目标是“权威单源是否真正闭合”，在这个标准下仍不能通过。

最主要问题不是机制缺失，而是“权威层级仍然分裂”：Markdown registry、机器可读 IDL、tick protocol、command validation、persistence contract 各自都在声明同一类合同，但并未完全同步。这类问题在实现阶段会表现为 codegen、CI、SDK、replay verifier、validator、文档生成器各自相信不同事实源，属于典型的“看起来文档很多、实际没有一个能做唯一真相”的失败模式。

## Strengths / 亮点

1. WASM-only 玩家执行路径清晰

   README、tick protocol、sandbox 文档一致强调：AI agent 与人类玩家都只通过 WASM 模块参与游戏，没有 McpPlayerExecutor 作为 gameplay shortcut。这个方向是对的，也避免了“AI 玩家特权通道”破坏公平性的架构陷阱。

2. Tick 主生命周期具备可实现形态

   COLLECT → EXECUTE → BROADCAST 的三段式设计清楚；Phase 2a inline apply 与 Phase 2b deferred systems 的边界也基本稳定。特别是“Phase 2a 基于当前 Bevy World 状态逐条校验并应用”这个决策，对处理资源竞争和 TOCTOU 很关键。

3. Phase 2b manifest 是当前最接近权威闭合的部分

   `specs/core/06-phase2b-system-manifest.md` 明确给出 29 systems、stable system IDs、serial spine、parallel sets、R/W matrix、manifest hash 和 CI 验证项。相较常见设计文档，这是非常好的实现契约形式。

4. 持久化分层方向正确

   `specs/core/05-persistence-contract.md` 把 FDB 小事务、object store 大 blob、WAL、keyframe、orphan GC、hash chain 的角色分开，避免了“把完整 TickTrace 都塞进 FDB 事务”与“跨存储双写不可恢复”两种常见灾难。

5. Sandbox 边界较完整

   Wasmtime fuel、epoch interruption、Store reset、WASI 默认关闭、host function 白名单、cgroup/seccomp、恶意 WASM 样本和 CI 检查都已覆盖。对 MMO 编程游戏来说，这是必须的底座。

## Concerns / 发现问题

### A1. Critical — API registry 与 IDL 版本不一致，单一事实源未闭合

证据：

- `specs/reference/api-registry.md` 声明：
  - “机器可读权威源: game_api.idl.yaml”
  - 当前 API 版本为 `0.1.0`
  - 变更记录也停留在 `0.1.0`
- `specs/reference/game_api.idl.yaml` 声明：
  - `api_version: "0.2.0"`

这不是小 typo。registry 同时声称“Markdown 表格由 YAML 生成，冲突时以 YAML 为准”，但 Markdown 自己的版本号与 YAML 不一致，说明生成链、CI 校验或发布流程至少有一个没有闭合。

架构风险：

- SDK/codegen 可能以 `game_api.idl.yaml` 为准生成 0.2.0；
- 人类实现者可能以 `api-registry.md` 为准实现 0.1.0；
- TickTrace 记录 `api_version` 时不知道应写哪个；
- 兼容性迁移无法判断“旧 replay 用 0.1.0 还是 0.2.0”。

这类问题会在实现早期就爆炸，因为 registry/IDL 是所有 validator、SDK、文档生成、replay verifier 的根。

建议：

- 只允许 `game_api.idl.yaml` 存储 `api_version`。
- `api-registry.md` 中版本号、变更记录、表格全部由生成器重写，不允许手改。
- CI 增加 hard gate：Markdown 中出现的版本、total count、enum list、field list 必须与 IDL 完全一致。

### A2. High — RejectionReason 未闭合：validation 文档仍使用大量未注册错误码

`api-registry.md` / `game_api.idl.yaml` 声明 RejectionReason 共 35 个变体，并明确“新增指令/错误码必须在此注册，未注册 CI 拒绝”。但 `specs/core/02-command-validation.md` 的逐指令校验矩阵仍在使用大量 registry/IDL 中没有注册的拒绝码，例如：

- `NotMovable`
- `Fatigued`
- `MissingBodyPart(...)`
- `TileBlocked`
- `NotSource`
- `SourceEmpty`
- `CarryFull`
- `TargetFull`
- `TargetEmpty`
- `NotYourRoom`
- `TileOccupied`
- `InvalidTerrain`
- `TooManyConstructionSites`
- `FriendlyTarget`
- `NotFriendly`
- `AlreadyFullHealth`
- `NotYourSpawn`
- `BodyTooLarge`
- `ExceedsRoomCapacity`
- `AlreadyHacked`
- `InvalidDamageType`
- `AlreadyDebilitated(...)`
- `MainActionQuotaExceeded`

其中有些不是边缘情况，而是核心 gameplay validation 必需项，例如 fatigue、body part、source empty、target full、tile blocked。如果 registry 的 35 个变体是权威，那 validation 文档非法；如果 validation 文档是权威，那 registry/IDL 不完整。

架构风险：

- 玩家 SDK 无法穷举错误处理。
- TickTrace replay 无法稳定解析拒绝原因。
- 安全层的 opaque error 策略会被“更具体但未注册”的错误码绕穿。
- CI 如果真按 registry 执行，会拒绝 validation 文档中描述的大量合法场景；如果 CI 不拒绝，则 registry 的权威声明是假的。

建议：

- 将 RejectionReason 分层建模：
  - public/player-facing opaque code；
  - admin/internal detailed reason；
  - structured details enum 或 string-limited diagnostic。
- 对所有 validation 文档中的失败码做机器抽取，与 IDL 比对。
- 要么扩展 IDL 至覆盖这些码，要么把 validation 文档改成只使用 registry 中存在的码，并把具体原因放入 admin-only detail。

### A3. High — TickTrace Envelope 字段在 registry 与 persistence/engine 之间不一致

`design/engine.md` 与 `specs/core/05-persistence-contract.md` 都引入了 R16 B3 的 retry/commit 标识：

- `collect_id`
- `attempt_id`
- `commit_id`
- `terminal_state`

但 `specs/reference/api-registry.md` 的 TickTrace Envelope 表仍列出旧字段集合，未包含这些字段。`game_api.idl.yaml` 的 `tick_trace_envelope.total_fields: 22` 也没有包含 `collect_id` / `attempt_id` / `commit_id` / `terminal_state`。

架构风险：

- FDB commit retry 的 replay 语义依赖这些字段；
- persistence contract 已经把它们当作恢复和审计核心；
- 但 registry/IDL 没有注册，导致 codegen/replay verifier/schema validation 无法强制这些字段存在。

这会造成“文档说 retry 安全，但机器 schema 不知道 retry 发生过”的断层。

建议：

- TickTrace schema 必须在 IDL 中成为机器可读权威。
- `collect_id` / `attempt_id` / `commit_id` / `terminal_state` 若是正式合同，必须进入 IDL，并更新 total_fields。
- 如果这些字段只是 persistence 内部字段，则 engine.md 不应把它们放入 `TickInputEnvelope` 的公共字段列表。

### A4. High — CommandAction 与执行系统之间存在命名/职责漂移

registry/IDL 中核心指令是 `ClaimController`，manifest 的 S01 写 `Claim`，S02 写 `Claim` / `UpgradeController`，而 `UpgradeController` 并未出现在 CommandAction registry 中。engine.md Phase 2a 列表中也写 `Claim` 而不是 `ClaimController`。

类似地，validation 文档中把 `Leech` / `Fabricate` 写入特殊攻击优先级和后续章节，registry/IDL 说它们是 custom actions，不是 Core enum 成员。

架构风险：

- 实现者不知道 `Claim` 是 alias、旧名，还是另一个 action。
- `UpgradeController` 是 command、系统内部行为，还是 Transfer 到 controller 后的被动效果？当前文档同时暗示了多种解释。
- custom action 若进入 core priority table，需要一个 World Action Manifest 的排序合并规则，否则核心 manifest hash 无法完整决定执行顺序。

建议：

- 所有系统 manifest 中的 “Handled Commands” 必须只引用 IDL 中的 action name，或显式标注 internal event。
- 如果 `UpgradeController` 不是 CommandAction，应改名为 `controller_progress_apply` 之类的 internal system effect。
- custom actions 的 priority merge point 应由 World Action Manifest 注册，并且其 hash 已进入 TickTrace；不要在 core validation 文档中半注册。

### A5. Medium — 性能/容量权威源仍有重复声明，存在未来漂移风险

`api-registry.md` §5 声称全局容量限制是权威。`engine.md` §3.4.2 又完整列出 active players、drone cap、entity cap、snapshot cap、commands cap、pathfinding cap 等数值，虽然目前大多数值一致，并注明引用 registry，但仍是重复声明。

重复声明在设计阶段看似方便阅读，但在容量合同中很危险：一旦 registry 更新，engine.md 的表格很容易成为过时副本。

建议：

- engine.md 只保留性能解释与推导，不保留完整数值表。
- 或者把数值表标记为 generated-from-IDL，并由 CI 比对。

### A6. Medium — Snapshot truncation 策略存在两套描述

`engine.md` 描述 priority bucket 顺序为：自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源。

`01-tick-protocol.md` 描述：关键桶 Spawn/Controller/自有 depot/storage 无条件保留；高优先己方 drone/建筑；中优先敌方可见实体/资源点；低优先友方/中立实体，并按 `(distance_to_drone, entity_id)` 排序。

两者方向相近，但不是同一算法。对 replay determinism 来说，truncation 算法必须是单一版本化事实源；近似描述不够。

建议：

- 将 visibility/truncation 算法放入 IDL 或专门的 `visibility_truncation_version` manifest。
- 其他文档只引用该算法，不再重写 bucket 顺序。

### A7. Medium — 持久化合同与 tick protocol 对 TickTrace 写入失败的描述仍有张力

`05-persistence-contract.md` 说对象存储写入失败会导致 tick 放弃，FDB commit 是唯一权威持久化点，对象存储 blob 由 manifest/hash 证明。

`01-tick-protocol.md` 的失败矩阵仍包含：

- `TickTrace write fail`：tick 执行完成，审计不完整；
- `Replay write fail`：tick 执行完成，无 gameplay 影响；

但后文 6.3.4 又说 TickTrace 写入失败 = tick 放弃，不存在“tick 成功但回放数据丢失”。同一文件内部前后语义已经不一致，更不用说与 persistence contract 的关系。

架构风险：

- 运维 runbook 不知道“审计写失败”是继续运行还是暂停 tick。
- Replay verifier 不知道 audit_gap 是允许状态，还是 tick abandon 的结果。

建议：

- 删除或更新失败矩阵中的旧语义。
- 以 `05-persistence-contract.md` 为权威，明确：哪些 blob 是 gameplay-critical，哪些 artifact 可以 best-effort。
- 区分 `TickTrace canonical blob` 与 `analytics/replay artifact`，不要都叫 TickTrace/replay write。

## Missing / 缺失项

1. 缺少真正的 IDL → Markdown 生成闭环说明

   文档声称 Markdown 表格由 YAML 生成，但当前版本不一致。需要补充生成命令、CI gate、禁止手改策略、diff 检查策略。

2. 缺少 public error / internal diagnostic 的分层 schema

   当前安全目标要求 opaque error，但 gameplay 设计又需要丰富 rejection detail。需要正式 schema 解决两者冲突。

3. 缺少 custom action 与 core manifest 的合并规则

   `Leech` / `Fabricate` 被声明为 custom actions，但又出现在核心优先级矩阵与特殊攻击章节中。需要定义 custom action 如何进入 execution priority、validation、replay hash、SDK 类型。

4. 缺少 canonical codec 的具体定义

   TickTrace Envelope 包含 `canonical_codec_version`，但当前阅读范围内没有看到足够的 canonical serialization 规范。对 state_checksum、commands_hash、manifest_hash 来说，这将是实现 blocker。

5. 缺少“文档权威层级图”

   现在每个文件都说自己或别的文件是权威。建议明确：
   - IDL 是 API/limits/error/host ABI/TickTrace schema 权威；
   - phase2b manifest 是 system schedule 权威；
   - persistence contract 是 storage failure semantics 权威；
   - design docs 只解释 rationale，不重复可冲突表格。

## Phase Ordering / 建议修复顺序

1. 先修复 IDL / registry 生成链

   在继续任何实现前，必须让 `game_api.idl.yaml` 与 `api-registry.md` 完全一致。版本号、count、action list、rejection list、host functions、limits、TickTrace fields 都必须机器校验。

2. 然后统一 RejectionReason

   把 `02-command-validation.md` 中所有失败码抽取出来，与 IDL 对齐。这个问题优先级高于 gameplay 微调，因为 validator/SDK/TickTrace 都依赖它。

3. 再统一 TickTrace schema

   决定 `collect_id` / `attempt_id` / `commit_id` / `terminal_state` 是否是公共权威字段。若是，加入 IDL；若不是，从 engine/api registry 的公共 envelope 中移除并限定在 persistence 内部。

4. 再清理命名漂移

   统一 `ClaimController` / `Claim`、`UpgradeController`、custom action 的归属。manifest 的 handled command 名称必须全部可从 IDL 解析。

5. 最后压缩重复表格

   将 engine.md、tick protocol、sandbox 文档中的容量、host function、snapshot truncation、failure semantics 表格改为引用权威源或生成副本，避免后续轮次再次漂移。

## Final Assessment

R17 的架构方向值得保留，尤其是 WASM-only、公平 fuel、Phase 2a/2b、manifest hash、persistence 分层这些关键决策都符合成功案例的形态。但它还没有达到“权威单源闭合”的验收标准。

当前最危险的不是某个系统没设计，而是多个文档都足够详细、却不完全一致。这种状态在设计阶段比“缺文档”更危险，因为实现者会以为自己按文档做了，实际却是在按不同版本的事实源做。

因此本轮建议 REQUEST_MAJOR_CHANGES：先关闭 IDL/registry/validation/TickTrace 的权威源断裂，再进入下一轮评审。