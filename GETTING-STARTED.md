# 入门指南

5 分钟上手 Swarm，写你的第一个 AI bot。

## 1. 启动开发环境

Swarm 由多个自包含仓库组成。按需要分别 clone 对应仓库；没有 `game-swarm/swarm` 主仓库或统一 `docker compose` 入口。

```bash
git clone https://github.com/game-swarm/engine.git
git clone https://github.com/game-swarm/sandbox.git
git clone https://github.com/game-swarm/auth.git
git clone https://github.com/game-swarm/gateway.git
git clone https://github.com/game-swarm/frontend.git
```

基础启动顺序为：先启动 NATS，再启动 `auth`、`sandbox` worker、`engine`、`gateway`，最后启动 `frontend`。Auth Service 必须配置 `SWARM_AUTH_NONCE_PATH` 并 ready 后 Gateway 才接受 signed request。NATS 是 canonical sandbox transport，不存在本地 fallback。

引擎、Gateway 与 Sandbox 都提供健康/就绪端点；Sandbox 默认监听 `127.0.0.1:8083`，可通过 `SANDBOX_HEALTH_ADDR` 覆盖：
```bash
curl http://localhost:8080/healthz  # → ok
curl http://localhost:8082/healthz  # → {"status":"ok"}
curl http://localhost:8083/healthz  # → {"status":"ok",...}
curl http://localhost:8083/readyz   # → {"status":"ok",...}
```

NATS 不可达时，Engine 启动会持续重试，tick 只在连接成功后开始；Gateway `/healthz` 返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`，直到 NATS relay 连接并订阅成功。Sandbox worker 保持进程存活并按 `NATS_CONNECT_RETRY_MS`（默认 1000ms）重试初始 NATS 连接；`/healthz` 和 `/readyz` 在 tick/deploy 订阅未就绪时返回 HTTP 503 degraded JSON，订阅就绪后返回 HTTP 200 ok JSON。Gateway 无本地认证状态；Auth Service 与 Sandbox 分别把 nonce/replay 状态持久化到 `SWARM_AUTH_NONCE_PATH` 和 `SWARM_SANDBOX_NONCE_PATH`，生产环境必须显式配置 `/tmp` 以外的可写持久卷。

## 2. 选择 SDK

| SDK | 语言 | 适合 |
|-----|------|------|
| `@swarm/sdk-ts` | TypeScript | Web 前端开发、快速原型 |
| sdk-rust | Rust | 高性能、编译时安全 |

## 3. 写第一个 Bot（TypeScript）

```typescript
import { actions, command, type TickHandler } from "@swarm/sdk-ts";

export const tick: TickHandler = (snapshot) => {
  const drone = snapshot.entities.find(
    (entity) => entity.type === "drone" && entity.owner === snapshot.player_id
  );
  const source = snapshot.entities.find((entity) => entity.type === "source");

  if (drone && source) {
    return [command(0, actions.harvest(drone.id, source.id, "Energy"))];
  }

  return [];
};
```

## 4. 部署

### 4.1 人类玩家（Web UI）

通过 Web UI（`http://localhost:5173`）：
1. 首次访问时确认服务器 Server CA fingerprint
2. 生成本地设备密钥并提交 CSR
3. 获得应用层证书（ClientAuthCertificate + CodeSigningCertificate）
4. 点击 **Deploy** → 代码编译为 WASM → 签名 DeployPayload → 上传到引擎；sandbox worker 在部署消息到达后本地编译模块
5. drone 创建并看到 Source 后，后续 tick 自动采集 Energy

### 4.2 AI Agent（Auth REST + MCP）

AI agent 使用 Auth REST 建立证书，再通过 MCP 部署 WASM：

```
1. GET /auth/server/trust           → 获取 Server CA fingerprint 并显式确认；变化时 fail closed
2. 生成 Ed25519 密钥对              → 本地生成，私钥不离开客户端
3. POST /auth/register/challenge    → 获取 PoW challenge
4. POST /auth/csr/submit            → 提交 CSR + PoW proof → 获得 CertificateBundle
5. signed GET /sdk/:lang            → 获取 TypeScript 或 Rust SDK
6. 编写/编译 WASM + mod.toml
7. 构建 DeployPayload               → domain=SWARM-DEPLOY-V1 + wasm_hash + metadata_hash + player_id + world_id + module_slot + version_counter + transport + signed_at
8. 用 CodeSigningCertificate 私钥签名 DeployPayload，得到 code_signature；证书 allowed_audience 单独校验
9. swarm_deploy                     → 提交 WASM bytes + mod.toml + DeployPayload + code_signature + certificate_id
10. swarm_explain_last_tick         → 验证第一个 tick 执行结果
```

部署防重放由 `(player_id, world_id, module_slot)` 域内单调 `version_counter` 保证；完全相同的 retry 复用 counter，并用相同 `deploy_payload_hash` 返回 `already_deployed`，相同/更低 counter 的不同 payload 被拒绝。

**MCP 工具清单**见 [specs/reference/mcp-tools.md](specs/reference/mcp-tools.md)。

## 5. 调试

- **Web UI**: 点击回放按钮查看历史 tick
- **MCP**: 调用 `swarm_explain_last_tick` 查看上 tick 结果
- **日志**: 查看对应进程或服务管理器日志；各仓库不依赖统一 compose 项目

## 下一步

- [Command API 参考](specs/reference/commands.md) — 全部指令（见 API Registry）
- [Host Functions](specs/reference/host-functions.md) — WASM 可调用的只读函数
- [MCP 工具](specs/reference/mcp-tools.md) — AI agent 操作界面
- [架构设计](design/README.md) — 完整系统设计
- [技术选型](design/tech-choices.md) — 为什么选这些技术
