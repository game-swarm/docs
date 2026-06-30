# R44 Parliament Review — Cross-Cutting — GPT-5.5

Reviewer: rev-gpt-cross-cutting
Scope: Security, Performance, Operations, Edge Cases, Missing Specs
Verdict: REQUEST_MAJOR_CHANGES

本轮结论：文档整体已经形成了清晰的两层计算模型（COLLECT sandbox 并行、EXECUTE 权威确定性串行）和较完整的安全边界，但仍存在若干跨模块合同冲突与安全/运维空洞。最阻塞的是分片架构的目标状态互相矛盾、分布式 sandbox/NATS 信任边界不足、以及长期 replay/备份保留合同不闭合。这些问题会直接影响目标架构能否实现“可扩展、可审计、可安全运营”的承诺。

## §1 Critical Findings (blockers)

### C1 — Critical — 多 shard 架构存在互斥目标状态：静态多 Engine 分片 vs 单进程同 redb 汇总

文件引用：
- `/data/swarm/docs/design/architecture.md:29-46`
- `/data/swarm/docs/design/architecture.md:290-301`
- `/data/swarm/docs/specs/core/shard-protocol.md:6-18`
- `/data/swarm/docs/specs/core/shard-protocol.md:66-72`

问题描述：
`architecture.md` 将目标架构定义为“每 shard 一个 Engine 进程 + 一个 redb 文件”，并明确“无 cluster、无 leader election、无 gossip”，通过增加 Engine shards 水平扩容。`shard-protocol.md` 却同时声称“世界规模 >5,000 drone / 多节点部署”需要多世界分片协议，但在 §5 又定义“所有分片在同一进程内提交到同一个 .redb 文件，跨分片提交通过 Engine 调度层汇总后进入同一个 redb WriteTransaction”。这不是实现细节差异，而是权威性、故障域、提交原子性与扩展边界的根本冲突。

影响分析：
- 架构层无法判断 shard 是独立故障域还是单进程内逻辑分区。
- 跨 shard Move/Combat 的一致性协议无法确定是否需要网络协议、事务协调、重试/幂等、跨进程 replay merge。
- 运维层无法规划容量、备份、恢复和 shard migration：是每 shard 备份一个 redb，还是一个全局 redb。
- 性能声明会失真：如果所有 shard 汇总进同一个 Engine/redb，则多节点扩展承诺不成立；如果每 shard 独立 Engine，则 `shard-protocol.md` 的同 redb 原子提交不成立。

修复建议：
选择并写成唯一目标状态，不要两套并存：
- 方案 A：单进程 room-partition 是 shard 内优化，真正 multi-shard = 每 shard 独立 Engine + redb。跨 shard Move/Combat 通过确定性消息协议 + tick barrier/logic-clock 结算；replay 用每 shard hash chain + global anchor 合并。
- 方案 B：取消 multi-node shard 承诺，将 shard-protocol 改名为“room partition protocol”，明确它只在单 Engine 内工作，`architecture.md` 删除多 Engine shard 的水平扩容说法。

我建议方案 A，因为它与 `architecture.md` 的扩展模型、故障域和运行边界更一致。

### C2 — Critical — 分布式 Sandbox/NATS 信任边界缺少认证、完整性、reply correlation 与 replay 防护

文件引用：
- `/data/swarm/docs/specs/core/distributed-sandbox.md:46-64`
- `/data/swarm/docs/specs/core/distributed-sandbox.md:74-84`
- `/data/swarm/docs/specs/core/distributed-sandbox.md:86-124`
- `/data/swarm/docs/design/architecture.md:255-265`
- `/data/swarm/docs/design/architecture.md:278-286`

问题描述：
分布式 sandbox 使用 NATS request-reply 分发 `snapshot_json + module_hash + fuel_budget`，Sandbox 返回 `commands + metrics + status`。文档明确 NATS “不需要持久化”，并将 NATS 定位为非权威传输，但没有定义：
- NATS 连接认证与 subject ACL；
- Engine→Sandbox request envelope 的签名/MAC；
- Sandbox→Engine reply 的实例身份、签名/MAC、reply subject inbox；
- request_id / collect_id / deadline / nonce；
- 重放 reply、伪造 reply、跨 player reply、旧 tick reply 的拒绝规则；
- sandbox 实例注册、吊销、隔离后的重新信任流程。

影响分析：
Sandbox 本身非权威，但它的输出是进入 command validation 的唯一玩家命令来源。若 NATS 或 sandbox worker 被恶意实例加入/劫持：
- 可对目标玩家制造 deterministic no-op / timeout，形成定向 DoS；
- 可伪造“合法形状”的 commands，依赖 validation 拦截，但仍消耗执行/审计/限流预算；
- 可污染 metrics，使调度器错误缩容/扩容或误判玩家行为；
- 可读取 per-player snapshot，造成视野、资源、私有状态泄露；
- 可 replay 旧 tick reply，制造难以审计的跨 tick 行为。

修复建议：
为 Distributed Sandbox 增加独立安全合同：
1. NATS 层：NATS credentials 或 mTLS，subject ACL 最小化；sandbox 只能订阅 `swarm.tick.*` queue group 与模块分发主题，不能 publish 任意 tick/delta/admin subject。
2. Request envelope：`SandboxTickRequest` 增加 `request_id`, `collect_id`, `deadline_unix_ms`, `engine_instance_id`, `engine_signature/MAC`, `policy_version`。
3. Reply envelope：`SandboxTickReply` 增加 `request_id`, `sandbox_instance_id`, `compiled_artifact_hash`, `reply_signature/MAC`, `started_at/ended_at`, `status_code`。
4. Engine 只接受匹配当前 collect_id、deadline 内、未消费 request_id、来自 allowlisted sandbox identity 的 reply。
5. 将 forged/replayed/mismatched reply 作为 security event 写入 audit，而不是普通 timeout。

### C3 — Critical — 长期 replay / audit 保留合同不闭合：Blob 180d、Keyframe 30d、“redb 全量重建”语义冲突

文件引用：
- `/data/swarm/docs/specs/core/persistence-contract.md:21-27`
- `/data/swarm/docs/specs/core/persistence-contract.md:228-236`
- `/data/swarm/docs/specs/core/persistence-contract.md:249-265`
- `/data/swarm/docs/specs/core/persistence-contract.md:321-347`
- `/data/swarm/docs/RUNBOOK.md:106-139`

问题描述：
Persistence Contract 声称 Blob Store hot/warm/cold 保留到 180d，Keyframe Store hot 7d / cold 30d；Keyframe GC 删除 keyframe 时同步删除 snapshot delta chain。与此同时，Replay 恢复写道“若最近 keyframe 已被 GC，可从 redb 全量重建 world state”，但没有说明 redb 是否保存历史全量状态、历史 per-entity 版本，还是只保存当前 committed head。若 redb 只保存当前状态，则 30d 后旧 tick deterministic replay 无法从 180d blob 独立恢复；若 redb 保存历史全量，则与 redb 只写小对象/状态 head 的设计冲突。

影响分析：
- “180d cold replay artifacts”可能给出虚假的审计承诺。
- 竞技赛后争议、反作弊追溯、CVE 事后审计可能在 keyframe GC 后不可恢复。
- RUNBOOK 的 backup/restore 只复制 redb 或 keyframe 的描述不够，灾难恢复后可能丢失 replay 所需历史链。
- `terminal_state = audit_gap` / `unreplayable` 的分类无法可靠执行，因为保留策略本身没有保证 replay-critical chain 可用。

修复建议：
定义一套明确的 replay retention policy：
- 若目标是 deterministic replay 180d，则 keyframe + delta chain 的 replay-critical subset 至少也保留 180d，Blob/RichTrace 可单独降级。
- 若只保证 30d deterministic replay，则将 Blob 180d 明确改成“rich artifacts only, not deterministic replay”，并在 API/Runbook 中暴露 replay horizon。
- 明确 redb 是否保留历史 state versions；如果不保留，不得写“从 redb 全量重建目标 tick”。
- RUNBOOK 增加备份清单：redb、keyframes、delta chain、blob store、CA/CRL、world config、mods lock。

## §2 Design Tensions (inconsistencies, conflicts)

### T1 — High — Gateway 暴露面与 DNS rebinding 防护写法冲突，且 `/metrics` 默认无认证

文件引用：
- `/data/swarm/docs/specs/security/gateway-protocol.md:5-18`
- `/data/swarm/docs/specs/security/gateway-protocol.md:101-110`
- `/data/swarm/docs/specs/security/gateway-protocol.md:146-154`
- `/data/swarm/docs/specs/security/mcp-security.md:135-145`
- `/data/swarm/docs/specs/security/mcp-security.md:146-167`
- `/data/swarm/docs/RUNBOOK.md:52-63`

问题描述：
Gateway 被定义为所有 Browser/CLI/MCP 的唯一入口，但 DNS rebinding 防护表又写“Gateway bind 到 127.0.0.1 或 unix socket，不监听 0.0.0.0”。`mcp-security.md` 的拓扑图则显示 Internet→nginx→Browser/AI endpoint→MCP Server 127.0.0.1。两者缺少清晰分层：到底是 public Gateway 暴露，还是 nginx 暴露、Gateway 仅 loopback。此外，REST API 表将 `/metrics` 标为“可见性过滤：无”，RUNBOOK 直接 `curl localhost:8080/metrics`，没有定义 metrics 是否只能 loopback/admin scrape。

影响分析：
- 部署者可能把 Gateway 直接绑定公网，误以为文档已覆盖 DNS rebinding/Origin/CSRF。
- `/metrics` 可能泄露 player counts、tick health、sandbox crash rate、compile queue、security anomalies，形成攻击者容量探测面。
- Admin scrape、public healthz、gateway-internal metrics 三类端点混在一起，运维和安全边界不直观。

修复建议：
明确三层入口：
1. Public edge：nginx/HTTPS/WSS 监听公网，执行 TLS、Host、Origin、CORS、CSRF、body limit。
2. Gateway internal：只监听 loopback/unix socket，信任来自 edge 的 forwarded transport context，仍独立验证应用层证书。
3. Admin/metrics：单独端口或 path，默认 loopback + admin scope / Prometheus mTLS，不进入 public route table。

同时将 `/healthz` 分为 public liveness（不含敏感指标）与 authenticated readiness/metrics。

### T2 — High — Rate limit 权威位置与粒度分散，易导致 Gateway/Engine/IDL 三处分叉

文件引用：
- `/data/swarm/docs/specs/security/gateway-protocol.md:119-122`
- `/data/swarm/docs/specs/security/mcp-security.md:298-329`
- `/data/swarm/docs/specs/reference/api-registry.md:155-176`
- `/data/swarm/docs/specs/reference/api-registry.md:769-779`

问题描述：
Gateway Protocol 写 MCP 限流“50 MCP 请求/tick per player”；MCP Security 又列 deploy 10/hour、snapshot 1/tick、读类 50/tick、debug 30/tick、开发辅助 20/tick、全局连接/IP 限制；API Registry 只给 RateLimited 的错误码和 canonical signature 部分。文档多次说 Registry 是权威，但 rate-limit 的具体 token bucket、窗口、key、burst、跨 Gateway 汇总方式并未在 Registry 中形成机器可读单事实源。

影响分析：
- Gateway 无状态水平扩展时，per-player/tick 限流如果只在实例内执行，会被多连接绕过。
- Engine 与 Gateway 双方若都限流但 key/window 不同，会产生不可解释拒绝。
- AI/CLI SDK 无法从 IDL 得到准确 backoff 策略，错误处理不直观。

修复建议：
把每个 tool 的 `rate_limit`、`burst`、`scope_key`、`enforcement_point`、`retry_after_tick`、`global_budget_class` 写入 IDL/Registry；Gateway 只做粗粒度 connection/body/IP 防护，tool-level 权威限流由 Engine/Auth domain 基于 redb/Moka/tick cache 执行，或明确采用共享 rate-limit store。所有文档只引用 Registry。

### T3 — High — World seed / keyframe 的秘密分级与备份流程不闭合

文件引用：
- `/data/swarm/docs/specs/core/tick-protocol.md:277-340`
- `/data/swarm/docs/specs/security/visibility.md:166-173`
- `/data/swarm/docs/specs/core/persistence-contract.md:433-440`
- `/data/swarm/docs/RUNBOOK.md:67-75`

问题描述：
Tick Protocol 明确 World seed 运行时不公开，但每 epoch seed 会记录在 keyframe snapshot 中以支持 replay。Visibility 将 `world_seed/RNG state` 列为 Admin-only。Persistence 又要求 keyframe 独立存储在 `$REDB_PATH.keyframes/{tick}.snap`。RUNBOOK 对 world_seed 仅提供手动生成/更新命令，没有说明 keyframe 文件和备份介质属于 seed-bearing secret，也没有定义加密、访问审计、seed-bump 后旧 keyframe 的保护策略。

影响分析：
- 运维人员可能把 keyframe store 当作普通 replay artifact 对外分发，间接泄露 World seed。
- 一旦历史 keyframe 泄露，攻击者可根据文档推导后续 seed 链，影响未来 tick 排序/RNG，直到 seed-bump。
- seed-bump 的 runbook 与 keyframe backup/restore 不一致，恢复旧备份可能回滚到 compromised seed epoch。

修复建议：
将 keyframe 分为两类字段：replay-critical secret (`seed_epoch`, RNG state, private admin trace) 与 public/replay artifact。默认 keyframe at-rest 加密；备份/restore 必须携带 KMS/HSM policy；公开 replay 必须先 redaction。RUNBOOK 增加 seed leak 响应：隔离 keyframe backups、bump seed、标记 compromised epoch、禁止从 compromised backup 无审计恢复。

### T4 — Medium — WASM sandbox 资源上限在分布式与基线规范中不一致

文件引用：
- `/data/swarm/docs/specs/core/distributed-sandbox.md:181-184`
- `/data/swarm/docs/specs/core/wasm-sandbox.md:289-296`
- `/data/swarm/docs/specs/core/wasm-sandbox.md:336-350`
- `/data/swarm/docs/design/engine.md:501-512`

问题描述：
Distributed Sandbox 写容器 `memory.max = 256MB`、`cpu.max = 无硬限（WASM fuel 已限制计算量）`；WASM Sandbox baseline 写 cgroup `memory.max = 128MB`、`cpu.max = 250000 3000000`、资源总表内存总进程 128MB。Engine 又把 sandbox 生命周期与 worker pool 作为性能合同的一部分。三者对 memory/cpu 的权威值和理由不一致。

影响分析：
- 容量推导与 OOM/timeout 语义无法稳定复现。
- 运营商按不同文档部署会得到不同安全边界。
- “fuel 足以限制 CPU”不覆盖 host function、JIT/runtime bug、busy host calls、syscall 层异常等 wall-clock/CPU 消耗。

修复建议：
指定 `wasm-sandbox.md` 为资源安全权威，Distributed Sandbox 只引用；或者把本地/分布式 profile 差异写成表格。即使使用 fuel，也保留 cgroup CPU hard/soft quota 与 wall-clock deadline，避免单 worker 异常消耗宿主 CPU。

### T5 — Medium — Snapshot abuse 响应会改变游戏语义，且可能惩罚受害者

文件引用：
- `/data/swarm/docs/specs/core/tick-protocol.md:179-185`
- `/data/swarm/docs/design/engine.md:513-529`
- `/data/swarm/docs/specs/core/snapshot-contract.md:19-32`

问题描述：
Tick Protocol 的滥用检测写“玩家可见实体数连续 5 tick 超过 MAX_VISIBLE_ENTITIES → 标记玩家 visibility_abuse，降低其 COMBAT 优先级”。但 snapshot pressure 可能由敌对方堆叠实体制造，Engine 文档也承认“敌对方可通过堆叠实体增加受害方 snapshot 压力”。因此降低“该玩家”的 COMBAT 优先级既可能惩罚受害者，也把资源保护机制引入核心战斗排序语义。

影响分析：
- 攻击者可通过制造可见实体膨胀来降低受害者 combat priority，形成新的 DoS/战术漏洞。
- Command ordering 的公平性和 replay 解释变复杂：性能保护状态会影响战斗结果。
- “snapshot 可截断，不可伪造”的合同被“降低 COMBAT 优先级”污染。

修复建议：
删除语义性惩罚。资源保护应只作用于输出大小、查询预算、attacker cost、room/entity cap、density tax 或可见性截断。若需要识别实体膨胀攻击，应把成本归因到制造 pressure 的 source/owner，而不是 snapshot 接收者。

### T6 — Medium — Public spectator / player_view full / MCP 查询之间的信息公平边界不够直观

文件引用：
- `/data/swarm/docs/specs/security/visibility.md:125-139`
- `/data/swarm/docs/specs/security/visibility.md:299-349`
- `/data/swarm/docs/specs/security/mcp-security.md:35-40`

问题描述：
MCP Security 声称 MCP 与 Web UI 信息量等量，不更多也不更少。Visibility 又允许 `player_view = full` 使玩家屏幕/MCP 可见全地图，但 WASM snapshot 仍按 `is_visible_to`；同时 `fog_of_war=false` 可让 drone 感知全图。这里的“玩家屏幕 / MCP”到底包括哪些 MCP 工具并不够明确，容易误把 AI agent 的策略输入与人类 UI 的观战视角混同。

影响分析：
- AI agent 可能通过 MCP `swarm_get_snapshot` 看到比 WASM tick 更多的信息，从而在下一次部署/策略生成中获得人类同等但高于 drone 的“屏幕信息”。这或许是设计意图，但需要明确。
- 若 `player_view=full` 用于教学/合作世界，竞技/标准世界必须强制禁止，否则 fog-of-war 只限制 WASM 但不限制 AI 策略层。

修复建议：
把 MCP 工具分为 `drone_perception`、`player_screen_view`、`spectator_view` 三个 visibility class。标准 World 中 AI 策略可用的 MCP snapshot 应默认等于 human screen 还是 drone perception，需要明确。若允许 human/AI player screen full-map，则承认这是 mode-level 公平性变体，并在 world.toml validation 中禁止与 competitive/ladder 同时启用。

### T7 — Medium — 不安全 HTTP + TOFU 的可用边界与生产 WSS 强制要求存在张力

文件引用：
- `/data/swarm/docs/design/auth.md:215-218`
- `/data/swarm/docs/specs/security/mcp-security.md:115-121`
- `/data/swarm/docs/specs/security/gateway-protocol.md:146-154`

问题描述：
Auth 允许显式开启 HTTP，并通过 Server CA fingerprint pinning 保证身份；MCP Security 进一步写“HTTP 不安全传输可用于身份认证和完整性校验”。Gateway Security 又要求生产环境强制 WSS、禁止 ws://。三者可以兼容，但当前缺少 profile/环境条件：哪些端点允许 HTTP，首次 pinning 如何防 MITM，生产模式是否硬拒绝不安全传输。

影响分析：
- 部署者可能把 HTTP+TOFU 用在公网生产，首次连接被 MITM 后永久 pin 错 CA。
- Browser 与 Agent/CLI 的 transport 安全模型可能被混用。

修复建议：
定义 `transport_security_profile = production | lan | offline-dev`。production 强制 HTTPS/WSS + 应用层证书；lan/offline-dev 可 HTTP+manual fingerprint pin，但必须交互式确认 fingerprint，不允许 silent TOFU。配置校验应拒绝 public bind + insecure transport。

## §3 Suggestions (improvements, simplifications)

### S1 — Medium — 将“权威单事实源”进一步收敛到少数 machine-readable specs

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:1-14`
- `/data/swarm/docs/specs/reference/codegen.md:1-14`
- `/data/swarm/docs/design/interface.md:5-21`

建议：
API/IDL 的单事实源方向很好，但 rate limits、auth modes、visibility classes、transport labels、error detail levels 仍散落在 Gateway/MCP/Registry/IDL 多处。建议把这些全部机器化到 IDL：
- `auth_mode`
- `visibility_class`
- `rate_limit`
- `replay_class`
- `audit_class`
- `transport_allowed`
- `admin_required`

设计文档只解释原则，不重复数值。

### S2 — Medium — 为运维 Runbook 增加“恢复矩阵”，覆盖组件级丢失而非只覆盖 redb

文件引用：
- `/data/swarm/docs/RUNBOOK.md:106-151`
- `/data/swarm/docs/specs/core/persistence-contract.md:419-440`

建议：
Runbook 目前偏启动/备份命令，缺少按组件故障分类的恢复矩阵。建议新增：
- redb 丢失；
- keyframe store 丢失；
- blob store 丢失；
- CA 私钥泄露；
- CRL/Auth redb 损坏；
- NATS cluster 丢失；
- sandbox image 回滚；
- world_seed/keyframe 泄露；
- mods lock / action registry drift。

每项列出 RPO/RTO、是否影响 deterministic replay、是否需要公告/补偿、验证命令。

### S3 — Low — Gateway API path 命名不直观，疑似把文档路径泄漏进运行 API

文件引用：
- `/data/swarm/docs/specs/security/gateway-protocol.md:77-80`
- `/data/swarm/docs/specs/security/gateway-protocol.md:101-110`
- `/data/swarm/docs/specs/security/visibility.md:118-123`

建议：
`GET /specs/reference/v1/world/...` 看起来像文档路径，不像产品 API。建议改为 `/api/v1/world/...` 或 `/swarm/v1/world/...`；文档链接使用 Markdown 引用，不进入 runtime route。这样更符合接口直觉，减少 SDK/网关路由混淆。

### S4 — Low — 文档中仍残留“RFC/queued/后续”等非目标状态措辞

文件引用：
- `/data/swarm/docs/design/modes.md:150`
- `/data/swarm/docs/specs/reference/api-registry.md:250-258`
- `/data/swarm/docs/specs/core/wasm-sandbox.md:501-512`

建议：
项目原则强调“设计即目标状态”。少量文档仍出现 RFC-gated、queued、non-blocking 等措辞。若这些是正式 feature gate，应统一改成“inactive schema / feature-gated but specified”；若不是目标设计，应移出核心文档或放入明确的 extension registry，避免评审和实现误读成路线图占位。

## §4 Cross-Reference Matrix

| ID | Severity | Area | Primary Docs | Related Docs | Status |
|----|----------|------|--------------|--------------|--------|
| C1 | Critical | Sharding / Architecture | `design/architecture.md`, `specs/core/shard-protocol.md` | `persistence-contract.md`, `tick-protocol.md` | Must fix |
| C2 | Critical | Security / Sandbox / NATS | `specs/core/distributed-sandbox.md` | `design/architecture.md`, `wasm-sandbox.md`, `gateway-protocol.md` | Must fix |
| C3 | Critical | Persistence / Replay / Ops | `specs/core/persistence-contract.md` | `RUNBOOK.md`, `tick-protocol.md` | Must fix |
| T1 | High | Gateway / Deployment / Observability | `specs/security/gateway-protocol.md` | `mcp-security.md`, `RUNBOOK.md` | Must resolve before production spec freeze |
| T2 | High | API / Rate Limit / Authz | `mcp-security.md`, `api-registry.md` | `gateway-protocol.md`, IDL YAML files | Must consolidate |
| T3 | High | Seed Security / Backup | `tick-protocol.md`, `visibility.md` | `persistence-contract.md`, `RUNBOOK.md` | Must specify secret handling |
| T4 | Medium | Sandbox Resource Limits | `wasm-sandbox.md`, `distributed-sandbox.md` | `engine.md` | Needs single authority |
| T5 | Medium | Abuse / Gameplay Fairness | `tick-protocol.md` | `engine.md`, `snapshot-contract.md` | Needs semantic correction |
| T6 | Medium | Visibility / MCP Fairness | `visibility.md`, `mcp-security.md` | `gateway-protocol.md` | Needs class split |
| T7 | Medium | Transport Security | `auth.md`, `mcp-security.md` | `gateway-protocol.md` | Needs profile gates |
| S1 | Medium | Spec Layering | `api-registry.md`, `codegen.md` | `interface.md` | Improvement |
| S2 | Medium | Operations | `RUNBOOK.md` | `persistence-contract.md` | Improvement |
| S3 | Low | API Ergonomics | `gateway-protocol.md`, `visibility.md` | `mcp-tools.md` | Cleanup |
| S4 | Low | Documentation Consistency | multiple | `AGENTS.md` | Cleanup |

## 亮点

- 两层计算模型非常清晰：`design/architecture.md:13-25` 将 COLLECT 的水平扩展性与 EXECUTE 的确定性瓶颈分开，这是正确的核心抽象。
- WASM sandbox 基线深入到 Wasmtime config、WASI 禁用、seccomp clone flags、cgroup、host function budgets，安全深度明显高于普通设计文档。
- Deferred Command Model 与“WASM 只产生命令、不直接写世界”的边界清楚，降低了 sandbox 逃逸后的权威状态风险。
- Persistence Contract 对 replay-critical subset 与 RichTraceBlob 的分层思路正确，避免了对象存储双写失败影响 tick commit。
- Visibility 文档强调所有输出面统一 `is_visible_to`，并把 debug/replay/spectator 也纳入同一安全模型，这是很好的跨模块防泄漏原则。
- API Registry/IDL/codegen 的单事实源方向正确，适合作为后续收敛 auth/rate/visibility 机器合同的基础。

## CrossCheck

CX-1: `shard-protocol.md` 的跨 shard Move “0 tick 强一致 atomically transfer entity” 与多 Engine 架构可能不兼容 → 建议 Determinism/Simulation reviewer 检查跨 shard tick barrier、entity ownership transfer、logic-clock ordering 是否可 replay。

CX-2: `visibility.md` 中 `player_view=full` / `fog_of_war=false` 对 AI 策略公平性的影响超出纯安全范围 → 建议 Gameplay reviewer 检查标准 World、Tutorial、Arena、Co-op 的可见性模式是否符合设计目标。

CX-3: `engine.md` 的 1000 active players 容量推导依赖 p50 5ms、40 cores、dispatch overhead 500ms → 建议 Performance reviewer 用 benchmark gate 重新核对 p95/p99、NATS request-reply overhead、snapshot stitching、host function heavy workloads。

CX-4: `resource-ledger.md` 的 AlliedTransfer / new_player_transfer_lock 与跨 shard identity/nonce registry 交叉 → 建议 Economy reviewer 检查 transfer lock、alliance age、daily cap 在多 shard 下是否存在绕过。

CX-5: `api-registry.md` 中 RejectionReason 同时出现 validation `TargetNotVisible` 与安全合并码 `NotVisibleOrNotFound` → 建议 Security/API reviewer 检查哪些 endpoint/command 可以返回精确不可见，避免 oracle。

CX-6: `wasm-sandbox.md` 允许 deterministic SIMD subset opt-in，但跨架构验证只简略提及 → 建议 Determinism reviewer 检查 SIMD、integer overflow、Wasmtime version drift 对 replay hash 的影响。

CX-7: RUNBOOK 的 CA/epoch bump 与证书吊销策略可能需要更细粒度 UX/账号恢复流程 → 建议 Auth reviewer 检查用户设备丢失、email recovery、agent-generated key handoff 的完整闭环。
