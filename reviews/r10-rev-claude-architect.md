# R10 架构评审报告 — Architect Reviewer (Claude Opus 4.8)

**评审日期**: 2026-06-14
**评审范围**: r10-arch-summary.md (基于 DESIGN.md + tech-choices.md + ROADMAP.md + P0-01/02/04/08/09)
**评审维度**: 全局架构一致性 | Tick 协议正确性 | 确定性合同完整性 | 信任边界 | Phase 过渡风险
**同行参考**: rev-dsv4-architect + rev-gpt-architect 已阅，独立判断，只在共识处标注

---

## VERDICT: REQUEST_CHANGES

架构骨架正确，Phase 0 的方向性决策（Deferred Command、三层信任、Blake3 单原语、MCP 不载 gameplay）已达到冻结质量。但 Phase 1 的编码闸门前有 3 个硬阻断和 4 个结构性问题必须解决——这些问题在任何正经的实现尝试中不可避免地会导致返工。两个同行评审（dsv4 和 gpt）覆盖了大部分发现，我在下方注明共识和分歧，并补充了 2 个两者都未触及的架构级关注点。

**Phase 1 可开始的条件**: 解决以下 C1-C3（阻断），并将 S1-S4（结构性）纳入 Phase 1.0 的 contract hardening 阶段。

---

## 评审前注：与 dsv4/gpt 同行的共识与分歧

| 发现 | dsv4 | gpt | Claude Opus |
|------|------|-----|-------------|
| Source.produces HashMap 残留 | D1-1 ✅ | 未显式提及 | 同意 dsv4 — C1 阻断 |
| Wasmtime 版本 vs 回放 | D1-2 ✅ | 隐含在 A7 | 同意 dsv4 — 但是否多版本 Wasmtime 可行性存疑，见 C2 |
| COLLECT 读取源未定义 | D1-3 ✅ | 未显式提及 | 同意 dsv4 — 但认为后果比 dsv4 描述的更严重，见 C3 |
| TickStore 边界未冻结 | 未提及 | A1 ✅ | 同意 gpt — 这是 Phase 1→3 最大架构风险 |
| ClientCommand/AuthenticatedCommand 未分离 | 未提及 | A2 ✅ | 强同意 gpt — 这是最危险的 confused deputy 入口 |
| WASM ABI 语义歧义 | 未提及 | A3 ✅ | 同意 gpt — 但认为还有更深层的 ABI 契约缺失，见 S1 |
| RuleMod capability 漂移 | D2-1 部分 | A4 ✅ | 同意两者 — Rhai 的第二写路径必须用独立管线约束 |
| IDL single source 无真实 artifact | 未提及 | A5 ✅ | 强同意 — 直到 game_api.idl 文件存在前，不存在"单一真相来源" |
| 配置 fixed-point 与示例浮点冲突 | 未提及 | A6 ✅ | 同意 gpt |
| Drone lifespan reset 可滥用 | D2-2 | 未显式提及 | 同意 dsv4 的问题定位，但认为是游戏设计问题而非架构阻断 |
| EXECUTE 超时无策略 | D2-3 (遗留) | 未显式提及 | 同意 dsv4 |
| PLANNER-OUTPUT.md 过时 | D2-4 | 未提及 | 同意 — 应删除，见 S4 |
| TickTrace 写入矛盾 | CG-2 | 未提及 | 同意 dsv4 |
| 批量 snapshot 序列化内存 | AR-1 | 隐含在 A7 | 同意 dsv4 的定量分析 |
| **新发现: Tick 边界 FDB vs Bevy 一致性契约缺失** | 未提及 | 未提及 | **本次新发现 — S2** |
| **新发现: Phase 1 的 in-memory 模式缺少 FDB 语义对等要求** | 未提及 | 隐含在 A1 但未展开 | **本次新发现 — S3** |

---

## C1-C3: 阻断级 (Phase 1 编码前必须解决)

### C1 — BLOCKER — 确定性合同中的 HashMap 残留需全量审计

**与 dsv4 D1-1 共识**。

R9 D2-2 只修复了 `Resource.amounts: HashMap → IndexMap`，但 `Source.produces` 仍为 HashMap。dsv4 的发现正确——任何 `>1` 种资源产出的世界都无法保证回放确定性。

但问题比 dsv4 指出的更深：**这是一个模式问题，不是一个单点 bug**。三次评审迭代（R8→R9→R10）中，每次我们都发现新的 HashMap 残留。这说明用"发现问题→修复单个"的方法不收敛。

**系统性修复要求**:

1. 在 Rust 代码库中引入 clippy lint 或编译期检查，禁止在 ECS 组件和世界状态 struct 中使用 `HashMap`，仅允许 `IndexMap`/`BTreeMap`/`Vec<(K,V)>`
2. 确定性合同文档应新增一条规则："任何在 tick 执行过程中被迭代的集合类型必须具有确定的迭代顺序。这包括 ECS 组件的所有字段和系统间传递的数据结构"
3. CI 应包含静态分析检查——例如 `rg "HashMap" --type rust` 后人工审核白名单（允许 HashMap 之处需显式注释 `// DETERMINISM_OK: used only for lookup, never iterated`）

**严重性**: 阻断。任何遗漏的 HashMap 意味着回放保证在对应的世界配置下完全破裂——这不是性能问题，是正确性问题。

---

### C2 — BLOCKER — Wasmtime 版本锁定与安全 SLA 的根本矛盾

**与 dsv4 D1-2 共识，但结论有分歧**。

dsv4 正确识别了矛盾：`=30.0` 锁定 + "72h CVE 响应" + 回放依赖精确 Wasmtime 版本。但 dsv4 把"多版本 Wasmtime 共存"作为方案 A，我认为**多版本 Wasmtime 方案可行性存疑**：

- Wasmtime 的 C API 和内部结构在 major 版本间变化显著
- 维护 N 个 Wasmtime 版本 = N 个安全攻击面，而非 1 个
- 每个版本需要独立编译、独立 sandbox worker、独立进程管理
- 与 Rust 生态的单版本链接模型冲突

**更可行的架构方案**: 在 TickTrace 中**总是记录已校验的 Command[]**。回放时：
- **正常模式**: 用当前 Wasmtime 版本重新执行 WASM，验证 `recorded_commands == replayed_commands`
- **降级模式**: 当验证失败时（Wasmtime 升级导致），**跳过 WASM 执行，直接使用记录的 Command[] 驱动世界状态机**，并标记回放为 `replay_fidelity: degraded` 附带 wasmtime_version_diff 元数据

这从根本上解耦了"Wasmtime 版本"与"世界状态回放"——Command[] 成为回放的最小充分数据集，WASM 执行降级为优化（验证而非依赖）。

**必须在 P0-4 新增"回放兼容性策略"节**，明确：回放的首要数据源是 `TickTrace.commands[]`，次要数据源是 WASM re-execution（用于交叉验证）。Phase 1 的 TickTrace schema 必须包含完整的 `commands` 字段，不可省略。

---

### C3 — BLOCKER — COLLECT 阶段数据源与 FDB 的关系未定义

**与 dsv4 D1-3 共识，但认为后果更严重**。

dsv4 正确指出 P0-1 §2.3 未声明 `all_entities` 来源。我补充一个更深层的架构问题：

**COLLECT 和 EXECUTE 之间，Bevy World 与 FDB 的关系契约完全缺失**。

当前隐含模型：
- COLLECT 从 Bevy World 读取（快速、内存）
- EXECUTE 写入 FDB 后，Bevy World 从 snapshot 恢复以匹配 FDB
- 下一 tick 的 COLLECT 再次从 Bevy World 读取

但以下场景无定义：

1. **COLLECT 中途 FDB 状态变更**: 如果 tick N 的 COLLECT 正在读取 Bevy World，而 tick N-1 的 EXECUTE 恰好在这时 FDB commit 成功并触发了 `world.restore(snapshot)`，COLLECT 读到的是哪个版本？
2. **Bevy World 崩溃重建**: 进程重启后，Bevy World 从何处初始化？从 FDB 的最新 committed state？还是从本地快照？启动时 FDB 读取的延迟是否计入 tick 计时？
3. **双读路径一致性**: 某些 host function（如 `host_get_world_rules`）可能从 Rhai 引擎或配置文件读取而非 Bevy World——这些非 ECS 数据的 tick 一致性如何保证？

**修复要求**:

在 P0-1 新增"Tick Boundary Contract"节，明确定义：
```
tick N 的 COLLECT 的读取一致性边界:
  - 所有 ECS 组件: 从 Bevy World 读取，Bevy World 反映 tick N-1 EXECUTE 完成后状态
  - 世界配置/规则: 从配置快照读取，在 tick 开始时固化为不可变引用
  - FDB: COLLECT 期间不读取 FDB
  - Dragonfly: COLLECT 期间不读取 Dragonfly（防止读到未提交数据）

tick N 的 COLLECT → EXECUTE 过渡:
  - EXECUTE 启动时，所有 COLLECT 的 WASM 执行已完成
  - EXECUTE 期间，Bevy World 可变（应用指令），其他读取路径冻结
  - FDB commit 成功后，Bevy World 快照更新为 post-EXECUTE 状态
```

---

## S1-S4: 结构性 (Phase 1 开工前应冻结)

### S1 — HIGH — WASM ABI 契约缺失项比 gpt A3 指出的更多

**在 gpt A3 基础上补充**。

gpt 正确指出了 `tick()` 返回值的 ptr/len/error 歧义。但完整的 WASM ABI 契约还缺失：

1. **snapshot 的线性内存布局**: `tick(snapshot_ptr, snapshot_len)` — 但 snapshot 是 JSON 字符串？MessagePack？自定义二进制格式？如果 Phase 1 用 JSON、Phase 3 切到 MessagePack 以优化序列化开销，所有 bot 需要重编译
2. **host function 的错误传播**: 如果 `host_path_find` 失败（内存不足、path 不存在），返回值是什么？(-1, 0, 特殊 sentinel？) — gpt/DESIGN/P0-4/P0-8 都未定义
3. **WASM 内存释放契约**: WASM 内的 `tick()` 返回后，snapshot 内存何时释放？host 是否负责释放？还是 guest 在下一次 tick 调用时复用？
4. **ABI version negotiation**: 如果 SDK 版本与引擎版本不匹配，如何检测？`host_get_abi_version()` → `(major, minor)` 然后 bot 自行判断兼容性？

**建议**: 在 game_api.idl 中定义 `abi` section，包含：
- `snapshot_encoding: json | msgpack | custom`
- `tick_signature: (snapshot_ptr: i32, snapshot_len: i32) -> (cmd_ptr: i32, cmd_len: i32, status: i32)`
- `error_sentinel: -1`
- `host_function_errors: enum { Ok, OutOfMemory, InvalidArgs, NotAllowed }`
- `abi_version: { major: u16, minor: u16 }`

### S2 — HIGH — COLLECT 并行执行中 Bevy World 的只读借用未定义

**dsv4 和 gpt 都未提及**。

COLLECT 阶段并行执行 N 个 WASM 实例，每个调用 `host_get_objects_in_range`、`host_get_terrain` 等只读 host function。这些 host function 需要读取 Bevy World 的 ECS 数据。

如果 Bevy World 在 COLLECT 期间是**不可变的共享引用**（`&World`），并行读取天然安全。
但如果任何 host function 需要**内部可变性**（如缓存 path_find 结果、更新访问统计），就需要同步机制。

当前文档未定义：
- COLLECT 期间 Bevy World 的并发模型：`&World`（只读共享）还是 `RWLock<World>`（读写锁）？
- host function 是否可以缓存（如 path_find 结果）？缓存是否需要同步？
- `host_path_find` 如果内部使用 Bevy 的 ECS query，这是否与 COLLECT 的并行语义冲突？

**建议**: P0-1 新增："COLLECT 期间，Bevy World 以不可变引用 `&World` 提供。所有 host function 必须是无副作用的纯读取。不允许缓存或内部可变性。path_find 等计算密集操作的结果可以缓存在每个 WASM 实例的本地栈上，不跨实例共享。"

### S3 — HIGH — Phase 1 in-memory 模式必须实现与 FDB 同构的 tick 语义

**gpt A1 指出了 TickStore 边界问题，但未展开实现约束**。

Phase 1 用 in-memory/local-log TickStore 是正确的工程策略，但必须满足以下同构要求，否则 Phase 3 接 FDB 时整个 tick 循环需要重写：

1. **`commit_tick()` 必须是原子操作** — 即使 in-memory 实现只是一个 `Vec<TickRecord>` push，也要暴露 `fn commit_tick(&mut self, record: TickRecord) -> Result<(), CommitError>` 而非 `push(record)`。Phase 3 换成 `FdbTickStore` 时只改 backend，不改调用方
2. **"commit before broadcast" 不变式** — in-memory 实现必须在 `commit_tick()` 返回 `Ok(())` 之后才发送 NATS 广播。如果 in-memory 先广播再记录，Phase 3 无法保证相同顺序（FDB commit 可能失败）
3. **TickTrace schema 兼容** — Phase 1 的 in-memory TickTrace 结构与 FDB 的 `/tick/{N}/...` 键空间结构对应。不能 Phase 1 用 flat JSON、Phase 3 换结构化 key path
4. **`TickStore` trait 必须有 `load_tick(tick_number) -> Option<TickRecord>` 方法**（用于回放和 gap recovery），即使 Phase 1 只有内存实现

**建议**: Phase 1.0 先定义 `TickStore` trait 并完成 `InMemoryTickStore` 实现，CI 测试 trait contract。Phase 3 的任务是 "FdbTickStore 实现已有 trait" 而非 "引入持久化语义"。

### S4 — MEDIUM — PLANNER-OUTPUT.md 应删除而非归档

**与 dsv4 D2-4 共识**。

PLANNER-OUTPUT.md 包含已在 P0 规范中被明确推翻的内容（McpPlayerExecutor、MCP 游戏动作工具、AI 不需 WASM）。dsv4 的方案 A（删除）是正确的。

但在删除前应先验证：
- 文件中的有效信息（如仓库结构建议）是否已被 DESIGN.md 或 ROADMAP.md 吸收
- 是否有其他文件交叉引用 PLANNER-OUTPUT.md

---

## 已确认的结构性风险（来自 dsv4/gpt，Claude Opus 确认）

以下发现我完全同意同行评审，不需重复展开，但在此确认以建立完整审计链：

| 发现 | 来源 | 确认 |
|------|------|------|
| ClientCommand 与 AuthenticatedCommand 未分离 | gpt A2 | **同意** — confused deputy 入口，必须在 Phase 1 前冻结两层类型 |
| RuleMod capability 在三处漂移 | gpt A4 | **同意** — 第二写路径需独立 RuleActionPipeline |
| IDL 无真实 artifact | gpt A5 | **同意** — 直到 `game_api.idl` 文件存在并 CI-gated 前，不存在单一真相来源 |
| 配置 fixed-point 示例冲突 | gpt A6 | **同意** — 必须冻结解析器行为，TOML float 必须在配置层拒绝 |
| Wasmtime per-tick fork 性能未 spike | gpt A7 | **同意** — Phase 1 必须有 50/100 bot 基准测试 |
| Rhai mini-validator 未定义 | dsv4 D2-1 | **同意** — P0-7 缺完整规范 |
| Drone lifespan reset 可滥用 | dsv4 D2-2 | **同意问题存在，但归类为游戏设计而非架构阻断** — Designer 应在 Phase 6 前解决 |
| EXECUTE 超时无策略 | dsv4 D2-3 | **同意** — 需部分完成策略 |
| TickTrace 写入矛盾 | dsv4 CG-2 | **同意** — 与 FDB 事务一致性矛盾 |
| host_get_world_rules 在 P0-4 缺失 | dsv4 CG-1 | **同意** — 安全文档白名单不完整 |
| 批量 snapshot 序列化内存 | dsv4 AR-1 | **同意** — 500 玩家 × 200KB 需并行策略 |
| Tick 放弃后延迟重试雪崩 | dsv4 AR-2 | **同意** — 建议指数退避 |

---

## Strengths (不应改动的架构决策)

1. **Deferred Command Model 是 Swarm 的宪法**。DESIGN.md + P0-2 + P0-4 三处对 "WASM → tick() → JSON → 引擎校验执行" 的约束完全一致，无任何 mutating host function 例外。这是整个系统最关键的架构不变式——它使得确定性回放、MCP 公平性、防作弊在同一个合同下收敛。

2. **三层信任模型 (WASM/Rhai/Rust) 精确对应三种隔离级别**: 进程隔离 (seccomp+cgroup)、语言沙箱 (AST 解释+预算)、编译期+审计。没有模糊地带——每种信任级别的能力和限制可以精确定义。

3. **Blake3 单原语策略**: 哈希/PRNG/代码签名统一，依赖栈减 30%，审计面减半，且确定性合同中 PRNG 的 `seed||offset` 模型简洁且可验证。

4. **Source Gate (P0-9) 是纵深防御的正确位置**: 在管线入口处区分 12 种来源并限制能力，而非让每个 validator 自行判断。`MCP_Deploy` 不能发 gameplay 指令——这是一个简洁的规则，消除了整个 MCP-as-game-controller 攻击面。

5. **MCP 不做游戏动作**: AI agent 和人类走完全相同的 WASM 代码路径。这不是安全措施，是架构公平性——它确保了无论未来 API 如何演变，AI 永远是"一个会写代码的玩家"而非"一个有特权的 bot"。

6. **世界规则可配置 (world.toml + Rhai)**: 伤害类型像资源类型一样是数据而非代码，模组不需要 fork 引擎。这是 MMO 长期运营的正确架构——规则引擎承载差异化，引擎核心承载稳定性。

7. **COLLECT 宽容失败 (`未响应 → 空指令`)** 是正确的分布式系统设计。在 500 玩家的 MMO 中，不允许一个玩家的慢 WASM 阻塞整个 tick。这比"严格超时 → tick 失败"更符合在线游戏的可用性要求。

8. **Fuel Refund 的三层防滥用** (退还时序 + Deploy-reset + 同源不重复) 设计精巧。`Deploy-reset 规则`（模块变更后 credit 作废）是 R9 时期不存在的增量——它堵住了"囤积退还 credit → 部署超大模块 → 瞬间消耗"的路径。

---

## Phase 顺序建议

当前 ROADMAP 的 Phase 1 定义过于乐观——直接跳到"Core MVP"跳过了一些前置契约工作。建议：

```
Phase 1.0 — Contract Hardening (2-4 天)
  ├─ C1: 全量 HashMap 审计 + clippy lint + CI gate
  ├─ C2: P0-4 回放兼容性策略 (Command[] 记录方案)
  ├─ C3: P0-1 Tick Boundary Contract
  ├─ S1: game_api.idl ABI section 冻结
  ├─ S2: COLLECT 并发模型定义
  ├─ S3: TickStore trait + InMemoryTickStore + 测试
  ├─ gpt A2: ClientCommand/AuthenticatedCommand 两层类型
  ├─ gpt A5: game_api.idl 文件 + generator skeleton + CI gate
  ├─ gpt A6: 配置 fixed-point 冻结
  ├─ dsv4 CG-1: P0-4 host function 列表补全
  └─ S4: 删除 PLANNER-OUTPUT.md

Phase 1.1 — Deterministic Single-Player Core (4-6 周)
  ├─ Bevy ECS .chain() + state_checksum + TickTrace min loop
  ├─ InMemoryTickStore (实现 Phase 1.0 定义的 trait)
  ├─ Sandbox worker spike (50/100 bot 基准测试)
  └─ Tick-level replay verify (CI 随机采样)

Phase 2 — Multiplayer + Source Gate + Visibility (6-8 周)
Phase 3 — FDB TickStore backend + Rhai RuleActionPipeline (6-8 周)
...
```

核心调整：**Phase 1 拆分为 contract hardening（编码前）和 core implementation（编码）**。contract hardening 的输出是冻结的接口定义——`TickStore` trait、`game_api.idl`、ABI spec、`ClientCommand`/`AuthenticatedCommand` 类型——这些是"一旦开始写实现就不能再改"的接口。

---

## 进入 Phase 1 的最低条件

| 条件 | 类型 | 优先级 |
|------|------|--------|
| C1: HashMap 全量审计完成，CI gate 上线 | 阻断 | P0 |
| C2: 回放兼容性策略确定并写入 P0-4 | 阻断 | P0 |
| C3: Tick Boundary Contract 写入 P0-1 | 阻断 | P0 |
| gpt A2: ClientCommand/AuthenticatedCommand 冻结 | 高危 | P0 |
| gpt A5: game_api.idl artifact 存在 + CI gate | 高危 | P0 |
| S1: WASM ABI 契约冻结 | 高危 | P1 |
| S3: TickStore trait 定义 | 高危 | P1 |
| gpt A6: fixed-point 配置规范 | 中危 | P1 |
| dsv4 CG-1: P0-4 host function 补全 | 中危 | P1 |

满足以上 9 项后，架构从 REQUEST_CHANGES 升级为 **APPROVE**，Phase 1 可开始实现。

---

*评审完成于 2026-06-14 | Claude Opus 4.8 | Architect Reviewer*
