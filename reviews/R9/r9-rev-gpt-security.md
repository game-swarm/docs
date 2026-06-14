# R9 终审 — rev-gpt-security

Reviewer: rev-gpt-security (Security)
Scope: /data/swarm/docs/design/DESIGN.md, /data/swarm/docs/design/tech-choices.md, /data/swarm/docs/specs/p0/
Date: 2026-06-14

## Verdict

REQUEST_MAJOR_CHANGES

总体设计已经解决了前几轮最危险的架构混淆：MCP 不再是 gameplay controller，AI 与人类都通过 WASM；Command Source Model 明确了服务端注入身份；统一可见性策略覆盖 WASM/MCP/WS/REST/replay；WASM 沙箱有 fuel、epoch、cgroup、seccomp、WASI 禁用和恶意样本测试。这些方向是正确的。

但终审仍不能直接 APPROVE：当前 P0-4/tech-choices 把 untrusted player code 的核心隔离边界建立在 `wasmtime = "=30.0"` 上，而公开资料显示 Wasmtime 29.0.0 至 36.0.5/40.0.3/41.0.1 之前版本存在 2026 年安全公告覆盖的问题；Bytecode Alliance 2026-04-09 公告还包含多项 Wasmtime 安全问题。对于“开放上传任意 WASM、每 tick 执行”的产品，这不是普通依赖升级问题，而是沙箱边界安全前提失效。因此需要先修正运行时版本策略与安全基线，才能冻结架构。

建议：修完 Critical + High 后可进入 APPROVE_WITH_RESERVATIONS；Medium 可作为 Phase 1/2 前置安全清单。

## Critical

### C-1: Wasmtime 固定到已知风险区间，直接承载不可信代码执行边界

位置:
- P0-4: `wasmtime = "=30.0"`，并声明“锁定版本 — 不自动升级”
- tech-choices: 选择 Wasmtime 作为玩家沙箱核心

问题:
Swarm 的最强安全假设是“玩家 WASM 不可信，但 Wasmtime + OS 隔离可控”。然而当前文档钉死 `=30.0`。Web 检索到的公开信息显示：
- NVD CVE-2026-24116 描述覆盖 Wasmtime 29.0.0 起、36.0.5/40.0.3/41.0.1 之前版本。
- Bytecode Alliance 2026-04-09 发布 Wasmtime security advisories，多项安全问题，其中公开摘要提到 sandbox escape 级别问题。

风险:
任意玩家上传 WASM 是核心功能。一旦 Wasmtime JIT/runtime 漏洞可触达，攻击面就是远程非认证/低门槛注册用户 → sandbox escape / host data leakage / engine compromise。P0-4 的 cgroup/seccomp 有帮助，但不能把已知漏洞运行时作为基线。

要求:
1. 不得在设计冻结时固定 `=30.0`。
2. 改为“当前受安全支持且已修复已知 advisories 的版本”，文档中写明最低安全版本，例如不低于公开 advisory 修复线：36.0.5 / 40.0.3 / 41.0.1 中选定一个受支持分支。
3. 增加 `cargo audit` + `cargo deny` + GitHub Security Advisory / Bytecode Alliance advisory watcher，Critical/High advisory 触发阻断发布。
4. 增加 emergency runtime bump 流程：沙箱 runtime 可在不改 Game API ABI 的情况下快速升级；升级后跑 replay determinism corpus + malicious wasm corpus。
5. 明确禁用或固定高风险 WASM proposals：memory64、component model、threads、relaxed SIMD、tail-call、exceptions 等按白名单开启，而不是默认跟随 Wasmtime 新版本能力。

Severity: Critical

## High

### H-1: Admin / Rollback 权限模型仍过宽，缺少强制双人授权和可执行策略

位置:
- P0-9: `Admin` 允许写世界、全局存储、部署代码、查询全局、触发战斗；rate_limit “无限制”
- P0-9: `Rollback` 写世界/全局存储/部署代码，审计为“双人审计”但未定义授权协议
- P0-5: admin 可见全量 tick trace、world_seed、RNG 状态

问题:
Admin 是全能 capability，Rollback 是世界状态写入 capability。文档只写“完整审计/双人审计”，但没有定义：谁能签、签什么、有效期、是否防重放、是否需要 break-glass reason、是否能绕过 source gate。

风险:
管理面 token 泄露或内部误操作可直接修改游戏状态、部署代码、回滚历史、读取隐藏策略信息。对于竞技或持久经济系统，这是最高价值攻击面。

要求:
1. Admin capability 拆分：read_audit、world_pause、player_ban、module_revoke、state_mutate、rollback 等最小权限。
2. Rollback 必须 2-of-N signed approval，签名内容包含 world_id、from_tick、to_tick、reason、expires_at、nonce、diff hash。
3. Admin 写操作必须有 rate limit / break-glass workflow，不应是“无限制”。
4. Admin 读取 world_seed/RNG 状态应单独 high-security scope，默认不可通过普通 admin token 读取。
5. 所有 Admin/Rollback 操作进入 append-only audit，并在世界公告/治理日志中可追溯。

Severity: High

### H-2: Rhai 规则模组供应链信任过强，缺少包签名、权限声明和安装隔离

位置:
- DESIGN §8.7: 模组市场、Rhai 模组源码、服主安装
- P0-7: RuleMod 可通过 actions 扣资源、奖励资源、伤害实体、设置 flag、emit event
- P0-9: RuleMod 来源允许 deduct/award/emit_event，rate limit 100 actions/tick

问题:
文档把 Rhai 定位为“服主信任”，但同时设计了模组市场、依赖、conflicts、版本安装。社区模组市场必然变成供应链攻击入口。当前缺少：包签名、发布者身份、依赖锁、权限 manifest、review 状态、升级策略、恶意模组回滚。

风险:
恶意或被接管的模组可在规则允许范围内系统性操纵经济、奖励资源、伤害实体，破坏世界完整性；如果 Rhai embedding 或 actions mini-validator 有 bug，还可能扩大到引擎层。

要求:
1. mod.toml 增加 capability manifest，例如 `resources:deduct`, `resources:award`, `entity:damage`, `flag:set`, `event:emit`，默认 deny。
2. 模组包必须签名；世界配置锁定 mod digest，而不仅是 name/version。
3. 模组依赖用 lockfile 固定 transitive dependencies，禁止隐式升级。
4. 安装/升级时展示 capability diff；新增高危 capability 需要显式确认。
5. RuleMod actions 进入与 WASM command 同等级的 audit/replay trace；每个 action 记录 mod_digest 与 callsite。

Severity: High

### H-3: path_find / get_objects 查询类 host function 存在放大型 DoS 面，需要算法预算而不只是调用次数

位置:
- P0-4 §8: `host_path_find` 10 calls/tick，`10,000 + 50/tile` fuel，响应 8KB；`get_objects_in_range` 5 calls/tick，响应 64KB
- P0-3: MCP `get_objects_in_range` 5/tick、`swarm_simulate` 5/tick

问题:
调用次数限制不足以约束服务端最坏情况开销。路径搜索和范围查询的真实成本取决于地图大小、障碍分布、可见实体密度、缓存命中率。攻击者可以构造“短输出、高搜索成本”的 path_find，例如不可达目标、迷宫、跨房间边界、最大搜索半径，导致服务端 CPU 远超 fuel 估算。

风险:
500 AI 玩家 × 10 path_find/tick 已是每 3 秒 5000 次潜在 A*；再叠加 MCP simulate/dry-run，最小请求可能触发最大服务器开销，拖慢 COLLECT 阶段并造成全局 tick timeout。

要求:
1. path_find 必须有 node expansion 上限、room boundary 上限、不可达快速失败策略。
2. fuel 成本按实际 expanded_nodes / heap operations 计费，而不是只按返回 tile 数计费。
3. 每玩家、每房间、全局三层 path budget；超过后返回 `PathBudgetExceeded`。
4. 对同 tick 同源/同目标路径做缓存；缓存 key 包含 terrain_version + dynamic_obstacle_version。
5. 恶意样本库加入 unreachable maze、dense obstacle、max range objects、simulate fanout 测试。

Severity: High

### H-4: MCP 无认证 docs/schema 端点“无限制”，与 HTTP max body/批处理防护不一致

位置:
- P0-3 §4.4: `swarm_get_schema` 无 scope、无限制；`swarm_get_docs` 无 scope、无限制
- P0-3 §5.1: 开发辅助工具 20/tick，但表内 docs/schema 又写无限制

问题:
同一文档中开发辅助限流相互矛盾。docs/schema 通常响应大、容易缓存，但如果动态生成或带 i18n/世界规则拼接，匿名无限制会成为低成本流量放大点。

风险:
匿名请求可打满 MCP/gateway 带宽或 CPU；也可枚举 API 版本、世界规则、模组信息，为攻击做 reconnaissance。

要求:
1. docs/schema 可匿名，但必须全局/IP rate limit + CDN/static cache + ETag。
2. 世界特定 rules/schema 需要 `swarm:read` 或只返回 public subset。
3. 统一 P0-3 表述：取消“无限制”，改为明确 per-IP/per-token 限制。

Severity: High

## Medium

### M-1: Tick 协议中 FDB commit 阶段表述仍有残留不一致

位置:
- DESIGN §3.2: FDB 原子提交在 EXECUTE 阶段
- P0-1 状态机图: BROADCAST 阶段第 2 步写 “FDB 原子提交”
- P0-1 §4.2: 又写 BROADCAST failure never rolls back committed tick，说明 tick 已在 EXECUTE 阶段持久化

问题:
这是文档一致性问题，但会影响实现者对原子边界的理解。

风险:
如果实现按状态机图把 commit 放到 BROADCAST，NATS/Dragonfly 失败语义会混乱，可能出现客户端看到未提交状态或 tick replay 缺口。

要求:
修正 P0-1 状态机图：BROADCAST 只能 read committed result / update cache / publish；FDB commit 只在 EXECUTE。

Severity: Medium

### M-2: ClickHouse audit “不可修改”表述不成立，缺少 WORM/哈希链

位置:
- P0-3 §7: `mcp_audit` MergeTree，写“不可修改，保留 90 天”
- DESIGN §6.3: ClickHouse 存 MCP 审计和 player events

问题:
ClickHouse MergeTree 不是不可修改介质。管理员或被入侵的写权限可以 ALTER/DELETE/MUTATE。仅写“不可修改”会给安全响应错误信心。

风险:
攻击者拿到管理面或 ClickHouse 凭据后可篡改 MCP/部署/调试调用痕迹。

要求:
1. 审计日志增加 hash chain：每条记录包含 prev_hash / record_hash。
2. 周期性 checkpoint 到对象存储 WORM bucket 或外部透明日志。
3. ClickHouse 权限只允许 insert/select，禁止 mutation；schema migration 单独 break-glass。
4. TickTrace 与 MCP audit 交叉引用 request_id/module_hash。

Severity: Medium

### M-3: Auth 设计中“服务端生成临时 Ed25519 密钥对”与客户端签名流程不清

位置:
- P0-3 §1.1: 证书包含 public_key，注释写“服务端生成的临时密钥对”
- P0-3 §1.1: 部署时“客户端附带证书 + 私钥签名(Blake3(WASM bytes))”

问题:
如果密钥对由服务端生成，私钥如何安全交给客户端？如果私钥留在服务端，客户端如何签名？如果通过 TLS 返回私钥，会扩大凭据泄露面。

风险:
实现者可能把 player signing private key 下发到浏览器/AI runtime 长期保存，增加 token/私钥双泄露风险；或误以为 issuer_sig 就等于客户端持有签名。

要求:
明确二选一：
1. 客户端生成 ephemeral keypair，服务端只签 public key；或
2. 不做客户端私钥签名，只用 OAuth/JWT + 服务端绑定 module_hash。

推荐客户端生成 keypair，证书短期有效，私钥不离开客户端；部署请求签名包含 module_hash、player_id、world_id、nonce、expires_at。

Severity: Medium

### M-4: Replay source “跳过 Source Gate”需要更严格的只读执行边界

位置:
- P0-9 §5: Replay 使用 `Replay` source，跳过 Source Gate 但保留完整 auth 信息
- P0-9 能力矩阵: Replay 只读

问题:
“跳过 Source Gate”容易被实现成特殊 bypass。Replay 应该走独立 replay executor，不能接触生产世界 write transaction，也不能复用可写 Command Validation Pipeline 的 apply path。

风险:
Replay 输入如果可由用户控制，可能通过边界错误写入当前世界，或通过 replay diff 泄漏 hidden state。

要求:
Replay source 只能在 snapshot copy / read-only transaction / detached world state 中执行；类型层面禁止拿到 production `WorldWrite` capability。

Severity: Medium

### M-5: JSON Schema “additionalProperties: false”写在顶层数组描述中，需确保 Command 变体也拒绝未知字段

位置:
- P0-2 §1.1: 顶层 array + additionalProperties false
- P0-8: Command IDL 生成 schema

问题:
顶层是 array，`additionalProperties` 对 array 本身没有意义。真正需要拒绝额外字段的是每个 Command variant 和嵌套 action object。

风险:
如果生成器没有对每个 command variant 设置 deny_unknown_fields，可能出现 mass assignment / confused deputy：客户端塞入 `player_id`、`source`、`admin`、`tick_target`、`refund_hint` 等字段，被某些路径误用。

要求:
IDL codegen 必须对所有 generated Rust structs 加 `deny_unknown_fields` 等价约束；JSON Schema 每个 object 都设置 `additionalProperties: false`。

Severity: Medium

## Informational

### I-1: MCP / Web UI 等量信息原则是正确的，但 `player_view = full` 对 MCP 的影响需标注为只读体验层

P0-5 已写关键不变量：WASM snapshot 始终按 `is_visible_to`，`player_view` 只影响人类屏幕和 MCP 只读查询。建议在 P0-3 MCP 工具表旁重复引用该不变量，防止实现者把 full view 误传给 WASM 或 simulate。

Severity: Informational

### I-2: seccomp syscall 白名单需要按平台实测生成

P0-4 的 syscall 列表方向正确，但 Wasmtime/Cranelift/glibc/musl 在不同 Linux 版本可能需要 rseq、prlimit64、sched_getaffinity、gettid 等。建议用 integration test 生成最小 allowlist，并把“新增 syscall 必须安全评审”写入 CI。

Severity: Informational

### I-3: rmcp 本身未检索到明确 CVE，但 MCP 协议栈仍应 vendor-pin + audit

检索未发现 rmcp 的公开 CVE 结果，主要资料是官方 rust-sdk / crates.io / docs.rs。但 rmcp 仍处于年轻生态，建议 pin exact version、cargo audit/deny、禁 JSON-RPC batch、限制 request body 和 tool name allowlist。P0-3 已覆盖 batch 禁用和 max body，方向正确。

Severity: Informational

## 终审结论

当前设计安全方向正确，但 C-1 是 release-blocking / architecture-freeze-blocking：不能以 `wasmtime = "=30.0"` 作为不可信代码执行基线。修复 Critical 后，若同时补齐 Admin/Rollback、RuleMod supply chain、path_find DoS、docs/schema 限流四项 High，本 reviewer 可接受进入下一轮 APPROVE_WITH_RESERVATIONS。
