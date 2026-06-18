# R17 确定性评审 — Determinism Reviewer (DSV4 Pro)

**评审员**: rev-dsv4-determinism (DeepSeek V4 Pro)
**日期**: 2026-06-18
**Phase**: R17 Phase 1 Clean-Slate 独立评审

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 存在 1 Critical（MCP f64 泄漏进入确定性边界）、2 High（文档间排序矛盾、custom_action 缺少确定性合同），但核心确定性架构极其扎实。修复后可达 APPROVE。

---

## 2. 发现的问题

### D1 [CRITICAL] MCP Tool 输出中的 f64 泄漏 — 确定性边界未闭合

**位置**: `game_api.idl.yaml` — 多个 MCP tool 的 output_schema 中包含 `f64` 类型

**证据**:
- `swarm_get_resources` → `income_rate: f64` (L455)
- `swarm_get_path` → `distance: f64`, `cost: f64` (L610-611)
- `swarm_get_controller` → `progress: f64` (L653)
- `swarm_get_economy` → `income: f64, expenses: f64, storage_tax: f64, maintenance: f64` (L726-729)
- `swarm_get_drone_efficiency` → `efficiency: f64` (L742)
- `swarm_simulate` → `confidence: f64` (L943)

**确定性影响**:

引擎核心合约（`01-tick-protocol.md` §7.1）明确规定：「数值：整数 + 定点数，禁用 `f64`（跨平台/编译器非确定）」。然而 MCP tool 的输出 schema 直接暴露 `f64` 给客户端。存在两条泄漏路径：

1. **AI Agent 路径**：AI 玩家通过 MCP 读取这些 f64 值 → 生成 WASM 代码 → 编译部署。若 f64 在 ARM/x86 间产生不同二进制表示，AI 在不同平台读到的值不同 → 生成的代码不同 → 回放分叉。
2. **人类玩家路径**：人类看到的数据与 replay verifier 重算的数据可能因 f64 舍入差异而不一致。

**需要修复**:
- MCP 输出中所有 `f64` 改为定点整数（如 basis points × 10000 的 `u64`）或 `string`（明确序列化格式）
- `progress: f64` 在 Controller struct（`engine.md` L62-63）中已是 `u32`，MCP 层不应重新解释为 f64
- 所有比率/效率值使用 `u32` basis points 表示

**严重度**：Critical。因为 AI Agent 路径（MCP → WASM → tick）将此值纳入确定性边界——不同平台的 f64 差异将导致回放验证失败。

---

### D2 [HIGH] 文档间 status_advance_system 调度位置矛盾

**位置**: `02-command-validation.md` §3.19 vs `06-phase2b-system-manifest.md` §1

**02-command-validation.md §3.19** 描述：
```
death_mark → spawn → spawning_grace → combat → status_advance → (regeneration, decay 并行) → death_cleanup
```

**06-phase2b-system-manifest.md §1** 定义权威顺序为：
```
S07 death_marker → S08 spawn → S09 spawning_grace → S10 regeneration → 
S11-S13 combat (parallel set A) → S14 special_attack_reducer → S15 damage_application →
S16-S22 status effects (parallel set B) → S23 aging → S24 decay → S25 death_cleanup
```

**矛盾**：
1. `regeneration` (S10) 在 manifest 中位于 combat 之前，在 command-validation 中位于 status_advance 之后
2. `status_advance` (S22) 在 manifest 中位于 damage_application 之后，在 command-validation 中紧接 combat 之后
3. command-validation 将 `decay` 与 `regeneration` 并行，manifest 中是串行的 (S24 在 S23 aging 之后)

**确定性影响**：Critical——系统执行顺序是确定性合同的基石。若有两个文档声称不同顺序，实现者选择任一都会导致「合法」的分叉。回放验证时若基于另一顺序重放，结果将不匹配。

**明确性**：`06-phase2b-system-manifest.md` 声明自己为「唯一权威定义」(L4)，且有版本号 2.0.0。`02-command-validation.md` §3.19 应被修复以匹配 manifest，或删除该节改为引用 manifest。

---

### D3 [HIGH] Custom Action 缺少确定性合同

**位置**: `api-registry.md` §1.4, `game_api.idl.yaml` custom_actions 段

`Leech` 和 `Fabricate` 通过 World Action Manifest 注册为 `custom_actions`。TickTrace 记录 `world_action_manifest_hash` 以确保回放确定性。但以下缺口存在：

1. **Custom action handler 的确定性要求未声明**：handler 是否必须仅使用确定性操作？是否允许访问 f64/WASI/OS 熵源？
2. **Validator 的确定性与 handler 的关系未定义**：若 validator 拒绝某命令而 handler 可接受（或反之），在不同 World Action Manifest 版本下回放结果可能不同
3. **Leech 伤害类型为 Corrosive，含 `base_damage: 15`** (`02-command-validation.md` L823)——此伤害计算是否使用引擎确定性数值层（整数）？文档未明确

**修复建议**：
- 在 `api-registry.md` §1.4 增加「Custom Action 确定性合同」：要求 handler 仅使用引擎提供的确定性原语（PRNG/整数运算/固定排序），禁止访问 OS 熵源/f64/WASI
- 要求 custom action 的 validator 和 handler 实现同一确定性接口 trait

---

### D4 [MEDIUM] SIMD 启用时跨架构确定性缺失

**位置**: `04-wasm-sandbox.md` §2.2 L94

```rust
config.wasm_simd(world_config.simd_enabled);
// World 默认 true（性能），Arena 默认 false（确定性/公平）
```

文档明确承认 SIMD 对确定性的影响，且 Arena 默认禁用。但对于 World 模式（默认 `simd_enabled = true`）：

- x86 (AVX2/AVX-512) 与 ARM (NEON/SVE) 的 SIMD 指令行为可产生不同浮点结果
- TickInputEnvelope 记录了 `wasmtime_version` 和 `engine_abi_version`，但**未记录 CPU 架构或 SIMD 能力集**
- 回放时若在 ARM 上重放 x86 tick，SIMD 指令差异将导致 WASM 输出不同 → 确定性合同破裂

**缓解现状**：WASM 模块在 COLLECT 阶段的输出被记录到 TickTrace，回放时不重跑 WASM（`01-tick-protocol.md` §6.3.3）。这意味着 World 模式的 replay 实际上不依赖 WASM 重执行——这是一个有效的缓解措施。但文档未将此作为确定性保证的是否前提明确声明。

**修复建议**：在 `01-tick-protocol.md` §7.1 确定性合同中增加一条：「World 模式回放不重执行 WASM——回放基于记录的 Command[] + Bevy ECS 重执行。WASM 重执行仅用于二次审计验证，且要求匹配的 (wasmtime_version, cpu_arch) 环境。」

---

### D5 [MEDIUM] Build (S03) inline entity creation vs Spawn (S08) deferred creation

**位置**: `06-phase2b-system-manifest.md` §2 S03/S08

- **S03 build_system**：Phase 2a inline，立即创建 Structure entity（"Entity creation: ✅ (immediate, inline — structure appears in current tick)"）
- **S08 spawn_system**：Phase 2b deferred，从 PendingSpawn buffer 创建 Drone

Bevy ECS 中 inline immediate creation 意味着：Build 执行后的同 tick 后续 Phase 2a 命令**可见**新建的 Structure，而 Spawn 创建的 Drone 在 Phase 2a 中**不可见**。

**确定性影响**：
- 这在命令排序（shuffle→inline apply）下是确定的——Structure 的可见性取决于 Build 命令的排序位置，排序位置由 PRNG 种子洗牌决定 → 确定。
- 但创建时序的不对称性（inline vs deferred）在语义上不统一，未来新增 entity type 时可能引入 bug。

**建议**：在 manifest 中增加一条设计规则：「Phase 2a 内创建的所有 entity 在 Phase 2a 后续命令中可见；Phase 2b 创建的 entity 在下一 Phase 2a 前不可见。此语义必须对所有 entity type 一致适用。」

---

### D6 [LOW] `swarm_get_random(sequence)` 未注册在 Host Functions

**位置**: `01-tick-protocol.md` §9.5

文档描述：「WASM 代码必须使用 `swarm_get_random(sequence)` 从 host 获取确定性随机数」。但此函数未出现在 `api-registry.md` §4 Host Functions 权威列表（仅 5 个函数）或 `04-wasm-sandbox.md` §3.2 允许的白名单中。

如果存在但未注册，CI 校验（api-registry 原则 4：「新增指令/错误码/工具/函数必须在此注册，未注册的 CI 拒绝」）将阻止其使用。如果不存在，则 WASM 无途径获取随机数——这本身是安全的（WASM 不应自行生成随机数），但文档描述具有误导性。

---

### D7 [LOW] Rhai RuleMod 确定性仅一句约束

**位置**: `01-tick-protocol.md` §9.8 L857-858

对 Rhai RuleMod 的确定性约束仅一句话：「固定点数（integer，禁止 f64）；禁止第二套状态修改路径；扩展 action 必须通过 World Action Manifest + IDL 注册 schema」。没有：
- 强制执行机制（编译期检查？运行时拒绝？）
- Rhai 是否可调用非确定性 host function？
- Rhai 迭代器的顺序保证？

对于一种图灵完备的嵌入式脚本语言，一句约束不足以构成确定性合同。

---

### D8 [LOW] `path_find` cache key 中的 `player_visibility_fingerprint` 未定义

**位置**: `04-wasm-sandbox.md` §8 L355

缓存键 `(from, to, terrain_hash, player_visibility_fingerprint)`——`player_visibility_fingerprint` 的计算方式未定义。此指纹必须仅依赖确定性状态（玩家位置、可见性过滤器结果、fog-of-war 状态），不能依赖墙钟或并行调度。

当前实现中可见性本身应该是确定性的（基于 snapshot + fog-of-war filter），但 fingerprint 作为缓存键需要显式定义以确保跨 replay 一致。

---

## 3. 亮点

1. **确定性核心合同极其扎实**（`01-tick-protocol.md` §7）：
   - PRNG: Blake3 XOF，种子确定性派生，namespace 隔离
   - Hash: Blake3 固定实现，不用 `std::hash`
   - 排序: 5 层 canonical sort key `(priority_class, shuffle_index, source_rank, sequence, command_hash)` — 无歧义
   - 数据结构: IndexMap 替代 HashMap，StableEntityId 替代 archetype order
   - 数值: 整数 + 定点数，显式禁止 f64
   - 种子洗牌: Fisher-Yates with Blake3——确定且公平

2. **Complete Tick Execution Manifest** (`06-phase2b-system-manifest.md`)：29 systems，serial spine + 3 parallel sets，完整的 R/W 矩阵覆盖全部 systems。明确了每个 system 的迭代键（StableEntityId 或 canonical key），并行安全有形式化证明。此文档是确定性合同的基石。

3. **Bevy World Snapshot/Restore** (`01-tick-protocol.md` §3.5, §9.3)：FDB commit 失败时完整恢复 Bevy World（所有 Component + Resource）——确保重试的确定性。快照范围清单完整覆盖了所有必须捕获的 Resource 类型和 Component 类别。

4. **COLLECT 跨重试缓存** (`05-persistence-contract.md` §6, `01-tick-protocol.md` §8.4)：FDB commit 失败重试时复用 COLLECT 结果，不重新执行 WASM。`collect_id` 不变，`attempt_id` 递增，fuel 不追加扣费。这是防止「重试非确定性」的关键设计。

5. **TickInputEnvelope 完整性** (`api-registry.md` §6, `05-persistence-contract.md` §6.1)：`collect_id`/`attempt_id`/`commit_id` 三层标识 + `module_hash`/`wasmtime_version`/`snapshot_hash`/`commands_hash`/`world_config_hash`/`mods_lock_hash`/`engine_abi_version`/`system_manifest_hash`/... 共 22 字段。完整性超过典型游戏引擎的审计需求。

6. **确定性快照截断** (`01-tick-protocol.md` §2.3)：分桶权重 + `(distance, entity_id)` 排序键——完全基于世界状态中的确定性值。`sort_and_truncate` 结果由 `(tick_state, player_visibility_fingerprint)` 唯一确定。

7. **回放不重跑 WASM** (`01-tick-protocol.md` §6.3.3)：TickTrace 记录 `Command[]` 而非 WASM 输出。回放时直接执行已记录指令序列——Wasmtime 版本/CPU 架构变更不影响回放。这是对抗 WASM 层非确定性的终极防线。

8. **种子前向保密威胁模型** (`01-tick-protocol.md` §3.1)：明确分析了 `world_seed` 泄露的影响面、已接受的残余风险、缓解措施和应急 runbook。这是极少在设计文档中看到的安全工程严谨度。

9. **SpawningGrace 机制** (`06-phase2b-system-manifest.md` S09, `engine.md` §3.2)：出生 tick 免疫——防止「先到先得」排序中的 spawn-kill 竞争。`SpawningGrace { remaining: 1 }` 精确的时序保证（combat 之前附加，combat 时 filter 生效）是确定的。

10. **Overload 抗永久锁死证明** (`02-command-validation.md` §3.17)：数学证明不存在一组攻击者能通过协调 Overload 永久锁死目标 fuel budget。全局冷却 + 恢复速率 + 下限保护的形式化论证——罕见但关键的正确性保证。

11. **CI 确定性验证管线** (`01-tick-protocol.md` §7.4, §3.5)：每 CI run 随机选取 5% tick 做 full replay + `state_checksum` 比较。FDB 故障注入 CI 测试验证 snapshot restore 一致性。覆盖重放完整性和故障恢复两个维度。

12. **Phase 2b 并行安全证明** (`06-phase2b-system-manifest.md` §4)：按 target_id partition 的 Combat 并行、按 StatusState subtype 的 Status Effects 并行、RoomCap 中间态保护——所有并行路径有形式化 R/W 冲突分析。

13. **Spawn body_cost refund 原子性** (`02-command-validation.md` §3.8, `01-tick-protocol.md` §9.4)：Phase 2a 扣费 → Phase 2b spawn 创建失败 → 全额退还。refund 路径完整覆盖了 spawn.energy 容量不足时的全局存储回退，且与 fuel refund 池隔离。

---

## 4. CrossCheck

### 4.1 跨文档一致性

| 检查项 | 文档 A | 文档 B | 状态 |
|--------|--------|--------|:--:|
| f64 禁令 | `01-tick-protocol.md` §7.1: "数值：整数 + 定点数，禁用 `f64`" | `game_api.idl.yaml`: 多处 f64 在 MCP output_schema | ❌ **矛盾** → D1 |
| status_advance 调度 | `02-command-validation.md` §3.19: status_advance 在 combat 之后、regen 之前 | `06-phase2b-system-manifest.md` §1: status_advance (S22) 在 dmg_apply 之后 | ❌ **矛盾** → D2 |
| CommandAction 总数 | `api-registry.md`: 19 (11+2+6) | `game_api.idl.yaml`: total_variants: 19, 含 custom_actions 2 个未计数 | ✅ 一致 |
| RejectionReason 总数 | `api-registry.md`: 35 | `game_api.idl.yaml`: total_variants: 35 | ✅ 一致 |
| Host Functions 数量 | `api-registry.md` §4: 5 | `04-wasm-sandbox.md` §3.2: 5 | ✅ 一致 |
| Phase 2b system 总数 | `engine.md` §3.2: "23" | `06-phase2b-system-manifest.md`: S07-S29 = 23 | ✅ 一致 |
| TickInputEnvelope 字段 | `engine.md` §3.3: 17 fields (含R16 B3) | `api-registry.md` §6: 22 fields | ✅ api-registry 是权威源，engine.md 引用之 |
| Drone lifespan 默认值 | `engine.md` §3.1: DEFAULT_DRONE_LIFESPAN = 1500 | `api-registry.md` §5: 1500 tick | ✅ 一致 |
| MAX_BODY_PARTS | `api-registry.md` §5: 50 | `02-command-validation.md` §3.8: MAX_BODY_PARTS (50) | ✅ 一致 |
| Commands/player/tick | `api-registry.md` §5: 100 | `02-command-validation.md` §1.1: MAX_COMMANDS_PER_PLAYER (100) | ✅ 一致 |
| Seed shuffle 种子公式 | `engine.md` §3.3: Blake3("shuffle" \|\| world_seed \|\| tick.to_le_bytes()) | `01-tick-protocol.md` §9.1: 同上公式 | ✅ 一致 |

### 4.2 确定性关键路径闭合检查

| 关键路径 | 确定性保证 | 状态 |
|---------|----------|:--:|
| 世界状态 → snapshot | 一次性构建 → 按房间分片 → 确定性 | ✅ |
| snapshot → WASM tick() | 只读访问，256KB cap，超限确定性截断 | ✅ |
| WASM 输出 → Command[] | JSON schema 校验，超限丢弃，不保留部分 | ✅ |
| Command[] → 排序 | 5 层 canonical sort key + Blake3 tiebreaker | ✅ |
| 命令 → inline apply | 逐条基于当前 Bevy World，PRNG shuffle | ✅ |
| Phase 2b ECS | 29 systems serial spine + manifest 权威顺序 | ✅ |
| FDB commit | 原子事务，失败 → snapshot restore → 重试（复用 COLLECT） | ✅ |
| 状态 → 持久化 | TickTrace 同一 FDB 事务，hash chain 验证 | ✅ |
| Replay | 基于记录 Command[] + Bevy ECS 重执行，不重跑 WASM | ✅ |
| WASM 跨架构 | World: SIMD=true 默认, 回放不重跑 WASM | ⚠️ → D4 |
| MCP f64 → AI agent | f64 值进入 WASM 生成逻辑 → 潜在非确定 | ❌ → D1 |

### 4.3 Replay Gaps

只有一个实质 gap：

- **MCP f64 泄漏** (D1)：AI agent 通过 MCP 读取 f64 值 → 跨平台差异 → 生成不同 WASM 代码 → 回放分叉。此 gap 的缓解措施是 TickTrace 记录 Command[] 而非 WASM 输出（回放不重跑 WASM），但若 AI agent 在不同平台生成不同代码，则同一玩家在不同平台会有不同的 `module_hash`——这是更深层的一致性问题。

其他路径已闭合：COLLECT 缓存、snapshot restore、hash chain、canonical sort key 全部覆盖。

### 4.4 Formal State Issues

1. **Build inline creation vs Spawn deferred creation** (D5)：两种 entity 创建时序语义不一致——inline immediate 与 deferred flush。在 manifest 层面已有 R/W 矩阵保护，但语义差异值得显式文档化。

2. **SIMD 作为隐式非确定性源** (D4)：World 模式默认 `simd_enabled=true` 意味着 WASM 执行依赖 CPU 架构。当前回放不重跑 WASM 缓解了此问题，但若未来需要 WASM 级审计回放（如反作弊重放），此 gap 将成为 blocker。

---

## 5. 总结

**核心确定性架构评级：A (90/100)**

Swarm 的确定性设计是同类项目中最严谨的之一。Blake3 XOF PRNG、IndexMap、5 层 canonical sort key、29 system manifest + R/W 矩阵、Bevy snapshot/restore、COLLECT 跨重试缓存、TickInputEnvelope 22 字段——这套组合已经超越了绝大多数游戏引擎的确定性保证。

**需要修复以达 APPROVE**：
1. **D1 [Critical]**：MCP tool output 中所有 f64 改为定点整数或确定性序列化格式
2. **D2 [High]**：修复 `02-command-validation.md` §3.19 的调度顺序，统一到 `06-phase2b-system-manifest.md` 的权威定义
3. **D3 [High]**：为 custom_actions 补充确定性合同（handler/validator 的确定性约束）

D4-D8 为 Medium/Low，可在 APPROVE 后作为 follow-up 修复。核心路径已闭合。
