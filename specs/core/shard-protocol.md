# 多世界分片协议 (Multi-World Shard Protocol)

> 设计背景见 [引擎架构](../../design/engine.md)。
多世界分片协议纳入核心设计。

## 1. 目标

世界规模 >5,000 drone / 多节点部署。世界状态按房间分片，每个分片独立运行 ECS。跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界的房间出口），不在热路径。

## 2. 分片键设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `shard_key` | `room_id` | 以 Room 为分片键——每个 room 的所有实体归属于同一分片 |
| `shard_assignment` | **静态坐标分片** | world.toml 声明坐标范围，`shard_id = f(room_x, room_y)` O(1) 查找 |
| `max_rooms_per_shard` | 50 | 与核心设计的限制一致 |
| `cross_shard_rooms` | 仅相邻房间 | 跨分片交互仅发生在房间边界 |

## 3. 跨分片边界

跨分片边界仅覆盖玩家迁移：drone 穿过 shard 边界的房间出口后，从一个静态坐标 shard 迁移到相邻 shard。跨 shard RangedAttack、跨 shard 视野拼接、分布式 combat barrier、global anchor hash 与跨 shard 同 tick 结算协议不属于本规范定义范围。

分片内 combat 与核心设计一致——ECS chain 顺序执行，无分布式协调。

## 4. 每 shard 独立 Engine + redb

每个 shard 独立运行一个 Engine 进程、一个 redb 文件和一个故障域。redb 只保存本 shard 的权威状态、TickCommitRecord、keyframe/delta chain 与 shard-local hash chain。不存在跨 shard 的同一 redb WriteTransaction。

## 5. 身份/CRL/Deploy Nonce 跨分片链

Auth Service 作为全局服务（非分片），所有分片通过 RPC 查询证书状态。CRL 缓存每分片本地维护，60s TTL + Auth Service push 失效。Deploy nonce 去重使用 Auth Service 或 Gateway 管理的全局 nonce registry；shard-local redb 不承担跨 shard nonce 原子提交。

## 6. Shard-local Replay/Anti-Cheat 审计链

每个分片的 `TickTrace` 与 `TickModificationSet` 只进入该分片本地 hash chain。当前 design 未定义跨 shard 全局 anchor 或全局审计链归并，本 spec 不额外引入该协议。

相关协议见 [Tick 协议](tick-protocol.md)、[增量快照](incremental-snapshot.md)和[持久化合同](persistence-contract.md)。
