# R6 Architect 评审 — rev-claude-architect

## 总体 Verdict

**CONDITIONAL_APPROVE**

文档体在 R5 收敛后已进入"接近实施级"的稳定形态。Source Gate 单一管线、Determinism Contract、is_visible_to 单一函数、IDL 单一真相来源、Bevy snapshot 范围清单、TickTrace 写入 WAL 降级链、Overload 三种结果等价合同 + 抗永久锁死证明、特殊攻击优先级矩阵、Tier 1/2/3 路线带 entry gate 等机制都已经做到了"可直接进入实现"的细致程度。

但仍有 **3 项 High（A1+A2 跨文档 Phase 2b 调度顺序不一致 / A9 Tier 3 跨分片冲突解决与 Determinism Contract 直接冲突 / A11 Spawn 资源扣除时序未定义）** 阻塞了"看一遍合同就能开始写代码"的目标。这三项不修不该解锁实现。

修正后即可 APPROVE。

---

## Strengths（值得保留的设计决策）

1. **Source Gate + 单一 validate_and_apply 管线**（specs/02 §1 + specs/09 §4）—— 编译期 trait 设计强制所有 mutating 路径汇聚到一处，这是把"信任边界"从配置转为类型系统的正确方向。
2. **Determinism Contract 完整覆盖**（design/gameplay §8.8）—— PRNG/Hash/数值/排序/HashMap 五元一体，Blake3 单原语统一了哈希/PRNG/MAC 三种用途，依赖栈和审计面同时缩减。
3. **Bevy World snapshot 范围清单**（specs/01 §3.5）—— Resource + Component 列表逐项枚举，FDB rollback 不再是模糊的"恢复世界"。配上 §3.5 的 CI 故障注入测试模板，从"声明性"升级为"可验证性"。
4. **COLLECT 缓存跨重试 + fuel 不追加**（specs/01 §8.4）—— 关闭了"故意失败构造重试以放大 budget"的攻击窗口，且语义干净（首次扣费即最终扣费）。
5. **三层信任模型**（design/gameplay §8.2 + specs/07 §5.1）—— WASM 不可信 → Rhai 服主信任 → Rust 核心不可变，加上 Rhai 强制签名 + 能力白名单 + AST 节点确定性预算，把"模组生态"和"确定性回放"两个看似冲突的目标做到了共存。
6. **特殊攻击优先级矩阵 + 反制窗口矩阵**（specs/02 §3.16）—— 同 tick 多命中的语义被穷举到表格里，是这一轮文档质量飞跃最明显的一处。
7. **Overload 三结果等价 + 抗永久锁死证明**（specs/02 §3.12, §3.17）—— 把信息泄露面（fuel 状态 oracle）和均衡面（永久锁死可能性）一次性闭合，并以数学证明而非散文论证。
8. **快照截断分桶 + 确定性排序键**（specs/01 §2.3）—— 关键桶不丢、高优先按距离、确定性 (distance, entity_id) tiebreaker。`truncated/omitted_count` 暴露给 WASM 让玩家可推理。
9. **Tier 1/2/3 路线 + Phase 1 entry gate**（design/engine.md §3.2 + specs/future/*）—— 显式标记 T2/T3 必须在 Phase 1 实现前冻结，杜绝了"远期模糊声明"的常见架构债。
10. **IDL 单一真相 + Core IDL vs World Action Manifest 边界**（specs/08 §1）—— Core IDL 长期稳定 + ABI 版本控制；World Action Manifest 可由 world.toml 动态生成，target_manifest_hash 验证部署兼容。这是 mod 生态扩展性最干净的处理方式。

---

## Concerns

### A1 (HIGH) — Phase 2b ECS 主链 `.chain()` 顺序在 4 个文档中给出 4 个不同版本

| 文档 | 主线 chain 顺序 | regen/decay 调度 | spawning_grace | status_advance |
|---|---|---|---|---|
| design/engine.md §3.2 (line 211–215) | `death_mark → spawn → combat → death_cleanup` | 与主线**并行**（`before(death_cleanup)`） | 散文中提及，未入主链图 | 未出现 |
| specs/01 §3.4 (line 365–383) | `death_mark → spawn → spawning_grace → combat → status_advance` 后接 death_cleanup | 与主线**并行**（`.before(death_cleanup_system)`） | 在主链 | 在主链 |
| specs/02 §3.19 (line 519–523) | `death_mark → spawn → spawning_grace → combat → status_advance → (regen, decay 并行) → death_cleanup` | 并行 | 在主链 | 在主链 |
| specs/07 §3 (line 158–165) `register_systems` 示例 | `death_mark → spawn → regeneration → combat → decay → death_cleanup`（**全部 chain，串行**） | **串行**在主线，且 regen 在 combat 之**前** | 未出现 | 未出现 |
| specs/07 §10 (line 1063–1074) `register_rule_systems` 示例 | `death_mark → spawn → combat → death_cleanup` chain | regeneration / decay 并行（`after(death_mark).before(death_cleanup)`） | 未出现 | 未出现 |

**核心矛盾**：
- specs/07 §3 的示例把 regeneration 放在 combat **之前**——意味着资源点先再生再被采集 / 战斗结算基于"再生后"的资源量。
- 其他所有文档（specs/01, specs/02, design/engine, specs/07 §10）都规定 combat 在 regeneration **之前**——specs/01 §3.4 line 385 甚至有显式论证："combat 在 regeneration 之前执行——确保战斗结算基于本轮状态，再生在战斗后补充资源"。
- 这是一处真正的**语义冲突**，不只是表述风格不同。同 tick 内 source.energy 是先减后加还是先加后减，结果不同。

**修正建议**：
1. 选定权威：specs/01 §3.4 是顶层规范，其他文档全部对齐到"`death_mark → spawn → spawning_grace → combat → status_advance` 主链 + (regen, decay) 与主线并行（仅 before death_cleanup）"。
2. specs/07 §3 line 158–165 的 register_systems 代码示例需重写——**最容易被实施者抄走的是这段代码**，规范不一致 + 代码示例不一致 = 至少有一种实现会写错。
3. specs/07 §10 line 1063–1074 的第二段 register_rule_systems 同样需要补全 spawning_grace + status_advance。
4. design/engine.md §3.2 主链图（line 211–215）添加 spawning_grace 和 status_advance 节点——目前这两个 system 只在散文中出现。

### A2 (HIGH) — Tier 3 LWW + versionstamp 与 Determinism Contract 直接冲突

specs/future/T3 §5：
> "跨分片事务通过 FDB 的 multi-region 配置处理——冲突解决策略：`last-writer-wins` with `versionstamp` tiebreaker。"

design/gameplay §8.8 Determinism Contract：
> "PRNG: Blake3 XOF，确定种子 + offset → 随机流，**不依赖 OS 熵源**"
> "数值: 整数 + 定点数。**禁 f64**（跨平台/编译器非确定）"

**矛盾**：FDB versionstamp 包含集群单调时钟（10 字节 = 8 字节 commit version + 2 字节 batch order），其中 commit version 由 FDB cluster controller 物理时钟决定。多区域部署中，区域间时钟不同步、网络延迟波动 → versionstamp tiebreaker 是**事实上的非确定性来源**。

具体后果：
- 同一组跨分片 commands 在两次 replay 中可能得到不同的 versionstamp 顺序 → state_checksum 不同 → 回放不一致。
- specs/02 §6.3.2 `replay_tick` 要求 "execute_deterministic(state, commands) == recorded_state"——Tier 3 下这一性质被破坏。
- TickTrace 必须额外记录 versionstamp 才能回放——但 TickTrace 不应包含物理时间字段（违反 §8.8 哲学）。

**这不是"未来才考虑"的问题**——T3 §1 明确说"Tier 3 实现前必须冻结本文档"，那么冻结前必须解决这个根本性矛盾。

**修正建议**（任选其一）：
1. **方案 A — 放弃 Tier 3 跨分片确定性**：明确声明"Tier 3 跨分片操作不进入 replay 确定性合同。跨分片 replay 仅保证最终一致，不保证 tick-by-tick 等价"。
   - 配套：TickTrace 在 Tier 3 中分为"分片内 trace（确定）"和"跨分片 trace（最终一致）"两层。
   - 影响：Arena 模式赛后回放的"全知视角"只在单分片世界中可用。
2. **方案 B — 用逻辑时钟替代 versionstamp**：跨分片 combat 协议（T3 §4.2 两阶段）的 tiebreaker 改为 `(global_tick_id, attacker_shard_id, sequence)`。
   - global_tick_id 由全局共识（FDB 单 key 自增）保证单调；attacker_shard_id 来自分片注册表；sequence 来自 attacker 端 RawCommand。
   - 不依赖物理时钟 → 跨分片仍可 replay。
   - 代价：每次跨分片 commit 多一次 FDB 全局 key 自增（性能 cost）。

### A3 (HIGH) — Spawn 资源扣除时序在 Phase 2a/2b 之间未定义

design/engine.md §3.2：
> "Phase 2a: ... Spawn 命令在 Phase 2a 中只校验不入队。"

specs/02 §3.8：
> "Drone 在 Phase 2b spawn_system 中创建——位于 death_mark（释放 room cap 槽位）之后。"

specs/01 §3.3 Phase 2a TOCTOU 合同 #1：
> "Spawn pending 不可见：Phase 2a 中 Spawn 命令只校验不入队。新 drone 在 Phase 2b spawn_system 中统一创建。"

**未定义**：Spawn 的 body_cost（如 `{Energy: 200, Matter: 50}`）扣除是发生在哪一步？

候选：
- (a) Phase 2a 校验通过的同时立即从 spawn.energy 扣除（commit-pending）。
- (b) Phase 2b spawn_system 实际创建 drone 时才扣除。

两种选择带来不同的 Phase 2a 后续语义：

| 时点 | 在 Phase 2a 紧随 Spawn 之后的 Transfer / Build / Withdraw 命令 |
|---|---|
| (a) 立即扣除 | 看到的 spawn.energy 已经被扣过 → 后续命令的资源校验依赖正确 |
| (b) 延迟扣除 | 看到的 spawn.energy 还是原值 → 同一玩家可在 Phase 2a 中"双花"，Phase 2b 才发现冲突，Spawn 必须回滚 |

specs/02 §3.4 Build 校验需要 `drone.carry[Energy] ≥ build_cost`——drone 还没创建，所以这条不冲突。但同房间内**其他 drone** 从同一 Spawn 的 Energy 池 Withdraw 是合法操作，时序就成了关键。

**修正建议**：
1. 在 specs/01 §3.3 TOCTOU 合同中明确：**Spawn 的 body_cost 在 Phase 2a 校验通过时立即从 spawn.energy 扣除**（方案 a）。
2. 同步在 specs/02 §3.8 Spawn 校验表的"应用阶段"小结里写明扣除时点。
3. 若 Phase 2b spawn_system 因 room cap 在 death_mark 后未释放等原因失败 → 显式定义"Spawn 资源退还路径"——目前 specs/02 §7.1 Refund Strategy 没有覆盖"Phase 2b 创建失败"这个 case。

---

### A4 (MEDIUM) — Wasmtime 版本升级是"全停事件"但部署 runbook 缺失

specs/04 §2.1：
> `wasmtime = "=30.0"   # 锁定版本 — 不自动升级`
> "`=30.0` 版本的安全支持窗口：跟踪 Bytecode Alliance 的 LTS/non-LTS 发布策略，锁定版本需在官方安全支持窗口内"

specs/04 §7：
> "模块缓存 | 按 `Blake3(module_hash || wasmtime_build_commit || ... || security_epoch)` 缓存"

具体后果：
- Wasmtime 升级 → wasmtime_build_commit 变化 → 全量缓存失效。
- 假设单世界 1000 个活跃模块，每个编译耗时数秒，串行重编译 = 数小时停机。
- specs/04 §7 限制"并发编译 5 个"——重编译期间新部署阻塞。
- specs/security/CVE-SLA.md §部署：Critical CVE 24h 响应——但实际 24h 内能完成"全量重编译 + staging 验证 + 灰度 + 生产"吗？数学上不成立。

**矛盾**：CVE-SLA 24h 响应承诺 vs 编译并发 5 个的物理上限。

**修正建议**：
1. specs/security/CVE-SLA.md 增加"重编译预算"段，给出在 N 模块世界下 Critical CVE 的实际可达时间。
2. specs/04 §7 增加"批量重编译策略"——例如"CVE 触发的版本升级允许临时把并发编译上限提到 50，限定时长不超过 1h"。
3. design/engine.md / RUNBOOK.md 增加 "Wasmtime 升级降级模式"——正在重编译的世界进入只读模式（已部署模块继续运行，新部署/回滚拒绝），重编译完成后退出。
4. specs/02 §6.3.3 已声明"Wasmtime 版本变更不影响回放"——这是因为 TickTrace 记 Command 不记 WASM 输出。但是否需要在 TickTrace 中记录 `wasmtime_version_at_tick`，让 Critical CVE 触发时能定位"哪些 tick 在受影响版本下执行过"？

### A5 (MEDIUM) — Tier 1 vs Tier 2 vs Tier 3 的容量量纲在"玩家数"与"drone 数"间反复切换

| 文档 | 维度 | 数值 |
|---|---|---|
| design/engine.md §3.1a (line 169–171) | 活跃**玩家数** | MVP=500，单 Engine+缓存=1k–5k，水平分片=不限 |
| design/engine.md §3.2 (line 267–269) Tier 表 | **drone 数** | T1=500, T2=5000, T3>5000 |
| specs/future/T2 §1 | **drone 数** | ≤5000 drone, ≤500 房间 |
| specs/future/T3 §1 | **drone 数** | >5000 drone |
| specs/02 §6 + specs/07 line 94 | 单玩家 drone cap | 500（默认） |

**问题**：500 玩家 × 500 drone/玩家 = 250,000 drone — 直接突破 Tier 3 下限（5000）。如果"500 玩家"是 MVP 目标，那 MVP 一开始就不能容纳所有玩家用满 drone cap。这两个数字不在同一个量纲。

加上 specs/core/01 §2.3 规定"每玩家可见实体数 ≤ MAX_VISIBLE_ENTITIES (500)"——对单玩家可见性的限制是 500 实体，但全世界总 drone 数是另一个层面的事。

**修正建议**：
1. design/engine.md §3.1a 的扩展策略表换算单位——把"活跃玩家数"换成"world drone 总数"，或者明确"假设平均每玩家 N drone"做关联。
2. specs/future/T2/T3 文档的"5000 drone"标注上下文：是 world 全量 drone 还是单分片 drone？
3. 增加"单玩家 drone cap × 活跃玩家数 = world drone 数"的 invariant，跨文档一致。

### A6 (MEDIUM) — Overload `is_visible_to(target_player, attacker)` 校验 vs is_visible_to 函数签名不匹配

specs/05 §1：
```rust
fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool;
```
—— 第一参数是 **entity**，不是 player。

specs/02 §3.12 Overload 校验项：
> `is_visible_to(target_player, attacker)` — 可见性约束 | TargetNotVisible

specs/02 §6.3 字段级穷举校验：
> `Overload | ... | is_visible_to(target_player, attacker)` ...

specs/02 §3.12 描述：
> "**可见性约束**: 必须 `is_visible_to(target, attacker)`，不可攻击不可见玩家。"

`is_visible_to(target_player, attacker)` 的语义不能直接派生自 §1 的函数签名——target_player 不是 entity。

**两种可能的语义**：
- (X) attacker 看到 target_player **至少一个 entity**（任意 drone/structure）→ Overload 合法。
- (Y) attacker 看到 target_player **的某个特定 entity**（如 target_player 的最近 drone）→ Overload 合法。

specs/05 §6.1 Overload 可观察性表：
> "attacker 视角: ... 仅知 target 在当前世界中有可见实体"

—— 这倾向于语义 (X)，但不是 specs/02 校验合同的等价表述。

**修正建议**：
1. specs/05 §1 增加 `is_visible_to_player` 的派生定义：
   `is_visible_to_player(target_player_id, observer_player_id, tick) := exists e: Entity. e.owner == target_player_id ∧ is_visible_to(e, observer_player_id, tick)`
2. specs/02 §3.12 把校验项改写为这个明确的派生函数调用。
3. specs/02 §6.3 同步修正。

### A7 (MEDIUM) — 同 tick 特殊攻击优先级（§3.16）vs 命令循环排序（§3.1）的优先级关系未定义

specs/02 §3.1 命令循环排序：
> "按洗牌后的玩家顺序 + 玩家内部指令序号排序" + "对每条指令（按洗牌后顺序 + 玩家内 sequence 排序）逐条 inline 应用"

specs/02 §3.16 同 tick 多命中优先级：
> "1. Disrupt → 2. Fortify → 3. Debilitate → 4. Hack → 5. Drain/Leech → 6. Overload → 7. Fabricate"

**矛盾场景**：
- attacker_A（shuffle 顺序 #3）提交 Hack(target_T)
- attacker_B（shuffle 顺序 #7）提交 Disrupt(target_T)
- 按 §3.1 命令循环：A 先执行 → Hack 施加 control lock → B 后执行 → Disrupt 打断 control lock。✓ 时序合理。
- 但按 §3.16 优先级表：Disrupt 优先级 1，Hack 优先级 4 → "Disrupt 应该先生效"。

如果 §3.16 是覆盖 §3.1 的元级规则，那么命令循环不再是简单的"按 shuffle 顺序逐条 apply"，而要先按 action 类型分组、按优先级 apply、组内再按 shuffle。

如果 §3.16 是描述性的（"在 inline 模型下因为 Disrupt 通常排在前面所以先生效"），那么这个表只是对常见情况的描述，不是强制规则——但表头写"按以下优先级执行（高优先级先执行，低优先级可能被覆盖或拒绝）"明显是规则口吻。

**修正建议**：
1. specs/02 §3.16 在表头补充：**"§3.16 优先级在 inline 命令循环（§3.1）之上生效"** 或者 **"§3.16 优先级仅描述同 attacker 同 drone 多 effect 时的内部执行顺序，跨 attacker 不生效"**。
2. 选前者意味着命令循环不再是单一 inline 而是"分组 inline"——需在 specs/01 §3.4 中显式声明。
3. 选后者则 §3.16 表头需重写为"同一 effect_set apply 时的内部顺序"。

### A8 (MEDIUM) — Sandbox 进程模型 "每 tick fork → kill" 物理上不可达，但实施层面缺降级合同

specs/04 §1：
> "生命周期: sandbox worker 进程**每 tick 新 fork**，执行一个玩家，返回指令，然后 kill。"
> "防止跨 tick 内存泄漏、长运行进程资源累积、受感染模块持久化。"

物理预算：500 活跃玩家 × 每玩家 128MB cgroup × 每 tick fork-kill = 64GB 内存占用 + 500 × fork() 系统调用 / 3s = 167 fork/秒（fork 本身约 1–10ms，500 个 fork 串行 0.5–5s，已经吃掉整个 tick interval）。

实际部署一定是 worker pool 复用——但这与"防止跨 tick 内存泄漏 / 受感染模块持久化"的安全目标直接冲突。

**未定义**：
- worker pool 的实际尺寸？
- 每多少 tick reset 一次 worker？
- worker 复用时如何保证"上一个玩家的内存已清空"——单纯 reset Wasmtime store 是否足够？
- worker pool 实现下的"每 tick fork"安全合同如何落到工程实施？

**修正建议**：
1. specs/04 §1 区分"逻辑模型"和"物理模型"：
   - 逻辑模型：每 tick 一个隔离实例（用于安全推理）
   - 物理模型：worker pool + Wasmtime instance per tick（实际实现）
2. 显式声明 Wasmtime instance reset 的合同：每 tick 调用 `Store::limiter` reset → 内存清零 → 新建 instance。验证"reset 后无残留状态"作为 sandbox boundary CI 测试的一项（specs/04 §9.4）。
3. 给出 worker pool 重用次数上限——例如"每 worker 处理 1000 玩家-tick 后销毁重建，防止潜在内存碎片或漏洞累积"。

---

### A9 (LOW) — Tutorial source 的 mode 校验未在 Source Gate 中显式

specs/09 §2.4：
> "Tutorial 来源的指令仅可在 world.mode = "tutorial" 的世界中接受。在非 Tutorial 世界收到的 Tutorial 来源指令 → 静默丢弃 + 记录审计日志。"

specs/09 §4 校验管线只有 Source Gate 和 Auth Verify，没有 mode 校验环节。

**修正建议**：specs/09 §4 Source Gate 描述中增加"按 source 类型校验目标 world.mode"，或者新增 Mode Gate 步骤。这只是合同补全，不影响实施。

### A10 (LOW) — Rhai 模组 actions buffer 的跨模组 apply 顺序未定义

specs/07 §5.1：
> "所有脚本执行完毕后，buffer 中有效的 action 一次性 apply"

**未定义**：当模组 A 和模组 B 都修改同一资源（如 player.energy），apply 顺序是什么？
- (a) 按 world.toml 中 [[mods]] 的声明顺序
- (b) 按 mod_id 字典序
- (c) 按钩子触发顺序（但 tick_end 钩子是并行还是串行未定）

如果不固定，回放保证无法成立——同一组 actions 不同顺序得到不同 apply 结果。

**修正建议**：specs/07 §5.1 显式声明"actions buffer apply 顺序 = world.toml [[mods]] 声明顺序"，并在 mods.lock 中固化。

### A11 (LOW) — MAX_VISIBLE_ENTITIES (500) 与 256KB 截断的次序未明

specs/01 §2.3：
> "实体膨胀攻击 | 玩家可见实体数连续 5 tick 超过 `MAX_VISIBLE_ENTITIES`（500）"

但 256KB 截断在 sort_and_truncate 中已经先执行——实际进入快照的实体数受 256KB 限制，可能远少于 500。

**未定义**：MAX_VISIBLE_ENTITIES 检测的是"截断**前**视野内总实体数"还是"截断**后**实际进入快照的实体数"？

- 前者：玩家无法通过 truncation 规避检测——合理。
- 后者：玩家只要不停撞 256KB 上限就永远不会触发 MAX_VISIBLE_ENTITIES，检测失效。

**修正建议**：specs/01 §2.3 滥用检测表里 `MAX_VISIBLE_ENTITIES` 行补充"按截断前 visibility set 大小判定"。

### A12 (LOW) — design/engine.md §3.2 主链图未完整列出 spawning_grace 和 status_advance

A1 的子症状之一。design/engine.md 是顶层导航文档，主链图是实施者第一眼看到的"设计真相"。补全 spawning_grace 和 status_advance 节点不只是文档同步问题，是"设计真相"的完整性问题。

### A13 (LOW) — specs/07 §3 列出的可选 systems 缺单独合同

specs/07 §3 列出 `code_update_cost_system, code_update_window_system, drone_env_var_system, pvp_block_system` 等可选系统，但只有 code_propagation_system / memory_upkeep_system 在 §4 给出伪代码。其他系统的输入/输出/超限行为未定义——实施时各家会做出不同选择。

**修正建议**：specs/07 §4 补全所有可选系统的合同骨架（即使是简短描述）。

---

## Missing（缺失的合同）

### M1 — Tier 1 → Tier 2 数据迁移合同

T2 §5 描述了 Tier 2 内部 keyframe 间隔，但未定义：
- 现有 Tier 1 全量 keyframe 能否作为 Tier 2 的初始 base snapshot？
- Tier 1 的 state_checksum（基于全量快照）vs Tier 2 的 state_checksum（基于增量重建）是否同算法？
- 切换 Tier 时正在执行的 tick 如何处理？

没有这个合同，Phase 1 实施完成后无法平滑升级到 Phase 2。

### M2 — Tier 3 跨分片操作的 IDL 暴露

T3 §4.3 一致性表：
> "跨分片 RangedAttack: 最终一致（两阶段），延迟 1 tick"

Tier 1/2 中 RangedAttack 是 0 延迟、强一致——Tier 3 引入 1 tick 延迟。这是对玩家代码可见的语义变化吗？

如果是，IDL 必须暴露——玩家代码在 Tier 3 世界需要知道"我的 RangedAttack 命中目标的 HP 反馈会延迟 1 tick"。
如果不是（即引擎隐藏延迟、玩家看到的仍是即时 HP），那么 specs/01 §6.4 MCP/Query 的 "snapshot_tick == current_tick" 不变量在 Tier 3 中可能被破坏。

specs/08 IDL 当前没有任何"跨分片"或"延迟"字段——这个缺口必须填上。

### M3 — Engine ↔ NATS / Engine ↔ FDB 失败语义补全

specs/01 §6 的失败矩阵覆盖了 FDB commit fail 和 NATS publish fail，但：
- FDB 已持久化但 NATS 失败 → 下次 NATS 恢复时如何补推已 commit 的 deltas？
- deltas 是否在 FDB 中也作为 audit trail 持久化？specs/12 §6 NATS 主题表里有 `tick.<world_id>.<tick>` 但没说 FDB 是否也存一份。
- specs/12 §3.3 客户端通过 `GET /api/v1/world/ticks?from=<N>&to=<M>` fetch missing deltas——这意味着 deltas 必须可从 FDB 重建，但具体路径未定义。

### M4 — Rhai 引擎版本与 replay 兼容性

specs/02 §6.3.3 声明"Wasmtime 版本变更不影响回放"——因为 TickTrace 记的是 ACCEPTED Command，不是 WASM 输出。

但 RuleMod 的 actions buffer 也需要 replay。specs/07 §5.1 末尾说"所有 actions 操作被记录到 TickTrace"——但记录的是 actions（如 deduct_resource）还是 Rhai 脚本输出？如果 Rhai 1.x → 2.x 升级改变了脚本求值语义（如某个 builtin 行为变更），是否需要按"所记录的 actions"重放还是按"原 Rhai 脚本"重放？

specs/07 §5.1 没有 Rhai 版本锁定声明（specs/04 §2.1 锁了 Wasmtime 版本，但 Rhai 没对应锁）。

### M5 — 单 tick 全量 snapshot 大小数学

design/engine.md §3.2 Tier 表声明 Tier 2 "≤64MB / tick 构建"。

数学验算：50×50 格 × 500 房间 × 平均 5 entity/格 ≈ 625k entity，每 entity 序列化约 200 字节 = 125MB。即使 Tier 1 (50 房间) 都需要 12.5MB 接近上限。

Tier 2 的 64MB 限制是按 modification-set 增量大小算还是按全量算？T2 §2 modification-set 结构确实只记 added/removed/modified，但首 tick keyframe 还是全量——首 tick / keyframe 的 size 受不受 64MB 约束？

补全这层数学+边界。

### M6 — MCP Query 在 EXECUTE 阶段的访问语义

specs/01 §2.3 时序图：
> "[5] MCP query（swarm_get_snapshot）← 读取同一快照（步骤 1 构建的副本）"
> "MCP query 不能观察到 EXECUTE 阶段的中间状态"

**未定义**：
- COLLECT 期间（[1] 快照构建尚未完成）MCP query 是否被阻塞？
- EXECUTE 期间 MCP query 读到的是 COLLECT 开始时的 tick N snapshot；BROADCAST 完成后切换到 tick N+1 snapshot——切换是原子的吗？
- 如果一个 MCP 请求横跨 BROADCAST 边界，它读到的是哪个 tick？

### M7 — 大批量 deploy 的 nonce 池容量

specs/09 §7.3 deploy_nonce 是单次消费、60s TTL。Tournament 模式下假设 1000 玩家在赛前同时获取 nonce → 1000 个 nonce 在 60s 内全部活跃。

合理的实现要求 nonce store 容量足够——但文档未说明 nonce store 的容量上限和 LRU 策略。

### M8 — Wasmtime 升级触发的"全停 / 灰度"runbook

CVE-SLA.md 提到 "Critical CVE 24h 内评估 + 补丁，必要时临时降级到已知安全版本"——但没有具体步骤。

需要一个明确的 runbook：
1. 谁有权批准版本升级（dev team？Auth Service epoch？）
2. 升级期间正在跑的世界进入什么状态（暂停？只读？降级模式？）
3. 升级后旧 TickTrace 的 replay 验证是否需要双版本验证？
4. 灰度策略：先升级 1% 世界、确认无回归后扩大？

---

## Phase Ordering

> *AGENTS.md 第 12 行禁止 "Phase 0/Phase 1" 类阶段标签——以下"Phase Ordering"指 Tier 1/2/3 实现路线的依赖与并行性，非文档版本号。*

### 依赖图

```
                       [Tier 1 — MVP 单节点]
                               │
                ┌──────────────┼──────────────┐
                │              │              │
       [core/01 tick]   [core/02 cmd]   [core/04 wasm]
                │              │              │
                └──────────────┼──────────────┘
                               │
                       [core/07 world rules]  ← 依赖 02 (validate_and_apply)
                               │
                ┌──────────────┼──────────────┐
                │              │              │
        [security/03]   [security/05]  [security/09]  ← 与 core 并行可行
                │              │              │
                └──────────────┼──────────────┘
                               │
                       [gameplay/06,08]  ← 依赖 core/02 IDL
                               │
                       [Tier 1 实施完成]
                               │
                ┌──────────────┼──────────────┐
                │              │              │
        [future/T2 spec  [运营观察]    [基准测试数据]
         冻结依赖 ↑↓]
                │              │              │
                └──────────────┼──────────────┘
                               │
                       [Tier 2 实施]
                               │
                       [future/T3 spec 冻结依赖 Tier 2 数据载体]
                               │
                       [Tier 3 实施]
```

### 评审

**正确性 ✓**：
- core/01 tick 协议是基石，不依赖任何其他文档。
- core/02 命令校验依赖 core/01 (Phase 2a/2b 时序) 和 specs/08 IDL 的指令枚举。
- core/04 sandbox 与 core/01/02 接口边界清晰（COLLECT 阶段的 fuel/timeout/output 合同）。
- security/* 三个文档都依赖 core/02 的 validate_and_apply 单一管线，但相互之间正交（mcp-security 管 transport，visibility 管输出过滤，command-source 管 auth + source）。
- gameplay/06 反馈循环和 gameplay/08 IDL 是 Tier 1 用户体验和实施代码生成的入口，依赖 core/02 完成。

**可并行的工作**：
- core/01, core/02, core/04 可由 3 个独立 worker 并行启动——它们之间通过接口（CommandIntent / ValidatedCommand / Snapshot）解耦。
- security/03, security/05, security/09 可与 core/* 并行。
- specs/12 gateway 协议跨域汇聚 core/01 §4 + security/03 §2 + security/05 §3 + security/09 §7.0 — 这是阅读视角的整合，不引入新合同，可在 core/security 实现完成后再校对。

**Tier 2 / Tier 3 spec 冻结的循环依赖问题**（已在 Concerns 中外列）：
- design/engine.md 声称"Tier 2/3 spec 必须在 Phase 1 实现前完成"。
- specs/future/T2 §6 列出"待定项"，明确"需在 Tier 2 实现前通过基准测试确定"。
- 这构成循环：T2 spec 冻结需要 Tier 1 实施数据 → Tier 1 不能实施直到 T2 冻结。

**修正建议**：
- 把 design/engine.md "Tier 2/3 必须在 Phase 1 实现前完成" 弱化为"Tier 2/3 必须在 Tier 1 进入实施前确定**接口与候选方案集**，但具体参数（CoW 页大小、keyframe 间隔等）允许在 Tier 1 实施期间通过基准测试细化"。
- specs/future/T2/T3 在头部明确两类内容：
  - **必须冻结的接口**（modification_set 结构、跨分片实体引用格式、跨分片 combat 协议形态）—— 不可改。
  - **可调参数**（keyframe 间隔、shard size、CoW 页大小）—— 实施期间通过基准测试确定。

**Tier 3 entry 阻塞**：A2 (LWW + versionstamp vs Determinism) 必须先解决，T3 spec 才能真正冻结。否则 Tier 3 实施会撞上 replay 不一致这块墙。

### 关键路径

```
core/01 → core/02 → security/* + gameplay/* → Tier 1 实施完成 → 基准测试 → T2 参数细化 → T2 实施 → Tier 2 实施完成 → 基准测试 → T3 参数细化 + A2 决议 → T3 实施
```

A2 阻塞 T3 实施起点，但不阻塞 Tier 1。Tier 1 关键路径上没有阻塞性 Concerns——A1（Phase 2b 顺序不一致）和 A3（Spawn 资源时序）都是文档对齐工作，不需要新设计决策，1–2 天内可闭合。

---

## 总结

R6 是文档体逼近"实施级冻结"的临门一脚。R5 的 B1–B6 共识 Blocker 已经全部反映在当前文档中（已交叉验证 specs/02 §3.4 / §3 / §6 / specs/05 / specs/09 / DESIGN.md 等位置）。

**Tier 1 实施可以在 A1 / A3 修正后立即启动**——这两项是文档对齐，不引入新决策。

**Tier 3 实施起点必须先决议 A2**——否则 LWW 将破坏整个 replay 合同。

其他 Concerns（A4–A13）和 Missing（M1–M8）应作为 Tier 1 实施过程中并行修补的 backlog，不构成 Phase 1 entry 阻塞。

工程上 Strengths 一节列出的 11 项设计决策已经把"如何把可编程 MMO RTS 做成确定性回放系统"这件事的核心难题逐项闭合——这是过去 5 轮评审持续打磨的成果，值得继续推进而不是回炉重造。
