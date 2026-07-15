# 入门指南

5 分钟上手 Swarm，写你的第一个 AI bot。

## 1. 启动开发环境

Swarm 由多个自包含仓库组成。按需要分别 clone 对应仓库；没有 `game-swarm/swarm` 主仓库或统一 `docker compose` 入口。

```bash
git clone https://github.com/game-swarm/engine.git
git clone https://github.com/game-swarm/sandbox.git
git clone https://github.com/game-swarm/gateway.git
git clone https://github.com/game-swarm/frontend.git
```

基础启动顺序为：先启动 NATS，再启动 `sandbox` worker、`engine`、`gateway`，最后启动 `frontend`。Engine、Gateway 和 Sandbox worker 都会重试初始 NATS 连接，但当前没有无 NATS 的本地 sandbox fallback。每个仓库的 README 负责说明本仓库的本地启动命令。

引擎与 Gateway 的健康端点分别返回纯文本和 JSON：
```bash
curl http://localhost:8080/healthz  # → ok
curl http://localhost:8082/healthz  # → {"status":"ok"}
```

NATS 不可达时，Engine 启动会持续重试，tick 只在连接成功后开始；Gateway `/healthz` 返回 HTTP 503 和 `{"status":"degraded","nats":"unavailable"}`，直到 NATS relay 连接并订阅成功。Sandbox worker 没有 HTTP readiness endpoint；它保持进程存活并按 `NATS_CONNECT_RETRY_MS`（默认 1000ms）重试初始 NATS 连接。Gateway 与 Sandbox 会把认证 nonce/replay 状态分别持久化到 `SWARM_GATEWAY_NONCE_PATH` 和 `SWARM_SANDBOX_NONCE_PATH`；开发环境默认分别使用私有进程临时目录和私有用户状态目录，生产环境必须显式配置 `/tmp` 以外的可写持久卷，避免重启后接受旧 nonce。

## 2. 选择 SDK

| SDK | 语言 | 适合 |
|-----|------|------|
| `@swarm/sdk-ts` | TypeScript | Web 前端开发、快速原型 |
| sdk-rust | Rust | 高性能、编译时安全 |

## 3. 写第一个 Bot（TypeScript）

```typescript
import { actions, command, type TickHandler } from "@swarm/sdk-ts";

export const tick: TickHandler = (snapshot) => {
  const spawn = snapshot.entities.find(
    (entity) => entity.type === "structure" && entity.owner === snapshot.player_id
  );

  if (!spawn) return [];

  return [command(0, actions.spawn(spawn.id, ["Move", "Work", "Carry"]))];
};
```

## 4. 部署

### 4.1 人类玩家（Web UI）

通过 Web UI（`http://localhost:5173`）：
1. 首次访问时确认服务器 Server CA fingerprint
2. 生成本地设备密钥并提交 CSR
3. 获得应用层证书（ClientAuthCertificate + CodeSigningCertificate）
4. 点击 **Deploy** → 代码编译为 WASM → 签名 DeployPayload → 上传到引擎；sandbox worker 在部署消息到达后本地编译模块
5. 下一个 tick 开始，你的 drone 就会自动采集

### 4.2 AI Agent（MCP）

AI agent 通过 MCP 部署 WASM，与人类玩家走相同的证书路径：

```
1. swarm_get_server_trust    → 获取 server_id + Server CA fingerprint
2. 生成 Ed25519 密钥对       → 本地生成，私钥不离开客户端
3. swarm_register_challenge  → 获取 PoW challenge
4. swarm_submit_csr          → 提交 CSR + PoW proof → 获得 CertificateBundle
5. 编写/编译 WASM + mod.toml → TypeScript SDK 或 Rust SDK
6. 构建 DeployPayload         → version_counter + wasm_module_hash + metadata_hash + audience + signed_at
7. 用 CodeSigningCertificate 私钥签名 DeployPayload
8. swarm_deploy              → 提交 WASM bytes + mod.toml + DeployPayload + 证书
9. swarm_explain_last_tick   → 验证第一个 tick 执行结果
```

部署防重放由单调递增的 `version_counter` 保证。

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
