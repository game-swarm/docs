# Persistence Contract — FDB / TickCommitRecord / RichTraceBlob / WAL / Object Store 分层

> 详见 design/engine.md
>
> **R15 B8 修复**。本文档定义 Swarm 引擎的持久化分层架构，消除 "FDB 事务内写一切" 与 "跨存储双写会炸" 之间的合同空白。
>
> **R22 B1 修复**。加入显式的 replay-critical subset 声明、Deploy 完整状态机、replay-critical 字段清单。

## 原则

1. **FDB 只写小对象**：tick head、state checksum、small manifest、object pointers + content hashes。
2. **大 BLOB 进对象存储**：RichTraceBlob（debug/rich trace）、snapshot delta、replay artifacts、WASM module binaries。
3. **单写事务原子性**：FDB commit 是唯一权威持久化点。对象存储写入失败不破坏 FDB 状态完整性。
4. **Hash 链贯穿**：FDB 记录的 content hash 证明对象存储中数据的完整性。
5. **Replay-critical 与 debug/rich 分离**：FDB 事务原子提交 replay-critical subset（保证确定性回放与反作弊审计）；对象存储承载非关键的 rich trace/debug blob（可降级、可延迟、可丢失而不影响核心正确性）。

---

## 1. 存储层职责

| 存储层 | 存储内容 | 单条上限 | 保留期 |
|--------|---------|:------:|--------|
| **FDB** | tick head、state checksum、small manifest、object pointers、content hashes、audit rows | < 1KB/row | 永久（状态） |
| **Object Store** | RichTraceBlob、snapshot delta (full/diff)、replay artifacts、WASM binaries | < 10MB/object | 7d hot / 30d warm / 180d cold |
| **WAL (Write-Ahead Log)** | 未提交的 apply 操作日志 | 滚动 | 提交后截断 |
| **Keyframe Store** | 每 K tick 的完整世界状态快照 | < 100MB | 7d hot / 30d cold |

---

## 2. Replay-Critical Subset（权威声明）

> **R22 B1**: 明确哪些 Field 必须在 FDB 事务中原子提交（replay-critical），哪些可以异步写入对象存储（debug/rich）。此声明是 `05-persistence-contract.md` 的最权威条款——所有其他文档引用 persistence 合同时以此为准。

### 2.1 TickCommitRecord Fields（FDB 原子提交 — 不可降级）

以下 10 个字段组成 TickCommitRecord，随每 tick FDB **同一事务**原子提交。缺失任一则 tick 不可 replay：

| # | 字段 | 存储位置 | 用途 |
|---|------|---------|------|
| 1 | `commands` | FDB tick_commands | 所有 validated command 记录 |
| 2 | `rejections` | FDB tick_commands | 所有 command rejection 记录 |
| 3 | `fuel` | FDB tick_fuel | 每玩家 fuel 扣费明细 |
| 4 | `deploy_activation_decision` | FDB tick_deploy | 本 tick 激活的部署列表（drone_id, module_hash, fdb_version_counter） |
| 5 | `canonical_codec_version` | FDB tick_head | 序列化格式版本 |

> **canonical_codec_version CI 校验**：`canonical_codec_version` 为 `u32` 单调递增整数。CI 管线维护 Rust (`serde_swarm`) 和 Go (`swarm-codec-go`) 双实现的确定性 hash fixture——对固定 world state dump，两实现产出的 `Blake3(canonical_serialize(state))` 必须完全一致。fixture 随 codec version 更新纳入 `specs/reference/codec_fixtures/`。
| 6 | `snapshot_hash` | FDB tick_head | COLLECT 阶段快照 hash |
| 7 | `commands_hash` | FDB tick_head | commands + rejections 的 Blake3 hash |
| 8 | `state_checksum` | FDB tick_head | world state 完整性验证 |
| 9 | `manifest_hash` | FDB tick_manifest | ECS 系统版本/调度配置 hash |
| 10 | `world_config_hash` | FDB tick_manifest | world.toml 配置 hash |

### 2.2 Debug/Rich（对象存储异步写入 — 可降级）

**Object Store 仅承载 RichTraceBlob**。对象存储中不存放 replay-critical 数据。对象存储写入失败仅导致 `terminal_state = audit_gap`（审计记录缺失，游戏状态可从相邻 tick 重建），**绝不会**导致 `unreplayable`——FDB 中 TickCommitRecord 的 10 个字段足够完成确定性 replay。

以下字段写入对象存储 blob，缺失不影响 deterministic replay：

| 字段 | 内容 | 降级行为 |
|------|------|---------|
| `rich_trace_blob` | RichTraceBlob 序列化（含 debug detail, rich events, per-system metrics） | blob 缺失 → replay 可用但 rich audit 降级; 产生 `terminal_state = audit_gap` |
| `snapshot_delta_blob` | snapshotted entity 的详细状态变更 | blob 缺失 → 从相邻 keyframe 恢复 |
| `replay_artifact_blob` | 可视化/调试用 annotation | blob 缺失 → 无影响 |

### 2.3 Deploy 完整状态机

> **R22 B1**: 消除 `swarm_deploy` 的 TOCTOU 与激活前可用性缺口。FDB manifest 原子提交 deploy intent，object store 异步上传 WASM binary。

```
状态: VALIDATE → UPLOAD_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE
                                                                      ↘ FAILED (rollback)

VALIDATE:
  ├─ 输入: wasm_bytes + metadata + player cert
  ├─ 验证: WASM 合法性、模块大小 ≤ cap、fuel 预算充足、玩家未达 drone cap
  ├─ 失败 → 拒绝部署 (ERR_DEPLOY_VALIDATION)
  └─ 成功 → 进入 UPLOAD_PREPARE

UPLOAD_PREPARE:
  ├─ 编译 WASM → 原生码（预编译，不在 tick 内 JIT）
  ├─ 计算 module_hash = Blake3(compiled_module)
  ├─ 入队异步上传任务: upload_blob(wasm_binary, object_store_key)
  └─ 进入 MANIFEST_COMMIT（不等 blob 上传完成）

MANIFEST_COMMIT:
  ├─ FDB 事务原子提交 deploy manifest:
  │   ├─ deploy_id, player_id, drone_id, module_hash, fdb_version_counter
  │   ├─ object_store_key (blob 预期位置)
  │   ├─ upload_status = "pending"
  │   └─ activation_tick = current_tick + 1 (下一完整 tick 激活)
  ├─ COMMIT 成功 → 进入 ACTIVATION_PENDING
  └─ COMMIT 失败 → 回滚，deploy_id 无效

ACTIVATION_PENDING:
  ├─ 等待 activation_tick 到达
  ├─ 期间 blob upload 可能在后台完成 (upload_status → "complete") 或失败
  └─ activation_tick 到达时:
      ├─ upload_status == "complete" AND module_hash 验证通过 → ACTIVE
      │   └─ drone 获得新 WASM 模块，下一 tick 生效
      ├─ upload_status == "failed" OR module_hash 不匹配
      │   └─ → FAILED: drone 保持旧模块(如有)或空模块
      │        FDB 记录 deploy_failure_reason
      └─ upload_status == "pending" (blob 仍在传输)
          └─ 等待最多 30s → 仍 pending → 视为 FAILED

ACTIVE:
  └─ 模块已激活。drone 在 COLLECT 阶段使用此模块执行。

FAILED:
  ├─ FDB 记录 deploy_failure_reason
  ├─ object store 中 blob (如有) 由 GC 清理 (保留 1h 后删除)
  └─ 玩家可重新部署
```

**关键不变量（Deploy）**：
- **FDB manifest 是 deploy 的唯一权威记录**：`fdb_version_counter` 为 replay 提供严格全序。blob upload 异步执行，不阻塞 tick 循环。
- **同一 tick 内的 deploy 不影响当前 tick**：WASM 模块快照在 COLLECT 开始时确定。deploy 在 `activation_tick`（≥ current_tick + 1）生效。
- **Blob 缺失不影响 FDB 状态完整性**：`upload_status = "failed"` 时 drone 保持旧模块或空模块，FDB 状态不受对象存储影响。
- **Deploy mutation 的 replay class**：`deploy_mutation` — 状态变更通过 FDB 事务原子化，replay verifier 以 `fdb_version_counter` 全序重放，不依赖对象存储 blob 可用性。

---

## 3. Tick Commit 序列

> **D5/B 裁决**：对象存储写入改为异步——FDB commit 先完成，blob upload 在后台执行。FDB 仅存储 manifest + content_hash + pointer，不等待 blob 写入结果。

每个 tick 结束时执行以下持久化序列：

```
Phase A: Apply 完成
  ├─ 所有系统执行完毕，world state 确定
  ├─ state_checksum = Blake3(canonical_serialize(world))
  └─ RichTraceBlob 完整序列化到内存 buffer
  └─ 计算 content_hash = Blake3(compress(serialize(RichTraceBlob)))

Phase B: FDB 事务提交（原子 — 先于对象存储写入）
  ├─ BEGIN FDB TRANSACTION
  ├─ INSERT tick_head (tick, state_checksum, timestamp)
  ├─ INSERT tick_manifest (tick, object_id, content_hash, blob_size, upload_status = "pending")
  │   └─ 注意：object_store_etag 此时为 NULL（blob 尚未写入）
  ├─ INSERT tick_hash_chain (tick, chain_hash = Blake3(prev_chain_hash || tick_head_hash))
  ├─ FOR each persistent state mutation:
  │   └─ UPDATE entity/resource/controller/... rows
  ├─ COMMIT
  └─ 若 COMMIT 成功 → tick 持久化完成（world state 已安全）
     若 COMMIT 失败 → 事务回滚，tick 放弃

Phase C: 对象存储异步写入（FDB commit 成功后触发）
  ├─ 入队异步任务：write_blob(tick, tick_trace_binary, object_id)
  ├─ 任务成功：
  │   ├─ UPDATE tick_manifest SET upload_status = "complete", object_store_etag = <etag>
  │   └─ RichTraceBlob 可被 replay 读取
  ├─ 任务失败（网络/超时）：
  │   ├─ 重试最多 3 次（指数退避 1s/2s/4s）
  │   ├─ 3 次均失败 → UPDATE tick_manifest SET upload_status = "failed"
  │   └─ blob 缺失不影响 world state（FDB 已有完整状态），但该 tick replay 不可用
  └─ 任务超时（> 5s）：
      └─ 同失败处理

Phase D: WAL 截断
  └─ 截断已提交 tick 的 WAL 条目
```

### Async Upload Status Tracking

`tick_manifest` 表扩展 `upload_status` 字段，跟踪每个 tick 的 blob 上传生命周期：

| upload_status | 含义 | tick state 完整性 |
|:---|------|:---:|
| `pending` | blob 尚未写入对象存储 | ✅ FDB state 完整，replay 不可用 |
| `uploading` | blob 正在写入（worker 已接管） | ✅ FDB state 完整 |
| `complete` | blob 已写入，etag 已回填 | ✅✅ 完全持久化，replay 可用 |
| `failed` | 3 次重试后仍失败 | ✅ FDB state 完整，replay 不可用 |

**Replay 检查**：replay verifier 查询 `tick_manifest.upload_status`：
- `complete` → 从对象存储拉取 blob，验证 hash
- `pending` / `uploading` → 等待最多 30s 后重试；超时则降级为 `failed`
- `failed` → 跳过该 tick（replay gap），标记 `terminal_state = audit_gap`

**孤儿清理**：由于 FDB 先于对象存储写入，不再产生孤儿 blob。若 blob 写入成功但 etag 回填失败（FDB 更新超时），GC 通过对比对象存储中 blob 的 created_at 与 tick_manifest 中 upload_status 清理（`upload_status = 'failed'` 但对象存储中存在 blob → 保留 1h 后清理）。

### 关键不变量（更新）

- **FDB commit 成功 = tick 持久化完成**：`tick_manifest` 行证明 tick 已发生，`content_hash` 证明 blob 完整性。**blob 写入不再是 tick commit 的前提条件。**
- **FDB 只存小对象**：`tick_manifest` 仅含 `object_id + content_hash + blob_size + upload_status`——无 blob 本体。
- **FDB commit 失败 = tick 未发生**：world state 回滚到 Pre-Apply 快照，玩家 WASM 不重跑，tick 编号不递增。
- **TickCommitRecord hash chain 仅在 FDB commit 成功后追加**：prev_chain_hash 取自上一个已提交 tick，失败 tick 不产生链条目。

---

## 4. 持久化失败语义（D5/B async 模型）

FDB commit 先于对象存储写入——以下为所有失败场景的处理：

| 场景 | FDB 状态 | 对象存储状态 | 处理 |
|------|:------:|:----------:|------|
| 正常 | ✅ 已提交 | ✅ 已写入（异步完成） | 正常。`upload_status = complete` |
| FDB commit 失败 | ❌ 回滚 | ❌ 未写入 | Tick 放弃，不递增 tick 编号 |
| FDB commit 成功 + blob 写入成功 | ✅ 已提交 | ✅ 已写入 | 正常 |
| FDB commit 成功 + blob 写入失败（3 次重试后） | ✅ 已提交 | ❌ 缺失 | `upload_status = failed`。world state 完整，replay 不可用 |
| FDB commit 成功 + blob 写入超时（> 5s） | ✅ 已提交 | ❓ 未知 | 重试 3 次；仍失败 → `upload_status = failed` |
| Blob 写入成功 + etag 回填失败 | ✅ 已提交 | ✅ 已写入 | 对象存储中存在 blob 但 manifest 中无 etag。GC 扫描：1h 后若 `upload_status != 'complete'` 则清理孤儿 blob |

---

## 5. Replay 恢复

### 5.1 正常 Replay

```
1. 从 FDB 读取目标 tick 的 tick_manifest
2. 从对象存储按 object_id 获取 tick_trace_blob
3. 验证 Blake3(tick_trace_blob) == tick_manifest.content_hash
4. 验证 tick_hash_chain 完整性：从上一个 keyframe tick 到目标 tick
5. 反序列化 TickCommitRecord
6. 从最近 keyframe（≤ 目标 tick）恢复 world state
7. 重放 delta chain: keyframe → 目标 tick
```

### 5.2 Keyframe 不可用时

若目标 tick 最近的 keyframe 已被 GC：

```
1. 从 FDB 全量重建 world state（每个实体的最新状态）
2. 验证 FDB state_checksum 是否匹配 keyframe 的存在性
3. 若无可用 keyframe 且无 FDB 全量 → 该 tick 范围不可 replay
```

### 5.3 Replay Verifier 输入

Replay verifier 以 **FDB commit 的 manifest/hash 为权威**，不重新扫描对象存储：

- 输入: `(start_tick, end_tick, fdb_manifest_list, object_store_blobs)`
- 验证: 每个 tick 的 `tick_manifest.content_hash` 匹配 blob
- 验证: `tick_hash_chain` 连续且匹配
- 输出: `ReplayResult { verified, mismatches, first_bad_tick }`

---

## 6. GC (垃圾回收)

### 6.1 对象存储 GC

| 层级 | TTL | 清理策略 |
|------|:---:|---------|
| hot | 7d | tick + 7d 后转移至 warm |
| warm | 30d | tick + 30d 后转移至 cold |
| cold | 180d | tick + 180d 后删除 |

**孤儿清理**: 由于 FDB commit 先于 blob 写入，正常流程不产生孤儿 blob。唯一孤儿场景：blob 写入成功但 etag 回填失败 → GC 扫描 `upload_status != 'complete'` 但对象存储中存在对应 blob → 保留 1h 后删除。**正常 `upload_status = 'complete'` 的 blob 按 TTL 分层清理**（见上表）。

### 6.2 Keyframe GC

- hot: 保留 7d（每 K tick 一个 keyframe）
- cold: 保留 30d（每 10K tick 一个 keyframe）
- 删除 keyframe 时同步删除对应的 snapshot delta chain

### 6.3 WAL GC

- 每次 FDB commit 成功后截断已提交 tick 的 WAL
- WAL 仅保留未提交 tick 的条目

---

## 7. Commit Retry 对 Hash Chain 的影响（R16 B3 修复）

```
若 tick N 的 FDB commit 因瞬时错误（网络/锁冲突）失败：
  1. world state 回滚到 Pre-Apply 快照
  2. 不递增 tick 编号
  3. 复用 canonical COLLECT buffer：
     - snapshot_hash（相同——COLLECT 快照不变）
     - commands（相同——相同的 WASM 输出序列）
     - wasm_status（相同——WASM 不重跑）
     - fuel_ledger（相同——不追加扣费）
  4. ❌ 不重新执行 WASM（避免非确定性输出与双倍扣费）
  5. 重新执行 EXECUTE phase + FDB commit（使用相同 COLLECT 结果）
  6. 每次 retry attempt 产生新的 attempt_id（递增），但 collect_id 不变
  7. 最终 commit 成功后，commit_id 关联到成功的 attempt_id
```

这意味着：**同一 tick 编号的 TickCommitRecord 可能包含多个 attempt（attempt_id 递增），但 collect_id 始终不变**。Replay 只关心最终 committed 的 attempt——hash chain 验证以 FDB 中实际存在的链为准。跨 attempt 的燃料消耗上限 = `1 × MAX_FUEL`（首次 COLLECT 时的扣费即为最终扣费，重试不追加）。

### 7.1 TickCommitRecord 标识字段

TickCommitRecord 中新增以下标识字段以支持 attempt/collect/commit 追踪：

| 字段 | 类型 | 语义 |
|------|------|------|
| `collect_id` | `Blake3(tick || snapshot_hash || commands_hash)` | COLLECT 阶段的唯一标识。同一 tick 的所有 retry 共享此值。首次 COLLECT 后确定，重试不变。 |
| `attempt_id` | `u32`（从 0 开始递增） | 本次 commit 尝试的序号。首次尝试 = 0，每次 retry +1。仅当 commit 成功或 tick 放弃时终止。 |
| `commit_id` | `Blake3(collect_id || attempt_id || state_checksum)` | 成功 commit 的唯一标识。仅在 FDB commit 成功后生成。失败 attempt 无 commit_id。 |

**TickCommitRecord 结构**（R16 B3 扩展）：

```
TickCommitRecord {
    tick: u64,
    collect_id: Blake3,          // NEW — COLLECT 阶段唯一标识
    attempt_id: u32,             // NEW — 本次 commit 尝试序号
    commit_id: Option<Blake3>,   // NEW — commit 成功时填充
    snapshot_hash: Blake3,
    commands_hash: Blake3,
    wasm_status: WasmStatus,
    fuel_ledger: FuelLedger,
    state_checksum: Blake3,
    system_manifest_hash: Blake3,
    // ... 其余字段不变
}
```

### 7.2 Blob 损坏终端状态

当对象存储中的 RichTraceBlob 无法正常读取或验证时，引擎根据恢复能力将其归类为以下四种终端状态：

| 终端状态 | 定义 | 触发条件 | 恢复能力 |
|----------|------|---------|:--------:|
| `verified` | Blob 完整可用，`Blake3(blob) == content_hash` | 正常读取 + hash 匹配 | ✅ 直接使用 |
| `audit_gap` | Blob 缺失或部分损坏，但状态可从相邻 tick 重建 | content_hash 不匹配 OR 对象存储 404，但相邻 tick 的 state_checksum 链完整 | ⚠️ 审计记录缺失，游戏状态可重建（从前后 keyframe 插值） |
| `unreplayable` | Blob 不可读且无法从相邻 tick 重建 | content_hash 不匹配 AND 前后 keyframe 均不可用 | ❌ 该 tick 范围永久不可回放。审计记录不可恢复。 |
| `reconstructable` | Blob 部分损坏但可恢复（如 bit flip 在非关键段） | 次要字段损坏但关键字段（commands、state_checksum、fuel_ledger）可解析 | 🔧 部分恢复。损坏字段标记为 `reconstructed: true`。 |

**损坏检测流程**：

```
1. 从 FDB 读取 tick_manifest → 获取 object_id + content_hash
2. 从对象存储获取 blob
3. 验证 Blake3(blob) == content_hash
   ├─ 匹配 → terminal_state = verified
   └─ 不匹配 OR blob 不存在：
       ├─ 尝试从相邻 keyframe + delta chain 恢复
       │   ├─ 恢复成功 → terminal_state = audit_gap
       │   └─ 恢复失败 → terminal_state = unreplayable
       └─ 尝试部分解析 blob
           ├─ 关键字段完整 → terminal_state = reconstructable
           └─ 关键字段损坏 → terminal_state = unreplayable
```

**与 hash chain 的关系**：RichTraceBlob delta chain 按 tick 递增形成链——`chain[i] = Blake3(chain[i-1] || tick_commit_record_i)`。任一 tick 的 blob 进入 `unreplayable` 状态 → 链断裂 → replay verifier 可检测到损坏起始 tick。损坏 tick 之前的状态仍可验证，之后的需从最近有效 keyframe 重建。

---

## 8. Room-Partition FDB 事务策略

> **R23 D6/B 裁决**：FDB room-partition transaction 纳入 Phase 1 合同。单事务 MVP 仅支持小规模验证；500/1000-player 场景必须使用 room-level partition。

### 8.1 分区策略

```
单事务 MVP (默认):
  适用: ≤ 50 active players, ≤ 100 rooms
  策略: 整个 world 单 FDB 事务
  热区: tick_head + state_checksum + manifest (shared)
  
Room-Partition (500+ players):
  适用: > 50 active players 或 > 100 rooms
  策略: 每个 room 独立 FDB 事务分区
  Key layout: /swarm/{shard}/{room_id}/{tick}/{...}
  Conflict range: per-room transaction 不跨 room 冲突
  Cross-room operations: 2-phase commit（source room → target room）
```

### 8.2 实现约束

| 约束 | 单事务 MVP | Room-Partition |
|------|-----------|---------------|
| FDB 事务大小 | 单 tick < 10KB | 每 room < 2KB |
| 对象存储异步写入超时 | 5s；3 次重试 | 5s；3 次重试 |
| 对象存储读取 | 延迟 < 100ms p99 | 不变 |
| Keyframe 写入 | 异步，不阻塞 tick 循环 | 不变 |
| WAL 写入 | 同步 | per-room WAL |
| 内存 buffer | RichTraceBlob 10MB max | 不变 |
| Cross-room conflict | N/A | 2PC，超时 3s，fallback to best-effort |

### 8.3 Synthetic Benchmark 要求

为证明容量声明，实现 Phase 需交付以下 benchmark gate：

| Benchmark | 目标 | 判定标准 |
|-----------|------|---------|
| Command validate loop | 100k commands/tick | p99 < 50ms |
| Command apply loop | 100k commands/tick | p99 < 100ms |
| Entity snapshot clone | 50k entities | p99 < 20ms |
| Entity snapshot restore | 50k entities | p99 < 30ms |
| Snapshot stitching | 1000 × 256KB snapshots | p99 < 100ms |
| FDB single-tx commit | 500 active players | p99 < 200ms, conflict rate < 1% |
| FDB room-partition commit | 1000 active players, 200 rooms | p99 < 500ms, per-room conflict rate < 1% |
| Pathfinding | 50×50 A* nodes, 100 concurrent ops | p99 < 10ms/node, fair-share guarantee |
| Rollback Bevy snapshot/restore | 500 entities, all components | p99 < 50ms, entity ID allocator verified |

Gate 失败 → 对应容量声明不可信，需降级规模或优化实现。

---

## 9. 与现有文档的关系

- `design/engine.md` §3.3 (TickInputEnvelope)、§3.4.2 (容量合同)、§3.4.7 (keyframe)：本文件为权威持久化合同。engine.md 描述架构意图，本文档定义实现合同。
- `specs/core/01-tick-protocol.md` §2.3 (快照)、§9.4 (TickCommitRecord 完整性)：本文件补充持久化层面。
- `specs/core/02-command-validation.md`：apply 阶段在本文件的 "Phase A" 中执行。
