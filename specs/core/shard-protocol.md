# 多世界分片协议 (Multi-World Shard Protocol)

> 详见 design/engine.md
> **R33 D12**: 原 Tier 3 内容，现已纳入核心设计。移除所有 "Tier/未来/候选/待定" 标签。

## 1. 目标

世界规模 >5,000 drone / 多节点部署。世界状态按房间分片，每个分片独立运行 ECS，跨分片实体通过协议交互。

## 2. 分片键设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `shard_key` | `room_id` | 以 Room 为分片键——每个 room 的所有实体归属于同一分片 |
| `shard_assignment` | **一致性哈希 (Jump Hash)** | Google Jump Hash：简单、无状态、最小重分配 |
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

跨分片 combat（如 RangedAttack 跨越分片边界）使用两阶段协议：

```
Phase 1 — Intent Broadcast:
  attacker_shard → target_shard: AttackIntent { attacker_id, target_id, damage, damage_type }

Phase 2 — Settlement & Ack:
  target_shard: 本地结算 damage → target HP 更新
  target_shard → attacker_shard: AttackResult { actual_damage, target_hp_after }

两阶段保证:
  - attacker 的 Energy/fuel 消耗在 Phase 1 已扣除（不可逆）
  - target 的 HP 变化在 Phase 2 结算
  - 若 target 在 Phase 1-2 之间被其他攻击击杀 → Phase 2 返回 target_dead
```

### 4.3 一致性与延迟

| 场景 | 一致性 | 延迟 | 确定性 |
|------|:--:|------|:--:|
| 单分片 combat | 强一致（ECS chain 内） | 0 | ✅ tick-by-tick |
| 跨分片 RangedAttack | 最终一致（两阶段） | 1 tick | ✅ 逻辑时钟 `(tick, shard_order, entity_id)` |
| 跨分片 Move | 强一致（atomically transfer entity） | 0 | ✅ tick-by-tick |

**确定性保证**：跨分片 tie-breaker 使用**逻辑时钟**，非物理时间戳。冲突排序键：`(tick, shard_priority, entity_id)`——全部由游戏状态派生，不依赖存储引擎内部提交序号或墙钟。同一初始状态 + 同一指令 + 同一分片拓扑 → 同一结果 → 可 replay。

## 5. redb 单实例部署边界

redb 作为单 Engine 实例的嵌入式权威存储使用，所有分片在同一进程内提交到同一个 `.redb` 文件。跨分片提交通过 Engine 调度层汇总后进入同一个 redb WriteTransaction；冲突解决使用逻辑时钟排序键 `(tick, shard_priority, entity_id)`，不依赖存储引擎内部提交序号。

## 6. 身份/CRL/Deploy Nonce 跨分片链

Auth Service 作为全局单例（非分片），所有分片通过 RPC 查询证书状态。CRL 缓存每分片本地维护，60s TTL + Auth Service push 失效。Deploy nonce 去重使用全局 nonce registry（单点 redb key）——所有分片写入同一 `nonce/{nonce_id}` key，利用 redb WriteTransaction 原子性。

## 7. 跨分片 Replay/Anti-Cheat 审计链

多个分片的 TickTrace 通过逻辑时钟排序 `(tick, shard_priority, entity_id)` 合并为全局确定性审计链。每个分片的 `TickModificationSet` 进入该分片本地 hash chain；全局审计链以 tick 为锚点跨分片归并。

详见 `specs/core/tick-protocol.md`、`specs/core/incremental-snapshot.md`、`specs/core/persistence-contract.md`。", "path": "/data/swarm/docs/specs/core/shard-protocol.md"}
