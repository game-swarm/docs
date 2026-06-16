# Swarm 架构评审报告 — R2

**评审员**: rev-claude-architect (Claude Opus 4.7 — 架构师方向)
**评审日期**: 2026-06-16
**评审范围**: DESIGN.md (2300 行), ROADMAP.md, specs/01-09, api/*, 同方向 R2 评审 (rev-dsv4-architect, rev-gpt-architect)
**评审视角**: 组件边界 / 边界突破的爆炸半径 / 10→10k 规模化的瓶颈点 / 7 Phase 依赖图与并行机会
**R2 焦点**: 系统在「边界突破」与「规模拐点」两个维度是否能站住——而不只是「正确实现时是否对」。

---

## Verdict

**APPROVE_WITH_RESERVATIONS — 但前提是 R2 spec convergence patch 必须先做完，否则降级为 REQUEST_MAJOR_CHANGES**

我和 rev-dsv4-architect、rev-gpt-architect 在 D1-D5 spec convergence 上完全同向：DESIGN 已经走对了，specs 没跟上，这一点不重复论证。**我承担一个不同的角度**：

1. **边界穷举**：列出 9 条系统边界，逐条演练「如果这条边界破裂，爆炸半径多大？」
2. **规模穷举**：在 10 / 100 / 500 / 1000 / 5000 / 10000 玩家这 6 个台阶上，逐条找瓶颈拐点
3. **7 Phase 依赖图重排**：现有 Phase 排序（Spec Convergence → 生成链 → Tick → Visibility → Performance → 动态规则）实际上有 **3 处可并行**和 **2 处隐藏依赖**没有暴露

R2 的核心架构方向（WASM 唯一执行器、Deferred Command Model、`is_visible_to` 单点抽象、Source Gate、Two-Phase Snapshot、FDB 权威源 + Bevy 工作副本）**全部是正确的成功模式**。但这些模式只有在 spec 收敛之后才真正生效——分裂的 spec 让正确的架构变成纸面正确。

---

## Strengths

1. **Source Gate 是这个系统最重要的边界，且边界画得干净**
   `CommandIntent → RawCommand → ValidatedCommand` 的三段式让 trust boundary 有名字、有位置、有静态类型保证。WASM 可写的字段只有 `sequence` + `action`——`player_id` / `tick` / `source` / `auth` 全部服务端注入。这条边界一旦守住，IDOR / 身份伪造 / cross-player command injection 这些类（不是单点）漏洞被结构性消除。Screeps 当年的多个事故都是因为没有这条边界。

2. **WasmSandboxExecutor 是唯一执行器，AI 不是特殊玩家**
   这是 R1 之后最重要的架构胜利。`McpPlayerExecutor` 一旦存在，公平性、确定性、回放、anti-cheat、fuel metering 这五条不变量同时被破坏——它们只能在「同一个执行面」上闭合。R2 把这条边界写死在 specs/01 §2.1，非常关键。

3. **`is_visible_to` 是唯一可见性函数，所有出口均经过它**
   snapshot / MCP query / WS push / REST / replay 全部强制绕这一条函数（specs/05 §3）。这把「信息泄露」从「散落在 N 个 endpoint 里的 N 个 bug」变成「**一个**函数的正确性问题」。Mass-assignment / 调试接口超权 / 旁观者越权这一类问题被一次性收拢。

4. **Two-Phase Snapshot 把复杂度从 O(P × E) 降到 O(E + P × R)**
   不是 R1 才出现的设计，但 R2 把分片清单（specs/01 §3.5）做实了。500 玩家 × 50k 实体 → 25M 序列化操作 vs 50k + 500×9 → 54.5k——这是把规模拐点从 100 玩家推到 1000+ 玩家的关键单点优化。

5. **Bevy World 工作副本 + FDB 权威源 + 显式 `world.restore(snapshot)`**
   两个常见失败模式被避开：(a) 「内存与持久化各算各的」导致 commit 失败时内存状态污染下一 tick；(b) 「commit 失败回滚」与「BROADCAST 已经发出去」的双写不一致。specs/01 §3.5 显式说 BROADCAST failure never rolls back committed tick——这条契约挽救了大量隐式事务参与者的设计错误。

6. **Deferred Command Model 让所有 mutation 走同一条 `validate_and_apply()`**
   Host function 只读、所有 mutating 走 JSON intent → 单一校验路径。这意味着：新增一种命令时，安全校验**不可能**漏掉某个入口——因为只有一个入口。这是 success-mode 而非 antipattern。

---

## Concerns

> 我把 D1-D5 / C1-C3 / CRITICAL-1-2 这些已被 dsv4-architect、gpt-architect、dsv4-security、gpt-security 充分论证的项标记为 **[CONFIRMED]** 不再展开，下面只列**我的独立发现**。

### A1 — Critical · 边界突破：FDB rollback 与 BROADCAST 的「读已提交」窗口未定义（新发现）

**边界**: EXECUTE Phase 末尾的 `txn.commit()` 与 BROADCAST Phase 入口之间。

**问题**: specs/01 §4.2 写 `Read committed tick result from in-memory post-commit state or FDB versionstamp`——这是个二选一选项，不是契约。两种语义并存意味着：

- 选项 A：从内存读 → 与 FDB 实际持久化状态可能不一致（如果 commit ack 收到但 FDB 副本同步前 engine 崩溃，重启后 FDB 可能 rollback 该 tick，但客户端已收到 delta）
- 选项 B：从 FDB versionstamp 读 → 每 tick 多一次 FDB 读 RTT，500ms EXECUTE budget 进一步收紧

**爆炸半径**: 如果实现选 A 而 FDB 在 5.2 节列出的"事务冲突重试"路径触发，**客户端可能看到永不存在的世界状态**（A 已广播，FDB 后续 rollback）。回放时按 FDB 重建会得到不同结果——确定性合同破裂。这不是单玩家影响，是**全世界状态错乱**。

**必须修正**:
1. 选定 A 或 B 写死。我建议 A + 显式 commit-ack-then-broadcast 串行化：BROADCAST 必须在 `commit().await` 返回 Ok 之后开始；commit 中途崩溃 → 重启时检测 `/tick/{N}/complete` 标志 → 若不存在则回滚 BROADCAST queue 中未发出的 delta，已发出的通过下一 tick keyframe 强制纠偏。
2. specs/01 §6.1 的失败模式矩阵需要新增一行「commit success but BROADCAST not yet started → engine crash」——目前这一行缺失。

---

### A2 — Critical · 边界突破：Phase 2b 「部分并行」的数据竞争边界没有静态保证（新发现）

**边界**: `regeneration_system` / `decay_system` 与主线 `death_mark → spawn → combat → death_cleanup` 的并行边界。

**问题**: DESIGN.md §3.2 与 specs/01 §3.4 都说 regeneration / decay 与主线无数据竞争，可由 Bevy 调度器并行。但**两份文档都没有列出 Component / Resource 的读写矩阵**：

| System | 读 | 写 |
|--------|---|---|
| regeneration_system | Source.amounts, Source.ticks_to_regeneration, ResourceRegistry | Source.amounts, Source.ticks_to_regeneration |
| decay_system | Drone.fatigue, Drone.cooldown, Structure.cooldown | Drone.fatigue, Drone.cooldown, Structure.cooldown |
| spawn_system | Spawn.energy, Spawn.cooldown, RoomCap | Drone (创建), Spawn.energy, Spawn.cooldown, RoomCap |
| combat_system | Drone.hits, Structure.hits, Damage queue | Drone.hits, Structure.hits |

肉眼看 regen 写 `Source`、decay 写 `Drone.fatigue/cooldown`、spawn 写 `Drone(新建)`、combat 写 `Drone.hits` ——好像无冲突。但：

1. **decay 写 `Drone.cooldown`**，combat 也可能写 `Drone.cooldown`（特殊攻击 200 tick CD 在 apply 后写入）。如果 combat 在 Phase 2a 已经 inline 写完 cooldown，那 Phase 2b decay 读到的是新值——OK。但 DESIGN §8 又说 Tower 自动攻击在 Phase 2b combat_system 中结算——**Tower attack 写 cooldown vs decay 读 cooldown 是同 tick 内的并行写读**。
2. **spawn 写 RoomCap，death_mark 也写 RoomCap**（释放槽位）。DESIGN 说 death_mark 在 spawn 之前——OK。但 RoomCap 是 Resource 还是 Component？如果是房间级 Component，Bevy 的并行调度器需要看到 ParamSet 才能允许并行。
3. **regeneration_system 与 spawn_system 是否可能竞争同一 Source**？Spawn 命令本身不消耗 Source（消耗 Spawn.energy），看似不冲突。但 spawn 时若新 drone 立刻 harvest——不，harvest 是 Phase 2a，已结束。所以这条没问题。

**爆炸半径**: 如果 (1) 成立，确定性破裂——同一 input 在不同硬件 / 不同 Bevy 版本下，调度器的并行决策可能不同。这是**回放永久失效**类的故障：所有历史 tick trace 失去验证能力。

**必须修正**:
1. specs/01 §3.4 增加 system 读写矩阵表（上面那张），强制每次 system 调整时同步更新。
2. 写一条 CI 规则：用 `bevy_ecs::schedule::ScheduleGraph::dump()` 验证调度图不含跨 system 的 conflicting access（除非显式声明 `.before/.after`）。
3. **更保守的方案**（我推荐）：MVP 阶段全部 `.chain()`，把 Phase 2b 并行优化推到 Phase 4。理由是 500ms EXECUTE budget 的瓶颈在 Phase 2a 的命令循环和 FDB commit，**不在 Phase 2b 的 ECS systems**——并行 Phase 2b 的收益可能是 5-10ms 量级，付出确定性风险不值得。

---

### A3 — High · 爆炸半径：World Action Manifest 的回放绑定未定义（gpt-architect A4 的延伸）

**边界**: Core IDL（编译期单一真相源）与 World Action Manifest（运行时 world.toml + custom_actions + special_effects + Rhai handler）的边界。

gpt-architect 的 A4 已经说明了这条边界为什么必要——我补充**为什么仅"声明 manifest 概念"还不够**：

1. **回放确定性合同**: specs/01 §7.1 写「相同 world_config + 相同模组版本 → 相同 state_checksum」。但 world_config 是 TOML 文本，模组是 git tag。两者都不是 hash——TOML re-serialization 顺序不同、git tag force-push 都会让回放产生不同 checksum。
2. **跨 tick manifest 切换的时间点**: 如果服主在 tick 5000 通过 `swarm mod update` 切换 manifest 版本，是该 tick 立刻生效还是下个 keyframe 边界生效？specs/07 没说。如果立刻生效，回放遇到 tick 4999 时使用旧 manifest，tick 5000 切换——回放器需要记录每个 tick 的 manifest hash，否则**replay 在 manifest 切换点处永久失败**。
3. **WASM 模块的 manifest 兼容性**: 玩家 WASM 是基于 manifest v1 编译的。manifest 切到 v2 时，custom action enum 可能扩展（向后兼容）也可能 breaking（向前不兼容）。WASM 没有"manifest version check"机制——它会按 v1 schema 输出，引擎按 v2 schema 解析，可能产生**跨版本 silent corruption**。

**必须修正**:
1. specs/07 增加 `world_config_hash = Blake3(canonicalized_toml || sorted_mod_lock || sorted_custom_actions)`，每 tick 写入 TickTrace。
2. 定义切换时间点：**只在 keyframe 边界（每 100 tick）**切换 manifest，且需要服主显式 `--at-keyframe N` 参数。中途切换被拒绝。
3. WASM 部署时携带 `target_manifest_hash`，引擎在 tick 时校验 `current_manifest_hash == module.target_manifest_hash`，不匹配 → 该玩家进入 degraded mode（给用户重新部署的机会而不是 silent corrupt）。

---

### A4 — High · 规模拐点：500ms EXECUTE budget 在 1000+ 玩家时不够用（与 dsv4-architect N5 互补）

dsv4-architect 的 N5 提到了 fuel metering 不能用墙钟。我从**规模拐点**的角度把这条做成定量论证：

| 玩家数 | Command 总数（满载） | 每命令 ECS query 次数 | 总 query | Bevy archetype query 时间 | FDB delta 写入字节 | FDB commit p99 |
|--------|-------------------|---------------------|---------|------------------------|------------------|-------------|
| 10 | 1k | ~5 | 5k | <1ms | ~10KB | ~10ms |
| 100 | 10k | ~5 | 50k | ~5ms | ~100KB | ~30ms |
| 500 | 50k | ~5 | 250k | ~25ms | ~500KB | ~80ms |
| 1000 | 100k | ~5 | 500k | ~50ms | ~1MB | ~150ms |
| 5000 | 500k | ~5 | 2.5M | ~250ms | ~5MB | ~500ms ❌ |
| 10000 | 1M | ~5 | 5M | ~500ms ❌ | ~10MB | ~1s ❌ |

**ECS query 估算**: Bevy archetype query O(1) per access，但每条命令做 ownership check + range check + resource check + body check ≈ 5 次 query。1ns/query 量级。
**FDB delta**: 每条命令产生 1-3 个键值对变更，平均 ~10 字节/变更，加上 keyframe / commands / rejections 元数据。
**FDB commit p99**: 严格可序列化事务在 100KB 写入下 ~30ms，但**500 活跃玩家时 hot-key contention**（房间内多 drone 写同一 RoomCap，多玩家 harvest 同一 Source）会显著推高尾延迟。FDB 论文给的是 small txn p99 ~10ms，但 swarm 的 tick txn 是 batch txn，不在该基准内。

**爆炸半径**:
- 500 玩家附近：tick budget 还有 ~50% 余量，OK。
- 1000 玩家附近：开始挤压 BROADCAST 时间，p99 接近 500ms 但尚可。
- 5000 玩家附近：**FDB commit 单事务超 500ms**——这不是优化能解决的，是 FDB single-txn 的物理上限。需要架构改动（per-room transaction 而不是 per-tick transaction）。

**这是 DESIGN §3.1a 已经声明过的扩展策略边界**——我只是把"垂直扩展 500"和"水平分片"之间的中间地带（1000-5000）的具体瓶颈点定位出来：

1. **第一个拐点 ~1000 玩家**: ECS query 总量到 ms 级，需要 archetype query 优化（按 owner 索引而不是全 entity 扫描）。
2. **第二个拐点 ~3000 玩家**: FDB hot key contention 主导——需要 per-room transaction 拆分（接受 keyframe 一致性而非 strict tick consistency）。
3. **第三个拐点 ~5000 玩家**: 单 engine 内存 / 序列化带宽上限——必须水平分片。

**建议**: ROADMAP 增加一条「P1 性能门槛」：在 P0 完成（500 玩家 MVP）后，必须有一个 1000-玩家 stress test，作为决定何时投入分片工程的客观闸门，而不是凭感觉决定。

---

### A5 — High · 边界突破：Auth Service 是单点信任，证书签发的爆炸半径未限制（gpt-security H2 的延伸）

gpt-security 的 H-2 关注「私钥签名 vs 服务端 keypair」的混淆。我从**边界突破**角度补充：

**边界**: Auth Service 持有所有玩家的 Ed25519 短期证书签发权（specs/09 §3.3）。
**爆炸半径**: 如果 Auth Service compromise（容器逃逸 / 配置泄漏 / supply chain attack）——

1. 攻击者可签发任意 player_id 的证书 → 部署任意玩家的 WASM；
2. 证书 24h 有效 → 即使 compromise 被发现，已签发证书继续生效 24h；
3. specs/03 §1.1 没有证书撤销列表（CRL）或 short-lived JWT-with-revocation；
4. **TickTrace 中只记录 player_id + module_hash，不记录签发证书的 Auth Service epoch**。事后审计无法区分「玩家本人部署」和「Auth Service compromise 时段内的伪造部署」。

**必须修正**:
1. Auth Service epoch（每天轮换，写入 TickTrace 每条部署事件）+ 紧急 epoch bump 机制（compromise 发现时立刻让所有 24h 内证书失效）。
2. Auth Service 只能签 module_hash 已经被 WASM static analysis 通过的部署——添加 `audit-passed` 字段在证书 claim 中。
3. 高价值操作（tournament_precommit / mod 安装）走多签（玩家 + Auth Service + 至少一个第二签名源）。

---

### A6 — Medium · 规模拐点：BROADCAST 阶段的 fan-out 在 5000+ 玩家时是网络瓶颈（新发现）

DESIGN §3.2 写「分玩家推送（每个玩家只收到可见分片）」。看起来 fan-out 已经收敛了——但具体看：

每 tick 增量 → NATS publish → Gateway → 每个 WS 客户端 push。
- 每玩家 delta 大小 ~10KB（9 房间分片）
- 5000 玩家 × 10KB × 1/3s = **~16 MB/s 持续出站**
- 加上 spectator（DESIGN 没说 spectator 数量上限），可能 10x

**瓶颈链**:
1. Gateway 横向扩展可解决出口带宽（gpt-architect 的 Gateway-1/-2 多实例图已经画了）。
2. 但 Gateway → NATS 的入口带宽是 single-source bottleneck——所有 delta 必须先经过 NATS topic 才能 fan-out。NATS 默认配置在 100MB/s 量级，但 tick 突发是 spiky 的（每 3s 内 100ms 突发到 50MB/s ≈ 500MB/s 瞬时），可能触发 NATS slow consumer disconnect。
3. WS 客户端的下行带宽（家用网络可能 ~1MB/s）在 spectator 全图模式下可能撑不住。

**爆炸半径**: 1000+ spectator 同时观战 → 部分 spectator 断流 → 客户端通过 last_tick gap recovery 主动 fetch → 全部 spectator 同时向 Gateway 拉取 → Gateway 负载放大。

**建议（非 P0）**:
1. specs/01 §4.2 增加 NATS 积压压测要求：500 玩家 × 1000 spectator 持续 1h 不丢 delta。
2. spectator 推送 sample rate（每 3 tick 推一次而不是每 tick）作为降级开关。
3. delta 压缩（snappy / zstd）必须在 specs 里写死，不能让实现者自由选择——影响确定性日志大小估算。

---

### A7 — Medium · 失败模式枚举遗漏：specs/01 §6.1 有 9 行，但缺这 4 个常见模式（新发现）

specs/01 §6.1 的失败模式矩阵很好，但我清点了一下，这 4 个常见多人游戏后端的故障模式没出现：

| 失败点 | 触发条件 | 缺失的影响 |
|-------|---------|-----------|
| **clock skew** | engine 节点系统时间被 NTP 大跳跃修正 | tick_interval 错乱导致 collect_timeout 计算异常；未声明使用 monotonic clock |
| **WASM module size 超限** | 玩家上传 50MB WASM 模块 | 部署时校验在哪里？ROADMAP / specs/04 没说 module size 上限 |
| **player count 触发 room cap soft limit** | 单房间 drone 数接近 RCL 上限时，spawn 命令既不立刻 reject 也不 queue | 玩家无法预测自己的 spawn 是否成功；客户端 UX 模糊 |
| **storage tier failure cascade** | FDB 健康但 Dragonfly 完全宕机 | specs/01 §6.1 写「回退到 FDB 直读」，但没说 FDB 直读的 RPS 上限——5000 玩家全直读会打爆 FDB |

**建议**: specs/01 §6.1 补这 4 行。前 3 行影响 P0 实现，第 4 行是 P1 性能容量规划。

---

## Missing

> 我把 dsv4-architect 和 gpt-architect 已经列出的 missing 项（canonical invariants 文档、spec convergence tests、performance acceptance criteria、newcomer implementation path）标记为 **[CONFIRMED]** 不重复。下面只列**我的独立缺失项**：

1. **System 读写矩阵（具体见 A2）**: Phase 2b 并行决策的静态依据。这不是单个文档而是 specs/01 §3.4 的子表。

2. **Replay-safe Manifest Hash（具体见 A3）**: world_config canonical 序列化算法 + manifest_hash 字段在 TickTrace 的存储 schema。

3. **FDB 单事务大小预算 / per-room transaction 切换条件**: 5000+ 玩家时的架构 contingency plan。建议写成 ADR 而不是 spec——这是"什么时候触发架构改动"的决策文档。

4. **Auth Service epoch + 紧急轮换 runbook（具体见 A5）**: 安全应急响应文档，应放在 docs/security/ 而不是 specs/。

5. **Tick-level Resource 耗散建模**: specs/01 §3.5 的 Resource 列表里有 `RNGState`，但**RNG 调用次数预算**没有定义。一个恶意玩家是否可以用大量 path_find 调用让 RNG state 在 single tick 内消耗几百万次？这是 fuel metering 的盲区。

6. **Engine 重启时的"游戏内时间"恢复合同**: tick_counter 从 FDB 重建是显然的，但**正在 spawning 的 drone**（Phase 2a 校验通过但 Phase 2b 还没创建）在重启时怎么处理？specs/01 没有说——这是个跨 tick state 持久化的盲区。

---

## Phase Ordering

> 我同意 gpt-architect 提出的 5 阶段总框架（Spec Convergence → 生成链 → Tick → Visibility → Performance → Dynamic Rules）。下面给**依赖图重排**，找出**可并行**和**隐藏依赖**：

### 依赖图（明确化）

```
                   ┌─────────────────────────┐
                   │ R2 Gate: Spec Convergence │  必须先行
                   │  (D1-D5 / C1-C3 收敛)    │
                   └───────────┬─────────────┘
                               │
              ┌────────────────┼─────────────────────────┐
              │                │                         │
              ▼                ▼                         ▼
     ┌─────────────┐   ┌──────────────┐         ┌───────────────┐
     │ Phase 1     │   │ Phase 1.5    │         │ Phase 1.5     │
     │ 生成链      │◄──┤ Invariants 文档 │       │ Read/Write Matrix │
     │ + CI diff  │   │ (gpt-A4 missing)│       │ (我的 A2)      │
     └──────┬──────┘   └──────────────┘         └───────────────┘
            │
            ▼
     ┌────────────────────────────────────┐
     │ Phase 2: Core Tick (single-thread) │  ★ 用 .chain() 全串行
     │ - WasmSandboxExecutor              │
     │ - Source Gate                      │
     │ - Inline command loop              │
     │ - Phase 2b 全 .chain() (不并行)    │
     │ - TickTrace + state_checksum       │
     │ - FDB commit-then-broadcast 串行   │  ← A1 修正
     └──────┬─────────────────────────────┘
            │
            ▼
     ┌────────────────────────────────────┐         ┌─────────────────┐
     │ Phase 3: Visibility + MCP read     │ ◄──────┤ Phase 3 可并行: │
     │ - is_visible_to cache              │        │  Manifest Hash   │
     │ - Leakage tests (Snapshot/MCP/WS)  │        │  + Replay 绑定   │
     │ - MCP deploy / list / get_replay   │        │  (A3)            │
     │ - 不开放 gameplay tools           │         └─────────────────┘
     └──────┬─────────────────────────────┘
            │
            ▼
     ┌────────────────────────────────────┐
     │ Phase 4: Performance Hardening      │
     │ - Snapshot/restore benchmark       │
     │ - 1000-player stress test (A4 拐点) │
     │ - BROADCAST fan-out 压测 (A6)      │
     │ - Phase 2b 并行（基于 RW matrix）   │  ← 在这里才并行，不是 P0
     └──────┬─────────────────────────────┘
            │
            ▼
     ┌────────────────────────────────────┐
     │ Phase 5: Dynamic Rules + Modding   │
     │ - World Action Manifest            │
     │ - mod signature / capability       │
     │ - manifest hash → replay binding   │
     └────────────────────────────────────┘
```

### 与 gpt-architect Phase 排序的差异

| 项 | gpt-architect | 我的修正 | 理由 |
|---|---|---|---|
| Phase 1.5 | 不存在 | 新增 Invariants 文档 + RW Matrix | 与 Phase 1 并行；是 Phase 2 的输入而不是 Phase 2 的产物 |
| Phase 2b 并行 | 在 Phase 2 内默认实现 | 推迟到 Phase 4 | A2: MVP 用 `.chain()` 收益≈损失，并行的确定性风险不值得 |
| Performance 阶段任务 | snapshot/restore/visibility benchmark | 增加 1000-玩家 stress test 作为闸门 | A4: 缺乏定量闸门会让分片决策凭感觉做 |
| Manifest Hash | 在 Phase 5 | 在 Phase 3（与 Visibility 并行） | A3: replay 一致性是 Phase 3 leakage tests 的依赖（replay diff 测试需要 hash） |

### 可并行机会（节省日历时间）

1. **Phase 1 ⇄ Phase 1.5**: 生成链工程与 Invariants/RW Matrix 文档化。两个工作量均匀的小工程，不同人做。
2. **Phase 3 ⇄ Manifest Hash**: Visibility 实现和 Manifest 绑定逻辑没有共享代码，不同 module。
3. **Phase 4 内部**: snapshot benchmark / visibility benchmark / fan-out 压测 → 三套独立 benchmark，不同硬件并行。

### 隐藏依赖（必须串行）

1. **Spec Convergence → 所有其他 Phase**: 这是硬依赖，spec 不收敛就不能写代码。
2. **Phase 2 → Phase 4 Phase 2b 并行**: RW matrix 必须先有（Phase 1.5），Phase 2 全串行版本必须先验证确定性，**才能**在 Phase 4 引入并行优化。跳过这一步直接并行是在用确定性换性能。
3. **Phase 3 Manifest Hash → Phase 5 Dynamic Rules**: Phase 5 的 mod 系统假设 manifest hash 已经能写入 TickTrace。

---

## Bottom Line

R2 的架构方向已经成功——这一点我和 dsv4-architect、gpt-architect 一致。我的独立判断是：

1. **现在的状态**: 设计层 80% 收敛，spec 层 60% 收敛。差距全在 D1-D5 / C1-C3，全是**已识别但未执行**的修正。
2. **风险来源**: 不是设计错了，是**spec 和 design 不同步导致实现者按错的那份做**——这正是 gpt-architect A1-A8 所谓的 "split-brain specification"。我同意这个判断。
3. **我的独立增量**:
   - A1 (commit-broadcast 顺序) 是新发现的 critical 边界
   - A2 (Phase 2b 并行的 RW matrix) 影响实现策略——MVP 应该全串行
   - A3 (Manifest Hash + Replay 绑定) 是 gpt A4 的具体执行方案
   - A4 (规模拐点定量分析) 给出 1000/3000/5000 三个具体拐点
   - A5 (Auth Service 爆炸半径) 是 gpt H-2 的延伸
   - A6 (BROADCAST fan-out) 是新发现的网络瓶颈
   - A7 (4 个失败模式补充) 是 specs/01 §6.1 的缺口
4. **Phase 排序差异**: 我建议 Phase 2 用 `.chain()` 全串行，把并行化推迟到 Phase 4——这是 A2 的具体落地。

执行 R2 spec convergence + A1（commit-broadcast 串行化）+ A2（推迟 Phase 2b 并行）三项后，Verdict 升级为 **APPROVE**，可进入实现。

---

*rev-claude-architect (Claude Opus 4.7) — R2 评审结束。*
