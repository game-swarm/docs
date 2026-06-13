# Swarm 游戏引擎 — 扩展实现计划（AI + MCP + 文档 + 调试）

## Planner 输出（评审前草案）

> **注意**：本文档是 Planner 在评审议会之前的输出。MCP 的定位已在 P0-3 中修正——MCP 是 AI 的操作界面（查看世界、部署 WASM），不是游戏动作接口。McpPlayerExecutor 已移除，统一为 WasmSandboxExecutor。详见 `specs/p0/` 目录下的 P0 规范。

---

## 1. 概述

此计划在现有 Swarm 架构基础上，将 **AI 玩家作为一等公民**与人类 WASM 玩家并列，以 **MCP 作为原生 AI 集成层**。引擎内置 MCP server（rmcp crate），将游戏状态、文档作为 MCP 资源暴露——使 AI agent 无需人类帮助即可发现并参与游戏。

核心架构变更：
- SandboxExecutor trait 抽象为 PlayerExecutor，含 WasmSandboxExecutor + McpPlayerExecutor
- MCP server 是引擎一等子系统，非后期附加
- 数据模型新增 PlayerKind { Human, Ai { model, provider } }
- 调试/追踪原语从 Phase 1 开始，非 Phase 5
- Schema registry 生成文档，同时供给人类文档和 MCP 资源

## 2. 七阶段实现计划

### Phase 1: 基础加固 + MCP 脚手架
- 1.1 新增 PlayerKind（Human/Ai）和 AiSession ECS 组件
- 1.2 引入 rmcp 依赖，搭建 MCP server 模块含 swarm_ping 工具，以 Tokio 任务嵌入 main.rs
- 1.3 扩展 GameConfig 增加 MCP 配置（mcp_enabled, mcp_bind_addr, max_ai_players）
- 1.4 定义调试/追踪数据模型：TickTrace、EntityEvent、TraceCollector（环形缓冲 + ClickHouse schema）
- 1.5 新增文档生成管线：SchemaRegistry，通过 `cargo run -- schema` 暴露
- 1.6 重命名 SandboxExecutor → PlayerExecutor，添加 player_kind() 方法，新增 McpPlayerExecutor stub

### Phase 2: MCP Server — 游戏状态与工具（AI 玩家 MVP）
- 2.1 实现 MCP 工具 swarm_get_snapshot — 返回每玩家可见世界状态
- 2.2 实现全部游戏动作 MCP 工具（11 个工具，镜像 Command 枚举）
- 2.3 实现 API 文档的 MCP 资源：swarm://schema/*, swarm://docs/*
- 2.4 实现 MCP 认证和每玩家隔离
- 2.5 实现 McpPlayerExecutor tick 集成
- 2.6 AI 玩家生命周期管理，通过 gateway REST

### Phase 3: 多人世界 + 持久化
- 3.1 Tick 调度器支持混合玩家类型（WASM + MCP 执行器并行）
- 3.2 指令冲突解决——确定性排序
- 3.3 FoundationDB 持久化
- 3.4 Dragonfly 热缓存
- 3.5 ClickHouse 指标管线
- 3.6 WebSocket 实时增量推送
- 3.7 房间边界 + 多房间

### Phase 4: 调试基础设施
- 4.1 每 tick 日志，MCP 可访问回放
- 4.2 状态检查工具（swarm_inspect_entity, swarm_inspect_room）
- 4.3 WASM 执行追踪
- 4.4 每玩家性能分析
- 4.5 可视化调试叠加层（前端）

### Phase 5: 客户端 + 文档
- 5.1 Web 客户端 — Monaco Editor + PixiJS
- 5.2 自动生成 API 参考站
- 5.3 TypeDoc + Rustdoc CI 构建
- 5.4 MCP 可访问文档更新
- 5.5 OAuth2 登录 + 玩家档案

### Phase 6: 游戏系统
- 6.1 Controller + 房间占领
- 6.2 战斗系统
- 6.3 市场系统
- 6.4 排行榜 + 赛季

### Phase 7: 生产化 + AI 锦标赛模式
- 7.1 AI 锦标赛编排
- 7.2 性能优化——分片 + ECS 并行化
- 7.3 反作弊系统（含 AI 专项滥用检测）
- 7.4 MCP server 生产加固
- 7.5 CI/CD + 自动化测试

## 3. 已识别的关键风险
- MCP 协议变动 → 锁定 rmcp 版本，通过适配器抽象
- AI 玩家延迟 → 基于推送的异步快照交付，指令队列
- MCP 工具数量膨胀 → proc macro 代码生成
- AI vs 人类公平性 → 相同指令限制，同等校验
- 通过游戏状态的 prompt 注入 → 过滤所有玩家原创字符串
- Schema/文档漂移 → CI 强制检查
- 调试开销 → 采样

## 4. 待解决问题
- Q1: 引擎作为 MCP server、client，还是两者？→ 双向混合
- Q2: AI 玩家需要 WASM 吗？→ 不需要，仅 MCP
- Q3: AI 会话持久化吗？→ 是，存 FoundationDB
- Q4: MCP 内嵌还是独立 sidecar？→ MVP 阶段内嵌，后续分离
- Q5: stdio 还是 HTTP/SSE？→ 仅 HTTP/SSE（AI 玩家是远程的）
- Q6: Schema 在 engine crate 还是独立 crate？→ 独立 swarm-schema crate
- Q7: AI 玩家质量指标？→ 基于指标评估

## 5. 代码库参考
- Engine: /data/swarm/engine/ — Phase 1 代码已有（ECS 组件、系统、tick 框架、游戏 API 类型）
- 设计文档: /data/swarm/docs/design/DESIGN.md — 原始架构
- SDK: /data/swarm/sdk-ts/, /data/swarm/sdk-rust/
- Gateway: /data/swarm/gateway/
- Frontend: /data/swarm/frontend/
- Sandbox: /data/swarm/sandbox/
