# R13 — rev-gpt-architect 架构评审

Reviewer: rev-gpt-architect / GPT-5.5
Scope: `/data/swarm/docs/design/DESIGN.md`, `design/tech-choices.md`, `design/ROADMAP.md`, `specs/p0/*.md`
Date: 2026-06-14

## Verdict

REQUEST_MAJOR_CHANGES

整体方向已经从早期风险最大的「MCP 直接操作游戏」纠正为「世界只认 WASM」，这是正确的核心架构。P0 文档也已经覆盖 tick、command validation、visibility、sandbox、IDL、source gate 等关键面，说明架构已经进入可实现阶段。

但当前 R13 仍不建议冻结后直接进入 Phase 1。主要问题不是“缺功能”，而是几个基础合同之间存在实现级冲突：

1. Tick 持久化与 Phase Ordering 不一致：P0-1 把 FDB commit 放进 EXECUTE 的原子语义，但 ROADMAP 把 FDB 放到 Phase 3，同时 Phase 1 又要求 TickTrace + replay。
2. WASM ABI 仍不完整：`tick(ptr,len)->i32` 只返回指针，不返回长度/错误/free 协议，无法可靠读取 command JSON。
3. Visibility 中 `player_view = full` 同时影响 MCP，只要 AI 可通过 MCP 获取全图，就能把信息写进下一版 WASM 策略，破坏 fog-of-war 公平性。
4. RuleMod capability 模型与 P0-7 的实际 ECS system 能力不一致，容易绕过 Command Validation Pipeline。
5. Sandbox “每 tick fork → 执行 → kill”与 500 玩家、Wasmtime 模块缓存、3s tick 目标之间缺少容量模型，存在看起来安全但实际会被启动/实例化开销打爆的风险。

建议：不要扩大新功能；先做一次 “P0 contract cleanup”，把上述 blocker 变成明确可测试的不变量，再进入 Phase 1。

## Strengths

- 核心公平模型正确：人类和 AI 都通过部署 WASM 进入世界；MCP 是观察、部署、调试界面，不是 gameplay action controller。
- Deferred Command Model 是好选择：WASM 输出 `Command[]`，引擎统一校验和应用，天然利于 replay、audit、anti-cheat、UX rejection explanation。
- `Source Gate` 把 WASM / MCP_Deploy / MCP_Query / Admin / Replay / RuleMod 等来源显式建模，比“到处 if admin”更可审计。
- `is_visible_to(player,tick)` 单函数覆盖 snapshot/MCP/WS/REST/replay，是避免信息泄露的正确抽象。
- IDL 作为 single source of truth 的方向正确，能压住 Rust command enum、TS SDK、MCP schema、docs、test generator 分叉。
- Refund 策略已经考虑 anti-amplification、next-tick credit、module_hash binding，比大多数游戏经济设计更成熟。
- 技术选型总体务实：Rust + Bevy ECS、Wasmtime、NATS、ClickHouse 都和目标问题匹配；没有过早引入 Kubernetes/actor framework 这类无关复杂度。

## Concerns

### A1 — Critical — P0-1 的 FDB 原子 tick 语义与 ROADMAP Phase 1/3 矛盾

P0-1 §3.4 规定 EXECUTE 阶段包在 FoundationDB transaction 中，commit 失败则 tick abandon，且 Bevy World 需要显式 restore。P0-1 §6.3 又要求每 tick 写 `/tick/{N}/commands/state/rejections/metrics`。但 ROADMAP 把 FoundationDB 持久化列为 Phase 3，同时 Phase 1 交付物已经要求 TickTrace + replay 验证。

这不是排期小问题，而是语义分裂：

- 如果 Phase 1 没有 FDB，却实现 replay，那么 replay 存储在哪里？内存？文件？SQLite？这些都会影响 TickTrace schema 和 failure semantics。
- 如果 Phase 1 有 FDB，那么 ROADMAP Phase 3 “持久化上线”是假的，实际 Phase 3 只剩多房间/缓存/OLAP。
- 如果 Phase 1 用临时存储，Phase 3 再迁移到 FDB，TickTrace/replay 的早期测试价值会下降，因为核心 failure path 没被测试。

建议：二选一。

- 方案 A：把最小 FDB commit + TickTrace 移到 Phase 1，Dragonfly/ClickHouse/多房间留 Phase 3。
- 方案 B：把 P0-1 改成 `PersistenceAdapter` 合同，Phase 1 明确使用 `InMemoryTraceStore/FileTraceStore`，并说明其 failure semantics 不等价于生产 FDB；Phase 3 才启用 FDB abandon/restore 合同。

我倾向方案 A。因为 replay determinism 是本架构的根，不应晚于 MVP。

### A2 — Critical — WASM `tick()` ABI 不足以读取返回 JSON

P0-4 和 P0-8 定义：

`tick(snapshot_ptr: i32, snapshot_len: i32) -> i32`

注释说返回值是 “pointer to command JSON in WASM memory”。但 host 还需要知道：

- 返回 JSON 的长度在哪里？
- 返回值 0 是成功还是 null pointer？P0-8 写 “0 = success, pointer to command JSON” 本身矛盾。
- WASM 分配的返回 buffer 谁释放？何时释放？需要 `alloc/free` export 吗？
- snapshot 输入 buffer 由谁分配？host 写入 WASM memory 前如何获得可写区域？
- 如果 tick 返回错误码，错误码和 pointer 如何区分？
- command JSON 超过 256KB 时，host 是先读长度再拒绝，还是盲扫内存？

这是实现阻断项。建议冻结一个明确 ABI，例如：

- WASM 必须 export `alloc(len)->ptr`, `free(ptr,len)`, `tick(snapshot_ptr,snapshot_len,result_ptr)->i32`。
- `result_ptr` 指向 host 写入的 `{ ptr: u32, len: u32 }` out struct。
- `tick` 返回 `0=ok, negative=error_code`。
- host 读取 `(ptr,len)` 后检查 `len <= 256KB`，复制出 command JSON，然后调用 `free(ptr,len)`。
- 所有 pointer/len 做 bounds check、alignment check、integer overflow check。

没有这个，P0-2 JSON schema、P0-4 sandbox、P0-8 IDL 都无法落地。

### A3 — Critical — `player_view = full` 如果影响 MCP，会破坏 fog-of-war 公平性

P0-5 §3.5 表格写：

- `player_view = "full"`
- drone snapshot 仍按 `is_visible_to(player)` 过滤
- 玩家屏幕 / MCP = 全地图

这在“人类看全图但代码只看局部”的单机调试里也许可接受，但 Swarm 的 AI 玩家会通过 MCP 读取世界，然后生成/部署下一版 WASM。只要 MCP 能看全图，AI 就能把隐藏信息编码进策略，下一 tick 的 WASM 虽然 snapshot 被过滤，但策略已经利用了隐藏信息。

这等价于给 AI 一个 out-of-band oracle。它违反 DESIGN 的核心原则：MCP 与 Web UI 同级且不提供更多信息；更重要的是违反 gameplay fairness。

建议：

- 在 World 模式，player-authenticated MCP read 永远不得超过 `is_visible_to(player,tick)`。
- `player_view=full` 只能用于：local dev、admin、delayed spectator、post-game Arena replay、tutorial sandbox，且 source 不能是普通 `MCP_Query`。
- 若 Web UI 允许 full camera，也必须明确这是非 ranked / non-authoritative / delayed / admin-only。
- P0-9 Source Gate 增加 visibility mode gate：`MCP_Query` in World cannot request full map。

### A4 — High — RuleMod capability 合同自相矛盾，可能绕过 Command Validation

P0-9 说 `RuleMod` 只能 “经济 + 事件”，能力表写 `deduct/award/emit_event`，不能触发战斗，不能查询世界。P0-7 又说规则 System 可以：

- 在 Command 执行前拦截
- 在 Command 执行后补充
- 修改 ECS 资源/组件
- 例如 `code_propagation_system` 修改 `CodeVersion`
- `memory_upkeep_system` 修改 `PlayerResources` 和 memory

这已经不只是经济 + 事件，而是能影响 code version、resources、memory、visibility/combat systems 的 ECS plugin。若 Rhai/actions 可以间接修改组件，就必须有 capability model；否则“不能绕过 Command Validation Pipeline”只是文档愿望。

建议把 RuleMod 分成两层：

1. Declarative rules：配置项驱动 Rust 内置 systems，例如 costs、cooldown、visibility、damage multiplier。
2. Scripted mods：Rhai 只能发起受 schema 限制的 `RuleAction`，每个 action 进入 RuleAction Validator，不直接拿 ECS mutable access。

并在 P0-9 中把 RuleMod 能力从“经济 + 事件”扩展成枚举：`Economy`, `CodeDeploymentPolicy`, `VisibilityPolicy`, `CombatModifier`, `SpawnPolicy` 等，每项有预算、审计和 replay representation。

### A5 — High — Sandbox 生命周期和容量目标缺少可行性模型

文档同时要求：

- 每 tick fork → 执行 → kill。
- 每 tick 2500ms collect timeout。
- 500 AI 玩家/引擎实例。
- Wasmtime fuel metering、epoch interruption、64MB linear memory、128MB cgroup。
- 3s tick，Phase 2 p99 < 5s，Phase 7 p99 < 3s。

这个形态像 “serverless per-player per-tick invocation”。安全边界很好，但性能上有明显爆点：fork/cgroup/seccomp setup、Wasmtime Store/Instance 创建、memory mapping、module cache locality、Unix socket RPC、JSON snapshot copy，对 500 players × every 3s 非常敏感。

尤其 P0-4 §7 写“模块缓存按 `(module_hash, wasmtime_version)` 缓存”，但如果 worker 每 tick kill，缓存在哪里？父进程预编译 module 后 fork 子进程？长期 worker pool？如果是每 tick fresh process，JIT compiled artifact 和 loaded module 的复用边界必须写清楚。

建议 Phase 1 前补一页容量合同：

- `CompiledModuleCache` 位于 engine parent 还是 sandbox supervisor？
- per tick 是 fork 已预热 worker，还是 spawn 新进程？
- 目标玩家数下 collect fanout 的并发上限是多少？
- 每 player snapshot JSON 序列化预算是多少？
- `cpu.max = 250000 3000000` 与 `MAX_FUEL=10M` 的换算和冲突规则是什么？fuel 先到还是 wall-clock/cgroup 先到？
- 需要一个 microbenchmark gate：例如 500 no-op WASM players，snapshot 10KB，1000 tick，p99 collect < 2500ms。

### A6 — High — Auth/Certificate 模型过度复杂且存在 private key 语义不清

P0-3 §1.1 写 Auth Service “签发证书”，证书包含 `public_key`，并说 “服务端生成的临时密钥对”。部署时客户端附带证书 + 私钥签名 WASM bytes。

如果服务端生成 private key 再交给客户端：

- private key 传输与存储本身成为敏感面；
- 这基本退化为 bearer credential，PoP 的价值有限；
- 服务端既然知道 private key，就不能证明签名一定由客户端产生。

如果客户端生成 keypair，文档就写错了。

此外，MCP 网络层同时出现 OAuth2 JWT、mTLS、Ed25519 short-lived certificate、gateway cert validation、jti revocation。对 MVP 来说过重，且每层的职责边界不清。

建议：

- Phase 1/2 简化为 OAuth2 session/JWT + server-injected player_id + deployment audit。
- 若需要 proof-of-possession：客户端生成 keypair，服务端只签 public key；private key never leaves client。
- mTLS 只用于 service-to-service，不作为玩家/AI 客户端默认要求，除非明确运维模型。
- P0-3/P0-9 统一 token lifetime、cert lifetime、revocation source of truth。

### A7 — High — IDL 与 Command Validation Spec 已经分叉

P0-8 宣称 IDL 是 single source of truth，但 P0-2 已经有手写 validation matrix，且两者不完全一致或覆盖不同：

- P0-8 含 `global_storage_commands`，P0-2 没有逐指令校验矩阵。
- P0-8 `Harvest` 有 optional `resource`，P0-2 Harvest 示例没有。
- P0-8 `Transfer.cost` 写 `{ transfer_amount: amount }`，但 P0-2 说 transfer 只是资源检查，没有“cost”语义。
- P0-2 查询指令说 “不计每 tick 配额/每 tick 查询配额”，P0-4 又说 host function 计入 fuel；需要统一预算语言。
- P0-8 host_functions 里有 `get_world_rules`，P0-4 §3.2 列表只有 `host_get_world_config`，但 §8 成本表又出现 `host_get_world_rules`。

如果 IDL 真是权威，P0-2 不应手写另一份 authoritative matrix。建议改成：P0-2 只描述 pipeline 和 rejection semantics；具体 command schema/validator/cost/refund 全部引用 generated IDL artifact。

### A8 — Medium — Bevy `.chain()` 不等于完整 determinism contract

文档多处把 `.chain()` 当作确定性保证。`.chain()` 只保证 system order，不自动保证：

- Query iteration order 在 entity spawn/despawn 后跨版本稳定；
- HashMap/HashSet iteration 不参与 gameplay；
- floating point、SIMD、parallel iterator 不引入平台差异；
- Bevy/wasmtime/rhai 版本升级后的 replay stability；
- entity ID allocation 与 rollback restore 一致。

DESIGN §8.8 已经写了一些 contract（Blake3、禁 f64、IndexMap、禁 std::hash），这是正确方向。但需要把 Bevy-specific pitfalls 写入 P0-1 或单独 Determinism Spec，而不是只存在 DESIGN 正文里。

建议加 CI：同一 TickTrace 在 debug/release、不同机器、不同 seed shard 下 replay，state_checksum 必须一致。

### A9 — Medium — Tick abandon 的 fuel refund 语义可能被滥用或造成经济时间停滞

P0-1 规定 FDB commit fail → tick 放弃，state 不变，tick_counter 不递增，消耗 CPU fuel 退还玩家；连续 abandon 进入 degraded。这个是正确的原子性语义，但需要补充：

- 如果某玩家可诱导事务冲突或超大 write set，能否让全世界 tick 反复 abandon？
- abandon 后重试同一 tick，是否重新执行所有 WASM？如果重新执行，玩家代码可能因 host query、fuel refund、timeout 统计产生不同 observability。
- 如果不重新执行，而重用 collected commands，P0-1 应明确。

建议：EXECUTE commit fail 后重试应重用同一 `CollectedCommandSet`，不得重新调用 WASM；否则 replay/audit 复杂度上升。

### A10 — Medium — MCP `swarm_simulate` / dry-run 边界容易成为 oracle

P0-3 提供 `swarm_simulate`，P0-9 说 Simulate 是 snapshot-bound dry-run，World 5/tick、Arena 3/tick，budget 0.5× MAX_FUEL。方向可以，但还缺关键边界：

- simulate 能否调用 path_find beyond visibility？
- simulate 的 initial snapshot 是否 cryptographically tied to player-visible snapshot id？
- simulate 是否允许猜测隐藏敌人并通过结果差异探测？
- simulate 是否写审计和 rate limit per strategy/version？

如果 simulate 返回的 rejection/physics 差异包含隐藏状态，就会成为 side-channel。建议 P0-9 明确：simulation 只在 provided visible snapshot copy 上运行，隐藏实体不存在，不访问 authoritative world。

### A11 — Medium — Resource/global storage 设计过早进入 P0，但核心 Phase 1 不需要

DESIGN 与 P0-8 已包含全局存储、运输中、市场、Terminal、资源税、运输拦截、custom resources。它们很有设计价值，但 P0 冻结后会拖累 Phase 1 的实现面。

建议把 P0-8 的 `global_storage_commands` 标为 `phase: 3` 或移到 P1/P2 spec；Phase 1 IDL 只冻结 Move/Harvest/Build/Spawn/Transfer/Withdraw/Repair/Recycle 的最小闭环。否则 single source of truth 会迫使早期 SDK 暴露尚未实现的高级 API。

### A12 — Low — 文档状态标签不统一

示例：

- DESIGN §9 写 Phase 0 完成。
- ROADMAP Phase 1 依赖 P0 frozen。
- P0-1 状态是 “Phase 2 阻断项”，但 Phase 1 又依赖 P0-1。
- P0-6 是 “Phase 2 阻断项”，但 ROADMAP 把教程大头放 Phase 4。
- P0-7 是 “Phase 1 设计基础”，但 ROADMAP 把 Rhai 实现放 Phase 3。

这会让新人误判“现在必须实现什么”。建议统一每份 spec 的 frontmatter：`status`, `contract_phase`, `first_implementation_phase`, `blocking_for`。

## Missing

- WASM ABI spec：alloc/free/result pointer/length/error code/memory ownership。
- PersistenceAdapter 或最小 FDB Phase 1 决策。
- Sandbox capacity model and benchmark gates。
- RuleMod capability/action schema and validator。
- MCP visibility mode gate：World/Arena/Admin/Spectator/Replay 各 source 的最大可见性。
- Deployment/versioning contract：module_hash、version_tag、rollback、code propagation、Arena lock 的统一状态机。
- Determinism test matrix：debug/release、platform、Bevy version、Wasmtime version、Rhai version、replay checksum。
- Threat model：prompt injection、MCP oracle、spectator delay、simulate side-channel、deployment spam、transaction abandon griefing。
- IDL governance：哪些 command 是 Phase 1 stable，哪些是 future extension；generated artifact 的目录和 CI ownership。
- Error/rejection schema：P0-2 说 detail 是 machine-readable JSON，但示例是字符串；需要定型。

## Phase Ordering

建议按下面顺序重排近期工作：

1. R13.1 — P0 Contract Cleanup（1 周）
   - 修正 WASM ABI。
   - 决定 Phase 1 是否引入最小 FDB；若否，写 PersistenceAdapter。
   - 修正 P0-5 MCP full visibility 漏洞。
   - 统一 P0-8 与 P0-2 的 command schema 来源。

2. R13.2 — Minimal Vertical Slice Spec（1 周）
   - 明确 Phase 1 只实现单房间、单玩家、基础 5 指令、最小 replay。
   - 把 global storage、market、Rhai scripted mods、Arena、public replay 标为 later-phase extension。

3. Phase 1a — Deterministic Core
   - Bevy world + fixed system order + state_checksum。
   - Command validation generated from IDL。
   - TickTrace persisted using最终选定存储。
   - Replay CI 先过。

4. Phase 1b — WASM Sandbox
   - ABI、fuel、memory、timeout、host query functions。
   - 恶意 WASM corpus。
   - no-op/harvest bot 1000 tick soak test。

5. Phase 1c — Minimal MCP/Web deploy surface
   - `swarm_deploy`, `swarm_validate_module`, `swarm_get_snapshot`, `swarm_get_world_rules`。
   - 不做 gameplay action。
   - MCP visibility capped to player snapshot。

6. Phase 2 — Multiplayer only after benchmarks
   - seeded shuffle。
   - conflict/refund。
   - unified visibility across snapshot/MCP/WS/REST。
   - 3-player integration test before 500-player load test。

7. Phase 3+ — Persistence scaling, Rhai, global storage, market, Arena
   - 这些都依赖前面的 replay/fairness/sandbox 合同，不应倒置。

## Bottom Line

R13 的设计方向是对的，尤其是“AI 写 WASM，不通过 MCP 直接行动”这一点已经站稳。但现在最大风险是文档之间的合同不一致：实现者会各自选择解释，最后得到一个能跑但不可回放、不可公平审计、不可安全扩展的系统。

在进入代码实现前，先把 P0 当作 API contract 清理一轮。清理完成后，Swarm 的架构会非常有竞争力；不清理就进入 Phase 1，会在 WASM ABI、visibility oracle、tick persistence 这三个地方反复返工。
