# Swarm 架构评审报告 — R2

**评审员**: rev-dsv4-architect (DeepSeek V4 Pro — 架构师方向)
**评审日期**: 2026-06-16
**评审轮次**: R2（Design Review Round 2）
**评审范围**: DESIGN.md (2300行), ROADMAP.md, specs/01-09 (全部9份规范), tech-choices.md
**评审视角**: 系统架构 / ECS 调度正确性 / Tick 生命周期完整性 / 数据一致性 / 算法复杂度 / 确定性保证

**R2 评审焦点**: 验证 R1 裁决的 9 项入场条件是否已修正，同时以全新眼光审视设计变更。

---

## 1. 总评 (Verdict)

**APPROVE_WITH_RESERVATIONS** — R2 的 DESIGN.md 变更方向正确，Overload/B4-ROADMAP/H2-WASM签名 三个核心项已正确修正。但 specs 层（specs/02, specs/05, specs/08）存在 4 项未同步的遗留不一致，导致 DESIGN↔specs 合同裂口。另有 1 项新发现的架构关注点（N5）。均不阻塞 MVP 实现开始，但需在实现前闭合 specs。

**关键判断**: DESIGN.md 已准备好指引实现。specs 层有裂口但范围明确、修正工作量小（4 处点状修改）。

---

## 2. R1 入场条件逐项验证

### ✅ 已修正（DESIGN 层）

#### B1: Overload 攻击规范 — DESIGN.md 层 ✅

DESIGN.md §8 Overload 行（L1148）已正确更新：
- "必须满足 `is_visible_to(target, attacker)`——不可攻击不可见玩家" — visibility 约束已明确
- "全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限来源）" — per-target 冷却已写入
- "Overload 返回静默结果——攻击者无法从结果推断目标 fuel 状态" — 信息泄露合同已建立

**但**: specs/02 §3.12 仍保留 `TargetFuelTooLow` 拒绝码（L343），校验表未包含 `visible_target` 或 per-target 全局冷却。见下文 D1。

#### B4: ROADMAP 状态粒度 ✅

ROADMAP.md 已重构为模块级 checklist（P0/P1 分组），每项含 `[x]` 完成标记、实现细节、测试数量。状态粒度从「100% 完成」提升到可审计的逐项追踪。

#### H2: WASM 部署签名模型 ✅

specs/09 §3.3 明确了「证书（含服务端签名）」模型：
- 客户端获取 OAuth2 + 服务端签发短期证书（Ed25519 keypair, 24h 过期）
- 部署时附证书 + `Blake3(WASM bytes)` 私钥签名
- `player_id` 从证书提取，不可自报
- 明确写了「为何不用客户端 keypair」的架构决策理由

specs/03 §1.1 与 specs/09 一致，证书流程一致。

---

### ❌ 未修正（specs 层裂口）

#### D1: Overload — specs/02, specs/08 未同步到 DESIGN 合同 ⭐⭐⭐

| 文档 | visibility check | per-target 冷却 | TargetFuelTooLow |
|------|:--:|:--:|:--:|
| DESIGN.md §8 | ✅ | ✅ | ✅ (移除) |
| specs/02 §3.12 | ❌ | ❌ (仅 drone 冷却 200tick) | ❌ (仍存在, L343) |
| specs/08 §Overload | ❌ | ❌ (validator 无 global_cooldown) | N/A (validator 用 `target_fuel_above`) |

**影响**: 实现者按 specs/02 §3.12 落地 → 信息泄露未堵住、多攻击者可协同 Overload → B1 问题残留。specs/08 的 IDL validator `target_fuel_above(0.2)` 本身表达了「拒绝低于下限」的语义，但 DESIGN 合同现在要求静默返回——IDL 层无法表达「静默接受」语义，需在 validator 层面改为始终 `Accepted`。

**建议修正**: 
- specs/02 §3.12: 移除 `TargetFuelTooLow` 行，增加 `target_visible` + `target_global_cooldown(50)` 校验行
- specs/08 Overload validator: 增加 `visible_target` + `target_global_cooldown(50)`；将 `target_fuel_above(0.2)` 标记为「静默截断」（非 RejectionReason）
- specs/02 Overload 效果描述：增加「始终返回 Accepted（静默）」说明

#### D2: 命令数量/大小限制 — specs/02 内部自冲突 ⭐⭐

specs/02 存在两套冲突的限制：

| 位置 | 条数上限 | 字节上限 | 单条字节 |
|------|---------|---------|---------|
| §1.1 (L45, L51-52) | 100 | 256KB | — |
| §6 批级校验 (L498-500) | 500 | 1MB | 64KB |

R1 B3 裁决明确要求统一为：`MAX_COMMANDS_PER_PLAYER = 100`, `MAX_TICK_OUTPUT_BYTES = 256KB`, `MAX_COMMAND_BYTES = 16KB`。**这一修正在 specs/02 中未执行**。

**影响**: 实现者按 §6 落地（500 条/1MB/64KB）会绕过 §1.1 的 JSON schema 校验（maxItems=100），产生隐蔽的 DoS 面（500 条 × 64KB = 32MB 可能）。§6 的「含 Admin 来源」语义也与 §1.1 的「WASM tick 输出」不一致——Admin 不该跟玩家共 pool。

**建议修正**: 全仓统一为 R1 裁决值（100/256KB/16KB），删除 §6 的冲突行。Admin bulk operation 显式排除在实时 tick pipeline 外。

#### D3: spectate_delay 强制校验 — specs/05 未实现 ⭐⭐

specs/05 §3.5（L133）已声明约束「World 模式下若 `public_spectate = true`，`spectate_delay` 必须 ≥ 50 tick」，但：

- §8.5 配置示例仍显示 `spectate_delay = 0`（L290）
- 未给出 `validate_config()` 伪代码
- 未说明默认值在 World 模式下应自动 clamp 到 50

**影响**: 服主复制 §8.5 示例 → `public_spectate=true` + `spectate_delay=0` → 实时全图信息泄露（B2 问题残留）。

**建议修正**: 
- §8.5 示例改为 `spectate_delay = 50`，附注释说明「World 模式下自动 clamp ≥ 50」
- 增加 `validate_config()` 伪代码：`if world.mode == persistent && visibility.public_spectate && visibility.spectate_delay < 50 → error`
- 默认值声明：World 模式下若未显式设置且 `public_spectate` 开启，自动 clamp 到 50

#### D4: Tick/ECS 系统顺序 — DESIGN vs specs/01 仍不一致 ⭐

DESIGN.md §3.2 Phase 2b ECS Systems 顺序：
```
death_mark → spawn → combat(damage→heal) → regeneration → decay → death_cleanup
```

specs/01 §3.4 `.chain()` 顺序：
```
death_mark → spawn → regeneration → combat(damage→heal) → decay → death_cleanup
```

**差异**: `combat` 和 `regeneration` 顺序互换。这影响游戏语义——regeneration 在 combat 之前意味着资源点在战斗前再生（战斗双方都从满资源点取），在 combat 之后意味着战斗消耗后才再生（先到先得的激烈程度不同）。R1 H1 已要求统一，未执行。

**判断**: specs/01 的顺序（regeneration 先于 combat）与「资源点每 tick 稳定再生」的直觉更一致，且不影响确定性（只要一致就好）。建议 DESIGN.md 对齐到 specs/01。

#### D5: 坐标/网格模型 — specs/08 Direction enum 仍是六边形 ⭐

| 文档 | 网格 | 方向 |
|------|------|------|
| DESIGN.md §3.1a (L249) | 正方形 50×50 | N/S/E/W |
| specs/01 §1.1 | 正方形, N/S/E/W | N/S/E/W |
| specs/08 IDL (L42) | — | `[Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft]` — **六边形** |

**影响**: SDK 代码生成器从 specs/08 IDL 读取 Direction enum → 生成六边形移动 API → 与正方形网格不匹配 → 移动路径计算错误。R1 H5 已要求统一，specs/08 未修正。

**建议**: specs/08 Direction enum 改为 `[North, South, East, West]`，或在 IDL 注释中明确「正方形网格的四方向模型」。

---

### ⚠️ 部分修正 / 需要评估

#### H3: MCP transport 安全边界 — 未处理

specs/03 §2 仍写「仅 HTTP/SSE」（L78），DESIGN.md 架构图仍写「rmcp, HTTP/SSE」（L125）。R1 要求拆分 browser/non-browser transport contract 并增加 DNS rebinding 防护测试。此修正未出现在任何文档中。

**评估**: 此为非阻塞性安全加固项。MCP 绑定 127.0.0.1 通过 nginx 代理对外暴露已提供基本防护。但 Streamable HTTP 的 MCP 规范进展（2025 替代 SSE）应纳入考量——SSE 在设计文档中作为「唯一传输」出现会随时间变成技术债。

---

## 3. 新发现项（R2 独立审查）

### N1: Overload 全局冷却的 key 设计未指定

DESIGN.md L1148 注入「同一目标每 50 tick 最多被 Overload 一次（不限来源）」。未指定冷却 key：
- Key = `target_player_id` → 全局单一冷却计时器（最严格）
- Key = `(target_player_id, tick_applied)` bucket → 滑动窗口（更精确）

**建议**: 明确采用 `(target_player_id, last_overloaded_tick)` 键值对，简单高效。在 specs/02 增加实现细节。

### N2: command 数量限制中「含 Admin 来源」的语义歧义

specs/02 §6 (L500) 写「每 tick 每玩家 ≤ 500 条指令（含 Admin 来源）」。Admin 不是「玩家」——Admin 账户可能不拥有 drone、不消耗 fuel。将 Admin 操作与玩家 tick 输出共 pool 会在 Admin 进行批量修复操作时拒绝玩家指令。

**建议**: Admin 指令显式走独立 budget，不与玩家 `MAX_COMMANDS_PER_PLAYER` 共 pool。

### N3: WASM 部署中 Blake3 签名的 HMAC vs keyed hash 混淆

specs/03 §1.1 (L59):「私钥签名(Blake3(WASM bytes))」。Blake3 是 hash 函数，不是签名算法。Ed25519 的 private key 用于 Ed25519 签名，不用于 Blake3 keyed hash。若意图是用 Ed25519 签名 Blake3 哈希，应写「`Ed25519_Sign(sk, Blake3(WASM_bytes))`」。当前表述可能让实现者误用 Blake3 keyed hash 代替 Ed25519 签名。

**建议**: 修正为「`Ed25519_Sign(player_sk, SHA-256(WASM_bytes))`」或等价的 Ed25519 签名表述。SHA-256 作为 Prehash 可提供更大的 WASM 文件签名兼容性。

### N4: Bevy World 快照的回滚成本未建模

specs/01 §3.5 描述了 FDB 事务失败时的回滚流程（`world.restore(snapshot)`），但未给出 Bevy World 快照的内存成本。500 活跃玩家 × 500 drones + 5000 structures + 50000 terrain tiles → 快照体积可能达数十 MB。每 tick 做一次完整 World 快照在 500ms tick 预算内的可行性需要基准测试。

**评估**: 这是 Phase 1 性能工程项，非 R2 blocker。

### N5: Tick 超时 500ms 与最大燃料预算的耦合未建模 ⭐

specs/01 §3.4 给出 500ms 的 EXECUTE 超时。若单个玩家的 WASM 消耗大量 fuel（MAX_FUEL=10M 指令），在 500ms 内执行完所有玩家的 WASM + ECS systems + FDB commit 的可行性取决于 fuel metering 粒度。WASM fuel metering 的指令/时间比因操作而异（memory ops vs arithmetic），10M 指令可能在 5-50ms 之间波动（取决于 CPU 和 WASM 操作混合）。

**建议**: 增加 `MAX_EXECUTION_WALL_TIME_PER_PLAYER` 参数（建议 100ms），作为 fuel budget 的补充墙钟兜底。注意不能用于状态决定（违反确定性），仅触发「该玩家本次 tick 指令部分执行，剩余 fuel 保留至下 tick」的延迟机制。

---

## 4. 架构亮点确认（R2 重申）

以下 R1 认定的架构亮点在 R2 中仍然成立，且部分得到增强：

- **S1: Deferred Command Model** — 仍然是最核心的架构决策。specs/09 command-source-model 进一步明确了所有入口共享 `validate_and_apply()` 路径，无绕过。
- **S2: Two-Phase Snapshot** — 复杂度优化在 specs/01 §3.1 有详细的快照范围清单（resources + all ECS component types），设计深度增加。
- **S3: Blake3 单原语** — WASM 部署签名模型中 Blake3 用于 hash（非签名），主逻辑链仍正确（hash/PRNG 统一为 Blake3）。
- **S4: FDB 权威源 + Keyframe/Delta** — specs/01 §3.5 增加了 Bevy World 快照 + FDB rollback 的显式协调，完整性提升。
- **S5: 三层扩展模型** — ROADMAP 的 P0 范围明确化使 Layer 3 的远期属性更清晰。

---

## 5. 数据流一致性矩阵

| 数据流 | DESIGN 描述 | specs 描述 | 一致? |
|--------|-----------|-----------|:--:|
| Overload visibility | `is_visible_to(target, attacker)` | 无 visibility check | ❌ D1 |
| Overload 结果 | 静默返回 | `TargetFuelTooLow` 拒绝码 | ❌ D1 |
| Overload per-target 冷却 | 50 tick | 无 | ❌ D1 |
| Command 数量上限 | (未明确) | 100 vs 500 冲突 | ❌ D2 |
| Tick 字节上限 | (未明确) | 256KB vs 1MB 冲突 | ❌ D2 |
| Tick ECS 顺序 | combat→regen | regen→combat | ❌ D4 |
| Direction enum | N/S/E/W (方形) | 六边形 | ❌ D5 |
| spectate_delay 约束 | 有意图描述 | 示例仍为 0, 无校验 | ❌ D3 |
| WASM 部署签名 | (未明确) | 证书 + Ed25519 | ✅ H2 |
| 快照构建时机 | 命令循环前 | 命令循环前 | ✅ |
| Spawn 在 Phase 2a 只校验 | ✅ | ✅ | ✅ |
| FDB 原子提交 | ✅ | ✅ | ✅ |
| MCP 不直接操控实体 | ✅ | ✅ | ✅ |

---

## 6. 算法复杂度检查

- **Command 循环 O(Σ commands)**：单玩家 100 条上限，500 玩家 → 50k 条/tick。每条至少 2 次 ECS query（entity 查找 + 归属校验 + range 校验 + resource 校验），总计 100k-250k ECS 查询。Bevy 的 archetype 查询 O(1) per access，总时间在 10ms 以内，可行。
- **Snapshot 构建 O(E + P×R)**：50000 entities + 500×9 房间 = 54.5k 序列化。每 entity ~200 bytes（Position + Owner + HP + Body），约 10MB/tick。序列化 + 网络推送是主要瓶颈，但分玩家推送（每个玩家只收到可见分片）使带宽分散。
- **FDB commit**：Keyframe 每 100 tick (~80s) 一次全量写入（~50MB），Delta 每 tick 增量（~500KB-1MB per 500 players）。FDB 严格可序列化事务的 p99 延迟是关键指标，建议 Phase 1 补充 benchmark。

---

## 7. 优先级行动清单

### R2 必须修正（阻塞实现开始）

| ID | 问题 | 文档 | 工作量 |
|----|------|------|--------|
| D1a | specs/02 §3.12: 移除 TargetFuelTooLow, 增加 visibility + global cooldown | specs/02 | 3 行修改 |
| D1b | specs/08 Overload validator: 增加 `visible_target`, `target_global_cooldown(50)` | specs/08 | 2 标记增加 |
| D2 | specs/02: 统一 command 限制为 100/256KB/16KB, 删除 §6 冲突行 | specs/02 | 5 行删除+修改 |
| D4 | DESIGN.md Phase 2b order 对齐到 specs/01 (regen→combat) | DESIGN.md | 2 行交换 |
| D5 | specs/08 Direction enum: [Top,TopRight,...] → [North,South,East,West] | specs/08 | 1 行修改 |

### Phase 1 补充（非阻塞）

| ID | 问题 | 文档 |
|----|------|------|
| D3 | specs/05: spectate_delay validate_config() 伪代码 + 示例修正 | specs/05 |
| N1 | specs/02: Overload 全局冷却 key 设计明确 | specs/02 |
| N3 | specs/03: 修正「Blake3 签名」为「Ed25519 签名」表述 | specs/03 |
| N5 | specs/01: MAX_EXECUTION_WALL_TIME_PER_PLAYER 参数 | specs/01 |

### 远期追踪（R3 或 Phase 2）

| ID | 问题 |
|----|------|
| H3 | MCP transport: SSE → Streamable HTTP 迁移路线图 |
| N4 | Bevy World 快照内存成本基准测试 |

---

## 8. 结论

R2 的 DESIGN.md 修正质量高——Overload/B4/H2 三个核心项已正确解决。但 specs 层同步是 R2 的短板：4 项 DESIGN↔specs 不一致（D1-D5），均为 R1 已识别但 specs 层未执行的修正。这些修正范围小（总计约 15 行级别）、无歧义、不涉及架构方向变更。

**建议**: 执行 5 项 R2 必须修正后立即进入实现。Phase 1 补充项可与 MVP 实现并行。

---

*rev-dsv4-architect (DeepSeek V4 Pro) — R2 评审结束。*
