# Swarm 运维手册 (Runbook)

> 本手册描述当前工作树的运行行为。设计文档中的目标态组件或指标端点不应当作为现网操作步骤。

## 1. 启动序列

### 1.1 完整栈启动 (生产)

Swarm 没有单一主仓库。生产部署应把 `engine`、`sandbox`、`gateway`、`frontend` 作为独立制品发布；NATS 是外部基础设施服务。

**生产环境强制安全要求：**

- **NATS 安全**：Engine、Gateway 和 Sandbox 默认使用 `production` 模式。必须设置 `NATS_TLS_REQUIRED=true` 并通过 `NATS_CREDENTIALS_FILE` 指定有效的 NATS 角色凭据。
- **消息认证**：Engine 与 Sandbox 必须从 secrets store 读取同一个 `SWARM_NATS_AUTH_SECRET`；Engine 与 Gateway 必须读取同一个 `SWARM_PROXY_SIGNATURE_SECRET`。
- **Engine 发行者密钥**：必须设置 `SWARM_ENGINE_ISSUER_KEY_FILE` (32字节种子文件) 或 `SWARM_ENGINE_ISSUER_KEY_B64`。
- **持久化 Nonce**：Engine proxy nonce store `SWARM_PROXY_NONCE_PATH`、Gateway 认证 nonce store `SWARM_GATEWAY_NONCE_PATH` 与 Sandbox NATS nonce store `SWARM_SANDBOX_NONCE_PATH` **必须指向 `/tmp` 以外的可写持久卷**。Engine nonce store 的父目录必须为 engine 用户所有、私有权限且不能是 symlink；未设置时生产默认使用 `/var/lib/swarm-engine/proxy-nonces.db`。开发环境必须为 Engine 显式设置带私有父目录的 `SWARM_PROXY_NONCE_PATH`；Gateway 与 Sandbox 未显式设置时分别使用私有进程临时目录和私有用户状态目录。
- **备份**：Engine 必须配置 `KEYFRAME_BACKUP_PATH` 以启用生产级 Keyframe 备份。

```bash
# 1. 基础设施
systemctl start nats

# 2. 等待 NATS 就绪
nats server check connection

# 3. Sandbox workers (SWARM_SANDBOX_MODE=production)
systemctl start swarm-sandbox

# 4. 引擎 (SWARM_ENGINE_MODE=production, REDB_PATH 指向持久卷)
systemctl start swarm-engine

# 5. Gateway (SWARM_GATEWAY_MODE=production)
systemctl start swarm-gateway

# 6. Frontend
# 环境变量必须包含:
# VITE_SWARM_COMPILE_URL=https://.../compile
# VITE_ENGINE_MCP_URL=https://.../mcp
# VITE_SWARM_WS_URL=wss://...
# VITE_SWARM_WORLD_ID=...
# VITE_SWARM_ROOM_ID=...
# VITE_SWARM_DRONE_ID=...
# VITE_SWARM_TARGET_MANIFEST_HASH=...
# VITE_SWARM_ENGINE_ABI_VERSION=...
systemctl start swarm-frontend
```


### 1.2 启动顺序约束

```
nats ──→ sandbox workers ──→ engine ──→ gateway ──→ frontend
```

| 服务 | 依赖 | 启动超时 | 就绪信号 |
|------|------|---------|---------|
| NATS | 无 | 10s | `nats server check connection` |
| Sandbox | NATS | 无固定超时；持续重试初始连接 | 无 HTTP readiness；日志显示 NATS connected 后订阅 active |
| Engine | NATS + Sandbox | 无固定超时；按 tick interval 重试初始 NATS | `/healthz` → `200 ok`；依赖未就绪时 `503 degraded` |
| Gateway | Engine + NATS | 无固定超时；按 `NATS_RETRY_DELAY_MS` 重试 NATS relay | `/healthz` → 200 JSON；NATS relay 未就绪时 503 degraded JSON |
| Frontend | Gateway | 10s | HTTP 200 on `/` |

### 1.3 降级启动

```bash
# 引擎 + NATS — 当前支持的运行方式
systemctl start nats swarm-sandbox swarm-engine swarm-gateway
```

Engine、Gateway 和 Sandbox 都会重试初始 NATS 连接；NATS 不可达时不会切换到本地 sandbox fallback。Engine `/healthz` 在依赖未就绪时返回 `503 degraded`。Gateway HTTP server 保持运行，但 `/healthz` 在 NATS relay 未连接并订阅前返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`。Sandbox worker 没有 HTTP readiness endpoint；它保持进程存活并按 `NATS_CONNECT_RETRY_MS` 重试初始 NATS 连接。当前没有外部缓存库。

### 1.4 启动后验证

```bash
# 1. 引擎存活（纯文本 ok/degraded）
curl -fsS http://localhost:8080/healthz

# 2. 引擎就绪（当前没有 /metrics 端点）
curl -fsS http://localhost:8080/healthz

# 3. Gateway 就绪（NATS relay 未就绪时返回 503 degraded JSON）
curl -s http://localhost:8082/healthz | jq .
```

### 1.5 本地开发启动 (Development)

本地开发环境允许使用明文 NATS，但 Engine 仍要求可用的 redb 与 keyframe backup 文件路径。Gateway 与 Sandbox 未显式配置 nonce 路径时，分别使用私有的进程临时目录和用户状态目录；不会回退到内存 nonce store。

```bash
# 设置开发环境变量
export SWARM_ENGINE_MODE=development
export SWARM_SANDBOX_MODE=development
export SWARM_GATEWAY_MODE=development

# 必须设置的基础密钥
export SWARM_NATS_AUTH_SECRET="dev-secret"
export SWARM_PROXY_SIGNATURE_SECRET="dev-proxy-secret"

# Engine 必须设置的持久化路径
export REDB_PATH="./dev.redb"
export KEYFRAME_BACKUP_PATH="./dev-backups"
export SWARM_PROXY_NONCE_PATH="./.swarm-state/proxy-nonces.db"
install -d -m 700 "$(dirname "$SWARM_PROXY_NONCE_PATH")"

# Gateway 与 Sandbox 的可选覆盖；缺失时使用各自的私有开发目录
export SWARM_GATEWAY_NONCE_PATH="./gateway-nonces.db"
export SWARM_SANDBOX_NONCE_PATH="./sandbox-nonces.db"

# 启动服务
# (请参考各目录下的 README.md 获取具体的 cargo/npm 启动指令)
```

---

## 2. 密钥轮换

### world_seed

```bash
# 生成新种子
python3 -c "import secrets; print(secrets.token_hex(32))"
# 更新 world.toml 中的 world_seed
```

world_seed 必须存放在加密 secrets store 或等价 KMS/HSM 中，不写入公开配置仓库。keyframe 包含 replay 所需 seed epoch，keyframe primary 与 backup 都必须静态加密；解密密钥与 keyframe 文件分离存放。

seed-bump 后：
- 旧 seed epoch 标记为 compromised 或 superseded，但配置 retention 窗口内的旧 keyframe 继续加密保留，保证历史 replay 可验证。
- 旧 keyframe 不随 seed-bump 删除；删除只由 `[retention]` 策略驱动。
- 访问旧 keyframe 需要 admin 审计记录，包含 operator、原因、tick range 和 key id。

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
systemctl stop swarm-engine
cp /data/swarm/world.redb /backup/world_$(date +%Y%m%d_%H%M%S).redb
systemctl start swarm-engine
```

Keyframe 备份要求：

```bash
swarm keyframe verify --path /data/swarm/world.redb.keyframes
swarm keyframe backup \
  --source /data/swarm/world.redb.keyframes \
  --dest /backup/keyframes \
  --encrypt-key kms://swarm/keyframe-backup
```

每个 keyframe 至少保留 primary + backup 两份，分别校验 `header_crc32c` 与 `payload_blake3`。备份目标与 redb 主盘隔离，避免同一磁盘故障同时损坏 redb 与 keyframe。

### Retention 配置

`world.toml` 使用 tick 数配置 replay 与 rich artifact 保留期：

```toml
[retention]
deterministic_replay_retention_ticks = 5_184_000
rich_artifact_retention_ticks = 864_000
keyframe_backup_copies = 2
```

`deterministic_replay_retention_ticks` 控制 redb replay-critical core、keyframe 和 delta chain；Arena 默认约 180 天。`rich_artifact_retention_ticks` 控制 RichTraceBlob、可视化 annotation 和调试 artifact，可独立缩短。

恢复目标：RPO ≤ 100 ticks，RTO ≤ 300s。

### 恢复

```bash
# 停止引擎
systemctl stop swarm-engine

# 替换 redb 文件
cp /backup/world_latest.redb /data/swarm/world.redb

# 验证 state_checksum
swarm verify --redb /data/swarm/world.redb

# 启动引擎
systemctl start swarm-engine

# 监控引擎健康（当前不提供 HTTP /metrics）
watch -n 5 "curl -fsS localhost:8080/healthz"
```

---

## 4. 降级模式

| 模式 | 触发 | 影响 | 恢复 |
|------|------|------|------|
| **无 NATS** | NATS 不可达或连接丢失 | Engine `/healthz` 返回 `503 degraded`；Gateway `/healthz` 返回 503 degraded JSON；Sandbox 无 HTTP readiness 并持续重试初始连接；无本地 sandbox fallback | 恢复 NATS 后 Engine/Gateway 重新变为健康，Sandbox 订阅恢复 |
| **BTreeMap cache miss** | Engine 进程内缓存未命中 | 读取回退 redb 直读 | Engine 重建缓存 |
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

1. 停止引擎: `systemctl stop swarm-engine`
2. 恢复 redb 备份: `cp /backup/world_latest.redb /data/swarm/world.redb`
3. 恢复 keyframe backup: `swarm keyframe restore --source /backup/keyframes --dest /data/swarm/world.redb.keyframes`
4. 验证 state_checksum 与 keyframe hash: `swarm verify --redb /data/swarm/world.redb --keyframes /data/swarm/world.redb.keyframes`
5. 启动引擎: `systemctl start swarm-engine`
6. 监控引擎健康: `watch -n 5 "curl -fsS localhost:8080/healthz"`
7. 验证无玩家数据丢失: 抽样检查 player 资源总量

---

## 7. 组件清单 (与设计一致)

| 组件 | 类型 | 部署方式 |
|------|------|---------|
| **redb** | Engine 进程内嵌入式 KV | 无需独立 daemon，每 shard 一个 `.redb` 文件 |
| **BTreeMap cache** | Engine 进程内读缓存 | 无需独立 daemon，随 Engine 生命周期 |
| **NATS** | 外部 daemon | 独立服务，单节点部署即为单节点 cluster |
| **Gateway** | Rust 独立进程 | 独立制品发布，无状态可水平扩展 |
| **Sandbox Workers** | WASM 执行 worker pool | 独立制品发布，通过 NATS queue-group 负载均衡 |
| **Frontend** | 静态 Web 制品 | 独立构建后由任意静态文件服务托管 |

## 8. Container Tags

Engine, frontend, gateway, and sandbox CI publish to GHCR (`ghcr.io/game-swarm/<service>`). Each workflow publishes `sha-<commit>` tags, and publishes mutable `latest` only for the default branch. The workflows require GHCR login before pushing; no Docker Hub or branch-tag publishing path is defined. A SHA-shaped tag is a deployment pin, but the repositories do not configure GHCR policy to enforce immutability. Record the full image digest in production deployment configuration when an immutable artifact reference is required.
