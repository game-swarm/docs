# R27 Phase 1 Clean-Slate Review — Architect (GPT-5.5)

## Verdict

CONDITIONAL_APPROVE

架构主线是正确的：WASM-only 玩家模型、deferred command、Phase 2a inline + Phase 2b manifest、FDB 小事务 + object-store 大对象、API Registry 作为单事实源，这些都像是经历过多轮 review 后形成的可实现架构，而不是概念草图。当前不建议进入大规模实现冻结；应先修复若干“看起来只是文档问题、实现时会炸”的合同冲突，尤其是权威源边界、tick 失败语义、Phase 2b 调度一致性和容量扩展路径。

## Strengths

1. **单执行路径清晰**：`WasmSandboxExecutor` 是唯一玩家执行器，AI 与人类都通过 WASM 部署路径进入游戏，避免了 Screeps/agent 游戏常见的“AI 特权控制面”公平性破坏。

2. **权威源意识明显增强**：API Registry、Persistence Contract、Complete Tick Execution Manifest 分别承担 API、持久化、系统调度的权威合同角色，整体方向符合大型协议型系统的成功模式：机器可读源优先，Markdown 只做派生/引用。

3. **tick 生命周期已从概念走向工程合同**：COLLECT / EXECUTE / BROADCAST 分段、snapshot boundary、FDB commit retry、Bevy World restore、COLLECT buffer reuse 等关键时序都有明确叙述，说明设计已经覆盖了确定性引擎最容易遗漏的失败路径。

4. **沙箱设计选择务实**：long-lived worker pool + per-tick Store reset 是合理折中。fork-per-tick 虽然隔离更强，但在 500 active players 目标下不可行；当前方案像 Cloudflare Workers / Wasmtime embedding 的实用派路线。

5. **扩展路径有阶段感**：单事务 MVP、room-partition、未来水平分片被分层描述，避免了一开始就实现分布式世界模拟的过度设计。

6. **可观察性与回放意识强**：TickTrace envelope、manifest hash、system_manifest_hash、canonical codec version、visibility/truncation version 等字段使 replay verifier 有机会定位“代码变了但回放不一致”的根因。

## Concerns

### A1 — High — 文档内路径与权威源引用存在系统性错位，可能导致实现者读错规范

多个文件从新 docs layout 拆分后，仍存在相对路径不一致或指向未在当前子集中的旧文件。例如 `design/engine.md` 多处引用 `specs/core/06-phase2b-system-manifest.md`，但从 `design/engine.md` 所在目录看，应为 `../specs/core/06-phase2b-system-manifest.md`；`01-tick-protocol.md` 写 `../specs/core/09-snapshot-contract.md`，从 `specs/core/` 所在目录看会解析到 `specs/specs/core/09-snapshot-contract.md`；`tech-choices.md` 从 `design/` 引用 `specs/core/04-wasm-sandbox.md` 也同样少了 `../`。

这类问题看起来是 Markdown 链接小错，但对 Swarm 这种“文档即合同”的项目是架构风险：新人会打开错误路径、工具链校验会失效，后续 codegen/CI 链接检查也可能误判。更严重的是，某些“权威源”引用错位后，读者会转而复制当前文件中的旧表格，重新制造多事实源。

建议：在 R27 修复阶段加入 link-check gate，并明确所有规范文件使用相对路径规则；权威引用最好使用从 docs root 起的稳定路径或自动 lint。

### A2 — High — TickTrace / replay-critical / async object store 的终端状态语义仍然冲突

`05-persistence-contract.md` 明确把 replay-critical subset 放进 FDB，object store 的 rich trace 缺失只造成 `audit_gap`，不影响 deterministic replay。与此同时，`01-tick-protocol.md` 的旧段落仍写到 TickTrace 写入失败与 tick 执行在同一事务中、失败则 tick 放弃；后文又说 TickTrace delta chain 断裂会导致 replay verifier 从 keyframe 重建。

这三种模型分别是：

- 模型 A：TickTrace 完整体是 commit 前提，失败则 tick 不发生。
- 模型 B：replay-critical 在 FDB，rich blob 异步，失败只降级 audit。
- 模型 C：delta chain / keyframe 可从对象存储恢复世界状态。

它们不能同时成立。当前设计试图用术语区分 `TickTrace`、`tick_trace_blob`、`replay-critical subset`，但在文件间仍混用，会让实现者不清楚：到底哪些字段必须在 FDB 小事务内，哪些缺失会使 replay 不可用，哪些只影响 debug。

建议：把术语收敛为三层：`TickCommitRecord`（FDB 必选）、`RichTraceBlob`（object store 可缺失）、`ReplayArtifact`（可重建/可丢弃）。其他文档禁止再用裸 `TickTrace` 表示三者之一。

### A3 — High — Phase 2b 特殊攻击调度仍有内部矛盾，实际实现会产生双写或顺序误解

`06-phase2b-system-manifest.md` 宣称所有特殊攻击状态由 S22 `status_advance_system` 统一推进，并列出 Unique Writer Contract；但同一文件的 S16-S22 表又把 `hack_system`、`drain_system`、`overload_system` 等写成各自 `Writes StatusState`，还把它们放在 Parallel Set B 与 S22 并列。`02-command-validation.md` §3.19 进一步说 `status_advance_system` 调度位置在 combat 之后、regeneration 之前，并给出 `death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup`，这又与 manifest 的 S10 regeneration 在 combat 前、S14/S15/S22 在其后冲突。

这是典型“图修好了，细节表没同步”的危险模式。实现阶段如果不同工程师分别照 schedule 图、R/W matrix、特殊攻击小节编码，最终会出现：

- `StatusState` 多 writer，Bevy schedule 无法安全并行或行为非确定；
- regeneration 与 damage/status 的顺序不一致，影响 replay；
- special attack reducer 到 status advance 的数据流边界不清。

建议：保留一种模型。若 S22 是唯一 writer，则 S16-S21 应改为“intent interpreter / validator / no state write”或直接删除为逻辑子步骤；R/W matrix 必须让 S16-S21 不写 `StatusState`。同时以 manifest schedule 为唯一顺序，删除 `02-command-validation.md` 的旧时序代码块。

### A4 — Medium — CommandAction / RejectionReason 注册表与校验矩阵仍有残留旧码，违反“wire enum 稳定”目标

API Registry 声明 canonical `RejectionReason` 共 47 个，并明确 `Fatigued`、`NotMovable`、`SourceEmpty`、`TargetFull` 等旧码进入 `debug_detail`，不再是 wire enum。但是 `02-command-validation.md` 的表格仍出现 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated(damage_type)`、`MainActionQuotaExceeded` 等非 registry canonical code。

文档在 §3 开头提醒“以下错误码为说明性名称”，但后续 §5.1 又把 `MainActionQuotaExceeded` 放入拒绝码表，§6/字段级表也继续混用。对新人和 SDK/codegen 实现者来说，这会导致最坏结果：客户端 SDK 暴露了不存在的 wire enum，或者服务端为了满足文档而扩展 enum，破坏 API Registry 的单事实源。

建议：所有校验矩阵的“失败码”列改为两列：`canonical_code` 与 `debug_detail.example`。凡不在 API Registry 的名称，只能出现在 debug_detail 示例中，不得以 code 形式出现。

### A5 — Medium — 容量目标与单节点/room-partition/FDB 事务策略的 phase gate 还不够硬

`engine.md` 宣称 target 500 / hard cap 1000 active players，`05-persistence-contract.md` 又说单事务 MVP 只适用于 ≤50 active players / ≤100 rooms，500+ 必须 room-partition。这个分层是对的，但目前 architecture README 和容量合同仍容易让人误以为 MVP 单实例 + FDB 单一提交即可支撑 500 active players。

已知失败案例是“先写单事务世界，后补分区”：一旦 gameplay、TickTrace、snapshot、cross-room movement 都围绕单事务抽象写死，后续 room partition 会变成重构数据库模型和执行模型，而不是扩展。当前设计虽提到 2PC 和 per-room transaction，但没有把“哪些接口从第一天必须携带 room/shard partition key”列为硬 gate。

建议：把实现 phase 明确拆成：

- Phase 1 MVP：≤50 players，单事务，容量文案不得宣称 500 可用；
- Phase 1.5 Partition Readiness：所有 entity id、command sort key、TickCommitRecord、snapshot shard 都携带 room/shard key；
- Phase 2：room-partition commit + cross-room 2PC benchmark 通过后，才恢复 500/1000 容量声明。

### A6 — Medium — FDB commit retry + in-memory Bevy restore 的成本与正确性风险被低估

设计要求 Phase 2a 前对完整 Bevy World 做深拷贝，commit 失败时 `world.restore(snapshot)`，并在 CI 中验证所有 component/resource 恢复一致。这个合同正确，但工程风险很高：Bevy ECS 的 world clone/restore 对 entity allocator、archetype layout、resource interior mutability、deferred commands、pending entity flush 都非常敏感。

`05-persistence-contract.md` benchmark 只要求 “Rollback Bevy snapshot/restore 500 entities p99 < 50ms”，而 `engine.md` 容量合同写 total entities hard cap 50,000。这里的 benchmark gate 与容量目标不在同一个数量级。若 50k entities 下 snapshot restore 不成立，FDB retry 语义会在高负载时变成 tick abandon 放大器。

建议：把 restore benchmark 对齐容量目标：至少覆盖 50k entities、所有 component 类型、pending create/despawn、RoomCap 中间态、ResourceLedger 变更、entity id allocator。若 full clone 太贵，应提前设计 command journal / inverse operation rollback，而不是实现后再替换。

## Missing

1. **权威术语表**：缺少一个全局 glossary 定义 `TickTrace`、`TickCommitRecord`、`RichTraceBlob`、`CommandIntent`、`RawCommand`、`ValidatedCommand`、`deploy_mutation`、`terminal_state` 等术语的唯一含义。

2. **链接与权威源 CI**：缺少文档链接校验、禁止非权威表格重列、API Registry enum 引用校验、manifest system count 校验的统一 doc-lint 说明。

3. **Partition-readiness checklist**：缺少“即使 MVP 单事务，哪些数据结构必须从第一天携带 room/shard key”的清单。

4. **Bevy rollback ADR**：需要一份 ADR 比较 full world clone、command journal、double-buffer world、FDB-first apply 四种 rollback 方案，并给出选择理由与 benchmark gate。

5. **Phase 2b 机器可读 manifest**：Markdown manifest 已经很详细，但真正防 drift 应该有 YAML/TOML manifest，代码注册与文档都由它生成。

## CrossCheck — 需要跨方向检查

- CX1: WASM sandbox 的 seccomp/cgroup/namespace 组合是否足以覆盖 Wasmtime JIT、epoch interruption、precompiled module cache 的真实 syscall 行为 → 建议 Security 检查 forbidden syscall 列表与 Wasmtime 30 实际运行依赖，尤其 `clone` 在上文一处允许、一处禁止的差异。

- CX2: `NotVisibleOrNotFound`、debug_detail detail_level、admin trace/player trace 的信息分层是否会泄露 fog-of-war oracle → 建议 Security 检查错误码优先级、MCP debug tools、training/practice 模式是否可能跨竞技世界误启用。

- CX3: 500/1000 active players 的 snapshot stitching、worker pool、FDB room-partition、pathfinding fair-share 是否在同一硬件基线上可达 → 建议 Performance 检查容量公式、benchmark gate 与 64GB/32 cores 假设的一致性。

- CX4: `Move = Action`、单 action slot、Transfer/Withdraw 不计 main action、特殊攻击全量解锁是否对新手可理解 → 建议 Designer 检查学习曲线与 SDK/tutorial 分层。

- CX5: API Registry generated-from-IDL 的流程是否已有真实 generator 与 CI `--check`，以及 Markdown 中旧码是否会污染 SDK → 建议 API/DX 检查 IDL → Registry → SDK 的单向生成链。

- CX6: world_seed 轮换承认未来可预测窗口，与 Arena 公平性是否冲突 → 建议 Determinism/Security 联合检查 seed 泄露后的 replay、rollback、公告与赛季处理策略。

## Phase Ordering

1. **先做文档合同清扫**：修复相对路径、删除旧错误码、统一 TickTrace 术语、统一 Phase 2b 调度。这个阶段不应写引擎代码，因为当前合同仍会让不同实现者写出不同系统。

2. **建立机器可读权威源**：把 Phase 2b manifest、RejectionReason mapping、capacity limits、persistence replay-critical fields 做成可 lint 的 YAML/IDL，Markdown 从中生成或至少被 CI 校验。

3. **实现最小单事务 MVP**：限制 ≤50 active players，验证 WASM sandbox、deferred command、single tick commit、replay checksum、Bevy rollback。此阶段不要宣传 500-player capacity。

4. **做 partition-readiness refactor gate**：在 entity id、command key、snapshot shard、TickCommitRecord 中落 room/shard key，哪怕底层仍单事务。

5. **再实现 room-partition commit**：通过 cross-room movement/transfer/claim 的 2PC 或等价协议，以及 500/1000-player synthetic benchmark 后，才把容量声明提升为产品承诺。

6. **最后开放复杂 gameplay surface**：特殊攻击全量、global storage、alliance transfer、advanced debug tools 应在核心 tick/replay/partition 稳定后逐步启用，避免在基础时序未定时叠加复杂状态机。
