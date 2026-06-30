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

### 2.4 Hash Chain 验证

每个 `TickModificationSet` 包含 `prev_modification_hash`，形成从 keyframe 到当前 tick 的 hash chain。Hash chain 验证确保增量序列完整无篡改：

```
modification_set_self_hash = blake3(serialize_canonical(modification_set))
chain_head = keyframe_hash → mod_set[N+1].prev == mod_set[N].self_hash → ... → current
```

Replay verifier 加载 keyframe 后逐 tick 验证 hash chain，任一断裂 → replay 无效。

## 3. Modification-Set 确定性截断排序

增量模式下 256KB 截断的确定性排序键：

```
方案: (entity_priority_bucket, last_modified_tick DESC, entity_id)
  — 优先保留最近被修改的实体（高信息价值），替换前实体先截断
  — modification_set 自带变更信息，无需额外索引
```

关键不变量：同 tick、同世界状态、同玩家 → 同截断结果。

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

Keyframe 写入 `persistence-contract.md` 定义的 blob store；modification_set 写入 redb（atomic mutation）。

## 5. redb 增量提交整合

modification_set 通过 redb WriteTransaction 提交。每个 tick 的 modification_set 作为单个 redb key-value pair 写入 `snapshots/delta/{world_id}/{tick}`。keyframe 写入 `snapshots/keyframe/{world_id}/{tick}`。Hash chain 完整性由 modification_set 内的 `prev_modification_hash` 字段保证，不依赖存储引擎内部提交序号排序。

详见 `specs/core/persistence-contract.md`。
