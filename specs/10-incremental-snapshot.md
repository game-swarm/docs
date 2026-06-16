# Tier 2 增量快照协议

> 详见 DESIGN §3.2 快照扩展路线（三级规模模型）
> 
> **状态**: Phase 1+ entry gate — Tier 2 实现前必须冻结本文档。

## 1. 目标

Tier 2 支持 ≤5,000 drone / ≤500 房间 / 单节点部署。Tier 1 的 Bevy World 深拷贝全量快照不再适用——须升级为增量快照。

## 2. Modification-Set 增量格式

### 2.1 Modification-Set 结构

```rust
struct TickModificationSet {
    tick: u64,
    base_snapshot_hash: Blake3Hash,        // 上一 tick 快照的 hash
    added_entities: Vec<EntitySnapshot>,    // 新创建的实体（完整序列化）
    removed_entities: Vec<EntityId>,        // 被销毁的实体 ID
    modified_components: Vec<ComponentDelta>, // 变更的 component
    resource_changes: Vec<ResourceDelta>,   // 全局 Resource 变更
}
```

### 2.2 ComponentDelta

每个修改的 component 记录 (entity_id, component_type_id, new_value)。不记录旧值——`base_snapshot_hash` 已锚定上一 tick 状态。

### 2.3 增量重建

```
tick N snapshot = apply(tick N-1 snapshot, tick N modification_set)
apply = remove(removed_entities) ∪ add(added_entities) ∪ update(modified_components) ∪ apply(resource_changes)
```

## 3. Copy-on-Write 实体分页

| 参数 | 值 | 说明 |
|------|-----|------|
| `cow_page_size` | 256 entity/page | TBD — 需基准测试确定最优值 |
| `max_dirty_pages` | 64 | 每 tick 最多复制的页面数 |
| `page_allocation_policy` | lazy-alloc | TBD — 首次写入时分配 |

CoW 策略在 modification-set tracking 与 CoW 分页之间选择。当前倾向 modification-set（粒度更细），CoW 作为备选。

## 4. 增量截断确定性排序

TBD — 增量模式下 256KB 截断的确定性排序键需重新定义：

- Tier 1 使用 `(distance_to_drone, entity_id)` 排序
- Tier 2 的 modification-set 中 entity 可能无 drone 位置参考 → 需新的确定性排序键
- 关键不变量：同 tick、同世界状态、同玩家 → 同截断结果

## 5. Tier 1 → Tier 2 迁移路径

```
Tier 1 (全量深拷贝):
  snapshot = World::deep_clone()

Tier 2 (增量):
  if first_tick OR keyframe_tick:
      snapshot = World::deep_clone()      // 定期全量 keyframe
  else:
      snapshot = apply(prev_snapshot, modification_set)
```

Keyframe 间隔 = TBD（建议每 100 tick 或每 1000 entity 变更）。

## 6. 待定项

- CoW 页大小 vs modification-set 粒度最终选择
- 增量 truncation 确定性排序键
- Keyframe 间隔与存储成本权衡
- 与 FDB 增量提交的整合策略
