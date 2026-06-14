# R10 — rev-gpt-security 安全评审

Reviewer: rev-gpt-security (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/*.md`
Perspective: 已知漏洞模式匹配、API 滥用检测、供应链风险、DoS 放大面

## Verdict

REQUEST_MAJOR_CHANGES

R10 结论：设计已经显著修正了前轮最危险的 MCP-as-game-controller 误区：P0-3/P0-9 明确 MCP 不提交 gameplay command，AI 与人类都只能通过 WASM 进入世界；WASM sandbox 也有较完整的 fuel、cgroup、seccomp、WASI 禁用、module validation 与 CVE SLA 基线。这些方向是正确的。

但 Phase 0 仍不应冻结。当前文档里还有若干安全边界在文字层面成立、实现契约层面不够可测试，尤其是：MCP/Web/API 的 IDOR 与 debug 信息泄漏、compile/simulate/docs/query 类工具的 DoS 放大、RuleMod/Rhai 的中间信任层越权、认证/证书/签名模型自相矛盾、以及 sandbox 细节中存在可能误实现的 seccomp/Wasmtime API/生命周期假设。建议修订 P0 spec 后再进入实现。

---

## Critical

无 Critical。

未发现“按当前设计必然导致远程任意 gameplay 控制 / sandbox 直接逃逸 / 全局状态未授权写入”的单点灾难。最接近 Critical 的风险是 RuleMod 与 Admin/Rollback 能力模型，但它们目前属于高危设计缺口，而不是已确定的不可接受架构。

---

## High

### H1. MCP debug / replay / inspect 工具的 IDOR 合同不够硬，容易重演“调试接口变成越权读取”漏洞

位置：P0-3 §4.3、§6，P0-5 visibility policy，P0-9 source model。

问题：
- `swarm_inspect_entity` 写的是“检查自身实体的完整组件数据”，但工具参数、服务端授权检查、对象归属检查、联盟/共享视野规则没有在 schema 层冻结。
- `swarm_get_replay` 写的是“自身 tick 范围回放数据”，但 replay trace 通常包含完整 auth context、rejection detail、位置、目标 ID、资源变化；如果 trace 存储的是全量，再靠接口层过滤，IDOR 风险很高。
- `swarm_explain_last_tick` 可能把敌方动作、不可见实体、资源竞争原因、路径/距离 detail 泄露给玩家。P0-2 §5 的 rejection detail 包含精确位置、距离和阈值；若直接进入 debug/replay，可能绕过 fog-of-war。

攻击模式：典型 IDOR：`inspect_entity(object_id=enemy_id)`、`get_replay(player_id=other)`、`explain_last_tick(room_id=contested)`。如果只检查 token 有 `swarm:debug` scope，而未绑定 subject/object/world/visibility，就泄漏战争迷雾、敌方策略与模块行为。

建议：
- 每个 MCP/Web REST 工具都写明 authz predicate，例如：
  - `entity.owner == caller.player_id OR entity in visible_set(caller, tick)`；
  - `replay.subject_player == caller.player_id`；
  - admin-only 必须显式 `swarm:admin` 且不可由普通 OAuth 流程签发。
- TickTrace 存储可以全量，但对玩家查询必须走 redaction pipeline；不要让工具直接读 ClickHouse/FDB 原始 trace。
- 将 P0-3 工具表扩展为 `params / scope / subject binding / visibility filter / redaction policy / rate limit` 六列。
- 为每个工具增加 IDOR 测试：同世界其他玩家、不可见实体、历史 tick、arena/public replay、tutorial namespace。

Severity: High

### H2. Compile / validate / simulate 是当前最大 DoS 放大面，限流粒度与成本模型不足

位置：P0-3 §4.4/§5，P0-4 §7，P0-9 source matrix。

问题：
- `swarm_validate_module` 在 P0-3 同时出现为 10/h 和 P0-3 §4.4 “开发辅助工具 20/tick”；P0-9 又写 `DryRun 20/h`、`Deploy 1/tick`。这些数字不一致，会导致实现者选择较宽松限制。
- `swarm_simulate` 为 5/tick，budget 为 `0.5× MAX_FUEL`。500 AI 玩家时理论上每 tick 可产生 500 * 5 * 5M fuel 的离线仿真负载，远大于正常 tick 执行负载。
- `swarm_get_docs`/`swarm_get_schema` 无 scope、无限制；如果动态生成、压缩、含大文档，容易成为廉价 bandwidth/CPU 放大器。
- 编译阶段只写“并发编译最多 5 个”，但缺少 per-player queue、per-IP、per-world、全局 backpressure、重复 hash 去重、失败缓存、module validation 解析成本上限与压缩包/超大 base64 拒绝策略。

攻击模式：最小请求触发最大服务端开销：反复提交接近 5MB 的畸形 WASM、构造 Cranelift worst-case 编译、刷 `simulate` 预测 N tick、刷 docs/schema 走动态渲染。

建议：
- 统一 P0-3/P0-4/P0-9 的限制表，明确“最严格值生效”。
- `validate_module` 与 `deploy` 先按 content hash 做去重和 negative cache；同一坏 hash 在 TTL 内 O(1) 拒绝。
- `simulate` 增加硬约束：最大未来 tick 数、最大 snapshot size、每玩家/世界/全局 CPU token bucket、队列长度、超时、结果大小；Arena 更严。
- docs/schema 必须静态缓存、ETag、全局限流；“无 scope”不等于“无限资源”。
- 建立资源预算不变量：所有辅助工具总 CPU 不得超过正常 tick budget 的固定比例，例如 20%。

Severity: High

### H3. RuleMod/Rhai 信任边界不足，可能成为 bypass Command Validation Pipeline 的“第二套游戏引擎”

位置：P0-7 world rules engine，P0-9 `RuleMod` source。

问题：
- P0-7 写“规则 System 可以修改 ECS 资源/组件”，又写“绝不可绕过 Command 校验管线”。这两句存在张力：只要 Rhai/规则系统能直接改组件，就天然可能绕过 Command Validation。
- P0-9 允许 `RuleMod` “deduct/award/emit_event”，但 P0-7 的示例 `memory_upkeep_system`、`code_propagation_system` 直接操作资源和 CodeVersion，能力边界更宽。
- `RuleMod` 的来源是 `mod_id + world_owner_id`，但缺少安装/升级权限、签名、审核、版本锁定、回滚、依赖权限声明、per-mod op budget、storage namespace、对其他玩家数据的读写限制。

攻击模式：恶意或被盗 world owner 安装 Rhai mod，悄悄给特定玩家扣资源/改 CodeVersion/影响视野/绕过 refund；或利用 Rhai 脚本复杂度制造 tick stall。

建议：
- 把 RuleMod 降级为 declarative actions，不允许任意 ECS mutable access。所有写入都必须转换成 `RuleAction`，再进入与 command 同级的 validator：`AwardResource`, `DeductUpkeep`, `EmitEvent`, `ModifyConfig` 等。
- 每个 mod manifest 声明 capability：`read_world_summary`, `deduct_resource`, `award_resource`, `alter_visibility` 等；默认 deny。
- Rhai engine 必须配置 max operations、max call depth、no float 或 fixed-point、no randomness、no wall clock、no file/network、deterministic iteration。
- 世界规则版本进入 replay hash；Arena 赛前锁定 mod hash。
- RuleMod actions 进入审计日志与 replay，不允许“系统内隐修改”。

Severity: High

### H4. 认证/代码签名模型存在概念混用：服务端生成临时私钥 vs 客户端签名无法同时成立

位置：P0-3 §1.1，P0-9 §3，tech-choices §8/§9。

问题：
- P0-3 §1.1 写证书包含 `public_key`，且“服务端生成的临时密钥对”；部署时“客户端附带证书 + 私钥签名(Blake3(WASM bytes))”。如果私钥由服务端生成，如何安全交给客户端？如果交给客户端，泄露面与 OAuth session token 类似；如果不交给客户端，客户端无法签名。
- tech-choices §8 把 Blake3 MAC 称为“代码签名”，但 MAC 是对称认证，不是客户端可验证的非对称签名；P0-3/P0-9 又使用 Ed25519。术语混用会造成错误实现。
- JWT、证书、mTLS、Ed25519 签名四套机制同时出现，但缺少明确的信任链和每个请求必须验证的材料。

攻击/失败模式：实现者可能只验证 JWT scope，不验证 module hash 与已部署主体绑定；或把 Blake3 keyed hash key 下发给客户端；或服务端生成私钥后长期存储，导致任意模块可被代签。

建议：
- 明确二选一：
  1. 客户端生成 Ed25519 keypair，服务端签发短期 cert 绑定 public key；客户端用私钥签 WASM hash；或
  2. 不做客户端代码签名，只做 TLS + OAuth + server-side module hash binding。
- 不要称 Blake3 MAC 为“代码签名”；用于 server internal MAC 可以，但不能替代 Ed25519。
- 写出部署验证伪代码：JWT subject == cert subject == deployment owner；signature verifies over `(module_hash, world_id, version_tag, timestamp, nonce)`；nonce 防重放。
- mTLS 如果是外部 AI 客户端强制要求，需要说明证书发行、轮换、撤销；否则删除 mTLS，避免伪安全要求。

Severity: High

---

## Medium

### M1. Sandbox seccomp / fork lifecycle 细节有误实现风险

位置：P0-4 §1/§4。

问题：
- 文档写“每 tick fork → 执行 → kill”，同时 seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`、禁止 fork/execve。真正的 per-tick worker 创建、Wasmtime JIT mmap/mprotect、线程/信号/futex 行为需要非常精确，否则要么跑不起来，要么不得不放宽 seccomp。
- `pids.max = 32` 与 `wasm_threads(false)`、Wasmtime/Cranelift 运行时线程之间需要验证；如果编译与执行在同进程，JIT 线程可能超出预期。
- `config.fuel_consumed_callback` 片段看起来像伪 API；若实现者照抄可能产生 false sense of security。

建议：
- 把 P0-4 明确成伪代码/意图，不要伪装成可直接编译的 Wasmtime API。
- 增加“已验证 syscall profile”：用恶意样本库跑 under seccomp，记录实际 syscall allowlist。
- 编译进程和执行进程分离；执行 worker 不允许 Cranelift 编译，只加载预编译 module cache。

Severity: Medium

### M2. `host_get_world_rules` / `swarm_get_world_rules` 可能泄露服主策略或 hidden config

位置：P0-4 §8，P0-3 §4.4，P0-7。

问题：
`swarm_get_world_rules` 返回“完整配置（含 i18n 描述）”，WASM host function 也可读 world rules。若规则中包含隐藏 spawn policy、arena seed、future event schedule、经济调参、mod private config，会形成信息泄漏。

建议：
- 将 world config 分为 public/player-visible/server-private 三层。
- IDL 里为每个 config key 标注 visibility。
- Arena seed、hidden event、anti-cheat threshold、admin config 不得通过 MCP/WASM 暴露。

Severity: Medium

### M3. `get_schema` / docs / player-originated strings 的 prompt injection 防护还停留在 SDK 约定

位置：P0-3 §6，P0-2 §6。

问题：
- 玩家名称限制很严格，但 prompt injection 不只来自名称；mod i18n 描述、room messages、版本标签、module metadata、rejection detail、docs 中的玩家内容都可能流入 AI context。
- “官方 SDK prompt 模板用分隔符包裹”属于客户端约定，不是服务端强制安全边界。

建议：
- 所有 player/world-owner/mod-authored strings 都进入 `UntrustedString` 类型，带 source、max length、charset/profile、rendering context。
- MCP 返回 JSON schema 中显式标注 `untrusted: true`，不要只在样例里标。
- 版本标签 `version_tag` 也限制长度/字符集并标注 untrusted。

Severity: Medium

### M4. Admin 与 Rollback 权限过宽，缺少 break-glass 与租户隔离模型

位置：P0-9 source model。

问题：
`Admin` 在能力矩阵中可写世界、全局存储、部署、查询、战斗，且 rate limit “无限制”。`Rollback` 可写入/部署/查询。虽然 Rollback 有双人签名，但 Admin 本身没有双人审批、scope 分级、world-level tenancy、审计不可抵赖细节。

建议：
- 拆分 `swarm:admin` 为 `admin:read_trace`, `admin:moderate_player`, `admin:rollback_world`, `admin:write_world` 等最小 scope。
- 高危 admin action 双人审批 + reason + ticket id + append-only audit。
- Admin 仍有 rate limit 和 anomaly detection；“管理员”不是 DoS 豁免。

Severity: Medium

### M5. NATS / WebSocket / REST 推送层缺少 backpressure 与 replay gap 安全合同

位置：DESIGN §2，tech-choices §5。

问题：
设计认为 NATS 丢消息可由客户端 gap → fetch 修复，但没有定义 gap fetch 的 authz、rate limit、最大窗口、visibility redaction。WebSocket 广播如果每客户端视野不同，不能简单发布同一 delta；否则可能向无视野客户端泄露实体。

建议：
- 明确 delta 是 per-player/per-visibility materialized，或广播公共事件 + 客户端按授权拉取私有 state。
- gap fetch 限制最大 tick window、每玩家速率、redaction 与 replay 同源。
- WebSocket 连接建立时绑定 player_id/world_id；所有消息按 binding 过滤。

Severity: Medium

### M6. Supply-chain 风险列了 CVE SLA，但缺少 rmcp/bevy/rhai/dragonfly/fdb 依赖审计策略

位置：tech-choices，DESIGN，P0-4。

问题：
Wasmtime 有版本 pin 和 CVE SLA；但 rmcp、Bevy、Rhai、ed25519-dalek、JWT/OAuth、nginx/gateway Go deps、FoundationDB client、Dragonfly/NATS/ClickHouse 都没有同等策略。Bevy API 变动、rmcp HTTP/SSE 暴露面、Rhai sandbox CVE/DoS、JWT crate alg confusion 都应进入供应链威胁模型。

建议：
- 给每个安全关键依赖建立 owner、pin policy、audit tool、upgrade cadence、CVE SLA。
- Rust: `cargo audit` + `cargo deny`；Go: `govulncheck`；frontend: `pnpm audit` 或等价；容器镜像扫描。
- 明确禁止 JWT `alg=none`/算法混淆；固定 EdDSA/RS256 等。

Severity: Medium

---

## Informational

### I1. “单一管线：所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一 校验→应用 路径”表述容易误导

P0-2 §1 写所有入口都走同一管线，但 P0-3/P0-9 又强调 MCP 不提交 gameplay command。建议改成：所有“世界写入 action”走 Source Gate + Auth Verify + Validation Pipeline；MCP read/deploy/debug 走各自 read/deploy validator，不进入 gameplay command validator。

Severity: Informational

### I2. `RawCommand` 仍包含 `player_id`

P0-2 §2 的 RawCommand 示例含 `player_id`，P0-9 又禁止客户端在 command body 自报 player_id。建议 RawCommand schema 中把 `player_id` 从客户端输入删除，改为 `ServerCommandEnvelope { auth_context, command }`，避免实现者接受客户端字段后再“覆盖”。

Severity: Informational

### I3. `swarm_deploy` 示例包含 `room_id`，但部署作用域未定

P0-3 §4.1 的 `swarm_deploy` 参数有 `room_id`。如果代码可按 room 部署，需要定义 per-room module binding、回滚、版本传播、CodeVersion 与 world rules 的一致性；否则删除该参数，避免 scope confusion。

Severity: Informational

### I4. `wasm_simd(true)` 与 deterministic contract 需要测试背书

P0-4 禁用 relaxed SIMD 但允许 SIMD。普通 SIMD 通常可控，但跨 CPU/Wasmtime 版本仍建议进入 replay determinism 测试矩阵，尤其是浮点/NaN 行为。若游戏 API 禁止浮点，则文档应明确。

Severity: Informational

---

## 建议的 Phase 0 冻结前阻塞项

1. 为所有 MCP/Web REST 工具补齐 authz predicate、visibility filter、redaction policy、rate-limit key。
2. 统一 DoS 预算表：deploy/validate/dry-run/simulate/docs/schema/path_find 的 per-player/per-IP/per-world/global 限制。
3. 重写 RuleMod 能力模型：manifest capability + RuleAction validator + deterministic Rhai budget。
4. 澄清认证/签名链：JWT、证书、Ed25519、mTLS、Blake3 MAC 各自用途，不混用术语。
5. 把 RawCommand 改为服务端 envelope；客户端输入不得包含 `player_id`。
6. 为 replay/debug/gap-fetch 增加 IDOR 与 fog-of-war regression tests。
7. 为 sandbox 增加真实 syscall profile 与 Wasmtime API 版本核对，避免不可编译或不得不放宽的安全配置。

