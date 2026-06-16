# Tier 3 分片协议

> 详见 DESIGN §3.2 快照扩展路线（三级规模模型）
>
> **状态**: Phase 1+ entry gate — Tier 3 实现前必须冻结本文档。

## 1. 目标

Tier 3 支持 >5,000 drone / 多节点部署。世界状态按房间分片，每个分片独立运行 ECS，跨分片实体通过协议交互。

## 2. 分片键设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `shard_key` | `room_id` | 以 Room 为分片键——每个 room 的所有实体归属于同一分片 |
| `shard_assignment` | 一致性哈希 | TBD — 具体哈希算法待定 |
| `max_rooms_per_shard` | 50 | 与 Tier 1 的限制一致 |
| `cross_shard_rooms` | 仅相邻房间 | 跨分片交互仅发生在房间边界 |

## 3. 跨分片实体引用

```
格式: shard_id:room_id:entity_id

示例: shard_3:W5N2:1001  — shard 3 上房间 W5N2 的 entity 1001
```

跨分片引用仅在以下场景出现：
- drone 移动到相邻房间（跨分片边界）
- RangedAttack 跨越房间边界
- 视野跨越分片边界（drone 可见相邻房间实体）

## 4. 分布式 Combat 结算

### 4.1 单分片内结算

分片内 combat 与 Tier 1/2 一致——ECS chain 顺序执行，无分布式协调。

### 4.2 跨分片 Combat

跨分片 combat（如 RangedAttack 跨越分片边界）需两阶段协议：

```
Phase 1 — 意图广播:
  attacker_shard → target_shard: AttackIntent { attacker_id, target_id, damage, damage_type }
  
Phase 2 — 结算与确认:
  target_shard: 本地结算 damage → target HP 更新
  target_shard → attacker_shard: AttackResult { actual_damage, target_hp_after }
  
两阶段保证:
  - attacker 的 Energy/fuel 消耗在 Phase 1 已扣除（不可逆）
  - target 的 HP 变化在 Phase 2 结算
  - 若 target 在 Phase 1-2 之间被其他攻击击杀 → Phase 2 返回 target_dead
```

### 4.3 一致性与延迟

| 场景 | 一致性 | 延迟 |
|------|:--:|------|
| 单分片 combat | 强一致（ECS chain 内） | 0 |
| 跨分片 RangedAttack | 最终一致（两阶段） | 1 tick |
| 跨分片 Move | 强一致（atomically transfer entity） | 0（drone 转移在本 tick 内完成） |

## 5. FDB 多区域部署

TBD — FDB 集群在多个物理区域部署时的延迟、冲突解决和分片亲和性策略。

## 6. 身份/CRL/Deploy Nonce 跨分片链

TBD — 证书吊销列表、deploy nonce 去重、epoch bump 等全局状态的跨分片同步。

## 7. 待定项

- 一致性哈希具体算法
- 跨分片 combat 两阶段协议的确定性保证
- FDB 多区域部署拓扑
- 分片动态重平衡策略（新增/移除节点）
- 跨分片 replay/anti-cheat 审计链
