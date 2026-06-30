# R41 Phase 1 独立评审 — Architecture Reviewer (GLM-5.5)

**评审范围**：架构 + 安全 + 确定性 + 性能
**评审日期**：2026-06-30
**文档版本**：R41 clean-slate 文档子集

---

## 1. Verdict

**CONDITIONAL_APPROVE**

整体架构设计成熟、一致性好，确定性合同和持久化分层是工程级水准。发现 3 个 High 级问题和若干 Medium 级问题需要修复，但不存在根本性架构缺陷。修复后可直接 APPROVE。

---

## 2. 发现的问题

### ARCH-H1: Dragonfly/ClickHouse 引用残留 — 术语与架构不一致 [High]

**文件**：
- `design/README.md` §2.1 架构图（行 134-136）
- `specs/core/01-tick-protocol.md` §2.3 快照构建时序（行 113）、§4.2 持久化→缓存+发布（行 628-629）、§6.1 失败模式矩阵（行 656-657）、§6.4 查询读源优先级（行 747）
- `specs/security/03-mcp-security.md` §7 审计日志（行 376-392）

**问题**：`design/tech-choices.md` §6/§7 明确移除了 Dragonfly 和 ClickHouse（"已被移除"），替换为 "Engine 进程内 Moka Cache" 和 "redb metrics table + Gateway 聚合"。但多个核心 spec 文档仍大量引用已移除的组件：

1. `01-tick-protocol.md` 行 113：BROADCAST 阶段流程图写 `Dragonfly + NATS (并行 fan-out)` — Dragonfly 已不存在
2. `01-tick-protocol.md` 行 628-629：`Dragonfly.update(delta) ──┐ NATS.publish(...)` — 并行 fan-out 描述仍用旧组件
3. `01-tick-protocol.md` 行 656-657：失败模式矩阵有 `Dragonfly cache miss`、`Dragonfly cache stale` 行
4. `01-tick-protocol.md` 行 747：查询读源优先级表写 `Dragonfly 缓存` — 应为 Moka 或去掉此行
5. `design/README.md` 行 134-136：架构图数据层画了 `Dragonfly (热缓存)`、`ClickHouse (分析+审计)`
6. `03-mcp-security.md` 行 376-392：审计日志写 `CREATE TABLE mcp_audit (...) ENGINE = MergeTree()` — 这是 ClickHouse DDL，但 ClickHouse 已被移除

**影响**：架构图与规范描述不一致——实现者会困惑于审计日志到底写哪里、缓存用什么。这是术语一致性级别的合同漂移。

**修复建议**：
1. 全局搜索 `Dragonfly`、`ClickHouse`、`MergeTree`，替换为当前设计（Moka / redb metrics / Gateway 聚合）
2. `design/README.md` §2.1 架构图重画数据层
3. `03-mcp-security.md` §7 审计日志改为 redb metrics table 或 Gateway 聚合查询的描述
4. `01-tick-protocol.md` §4.2/§6.1/§6.4 全部更新

---

### ARCH-H2: Rhai RuleMod 来源仍引用 — 与 "唯一扩展机制 = Bevy Plugin" 矛盾 [High]

**文件**：
- `design/engine.md` 行 11："扩展机制：Mod = Bevy Plugin，静态编译进 Engine 二进制。这是唯一的扩展机制——没有 Rhai 脚本层。"
- `design/tech-choices.md` §3："Rhai 已被移除——Bevy Plugin trait 是唯一的扩展机制。"
- `specs/security/09-command-source.md` §2.2 扩展来源矩阵（行 31）：`RuleMod | Rhai 规则模组 actions`
- `specs/security/09-command-source.md` §2.3（行 47）：`RuleMod | ⚠️ damage_entity/set_entity_flag/...`
- `specs/security/09-command-source.md` §1 原则（行 9）：无直接矛盾但整个 RuleMod 段落仍存在
- `specs/core/01-tick-protocol.md` §9.8（行 1032）：`Rhai RuleMod：固定点数...禁止第二套状态修改路径`

**问题**：`design/engine.md` 和 `design/tech-choices.md` 均明确声明 Rhai 已被移除、Bevy Plugin 是唯一扩展机制。但 `09-command-source.md` 仍将 `RuleMod` 作为独立 Source 保留了完整的来源矩阵（auth_context、能力约束、rate_limit、visibility、budget），且 `01-tick-protocol.md` §9.8 仍写 "Rhai RuleMod" 规范。

这造成两个矛盾：
1. 如果 Rhai 真的移除了，`09-command-source.md` 中的 `RuleMod` Source、`Rhai op budget` 应当移除或改写为 "Bevy Plugin mod actions" 的等价物
2. 如果 RuleMod 保留为概念但实现换了，文档应说明 Bevy Plugin mod 如何映射到 Command Source 模型——当前完全没提

**影响**：Command Source 模型的权威性被削弱。Mod 开发者无法确定自己的 system 输出是否走 `RuleMod` source 还是 `WASM` source，也不知道 `Rhai op budget` 是否仍然适用。

**修复建议**：
1. 将 `09-command-source.md` 中 `RuleMod` 行改写为 `BevyPluginMod`（或直接移除，将 mod actions 归入 engine 内部执行），更新 auth_context 为 `mod_id + world_owner_id`（保持），budget 从 `Rhai op budget` 改为 `mod system budget`
2. `01-tick-protocol.md` §9.8 将 "Rhai RuleMod" 改为 "Bevy Plugin Mod" 并删除 Rhai 相关措辞
3. 或者：如果设计意图是保留 Rhai 作为运行时 mod 脚本层（与静态编译的 vanilla mod 不同），则 `design/engine.md` 和 `tech-choices.md` 需要修正措辞。需用户裁决这是文档漂移还是设计变更。

---

### ARCH-H3: TickCommitRecord 字段数不一致 (10 vs 14+) [High]

**文件**：
- `specs/core/05-persistence-contract.md` §2.1：明确声明 "以下 10 个字段组成 TickCommitRecord"，编号 1-10
- `specs/core/01-tick-protocol.md` §3.3 `/TickInputEnvelope/`、设计文档 README 术语表：列出了 `collect_id`、`attempt_id`、`commit_id` 等额外标识字段
- `design/engine.md` 行 278-285：TickInputEnvelope 列出 `collect_id`, `attempt_id`, `commit_id`, `module_hash`, `wasmtime_version`, `effective_tick`, `fuel_schedule_version`, `host_cost_table_version`, `wasm_status`, `snapshot_hash`, `commands_hash`, `deploy_events`, `rollback_events`, `admin_events`, `world_config_hash`, `mods_lock_hash`, `engine_abi_version`, `terminal_state` — 远超 10 个

**问题**：`05-persistence-contract.md` §2.1 声称 TickCommitRecord "10 个字段" 组成，且 "缺失任一则 tick 不可 replay"。但：
1. `05-persistence-contract.md` 自身 §7.1 又新增了 `collect_id`、`attempt_id`、`commit_id` 三个标识字段
2. `design/engine.md` 列出了 18+ 个 TickInputEnvelope 字段
3. 术语表（README §附录 C）将 `TickCommitRecord` 定义为 "replay-critical 子集——仅包含状态 checksum、命令哈希列表、rejection 计数、fuel 扣费、attempt_id"

三处对 TickCommitRecord 的字段数定义不一致。实现者无法确定到底哪些字段是 "replay-critical 不可降级"（§2.1 声称 10 个）、哪些是 "标识字段"（§7.1 新增 3 个）、哪些属于 TickInputEnvelope（engine.md 列出 18+）。

**影响**：replay verifier 实现者无法确定最小 replay 输入集。如果遵循 §2.1 的 10 字段，则 `collect_id`/`attempt_id`/`world_config_hash`/`mods_lock_hash` 等被遗漏；如果遵循 engine.md 的完整列表，则 §2.1 的 "10 字段不可降级" 声明是错误的。

**修复建议**：
1. 在 `05-persistence-contract.md` §2.1 统一更新字段计数——将 §7.1 的 `collect_id`/`attempt_id`/`commit_id` 纳入正式编号（变为 13 字段），或明确区分 "replay-critical core (10)" vs "replay-identity (3)" 两层
2. 明确 TickInputEnvelope 与 TickCommitRecord 的关系——前者是 per-tick 元数据封套，后者是 redb 原子提交的 replay-critical 子集
3. README 术语表更新以匹配

---

### ARCH-M1: `WorldSeed` 在 Bevy 快照中被捕获但未声明 replay 处理 [Medium]

**文件**：`specs/core/01-tick-protocol.md` §3.5.6 Bevy World 快照范围清单（行 528）

**问题**：快照范围清单中 `WorldSeed` 被列为必须捕获的 Resource（行 528）。但 §3.3 种子轮换说明 `new_seed = Blake3(old_seed || current_tick)`，且 `seed_epoch` 记录在 keyframe 中。快照捕获 `WorldSeed` 意味着 redb commit 失败后 `world.restore(snapshot)` 会恢复旧 seed——这在语义上可能正确（恢复到 tick 前的 seed epoch），但如果 tick 内发生了 seed rotation（`tick % seed_rotation_interval == 0`），回滚后的 `WorldSeed` 应该是 rotation 前的值（tick N-1 的）还是 rotation 后的值（tick N 的）？

文档未显式说明 seed rotation 发生在 EXECUTE 的哪个 system 中，也未说明快照是在 rotation 前还是后捕获。

**影响**：确定性 replay 可能在 seed rotation tick 上产生歧义。如果快照在 rotation 后捕获，但 restore 后 seed 已变为新值，则 replay 从 keyframe 恢复时会使用错误的 seed epoch。

**修复建议**：明确 seed rotation 的执行时点（EXECUTE 开始前还是某个特定 system 中），并在快照范围清单中注明 `WorldSeed` 的快照语义："快照捕获 tick 开始时的 seed epoch，rotation 在 tick 末尾 commit 前执行"。

---

### ARCH-M2: `BROADCAST` 阶段引用不存在的基础设施 [Medium]

**文件**：`specs/core/01-tick-protocol.md` §2.3 快照构建时序（行 113）

**问题**：行 113 的 BROADCAST 阶段流程图画了 `Dragonfly + NATS (并行 fan-out)`，但 Dragonfly 已被移除。相应地，行 628-631 的 fan-out 描述、行 656-657 的失败模式矩阵、行 747 的查询读源优先级表都有残留引用。这属于 ARCH-H1 的一部分，但由于 BROADCAST 阶段是 tick 生命周期的核心环节，单独标注其严重性——实现者可能错误地部署 Dragonfly 实例。

**修复建议**：统一替换为 "Engine 进程内 Moka cache + NATS"。

---

### ARCH-M3: seccomp `clock_gettime` 和 `write` 的矛盾 [Medium]

**文件**：`specs/core/04-wasm-sandbox.md` §4.1 seccomp（行 258-271）、§9.1 OS 加固表（行 458-459）

**问题**：
1. §4.1 的允许列表包含 `write`，但 §9.1 加固表的注释说 `write` ✅ 允许的理由是 "输出指令 JSON"。然而 WASM 沙箱的 deferred command model 是通过 host function 调用 `tick()` → 返回 JSON → 引擎读取，WASM 不直接 `write` 到 stdout。`write` syscall 允许 Wasmtime runtime 的内部使用（如日志）——但 §9.3 relaxed 模式提到 "stderr 输出：禁止（仅 1KB/tick）"，暗示 stderr 默认也禁用。这里 `write` 的用途描述不够精确。
2. §4.1 明确 `clock_gettime` 禁止，但 §9.1 加固表行 458-459 说 `write` ✅ 允许、`clock_gettime` ❌ 禁止，而 §9.3 relaxed 模式说 `clock_gettime` 可放宽——`clock_gettime` 在 WASM 中不暴露（WASI clocks 禁用），但 host function 侧 `config.epoch_interruption(true)` 依赖 wasmtime 内部的计时。如果 seccomp 全禁 `clock_gettime`，wasmtime 的 epoch interruption 机制是否仍能工作？这需要 wamtime 内部使用 `clock_gettime` 的路径被 seccomp 阻断后的 fallback 行为说明。

**影响**：seccomp 与 wasmtime 内部机制可能有冲突——epoch interruption 依赖某种计时器，如果 clock 相关 syscall 全被 seccomp 拦截，wasmtime 可能在内部 panic 或 fall back 到 polling。

**修复建议**：
1. 明确 `write` 的允许范围——是否仅限 fd=1/2 (stdout/stderr)，是否需要 arg-based filter
2. 说明 wasmtime epoch interruption 的计时机制不依赖 `clock_gettime`（使用 `timerfd` 或 `setitimer`），或者如果依赖，在 §9.2 CI 验证中增加 "epoch interruption 在 seccomp 启用后仍正常工作" 的测试

---

### ARCH-M4: `Resource` 组件使用 `IndexMap<String, u32>` 但 `ResourceRegistry` 用 `BTreeMap` [Medium]

**文件**：`design/engine.md` 行 49-50（Resource struct）、行 275（BTreeMap 约束）

**问题**：`engine.md` 行 49-50 定义 `Resource { amounts: IndexMap<String, u32> }` 和 `Source { produces: IndexMap<String, u32> }`，注释说 "IndexMap 保证迭代顺序确定"。行 275 的确定性保证写 "需要确定性键排序的场景使用 BTreeMap...IndexMap 保留用于有序资源类型等插入顺序确定的场景"。

`IndexMap` 的确定性依赖**插入顺序**——如果资源类型的插入顺序由 world.toml 或 mod 定义决定且固定，则是确定的。但如果同一个 `Resource` 组件在不同实体的初始化路径中插入顺序不一致（例如 mod A 先插入 "Energy" 再插入 "Matter"，mod B 反过来），则跨 replat 迭代顺序不同。

`BTreeMap`（标准库全序排列）则不依赖插入顺序。`String` key 的字典序是跨平台一致的。

**影响**：如果资源迭代顺序进入确定性 replay（如 snapshot 序列化、TickTrace 记录），`IndexMap<String, u32>` 的确定性不如 `BTreeMap` 可靠——除非有合约保证所有 Resource 组件的插入顺序全局一致。

**修复建议**：
1. 如果 Resource key 是固定资源类型枚举（String 只是序列化表示），则 `IndexMap` 可接受——但需在确定性合同中声明 "Resource key 的插入顺序由 ResourceRegistry 初始化决定，全局一致"
2. 或改为 `BTreeMap<String, u32>`，更安全

---

### ARCH-M5: WASM `tick()` 函数签名缺少 fuel 剩余查询能力 [Medium]

**文件**：`specs/core/04-wasm-sandbox.md` §3.1 ABI（行 186-204）、§3.2 host functions（行 214-226）

**问题**：WASM `tick()` 接收 snapshot 并返回 commands。Host functions 白名单包含 `host_get_terrain`、`host_get_objects_in_range`、`host_path_find`、`host_get_random`、`host_get_world_config`、`host_get_world_rules`——但没有 `host_get_fuel_remaining`。玩家 WASM 代码无法查询自身剩余 fuel，无法在接近耗尽时主动缩减计算量。文档 §2.1 引擎配置注释提到 "Wasmtime ≥30 移除了 fuel_consumed_callback API；燃料检查改为在 Store 层通过 get_fuel() 轮询"——但这是引擎侧的检查，不暴露给 WASM 代码。

**影响**：玩家代码可能在不知情的情况下触发 fuel exhaustion trap——所有输出被丢弃，0 command。对于需要复杂 path_find 调用的策略（每次 2000+ fuel），玩家无法在调用前查询剩余 fuel 做决策。

**修复建议**：
1. 增加 `host_get_fuel_remaining() -> u64` host function（只读、低成本），让玩家代码能在执行中查询剩余 fuel
2. 或在设计哲学层面声明这是有意决策（迫使玩家自行估算 fuel 开销）——如果是后者，在文中明确说明

---

### ARCH-L1: 模组 `.swarm-mod` 签名包装与 Bevy Plugin 静态编译的矛盾 [Low]

**文件**：`design/README.md` 行 160-161

**问题**：README 行 160-161 描述模组发布为 `.swarm-mod` Ed25519 签名单文件包，"服主通过 `swarm mod install-vanilla` 一键安装"。但 `design/engine.md` 行 11 和 `tech-choices.md` §3 都说 "Mod = Bevy Plugin，静态编译进 Engine 二进制"。静态编译意味着 mod 是 Rust crate，编译进 Engine 二进制——不需要运行时安装签名包。`.swarm-mod` 的安装语义是运行时安装还是编译时引用？如果是编译时，则 `swarm mod install` 的含义是 "下载源码 crate → 加入 Cargo workspace → 重新编译"，签名验证的对象是什么？

**影响**：不影响核心确定性/安全，但模组分发链路有概念模糊。

**修复建议**：明确 `.swarm-mod` 与静态编译的关系——可能 `.swarm-mod` 是源码 crate 的签名打包格式，`install` 解包后加入编译依赖。需一段说明文字消除歧义。

---

### ARCH-L2: `seeded_shuffle` 代码示例与规范描述的偏差 [Low]

**文件**：`specs/core/01-tick-protocol.md` §3.1（行 249）

**问题**：行 249 的代码示例 `let seed = blake3::hash(&[&tick_number.to_le_bytes(), &world_seed]);` — 但后面的规范文本行 266 说 seed 公式是 `Blake3(\"shuffle\" || world_seed || tick.to_le_bytes())`。代码示例中 `tick_number` 在 `world_seed` 之前，且没有 domain separator `"shuffle"`。两处公式不一致——代码示例是示意性的（非可执行），但应该与规范公式匹配。

**修复建议**：更新代码示例为 `let seed = blake3::hash(format!("shuffle{}{}", world_seed, tick_number.to_le_bytes()));` 或保持伪代码但注明 "见 §3.1 正式公式"。

---

## 3. 亮点

1. **确定性合同层级清晰**：`01-tick-protocol.md` §9 确定性合同是整个设计中最成熟的部分。命令排序键的 5 层分级（priority_class → shuffle_index → source_rank → sequence → command_hash）、Blake3 XOF rejection sampling 消除模偏差、canonical JSON 遵循 RFC 8785/JCS——这些细节为跨平台 replay 一致性提供了坚实保障。

2. **Shadow Write + Atomic Publish 模型**：`01-tick-protocol.md` §3.5 将 per-room staging 写入与 GlobalTickCommit manifest-only publish 分离，消除了 "per-room 已 durable 但全局 abort" 的时序窗口。staging 行不是已提交状态、可由 GC 回收的设计干净利落。跨房间操作在 Bevy World 内预先裁决再写 staging——避免了 post-hoc overlay 合并的复杂度。

3. **TickCommitRecord 三层分离**：`05-persistence-contract.md` §2 将 replay-critical（redb 原子写入）、rich debug（对象存储异步）、WASM blob（非 replay-critical）三层清晰分离。`terminal_state` 四态分类（verified/audit_gap/unreplayable/reconstructable）为审计完整性提供了可操作的降级路径。

4. **Phase 2b 并行安全设计**：`06-phase2b-system-manifest.md` 的 Component R/W 矩阵是工程级的。Combat Parallel Set A 按 target_id partition、Status Buffer Production 按 typed buffer 隔离、S22 作为唯一 StatusState writer——并行安全证明有具体的 disjoint-set 论证，不是泛泛而谈。

5. **OS 隔离深度**：`04-wasm-sandbox.md` §9 的统一 OS 加固表覆盖了 seccomp/cgroup/namespace 三个维度，`clone` flags matrix 精确到 BPF 参数校验级别，netns 双层隔离（L1 netns + L2 seccomp）防止配置错误逃逸。这不是 "禁用危险 syscall" 的泛化描述，而是可 CI 验证的逐项 checklist。

6. **可见性函数统一**：`05-visibility.md` §1 的 "一个函数回答一切" 原则——所有输出面（WASM snapshot、MCP query、WebSocket delta、REST、replay、spectator）共用 `is_visible_to()`，缓存键 `(tick, player_id)` 防止跨输出面泄露。Oracle 防线（§10）的 `omitted_count` 分桶、特殊攻击拒绝码等价类是深思熟虑的反信息泄露设计。

7. **Command Source 模型**：`09-command-source.md` 将所有指令来源显式建模，auth_context 服务端注入不可伪造，`WorldMutate` trait 编译期约束确保无绕过。Admin 路径走标准 `validate_and_apply()` 管线而非独立代码路径——减少了特权代码面。

8. **CVE SLA 覆盖完整 Rust 生态**：`CVE-SLA.md` 不只追踪 Wasmtime，还覆盖了 14 个 critical Rust crate（blake3、ed25519-dalek、rustls 等），且要求 crypto crate 升级后执行 determinism regression test——这是对确定性系统安全维护的正确认知。

---

## 4. CrossCheck — 需要跨方向检查

- **CX-1**: `09-command-source.md` §8.1 RawCommand 顺序写 "Admin → Deploy → WASM → RuleMod → MCP_Query" 五层优先级，但 `01-tick-protocol.md` §9.1 命令全局排序键写的是 `priority_class` 四值（0=Admin, 1=WASM, 2=MCP_Deploy, 3=MCP_Query）。`Deploy` 和 `RuleMod` 在哪个 priority_class？`Deploy` 出现在 §8.1 第 2 层但不在 §9.1 的 priority_class 枚举中，`RuleMod` 在 §8.1 第 4 层但 §9.1 无对应 class → 建议 [命令校验方向] 检查 priority_class 枚举是否覆盖全部 Source 类型

- **CX-2**: `02-command-validation.md` §3.5 Attack 的 range=1，§3.6 RangedAttack 的 range=3，但 `api-registry.md` §1 的 CommandAction 表只列了 `Action dispatch`——具体 range 值应由 ActionRegistry / `special-attack-table.md` 定义。验证 `02-command-validation.md` 中写的 range=1/3 是否与 `special-attack-table.md` 一致 → 建议 [战斗机制方向] 检查 range 枚举一致性

- **CX-3**: `05-persistence-contract.md` §8.3 Synthetic Benchmark 要求 `redb room-partition commit: 1000 active players, 200 rooms, p99 < 500ms`，但 `06-phase2b-system-manifest.md` 的 31 个 system 串行 spine 执行时间在 `engine.md` §3.4.1 声称为 ≤400ms。200 个房间的 staging 写入 + GlobalTickCommit 是否在 400ms EXECUTE 预算内可完成？→ 建议 [性能方向] 检查 room-partition staging 写入的耗时对 EXECUTE 预算的挤压

- **CX-4**: `03-mcp-security.md` §7 审计日志写 ClickHouse DDL `ENGINE = MergeTree()`，但 `tech-choices.md` 已移除 ClickHouse → 建议 [安全方向] 检查审计日志存储是否应改为 redb metrics table

- **CX-5**: `04-wasm-sandbox.md` §3.2 host function `host_get_objects_in_range` 返回上限 64KB，但 `05-visibility.md` §3.1 snapshot 的 `omitted_count` 用分桶值（few/some/many/extreme）。如果 WASM 通过 `host_get_objects_in_range` 查询，返回的实体数是否也需分桶？还是 host function 返回精确 count 而 snapshot 才分桶？→ 建议 [可见性方向] 检查 host function 返回值的 oracle 防护

- **CX-6**: `09-command-source.md` §2.2 扩展来源中 `RuleMod` 的 budget 写 "Rhai op budget"，但 `01-tick-protocol.md` §9.8 说 "Rhai RuleMod：固定点数（integer，禁止 f64）"。如果 Rhai 被移除（见 ARCH-H2），这些 budget 和数值约束是否仍适用于 Bevy Plugin mod？→ 建议 [模组系统方向] 检查 mod budget 模型是否需要重新定义
