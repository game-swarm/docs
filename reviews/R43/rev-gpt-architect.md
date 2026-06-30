# R43 rev-gpt-architect 独立评审

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：整体架构方向（COLLECT/EXECUTE 分层、per-shard 单 writer、redb 权威提交、应用层证书）是清晰且匹配项目目标的，但当前文档在 Gateway 实现边界、Transport/Audience 标签、Deploy 激活语义、Mod 生命周期、Auth CA 签发职责、TickCommitRecord/WAL 语义等核心接口上存在多处互相冲突。它们不是文字润色问题，而会直接导致实现团队在组件职责、API 接入、回放/审计、部署链路上做出不同解释，因此需要重大修改后再进入下一轮。

## 2. 发现的问题

### A-H1 — Gateway 技术栈与组件边界自相矛盾

- severity: High
- 文件引用：
  - `/data/swarm/docs/design/README.md:84-89`
  - `/data/swarm/docs/design/architecture.md:59-63`
  - `/data/swarm/docs/specs/security/gateway-protocol.md:10-17`
- 问题描述：设计总览和 architecture 明确 Gateway 是 Rust / axum 风格组件；gateway-protocol 的架构图却写成 `Gateway (Go, 无状态)`。同一边界组件的语言、运行时和技术栈不一致。
- 影响分析：Gateway 是 Auth、MCP、REST、WebSocket、NATS 路由的统一入口。语言/技术栈不一致会影响：TLS/HTTP 框架选择、应用层证书验证库、NATS client、MCP JSON-RPC 处理、部署和运维模型。更重要的是，这会破坏 design/tech-choices 的“Rust Gateway”假设，使接口实现者无法判断哪份文档为准。
- 修复建议：统一 Gateway 技术栈为一个权威选择，并在 `design/architecture.md`、`design/README.md`、`specs/security/gateway-protocol.md`、`specs/security/mcp-security.md` 中同步。若选择 Rust，应将 gateway-protocol 图中的 `Go` 改为 `Rust (axum)` 或等价表达，并删除任何暗示 Go 实现的表述。

### A-H2 — Transport / audience 标签在 API Registry、Command Source、Gateway Protocol 之间不一致

- severity: High
- 文件引用：
  - `/data/swarm/docs/specs/reference/api-registry.md:815-822`
  - `/data/swarm/docs/specs/security/command-source.md:186-204`
  - `/data/swarm/docs/specs/security/gateway-protocol.md:21-31`
  - `/data/swarm/docs/specs/security/gateway-protocol.md:156-166`
  - `/data/swarm/docs/specs/security/mcp-security.md:115-133`
- 问题描述：同一 transport 概念存在多套标签：API Registry 定义 `agent-mcp` / `cli-rest` / `wasm-sdk`；Command Source 定义 `agent-mcp` / `agent-ws` / `spectator-ws` / `browser-http` / `cli-rest` / `replay-viewer`；Gateway Protocol 的 transport 表使用 Browser/REST/Agent/Replay Viewer，而认证矩阵又使用 `X-Swarm-Transport: ws/rest/mcp/replay`。这些值无法一一对应。
- 影响分析：audience 是应用层证书防跨协议重放的核心字段；`X-Swarm-Transport` 又是 Gateway 判定入口的硬门槛。标签不一致会导致合法请求被拒、非法跨 transport 重放被接受，或不同实现各自映射。API 直觉性也很差：用户和 SDK 生成器无法判断该填 `agent-mcp` 还是 `mcp`、`cli-rest` 还是 `rest`、`agent-ws` 还是 `ws`。
- 修复建议：建立唯一的 Transport Label Registry，推荐放在 `specs/reference/api-registry.md` 或 `specs/security/gateway-protocol.md` 的单一权威表中。所有文档只引用这些 canonical label。至少统一以下维度：HTTP header 值、certificate audience transport segment、DeployPayload audience、WebSocket handshake transport、公开 replay/spectator label。不要在 Gateway Protocol 中重新发明 `ws/rest/mcp/replay` 简写。

### A-H3 — Deploy 激活是否依赖 object-store upload 完成存在直接冲突

- severity: High
- 文件引用：
  - `/data/swarm/docs/specs/core/tick-protocol.md:923-935`
  - `/data/swarm/docs/specs/core/persistence-contract.md:72-127`
  - `/data/swarm/docs/specs/reference/api-registry.md:872-895`
- 问题描述：tick-protocol §9.2 规定：tick N+1 若 `upload_status == "complete"` 才加载新模块，否则保持旧模块且 deploy 进入 FAILED。persistence-contract §2.3 则规定：原始 wasm blob upload pending 不阻塞激活；只要 redb manifest 与预编译 artifact 完整即可 ACTIVE，blob 缺失只产生 audit gap。API Registry §11 又说 deploy manifest 同步提交并下一 tick 激活，但没有清晰裁定 blob upload 对 activation 的约束。
- 影响分析：这是 Deploy 状态机的核心合同。若实现按 tick-protocol，会把对象存储可用性放进激活关键路径；若按 persistence-contract，会允许 blob pending/failed 时激活。两者对玩家体验、审计语义、失败重试、replay verifier 都不同。该冲突会导致 deploy 状态机不可实现为单一确定性协议。
- 修复建议：裁定一个目标状态，并删除另一套语义。架构上更一致的方案是：redb manifest + compiled artifact 为激活必要条件，原始 WASM blob 为审计对象，不阻塞激活；即保留 persistence-contract 的分层语义。随后将 tick-protocol §9.2 改为“compiled artifact ready → activate；blob upload pending/failed → audit gap，不 FAILED deploy”，并同步 API Registry 的 Deploy Flow 字段。

### A-H4 — Mod 生命周期同时声称“静态编译”与“下一 tick 升级/禁用”，抽象层级不闭合

- severity: High
- 文件引用：
  - `/data/swarm/docs/design/README.md:162-163`
  - `/data/swarm/docs/design/engine.md:13-24`
  - `/data/swarm/docs/design/engine.md:68-79`
  - `/data/swarm/docs/design/tech-choices.md:48-87`
- 问题描述：文档明确 Mod 是 Bevy Plugin，静态编译进 Engine，启用依赖 Cargo features 和单 binary 构建；但 engine.md 的升级表又说 `swarm mod upgrade` 下一 tick 新版本生效、`disable` 后 tick 不再调用 Plugin。这两种模型不兼容：静态编译插件无法在不重启/不重建调度 manifest 的情况下于下一 tick 任意升级或禁用。
- 影响分析：Mod 是扩展机制的核心抽象。当前写法混合了“运行时插件管理”和“编译时 feature 选择”两种模式，导致 world.toml、mods_lock_hash、system_manifest_hash、ActionRegistry、replay 边界都不清楚。尤其是 Phase 2b manifest 进入 TickTrace 后，下一 tick 动态启停 Plugin 会改变 system set/hash，需要明确 restart boundary 或 hot-swap manifest 机制。
- 修复建议：二选一并写成唯一模型。若坚持 Bevy Plugin 静态编译，`swarm mod upgrade/disable` 应表示“修改 world/mod lock，触发 Engine rebuild/restart，在明确 tick boundary 切换整个 binary + manifest hash”，不能写成普通下一 tick 热更新。若要下一 tick热插拔，则需要改为动态插件/脚本/wasm module 机制，并重新定义安全、确定性和调度合同。

### A-H5 — Auth Service 的 CA 签发职责与“不得持有 Server CA 私钥”冲突

- severity: High
- 文件引用：
  - `/data/swarm/docs/design/auth.md:38-87`
  - `/data/swarm/docs/design/auth.md:90-97`
  - `/data/swarm/docs/design/auth.md:100-125`
- 问题描述：Auth 架构图和文字显示 Auth Service / Certificate Sessions 负责 `ClientAuth/CodeSign 签发`；职责表却写 Auth Service 不持有 Server CA 私钥，Engine/Gateway 也不持有。文档没有定义真正的 CA signer 组件、HSM/secret manager 边界或 operator-held signing API。
- 影响分析：证书签发是认证控制面的核心写操作。若 Auth Service 不持有 CA 私钥，必须有独立签名者；若它持有，职责表应承认并定义密钥保护。当前空洞会导致实现者把 CA 私钥放在任意位置，破坏“应用层证书”为身份根的安全边界。
- 修复建议：新增明确的 `CA Signer`/`Key Custody` 子组件：例如 Auth Service 调用本机 HSM/secret manager 中的 Server CA key，Auth Service 不直接导出私钥但拥有签名能力；或声明 Auth Service 持有加密私钥并定义解锁、轮换、审计。职责表应区分“持有私钥材料”与“拥有签名能力”。

### A-M1 — TickCommitRecord 同事务失败语义与 WAL 兜底语义冲突

- severity: Medium
- 文件引用：
  - `/data/swarm/docs/specs/core/tick-protocol.md:717-737`
  - `/data/swarm/docs/specs/core/tick-protocol.md:953-985`
  - `/data/swarm/docs/specs/core/persistence-contract.md:30-62`
- 问题描述：tick-protocol 多处强调 TickCommitRecord 与世界状态同一 redb WriteTransaction，写入失败则 tick 放弃，不存在“状态已变但无审计记录”；但 §6.3.4 又写第 3 次失败后写入本地 WAL，且 WAL 恢复“不阻塞 tick 执行”。这与“同事务不可降级、失败即 abandon”的权威语义冲突。
- 影响分析：审计完整性是 replay 和反作弊的基础。如果 WAL 是 redb 同事务失败后的异步兜底，并且 tick 继续推进，就重新引入“状态与审计最终一致”的双写问题；如果 tick 已放弃，则 WAL 中记录的是什么也不清楚。该不一致会影响 crash recovery、hash chain、terminal_state 判断。
- 修复建议：明确 WAL 只记录未提交 attempt 的诊断/恢复日志，不能代替 TickCommitRecord，也不能允许 tick 在 redb critical commit 失败后继续推进。删除“WAL 恢复不阻塞 tick 执行”或改写为“不阻塞后续人工审计恢复；游戏 tick 已 abandon”。

### A-M2 — Phase 2b manifest 编号与“31 systems”表达不直观，易误导实现

- severity: Medium
- 文件引用：
  - `/data/swarm/docs/specs/core/phase2b-system-manifest.md:20-87`
  - `/data/swarm/docs/specs/core/phase2b-system-manifest.md:167-168`
  - `/data/swarm/docs/design/engine.md:289-323`
- 问题描述：manifest 声称 “S07–S31”，但实际列表结束于 S29，并通过 S22a/S22b 插入补足 31 个 system。engine.md 又以“Phase 2a inline 6 + Phase 2b deferred 25”解释。虽然数学上可凑成 31，但编号和命名不连续，且 S22a/S22b 既算 system 又不像普通 S 编号。
- 影响分析：manifest hash、CI system 注册校验、R/W matrix 和实现中的 system_id 需要稳定、可枚举、可直觉检查。非连续编号会让实现者误以为缺失 S30/S31，或在代码中采用另一套连续编号，导致 manifest hash 和文档不一致。
- 修复建议：将全部 31 个 system 改为连续稳定 ID（例如 S01–S31），或明确 system_id 与 display order 的机器可读表，避免 S22a/S22b 这种后插式编号。若保持插入编号，必须删除 “S07–S31” 表述，改为“Phase 2b deferred systems: S07–S29 plus S22a/S22b”。

### A-M3 — `player_view=full` 在不同章节中既被允许又被 competitive world 禁止，配置层次需要更清晰

- severity: Medium
- 文件引用：
  - `/data/swarm/docs/specs/security/visibility.md:125-139`
  - `/data/swarm/docs/specs/security/visibility.md:311-349`
  - `/data/swarm/docs/specs/security/visibility.md:363-376`
- 问题描述：visibility §3.5 和 §9 描述 `player_view="full"` 可让玩家/MCP 全地图可见；§10.1 又规定 competitive world 中 `fog_of_war=true && player_view=full` 被拒绝。最终规则可以成立，但当前文档先给出广义能力，再在后文补充禁止组合，读者容易误以为 MCP 在 World 中也可能全图。
- 影响分析：这是接口直觉性问题。MCP 与 WASM 等量信息是项目核心原则之一；若玩家视野、MCP 查询、spectator、drone snapshot 的层级不够突出，实现者可能在查询面开放 `full` 而造成信息泄露。
- 修复建议：在 `player_view` 定义处直接拆分“competitive allowed values”和“non-competitive allowed values”，并在表格中标注 `full` 仅 tutorial/coop/sandbox 可用。把 §10.1 的 oracle 防线前移为配置定义的一部分。

### A-L1 — 文档仍包含变更记录、日期和“旧/当前设计”叙述，违反目标状态文档风格

- severity: Low
- 文件引用：
  - `/data/swarm/docs/specs/reference/api-registry.md:964-975`
  - `/data/swarm/docs/specs/core/phase2b-system-manifest.md:511-517`
  - `/data/swarm/docs/design/auth.md:221-229`
  - `/data/swarm/docs/design/tech-choices.md:200-209`
- 问题描述：多个目标规范文档仍保留版本变更记录、日期、Rxx 修复来源、“旧设计/当前设计”“已移除组件”等历史叙述。AGENTS.md 明确要求设计/spec/reference 读起来像目标状态规格，不做历史日志。
- 影响分析：这不会直接破坏架构运行，但会污染 clean-slate 评审语境，让读者把文档当迁移记录而非目标规格；也会让“当前/旧版/已移除”这类词成为潜在不一致源。
- 修复建议：将 changelog、历史差异、Rxx 修复说明移出目标规格正文，必要时由 git history 或 reviews/ROADMAP 承载。正文只保留最终目标状态。

## 3. 亮点

- COLLECT 与 EXECUTE 的两层计算模型非常清晰：`design/architecture.md:13-26` 把并行 WASM 执行与串行权威世界模拟分开，直接对应扩展策略与瓶颈位置，避免把所有组件过度分布式化。
- per-shard 单 Engine + redb 单 writer 的边界合理：`design/architecture.md:29-47` 与 `design/architecture.md:206-219` 明确 redb 不是分布式事务系统，而是 shard 内权威提交点，抽象层次克制。
- Action dispatch 与 Phase 2b 状态推进的职责拆分较好：`design/engine.md:325-337` 和 `phase2b-system-manifest.md:88-94` 将 combat intent、status intent、HP 写入、StatusState writer 分层，避免 action handler 随意写世界状态。
- 可见性统一函数是正确的安全抽象：`visibility.md:5-14` 明确所有输出面走 `is_visible_to`，并在 host function、MCP、WS、REST、replay 中展开，接口边界直观。
- API Registry 作为 canonical schema authority 的意图明确：`api-registry.md:1-16` 把 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制统一到单一事实源，方向正确。
- 应用层证书而非 TLS client certificate 作为身份根的设计与自托管/AI agent 场景匹配：`auth.md:23-35` 的用途隔离、CSR、PoW、单层 CA 等原则总体一致。
- redb replay-critical subset 与 RichTraceBlob 分层是好的抽象：`persistence-contract.md:30-62` 将 deterministic replay 和 rich debug replay 分离，避免把对象存储可靠性放进核心正确性路径。

## 4. CrossCheck — 需要跨方向检查

- CX1: Transport label 不一致同时影响安全验证与 SDK codegen → 建议 安全方向 检查 audience/header/签名验证是否存在跨协议重放缺口。
- CX2: Deploy 激活与 object-store upload 冲突可能影响 replay/audit 结论 → 建议 确定性/持久化方向 检查 deploy_mutation、redb_version_counter、compiled_artifact_hash、blob audit gap 的完整状态机。
- CX3: Mod 静态编译与下一 tick 升级冲突会改变 system_manifest_hash → 建议 引擎方向 检查 Bevy Plugin 装载、world_action_manifest_hash、mods_lock_hash、Phase 2b manifest hash 的切换边界。
- CX4: Auth Service 不持有 CA 私钥但负责签发证书 → 建议 安全方向 检查 Server CA key custody、HSM/secret manager、签名 API、epoch bump 和 CRL 策略。
- CX5: `player_view=full` 与 MCP 等量视野原则的组合规则不够前置 → 建议 信息安全/游戏公平方向 检查 competitive world 下所有 query/debug/simulate/explain 接口是否无法形成 oracle。
- CX6: 文档中保留日期、版本变更、旧设计对照 → 建议 文档治理方向 检查 design/spec/reference 是否整体符合“目标状态，非历史追踪”的仓库规范。
