# 入门指南

5 分钟上手 Swarm，写你的第一个 AI bot。

## 1. 启动开发环境

```bash
git clone git@git.kagurazakalan.com:swarm/infra.git swarm
cd swarm
docker compose up --build
```

确认服务就绪：
```bash
curl http://localhost:8080/healthz  # → {"status":"ok"}
```

## 2. 选择 SDK

| SDK | 语言 | 适合 |
|-----|------|------|
| [sdk-ts](../sdk-ts/) | TypeScript | Web 前端开发、快速原型 |
| [sdk-rust](../sdk-rust/) | Rust | 高性能、编译时安全 |

## 3. 写第一个 Bot（TypeScript）

```typescript
import { tick, Snapshot, Command } from "swarm-sdk";

tick((snap: Snapshot): Command[] => {
  const cmds: Command[] = [];

  // 找到自己的 spawn
  const spawn = snap.entities.find(e => e.type === "Structure" && e.structure_type === "Spawn");
  if (!spawn) return [];

  // 没有 drone → 生成一个
  const drones = snap.entities.filter(e => e.type === "Drone");
  if (drones.length === 0) {
    cmds.push({
      action: "Spawn",
      object_id: spawn.id,
      body: ["MOVE", "WORK", "CARRY"],
      sequence: 1,
    });
    return cmds;
  }

  // 有 drone → 找最近的 Source 采集
  const drone = drones[0];
  const source = snap.entities.find(e => e.type === "Source");
  if (source) {
    cmds.push({
      action: "Harvest",
      object_id: drone.id,
      target_id: source.id,
      sequence: 2,
    });
  }

  return cmds;
});
```

## 4. 部署

### 4.1 人类玩家（Web UI）

通过 Web UI（`http://localhost:5173`）：
1. 首次访问时确认服务器 Root CA fingerprint
2. 生成本地设备密钥并提交 CSR
3. 获得应用层证书 bundle（ClientAuthCertificate + CodeSigningCertificate）
4. 点击 **Deploy** → 代码编译为 WASM → 签名 DeployPayload → 上传到引擎
5. 下一个 tick 开始，你的 drone 就会自动采集

### 4.2 AI Agent（MCP）

AI agent 通过 MCP 部署 WASM，与人类玩家走相同的证书路径：

```
1. swarm_get_server_trust    → 获取 server_id + Root CA fingerprint
2. 生成 Ed25519 密钥对       → 本地生成，私钥不离开客户端
3. swarm_register_challenge  → 获取 PoW challenge
4. swarm_submit_csr          → 提交 CSR + PoW proof → 获得 CertificateBundle
5. 编写/编译 WASM + mod.toml → TypeScript SDK 或 Rust SDK
6. 构建 DeployPayload         → version_counter + wasm_module_hash + metadata_hash + audience + signed_at
7. 用 CodeSigningCertificate 私钥签名 DeployPayload
8. swarm_deploy              → 提交 WASM bytes + mod.toml + DeployPayload + 证书链
9. swarm_explain_last_tick   → 验证第一个 tick 执行结果
```

不需要先请求 `swarm_deploy_challenge`——防重放由 `version_counter` 保证。

**MCP 工具清单**见 [specs/reference/mcp-tools.md](specs/reference/mcp-tools.md)。

## 5. 调试

- **Web UI**: 点击回放按钮查看历史 tick
- **MCP**: 调用 `swarm_explain_last_tick` 查看上 tick 结果
- **日志**: `docker compose logs engine`

## 下一步

- [Command API 参考](specs/reference/commands.md) — 全部指令（见 API Registry）
- [Host Functions](specs/reference/host-functions.md) — WASM 可调用的只读函数
- [MCP 工具](specs/reference/mcp-tools.md) — AI agent 操作界面
- [架构设计](design/README.md) — 完整系统设计
- [技术选型](design/tech-choices.md) — 为什么选这些技术
