# R41 Phase 1 Architect Review — rev-dsv4-architect

**评审日期**: 2026-06-30
**评审方向**: 架构 + 安全 + 确定性 + 性能
**文档集**: 14 files (design/ 4 + specs/core/ 6 + specs/security/ 4)

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

设计核心——ECS 调度、确定性合同、Shadow Write 持久化、WASM 沙箱隔离、可见性 Oracle 防线——已达高质量水准。但存在 **3 项 Critical 级文档一致性缺陷**：tech-choices.md 明确移除了 Dragonfly/ClickHouse/Rhai，而其他多份 spec 文档仍在引用这些已移除组件。此类不一致会导致实现者分叉解读，在安全层（Rhai RuleMod source）和持久化层（Dragonfly 缓存 vs Moka）均产生合同空白。必须全局修复后重新评审。

---

## 2. 发现的问题

### C1 — Critical: 架构图中仍引用已移除的 Dragonfly 和 ClickHouse

- **文件**: `design/README.md` 行 133-136
- **问题**: 2.1 整体架构图的数据层仍展示 `Dragonfly (热缓存)` 和 `ClickHouse (分析 + 审计)`，但 `design/tech-choices.md` §6 和 §7 已明确移除这两个组件，替换为 Engine 进程内 Moka Cache 和 redb metrics table + Gateway 聚合。
- **影响**: 新人/实现者阅读 README 架构图会按 Dragonfly+ClicHouse 部署，导致与 tech-choices/specs 的严重脱节。R41 作为 clean-slate 评审，架构图是首要入口，此项必须修复。
- **修复**: 将架构图数据层更新为 `redb (世界状态 + metrics)` + `进程内 Moka Cache (读加速)`，移除 Dragonfly 和 ClickHouse 条目。

### C2 — Critical: 多份 spec 仍引用 Dragonfly

- **文件**: 
  - `specs/core/01-tick-protocol.md` 行 115、623-634、657-658、748
  - `specs/security/05-visibility.md` 行 204-219 标题
- **问题**: 01-tick-protocol 的 tick 状态机图和 BROADCAST 阶段、健康指标表、MCP 读源优先级中多处出现 `Dragonfly`；visibility 文档的「各输出面 Tick 基准」表标题也提及 Dragonfly。tech-choices.md §6 已将 Dragonfly 替换为 `moka::sync::Cache`。BROADCAST 阶段的 `Dragonfly.update(delta)` 应替换为 `MokaCache.insert_batch(delta)`。
- **影响**: 实现者按 tick-protocol（核心合同）实现时会集成 Dragonfly Redis 协议——错误架构扩散到整个广播和缓存层。
- **修复**: 全局替换 tick-protocol 和 visibility 文档中的 Dragonfly → Moka Cache。01-tick-protocol §4.2 Broadcast 的并行 fan-out 改为 `MokaCache.update(delta) || NATS.publish(...)`。§6.1 失败模式表中的 Dragonfly 条目改为 Moka Cache 条目。

### C3 — Critical: 多份 spec 仍引用 Rhai RuleMod（已被移除）

- **文件**:
  - `specs/security/09-command-source.md` §2.2 扩展来源表、§2.3 来源能力约束表
  - `specs/core/01-tick-protocol.md` §9.8
- **问题**: 09-command-source.md 的来源矩阵明确出现 `RuleMod | Rhai 规则模组 actions` 及 `Rhai op budget`，01-tick-protocol §9.8 直接标题为「RuleMod / 动态 action 边界」内含 Rhai 规范。但 `design/tech-choices.md` §3 明确「Rhai 已被移除——Bevy Plugin trait 是唯一的扩展机制」且 `design/engine.md` §3 声明「没有 Rhai 脚本层」。
- **影响**: 存在第二套扩展机制（Rhai）会在安全层开新攻击面（引擎进程内不可信脚本执行），且与「Command Validation 单一路径」原则冲突。Rhai RuleMod 拥有 `damage_entity/set_entity_flag/deduct_resource` 等能力白名单——这是绕过 WASM 沙箱的引擎内执行路径。
- **修复**: 
  - 从 09-command-source.md §2.2/§2.3 移除 RuleMod 条目。
  - 删除 01-tick-protocol.md §9.8 整个小节（Rhai 规范），或替换为 Bevy Plugin 动态 action 注册说明（不在 tick protocol 范围，应在 engine mod 系统文档）。
  - 确认 01-tick-protocol.md 行 1033 中「所有 action 必须进入 Command Validation 单一路径」的原则对 Bevy Plugin 模组保持约束。

### H1 — High: Gateway 语言不一致（Rust vs Go）

- **文件**: `design/auth.md` 行 52 vs `design/README.md` 行 82
- **问题**: auth.md 架构图中标注 `Gateway (Rust)`，README 架构图和 §2.2 仓库结构中标注 `网关 (Go)`。两者无法同时成立——Gateway 的实现语言是单选的。
- **影响**: 虽然不影响核心引擎设计，但会导致 Gateway 团队选型分歧。gateway/ 目录的代码语言决定安全审计面（Go vs Rust 的内存安全模型不同）。
- **修复**: 统一为一种语言。建议以 README.md 仓库结构为准（`gateway/ Go API 网关`），auth.md 的架构图改为 `Gateway (Go)`。

### H2 — High: 03-mcp-security.md 仍引用 ClickHouse

- **文件**: `specs/security/03-mcp-security.md` 行 377-390
- **问题**: MCP 审计日志的 SQL schema 明确针对 `ClickHouse`（`ENGINE = MergeTree()`），但 `design/tech-choices.md` §7 已将 ClickHouse 替换为 redb metrics table + Gateway 聚合。
- **影响**: 安全审计路径的实现会错误依赖 ClickHouse 部署。
- **修复**: 替换为 redb metrics table 或明确的审计存储描述。审计日志的 retention 和查询语义保持不变，仅存储后端改为 redb。

### H3 — High: Visibility 文档引用已移除的 Dragonfly 缓存

- **文件**: `specs/security/05-visibility.md` 行 204-219
- **问题**: §5「各输出面 Tick 基准」表标题和部分描述中引用 Dragonfly，但 Dragonfly 已移除。MCP/Query 读源优先级应改为使用进程内 Moka Cache。
- **影响**: Visibility 合同与缓存层实现脱节。
- **修复**: 将 Dragonfly 引用替换为 Moka Cache。

### M1 — Medium: README 架构图 Dragonfly/NATS 耦合描述

- **文件**: `design/README.md` 行 130-137
- **问题**: 架构图数据层和引擎层之间的连接语义在移除 Dragonfly 后需澄清。Moka Cache 是 Engine 进程内组件，不应出现在数据层独立框中。BROADCAST 阶段的并行 fan-out 语义需要反映 Moka Cache（进程内）+ NATS（网络）的新组合。
- **影响**: Medium——架构图是多文档的视觉锚点，不一致会产生级联误解。
- **修复**: 更新架构图数据层。进程内 Cache 在 Engine 框内标注，NATS 保持为独立基础设施。

### M2 — Medium: 05-persistence-contract 中 Dragonfly 的回退语义

- **文件**: `specs/core/05-persistence-contract.md` 行 420
- **问题**: 文档末尾「与现有文档的关系」行 420 中引用 Dragonfly，但本文件其他部分已不再讨论 Dragonfly。这是一个单点残留引用。
- **影响**: 读者会疑惑「Dragonfly 还存在吗？」
- **修复**: 移除该行中的 Dragonfly 引用，或替换为 Moka Cache。

### M3 — Medium: Snapshot 关键实体不可截断的硬上限缺失

- **文件**: `design/engine.md` §3.4.4 行 436-444
- **问题**: snapshot truncation 规则规定「关键实体（自身/Controller/target/己方 drone/攻击者）不可截断」。若玩家在极拥挤场景中有大量「己方 drone」+ 多个攻击者 + 多个 target，这些不可截断实体本身就可能超过 256KB cap。文档未定义此场景的降级行为。
- **影响**: 理论上可被滥用——攻击者在目标玩家周围部署大量自身 drone，迫使 target 的 snapshot 在「不可截断」规则下溢出。
- **修复**: 增加一条规则：当不可截断实体自身的序列化大小 > 256KB 时，按 entity_id 字典序从最远距离桶中的己方实体开始截断（关键实体仅保证「至少保留自身 + 最近 1 个 target + 最近 1 个攻击者」）。溢出时标记 `snapshot.over_budget_rejected=true` 而非静默截断。

### M4 — Medium: 模组仓库结构说明不清

- **文件**: `design/README.md` §2.2 vs `design/tech-choices.md` §3
- **问题**: README 描述 `engine/mods/` 为 git submodule（独立仓库），tech-choices 描述 Mod = Bevy Plugin 静态编译。两者并非矛盾（submodule 仓库中的代码在编译时作为 Plugin 静态链接），但 README 未说明 submodule → Bevy Plugin 的编译集成语义。新贡献者可能困惑：submodule 的代码如何在 engine build 中参与？
- **影响**: Low-Medium——不影响技术正确性但影响贡献者上手。
- **修复**: 在 README §2.2 中增加一句：「每个 submodule 仓库输出一个 Bevy Plugin crate，通过 `cargo build --features` 静态编译进 Engine 二进制。`swarm mod pack` 产出 Ed25519 签名的 `.swarm-mod` 分发包。」

### L1 — Low: 01-tick-protocol.md 中 COLLECT 阶段编号不连续

- **文件**: `specs/core/01-tick-protocol.md` 行 188-206
- **问题**: 快照构建时序边界中，步骤编号为 `[1]` → `[2]` → `[3]` → `[4]` → `[5]`，但 `[5]` 的注释行 `MCP query（swarm_get_snapshot）` 的缩进异常——它在步骤 `[4]` 的注释块内，不应该是独立的 `[5]`。MCP query 和 WASM tick 共享同一快照，MCP query 是 COLELCT 阶段的并发步骤而非子步骤。
- **影响**: 微小——不会导致实现错误，但时序边界图的精确度受影响。
- **修复**: 将 `[5] MCP query` 提升为与 `[4] WASM tick` 平级的并发步骤，或合并为 `[4] WASM tick + MCP query（并行，共读同一快照）`。

### L2 — Low: 06-phase2b-system-manifest.md 版本表中引用过时信息

- **文件**: `specs/core/06-phase2b-system-manifest.md` 行 517
- **问题**: Version 3.0.0 的变更说明中写道「S01 写入 PendingSpecialAttackIntent」和「S14 从 S01 读取 intents」，但 **R35 D3** 已修改为 A01 action_dispatch 写入 status intent buffer，S14 从 A01 的 buffer 读取（非 S01）。当前 S01 的 R/W 矩阵中 `SpecAtkIntent` 列为 `-`（不访问），但版本日志仍描述旧设计。
- **影响**: 实现者按版本日志理解数据流会误判 intent 的生产者。
- **修复**: 更新 v3.0.0 changelog 以反映 R35 D3：`A01 action_dispatch → status intent buffer → S14 reducer → S22 status_advance`。

### L3 — Low: 09-command-source.md 来源矩阵中存在冗余 Row

- **文件**: `specs/security/09-command-source.md` 行 14-23 vs 行 27-35
- **问题**: §2.1「来源矩阵」包含 `Tutorial` 行，§2.2「扩展来源」又包含 `Tutorial`。同一 source 出现在两个表中，且字段不完全一致——可能产生混淆。
- **影响**: 低——不影响功能，但 source model 的单事实源原则要求消歧。
- **修复**: 仅在 §2.1 或 §2.2 之一保留 Tutorial，另一个标注「见上表」。

### L4 — Low: 确定性保证中 BTreeMap 描述可更精确

- **文件**: `design/engine.md` §3.3 行 275
- **问题**: 确定性保证描述「禁止 `std::HashMap`（迭代顺序跨运行非确定）」——正确。但提及 `BTreeMap` 时只说了「标准库全序排列」，未提及 `BTreeMap` 的键类型约束（键必须实现 `Ord`，且 `Ord` 实现必须在所有 target 平台上一致）。`String` 的 `Ord` 在不同 Rust 版本间是稳定的（基于字节序），但自定义类型的 `#[derive(Ord)]` 依赖字段声明顺序——也应注明此约束。
- **影响**: 低——Rust `derive(Ord)` 基于声明顺序（稳定），但文档中明确列出可避免实现者使用运行时排序。
- **修复**: 增加一句：「自定义类型的 `Ord` 实现必须基于固定字段顺序（`#[derive(Ord)]` 满足此要求，手动 `impl Ord` 需文档声明排序稳定性）。」

---

## 3. 亮点

1. **Shadow Write + Atomic Publish 持久化模型**（`01-tick-protocol.md` §3.5）——将 per-room staging payload 与 GlobalTickCommit manifest-only publish 分离，彻底消除旧模型中「per-room 已 durable 但全局 abort」的时序窗口。Staging GC 在 <15s 内清理孤立数据，不存在持久化中间态。这是成熟的分布式持久化设计。

2. **Phase 2b System Manifest**（`06-phase2b-system-manifest.md`）——31 个 system 的完整 R/W 矩阵 + unique writer contract + 并行安全证明。Serial spine + 2 parallel sets 的调度清晰可验证。StatusState 的 S22 唯一 writer 合同 + S16-S22b 并行 typed buffer 生产是高并发安全的教科书设计。

3. **Oracle 防线闭合**（`05-visibility.md` §10）——`omitted_count` 分桶、统一 `NotVisibleOrNotFound` 拒绝码、special attack 拒绝码等价策略、MCP simulate/dry_run 脱敏——四条防线全覆盖了跨接口信息泄露的所有已知 Oracle 向量。这在同类游戏中极为罕见。

4. **确定性合同深度**（`01-tick-protocol.md` §9）——从 5 层 command sort key + Blake3 XOF seeded shuffle + rejection sampling 消除模偏差，到 canonical JSON (RFC 8785) + 定点整数 + `BTreeMap` 强制 + PRNG namespace 隔离。确定性保证不仅声明原则，深入到了具体数据结构和编码格式。

5. **WASM Sandbox OS 加固 Checklist**（`04-wasm-sandbox.md` §9）——seccomp BPF flags matrix (精确 clone flags)、双层网络隔离 (netns + seccomp)、cgroup io.max 限制——统一验证表中每一项都有验证命令。这是生产级沙箱基线的完整规范。

6. **Overload 抗永久锁死证明**（`02-command-validation.md` §3.17）——数学证明多攻击者协调无法突破全局冷却 + 恢复速率下限，同时 Fortify 提供清除手段。将 game design 决策转化为可验证的不变量。

7. **Deploy 完整状态机**（`05-persistence-contract.md` §2.3）——6 状态（VALIDATE → COMPILE_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE / FAILED），每步的不变量和 blob upload 异步语义清晰。`redb_version_counter` 为 replay 提供 deploy 事件的严格全序。

---

## 4. CrossCheck

以下问题超出架构方向范围，需其他方向评审员确认：

- **CX-1**: `specs/gameplay/` 目录中的特殊攻击 IDL 定义（`08-api-idl`）与 `02-command-validation.md` §3.10-3.15 中的参数表是否一致？→ 建议 **GameMechanics 方向** 检查每项 special attack 的 body part、冷却、资源消耗、抗性参数在两个文档中是否对齐。

- **CX-2**: `design/auth.md` 描述的 Server CA 签发证书格式（Ed25519 public key + usage + scope + audience）与 `api-registry.md` §9 中的 Application-Layer Certificate Envelope 字段是否一一匹配？→ 建议 **Interface/API 方向** 检查 auth_api.idl.yaml 中的 cert schema 与 design/auth.md 一致。

- **CX-3**: `design/engine.md` §3.4.2 的容量推导（500 target / 1000 hard cap）假设 `PER_CORE_FUEL_RATE = ~500M fuel/s per core`。此值未经 benchmark 验证。→ 建议 **实现方向** 在 benchmark gate（`05-persistence-contract.md` §8.3）中纳入 fuel rate 校准测试。

- **CX-4**: `specs/security/CVE-SLA.md` 的 Critical Rust crate 列表中包含 `blake3`、`ed25519-dalek`、`ring`、`rustls`。这些 crate 的版本锁定（`=X.Y.Z`）与 `cargo audit` 的兼容性是否验证过？→ 建议 **DevOps/Infra 方向** 确认 CI 中的 dep lock + audit pipeline 不会因精确版本锁定而无法获取安全补丁。

- **CX-5**: `01-tick-protocol.md` §8.1 中 `tick_hard_deadline_ms = 4000ms` 和 `tick_soft_deadline_ms = 2500ms` 与 `engine.md` §3.4.1 中的 `Tick interval = 3000ms` 之间的 1000ms gap 是设计余量还是超时容忍区？→ 建议 **Engine 实现方向** 确认 tick interval 和 hard deadline 的关系——若 interval=3000 但 hard deadline=4000，意味着 tick 可以 overrun 到 4s 才 abort，这可能导致 tick 漂移累积。

---

## 5. 评审统计

| 严重性 | 数量 | 类型 |
|--------|:----:|------|
| Critical | 3 | 文档一致性 (Dragonfly/ClicHouse/Rhai 残留) |
| High | 3 | Gateway 语言 + ClickHouse 引用 + Visibility Dragonfly |
| Medium | 4 | Snapshot 硬上限 + 模组仓库 + 持久化残留 + 架构图 |
| Low | 4 | 编号/日志/来源表/BTreeMap 细节 |
| CrossCheck | 5 | GameMechanics/API/实现/DevOps/Engine 方向 |

**结论**: 核心设计质量高，但 R41 Clean-Slate 作为「设计即终态」的定位要求所有文档统一呈现当前技术栈。3 项 Critical 级一致性缺陷（Dragonfly/ClicHouse/Rhai 在多份 spec 中残留）必须在进入 Phase 2 Speaker 评审前全局修复。