# R4 Clean-Slate Architect Review — rev-dsv4-architect

> **评审视角**: 系统架构、模块划分、数据流、边界定义、扩展性
> **评审人**: rev-dsv4-architect (DeepSeek V4 Pro)
> **日期**: 2026-06-16
> **文档**: DESIGN.md + 9 specs + tech-choices.md + ROADMAP.md (12 份，clean-slate)

---

## Verdict: CONDITIONAL_APPROVE

架构设计整体出色：ECS 确定性调度、三层扩展模型、FDB 原子提交、Wasmtime fuel metering、Blake3 单原语策略、IDL 驱动代码生成——这些核心决策展现了极高的架构纪律。

以下 4 个关注点需要在进入实现前澄清/修正（D1–D2 为文档精确性问题，D3–D4 为语义缺口），但不构成架构返工。5 个一致性缺口 (CG1–CG5) 需跨文档对齐。

---

## Strengths (亮点)

### S1. ECS 确定性调度 + 种子洗牌
Phase 2a/2b 分离（inline 命令 vs deferred systems）、`.chain()` 串行化、Blake3 XOF 种子洗牌、RW 矩阵——构成了清晰的确定性合同。先到先得 + 随机轮换的公平性模型简洁且可验证。

### S2. 三层扩展模型 (Core/Declarative/Experimental)
Layer 1 (IDL 冻结) → Layer 2 (world.toml 调参) → Layer 3 (模组世界) 的分层设计精准捕获了扩展需求的谱系。90% 的定制需求通过 Layer 2 解决，无需触动 SDK。manifest_hash 机制优雅地处理了 WASM 模块与世界的兼容性校验。

### S3. FDB 原子提交 + Bevy World 快照恢复
每 tick 包裹在单一 FDB 事务中，全或无。FDB 失败时通过 Bevy World 内存快照恢复——不是简单的「重试」，而是状态级回滚。快照范围清单（所有 Resource + Component）详尽完整。FDB 故障注入 CI 测试进一步加固了此路径。

### S4. Blake3 单原语策略
哈希、PRNG (XOF)、代码签名 (MAC) 统一为 Blake3——减少了依赖面、审计面、和跨平台退化风险。`blake3::Hasher::update_with_seek(seed, offset)` 替代整个 ChaCha keystream 管理。这是教科级别的密码学工程决策。

### S5. MCP Transport 拆分 (Browser vs Agent)
MCP 网络架构按客户端环境明确分为 Browser（Origin/CSRF/Sec-Fetch）和 Agent（mTLS/Ed25519 签名）两条路径，DNS rebinding 防御覆盖 6 个攻击向量，Token audience 绑定 transport 类型。这是安全架构的标杆实践。

### S6. 两阶段快照架构
从「每玩家独立序列化」(O(P×E)) 优化为「一次性构建 + 按房间分片拼接」(O(E + P×visible_rooms))，消除重复序列化开销。256KB 快照截断 + 分桶权重策略保证了资源边界。

### S7. Keyframe + Delta 存储
每 K tick 存储完整快照 + 中间 delta，整体存储减少约 90%。回放时定位最近 keyframe → 重放 delta 链——兼顾完整性和效率。

### S8. 指令管线单一入口
所有来源（WASM/MCP/Admin/REST/CLI）走同一 `校验→应用` 路径。CommandIntent → RawCommand → ValidatedCommand 的三级表示从不可信输入逐级升级为可信指令。Source Gate 服务端注入身份，客户端不可自报。

### S9. 世界级可配置性
资源类型、身体部件、建筑类型、伤害类型、特殊攻击——全部通过 world.toml 声明式定义。引擎核心只提供 validation + execution pipeline，不硬编码任何游戏内容。这不是「可配置的游戏」，而是「游戏引擎平台」。

### S10. 全面失败语义
Tick 失败矩阵覆盖 12 个故障点，每个故障点明确定义了对世界状态、玩家影响、和恢复策略的影响。降级模式（3 次连续 abandon → join_lock + 暂停部署 → 10 tick 正常自动恢复）给出了清晰的运维合同。

---

## Concerns (关注点)

### D1. Bevy World 快照实现复杂度 — Medium

**发现**: specs/01 §3.5 定义了 Bevy World 的快照/恢复机制，列出了必须捕获的 7 个 Resource 类型和 12 个 Component 类别。但 Bevy ECS 不提供内置的「深拷贝整个 World」API——这需要自定义实现。

**分析**: 
- Bevy 的 `World` 没有 `Clone` derive。快照需要遍历所有 archetypes、逐个复制 component 数据、并重建 entity 映射。
- 快照中的 `RNGState`（Blake3 XOF 内部状态）特别敏感——必须精确捕获 XOF 的内部计数器/缓冲区，否则 restore 后随机序列会分叉。
- 快照构建必须在 Phase 2a 前完成，其耗时计入 tick 时间预算。对于 500 活跃玩家、数万实体的世界，全量深拷贝的 wall-clock 成本需要基准测试。

**建议**: 
1. 在 MVP 前对 snapshot/restore 做独立基准测试（1000 实体、10000 实体、50000 实体规模）。
2. `RNGState` 的捕获需要 Blake3 XOF 暴露内部状态 API——验证 `blake3::Hasher` 是否支持此操作，或改用 seed+offset 模式重建。
3. 考虑增量快照：仅拷贝 Phase 2a 会修改的 component（Position/HitPoints/Fatigue/Energy/Cooldown/Owner/DeathMark/RoomCap），而非全量深拷贝。静态数据（Terrain/StructureType/WorldConfig）不需要快照。

### D2. Phase 2b RW 矩阵精度 — Medium

**发现**: specs/01 §3.4 的 Component/Resource 读写矩阵声明 `regeneration` (W: Energy/Carry) 和 `spawn` (W: Energy/Carry) 可以并行执行。矩阵未区分 entity archetype。

**分析**:
- 如果 `regeneration` 操作 Source 实体、`spawn` 操作新 Drone 实体，它们访问不同的 archetype——Bevy 的调度器确实可以并行执行。
- 但如果某个资源点系统的实现意外触及了 Drone/Spawn 上的 Energy/Carry（例如 spawn 从 Source 扣除能量），则存在数据竞争。
- 矩阵应该标注「操作哪些 archetype」，而非仅标注「写入哪些 component」。当前矩阵对系统间交互的推理不够精确。

**建议**: 
1. 在 RW 矩阵中增加「操作实体类型」列：
   - `regeneration`: 仅 `Source` archetype
   - `decay`: 仅 `Drone` archetype  
   - `spawn`: `Drone` + `Spawn` archetype（新 drone 和扣能量的 spawn）
2. 增加集成测试：启用 Bevy 的 ambiguity detection (`app.add_plugins(bevy::ecs::schedule::ReportExecutionOrderAmbiguities)`) 验证调度图无冲突。
3. 这不是实现错误（Bevy 调度器会正确处理），但文档精度不足可能导致未来系统扩展时引入真正的数据竞争。

### D3. Rhai 执行模型矛盾 — Medium

**发现**: specs/07 §5.1 描述 Rhai 运行于「独立 sandbox 进程，通过 IPC 与核心引擎通信」，描述了 seccomp/cgroup 加固。但 DESIGN.md §8.7 明确写「Rhai 模组在引擎进程内运行——服主安装的模组是受信代码。不引入进程隔离的复杂性和性能开销。」

**分析**:
- 两份文档对 Rhai 的隔离级别存在根本性矛盾：一个是进程隔离（specs/07），一个是进程内（DESIGN.md）。
- specs/07 的 `[rhai] isolation = "inprocess"` 配置暗示进程外是默认——但 DESIGN.md 明确否定了进程隔离。
- 这影响安全模型：如果 Rhai 模组进程内运行，一个恶意模组可以 panic 整个引擎（比进程隔离更危险）。

**建议**: 
1. 明确决策：Rhai 默认进程内还是进程外？如果进程内，删除 specs/07 中的 seccomp/cgroup/进程隔离描述，保留 AST 节点预算 + 能力白名单作为主要安全边界。同时加强 `mods.lock` pinning 和 Ed25519 签名验证作为补偿控制。
2. 如果保留进程外选项（远期扩展），标记为「计划中，非 MVP」，避免混淆。

### D4. Overload 可见性检查的实体引用语义 — Medium

**发现**: specs/02 §3.12 和 DESIGN.md §8.2 中，Overload 的 target 是 `player_id`（非 entity_id），但校验规则要求「`is_visible_to(target_player, attacker)`」。`is_visible_to` 的函数签名是 `fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool`——它接受 entity，不接受 player_id。

**分析**:
- Overload 的语义是「攻击玩家」，而非「攻击实体」。但可见性检查是基于实体的——需要将 `player_id` 映射到一个或多个可见实体。
- 可能的解析：如果 attacker 能看到 target_player 的任意一个 entity，则 target_player「可见」。但这引入了模糊性——应该基于 target_player 的 Controller/Spawn 还是任意 drone？
- specs/05 定义了 `is_visible_to` 为 entity 级别函数，没有 `is_player_visible_to` 的变体。

**建议**: 
1. 定义 `is_player_visible_to(target_player: PlayerId, observer: PlayerId) -> bool`——当 observer 在 target_player 拥有的任意房间有视野时返回 true。
2. 在 specs/05 中补充此函数定义。
3. 或者改为：Overload 要求 attacker 能看到 target_player 的 Controller 或任意 drone（取最宽松的）——并在校验规则中明确引用此语义。

---

## Consistency Gaps (跨文档对齐缺口)

### CG1. Controller 维修硬上限公式精度 — specs/01 vs DESIGN.md
- DESIGN.md §8.2: `max(0, age + 1 - min(0.5, controller_count * 0.5))` 使用浮点语义
- Determinism Contract §8.8: "禁 f64，整数 + 定点数"
- **问题**: 公式中的 0.5 在整数域无意义。需要改为 `max(0, age + 1 - min(FIXED_HALF, controller_count * FIXED_HALF))` 并定义定点精度。
- **影响**: 实现时如果不统一精度，跨平台回放可能产生不同结果。

### CG2. Phase 2b 系统注册顺序 — specs/01 §3.4 vs specs/07 §3
- specs/01 §3.4 的主线顺序: `death_mark → spawn → combat → (regeneration/decay 并行) → death_cleanup`
- specs/07 §3 中 `register_systems()` 的顺序: `death_mark → spawn → regeneration → combat → decay → death_cleanup` (全 `.chain()`)
- **问题**: specs/07 将 regeneration 放在 combat 之前，而 specs/01 让两者并行。specs/07 的 `.chain()` 写法使 regeneration 必须在 combat 前完成——如果 regeneration 和 combat 确实无依赖，这不正确。但如果 regeneration 的结果（再生后的资源量）需要被 combat 后的 decay 使用，则顺序重要。
- **建议**: 统一两个文档的 ECS 调度顺序，或明确注明 specs/07 是伪代码/示例（非精确调度配置）。

### CG3. Fortify per-target 冷却一致性 — specs/02 §3.15 vs DESIGN.md §8.2
- specs/02 §3.15: Fortify 有 per-target 冷却（同一 target 过去 300 tick 内被 Fortify → `TargetFortifyCooldown`）。同时 Fortify 效果「不可刷新」。
- DESIGN.md §8.2 的特殊攻击表中 Fortify: 冷却 300 tick，但未提及 per-target 冷却。
- **问题**: 这是两个独立的冷却维度（drone 冷却 + target 冷却），还是同一个冷却？如果 Fortify 了目标 A，300 tick 内同一 drone 不能 Fortify 任何人（drone 冷却），同时目标 A 也不能被任何人 Fortify（target 冷却）？DESIGN.md 未说明第二个维度。
- **建议**: 在 DESIGN.md 的特殊攻击表中补充 per-target 冷却说明。

### CG4. COLLECT 缓存中 fuel 扣费来源 — specs/01 §3.5 vs specs/04 §6
- specs/01 §3.5: "首次 COLLECT 时缓存 `Map<PlayerId, Vec<RawCommand>>` + fuel 扣费明细"
- specs/04 §6: fuel metering 在 Wasmtime Store 层通过 `get_fuel()` 轮询实现——引擎在 tick() 返回后读取消耗的 fuel。
- **问题**: specs/04 描述的是 Wasmtime 内部的 fuel 消耗记录，specs/01 说的是缓存这个记录。但「fuel 扣费明细」的精确内容未定义——是 consumed_fuel: u64 还是包含分项（host function 调用各多少 fuel）？跨重试的「fuel 消耗上限 = 1 × MAX_FUEL」意味着缓存的是总消耗量。但 Wasmtime 的 fuel 是消费性的（Store 内递减），重试时不重新执行 WASM 就不会产生新的 fuel 消费——这个语义需要更明确。
- **建议**: 在 specs/01 §3.5 明确「fuel 扣费明细 = consumed_fuel: u64（单次执行总消耗）」，并说明重试时此值不再变化。

### CG5. Arena `simulate` 配额差异 — specs/04 §6.1 vs specs/09 §2.4
- specs/04 §6.1: MCP simulate 限制为 World 5/tick，未区分 Arena。
- specs/09 §2.4 来源矩阵: Simulate 在 Arena 中为 10/tick（"Arena 对模拟需求更高"）。
- **问题**: 两份文档对 Arena 的 simulate 配额不一致（specs/04 未提及 Arena 的特殊配额）。
- **建议**: 在 specs/04 §6.1 的 MCP Simulate 限制表中增加 Arena 行（10/tick），或改为「World: 5/tick, Arena: 10/tick」。

---

## Algorithmic Risks (算法风险)

### AR1. 种子洗牌的可预测性窗口
- 每 10,000 tick 轮换 `world_seed`。但 10,000 tick × 3s = 约 8.3 小时。在这 8 小时内，如果玩家能观察足够多的 tick 排序结果并逆向 Blake3（不可行）或通过侧信道推断位置（可能），公平性会受损。
- **缓解**: 10,000 tick 的轮换窗口对于当前安全参数是足够的（Blake3 256-bit 不可逆）。但需监控是否有玩家利用多个 drone slot 在单个 tick 内进行排列推断。

### AR2. 快照 256KB 截断的确定性
- 快照截断策略是「按分桶权重 + 同桶内距离优先」。如果两个实体距离相同（等距），截断结果可能依赖于 iteration order。
- `IndexMap` 保证迭代顺序确定——但如果实体插入顺序在不同运行中不同（例如由于并发 sandbox 执行完成顺序不同），截断结果可能非确定。
- **缓解**: 快照构建在 COLLECT 阶段一次性完成，此时 Bevy World 状态已确定。但需要验证 IndexMap 的插入顺序是否在所有代码路径中一致。

### AR3. path_find 缓存键中的 `player_visibility_fingerprint`
- specs/04 §8 定义 path_find 缓存键包含 `(from, to, terrain_hash, player_visibility_fingerprint)`。
- `player_visibility_fingerprint` 未在文档中定义。如果它是对玩家可见实体的 hash，则大多数查询的 fingerprint 不同 → 缓存命中率极低 → 退化为每查询重算。
- **建议**: 明确 fingerprint 的粒度。如果基于「玩家在哪些房间有视野」计算，粒度更粗但命中率更高。

---

## Data Flow Verification (数据流验证)

### FDB + Dragonfly 读写一致性

权威链: `Bevy World (内存工作副本) → FDB commit → Dragonfly update`

已验证:
- EXECUTE 阶段在 Bevy World 上原地修改，FDB 事务提交成功后 Dragonfly 更新缓存。DESIGN.md §3.2 和 specs/01 §3.5、§4.2 的描述一致。
- BROADCAST 失败不影响已提交 tick——FDB 为权威源，Dragonfly/NATS 为非权威。客户端通过 `last_tick` gap 检测主动 fetch。正确。
- COLLECT 阶段从 Bevy World 读取（内存），不访问 FDB/Dragonfly。正确。
- MCP_Query 不得直接读 FDB（绕过可见性过滤）——specs/01 §6.4 明确约束。正确。

未发现问题。

### Tick 生命周期完整性

已验证:
- COLLECT → EXECUTE (2a → 2b → FDB commit) → BROADCAST。状态机完整。
- 快照构建在 COLLECT 开始时一次性完成，WASM 执行期间不变化。正确。
- Phase 2a Spawn 只校验不入队，Phase 2b spawn_system 统一创建。TOCTOU 保护完整。
- Phase 2b 中 death_mark 释放 room cap → spawn 创建新 drone → combat 结算。顺序合理。
- 新 spawn drone 参与同 tick combat/decay——有意设计（「出生即投入战斗」），非错误。已记录。

---

## Scalability Analysis (扩展性分析)

### 垂直扩展路径
- 单 Engine 实例目标 500 活跃玩家。3s tick 中 2500ms COLLECT + 500ms EXECUTE 的分配合理。
- WASM 预编译消除 JIT 延迟，per-tick 仅实例化——这是正确的性能优化。
- 两阶段快照从 O(P×E) 降为 O(E + P×visible_rooms)：500 玩家 × 9 房间分片拼接——可行。

### 水平扩展路径
- 联邦宇宙模型（每 Engine 一个世界实例）避免了跨分片实时同步的复杂性。
- 跨世界异步交互（资产转移、共享排名）边界清晰，不侵入实时游戏循环。
- 数据模型（FDB key 结构）预留了 `/world/{id}/...` 前缀，为未来分片扩展留下空间。

### 模块化边界
- `engine/` (Rust 核心) ↔ `sandbox/` (WASM 运行时) 通过 gRPC (Unix socket) 通信——进程边界清晰。
- `gateway/` (Go) ↔ `engine/` 通过 gRPC + NATS——语言边界清晰。
- SDK 通过 IDL 自动生成——API 边界清晰且可验证 (CI 中 `git diff --exit-code`)。
- Rhai 模组通过 `actions.*` API 访问世界——能力白名单提供了明确的扩展边界。

---

## Summary

| 维度 | 评估 |
|------|------|
| 架构完整性 | ✅ 优秀 — ECS + Tick + FDB 三层形成清晰的确定性合同 |
| 模块划分 | ✅ 优秀 — engine/sandbox/gateway/frontend/SDK 边界分明 |
| 数据流 | ✅ 正确 — FDB 权威→Dragonfly 缓存→NATS 广播 链路一致 |
| 扩展性 | ✅ 优秀 — 三层扩展模型 + 联邦宇宙 |
| 安全性 | ✅ 优秀 — Wasmtime 沙箱 + MCP transport 拆分 + DNS rebinding 防御 |
| 文档一致性 | ⚠️ 4 个 concerns + 5 个 consistency gaps — 不阻塞但需要修正 |
| 算法风险 | ⚠️ 3 个风险点 — 均非阻塞，需监控和明确 |

**建议下一步**: 优先处理 D3（Rhai 隔离模型矛盾）和 CG2（ECS 调度顺序不一致），这两项影响实现路径选择。D1、D2、D4 可在实现初期并行修正。CG1/CG3/CG4/CG5 为文档编辑级修正，低优先级。

---

*评审完成。架构设计展现了高质量的工程纪律——核心决策（Bevy ECS、FDB、Wasmtime、Blake3、IDL）构成了一套自洽且优雅的技术栈。4 个 concerns 均不构成架构级返工。*
