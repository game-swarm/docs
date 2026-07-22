# Swarm 运维手册 (Runbook)

> 本手册描述当前工作树的运行行为。设计文档中的目标态组件或指标端点不应当作为现网操作步骤。

## 1. 启动序列

### 1.1 完整栈启动 (生产)

Swarm 没有单一主仓库。生产部署应把 `engine`、`sandbox`、`gateway`、`frontend` 作为独立制品发布；NATS 是外部基础设施服务。

**生产环境强制安全要求：**

- **NATS 安全**：Engine、Gateway 和 Sandbox 默认使用 `production` 模式。必须设置 `NATS_TLS_REQUIRED=true` 并通过 `NATS_CREDENTIALS_FILE` 指定有效的 NATS 角色凭据。
- **消息认证**：Engine/Sandbox 共享 `SWARM_NATS_AUTH_SECRET`；Engine/Gateway 共享 `SWARM_PROXY_SIGNATURE_SECRET`；所有 shards 共享 `SWARM_MIGRATION_AUTH_SECRET`，并配置 `swarm.migration.v1.<target_shard>` 的 per-shard publish/subscribe ACL。
- **Engine 发行者密钥**：必须设置 `SWARM_ENGINE_ISSUER_KEY_FILE` (32字节种子文件) 或 `SWARM_ENGINE_ISSUER_KEY_B64`。
- **持久化 Nonce**：Auth Service canonical request replay store `SWARM_AUTH_NONCE_PATH`、Engine proxy nonce store `SWARM_PROXY_NONCE_PATH` 与 Sandbox NATS nonce store `SWARM_SANDBOX_NONCE_PATH` **必须指向 `/tmp` 以外的可写持久卷**。Gateway 无本地 nonce store，所有实例调用同一逻辑 Auth Service 原子校验。路径父目录必须归对应服务用户所有、权限私有且不能是 symlink。
- **备份**：Engine 必须配置 `KEYFRAME_BACKUP_PATH` 以启用生产级 Keyframe 备份。

```bash
# 1. 基础设施
systemctl start nats

# 2. 等待 NATS 就绪
nats server check connection

# 3. Auth Service
systemctl start swarm-auth

# 4. Sandbox workers (SWARM_SANDBOX_MODE=production)
systemctl start swarm-sandbox

# 5. 引擎 (SWARM_ENGINE_MODE=production, REDB_PATH 指向持久卷)
systemctl start swarm-engine

# 6. Gateway (SWARM_GATEWAY_MODE=production)
systemctl start swarm-gateway

# 7. Frontend
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
| Sandbox | NATS | 无固定超时；持续重试初始连接 | `/healthz`/`/readyz` on `SANDBOX_HEALTH_ADDR` (默认 `127.0.0.1:8083`)；订阅未就绪时 503 degraded JSON |
| Engine | NATS + Sandbox | 无固定超时；按 tick interval 重试初始 NATS | `/healthz` → `200 ok`；依赖未就绪时 `503 degraded` |
| Gateway | Engine + NATS | 无固定超时；按 `NATS_RETRY_DELAY_MS` 重试 NATS relay | `/healthz` → 200 JSON；NATS relay 未就绪时 503 degraded JSON |
| Frontend | Gateway | 10s | HTTP 200 on `/` |

### 1.3 降级启动

```bash
# 引擎 + NATS — canonical 运行方式
systemctl start nats swarm-sandbox swarm-engine swarm-gateway
```

Engine、Gateway 和 Sandbox 都会重试初始 NATS 连接；NATS 不可达时不得切换到本地 sandbox fallback。Engine `/healthz` 在依赖未就绪时返回 `503 degraded`。Gateway HTTP server 保持运行，但 `/healthz` 在 NATS relay 未连接并订阅前返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`。Sandbox worker 保持进程存活并按 `NATS_CONNECT_RETRY_MS` 重试初始 NATS 连接；`/healthz` 和 `/readyz` 在 tick/deploy 订阅未就绪时返回 HTTP 503 degraded JSON，订阅就绪后返回 HTTP 200 ok JSON。Gateway canonical request verification 依赖 Auth Service shared replay store；RPC 或 store 不可用时 fail closed。运行架构不依赖外部缓存库。

### 1.4 启动后验证

```bash
# 1. 引擎存活（纯文本 ok/degraded）
curl -fsS http://localhost:8080/healthz

# 2. 引擎指标核对（Prometheus text）
curl -fsS http://localhost:8080/metrics

# 3. Gateway 就绪（NATS relay 未就绪时返回 503 degraded JSON）
curl -s http://localhost:8082/healthz | jq .

# 4. Sandbox 就绪（tick/deploy 订阅未就绪时返回 503 degraded JSON）
curl -s http://localhost:8083/readyz | jq .
```

### 1.5 本地开发启动 (Development)

本地开发环境允许使用明文 NATS，但 Engine 仍要求可用的 redb 与 keyframe backup 文件路径。Auth Service 与 Sandbox 使用各自私有开发 nonce 路径；Gateway 始终无本地 nonce store。

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

# Auth Service 与 Sandbox 的本地开发路径
export SWARM_AUTH_NONCE_PATH="./auth-nonces.db"
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
swarm verify --redb /data/swarm/world.redb --keyframes /data/swarm/world.redb.keyframes
swarm keyframe backup \
  --source /data/swarm/world.redb.keyframes \
  --dest /backup/keyframes \
  --encrypt-key kms://swarm/keyframe-backup
```

每个 keyframe 至少保留 primary + backup 两份，分别校验 `header_crc32c` 与 `payload_blake3`。备份目标与 redb 主盘隔离，避免同一磁盘故障同时损坏 redb 与 keyframe。

### Retention 配置

redb replay-critical history 随世界生命周期永久保留且不可配置裁剪。`world.toml` 仅使用 tick 数配置 rich artifact 与 keyframe/delta 加速路径的保留期：

```toml
[retention]
rich_artifact_retention_ticks = 864_000
keyframe_acceleration_retention_ticks = 5_184_000
keyframe_backup_copies = 2
```

`rich_artifact_retention_ticks` 控制 RichTraceBlob、可视化 annotation 和调试 artifact。`keyframe_acceleration_retention_ticks` 只控制恢复加速窗口；对象全部丢失时必须从永久 redb genesis log replay。

恢复目标：RPO ≤ 100 ticks，RTO ≤ 300s。

### 恢复流程

恢复前必须进行 **redb replay-critical history 完整性** 验证。若 keyframe/delta 可用，再验证其连续性并作为加速起点；缺失或损坏时从 genesis replay。

1. **停止引擎**：`systemctl stop swarm-engine`
2. **保护现场**：**禁止删除任何疑似损坏的数据或日志**。将当前 redb 与 keyframe 移动到备份目录以供后续审计。
3. **验证备份**：
   - 使用 `swarm verify --redb /backup/target.redb --keyframes /backup/target.keyframes` 检查备份集的完整性与衔接性。
4. **数据恢复**：
   - 恢复上一份经过验证的完整 `redb` + `keyframe` 对。
   - **验证恢复目标**：在启动引擎前，再次对 `/data/swarm/` 下恢复后的文件运行 `swarm verify --redb ... --keyframes ...`。
5. **故障定义与回滚**：
   - 若验证失败或重启后 `/healthz` 持续 503：**保持引擎停止状态**，直到人工介入分析原因。
   - **记录 RPO/RTO**：手动记录数据丢失时长（RPO）与服务中断时长（RTO）。

### 恢复操作示例

```bash
# 1. 停止引擎
systemctl stop swarm-engine

# 2. 保护现场（同一恢复事件使用同一目录）
recovery_id=$(date +%s)
mkdir -p "/backup/recovery-${recovery_id}"
mv /data/swarm/world.redb "/backup/recovery-${recovery_id}/world.redb"
mv /data/swarm/world.redb.keyframes "/backup/recovery-${recovery_id}/world.redb.keyframes"

# 3. 验证备份 (必须步骤)
swarm verify --redb /backup/world_latest.redb --keyframes /backup/keyframes

# 4. 恢复文件
cp /backup/world_latest.redb /data/swarm/world.redb
swarm keyframe restore --source /backup/keyframes --dest /data/swarm/world.redb.keyframes

# 5. 验证恢复后的文件
swarm verify --redb /data/swarm/world.redb --keyframes /data/swarm/world.redb.keyframes

# 6. 启动并核对健康状态
systemctl start swarm-engine
watch -n 5 "curl -fsS localhost:8080/healthz"
```

## 4. 运行监控

Engine 提供 Prometheus text 格式的 `/metrics` 导出端点；其他服务的监控仍依赖健康端点和本地日志观测：

1. **日志收集**：所有服务日志输出至 stdout/stderr，由宿主系统（如 journald）收集。
2. **Engine 指标**：抓取 Engine `/metrics`，基础 readiness 指标包含 `swarm_engine_up`、`swarm_engine_authoritative_tick`、`swarm_engine_redb_ready`、`swarm_engine_nats_ready`。
3. **状态表观测**：定期检查 Engine `/healthz`、Gateway `/healthz`、Sandbox `/healthz`/`/readyz` 输出。
4. **警报所有权**：外部监控系统应主动探测各组件端口连通性及健康/就绪状态。
5. **数据源**：仅限本 Runbook 及各组件设计文档中说明的本地日志、指标和状态接口。

---

## 5. 降级模式

| 模式 | 触发 | 影响 | 恢复 |
|------|------|------|------|
| **无 NATS** | NATS 不可达或连接丢失 | Engine `/healthz` 返回 `503 degraded`；Gateway `/healthz` 返回 503 degraded JSON；Sandbox `/healthz`/`/readyz` 返回 503 degraded JSON 并持续重试初始连接；无本地 sandbox fallback | 恢复 NATS 后 Engine/Gateway 重新变为健康，Sandbox 订阅恢复 |
| **Moka cache miss** | Engine 进程内 Moka cache 未命中 | 读取回退 redb 直读 | Engine 重建缓存 |
| **引擎 OOM** | cgroup OOM killer | 进程重启，从 redb 恢复最近 tick | systemd auto-restart |
| **redb 写入失败** | 磁盘满/权限错误 | tick abort，世界状态不推进 | 运维介入检查磁盘/权限 |

---

## 6. 监控指标与阈值

> **注意**：Engine `/metrics` 是基础进程健康、authoritative tick 和 redb/NATS readiness 的权威 scrape 面。下表中的业务指标监控与阈值告警由 operator-provided 日志收集器或 TickTrace 收集器负责，并需要指派专门的告警责任人。

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

## 7. 灾难恢复

本节定义了完整的灾难恢复流程，详见 [恢复流程](#恢复流程)。恢复的核心操作必须包含对 redb 与 keyframe 组合的 `swarm verify`，禁止运行未经完整验证的备份或跳过任何步骤。

所有关键参数（如 `base_upkeep`, `room_soft_cap` 等）应在恢复后通过 `swarm inspect --redb /data/swarm/world.redb` 进行人工核对。

---

## 8. 组件清单 (与设计一致)

| 组件 | 类型 | 部署方式 |
|------|------|---------|
| **redb** | Engine 进程内嵌入式 KV | 无需独立 daemon，每 shard 一个 `.redb` 文件 |
| **Auth Service** | 应用层证书 + shared nonce replay store | 独立制品；Gateway fail-closed dependency |
| **Moka cache** | Engine 进程内读缓存 | 无需独立 daemon，随 Engine 生命周期；deterministic state iteration 仍使用 BTreeMap |
| **NATS** | 外部 daemon | 独立服务，单节点部署即为单节点 cluster |
| **Gateway** | Rust 独立进程 | 独立制品发布，无状态可水平扩展 |
| **Sandbox Workers** | WASM 执行 worker pool | 独立制品发布，通过 NATS queue-group 负载均衡 |
| **Frontend** | 静态 Web 制品 | 独立构建后由任意静态文件服务托管 |

## 9. Container Tags

Engine, frontend, gateway, and sandbox CI publish to GHCR (`ghcr.io/game-swarm/<service>`). Each workflow publishes `sha-<commit>` tags, and publishes mutable `latest` only for the default branch. The workflows require GHCR login before pushing; no Docker Hub or branch-tag publishing path is defined. A SHA-shaped tag is a deployment pin, but the repositories do not configure GHCR policy to enforce immutability. Record the full image digest in production deployment configuration when an immutable artifact reference is required.
