# Persistence Contract — redb / TickCommitRecord / RichTraceBlob / WAL / Blob Store 分层

> 详见 design/engine.md
>
> **修复**。本文档从 `design/engine.md` 与 `design/architecture.md` 派生 Swarm 引擎的持久化分层实现合同，消除 "redb WriteTransaction 内写一切" 与 "跨存储双写会炸" 之间的合同空白。
>
> **修复**。加入显式的 replay-critical subset 声明、Deploy 完整状态机、replay-critical 字段清单。

## 原则

1. **redb 只写小对象并永久保留 replay authority**：tick head、state checksum、small manifest、object pointers + content hashes，以及从 genesis 起所有 replay-critical commands、rejections、config/mod transitions、deploy decisions 与 hashes。
2. **大 BLOB 进对象存储**：RichTraceBlob（debug/rich trace）、snapshot delta、replay artifacts、WASM module binaries。
3. **单写事务原子性**：redb WriteTransaction commit 是唯一权威持久化点。对象存储写入失败不破坏 redb 状态完整性。
4. **Hash 链贯穿**：redb 记录的 content hash 证明对象存储中数据的完整性。
5. **Replay-critical 与 debug/rich 分离**：redb 事务原子提交 replay-critical subset（保证确定性回放与反作弊审计）；对象存储承载非关键的 rich trace/debug blob（可降级、可延迟、可丢失而不影响核心正确性）。

---

## 1. 存储层职责

| 存储层 | 存储内容 | 单条上限 | 保留期 |
|--------|---------|:------:|--------|
| **redb** | tick head、state checksum、small manifest、object pointers、content hashes、audit rows、commands/rejections、config+mod transitions、deploy decisions/hashes | < 1KB/row | 永久（从 genesis 起的 replay-critical authority） |
| **Blob Store** | RichTraceBlob、snapshot delta (full/diff)、replay artifacts、WASM binaries | 按类型：WASM 64MB、replay 1GB、snapshot 256MB | WASM 保留最近 10 版 + active slot/rollback pin/operator hold；历史 manifest 不构成 artifact 引用 |
| **WAL (Write-Ahead Log)** | 未提交的 apply 操作日志 | 滚动 | 提交后截断 |
| **Keyframe Store** | 每 K tick 的完整世界状态快照 | < 256MB | `keyframe_acceleration_retention_ticks`，primary + backup；仅加速恢复/审计 |

---

## 2. Replay-Critical Subset（权威声明）

replay-critical 字段在 redb WriteTransaction 中原子提交（replay-critical），哪些可以异步写入对象存储（debug/rich）。`design/engine.md` 与 `design/architecture.md` 是语义权威；本节是从设计派生的持久化实现合同，供其他 specs 引用 persistence 行为。

### 2.1 TickCommitRecord Fields（redb 原子提交 — 不可降级）

以下 10 个字段组成 TickCommitRecord，随每 tick redb **同一 WriteTransaction** 原子提交。缺失任一则 tick 不可 replay。

**三层分离声明：**
- **deterministic_replay**：仅需 redb 从 genesis 起永久保留的 replay-critical log：TickCommitRecord 的 10 个字段、所有 commands/rejections、config 与 mod transition、deploy activation decision、resolved config hash、manifest hash、module/artifact hashes。Blob Store 与 Keyframe Store 全量丢失时，replay verifier 必须仍能从 genesis 重放到任意 tick；keyframe/delta 只影响恢复速度。
- **rich_debug_replay**：RichTraceBlob（可选，存储于对象存储）。缺失 → `terminal_state = audit_gap`（审计记录缺失，可由 redb replay-critical log 重新推导状态，但 rich 细节不可恢复）。
- **WasmModuleArtifact**：对象存储中的 WASM 二进制/预编译 artifact。**operational-critical, non-state-authoritative**。Activation 前缺失/attestation 失败会使该 deploy FAILED，替换前模块继续运行；已 ACTIVE 的 artifact 后续丢失只暂停该 slot 执行并触发恢复，不追溯改变 deploy 结果。已提交 tick replay 不重新执行 WASM。

| # | 字段 | 存储位置 | 用途 |
|---|------|---------|------|
| 1 | `commands` | redb tick_commands | 所有 validated command 记录 |
| 2 | `rejections` | redb tick_commands | 所有 command rejection 记录 |
| 3 | `fuel` | redb tick_fuel | 每玩家 fuel 扣费明细 |
| 4 | `deploy_activation_decision` | redb tick_deploy | 本 tick 激活的 canonical deploy manifest（见 §2） |
| 5 | `canonical_codec_version` | redb tick_head | 序列化格式版本 |

> **canonical_codec_version CI 校验**：`canonical_codec_version` 为 `u32` 单调递增整数。CI 管线维护 Rust (`serde_swarm`) 和 Go (`swarm-codec-go`) 双实现的确定性 hash fixture——对固定 world state dump，两实现产出的 `Blake3(canonical_serialize(state))` 必须完全一致。fixture 随 codec version 更新纳入 `specs/reference/codec_fixtures/`。
| 6 | `snapshot_hash` | redb tick_head | COLLECT 阶段快照 hash |
| 7 | `commands_hash` | redb tick_head | commands + rejections 的 Blake3 hash |
| 8 | `state_checksum` | redb tick_head | world state 完整性验证 |
| 9 | `manifest_hash` | redb tick_manifest | composite replay digest：`Blake3(system_manifest_hash || world_action_manifest_hash || mods_lock_hash || limits_manifest_hash || host_fuel_schedule_version_hash)`；不存在 plugin schedule graph |
| 10 | `world_config_hash` | redb tick_manifest | world.toml 配置 hash，包含 `[mods.<plugin_id>]` typed config resolved hash |

### 2.2 Debug/Rich（对象存储异步写入 — 可降级）

**Blob Store 承载 redb small-row 之外的非权威大对象**：RichTraceBlob、snapshot delta/full artifact、可视化 replay artifact 与 WASM binary。redb 原子保存这些对象的 pointer、content hash 与 replay-critical decision；大对象写入失败不得回滚已提交 tick。RichTraceBlob、snapshot delta、keyframe 与可视化 replay artifact 缺失只降低恢复速度或审计丰富度，**绝不会**单独导致 `unreplayable`。WasmModuleArtifact 缺失是 operational gap：暂停受影响 player/drone 的后续执行或新激活，但不改变 redb 中已提交状态权威。

> **WasmModuleArtifact 非 state-authoritative（D6）**：Activation 前不可用 → 新 deploy FAILED；ACTIVE 后丢失 → slot PAUSED_RECOVERY，恢复同 hash artifact 后继续。两者都不影响 redb 中已提交 tick 的确定性 replay。

以下字段写入对象存储 blob，缺失不影响 deterministic replay：

| 字段 | 内容 | 降级行为 |
|------|------|---------|
| `rich_trace_blob` | RichTraceBlob 序列化（含 debug detail, rich events, per-system metrics） | blob 缺失 → replay 可用但 rich audit 降级; 产生 `terminal_state = audit_gap` |
| `snapshot_delta_blob` | snapshotted entity 的详细状态变更 | blob 缺失 → 从 redb genesis replay 或可用 keyframe 恢复，结果一致但更慢 |
| `replay_artifact_blob` | 可视化/调试用 annotation | blob 缺失 → 无影响 |

### 2.3 Deploy 完整状态机

`swarm_deploy` RPC 同步携带 canonical deploy body、metadata 与签名 `DeployPayload`；服务端在请求内完成 hash 计算、验证、编译准备与 redb manifest 原子提交。Object store 仅在 commit 后异步保存 WASM binary，用于审计/调试，不参与接受判定。

```
状态: VALIDATE → COMPILE_PREPARE → MANIFEST_COMMIT → ACTIVATION_PENDING → ACTIVE
                                                                      ↘ FAILED (rollback)

VALIDATE:
  ├─ 输入: canonical deploy body + metadata + player cert
  ├─ 验证: WASM 合法性、模块大小 ≤ cap、fuel 预算充足、玩家未达 drone cap
  ├─ 失败 → 拒绝部署 (ERR_DEPLOY_VALIDATION)
  └─ 成功 → 进入 COMPILE_PREPARE

COMPILE_PREPARE:
  ├─ 验证 signed DeployPayload.wasm_hash；manifest 将同一值记录为 wasm_module_hash
  ├─ Engine 通过 deploy NATS subject 将原始 WASM bytes 发送给 Sandbox worker
  ├─ Sandbox 使用 pinned Wasmtime 编译/缓存，计算 compiled_artifact_hash
  ├─ Sandbox 持久化 attested compiled artifact primary + backup
  ├─ Engine 验证 Sandbox HMAC、artifact_ref 与 replica etags；不接收任何外部 native artifact
  ├─ 记录 audit archive hint（commit 后可异步保存原始 WASM）
  └─ 进入 MANIFEST_COMMIT（不等 blob 上传完成）

MANIFEST_COMMIT:
  ├─ redb WriteTransaction 原子提交 deploy manifest:
  │   ├─ deploy_id, player_id, world_id, module_slot, wasm_module_hash, metadata_hash, deploy_payload_hash
  │   ├─ compiled_artifact_hash, certificate_id, version_counter, redb_version_counter, activation_tick
  │   ├─ code_update_cost_debit, cooldown_previous_tick, cooldown_next_tick, refund_credit_reset_amount
  │   ├─ audit_archive_status = "pending"
  │   ├─ archive_status = "pending"
  │   └─ activation_tick = current_tick + 1 (下一完整 tick 激活)
  ├─ COMMIT 成功 → 进入 ACTIVATION_PENDING
  └─ COMMIT 失败 → 回滚，deploy_id 无效

ACTIVATION_PENDING:
  ├─ 等待 activation_tick 到达
  ├─ 期间原始 WASM audit archive 可能在后台完成或失败
  └─ activation_tick 到达时:
      ├─ compiled_artifact_hash 与预编译 artifact 匹配 → ACTIVE
      │   └─ slot 在当前 activation_tick 的 COLLECT 前切换并立即用于本 tick
      ├─ compiled_artifact_hash 不匹配或预编译 artifact 不可用
      │   └─ → FAILED: drone 保持替换前模块(如有)或空模块
      │        redb 记录 deploy_failure_reason
      └─ audit_archive_status == "pending"
          └─ 不阻塞激活；记录 `wasm_blob_audit_gap_pending`

ACTIVE:
  └─ 模块已激活。drone 在 COLLECT 阶段使用此模块执行。

FAILED:
  ├─ redb 记录 deploy_failure_reason
  ├─ blob store 中 blob (如有) 由 GC 清理 (保留 1h 后删除)
  └─ 玩家可重新部署
```

**关键不变量（Deploy）**：
- **redb manifest 是 deploy 的唯一权威记录**：`redb_version_counter` 为 replay 提供严格全序。`wasm_module_hash` 与 `compiled_artifact_hash` 分离保存；blob upload 异步执行，不阻塞 tick 循环或激活判定。
- **同一 tick 内的 deploy 不影响当前 tick**：WASM 模块快照在 COLLECT 开始时确定。deploy 在 `activation_tick`（≥ current_tick + 1）生效。
- **Blob 缺失不影响 redb 状态完整性或模块激活**：`archive_status = "failed"` 只表示原始 WASM 审计 blob 缺失；只要 redb manifest 与预编译 artifact 完整，drone 仍可激活新模块。缺失 blob 产生 audit gap，不产生 deploy rollback。
- **Deploy mutation 的 replay class**：`deploy_mutation` — 状态变更通过 redb WriteTransaction 原子化，replay verifier 以 `redb_version_counter` 全序重放，不依赖对象存储 blob 可用性。
- **成本/冷却/credit 原子性**：新 deploy 的 cost debit、cooldown advance、refund-credit reset 与 manifest/counters 同事务；失败全部回滚。AlreadyDeployed 不产生这些 side effects。

---

## 3. Tick Commit 序列

> **裁决 (A)**：生产环境统一 per-room staging payload + GlobalTickCommit manifest-only publish。直接 `UPDATE entity/resource/controller/... rows` 仅用于 dev/test small profile（≤ 50 active players, ≤ 100 rooms），且必须标注不适用 production。

每个 tick 结束时执行以下持久化序列：

```
Stage A: Apply 完成
  ├─ 所有系统执行完毕，world state 确定
  ├─ state_checksum = Blake3(canonical_serialize(world))
  └─ RichTraceBlob 完整序列化到内存 buffer
  └─ 计算 content_hash = Blake3(compress(serialize(RichTraceBlob)))

Stage B: redb WriteTransaction 提交（原子 — 先于对象存储写入）
  ├─ BEGIN redb TRANSACTION
  ├─ INSERT tick_head (tick, state_checksum, timestamp)
  ├─ INSERT tick_manifest (tick, object_id, content_hash, blob_size, archive_status = "pending")
  │   └─ 注意：object_store_etag 此时为 NULL（blob 尚未写入）
  ├─ INSERT tick_hash_chain (tick, chain_hash = Blake3(prev_chain_hash || tick_head_hash))
  ├─ FOR each persistent state mutation (production: skip — use staging+manifest publish):
  │   └─ UPDATE entity/resource/controller/... rows  // dev/test small profile only; production uses Shadow Write (see §3.5)
  ├─ COMMIT
  └─ 若 COMMIT 成功 → tick 持久化完成（world state 已安全）
     若 COMMIT 失败 → 事务回滚，tick 放弃

Stage C: 对象存储异步写入（redb commit 成功后触发）
  ├─ 入队异步任务：write_blob(tick, tick_trace_binary, object_id)
  ├─ 任务成功：
  │   ├─ UPDATE tick_manifest SET archive_status = "complete", object_store_etag = <etag>
  │   └─ RichTraceBlob 可被 replay 读取
  ├─ 任务失败（网络/超时）：
  │   ├─ 重试最多 3 次（指数退避 1s/2s/4s）
  │   ├─ 3 次均失败 → UPDATE tick_manifest SET archive_status = "failed"
  │   └─ blob 缺失不影响 world state（redb 已有完整状态）。Rich/debug replay 不可用；deterministic replay 不受影响（TickCommitRecord 10 字段完整）。
  └─ 任务超时（> 5s）：
      └─ 同失败处理

Stage D: WAL 截断
  └─ 截断已提交 tick 的 WAL 条目
```

### Async Upload Status Tracking

`tick_manifest` 表扩展 `archive_status` 字段，跟踪每个 tick 的 blob 上传生命周期：

| archive_status | 含义 | tick state 完整性 |
|:---|------|:---:|
| `pending` | blob 尚未写入对象存储 | ✅ redb state 完整，rich debug replay 不可用（deterministic replay OK） |
| `uploading` | blob 正在写入（worker 已接管） | ✅ redb state 完整 |
| `complete` | blob 已写入，etag 已回填 | ✅✅ 完全持久化，replay 可用 |
| `failed` | 3 次重试后仍失败 | ✅ redb state 完整，rich debug replay 不可用（deterministic replay OK） |

**Replay 检查**：replay verifier 查询 `tick_manifest.archive_status`：
- `complete` → 从对象存储拉取 blob，验证 hash → rich debug replay 可用
- `pending` / `uploading` → 降级为 `audit_gap`。Deterministic replay 不受影响（redb TickCommitRecord 10 字段完整）
- `failed` → 标记 `terminal_state = audit_gap`。Deterministic replay 仍可用（redb 数据完整）

**孤儿清理**：由于 redb 先于对象存储写入，不再产生孤儿 blob。若 blob 写入成功但 etag 回填失败（redb 更新超时），GC 通过对比对象存储中 blob 的 created_at 与 tick_manifest 中 archive_status 清理（`archive_status = 'failed'` 但对象存储中存在 blob → 保留 1h 后清理）。

### 关键不变量（更新）

- **redb commit 成功 = tick 持久化完成**：`tick_manifest` 行证明 tick 已发生，`content_hash` 证明 blob 完整性。**blob 写入不再是 tick commit 的前提条件。**
- **redb 只存小对象**：`tick_manifest` 仅含 `object_id + content_hash + blob_size + archive_status`——无 blob 本体。
- **redb commit 失败 = tick 未发生**：world state 回滚到 Pre-Apply 快照，玩家 WASM 不重跑，tick 编号不递增。
- **TickCommitRecord hash chain 仅在 redb commit 成功后追加**：prev_chain_hash 取自上一个已提交 tick，失败 tick 不产生链条目。

---

## 4. 持久化失败语义（D5/B async 模型）

redb commit 先于对象存储写入——以下为所有失败场景的处理：

| 场景 | redb 状态 | 对象存储状态 | 处理 |
|------|:------:|:----------:|------|
| 正常 | ✅ 已提交 | ✅ 已写入（异步完成） | 正常。`archive_status = complete` |
| redb commit 失败 | ❌ 回滚 | ❌ 未写入 | Tick 放弃，不递增 tick 编号 |
| redb commit 成功 + blob 写入成功 | ✅ 已提交 | ✅ 已写入 | 正常 |
| redb commit 成功 + blob 写入失败（3 次重试后） | ✅ 已提交 | ❌ 缺失 | `archive_status = failed`。world state 完整，rich debug replay 不可用（deterministic replay 不受影响，TickCommitRecord 10 字段完整） |
| redb commit 成功 + blob 写入超时（> 5s） | ✅ 已提交 | ❓ 未知 | 重试 3 次；仍失败 → `archive_status = failed` |
| Blob 写入成功 + etag 回填失败 | ✅ 已提交 | ✅ 已写入 | 对象存储中存在 blob 但 manifest 中无 etag。GC 扫描：1h 后若 `archive_status != 'complete'` 则清理孤儿 blob |

---

## 5. Replay 恢复

### 5.1 正常 Replay

```
1. 从 redb 读取从 genesis 到目标 tick 的 replay-critical log（TickCommitRecord、commands/rejections、config/mod transitions、deploy decisions/hashes）
2. 验证 redb tick_hash_chain 与 state_checksum 连续
3. 可选：若 keyframe/delta 可用，先验证其 hash chain 并作为加速起点
4. 可选：从对象存储按 object_id 获取 RichTraceBlob/replay artifacts，用于 rich audit
5. 从 redb replay-critical log 重放到目标 tick；keyframe/delta 缺失只影响速度
```

### 5.2 Keyframe 不可用时

若目标 tick 最近的 keyframe 已被 GC 或 Blob/Keyframe Store 全量丢失：

```
1. 从 redb genesis replay-critical log 重放 world state
2. 验证每 tick state_checksum 与 tick_hash_chain
3. 若 redb replay-critical log 缺失或不一致 → 该 tick 范围不可 replay
```

### 5.3 Replay Verifier 输入

Replay verifier 以 **redb commit 的 manifest/hash 为权威**，不重新扫描对象存储：

- 输入: `(start_tick, end_tick, redb_manifest_list, object_store_blobs)`
- 验证: 每个 tick 的 `tick_manifest.content_hash` 匹配 blob
- 验证: `tick_hash_chain` 连续且匹配
- 输出: `ReplayResult { verified, mismatches, first_bad_tick }`

---

## 6. GC (垃圾回收)

### 6.1 Artifact Retention 配置

redb replay-critical history 在世界整个生命周期内永久保留，不提供可缩短的 retention 配置。`world.toml` 只配置非权威 rich artifacts 与 keyframe/delta 加速路径的保留期，使用 tick 数：

```toml
[retention]
rich_artifact_retention_ticks = 864_000            # 可独立设置
keyframe_acceleration_retention_ticks = 5_184_000   # 只影响恢复速度，不影响 replay authority
keyframe_backup_copies = 2                         # primary + backup
```

`rich_artifact_retention_ticks` 控制 RichTraceBlob、可视化 annotation 与调试 artifact。`keyframe_acceleration_retention_ticks` 控制可验证 keyframe/delta 加速窗口；该窗口完全丢失时必须回退到 redb genesis replay。

### 6.2 对象存储 GC

| 层级 | TTL | 清理策略 |
|------|:---:|---------|
| hot | configured | 按 `rich_artifact_retention_ticks` 的热/温/冷分层策略转移 |
| warm | configured | 按世界配置转移 |
| cold | configured | 超过 `rich_artifact_retention_ticks` 后删除 rich artifact |

**孤儿清理**: blob 写入成功但 etag 回填失败时，GC 对 `archive_status != 'complete'` 的孤儿保留 1h 后删除。WASM blobs 豁免通用 TTL，保留最近 10 版及 active slot/rollback pin/operator hold；永久历史 manifest 不阻止 GC。

### 6.3 Keyframe GC

- keyframe 与 delta chain 按 `keyframe_acceleration_retention_ticks` 保留；它们不是 replay authority
- 每个 keyframe 至少写入 2 份冗余：primary + backup，位于不同故障域
- 删除 keyframe 时同步删除其专属 snapshot delta chain；删除只降低恢复速度，不得删除 redb replay-critical history

### 6.4 WAL GC

- 每次 redb commit 成功后截断已提交 tick 的 WAL
- WAL 仅保留未提交 tick 的条目

---

## 7. Commit Retry 对 Hash Chain 的影响（修复）

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
| `collect_id` | `Blake3(length_delimited(tick, snapshot_hash, commands_hash))` | COLLECT 阶段唯一标识；retry 共享 |
| `attempt_id` | `u32`（从 0 开始递增） | 本次 commit 尝试的序号。首次尝试 = 0，每次 retry +1。仅当 commit 成功或 tick 放弃时终止。 |
| `commit_id` | `Blake3(length_delimited(collect_id, attempt_id, state_checksum))` | 仅成功 commit 生成 |

**TickCommitRecord 结构**（扩展）：

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
| `audit_gap` | Blob/Keyframe/Delta 缺失或部分损坏，但 redb replay-critical log 完整 | content_hash 不匹配 OR 对象存储 404，但 redb tick chain/state_checksum 链完整 | ⚠️ 审计记录或快速恢复路径缺失，游戏状态可从 redb genesis replay 重建 |
| `unreplayable` | redb replay-critical core 缺失 | TickCommitRecord 10 字段、commands/rejections、config/mod transition、deploy decision 或 required hash 缺失/不一致 | ❌ 该 tick 范围核心 replay 不可恢复。RichTraceBlob、snapshot delta、keyframe 或 WasmModuleArtifact 缺失不得触发此状态。 |
| `reconstructable` | Rich/debug blob 部分损坏但展示数据可恢复 | 次要 debug 字段损坏但 redb replay-critical core 完整 | 🔧 rich debug replay 部分恢复。损坏字段标记为 `reconstructed: true`。 |

**损坏检测流程**：

```
1. 从 redb 读取永久保留的 replay-critical core
   ├─ TickCommitRecord 10 字段、commands/rejections、config/mod transitions、deploy decisions/hashes 完整且 redb tick chain 连续 → deterministic replay 可用
   └─ redb replay-critical core 缺失或不一致 → terminal_state = unreplayable
2. 从对象存储获取 RichTraceBlob
3. 验证 Blake3(blob) == content_hash
   ├─ 匹配 → rich debug replay 可用；terminal_state = verified
   └─ 不匹配 OR blob 不存在：
       ├─ deterministic replay 继续使用 redb genesis log；keyframe/delta chain 仅作为可选加速路径
       ├─ 尝试部分解析 blob；次要 debug 字段可恢复 → terminal_state = reconstructable
       └─ 无可用 rich debug 数据 → terminal_state = audit_gap
```

**与 hash chain 的关系**：deterministic hash chain 只覆盖 redb TickCommitRecord replay-critical core：`chain[i] = Blake3(chain[i-1] || tick_commit_record_i)`。RichTraceBlob 不进入 deterministic hash chain；blob 缺失或损坏只让 rich debug replay 降级为 `audit_gap`，不会让核心 replay 进入 `unreplayable`。

---

## 8. Room-Partition redb WriteTransaction 策略

> redb room-partition transaction 纳入核心合同。单事务模式仅支持小规模验证（≤ 50 active players, ≤ 100 rooms）；接近 500-player shard cap 的场景必须使用 room-level partition（Shadow Write）。

> Per-room 写入目标为 `/staging/{tick}/{room}`——staging 行不是已提交状态。GlobalTickCommit 是唯一的 publish 点，将 staging 行原子提升为 `/committed/` 路径。所有下游读取仅走 `/committed/`。Staging 孤立行由 GC 清理（< 15s）。详见 `specs/core/tick-protocol.md` §3.5。

### 8.1 分区策略

```
单事务模式 (小规模自动选择):
  适用: ≤ 50 active players, ≤ 100 rooms
  策略: 整个 world 单 redb WriteTransaction
  热区: tick_head + state_checksum + manifest (shared)

Room-Partition (生产规模自动选择，最大 500 players):
  适用: > 50 active players 或 > 100 rooms
  策略: 每个 room 独立 redb WriteTransaction 写入 staging 区
  Key layout:
    /staging/{tick}/{room_id}/state   → 房间状态 delta（非 committed——仅 GlobalTickCommit 可见）
    /staging/{tick}/{room_id}/events  → 房间内事件
    /committed/head/{tick}            → global tick head（唯一 publish 点）
    /committed/manifest/{tick}        → room hashes + cross-room intent log
  Conflict range: per-room staging transaction 不跨 room 冲突
  Cross-room operations: 在 staging 写入**前**于 Bevy World 内裁决（，再对 affected rooms 写 staging payload。全或无。
  GC: staging 孤立行每 10s 扫描清理（检查 /committed/head/{tick} 是否存在）
```

### 8.2 实现约束

| 约束 | 单事务模式 | Room-Partition (Shadow Write) |
|------|-----------|---------------|
| redb WriteTransaction 大小 | 单 tick总计 < 10MB | 每 room staging < 2MB，GlobalTickCommit 后总计仍 < 10MB |
| 对象存储异步写入超时 | 5s；3 次重试 | 5s；3 次重试 |
| 对象存储读取 | 延迟 < 100ms p99 | 不变 |
| Keyframe 写入 | 异步，不阻塞 tick 循环 | 不变 |
| WAL 写入 | 同步 | per-room WAL |
| 内存 buffer | RichTraceBlob 10MB max | 不变 |
| Cross-room conflict | N/A | Staging 写入成功 + GlobalTickCommit 原子 publish → 全或无。不存在 per-room 独立推进或 best-effort 语义 |
| Staging GC | N/A | GC worker 每 10s 清理孤立 staging 行（最大残留 < 15s）

### 8.3 Synthetic Benchmark 要求

为证明容量声明，实现 Stage 需交付以下 benchmark gate：

| Benchmark | 目标 | 判定标准 |
|-----------|------|---------|
| Command validate loop | 100k commands/tick | p99 < 50ms |
| Command apply loop | 100k commands/tick | p99 < 100ms |
| Entity snapshot clone | 50k entities | p99 < 20ms |
| Entity snapshot restore | 50k entities | p99 < 30ms |
| Snapshot stitching | 500 × 256KB snapshots | p99 < 100ms |
| redb single-tx commit | 50 active players, 100 rooms | p99 < 50ms, conflict rate < 1% |
| redb room-partition atomic publish | 500 active players, 200 rooms | staging + final GlobalTickCommit p99 < 50ms, per-room conflict rate < 1% |
| Pathfinding | 50×50 A* nodes, 100 concurrent ops | p99 < 10ms/node, fair-share guarantee |
| Rollback Bevy snapshot/restore | 500 entities, all components | p99 < 50ms, entity ID allocator verified |

Gate 失败 → 对应容量声明不可信，需降级规模或优化实现。

---

## 9. 与现有文档的关系

- `design/engine.md` §3.3 (TickInputEnvelope)、§3.4.2 (容量合同)、§3.4.7 (keyframe) 与 `design/architecture.md`：设计文档是语义权威；本文档是派生的持久化实现合同。
- `specs/core/tick-protocol.md` §2.3 (快照)、§9.4 (TickCommitRecord 完整性)：本文件补充持久化层面。
- `specs/core/command-validation.md`：apply 阶段在本文件的 "Stage A" 中执行。

---

## 10. redb 文件可恢复性

redb 是嵌入式单文件 KV——没有内置副本或 WAL 恢复机制。本节定义防范和恢复策略。

### 10.1 风险模型

| 场景 | 后果 | 恢复 |
|------|------|:--:|
| 进程崩溃 | CoW B-tree：替换前根或新根，无半页 | ✅ 自动 |
| OS crash（fsync 未落盘） | 丢最近 1 tick | hash chain 断裂检测；从 redb backup 或可用 keyframe 加速恢复 |
| 磁盘坏块 | `.redb` 部分损坏 | redb backup 优先；keyframe 可作为灾难恢复锚点 |
| `.redb` 误删 | 全丢 | redb backup 优先；keyframe 仅恢复快照状态，不能替代 genesis replay log |
| 静默损坏（bit rot） | hash chain 断裂可检测 | redb backup 优先；keyframe 可作为恢复加速输入 |

### 10.2 Keyframe 独立存储

**Keyframe 不放在 redb 内**——否则 redb 损坏时 keyframe 一并丢失。

```
存储位置: $REDB_PATH.keyframes/{tick}.snap（独立文件）
格式: KeyframeHeader + canonical_serialize(Bevy World)
写入时机: redb commit 成功后，仅当 tick % K == 0
写入方式: tmp 文件 + fsync + 原子 rename；primary 与 backup 都完成后标记可用
保留: `keyframe_acceleration_retention_ticks`（只影响恢复速度）
```

`KeyframeHeader` 包含 magic、format_version、world_id、shard_id、tick、state_checksum、payload_len、payload_blake3 与 header_crc32c。读取 keyframe 时先验证 header CRC，再验证 payload Blake3 与 TickCommitRecord 的 state checksum。

### 10.3 灾难恢复

```
引擎启动:
  1. 打开 redb
     ├─ 成功 → recover_latest() → hash chain 验证
     │   ├─ 全部通过 → 正常启动
     │   └─ 断裂在 tick N → 从 redb backup 恢复；可用 keyframe 只作为加速输入
     └─ 失败 → 从 redb backup 恢复；若只剩 keyframe，则进入 degraded disaster-recovery 模式
         └─ 加载最新 .snap → Bevy World 恢复；等待 redb replay-critical log 修复后才可声明 deterministic replay 完整
```

### 10.4 备份

```
在线备份:
  redb 读事务期间 cp swarm.redb → CoW 保证一致性
  频率: 每 100 tick 或每 keyframe 周期，满足 RPO ≤ 100 ticks

Keyframe 自身即可作备份:
  primary: $REDB_PATH.keyframes/{tick}.snap
  backup:  $KEYFRAME_BACKUP_PATH/{world_id}/{shard_id}/{tick}.snap
  两份 keyframe 必须隔离存储并分别校验 header_crc32c + payload_blake3
```

设计恢复目标：RPO ≤ 100 ticks（5 min @ 3s/tick），RTO ≤ 300s。redb 永久保存从 genesis 起的 replay-critical core；历史全量世界状态不保存在 redb。独立 Keyframe Store 提供恢复加速与灾难恢复锚点，但不替代 redb replay authority。

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
│  加速/灾备: Keyframe Store (默认 5_184_000 ticks) │
│  完整世界快照，不能替代 redb replay log       │
├────────────────────────────────────────────┤
│  审计/运行 artifact: Blob Store              │
│  RichTraceBlob/delta 按 TTL；WASM 保留最近 10 版及 active/pinned/hold │
├────────────────────────────────────────────┤
│  运行时: WAL (内存, tick 内)                  │
└────────────────────────────────────────────┘

确定性 replay 权威: redb > Keyframe acceleration > Blob Store rich artifacts
```
