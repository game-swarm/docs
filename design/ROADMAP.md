# Swarm 实施计划

> 锚定 Phase 0 Architecture Freeze（2026-06-14），所有交付物挂到对应 P0 规范。

## 阶段总览

```
Phase 0  ✅  架构冻结           (已完成, 2026-06-14)
Phase 1  ✅  核心 MVP           (已完成, 2026-06-14)  单人垂直切片
Phase 2  ✅  MCP + 多人         (已完成, 2026-06-14)  AI/人类并行
Phase 3  ✅  持久化 + Rhai      (已完成, 2026-06-14)  数据落地 + 模组
Phase 4  ✅  教程 + 调试         (已完成, 2026-06-14)  新手上手 + 回放
Phase 5  ✅  Web 客户端          (已完成, 2026-06-14)  完整产品体验
Phase 6  ✅  战斗 + Arena        (已完成, 2026-06-14)  游戏化收官
Phase 7      生产化             8-12 周   公测标准
─────────────────────────────────────────
总计                            42-58 周
```

---

## Phase 1: 核心引擎 — MVP 单人垂直切片

**目标**: 一个玩家在一个房间里，用自己的 WASM 代码操控 drone，完成采集→建造→扩张的基础循环。引擎可以 tick-by-tick 确定回放。

**时间窗口**: 4-6 周

**依赖**: Phase 0 Frozen 通过。P0-1/P0-2/P0-4/P0-8 作为实现合同。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 1.1 | Bevy ECS 世界模拟 | P0-1 §3, P0-7 | 单房间 terrain + 1 Source + 平原 tile；ECS `.chain()` 顺序固定；`state_checksum` 产出 |
| 1.2 | WASM 沙箱 (per-tick fork) | P0-4 §1/§2/§4 | fuel metering 运行；epoch interruption 2500ms；线性内存 64MB；host functions 仅查询 |
| 1.3 | Game API — 基础指令 | P0-8 commands | Move/Harvest/Build/Spawn/Transfer 5 指令可用；每条走 P0-2 管线 |
| 1.4 | Command Validation Pipeline | P0-2 §1/§3/§7 | JSON schema 校验 → 预校验 → 应用；拒绝原因结构化返回；Refund 时序正确 |
| 1.5 | Tick 调度器 (单玩家) | P0-1 §2 | Collect → Validate → Execute → Broadcast 完整周期；3s tick 间隔 |
| 1.6 | TickTrace + 回放验证 | P0-1 §6.3 | 每 tick 写入指令+状态+拒绝；CI 随机采样 10 tick 做完整回放；`execute_deterministic == recorded_state` |
| 1.7 | TypeScript SDK (基础) | P0-8 codegen | `tick(snapshot) → Command[]` 类型完整；IDL 驱动生成 |
| 1.8 | MCP Server 脚手架 | P0-3 §1 | `swarm_get_snapshot` + `swarm_deploy` + `swarm_get_world_rules` 可用；不支持 gameplay action |
| 1.9 | Docker Compose 开发环境 | — | 单机一键启动：引擎 + FDB + NATS；可跑完整 tick 循环 |
| 1.10 | Starter Bot (TS) | P0-6 §2 | 5 分钟教程：采集 100 Energy → spawn worker → 自动循环 |

### Phase 1 成功标准

- 单个 starter bot 能在本地 docker-compose 环境中运行 1000 tick 不出错
- CI 中 `replay_tick(sampled_tick) == recorded_state` 100% 通过
- 新开发者 git clone + docker compose up 后 10 分钟内看到 drone 在动

---

## Phase 2: MCP 完整界面 + 多人世界

**目标**: 多个玩家（人类 + AI）在同一世界中并行运行，通过 MCP 部署和调试。WebSocket 实时推送世界状态。

**时间窗口**: 6-8 周

**依赖**: Phase 1 MVP 通过；P0-1 §2.1 多玩家调度就绪。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 2.1 | 多玩家 Tick 调度 | P0-1 §2.1/§3.1 | 并行 Collect（per-player WASM sandbox）→ 种子洗牌（Blake3 XOF）→ 串行 Execute → NATS Broadcast |
| 2.2 | MCP 完整工具集 | P0-3 §4 | `swarm_get_available_actions` + `swarm_explain_last_tick` + `swarm_profile` + `swarm_dry_run_commands` + `swarm_get_docs/schema` 全部可用 |
| 2.3 | MCP 认证 + 限流 | P0-3 §1.1, P0-9 §3 | OAuth2 → Ed25519 证书签发；部署附带签名验证；限流按 P0-9 来源矩阵强制执行 |
| 2.4 | Source Gate | P0-9 §4 | 12 来源全部管线化；WASM 通过/MCP_Deploy 拒绝 gameplay command；client 自报 player_id 被覆盖 |
| 2.5 | WebSocket 实时推送 | P0-1 §4 | NATS → 网关 → 客户端；delta 仅包含变更实体；客户端检测 gap → fetch |
| 2.6 | 指令冲突解决 | P0-2 §7 | SourceEmpty/TileOccupied/TargetFull → 先到先得 + 退还 50% fuel；拒绝原因结构化 |
| 2.7 | 统一可见性 | P0-5 | `is_visible_to(entity, player_id, tick)` 覆盖 snapshot/MCP/WS/REST/replay 全部输出面 |

### Phase 2 成功标准

- 3 个不同玩家的 WASM 模块在同一世界中正确并行，无人能观察到不该看到的实体
- MCP 客户端可通过 OAuth2 登录 → 获取证书 → 部署 WASM → 观察世界 → 调试，完整闭环无人工介入
- 多玩家 tick 间隔稳定在 3s，p99 < 5s

---

## Phase 3: 持久化 + 多房间 + Rhai 模组

**目标**: 世界状态持久化到 FoundationDB，支持多房间。Rhai 模组系统上线——服主可以安装 `empire-upkeep` 等模组修改世界规则。

**时间窗口**: 6-8 周

**依赖**: Phase 2 多人世界通过。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 3.1 | FoundationDB 持久化 | P0-1 §3.4/§6.3 | 每 tick 原子提交：`/tick/{N}/state` + `/tick/{N}/commands` + `/tick/{N}/rejections` + `/tick/{N}/metrics` |
| 3.2 | Dragonfly 热缓存 | P0-1 §4.2 | FDB 为权威源，Dragonfly 为读取加速；miss → FDB 回填；与 FDB 不一致时 FDB 为准 |
| 3.3 | ClickHouse 指标 | P0-1 §5 | `TickMetrics` 写入 ClickHouse；tick 级查询 `refund_abuse_rate`/`command_rejection_rate`/`tick_duration_p99` |
| 3.4 | 多房间 + 房间边界 | P0-1 §2, P0-5 §3 | 房间按 `[A-Z][0-9]+[NS][0-9]+[EW]` 命名；跨房间移动；可见性限制到当前房间 + 相邻房间 |
| 3.5 | Rhai 模组引擎 | P0-7 §1/§3/§5 | `init.rhai` / `tick_start.rhai` / `tick_end.rhai` 加载和执行；`actions.deduct_resource/award_resource/emit_event` 可用 |
| 3.6 | 模组安装 + 配置 | P0-7 §2 | `swarm mod install/remove/config` CLI；world.toml 中 `[[mods]]` 配置；`empire-upkeep` 作为首个官方模组 |
| 3.7 | 模组执行预算 | DESIGN §8.7 | AST 节点 10,000/tick；actions 100/tick；墙钟 100ms；连续 10 tick 超限自动禁用 |
| 3.8 | 全局存储 | DESIGN §8.4 | TransferToGlobal/TransferFromGlobal 进入 IDL；累进存储税启用；运输时间 10/5 tick；snapshot 中暴露 pending transfers |

### Phase 3 成功标准

- FDB 事务每 tick 成功提交，tick abandon rate = 0（在标准负载下）
- 安装 `empire-upkeep` 后，维护费计算公式正确，回放 1000 tick 通过
- 两个房间之间的 drone 移动、可见性切换、资源不互通均正确

---

## Phase 4: 教程世界 + 调试 + 回放查看器

**目标**: 新手（人类和 AI）可以在教程世界中完成 5 分钟引导。所有玩家可以回放自己的历史 tick、查看性能指标。

**时间窗口**: 4-6 周

**依赖**: Phase 3 持久化通过。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 4.1 | 教程世界 | P0-6 §2, P0-9 §2.4 | `world.mode = "tutorial"`；`tutorial_tick_interval_ms = 1000`；独立 namespace（`tutorial_{world_id}`） |
| 4.2 | 5 分钟引导 | P0-6 §2 | 6 个成就：(1)首次采集 (2)首次 spawn (3)首次建造 (4)首次资源瓶颈解释 (5)首次回放 (6)首次 Arena |
| 4.3 | Starter Bot 触发 | DESIGN §8.7 | 新玩家进入 Tutorial 世界时自动部署 starter bot；AI 玩家通过 `swarm://docs/tutorials/basic-agent` MCP resource 获得 starter |
| 4.4 | 回放查看器（自身） | P0-1 §6.3 | 选择任意历史 tick → 查看世界状态快照 + 指令执行结果 + 拒绝原因 |
| 4.5 | Tick 详细解释 | P0-6 §5 | `swarm_explain_last_tick` 返回结构化 JSON：每条指令的 status + rejection_reason + 位置/距离/资源/冷却等上下文 |
| 4.6 | 策略指标仪表盘 | P0-6 §6 | fuel 消耗/timeout 率/指令拒绝率/资源增长率，按玩家和 tick 范围聚合 |

---

## Phase 5: Web 客户端 + AI 玩家完整体验

**目标**: Web 客户端上线（Monaco 编辑器 + PixiJS 地图渲染）。人类和 AI 玩家都具备完整的开发→部署→观察→迭代循环。

**时间窗口**: 6-8 周

**依赖**: Phase 4 通过。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 5.1 | Web 客户端 | P0-6 §3.2 | React + Monaco 编辑器（TypeScript 自动补全） + PixiJS 地图渲染（WebGL tilemap） |
| 5.2 | IDE 集成 | P0-6 §3.2 | 行内校验："drone.harvest() 需要 WORK body part"；一键编译部署；版本历史 |
| 5.3 | OAuth2 登录 + 证书 | P0-3 §1.1, P0-9 §3 | GitHub/Google OAuth2 → Ed25519 证书签发 → 24h 自动续签；吊销支持 |
| 5.4 | API 参考站 | P0-8 | 从 IDL 自动生成的 API 文档站；人类可读 + 机器可读（MCP resource） |
| 5.5 | AI 玩家教程 | P0-3, P0-6 | `swarm://docs/` 下完整的 MCP resources 教程树；AI agent 可在 30 分钟内从零到成功部署 |
| 5.6 | 本地模拟 | P0-6 §3.3 | `swarm sim --ticks=5000 --speed=100x`；供玩家在本地快速迭代代码 |

---

## Phase 6: 战斗 + 市场 + Arena 模式

**目标**: PvP 战斗、玩家间市场交易、Arena 1v1 比赛制上线。

**时间窗口**: 8-10 周

**依赖**: Phase 5 通过；P0-9 World/Arena 差异明确。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 6.1 | Controller + 房间占领 | DESIGN §10 | Claim body part；Controller 升级（GCL）；房间归属切换 |
| 6.2 | 战斗系统 | P0-8 Attack/RangedAttack/Heal | 数值平衡（body part 伤害/治疗）；damage_multiplier 世界规则生效 |
| 6.3 | 运输拦截 | DESIGN §8.4 | 全局↔本地运输中的资源可被敌方巡逻 drone 拦截（PvP 世界启用） |
| 6.4 | 市场（玩家间交易） | DESIGN §8.4 | 全局存储中的资源可挂单；Terminal 建筑交易；MarketOrder 进入 snapshot |
| 6.5 | Arena 模式 | DESIGN §10, P0-9 §6 | 对称初始条件；赛前代码锁定；固定时长（5000 tick ≈ 4h）；赛后自动公开回放 |
| 6.6 | 排行榜 + 赛季 | DESIGN §10 | 按 league 分层；Elo/Glicko 评级；赛季遗产 bonus |
| 6.7 | AI 锦标赛 | P0-3, DESIGN §10 | 预提交制（WASM 赛前锁定）；AI 专用 MCP 竞赛界面 |

---

## Phase 7: 生产化

**目标**: 性能优化、反作弊、CI/CD、自动化测试，达到公测标准。

**时间窗口**: 8-12 周

**依赖**: Phase 6 通过。

### 交付物

| # | 交付物 | 锚定规范 | 验收标准 |
|---|--------|---------|---------|
| 7.1 | ECS 并行化 | — | `.before()/.after()` 替代部分 `.chain()`；并行那些不冲突的系统；保持确定性 |
| 7.2 | Sharding（多房间分布） | — | 不同房间分配到不同引擎进程；跨房间移动通过 FDB 事务协调 |
| 7.3 | 反作弊系统 | P0-1 §6.3, P0-5 | 回放审计；异常行为检测（fuel/rejection pattern）；注入检测 |
| 7.4 | CI/CD Pipeline | P0-8 §4 | IDL gen → lint → unit test → integration test → replay test → deploy |
| 7.5 | 负载测试 | — | 500 并发玩家 × 500 tick 稳定运行；p99 tick duration < 3s |
| 7.6 | Wasmtime 安全补丁 SLA | P0-4 §2.1 | CVE 响应 < 7 天；版本迁移脚本 |
