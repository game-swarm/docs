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

## 6. Commit Retry 对 Hash Chain 的影响

```
若 tick N 的 FDB commit 因瞬时错误（网络/锁冲突）失败：
  1. world state 回滚到 Pre-Apply 快照
  2. 不递增 tick 编号
  3. 下次循环重新执行 tick N（重跑 COLLECT → apply）
  4. 重新生成 TickTrace（可能不同，因为时间流逝）
  5. 新的 TickTrace 产生新的 content_hash
  6. 提交成功后，chain_hash 包含新 hash
```

这意味着：**同一 tick 编号的 tick_hash_chain 条目在重试后可能不同**。Replay 只关心最终 committed 的条目——hash chain 验证以 FDB 中实际存在的链为准。

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
