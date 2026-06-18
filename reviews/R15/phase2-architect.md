# R15 Phase 2 CrossCheck — Architect 补充阅读

范围：仅补充阅读 `rev-gpt-apidx`、`rev-dsv4-apidx`、`rev-gpt-economy`、`rev-gpt-determinism`、`rev-dsv4-performance`、`rev-gpt-security` 的 CrossCheck 指向段落，并核对相关 specs。未重跑完整架构评审。

## CrossCheck item -> Finding -> disposition

### CX-A1: CommandAction / CustomActionRegistry 边界与 replay determinism

Finding:
- `specs/gameplay/08-api-idl.md` 已给出正确方向：Core IDL 是基础 envelope / host functions / 内置指令的单一真相，World Action Manifest 负责 `custom_actions` / `special_effects`，并用 canonical hash 绑定 TickTrace 与 WASM `target_manifest_hash`。
- 但同一文件仍把特殊攻击列表、动态注册链路、IDL 扫描注册表混在一个 spec 内。API/DX 指出的 Command 数量、Tier 2 action、字段命名、错误命名不一致，说明“Core enum 固化 vs registry 动态派发”的边界还没有变成可执行约束。
- 架构上最危险的不是动态扩展本身，而是 replay 没有明确记录“本 tick 使用的 action manifest hash + validator version + generated schema version”。如果 replay 只记录 Command JSON，而不绑定当时 registry，后续 world.toml / RuleMod / handler 变更会让同一 TickTrace 复放出不同状态。

Disposition: high

Required close condition:
- 冻结 Core CommandAction 最小集合；所有 Vanilla special/custom action 必须从 World Action Manifest 生成，不得手写散落表格。
- TickTrace / replay envelope 必须记录 `core_idl_version`、`world_action_manifest_hash`、`validator_version`、`rejection_reason_registry_version`。
- CI 必须证明 Rust/TS/MCP/Replay schema 全部由同一 IDL+manifest 生成，禁止手写 Command 变体或错误码。

### CX-A2: FDB 单事务、TickTrace/WAL、对象存储分层是否架构自洽

Finding:
- `specs/core/02-command-validation.md` 写明应用修改在 FDB 事务内完成，并随后记录 TickTrace；多份评审同时指出 TickTrace/WAL 与 FDB 同事务语义、事务大小、rollback、对象存储大 blob 分层没有闭合。
- 当前能确认“单一管线”和“事务内 apply”的意图，但没有看到足够明确的持久化形态：哪些小对象进 FDB、哪些大 blob 进对象存储、对象存储写入失败如何影响 FDB commit、TickTrace 是事务内行、WAL append，还是 hash pointer。
- 这是典型“看起来原子，实际上跨存储双写会炸”的模式。若 FDB commit 成功但 TickTrace blob / replay artifact 失败，审计完整性断裂；若 blob 先写成功但 FDB commit 回滚，会留下孤儿对象；若把完整 TickTrace 放进单 FDB 事务，又会触发事务大小和热点风险。

Disposition: blocker

Required close condition:
- 发布 Persistence Contract：FDB 只提交 tick head / state checksum / small manifest / object pointer / content hash；大 TickTrace、snapshot delta、replay blob 进入对象存储或日志层。
- 定义双写顺序、幂等 key、GC 规则、orphan recovery、commit retry 对 TickTrace hash chain 的影响。
- replay verifier 输入必须以 FDB commit 的 manifest/hash 为权威，而不是重新扫描对象存储最新内容。

### CX-A3: Allied transfer / PvE budget / ResourceAmount 定点 schema 的唯一权威入口

Finding:
- `ResourceAmount: u32`、`TransferToGlobal` / `TransferFromGlobal` 和 `transfer_to_global_cost() * amount` 已出现在 `08-api-idl.md`，但 Economy CrossCheck 指出的 `0.01` 费率、refund `0.5`、PvE cap、allied direct transfer 仍把整数资源、定点费率、账本预算混在文本和示例里。
- 如果 allied direct transfer 与 Global/Local transfer 不是同一个 Resource Ledger 入口，它会绕过损耗、运输时间、存储税、new player lock、same-origin quota。该风险与 Speaker B7 完全同源。
- PvE drop budget 也不能只是一条“≤世界再生 30%”说明；它需要 global / zone / player / event window ledger，并在 deterministic apply 阶段扣减，否则 NPC spawn/drop/Rhai event 会形成多个 faucet 入口。

Disposition: blocker

Required close condition:
- 建立唯一 Resource Ledger / Transfer Gateway：local transfer、global transfer、allied transfer、market/merchant/RFC 入口、PvE award 全部经同一账本 API 和 TickTrace attribution。
- 所有小数费率改为 basis points / ppm 等定点 schema；`ResourceAmount` 保持整数，`ResourceRate` / `FeeBps` 独立建模。
- PvE budget 写成确定性账本：global、zone、player、event window 维度，扣减发生在同一 apply 顺序中，并记录到 TickTrace。

### CX-A4: WASM worker pool、sandbox reset、engine-sandbox IPC 容量

Finding:
- `04-wasm-sandbox.md` 清楚说明 long-lived worker pool + per-tick Store reset，gRPC over Unix socket，缓存编译模块，重建 Instance，清空线性内存、fuel、epoch deadline。这是现实的性能取舍，优于 fork-per-tick。
- 但 CrossCheck 指出的残留状态问题仍成立：Store/Instance/Memory/Linker/Engine/Module/HostContext/HostCallCounters/cache 的生命周期边界没有表格化；reset 失败/OOM 后 worker 是否销毁、health check 如何证明清洁、host-side per-player state 是否清空仍不够硬。
- Performance 指出的 IPC 容量也未闭合：500 worker、256KB snapshot、command JSON/protobuf、host function 频繁调用，经 Unix socket + gRPC 的延迟/吞吐没有 benchmark 或 admission contract。尤其 host_get_terrain 等低 fuel host call 若缺 per-tick 次数上限，会把 fuel 模型转化为 engine-side IPC DoS。

Disposition: high

Required close condition:
- 新增 Sandbox Lifecycle Matrix：Engine/Module 可复用；Store/Instance/Memory/CallerContext/HostCallCounters 必须 per invocation 新建；任何 reset 异常销毁 worker，不回池。
- 新增 worker health check 与跨 tick residue CI：恶意模块后同 worker 执行干净模块，证明无 memory/global/table/host context 残留。
- 新增 IPC capacity contract：snapshot 大小、host call 数、gRPC payload、worker 并发、p99 latency、backpressure/admission policy；所有 host function 都必须有 per-tick call cap 或 global budget。

### CX-A5: admin 命令是否全部走 validate_and_apply 且不可绕过审计

Finding:
- 这一项在文档层面比其他项更接近关闭。`02-command-validation.md` 明确“所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一 校验→应用 路径”，`09-command-source.md` 进一步声明 Admin 走标准 `validate_and_apply()`，仅所有权/RejectionReason 阈值放宽，并由 `WorldMutate` trait 限制绕过。
- 仍需注意：这目前是设计断言，不是实现可验证合同。`RuleMod`、Rollback、TestHarness、Admin global storage mutation、world owner override 都在 source matrix 中拥有写能力；如果这些路径拿到 `&mut World` 或 FDB write handle，就会绕开审计。
- 因此不是 blocker，但必须成为实现前的架构门禁：trait/sealed module、lint、integration test 和 audit sink 必须证明“所有世界状态修改都产生 CommandSource + TickTrace/audit row”。

Disposition: medium

Required close condition:
- `WorldMutate` / `ApplyContext` 采用 sealed trait 或 crate-private constructor，只有 validation/apply 模块可创建。
- Admin、Rollback、RuleMod、TestHarness 的所有写操作必须生成统一 `CommandSource` / `AuditContext`，并进入 TickTrace 或安全审计日志。
- CI 增加绕过检测：禁止非 apply 模块持有 `&mut World` / FDB mutation capability；测试 admin 修改会产生完整 audit trail。

## Consolidated disposition

- close: 无。所有指向 Architect 的 CrossCheck 都至少需要文档或实现门禁补强。
- medium: CX-A5 admin `validate_and_apply` 管线，文档已有清晰方向，但缺实现级不可绕过证明。
- high: CX-A1 CommandAction/CustomActionRegistry；CX-A4 sandbox worker lifecycle / IPC capacity。
- blocker: CX-A2 FDB/TickTrace/WAL/object-store persistence；CX-A3 Resource Ledger / allied transfer / PvE budget / fixed-point schema。

## Phase Ordering

1. 先冻结 API/IDL 与 manifest 权威入口：Core CommandAction、World Action Manifest、RejectionReason、ResourceAmount/Rate schema、generated artifacts。
2. 再冻结 Persistence Contract：FDB head、TickTrace/WAL、object-store blob、hash chain、rollback/retry/GC。
3. 再冻结 Resource Ledger：allied/global/local/PvE 全部统一入口与定点费率。
4. 再冻结 Sandbox Lifecycle + IPC Budget：worker reset、host context、health check、capacity benchmark、host call caps。
5. 最后才实现 Admin/RuleMod/TestHarness 写路径，并用 trait/lint/test 证明不可绕过 validate_and_apply 与审计。
