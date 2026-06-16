# Tier 2 增量快照协议

> 详见 design/engine.md（快照扩展路线）
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
| `cow_page_size` | 256 entity/page | 候选值，需基准测试确认——目标：page 内平均 50% entity 在单 tick 变更 |
| `max_dirty_pages` | 64 | 每 tick 最多复制的页面数 |
| `page_allocation_policy` | lazy-alloc | 首次写入时分配页面——与 Bevy change detection 集成 |

CoW 策略在 modification-set tracking 与 CoW 分页之间选择。当前倾向 modification-set（粒度更细），CoW 作为备选。

## 4. 增量截断确定性排序

增量模式下 256KB 截断的确定性排序键：

```
候选方案:
  方案 A: (entity_priority_bucket, last_modified_tick DESC, entity_id)
    — 优先保留最近被修改的实体（高信息价值），旧实体先截断
  方案 B: (entity_priority_bucket, distance_to_nearest_player_drone, entity_id)
    — 与 Tier 1 语义一致，但需维护 drone→entity 距离索引

推荐方案 A——增量模式下 modification_set 自带变更信息，无需额外索引。
关键不变量：同 tick、同世界状态、同玩家 → 同截断结果。
```

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

Keyframe 间隔：候选值 100 tick（约 5 分钟 @ 3s/tick），或每 1000 entity 变更。最终值需在 Tier 2 实现前通过基准测试确定——权衡存储成本（全量 keyframe 大小）与重建延迟（keyframe→当前 需 replay 的最大 tick 数）。

## 6. 待定项

以下项在正文中已提供候选方案，最终值需 Tier 2 实现前通过基准测试确定：

- **CoW 页大小 vs modification-set 粒度**：当前倾向 modification-set（粒度更细），CoW 作为备选——需基准测试对比两者在 5000 entity 下的内存/CPU 开销
- **Keyframe 间隔**：候选值 100 tick 或 1000 entity 变更——需权衡存储成本 (每 keyframe ≈16MB) 与重建延迟
- **FDB 增量提交整合**：modification-set 如何映射到 FDB 的 atomic mutation——需与 FDB 事务模型对齐
