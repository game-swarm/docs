# Persistence Contract — FDB / TickTrace / WAL / Object Store 分层

> **R15 B8 修复**。本文档定义 Swarm 引擎的持久化分层架构，消除 "FDB 事务内写一切" 与 "跨存储双写会炸" 之间的合同空白。

## 原则

1. **FDB 只写小对象**：tick head、state checksum、small manifest、object pointers + content hashes。
2. **大 BLOB 进对象存储**：完整 TickTrace、snapshot delta、replay artifacts、WASM module binaries。
3. **单写事务原子性**：FDB commit 是唯一权威持久化点。对象存储写入失败不破坏 FDB 状态完整性。
4. **Hash 链贯穿**：FDB 记录的 content hash 证明对象存储中数据的完整性。

---

## 1. 存储层职责

| 存储层 | 存储内容 | 单条上限 | 保留期 |
|--------|---------|:------:|--------|
| **FDB** | tick head、state checksum、small manifest、object pointers、content hashes、audit rows | < 1KB/row | 永久（状态） |
| **Object Store** | 完整 TickTrace、snapshot delta (full/diff)、replay artifacts、WASM binaries | < 10MB/object | 7d hot / 30d warm / 180d cold |
| **WAL (Write-Ahead Log)** | 未提交的 apply 操作日志 | 滚动 | 提交后截断 |
| **Keyframe Store** | 每 K tick 的完整世界状态快照 | < 100MB | 7d hot / 30d cold |

---

## 2. Tick Commit 序列

每个 tick 结束时执行以下持久化序列：

```
Phase A: Apply 完成
  ├─ 所有系统执行完毕，world state 确定
  ├─ state_checksum = Blake3(canonical_serialize(world))
  └─ TickTrace 完整序列化到内存 buffer

Phase B: 对象存储写入（可并行）
  ├─ Write tick_trace_blob = compress(serialize(TickTrace))
  ├─ object_id = "{tick}/tick_trace.bin.zst"
  ├─ content_hash = Blake3(tick_trace_blob)
  └─ 写入对象存储，获得 object_store_etag

Phase C: FDB 事务提交（原子）
  ├─ BEGIN FDB TRANSACTION
  ├─ INSERT tick_head (tick, state_checksum, timestamp)
  ├─ INSERT tick_manifest (tick, object_id, content_hash, object_store_etag, blob_size)
  ├─ INSERT tick_hash_chain (tick, chain_hash = Blake3(prev_chain_hash || tick_head_hash))
  ├─ FOR each persistent state mutation:
  │   └─ UPDATE entity/resource/controller/... rows
  ├─ COMMIT
  └─ 若 COMMIT 成功 → TickTrace 持久化完成
     若 COMMIT 失败 → 事务回滚（对象存储中的 blob 成为孤儿，由 GC 清理）

Phase D: WAL 截断
  └─ 截断已提交 tick 的 WAL 条目
```

### 关键不变量

- **对象存储写入先于 FDB commit**：即使对象写入成功但 FDB commit 回滚，孤儿 blob 由 GC 清理。
- **FDB commit 成功 = tick 持久化完成**：`tick_manifest` 行证明对象存储 blob 的存在性。
- **FDB commit 失败 = tick 未发生**：world state 回滚到 Pre-Apply 快照，玩家 WASM 不重跑，tick 编号不递增。
- **TickTrace hash chain 仅在 FDB commit 成功后追加**：prev_chain_hash 取自上一个已提交 tick，失败 tick 不产生链条目。

---

## 3. 双写失败语义

| 场景 | 对象存储状态 | FDB 状态 | 处理 |
|------|:----------:|:------:|------|
| 正常 | ✅ 已写入 | ✅ 已提交 | 正常 |
| 对象存储写入失败 | ❌ 失败 | ❌ 回滚 | Tick 放弃，不递增 tick 编号 |
| 对象存储写入超时 | ❓ 未知 | ❌ 回滚 | 即使对象最终写入成功，FDB 无对应 manifest → GC 清理 |
| FDB commit 失败 | ✅ 已写入 | ❌ 回滚 | 对象成为孤儿 → GC 按 `created_at + orphan_ttl` 清理 |
| FDB commit 超时 | ✅ 已写入 | ❓ 未知 | 重新查询 tick_head。若存在 + 匹配 content_hash = 成功；否则回滚 + GC |

---

## 4. Replay 恢复

### 4.1 正常 Replay

```
1. 从 FDB 读取目标 tick 的 tick_manifest
2. 从对象存储按 object_id 获取 tick_trace_blob
3. 验证 Blake3(tick_trace_blob) == tick_manifest.content_hash
4. 验证 tick_hash_chain 完整性：从上一个 keyframe tick 到目标 tick
5. 反序列化 TickTrace
6. 从最近 keyframe（≤ 目标 tick）恢复 world state
7. 重放 delta chain: keyframe → 目标 tick
```

### 4.2 Keyframe 不可用时

若目标 tick 最近的 keyframe 已被 GC：

```
1. 从 FDB 全量重建 world state（每个实体的最新状态）
2. 验证 FDB state_checksum 是否匹配 keyframe 的存在性
3. 若无可用 keyframe 且无 FDB 全量 → 该 tick 范围不可 replay
```

### 4.3 Replay Verifier 输入

Replay verifier 以 **FDB commit 的 manifest/hash 为权威**，不重新扫描对象存储：

- 输入: `(start_tick, end_tick, fdb_manifest_list, object_store_blobs)`
- 验证: 每个 tick 的 `tick_manifest.content_hash` 匹配 blob
- 验证: `tick_hash_chain` 连续且匹配
- 输出: `ReplayResult { verified, mismatches, first_bad_tick }`

---

## 5. GC (垃圾回收)

### 5.1 对象存储 GC

| 层级 | TTL | 清理策略 |
|------|:---:|---------|
| hot | 7d | tick + 7d 后转移至 warm |
| warm | 30d | tick + 30d 后转移至 cold |
| cold | 180d | tick + 180d 后删除 |

**孤儿清理**: 对象创建后 1h 内若无对应 `tick_manifest` 行 → 标记为 orphan → 24h 后删除。

### 5.2 Keyframe GC

- hot: 保留 7d（每 K tick 一个 keyframe）
- cold: 保留 30d（每 10K tick 一个 keyframe）
- 删除 keyframe 时同步删除对应的 snapshot delta chain

### 5.3 WAL GC

- 每次 FDB commit 成功后截断已提交 tick 的 WAL
- WAL 仅保留未提交 tick 的条目

---

## 6. Commit Retry 对 Hash Chain 的影响（R16 B3 修复）

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

这意味着：**同一 tick 编号的 TickTrace 可能包含多个 attempt（attempt_id 递增），但 collect_id 始终不变**。Replay 只关心最终 committed 的 attempt——hash chain 验证以 FDB 中实际存在的链为准。跨 attempt 的燃料消耗上限 = `1 × MAX_FUEL`（首次 COLLECT 时的扣费即为最终扣费，重试不追加）。

### 6.1 TickTrace 标识字段

TickTrace 中新增以下标识字段以支持 attempt/collect/commit 追踪：

| 字段 | 类型 | 语义 |
|------|------|------|
| `collect_id` | `Blake3(tick || snapshot_hash || commands_hash)` | COLLECT 阶段的唯一标识。同一 tick 的所有 retry 共享此值。首次 COLLECT 后确定，重试不变。 |
| `attempt_id` | `u32`（从 0 开始递增） | 本次 commit 尝试的序号。首次尝试 = 0，每次 retry +1。仅当 commit 成功或 tick 放弃时终止。 |
| `commit_id` | `Blake3(collect_id || attempt_id || state_checksum)` | 成功 commit 的唯一标识。仅在 FDB commit 成功后生成。失败 attempt 无 commit_id。 |

**TickTrace 结构**（R16 B3 扩展）：

```
TickTrace {
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

### 6.2 Blob 损坏终端状态

当对象存储中的 TickTrace blob 无法正常读取或验证时，引擎根据恢复能力将其归类为以下四种终端状态：

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

**与 hash chain 的关系**：TickTrace delta chain 按 tick 递增形成链——`chain[i] = Blake3(chain[i-1] || tick_trace_i)`。任一 tick 的 blob 进入 `unreplayable` 状态 → 链断裂 → replay verifier 可检测到损坏起始 tick。损坏 tick 之前的状态仍可验证，之后的需从最近有效 keyframe 重建。

---

## 7. 实现约束

| 约束 | 要求 |
|------|------|
| FDB 事务大小 | 单 tick 事务 < 10KB（仅 tick_head + manifest + hash_chain row + small mutations） |
| 对象存储写入超时 | 5s；超时 → tick 放弃，不重试对象写入 |
| 对象存储读取 | 延迟 < 100ms p99 |
| Keyframe 写入 | 异步，不阻塞 tick 循环 |
| WAL 写入 | 同步，在 Apply 阶段每步写入 |
| 内存 buffer | TickTrace 序列化后最大 10MB buffer；超限 → tick 放弃 + metric 告警 |

---

## 8. 与现有文档的关系

- `design/engine.md` §3.3 (TickInputEnvelope)、§3.4.2 (容量合同)、§3.4.7 (keyframe)：本文件为权威持久化合同。engine.md 描述架构意图，本文档定义实现合同。
- `specs/core/01-tick-protocol.md` §2.3 (快照)、§9.4 (TickTrace hash chain)：本文件补充持久化层面。
- `specs/core/02-command-validation.md`：apply 阶段在本文件的 "Phase A" 中执行。
