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
      action: "SpawnDrone",
      object_id: spawn.id,
      body: ["MOVE", "WORK", "CARRY"],
      seq: 1,
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
      seq: 2,
    });
  }

  return cmds;
});
```

## 4. 部署

通过 Web UI（`http://localhost:5173`）：
1. 用 GitHub 登录
2. 在 Monaco 编辑器中粘贴代码
3. 点击 **Deploy** → 代码编译为 WASM → 上传到引擎
4. 下一个 tick 开始，你的 drone 就会自动采集

通过 MCP（AI agent）：
```
swarm_deploy(module_bytes, wasm_signature)
```

## 5. 调试

- **Web UI**: 点击回放按钮查看历史 tick
- **MCP**: 调用 `swarm_explain_last_tick` 查看上 tick 结果
- **日志**: `docker compose logs engine`

## 下一步

- [Command API 参考](api/commands.md) — 全部 12 种指令
- [Host Functions](api/host-functions.md) — WASM 可调用的只读函数
- [MCP 工具](api/mcp-tools.md) — AI agent 操作界面
- [架构设计](design/DESIGN.md) — 完整系统设计
- [技术选型](design/tech-choices.md) — 为什么选这些技术
