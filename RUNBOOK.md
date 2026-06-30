# Swarm 运维手册 (Runbook)

## 1. 启动序列

### 1.1 完整栈启动 (生产)

```bash
# 1. 基础设施
docker compose up -d fdb nats dragonfly

# 2. 等待依赖就绪
docker compose exec fdb fdbcli --exec "status" | grep -q "available"
docker compose exec nats nats server check connection
docker compose exec dragonfly redis-cli PING | grep -q "PONG"

# 3. 编译服务 (独立启动，不阻塞引擎)
docker compose up -d compiler

# 4. 引擎 (等待 FDB + NATS 就绪后)
docker compose up -d engine

# 5. 健康检查
curl -f http://localhost:8080/healthz          # 引擎
curl -f http://localhost:8081/healthz          # compiler
curl -f http://localhost:8082/healthz          # gateway
```

### 1.2 启动顺序约束

```
fdb ──→ nats ──→ engine ──→ gateway ──→ frontend
  │                │
  └──→ compiler ───┘  (compiler 可与 engine 并行启动)
  │
  └──→ moka cache    (Engine 进程内读缓存)
```

| 服务 | 依赖 | 启动超时 | 就绪信号 |
|------|------|---------|---------|
| FDB | 无 | 30s | `fdbcli --exec status` 返回 `available` |
| NATS | 无 | 10s | `nats server check connection` |
| Compiler | FDB | 15s | `/healthz` → 200 |
| Engine | FDB + NATS | 60s | `/healthz` → 200，`tick_ok: true` |
| Gateway | Engine + NATS | 15s | `/healthz` → 200 |
| Frontend | Gateway | 10s | HTTP 200 on `/` |

### 1.3 降级启动

```bash
# 仅引擎 (无 FDB/NATS) — 开发/测试
docker compose up engine

# 引擎 + FDB (无 NATS) — 单节点持久化
docker compose up fdb engine

# 引擎 + NATS (无 FDB) — 无持久化，仅广播
docker compose up nats engine
```

降级模式下引擎自动检测依赖缺失：
- 无 FDB → 状态仅内存，tick 继续运行，`/healthz` 返回 `503 degraded`
- 无 NATS → delta 推送暂停，客户端 REST fetch 同步
- Moka Cache miss → 所有读取回退 FDB 直读

### 1.4 启动后验证

```bash
# 1. 引擎存活
curl -s http://localhost:8080/healthz | jq .

# 2. 首个 tick 完成
curl -s http://localhost:8080/metrics | grep "tick_number"

# 3. 玩家连接就绪
curl -s http://localhost:8082/healthz | jq .

# 4. WASM 编译就绪
curl -s http://localhost:8081/healthz | jq .
```

---

## 2. 密钥轮换

### world_seed
```bash
# 生成新种子
python3 -c "import secrets; print(secrets.token_hex(32))"
# 更新 world.toml 中的 world_seed
```

### Swarm CA 与应用层证书
```bash
# 生成离线 Server Root CA（仅示例；生产应放入离线介质/HSM）
swarm ca root init --out /secure/swarm-root-ca

# 生成在线 Server Intermediate CA
swarm ca intermediate issue --root /secure/swarm-root-ca --out /etc/swarm/intermediate

# 查看服务器 trust fingerprint，供客户端首次 pinning
swarm ca fingerprint --root /secure/swarm-root-ca
```

手动吊销证书或设备 public key：
```bash
swarm cert revoke --certificate-id <CERT_ID> --reason <lost_device|key_compromise|admin_action>
swarm key revoke --player-id <ID> --public-key-id <KEY_ID> --reason lost_device
```

在线 CRL 仅保留未过期和最近过期窗口内的吊销项；自然过期证书不需要长期保留在在线认证路径。

### FDB credential
```bash
# 轮换 FDB 集群密钥
fdbcli --exec "configure new ssd"
```

---

## 3. 备份恢复

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

---

## 4. 降级模式

| 模式 | 触发 | 影响 | 恢复 |
|------|------|------|------|
| **无 FDB** | FDB 连接丢失 >3s | 状态仅内存，`/healthz 503` | FDB 恢复后自动重连 |
| **无 NATS** | NATS 连接丢失 | delta 推送暂停，客户端 REST fetch | NATS 恢复后自动重连 |
| **Moka Cache miss** | Engine 进程内缓存未命中或过期 | 读取回退 FDB 直读，性能下降 | Engine 异步重建缓存 |
| **引擎 OOM** | cgroup OOM killer | 进程重启，当前 tick 丢失（snapshot 恢复） | systemd auto-restart |
| **FDB commit 连续失败** | ≥3 次/tick | tick 放弃，引擎降级 | 运维介入检查 FDB 集群 |

---

## 5. 监控指标

| 指标 | 告警阈值 | 严重度 |
|------|---------|:--:|
| tick_duration_p99 | > 3s | WARN |
| tick_duration_p99 | > 4s | CRITICAL — tick 放弃风险 |
| refund_abuse_rate | > 20% | WARN |
| command_rejection_rate | > 30% | WARN |
| consecutive_tick_failures | > 3 | CRITICAL |
| FDB 连接丢失 | 即时 | CRITICAL |
| NATS 连接丢失 | > 5s | WARN |
| WASM compile queue depth | > 10 | WARN |
| Engine memory usage | > 80% cgroup limit | WARN |
| Sandbox worker crash rate | > 5% | WARN |

---

## 6. 灾难恢复

1. 停止引擎: `docker compose stop engine`
2. 恢复 FDB 备份: `fdbbackup restore file:///backup/fdb`
3. 恢复引擎快照: `swarm snapshot restore --input /backup/snapshot_latest.json`
4. 验证 state_checksum: `swarm verify --tick $(swarm status --last-tick)`
5. 启动引擎: `docker compose up -d engine`
6. 监控 100 tick: `watch -n 5 "curl -s localhost:8080/metrics | grep tick_number"`
7. 验证无玩家数据丢失: 抽样检查 player 资源总量
