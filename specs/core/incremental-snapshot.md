# 增量快照协议 (Incremental Snapshot Protocol)

> 详见 design/engine.md
增量快照协议纳入核心设计。

## 1. 目标

世界规模 ≤5,000 drone / ≤500 房间时，全量 Bevy World 深拷贝快照不再适用。增量快照以 modification-set 替代全量拷贝，减少内存/CPU 开销。

## 2. Modification-Set 增量格式

### 2.1 Modification-Set 结构

```rust
struct TickModificationSet {
    tick: u64,
    prev_modification_hash: Blake3Hash,  // 上一 modification_set 的 hash（形成 hash chain）
    base_snapshot_hash: Blake3Hash,       // 上一 tick 快照的 hash
    added_entities: Vec<EntitySnapshot>,  // 新创建的实体（完整序列化）
    removed_entities: Vec<EntityId>,      // 被销毁的实体 ID
    modified_components: Vec<ComponentDelta>, // 变更的 component
    resource_changes: Vec<ResourceDelta>,  // 全局 Resource 变更
}
```

### 2.2 ComponentDelta

每个修改的 component 记录 (entity_id, component_type_id, new_value)。不记录替换前值——`base_snapshot_hash` 已锚定上一 tick 状态。

### 2.3 增量重建

```
tick N snapshot = apply(tick N-1 snapshot, tick N modification_set)
apply = remove(removed_entities) ∪ add(added_entities) ∪ update(modified_components) ∪ apply(resource_changes)
```

### 2.4 Hash Chain 验证（加速/审计，不是 replay authority）

每个 `TickModificationSet` 包含 `prev_modification_hash`，形成从 keyframe 到当前 tick 的 hash chain。Hash chain 验证确保增量序列完整无篡改，用于快速恢复和审计加速；确定性 replay 的权威输入仍是 `persistence-contract.md` 中 redb 从 genesis 永久保留的 commands/rejections/config+mod transitions/deploy decisions/hashes。

```
modification_set_self_hash = blake3(serialize_canonical(modification_set))
chain_head = keyframe_hash → mod_set[N+1].prev == mod_set[N].self_hash → ... → current
```

Replay verifier 可加载 keyframe 后逐 tick 验证 hash chain，任一断裂 → 该 keyframe/delta chain 不可作为加速路径。它不得使世界变成 `unreplayable`；verifier 必须回退到 redb genesis replay。Blob Store 与 Keyframe Store 全量丢失时，确定性 replay 仍必须成功，只是恢复时间变长。

## 3. Modification-Set 与感知快照截断

增量存储不定义独立的 256KB 截断顺序。面向 WASM/MCP 的感知快照始终使用 `snapshot-contract.md` 的 canonical 规则：messages 先截断，entity/resource/event 以 canonical primary_drone 的 distance bucket 排序，同 bucket 按 cross-category `(anchor_entity_id, kind_tag, local_key)` stable item key 排序，最后从最远 bucket shared queue 末尾移除。Modification-set 的 `last_modified_tick` 只用于 keyframe/delta storage compaction，不影响玩家可见 snapshot。

## 4. 快照策略：全量 Keyframe + 增量 Delta

```
if first_tick OR keyframe_tick:
    snapshot = World::deep_clone()       // 定期全量 keyframe
else:
    snapshot = apply(prev_snapshot, modification_set)
```

| 参数 | 值 | 说明 |
|------|-----|------|
| `keyframe_interval` | **100 tick**（约 5 分钟 @ 3s/tick） | 权衡存储成本（全量 keyframe ≈16MB）与重建延迟 |
| `cow_page_size` | 256 entity/page | modification-set 为主策略，CoW 作为备选 |

Keyframe 写入 `persistence-contract.md` 定义的 blob store；modification_set 可写入 redb 或 blob-backed delta index 作为加速/审计 artifact。二者都不是 state authority；redb 中的 replay-critical log 才是确定性 replay 的最低依赖。

## 5. redb 增量提交整合

modification_set pointer/hash 通过 redb WriteTransaction 提交。每个 tick 的 modification_set 可作为 redb small row 或 blob object 写入 `snapshots/delta/{world_id}/{tick}`；keyframe 写入 `snapshots/keyframe/{world_id}/{tick}`。Hash chain 完整性由 modification_set 内的 `prev_modification_hash` 字段保证，不依赖存储引擎内部提交序号排序。delta/keyframe 缺失只禁用该加速路径；replay 从 redb genesis log 继续提供权威状态。

详见 `specs/core/persistence-contract.md`。
