# 多世界分片协议 (Multi-World Shard Protocol)

> 设计背景见 [引擎架构](../../design/engine.md)。
多世界分片协议纳入核心设计。

## 1. 目标

世界规模 >5,000 drone / 多节点部署。世界状态按房间分片，每个分片独立运行 ECS，跨分片实体通过协议交互。

## 2. 分片键设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `shard_key` | `room_id` | 以 Room 为分片键——每个 room 的所有实体归属于同一分片 |
| `shard_assignment` | **静态坐标分片** | world.toml 声明坐标范围，`shard_id = f(room_x, room_y)` O(1) 查找 |
| `max_rooms_per_shard` | 50 | 与核心设计的限制一致 |
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

分片内 combat 与核心设计一致——ECS chain 顺序执行，无分布式协调。

### 4.2 跨分片 Combat

跨分片 combat（如 RangedAttack 跨越分片边界）使用 tick-barrier 协议：

```
Barrier N — Intent Broadcast:
  attacker_shard → target_shard: AttackIntent { attacker_id, target_id, damage, damage_type }

Barrier N — Global Anchor:
  all shards publish local intent hash
  global_anchor_hash = blake3(sorted(shard_id, local_intent_hash))

Barrier N+1 — Settlement & Ack:
  target_shard: 本地结算 damage → target HP 更新
  target_shard → attacker_shard: AttackResult { actual_damage, target_hp_after }

两阶段保证:
  - attacker 的 Energy/fuel 消耗在 Barrier N 已扣除（不可逆）
  - target 的 HP 变化在 Barrier N+1 结算
  - 若 target 在 barrier 间被其他攻击击杀 → settlement 返回 target_dead
```

### 4.3 一致性与延迟

| 场景 | 一致性 | 延迟 | 确定性 |
|------|:--:|------|:--:|
| 单分片 combat | 强一致（ECS chain 内） | 0 | ✅ tick-by-tick |
| 跨分片 RangedAttack | barrier 一致 | 1 tick | ✅ `(tick, global_anchor_hash, shard_order, entity_id)` |
| 跨分片 Move | barrier 一致（transfer at boundary） | 1 tick | ✅ `(tick, global_anchor_hash, shard_order, entity_id)` |

**确定性保证**：跨分片 tie-breaker 使用**逻辑时钟 + 全局 anchor hash**，非物理时间戳。冲突排序键：`(tick, global_anchor_hash, shard_priority, entity_id)`——全部由游戏状态派生，不依赖存储引擎内部提交序号或墙钟。同一初始状态 + 同一指令 + 同一分片拓扑 → 同一结果 → 可 replay。

## 5. 每 shard 独立 Engine + redb

每个 shard 独立运行一个 Engine 进程、一个 redb 文件和一个故障域。redb 只保存本 shard 的权威状态、TickCommitRecord、keyframe/delta chain 与 shard-local hash chain。跨分片交互通过 tick-barrier 消息与全局 anchor hash 归并；不存在跨 shard 的同一 redb WriteTransaction。

## 6. 身份/CRL/Deploy Nonce 跨分片链

Auth Service 作为全局服务（非分片），所有分片通过 RPC 查询证书状态。CRL 缓存每分片本地维护，60s TTL + Auth Service push 失效。Deploy nonce 去重使用 Auth Service 或 Gateway 管理的全局 nonce registry；shard-local redb 不承担跨 shard nonce 原子提交。

## 7. 跨分片 Replay/Anti-Cheat 审计链

多个分片的 TickTrace 通过逻辑时钟排序 `(tick, shard_priority, entity_id)` 合并为全局确定性审计链。每个分片的 `TickModificationSet` 进入该分片本地 hash chain；全局审计链以 tick 为锚点跨分片归并。

相关协议见 [Tick 协议](tick-protocol.md)、[增量快照](incremental-snapshot.md)和[持久化合同](persistence-contract.md)。
