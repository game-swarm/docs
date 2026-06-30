# Swarm 运维手册 (Runbook)

## 1. 启动序列

### 1.1 完整栈启动 (生产)

```bash
# 1. 基础设施 (仅 NATS 是外部 daemon)
docker compose up -d nats

# 2. 等待 NATS 就绪
docker compose exec nats nats server check connection

# 3. 引擎 (redb + Moka Cache 均为进程内，无需额外 daemon)
docker compose up -d engine

# 4. Gateway
docker compose up -d gateway

# 5. 健康检查
curl -f http://localhost:8080/healthz          # 引擎
curl -f http://localhost:8082/healthz          # gateway
```

### 1.2 启动顺序约束

```
nats ──→ engine ──→ gateway ──→ frontend
```

| 服务 | 依赖 | 启动超时 | 就绪信号 |
|------|------|---------|---------|
| NATS | 无 | 10s | `nats server check connection` |
| Engine | NATS | 60s | `/healthz` → 200，`tick_ok: true` |
| Gateway | Engine + NATS | 15s | `/healthz` → 200 |
| Frontend | Gateway | 10s | HTTP 200 on `/` |

### 1.3 降级启动

```bash
# 仅引擎 (无 NATS) — 单节点开发/测试
docker compose up engine

# 引擎 + NATS — 标准生产
docker compose up nats engine gateway
```

降级模式下引擎自动检测依赖缺失：
- 无 NATS → delta 推送暂停，客户端 REST fetch 同步
- Moka Cache miss → Engine 从 redb 重建缓存

### 1.4 启动后验证

```bash
# 1. 引擎存活
curl -s http://localhost:8080/healthz | jq .

# 2. 首个 tick 完成
curl -s http://localhost:8080/metrics | grep "tick_number"

# 3. Gateway 就绪
curl -s http://localhost:8082/healthz | jq .
```

---

## 2. 密钥轮换

### world_seed

```bash
# 生成新种子
python3 -c "import secrets; print(secrets.token_hex(32))"
# 更新 world.toml 中的 world_seed
```

### Server CA 与应用层证书

Swarm 使用单层 Server CA，不分 Root/Intermediate。详见 `design/auth.md`。

```bash
# 生成 Server CA（生产应放入离线介质/HSM）
swarm ca init --out /secure/swarm-ca

# 查看 server CA fingerprint，供客户端首次 pinning
swarm ca fingerprint --ca /secure/swarm-ca
```

手动吊销证书：

```bash
swarm cert revoke --certificate-id <CERT_ID> --reason <lost_device|key_compromise|admin_action>
```

在线 CRL 仅保留未过期和最近过期窗口内的吊销项；自然过期证书不需要长期保留在在线认证路径。

### Auth Service epoch emergency bump

```bash
# Server CA 泄露 → bump epoch → 所有替换前证书立即失效
swarm auth epoch-bump --reason "ca_compromise"
```

---

## 3. 备份恢复

### 备份

redb 是嵌入式单文件存储。备份只需复制 `.redb` 文件（引擎停止时）或使用 redb 在线备份。

```bash
# 在线备份 (redb 支持在线一致快照)
swarm backup create --output /backup/swarm_$(date +%Y%m%d_%H%M%S).redb

# 或直接复制（需停止引擎）
docker compose stop engine
cp /data/swarm/world.redb /backup/world_$(date +%Y%m%d_%H%M%S).redb
docker compose up -d engine
```

### 恢复

```bash
# 停止引擎
docker compose stop engine

# 替换 redb 文件
cp /backup/world_latest.redb /data/swarm/world.redb

# 验证 state_checksum
swarm verify --redb /data/swarm/world.redb

# 启动引擎
docker compose up -d engine

# 监控 100 tick
watch -n 5 "curl -s localhost:8080/metrics | grep tick_number"
```

---

## 4. 降级模式

| 模式 | 触发 | 影响 | 恢复 |
|------|------|------|------|
| **无 NATS** | NATS 连接丢失 | delta 推送暂停，客户端 REST fetch | NATS 恢复后自动重连 |
| **Moka Cache miss** | Engine 进程内缓存未命中或过期 | 读取回退 redb 直读 | Engine 异步重建缓存 |
| **引擎 OOM** | cgroup OOM killer | 进程重启，从 redb 恢复最近 tick | systemd auto-restart |
| **redb 写入失败** | 磁盘满/权限错误 | tick abort，世界状态不推进 | 运维介入检查磁盘/权限 |

---

## 5. 监控指标

| 指标 | 告警阈值 | 严重度 |
|------|---------|:--:|
| tick_duration_p99 | > 3s | WARN |
| tick_duration_p99 | > 4s | CRITICAL — tick 放弃风险 |
| refund_abuse_rate | > 20% | WARN |
| command_rejection_rate | > 30% | WARN |
| consecutive_tick_failures | > 3 | CRITICAL |
| NATS 连接丢失 | > 5s | WARN |
| WASM compile queue depth | > 10 | WARN |
| Engine memory usage | > 80% cgroup limit | WARN |
| Sandbox worker crash rate | > 5% | WARN |

---

## 6. 灾难恢复

1. 停止引擎: `docker compose stop engine`
2. 恢复 redb 备份: `cp /backup/world_latest.redb /data/swarm/world.redb`
3. 验证 state_checksum: `swarm verify --redb /data/swarm/world.redb`
4. 启动引擎: `docker compose up -d engine`
5. 监控 100 tick: `watch -n 5 "curl -s localhost:8080/metrics | grep tick_number"`
6. 验证无玩家数据丢失: 抽样检查 player 资源总量

---

## 7. 组件清单 (与设计一致)

| 组件 | 类型 | 部署方式 |
|------|------|---------|
| **redb** | Engine 进程内嵌入式 KV | 无需独立 daemon，每 shard 一个 `.redb` 文件 |
| **Moka Cache** | Engine 进程内读缓存 | 无需独立 daemon，随 Engine 生命周期 |
| **NATS** | 外部 daemon | Docker Compose，单节点部署即为单节点 cluster |
| **Gateway** | Rust 独立进程 | Docker Compose，无状态可水平扩展 |
| **Sandbox Containers** | WASM 执行 worker pool | Docker Compose + NATS queue-group 负载均衡 |
| **Frontend** | Nginx 静态文件服务 | Docker Compose |