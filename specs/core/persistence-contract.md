# Persistence Contract — redb / TickCommitRecord / RichTraceBlob / WAL / Object Store 分层

> 详见 design/engine.md
>
> **R15 B8 修复**。本文档定义 Swarm 引擎的持久化分层架构，消除 "redb WriteTransaction 内写一切" 与 "跨存储双写会炸" 之间的合同空白。
>
> **R22 B1 修复**。加入显式的 replay-critical subset 声明、Deploy 完整状态机、replay-critical 字段清单。

## 原则

1. **redb 只写小对象**：tick head、state checksum、small manifest、object pointers + content hashes。
2. **大 BLOB 进对象存储**：RichTraceBlob（debug/rich trace）、snapshot delta、replay artifacts、WASM module binaries。
3. **单写事务原子性**：redb WriteTransaction commit 是唯一权威持久化点。对象存储写入失败不破坏 redb 状态完整性。
4. **Hash 链贯穿**：redb 记录的 content hash 证明对象存储中数据的完整性。
5. **Replay-critical 与 debug/rich 分离**：redb 事务原子提交 replay-critical subset（保证确定性回放与反作弊审计）；对象存储承载非关键的 rich trace/debug blob（可降级、可延迟、可丢失而不影响核心正确性）。

---

## 1. 存储层职责

| 存储层 | 存储内容 | 单条上限 | 保留期 |
|--------|---------|:------:|--------|
| **redb** | tick head、state checksum、small manifest、object pointers、content hashes、audit rows | < 1KB/row | 永久（状态） |
| **Object Store** | RichTraceBlob、snapshot delta (full/diff)、replay artifacts、WASM binaries | < 10MB/object | 7d hot / 30d warm / 180d cold |
| **WAL (Write-Ahead Log)** | 未提交的 apply 操作日志 | 滚动 | 提交后截断 |
| **Keyframe Store** | 每 K tick 的完整世界状态快照 | < 100MB | 7d hot / 30d cold |

---

## 2. Replay-Critical Subset（权威声明）

> **R22 B1**: 明确哪些 Field 必须在 redb WriteTransaction 中原子提交（replay-critical），哪些可以异步写入对象存储（debug/rich）。此声明是 `persistence-contract.md` 的最权威条款——所有其他文档引用 persistence 合同时以此为准。

### 2.1 TickCommitRecord Fields（redb 原子提交 — 不可降级）

以下 10 个字段组成 TickCommitRecord，随每 tick redb **同一 WriteTransaction** 原子提交。缺失任一则 tick 不可 replay。

**三层分离声明：**
- **deterministic_replay**：仅需 redb 中 TickCommitRecord 的 10 个字段 + keyframe/delta chain。对象存储中的任何数据均非 replay 必需。
- **rich_debug_replay**：RichTraceBlob（可选，存储于对象存储）。缺失 → `terminal_state = audit_gap`（审计记录缺失，可从相邻 tick/keyframe 重建）。
- **WASM module blob**：对象存储中的 WASM 二进制。**非 replay-critical**。缺失 → 安全审计 gap（无法重新读取玩家提交的 WASM bytecode），**绝非** `unreplayable`——redb manifest 中的 `wasm_module_hash`、`compiled_artifact_hash` 与 `redb_version_counter` 足够完成确定性 replay。

| # | 字段 | 存储位置 | 用途 |
|---|------|---------|------|
| 1 | `commands` | redb tick_commands | 所有 validated command 记录 |
| 2 | `rejections` | redb tick_commands | 所有 command rejection 记录 |
| 3 | `fuel` | redb tick_fuel | 每玩家 fuel 扣费明细 |
| 4 | `deploy_activation_decision` | redb tick_deploy | 本 tick 激活的部署列表（drone_id, wasm_module_hash, compiled_artifact_hash, redb_version_counter） |
| 5 | `canonical_codec_version` | redb tick_head | 序列化格式版本 |

> **canonical_codec_version CI 校验**：`canonical_codec_version` 为 `u32` 单调递增整数。CI 管线维护 Rust (`serde_swarm`) 和 Go (`swarm-codec-go`) 双实现的确定性 hash fixture——对固定 world state dump，两实现产出的 `Blake3(canonical_serialize(state))` 必须完全一致。fixture 随 codec version 更新纳入 `specs/reference/codec_fixtures/`。
| 6 | `snapshot_hash` | redb tick_head | COLLECT 阶段快照 hash |
| 7 | `commands_hash` | redb tick_head | commands + rejections 的 Blake3 hash |
| 8 | `state_checksum` | redb tick_head | world state 完整性验证 |
| 9 | `manifest_hash` | redb tick_manifest | ECS 系统版本/调度配置 hash |
| 10 | `world_config_hash` | redb tick_manifest | world.toml 配置 hash |

### 2.2 Debug/Rich（对象存储异步写入 — 可降级）

**Object Store 仅承载 RichTraceBlob**。对象存储中不存放 replay-critical 数据。对象存储写入失败仅导致 `terminal_state = audit_gap`（审计记录缺失，游戏状态可从相邻 tick 重建），**绝不会**导致 `unreplayable`——redb 中 TickCommitRecord 的 10 个字段足够完成确定性 replay。

> **WASM 模块 blob 非 replay-critical（D6）**：WASM 模块二进制文件存储在对象存储中，其可用性不影响确定性 replay。Replay verifier 仅使用 redb 中的 TickCommitRecord（含 `commands`、`canonical_codec_version`、`manifest_hash` 等 10 字段）重放，不重新执行 WASM 模块。WASM 模块 blob 缺失只影响 rich audit/debug 路径——deploy 的 `deploy_activation_decision` 已在 redb 清单中通过 `wasm_module_hash`、`compiled_artifact_hash` + `redb_version_counter` 完整记录激活决策，replay 不需要原始 WASM 字节。

以下字段写入对象存储 blob，缺失不影响 deterministic replay：

| 字段 | 内容 | 降级行为 |
|------|------|---------|
| `rich_trace_blob` | RichTraceBlob 序列化（含 debug detail, rich events, per-system metrics） | blob 缺失 → replay 可用但 rich audit 降级; 产生 `terminal_state = audit_gap` |
| `snapshot_delta_blob` | snapshotted entity 的详细状态变更 | blob 缺失 → 从相邻 keyframe 恢复 |
| `replay_artifact_blob` | 可视化/调试用 annotation | blob 缺失 → 无影响 |

### 2.3 Deploy 完整状态机

> **R22 B1 / R35 D4+B6**: 消除 `swarm_deploy` 的 TOCTOU 与激活前可用性缺口。`swarm_deploy` RPC 同步携带 `wasm_bytes`、`metadata` 与签名 `DeployPayload`；服务端在请求内完成 hash 计算、验证、编译准备与 redb manifest 原子提交。Object store 仅在 commit 后异步保存 WASM binary，用于审计/调试，不参与接受判定。

```
状态: VALIDATE → COMPILE_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE
                                                                      ↘ FAILED (rollback)

VALIDATE:
  ├─ 输入: wasm_bytes + metadata + player cert
  ├─ 验证: WASM 合法性、模块大小 ≤ cap、fuel 预算充足、玩家未达 drone cap
  ├─ 失败 → 拒绝部署 (ERR_DEPLOY_VALIDATION)
  └─ 成功 → 进入 COMPILE_PREPARE

COMPILE_PREPARE:
  ├─ 计算 wasm_module_hash = Blake3(wasm_bytes)
  ├─ 编译 WASM → 原生码（预编译，不在 tick 内 JIT）
  ├─ 计算 compiled_artifact_hash = Blake3(compiled_artifact_bytes)
  ├─ 准备 object_store_key（commit 后异步保存原始 wasm_bytes）
  └─ 进入 MANIFEST_COMMIT（不等 blob 上传完成）

MANIFEST_COMMIT:
  ├─ redb WriteTransaction 原子提交 deploy manifest:
  │   ├─ deploy_id, player_id, drone_id, wasm_module_hash, compiled_artifact_hash, redb_version_counter
  │   ├─ object_store_key (原始 wasm_bytes blob 预期位置)
  │   ├─ upload_status = "pending"
  │   └─ activation_tick = current_tick + 1 (下一完整 tick 激活)
  ├─ COMMIT 成功 → 进入 ACTIVATION_PENDING
  └─ COMMIT 失败 → 回滚，deploy_id 无效

ACTIVATION_PENDING:
  ├─ 等待 activation_tick 到达
  ├─ 期间原始 wasm_bytes blob upload 可能在后台完成 (upload_status → "complete") 或失败
  └─ activation_tick 到达时:
      ├─ compiled_artifact_hash 与预编译 artifact 匹配 → ACTIVE
      │   └─ drone 获得新 WASM 模块，下一 tick 生效
      ├─ compiled_artifact_hash 不匹配或预编译 artifact 不可用
      │   └─ → FAILED: drone 保持旧模块(如有)或空模块
      │        redb 记录 deploy_failure_reason
      └─ upload_status == "pending" (原始 wasm blob 仍在传输)
          └─ 不阻塞激活；记录 `wasm_blob_audit_gap_pending`

ACTIVE:
  └─ 模块已激活。drone 在 COLLECT 阶段使用此模块执行。

FAILED:
  ├─ redb 记录 deploy_failure_reason
  ├─ object store 中 blob (如有) 由 GC 清理 (保留 1h 后删除)
  └─ 玩家可重新部署
```

**关键不变量（Deploy）**：
- **redb manifest 是 deploy 的唯一权威记录**：`redb_version_counter` 为 replay 提供严格全序。`wasm_module_hash` 与 `compiled_artifact_hash` 分离保存；blob upload 异步执行，不阻塞 tick 循环或激活判定。
- **同一 tick 内的 deploy 不影响当前 tick**：WASM 模块快照在 COLLECT 开始时确定。deploy 在 `activation_tick`（≥ current_tick + 1）生效。
- **Blob 缺失不影响 redb 状态完整性或模块激活**：`upload_status = "failed"` 只表示原始 WASM 审计 blob 缺失；只要 redb manifest 与预编译 artifact 完整，drone 仍可激活新模块。缺失 blob 产生 audit gap，不产生 deploy rollback。
- **Deploy mutation 的 replay class**：`deploy_mutation` — 状态变更通过 redb WriteTransaction 原子化，replay verifier 以 `redb_version_counter` 全序重放，不依赖对象存储 blob 可用性。

---

## 3. Tick Commit 序列

> **R39 D5 裁决 (A)**：生产环境统一 per-room staging payload + GlobalTickCommit manifest-only publish。直接 `UPDATE entity/resource/controller/... rows` 仅用于 dev/test small profile（≤ 50 active players, ≤ 100 rooms），且必须标注不适用 production。

每个 tick 结束时执行以下持久化序列：

```
Phase A: Apply 完成
  ├─ 所有系统执行完毕，world state 确定
  ├─ state_checksum = Blake3(canonical_serialize(world))
  └─ RichTraceBlob 完整序列化到内存 buffer
  └─ 计算 content_hash = Blake3(compress(serialize(RichTraceBlob)))

Phase B: redb WriteTransaction 提交（原子 — 先于对象存储写入）
  ├─ BEGIN redb TRANSACTION
  ├─ INSERT tick_head (tick, state_checksum, timestamp)
  ├─ INSERT tick_manifest (tick, object_id, content_hash, blob_size, upload_status = "pending")
  │   └─ 注意：object_store_etag 此时为 NULL（blob 尚未写入）
  ├─ INSERT tick_hash_chain (tick, chain_hash = Blake3(prev_chain_hash || tick_head_hash))
  ├─ FOR each persistent state mutation (production: skip — use staging+manifest publish):
  │   └─ UPDATE entity/resource/controller/... rows  // dev/test small profile only; production uses Shadow Write (see §3.5)
  ├─ COMMIT
  └─ 若 COMMIT 成功 → tick 持久化完成（world state 已安全）
     若 COMMIT 失败 → 事务回滚，tick 放弃

Phase C: 对象存储异步写入（redb commit 成功后触发）
  ├─ 入队异步任务：write_blob(tick, tick_trace_binary, object_id)
  ├─ 任务成功：
  │   ├─ UPDATE tick_manifest SET upload_status = "complete", object_store_etag = <etag>
  │   └─ RichTraceBlob 可被 replay 读取
  ├─ 任务失败（网络/超时）：
  │   ├─ 重试最多 3 次（指数退避 1s/2s/4s）
  │   ├─ 3 次均失败 → UPDATE tick_manifest SET upload_status = "failed"
  │   └─ blob 缺失不影响 world state（redb 已有完整状态）。Rich/debug replay 不可用；deterministic replay 不受影响（TickCommitRecord 10 字段完整）。
  └─ 任务超时（> 5s）：
      └─ 同失败处理

Phase D: WAL 截断
  └─ 截断已提交 tick 的 WAL 条目
```

### Async Upload Status Tracking

`tick_manifest` 表扩展 `upload_status` 字段，跟踪每个 tick 的 blob 上传生命周期：

| upload_status | 含义 | tick state 完整性 |
|:---|------|:---:|
| `pending` | blob 尚未写入对象存储 | ✅ redb state 完整，rich debug replay 不可用（deterministic replay OK） |
| `uploading` | blob 正在写入（worker 已接管） | ✅ redb state 完整 |
| `complete` | blob 已写入，etag 已回填 | ✅✅ 完全持久化，replay 可用 |
| `failed` | 3 次重试后仍失败 | ✅ redb state 完整，rich debug replay 不可用（deterministic replay OK） |

**Replay 检查**：replay verifier 查询 `tick_manifest.upload_status`：
- `complete` → 从对象存储拉取 blob，验证 hash → rich debug replay 可用
- `pending` / `uploading` → 降级为 `audit_gap`。Deterministic replay 不受影响（redb TickCommitRecord 10 字段完整）
- `failed` → 标记 `terminal_state = audit_gap`。Deterministic replay 仍可用（redb 数据完整）

**孤儿清理**：由于 redb 先于对象存储写入，不再产生孤儿 blob。若 blob 写入成功但 etag 回填失败（redb 更新超时），GC 通过对比对象存储中 blob 的 created_at 与 tick_manifest 中 upload_status 清理（`upload_status = 'failed'` 但对象存储中存在 blob → 保留 1h 后清理）。

### 关键不变量（更新）

- **redb commit 成功 = tick 持久化完成**：`tick_manifest` 行证明 tick 已发生，`content_hash` 证明 blob 完整性。**blob 写入不再是 tick commit 的前提条件。**
- **redb 只存小对象**：`tick_manifest` 仅含 `object_id + content_hash + blob_size + upload_status`——无 blob 本体。
- **redb commit 失败 = tick 未发生**：world state 回滚到 Pre-Apply 快照，玩家 WASM 不重跑，tick 编号不递增。
- **TickCommitRecord hash chain 仅在 redb commit 成功后追加**：prev_chain_hash 取自上一个已提交 tick，失败 tick 不产生链条目。

---

## 4. 持久化失败语义（D5/B async 模型）

redb commit 先于对象存储写入——以下为所有失败场景的处理：

| 场景 | redb 状态 | 对象存储状态 | 处理 |
|------|:------:|:----------:|------|
| 正常 | ✅ 已提交 | ✅ 已写入（异步完成） | 正常。`upload_status = complete` |
| redb commit 失败 | ❌ 回滚 | ❌ 未写入 | Tick 放弃，不递增 tick 编号 |
| redb commit 成功 + blob 写入成功 | ✅ 已提交 | ✅ 已写入 | 正常 |
| redb commit 成功 + blob 写入失败（3 次重试后） | ✅ 已提交 | ❌ 缺失 | `upload_status = failed`。world state 完整，rich debug replay 不可用（deterministic replay 不受影响，TickCommitRecord 10 字段完整） |
| redb commit 成功 + blob 写入超时（> 5s） | ✅ 已提交 | ❓ 未知 | 重试 3 次；仍失败 → `upload_status = failed` |
| Blob 写入成功 + etag 回填失败 | ✅ 已提交 | ✅ 已写入 | 对象存储中存在 blob 但 manifest 中无 etag。GC 扫描：1h 后若 `upload_status != 'complete'` 则清理孤儿 blob |

---

## 5. Replay 恢复

### 5.1 正常 Replay

```
1. 从 redb 读取目标 tick 的 tick_manifest
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
1. 从 redb 全量重建 world state（每个实体的最新状态）
2. 验证 redb state_checksum 是否匹配 keyframe 的存在性
3. 若无可用 keyframe 且无 redb 全量 → 该 tick 范围不可 replay
```

### 5.3 Replay Verifier 输入

Replay verifier 以 **redb commit 的 manifest/hash 为权威**，不重新扫描对象存储：

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

**孤儿清理**: 由于 redb commit 先于 blob 写入，正常流程不产生孤儿 blob。唯一孤儿场景：blob 写入成功但 etag 回填失败 → GC 扫描 `upload_status != 'complete'` 但对象存储中存在对应 blob → 保留 1h 后删除。**正常 `upload_status = 'complete'` 的 blob 按 TTL 分层清理**（见上表）。

### 6.2 Keyframe GC

- hot: 保留 7d（每 K tick 一个 keyframe）
- cold: 保留 30d（每 10K tick 一个 keyframe）
- 删除 keyframe 时同步删除对应的 snapshot delta chain

### 6.3 WAL GC

- 每次 redb commit 成功后截断已提交 tick 的 WAL
- WAL 仅保留未提交 tick 的条目

---

## 7. Commit Retry 对 Hash Chain 的影响（R16 B3 修复）

```
若 tick N 的 redb commit 因瞬时错误（网络/锁冲突）失败：
  1. world state 回滚到 Pre-Apply 快照
  2. 不递增 tick 编号
  3. 复用 canonical COLLECT buffer：
     - snapshot_hash（相同——COLLECT 快照不变）
     - commands（相同——相同的 WASM 输出序列）
     - wasm_status（相同——WASM 不重跑）
     - fuel_ledger（相同——不追加扣费）
  4. ❌ 不重新执行 WASM（避免非确定性输出与双倍扣费）
  5. 重新执行 EXECUTE phase + redb commit（使用相同 COLLECT 结果）
  6. 每次 retry attempt 产生新的 attempt_id（递增），但 collect_id 不变
  7. 最终 commit 成功后，commit_id 关联到成功的 attempt_id
```

这意味着：**同一 tick 编号的 TickCommitRecord 可能包含多个 attempt（attempt_id 递增），但 collect_id 始终不变**。Replay 只关心最终 committed 的 attempt——hash chain 验证以 redb 中实际存在的链为准。跨 attempt 的燃料消耗上限 = `1 × MAX_FUEL`（首次 COLLECT 时的扣费即为最终扣费，重试不追加）。

### 7.1 TickCommitRecord 标识字段

TickCommitRecord 中新增以下标识字段以支持 attempt/collect/commit 追踪：

| 字段 | 类型 | 语义 |
|------|------|------|
| `collect_id` | `Blake3(tick || snapshot_hash || commands_hash)` | COLLECT 阶段的唯一标识。同一 tick 的所有 retry 共享此值。首次 COLLECT 后确定，重试不变。 |
| `attempt_id` | `u32`（从 0 开始递增） | 本次 commit 尝试的序号。首次尝试 = 0，每次 retry +1。仅当 commit 成功或 tick 放弃时终止。 |
| `commit_id` | `Blake3(collect_id || attempt_id || state_checksum)` | 成功 commit 的唯一标识。仅在 redb commit 成功后生成。失败 attempt 无 commit_id。 |

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
| `unreplayable` | redb replay-critical core 或 keyframe/delta chain 缺失 | TickCommitRecord 10 字段缺失、hash chain 断裂且无可用 keyframe | ❌ 该 tick 范围核心 replay 不可恢复。RichTraceBlob 缺失不得触发此状态。 |
| `reconstructable` | Rich/debug blob 部分损坏但展示数据可恢复 | 次要 debug 字段损坏但 redb replay-critical core 完整 | 🔧 rich debug replay 部分恢复。损坏字段标记为 `reconstructed: true`。 |

**损坏检测流程**：

```
1. 从 redb 读取 TickCommitRecord replay-critical core
   ├─ 10 字段完整且 hash chain 连续 → deterministic replay 可用
   └─ 缺失或 hash chain 断裂 → terminal_state = unreplayable
2. 从对象存储获取 RichTraceBlob
3. 验证 Blake3(blob) == content_hash
   ├─ 匹配 → rich debug replay 可用；terminal_state = verified
   └─ 不匹配 OR blob 不存在：
       ├─ deterministic replay 继续使用 redb core + keyframe/delta chain
       ├─ 尝试部分解析 blob；次要 debug 字段可恢复 → terminal_state = reconstructable
       └─ 无可用 rich debug 数据 → terminal_state = audit_gap
```

**与 hash chain 的关系**：deterministic hash chain 只覆盖 redb TickCommitRecord replay-critical core：`chain[i] = Blake3(chain[i-1] || tick_commit_record_i)`。RichTraceBlob 不进入 deterministic hash chain；blob 缺失或损坏只让 rich debug replay 降级为 `audit_gap`，不会让核心 replay 进入 `unreplayable`。

---

## 8. Room-Partition redb WriteTransaction 策略

> **R23 D6/B 裁决**：redb room-partition transaction 纳入核心合同。单事务模式仅支持小规模验证（≤ 50 active players, ≤ 100 rooms）；500/1000-player 场景必须使用 room-level partition（Shadow Write）。

> **R32 B1**：模型从「per-room 独立 redb commit + 全局回滚」升级为「shadow write + atomic publish」。Per-room 写入目标为 `/staging/{tick}/{room}`——staging 行不是已提交状态。GlobalTickCommit 是唯一的 publish 点，将 staging 行原子提升为 `/committed/` 路径。所有下游读取仅走 `/committed/`。Staging 孤立行由 GC 清理（< 15s）。详见 `specs/core/tick-protocol.md` §3.5。

### 8.1 分区策略

```
单事务模式 (默认):
  适用: ≤ 50 active players, ≤ 100 rooms
  策略: 整个 world 单 redb WriteTransaction
  热区: tick_head + state_checksum + manifest (shared)
  
Room-Partition (500+ players):
  适用: > 50 active players 或 > 100 rooms
  策略: 每个 room 独立 redb WriteTransaction 写入 staging 区
  Key layout:
    /staging/{tick}/{room_id}/state   → 房间状态 delta（非 committed——仅 GlobalTickCommit 可见）
    /staging/{tick}/{room_id}/events  → 房间内事件
    /committed/head/{tick}            → global tick head（唯一 publish 点）
    /committed/manifest/{tick}        → room hashes + cross-room intent log
  Conflict range: per-room staging transaction 不跨 room 冲突
  Cross-room operations: 在 staging 写入**前**于 Bevy World 内裁决（R39 D6），再对 affected rooms 写 staging payload。全或无。
  GC: staging 孤立行每 10s 扫描清理（检查 /committed/head/{tick} 是否存在）
```

### 8.2 实现约束

| 约束 | 单事务模式 | Room-Partition (Shadow Write) |
|------|-----------|---------------|
| redb WriteTransaction 大小 | 单 tick < 10KB | 每 room staging < 2KB |
| 对象存储异步写入超时 | 5s；3 次重试 | 5s；3 次重试 |
| 对象存储读取 | 延迟 < 100ms p99 | 不变 |
| Keyframe 写入 | 异步，不阻塞 tick 循环 | 不变 |
| WAL 写入 | 同步 | per-room WAL |
| 内存 buffer | RichTraceBlob 10MB max | 不变 |
| Cross-room conflict | N/A | Staging 写入成功 + GlobalTickCommit 原子 publish → 全或无。不存在 per-room 独立推进或 best-effort 语义 |
| Staging GC | N/A | GC worker 每 10s 清理孤立 staging 行（最大残留 < 15s）

### 8.3 Synthetic Benchmark 要求

为证明容量声明，实现 Phase 需交付以下 benchmark gate：

| Benchmark | 目标 | 判定标准 |
|-----------|------|---------|
| Command validate loop | 100k commands/tick | p99 < 50ms |
| Command apply loop | 100k commands/tick | p99 < 100ms |
| Entity snapshot clone | 50k entities | p99 < 20ms |
| Entity snapshot restore | 50k entities | p99 < 30ms |
| Snapshot stitching | 1000 × 256KB snapshots | p99 < 100ms |
| redb single-tx commit | 500 active players | p99 < 200ms, conflict rate < 1% |
| redb room-partition commit | 1000 active players, 200 rooms | p99 < 500ms, per-room conflict rate < 1% |
| Pathfinding | 50×50 A* nodes, 100 concurrent ops | p99 < 10ms/node, fair-share guarantee |
| Rollback Bevy snapshot/restore | 500 entities, all components | p99 < 50ms, entity ID allocator verified |

Gate 失败 → 对应容量声明不可信，需降级规模或优化实现。

---

## 9. 与现有文档的关系

- `design/engine.md` §3.3 (TickInputEnvelope)、§3.4.2 (容量合同)、§3.4.7 (keyframe)：本文件为权威持久化合同。engine.md 描述架构意图，本文档定义实现合同。
- `specs/core/tick-protocol.md` §2.3 (快照)、§9.4 (TickCommitRecord 完整性)：本文件补充持久化层面。
- `specs/core/command-validation.md`：apply 阶段在本文件的 "Phase A" 中执行。

---

## 10. redb 文件可恢复性

redb 是嵌入式单文件 KV——没有内置副本或 WAL 恢复机制。本节定义防范和恢复策略。

### 10.1 风险模型

| 场景 | 后果 | 恢复 |
|------|------|:--:|
| 进程崩溃 | CoW B-tree：旧根或新根，无半页 | ✅ 自动 |
| OS crash（fsync 未落盘） | 丢最近 1 tick | hash chain 断裂检测 → 从 keyframe replay |
| 磁盘坏块 | `.redb` 部分损坏 | keyframe 独立存储 + replay |
| `.redb` 误删 | 全丢 | keyframe 独立存储 + replay |
| 静默损坏（bit rot） | hash chain 断裂可检测 | keyframe 恢复 |

### 10.2 Keyframe 独立存储

**Keyframe 不放在 redb 内**——否则 redb 损坏时 keyframe 一并丢失。

```
存储位置: $REDB_PATH.keyframes/{tick}.snap（独立文件）
格式: canonical_serialize(Bevy World) + state_checksum
写入时机: redb commit 成功后，仅当 tick % K == 0
写入方式: tmp 文件 + fsync + 原子 rename
保留: hot 7d (每 K tick) / cold 30d (每 10K tick)
```

### 10.3 灾难恢复

```
引擎启动:
  1. 打开 redb
     ├─ 成功 → recover_latest() → hash chain 验证
     │   ├─ 全部通过 → 正常启动
     │   └─ 断裂在 tick N → 从最近 keyframe 恢复到 N-1
     └─ 失败 → 从 keyframe 文件恢复
         └─ 加载最新 .snap → Bevy World 恢复 → 从该 tick 重新开始
```

### 10.4 备份

```
在线备份:
  redb 读事务期间 cp swarm.redb → CoW 保证一致性
  频率: 每 1000 tick 或每 keyframe 周期

Keyframe 自身即可作备份:
  cp -r $REDB_PATH.keyframes/ → 异地/异机存储
```

### 10.5 完整性校验

```
每 N tick 或启动时:
  recover_latest() → 验证 hash chain 从 tick 0 到 latest
  state_checksum 对比当前 Bevy World → 不匹配则 degraded + 告警
```

### 10.6 存储分层总览

```
┌────────────────────────────────────────────┐
│  权威源: redb (小对象, 永久)                 │
│  tick_head, manifest, hash_chain, audit     │
├────────────────────────────────────────────┤
│  恢复锚点: Keyframe Store (独立文件, 7-30d)  │
│  完整世界快照，redb 失效时可独立恢复          │
├────────────────────────────────────────────┤
│  审计: Object Store (大 blob, 7-180d)        │
│  RichTraceBlob, delta, WASM binaries        │
├────────────────────────────────────────────┤
│  运行时: WAL (内存, tick 内)                  │
└────────────────────────────────────────────┘

恢复优先级: Keyframe > redb > Object Store
```
