# R24 Determinism Review — rev-dsv4-determinism

**Reviewer**: rev-dsv4-determinism (DeepSeek V4 Pro)
**Date**: 2026-06-20
**Round**: R24 (Clean Slate)
**Scope**: spec ↔ design alignment check — determinism focus

---

## Verdict: CONDITIONAL_APPROVE

**Summary**: 14 findings — 1 Critical (host function ABI mismatch), 3 High, 7 Medium, 3 Low.
No fundamental determinism contract violations. The core architecture (Blake3 PRNG, ECS chain ordering, f64 ban, FDB atomic commit) is sound.
The Critical finding requires immediate resolution: `host_get_terrain` ABI signature differs between the IDL (authoritative) and `api-registry.md` (generated output). This would cause WASM module incompatibility if implemented from the wrong source.

---

## Strengths

1. **f64 全面定点化**: 所有 resource/age/damage/progress 使用 u64/i64 定点整数 + basis points。`api-registry.md` §0 Fixed-Point Type Registry 注册了 8 个定点类型。无 f64 残留。
2. **PRNG 设计坚实**: Blake3 XOF 统一覆盖哈希和随机数，per-entity stream seed 使用 domain separation，shuffle seed 公式明确。01-tick-protocol.md §9.8 明确禁止 WASM 暴露 RNG。
3. **ECS Serial Spine**: 06-phase2b-system-manifest.md 定义了完整的 29-system 串行脊柱 + R/W 矩阵。Phase 2a inline 逐条校验消除 TOCTOU。
4. **FDB 原子提交 + COLLECT 缓存复用**: 重试不重跑 WASM，`collect_id` 不变，`attempt_id` 递增——保证确定性 replay。05-persistence-contract.md §2.1 replay-critical subset 声明完整。
5. **WASM 沙箱确定性隔离**: 禁用 clock/random/filesystem/network。SIMD 默认禁用。Wasmtime 版本锁定 `=30.0`。
6. **快照截断确定性**: 确定性排序键 `(distance, entity_id)`，同输入 → 同截断结果。09-snapshot-contract.md 有显式确定性保证声明。

---

## Concerns

### D1 [Critical] — `host_get_terrain` ABI 签名跨文档冲突

| 文档 | 签名 |
|------|------|
| **game_api.idl.yaml** (08-api-idl.md §2) | `get_terrain(x: i32, y: i32) -> i32` |
| **design/interface.md** §5.1 | `host_get_terrain(x: i32, y: i32) -> i32` |
| **specs/core/04-wasm-sandbox.md** §3.2 | `host_get_terrain(x: i32, y: i32) -> i32` |
| **specs/reference/api-registry.md** §4.1 | `host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32` |

`api-registry.md` 将签名从 `(x, y) -> i32`（按坐标查地形，返回 terrain_type 整数）改为 `(room_id, out_ptr, out_len) -> i32`（缓冲区输出的 pointer/length 模式，与其他 host function 一致）。三个 source-of-truth 文档（IDL + interface.md + wasm-sandbox.md）使用旧签名，生成的 registry 使用新签名。**这是 spec 生成管道与手写文档之间的分叉**——任何一方被实现都会导致 WASM 模块 ABI 不匹配。

**修复建议**: 以 IDL 为权威源统一所有文档。检查 `generate_api_registry.py` 是否正确读取 IDL 的 `host_functions.get_terrain` 段。若新签名是有意变更，需同步更新 IDL + interface.md + wasm-sandbox.md 三份文档。

---

### D2 [High] — Phase 2b 并行 Combat Set 确定性未经形式化验证

| 文档 | 位置 | 声明 |
|------|------|------|
| 06-phase2b-system-manifest.md §4 R/W 矩阵 | S11 atk / S12 rng_atk / S13 heal | 全部 **W**rite `HitPoints` |
| 06-phase2b-system-manifest.md §4 并行安全证明 | — | "按 `target_id` partition，同一 entity 只被一个 system 写入" |

R/W 矩阵显示 S11-S13 全部直接写入 `HitPoints`——三个并行系统对同一 Component 有写权限。并行安全声明依赖「按 target_id partition」保证无重叠写入，但：

1. **Bevy 不自动 partition**——引擎代码必须手动实现 target 分配逻辑。该分配逻辑的确定性未在任何文档中指定。
2. **多个 Tower/NPC 可能攻击同一 target**（01-tick-protocol.md §3.2: "攻击同一目标: 全部执行"）。若 S11 中两个不同 Tower 的 auto-attack 瞄准同一 drone，其写入顺序依赖线程调度——非确定性。
3. **S14 special_attack_reducer 的 sub-buffer 描述与 R/W 矩阵冲突**：S14 说明文字称 S11-S13 "写入 per-system sub-buffer"，S14 再 merge sort。但 R/W 矩阵显示 S11-S13 直接写 `HitPoints`，绕过了 sub-buffer。

**修复建议**: 
- A) 明确 S11-S13 实际写入 `PendingDamage` buffer（非 `HitPoints`），更新 R/W 矩阵。S15 `damage_application` 统一从 buffer 读取并应用。此方案天然确定。
- B) 若确实直接写 `HitPoints`，需在 manifest 中显式定义「target_id partition 算法」并证明其确定性。Tower 的 target 选择（最近敌方）本身依赖 HP 状态——可能引入非确定性循环依赖。

---

### D3 [High] — 快照截断优先级三套策略冲突

| 文档 | 策略 |
|------|------|
| **design/engine.md** §3.4.4 | 5 级简单优先级: 自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源 |
| **specs/core/01-tick-protocol.md** §2.3 | 4 桶: 关键桶（Spawn/Controller/depot/storage 无条件保留）→ 高优先（己方 drone/建筑）→ 中优先（敌方/资源）→ 低优先（友方/中立） |
| **specs/core/09-snapshot-contract.md** §1.3–1.4 | 7 距离桶 + 关键实体永不截断（own drone, Controller, current target, **all own drones**, entities attacking self） |

三个文档对「己方所有 drone」的优先级定义不同：
- engine.md: 第二优先（可被截断）
- 01-tick-protocol.md: 第二优先（高优先桶，可被截断）
- 09-snapshot-contract.md: **永不截断**（关键实体 §1.4 "己方所有 drone"）

09-snapshot-contract.md 自称权威源（R22 B5），但 engine.md 和 01-tick-protocol.md 未引用此优先级。**若 engine.md 的描述被实现而 09 被忽略，玩家多 drone 场景下 replay 将分叉**——某些 drone 在一种实现中可见，在另一种中被截断。

**修复建议**: 以 09-snapshot-contract.md 为唯一权威，在 engine.md 和 01-tick-protocol.md 中替换为引用链接。删除 engine.md 中的简单优先级表。

---

### D4 [High] — `host_path_find` ABI 签名跨文档不一致

| 文档 | 签名 |
|------|------|
| design/interface.md §5.1 | `(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32` |
| specs/core/04-wasm-sandbox.md §3.2 | `(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32` |
| specs/reference/api-registry.md §4.1 | `(from_x, from_y, to_x, to_y, **opts_ptr, opts_len**, out_ptr, out_len) -> i32` |
| specs/gameplay/08-api-idl.md §2 | `(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32` |

`api-registry.md` 比 IDL 多了 `opts_ptr, opts_len` 参数。若 registry 是正确的（允许传入寻路选项如 avoid_enemies、prefer_roads），需同步更新 IDL + interface.md + wasm-sandbox.md。若 registry 是生成错误，需修复 codegen。

**修复建议**: 以 IDL 为准，检查 registry 生成管道。若有意增加 opts 参数，需同步更新 IDL 并触发 ABI version bump（abi_version 递增）。

---

### D5 [Medium] — Controller Repair 公式写法歧义

**design/gameplay.md** (line 102):
```
每 tick 总 age 回退不超过自然增长（+1/tick）的 50%
（即 max(0, age + 1 - min(0.5, controller_count * 0.5))）
```

`min(0.5, controller_count * 0.5)` 恒等于 0.5（当 controller_count ≥ 1）。此公式无法表达「多 Controller 增加修复能力」的意图。正确的写法应为 `min(1.0, controller_count * 0.5)` 或直接移除 min。

**design/engine.md** §3.4.5:
```
global_cap = floor(active_drones × 0.5)
actual_reduction = min(total_reduction, global_cap)
```

engine.md 的 global_cap 是全局总量上限。gameplay.md 的公式是 per-drone 计算。两者概念不同但 gameplay.md 的描述文字 "每 tick 总 age 回退不超过自然增长的 50%" 与 engine.md 的 `active_drones × 0.5` 语义一致。但 gameplay.md 的伪代码公式有 bug。

**修复建议**: 修正 gameplay.md 中的伪代码公式。统一使用 engine.md §3.4.5 的权威公式或引用 resource-ledger.md §2.4。

---

### D6 [Medium] — Snapshot Build 性能预算不一致

| 文档 | 指标 | 值 |
|------|------|-----|
| design/engine.md §3.4.1 | SNAPSHOT build | ≤50ms (p99) |
| specs/core/09-snapshot-contract.md §7.1 | Snapshot build time | <200ms p95, hard budget 500ms |

engine.md 的 50ms p99 比 snapshot-contract.md 的 200ms p95 严格 4 倍。这不影响正确性但会造成性能预期分裂——实现者以哪个为目标？

**修复建议**: 统一为一个值。若 50ms p99 是目标，将 09-snapshot-contract.md SLO 收紧到 50ms。若 200ms p95 是现实，将 engine.md 放宽。

---

### D7 [Medium] — Per-Player Drone Cap "50→500" 表述歧义

**design/gameplay.md** (line 444): "Room drone cap (50→500)" — 括号内 "50→500" 未标注单位或上下文。此数值实际引用 engine.md RCL 表中的 per-room 总量上限（RCL1=50, RCL8=500），而非 per-player cap（默认 50，world.toml 可调）。在反雪球合同上下文中，读者可能误解为 per-player cap 从 50 可变到 500。

**修复建议**: 改为 "Room drone cap (per-room, 50 at RCL1 → 500 at RCL8)" 或引用 engine.md RCL 表。

---

### D8 [Medium] — Phase 2b ECS 系统排序缺失 `host_get_objects_in_range` 确定性

**01-tick-protocol.md §2.3** 定义了 `host_get_objects_in_range` 返回 `{items, truncated, total_visible_count?}`。但未指定 items 的排序顺序。`host_get_objects_in_range` 的返回列表排序直接影响 WASM 代码的决策（如「选择最近的敌人攻击」）。若不同 tick/不同节点的排序不同，WASM 可能产出不同的 Command[]。

**specs/core/04-wasm-sandbox.md** §3.2 提到 `host_get_objects_in_range` 返回结果经 `is_visible_to` 过滤——但未指定排序。**09-snapshot-contract.md** 的截断排序（距离桶 + entity_id）可作为参考，但未明确声明 host function 复用此排序。

**修复建议**: 在 api-registry.md §4.1 或 04-wasm-sandbox.md §3.2 中显式声明 `host_get_objects_in_range` 的返回列表排序规则（建议: 距离升序 → entity_id 升序）。

---

### D9 [Medium] — `host_path_find` 确定性缓存键遗漏

**specs/core/04-wasm-sandbox.md** §8: cache key = `(from, to, terrain_hash, player_visibility_fingerprint)`。
**specs/core/09-snapshot-contract.md** §7.3: cache key = `(from, to)` — 仅起点和终点。

09-snapshot-contract.md 的简化 cache key 遗漏了 terrain_hash 和 visibility_fingerprint。若 terrain 变化（建筑被摧毁改变可通过性）但 cache 未 invalidate，将返回过期路径。若 visibility 变化（fog_of_war 边缘移动）但 cache 未 invalidate，可能泄露不可见地形信息。

**修复建议**: 统一为 04-wasm-sandbox.md 的完整 cache key。在 09-snapshot-contract.md §7.3 中引用 04-wasm-sandbox.md 的 cache key 定义。

---

### D10 [Medium] — `swarm_simulate` 跨玩家确定性歧义

**specs/core/09-snapshot-contract.md** §2.1 声明 simulate fork 使用独立 RNG `seed = hash(authoritative_seed + "simulate_preview" + drone_id + tick)`。此 seed 绑定到 `drone_id`——不同玩家模拟同一场景得到不同结果。这符合 "not_predictive" 语义。

但 `swarm_dry_run` 使用 "固定 seed（确定性）"——未指定该固定 seed 的推导公式。若 dry_run seed 也绑定 drone_id，则不同玩家无法获得相同结果进行交叉验证。若 seed 完全不绑定玩家，则泄露全局信息。

**修复建议**: 在 09-snapshot-contract.md §2.2 中显式定义 `swarm_dry_run` 的 seed 公式。建议: `Blake3("dry_run" || world_seed || tick || module_hash)` ——不绑定 player_id，允许跨玩家交叉验证，但不泄露对手信息（dry_run 使用 NPC-only world）。

---

### D11 [Low] — Seed Shuffle 公式 domain separation 不一致

**01-tick-protocol.md §3.1** (实现伪代码): `blake3::hash(&[&tick_number.to_le_bytes(), &world_seed])`
**01-tick-protocol.md §9.1** (确定性合同): `Blake3("shuffle" || world_seed || tick.to_le_bytes())`
**engine.md §3.3** (确定性保证): `Blake3("shuffle" || world_seed || tick.to_le_bytes())`

§3.1 的实现伪代码缺少 `"shuffle"` domain separation prefix。虽然函数上结果相同（Blake3 的输入是拼接的），但 cryptographic hygiene 要求 domain separation。§9.1 和 engine.md 是正确的——§3.1 的伪代码应同步。

**修复建议**: 统一 §3.1 伪代码使用 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`。

---

### D12 [Low] — Snapshot Contract Debug Output 含 f64

**specs/core/09-snapshot-contract.md** §4.4 训练模式 debug output 示例:
```json
{ "distance": 12.53, "required_range": 5.0, "action_range": 3.0 }
```

这些是 debug_detail 字段（非 canonical wire code），但使用了 f64 浮点数。01-tick-protocol.md §7.1 确定性合同声明「禁用 f64」。虽 debug output 不影响 replay，但使用了 f64 字面量可能与 「全部定点」 原则产生认知混淆。

**修复建议**: 使用定点表示（如 `milli_distance` 类型: `12530` 表示 12.530）或标注 "仅 debug，非 replay 输入"。

---

### D13 [Low] — `host_get_terrain` 返回值语义未定义

**specs/gameplay/08-api-idl.md** §2:
```
get_terrain: returns: i32  # terrain_type as i32 (0=plain, 1=wall, 2=swamp, 3=lava)
```

但 design/interface.md 和 04-wasm-sandbox.md 均未列出 terrain_type 的完整枚举值。04-wasm-sandbox.md §3.2 仅写 "地形公开，无需过滤"——未说明返回值含义。实现者需从 IDL 注释推导——若注释丢失或被忽略，返回值语义将不确定。

**修复建议**: 在 api-registry.md §4.1 `host_get_terrain` 行中或 04-wasm-sandbox.md §3.2 中明确 terrain_type 枚举（0=Plain, 1=Wall, 2=Swamp, 3=Lava, 4+=预留）。

---

### D14 [Low] — Arena tick budget 总和歧义

**design/engine.md** §3.4.1 Arena 列:
```
SNAPSHOT: ≤20ms, COLLECT: ≤200ms, EXECUTE: ≤50ms, COMMIT: ≤20ms, BROADCAST: ≤10ms
```
合计: 20+200+50+20+10 = **300ms** = Arena tick_interval。

但 engine.md §3.4.1 的注释说明 "目标 tick 间隔"——实际执行可能略超。01-tick-protocol.md §8.1 定义了 `tick_soft_deadline_ms = 2500ms`（World），但 Arena 未定义对应的 soft/hard deadline。若 Arena COLLECT 用满 200ms 后 EXECUTE 超过 50ms，tick 是放弃还是延期？

**修复建议**: 在 01-tick-protocol.md §8.1 中加入 Arena 的 soft/hard deadline 定义。

---

## Replay Gaps

1. **D2 (Phase 2b 并行 Combat)** — 若 S11-S13 确实直接写 HitPoints 而非 sub-buffer，则 Tower/NPC 多对一攻击场景下 replay 不确定。需确认实际实现路径。
2. **D3 (快照截断)** — 目前三份文档定义三种截断策略。在统一前，以任一文档实现的 replay 都与其他文档的预期不一致。
3. **D8 (host_get_objects_in_range 排序)** — 若返回值排序不确定，WASM 对「最近敌人」的选择非确定 → 产出不同 Command[]。
4. **D9 (pathfinding cache key)** — 简化 cache key 可能导致 terrain 变更后返回过期路径，replay 结果不一致。

## Formal State Issues

1. **06-phase2b-system-manifest.md Parallel Set C** 仅含单一 serial system (S24 decay)。「Parallel Set」的命名暗示未来扩展，但当前无并行内容——属于结构噪声，不影响正确性。
2. **01-tick-protocol.md §3.3 Per-drone action quota**: "Transfer/Withdraw 不计入此配额但受 carry 容量约束"。Transfer chain 可在单 tick 内无限串联（A→B→C→D...），虽受 carry 容量约束，但 chain 长度不受限。极端情况下可能产生指数级 entity 遍历。建议在 manifest 或 validation spec 中增加 per-tick transfer chain 长度上限。
3. **08-resource-ledger.md §4 确定性执行顺序**列出了 11 步资源操作顺序，包含 `WorldStartupSubsidy`。此操作标注为 "首次进入时一次性"——但它位于每 tick 执行列表中。若引擎每 tick 检查此条件，需确保 `is_first_tick_for_player` 判定确定性（绑定到 FDB 记录的 join_tick，非墙钟）。

---

## 附录: 文档交叉引用完整性

| 文档 | 声明「唯一权威」 | 是否被其他文档引用 |
|------|:---:|:---:|
| 06-phase2b-system-manifest.md | ✅ ECS 系统调度权威 | 01-tick-protocol.md, engine.md |
| 09-snapshot-contract.md | ✅ 快照截断权威 (R22 B5) | engine.md (未引用), 01-tick-protocol.md (冲突) |
| api-registry.md | ✅ API 合约权威 | 大部分文档 |
| 08-resource-ledger.md | ✅ 经济权威 (R22 B2) | gameplay.md (部分), api-registry.md |
| 05-persistence-contract.md | ✅ 持久化权威 (R22 B1) | engine.md |
| 01-tick-protocol.md | ✅ 确定性合同 §7-9 | 多文档引用 |

唯一缺口: **09-snapshot-contract.md 自称权威但 engine.md 和 01-tick-protocol.md 仍保留自有截断描述**——需将后两者改为引用链接。