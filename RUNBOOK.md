# Swarm 运维手册 (Runbook)

## 密钥轮换

### world_seed
```bash
# 生成新种子
python3 -c "import secrets; print(secrets.token_hex(32))"
# 更新 world.toml 中的 world_seed
```

### JWT 签名密钥
```bash
openssl genpkey -algorithm Ed25519 -out jwt_private.pem
openssl pkey -in jwt_private.pem -pubout -out jwt_public.pem
```

### 证书
Ed25519 证书 24h 自动过期。手动吊销：
```bash
swarm cert revoke --player-id <ID>
```

### FDB credential
```bash
# 轮换 FDB 集群密钥
fdbcli --exec "configure new ssd"
```

## 备份恢复

### 备份
```bash
# FDB 备份
fdbbackup start -d file:///backup/fdb -t default
# 引擎状态快照
swarm snapshot create --output /backup/snapshot_$(date +%Y%m%d).json
```

### 恢复
```bash
# FDB 恢复
fdbbackup restore file:///backup/fdb -t default
# 引擎状态恢复
swarm snapshot restore --input /backup/snapshot_20260614.json
```

## 降级模式

### 无 FDB（降级运行）
引擎自动检测 FDB 不可达，进入降级模式：
- `/healthz` 返回 `503 degraded`
- 状态仅存于内存，不持久化
- tick 继续运行，无中断

### 无 NATS（无广播）
- delta 推送暂停
- `/healthz` 返回 `503 degraded`
- 客户端检测 gap 后通过 REST fetch 同步

### 完全降级（仅引擎）
`docker compose up engine` 仅启动引擎，无 FDB/NATS。

## 监控指标

| 指标 | 告警阈值 |
|------|---------|
| tick_duration_p99 | > 3s |
| refund_abuse_rate | > 20% |
| command_rejection_rate | > 30% |
| consecutive_tick_failures | > 3 |
| FDB 连接丢失 | 即时告警 |

## 灾难恢复

1. 停止引擎
2. 恢复 FDB 备份
3. 恢复引擎快照
4. 验证 state_checksum
5. 启动引擎
6. 监控 100 tick
