# R24 Determinism Review — rev-gpt-determinism

## Verdict

CONDITIONAL_APPROVE

Specs 已经覆盖 Swarm 确定性所需的大部分关键合同：tick 三阶段、全局排序、FDB/TickTrace 原子性、RNG namespace、系统 manifest、可见性基准与 replay envelope 都有明确约束。但仍存在若干 spec ↔ design 未对齐点，其中 T1/T2 会直接影响 `tick(seed, state, commands) -> new_state` 的闭包定义或跨节点一致性，建议在 R25 前修正。

## Strengths

- Tick 状态机主干清楚：`COLLECT -> EXECUTE -> BROADCAST`，并在 spec 中补充了 crash/retry/FDB commit 语义。
- 命令排序在核心 spec 中已升级为五元组 `priority_class, shuffle_index, source_rank, sequence, command_hash`，能覆盖跨 source 与 tie-break 场景。
- TickTrace 与世界状态同事务写入的合同强，避免 replay-critical 审计缺口。
- `Complete Tick Execution Manifest` 将 Bevy 系统顺序、R/W 集合、parallel set 和 manifest hash 明确化，是跨节点同 tick 同输出的关键基础。
- 明确禁止 `std::HashMap` 迭代顺序、浮点与 OS 熵源，方向正确。

## Concerns

### T1 — High — WASM deterministic RNG host function 与 host ABI 权威表冲突

- 冲突位置：design/interface.md §5.1、§5.2 vs specs/core/01-tick-protocol.md §9.5；specs/reference/api-registry.md §4；specs/reference/game_api.idl.yaml §4；specs/core/04-wasm-sandbox.md §3.2
- 冲突描述：design/interface 与 sandbox/reference 都声明 WASM host functions 只有 5 个只读查询函数，且明确禁止非查询/额外 host function。`api-registry.md` 和 `game_api.idl.yaml` 也把总数固定为 5。可是 `01-tick-protocol.md` §9.5 又要求 WASM 代码必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数。
- 确定性影响：这是 replay 闭包缺口。若实现遵循 ABI 权威表，WASM 无合法 deterministic RNG API；若实现遵循 tick spec 增加 host function，则 codegen/SDK/reference 与 sandbox allowlist 不一致，不同节点可能加载不同 ABI 或拒绝模块。
- 修正建议：二选一并同步全链路：
  1. 若允许 WASM 请求随机数，把 `host_get_random(sequence, out_ptr, out_len)` 加入 design/interface §5.1、04-wasm-sandbox §3.2、game_api.idl.yaml、api-registry、host-functions.md，并定义 namespace、ordinal/sequence、budget、返回长度、replay 记录字段；或
  2. 若不允许 WASM RNG，删除 `01-tick-protocol.md` §9.5 的 `swarm_get_random(sequence)` 要求，改为“WASM 自行用 snapshot 中公开 seed 派生本地非权威随机”或“WASM 无随机源”。

### T2 — High — world_seed 轮换算法与“泄露窗口限制”安全/确定性语义不一致

- 冲突位置：design/gameplay.md §2.8（种子每 10,000 tick 自动轮换）vs specs/core/01-tick-protocol.md §3.1（种子轮换与前向保密威胁模型）
- 冲突描述：design 写“每 10,000 tick 自动轮换（Blake3(旧种子, 当前tick)），防止长期观察推断种子空间”。spec 进一步承认“知道 tick N 的 seed 可推导 tick N+1, N+2... 的所有未来种子”，但同一节又说“定期轮换限制泄露窗口宽度——攻击者最多预测 10000 tick 的未来”。两者不能同时成立：若轮换是 `new_seed = Blake3(old_seed || tick)`，泄露当前 epoch seed 后可继续推导之后所有自动轮换 epoch。
- 确定性影响：seed 是排序、combat、loot、NPC/event 的根。此处不是单纯安全措辞问题，而是 replay 与运营事故恢复合同不清：自动轮换到底是否提供未来窗口上限？TickTrace 中记录 seed epoch 后，replay verifier 需要哪些 seed 材料也未完全对齐。
- 修正建议：将合同改为明确版本之一：
  1. “自动轮换仅做 domain separation/epoch accounting，不提供泄露后的未来不可预测性；泄露后必须 operator seed-bump 注入新 seed，TickTrace 记录新 seed hash/epoch id，replay 使用受保护 seed archive”；或
  2. 若坚持 10,000 tick 窗口，需要外部秘密/VRF/commit-reveal，不应声称纯 `old_seed -> new_seed` 能限制泄露后的未来预测。

### T3 — Medium — 命令排序键在 design 中仍是旧四元组，spec 是五元组

- 冲突位置：design/gameplay.md §2.8 固定算法表；design/engine.md §3.3 vs specs/core/01-tick-protocol.md §9.1；specs/core/02-command-validation.md §2.1
- 冲突描述：design/gameplay 的排序写为 `(priority_class, shuffle_index, sequence, source)`；design/engine 只描述“洗牌后顺序 + 玩家内 sequence”。核心 spec 已升级为 `(priority_class, shuffle_index, source_rank, sequence, command_hash)`，并明确 `sequence` 是 per-(player, source)。
- 确定性影响：设计层若被实现者作为入口，会遗漏 `source_rank` 与 `command_hash` tie-breaker。相同玩家、相同 source、相同 sequence 的重复/异常命令在不同节点可能因输入数组顺序或 map 迭代顺序不同而排序分叉。
- 修正建议：design/gameplay §2.8 与 design/engine §3.3 不应重述旧排序键；改为引用 `specs/core/01-tick-protocol.md` §9.1，或同步写入完整五元组，并说明 `command_hash = Blake3(canonical_command_json)`。

### T4 — Medium — 快照截断唯一权威与核心 tick spec 的截断算法不一致

- 冲突位置：specs/core/09-snapshot-contract.md §1.3/§1.4 vs specs/core/01-tick-protocol.md §2.3；design/engine.md §3.2
- 冲突描述：`09-snapshot-contract.md` 声称自己是 snapshot truncation 唯一权威，算法为距离桶 + `entity_id` 字典序，从最远桶末尾移除，并列出 critical 实体。`01-tick-protocol.md` §2.3 仍保留另一套“关键/高/中/低优先桶 + `(distance_to_drone, entity_id)` 升序”的截断描述，还要求 `host_get_objects_in_range` 返回 `{items, truncated, total_visible_count?}`，这不在 host function reference/API registry 的权威签名中。
- 确定性影响：快照是 WASM `tick()` 的输入；两套截断算法会让相同世界状态在不同实现中生成不同 snapshot，从而导致不同 commands/new_state。host query 的截断元数据也会影响玩家代码分支。
- 修正建议：从 `01-tick-protocol.md` §2.3 删除或降级旧算法，只保留“按 `09-snapshot-contract.md` 执行”；若 host query 也需要截断标记，把返回 schema 同步到 `game_api.idl.yaml`/`api-registry.md`/`host-functions.md`。

### T5 — Medium — “禁浮点”合同与 world rules / design 示例仍使用 float

- 冲突位置：design/gameplay.md §2.8（数值禁浮点） vs design/gameplay.md §伤害与武器类型；specs/core/07-world-rules.md §7.5/§7.6；specs/reference/game_api.idl.yaml Type Registry
- 冲突描述：design 的确定性合同要求所有引擎数值和 Rhai 模组参数使用整数/定点，禁用 f64/浮点。可是 design/gameplay 的 `default_resistance = 1.0`、`final_multiplier = body_resistance × attribute_resistance`，以及 `07-world-rules.md` 中 `special_param | float`、`default_resistance = 1.0` 仍在规则配置层暴露 float。
- 确定性影响：规则配置是 tick 输入的一部分。若 TOML/Rhai/引擎解析 float，不同平台、序列化库或舍入策略可能影响 combat damage、resistance、special effect 参数，破坏跨节点与 replay 一致性。
- 修正建议：将这些字段统一改为 fixed-point：例如 `default_resistance_bps = 10000`、`special_param_bps` 或按 effect 定义 typed fixed field；同时在 `07-world-rules.md` 配置校验中声明拒绝 float literal。

## State Machine Gaps

- Deploy 状态机整体已有 `05-persistence-contract.md`，但 design/engine 的回放 envelope 仍只是字段列表，未直接声明 `activation_tick/upload_status/failed/active` 的完整转换权威，建议 design 只引用 persistence spec，避免双写。
- `swarm_get_random(sequence)` 若保留，需要定义 RNG ordinal/sequence 状态机：同 tick 多次调用、重复 sequence、预算失败、trap/timeout、replay 不重跑 COLLECT 时如何记录和复现。
- Snapshot truncation 的 degraded tick 已在 `09-snapshot-contract.md` 定义，但 `01-tick-protocol.md` 的 tick failure/degraded matrix 没有把 `tick_integrity=degraded` 纳入 tick output contract，消费者可能不一致。
- Arena 终止条件在 design/modes.md 明确，但核心 spec 中没有对应 replay-critical terminal_state/score tie-break 的规范引用；若 Arena 属于本轮必须冻结范围，应补一个 spec 锚点。

## Non-Determinism Sources

- 浮点：`special_param: float`、`default_resistance = 1.0`、debug 示例中的 `distance: 12.53`/`required_range: 5.0` 若进入 replay-critical 数据，需要改为定点或明确仅展示层。
- RNG：`world_seed` 自动轮换不提供泄露后未来不可预测性；`swarm_get_random(sequence)` 未进入 ABI/IDL；simulate fork 有独立 RNG namespace，但与 authoritative ordinal 的边界需避免实现者共享状态。
- HashMap/迭代顺序：主合同要求 `indexmap`，但 design/gameplay §2.2/§2.7 示例仍多处使用 `HashMap<ResourceName, Amount>` 作为核心配置/成本容器；建议文档标注“逻辑 map，序列化/迭代按 canonical key sort”。
- 系统时间：auth/security 文档中的 timestamp/nonce/audit log 属于安全域；若这些事件进入 replay-critical TickTrace，需要使用 tick/logical time 或明确 replay 只记录不重算。
- 并行 push order：manifest 已正确要求 per-system sub-buffer + serial merge sort；需要保持所有新增 systems 继承此要求，特别是 RuleMod action log merge 与 NPC/event 生成。

## Replay Completeness Check

当前合同接近 `tick(seed, state, commands) -> new_state` 闭包，但 T1/T4/T5 未修前仍有三类输入未闭合：

1. WASM 随机数 API 是否存在、如何记录；
2. snapshot/query 截断采用哪套唯一算法；
3. world.toml/Rhai 数值是否完全定点。

修正后，跨节点同 tick 输出的一致性将主要依赖 `Complete Tick Execution Manifest`、canonical command sort、fixed-point world rules 与 TickTrace 同事务写入，这些基础已经足够强。