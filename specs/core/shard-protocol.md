# 多世界分片协议 (Multi-World Shard Protocol)

> 设计背景见 [引擎架构](../../design/engine.md)。
多世界分片协议纳入核心设计。

## 1. 目标

世界状态按静态坐标 shard 分片，每个 shard 固定覆盖 50x50 rooms（2500 rooms），最多 500 active players，并独立运行 ECS。跨 shard 通信仅在玩家迁移时发生（drone 穿过 shard 边界的房间出口），不在热路径。

玩家迁移是 entire-player bundle：所有 owned drones、player/global storage、module slots、deploy counters 与私有 player state 同批迁移。claimed rooms 与固定 structures 不迁移；玩家仍拥有任一 source-shard 固定资产时，边界 Move 返回 `SourceNotAllowed` + `debug_detail=MigrationAssetsRemain`。目标入口按 crossing drone anchor + StableEntityId 升序 formation 确定；容量不足在 ACK 前取消。

## 2. 分片键设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `shard_key` | `(floor(room_x / 50), floor(room_y / 50))` | 固定坐标 shard key；每个 room 的所有实体归属于同一分片 |
| `shard_assignment` | **静态坐标分片** | `world.toml [sharding].deployed_shards` 枚举 `{shard_id, origin_room}`；`routing=fixed-grid-v1` O(1) 校验 |
| `rooms_per_shard` | 50x50 = 2500 rooms | 与核心设计的静态 shard 尺寸一致 |
| `max_active_players_per_shard` | 500 | 目标 shard Prepare/Activation 都必须检查 |
| `cross_shard_rooms` | 仅相邻房间出口迁移 | 跨分片交互仅发生在玩家迁移协议中 |

## 3. 跨分片边界

跨分片边界仅覆盖玩家迁移：drone 穿过 shard 边界的房间出口后，从一个静态坐标 shard 迁移到相邻 shard。visibility snapshot 在 shard 边界硬裁剪；玩家代码不能读取相邻 shard 的房间、实体或敌对状态。跨 shard combat、heal、ranged attack、area effect、claim、资源交互、跨 shard 视野拼接、分布式 combat barrier、global anchor hash 与跨 shard 同 tick 结算协议均不存在。

分片内 combat 与核心设计一致——ECS chain 顺序执行，无分布式协调。

## 4. 每 shard 独立 Engine + redb

每个 shard 独立运行一个 Engine 进程、一个 redb 文件和一个故障域。redb 只保存本 shard 的权威状态、TickCommitRecord、keyframe/delta chain 与 shard-local hash chain。不存在跨 shard 的同一 redb WriteTransaction。

## 5. 身份/CRL 与 Deploy Anti-Replay

Auth Service 作为全局服务（非分片），所有分片通过 RPC 查询证书状态。CRL 缓存每分片本地维护，60s TTL + Auth Service push 失效。Deploy 防重放不使用全局 nonce registry：每个 shard 在本地 redb deploy manifest 中按 `(player_id, world_id, module_slot)` 原子校验并递增 `version_counter`。玩家迁移时，当前 world/slot counters 随迁移包进入目标 shard，并在 Destination Activation 前持久化。

## 6. Shard-local Replay/Anti-Cheat 审计链

每个分片的 `TickTrace` 与 `TickModificationSet` 只进入该分片本地 hash chain。当前 design 未定义跨 shard 全局 anchor 或全局审计链归并，本 spec 不额外引入该协议。

## 7. 跨 shard 玩家迁移协议

迁移使用 redb durable outbox，不使用全局事务或全局链。源 shard 和目标 shard 都记录同一个 `migration_id`，形成双边 shard-local audit trail。

所有迁移 phase 使用 NATS subject `swarm.migration.v1.<target_shard>`，要求 mTLS、per-shard publish/subscribe ACL 和 `SWARM_MIGRATION_AUTH_SECRET` HMAC。Canonical envelope 为 `version|migration_id|source_shard|target_shard|phase|sequence|timestamp|payload_hash`。接收方验证相邻 topology、source shard 对 player 的权威归属、target identity、phase/sequence、60 秒 timestamp window、payload hash 与 HMAC，并在 redb 对 `(migration_id, phase, sequence)` 原子去重。任何解析、ACL/HMAC、重放 store 或 payload 失败都 fail closed，不能推进 state machine。

1. **Stage**：源 shard 在 tick N 写入 migration outbox 记录，冻结玩家在源 shard 的可交互状态，并把迁移包内容 hash 固定。
2. **Prepare**：目标 shard 收到 Stage 后预留目标入口和 player slot。Prepare 最早在 N+1 生效；超过 10 ticks 未完成则取消，源 shard 解冻玩家。
3. **ACK**：目标 shard durable 写入 ACK 后，源 shard 进入不可回退段。ACK 后所有重试必须持续到 completion，不能因为网络超时回滚。
4. **Source Tombstone / Commit**：源 shard tombstone 原玩家状态并提交 tick；该玩家从源 shard visibility、combat 和 command validation 中消失。
5. **Destination Activation**：目标 shard 在 Commit 后激活玩家状态。激活 tick 不早于 N+1，且目标 shard 的 player slot 计入 500 active players cap。

Prepare 超时前，源 shard 按空命令处理迁移中的玩家；Prepare 取消后恢复正常。ACK 后如果目标 activation 暂时不可达，源 shard 保持 tombstone，目标 shard retry activation 直到完成。同一个 `migration_id` 必须出现在源/目标两侧本地审计记录中；不存在跨 shard 全局审计链。

相关协议见 [Tick 协议](tick-protocol.md)、[增量快照](incremental-snapshot.md)和[持久化合同](persistence-contract.md)。
