# R4 Clean-Slate Security Review — rev-gpt-security

Verdict: REQUEST_MAJOR_CHANGES

本轮从信任边界、攻击面、权限模型、协议安全性、数据完整性、DoS/资源放大角度独立审阅了 R4 文档副本。整体方向明显比前几轮成熟：MCP 不再是 gameplay 通道、WASM 是唯一玩家执行路径、可见性统一函数、Source Gate、部署 nonce、TickTrace 与沙箱预算都体现了正确的安全设计。但当前文档仍存在若干会直接影响实现安全性的高危不一致：尤其是 Rhai 模组信任/隔离模型、部署证书模型、可见性优先拒绝码与 IDL/校验顺序之间的冲突。建议在这些合同统一前不要进入实现或合并为稳定规范。

## Critical

本轮未发现必须立即判定为 Critical 的单点设计缺陷。主要风险来自多个 High 级合同不一致叠加：若实现者按较弱版本落地，可能演化成可利用的权限绕过、信息泄露或供应链执行风险。

## High

### H1. Rhai 模组信任边界前后矛盾，可能导致供应链代码在引擎进程内执行

位置：
- DESIGN §8.7 / §Rhai 安全隔离：描述“Rhai 模组在引擎进程内运行——服主安装的模组是受信代码”。
- 07-world-rules-engine §5.1：描述“默认配置：Rhai engine 运行于独立 sandbox 进程”，并要求 cgroup/seccomp、崩溃不影响核心引擎、签名强制。

问题：
同一安全边界出现两套互斥模型：
1. 进程内受信扩展：性能优先，安全依赖服主审查。
2. 默认进程外沙箱：供应链默认不可信，签名 + IPC + cgroup/seccomp。

这不是文档措辞问题，而是实现安全架构分叉。若工程实现按 DESIGN 的“进程内可信”落地，同时运营/审计按 07 的“默认 sandbox”假设验收，恶意或被劫持模组可以直接在核心进程上下文内触发 panic/OOM、逻辑篡改、状态泄露或引擎崩溃。

建议：
- 统一为一个强制合同：默认必须进程外 sandbox；进程内模式只能是显式 `unsafe_inprocess = true`，并在世界配置、启动日志、管理 UI 中红色告警。
- 将“服主信任”降级为“授权加载，但仍需最小权限执行”。
- 明确 IPC schema、actions buffer 签名/校验、崩溃恢复语义、沙箱超限后的事务回滚边界。
- 将模组签名、mods.lock checksum、trusted_keys、无 unsigned 宽松模式写成同一份权威规范，删除“checksum 可选”等弱化表述。

### H2. 部署证书与密钥所有权模型冲突，影响不可伪造身份与审计链

位置：
- 03-mcp-security-contract §1.1：证书内容写“public_key: Ed25519 — 服务端生成的临时密钥对”，部署时“客户端附带证书 + 私钥签名”。
- 09-command-source-model §3.1：客户端生成 Ed25519 密钥对，服务端签发证书；部署 payload 由客户端私钥签名。
- 03 §1.1 默认证书 24h；09 §3.4 默认证书 90 天。

问题：
密钥到底由服务端生成还是客户端生成，是认证信任模型的核心分界。服务端生成私钥会带来密钥托管、导出、传输、泄露审计问题；客户端生成则是端侧 possession proof。当前两处冲突会导致：
- 实现者可能把私钥从服务端下发给客户端，扩大泄露面。
- 证书生命周期与 CRL/epoch 扫描策略无法定稿。
- “某玩家部署某 WASM”的不可抵赖审计链不稳定。

建议：
- 采用 09 的模型：客户端生成 Ed25519 密钥对，服务端只签发公钥证书，不生成、不保存、不传输客户端私钥。
- JWT/证书必须包含 `aud`、`world_id`、`client_type`、`epoch`、`jti`/cert serial。
- 统一证书有效期：例如登录 token 15 min、deploy cert 24h 或 90d 二选一，并说明 CRL 检查成本与离线 agent 场景。
- `DeployPayload` 必须签名 canonical encoding（例如 RFC 8785 JSON Canonicalization 或 protobuf deterministic encoding），不能签名普通 JSON 字符串。

### H3. 可见性优先原则与 IDL/校验矩阵冲突，可能重新引入 IDOR / 枚举 oracle

位置：
- 02-command-validation §5：所有涉及 `target_id`/`target_player` 的校验第一步必须是可见性检查，不可见或不存在统一返回 `NotVisibleOrNotFound`。
- 08-game-api-idl §2：`RejectionReason` 仍包含 `ObjectNotFound`、`PlayerNotFound`、`TargetNotVisible`。
- 08 validators 多处顺序为 `exists, owner, ... visible_target ...`，例如 Overload: `target_player, enemy_target, visible_target`。
- 02 §3 指令表也多处先写 `target_id 存在`，再写 owner/range。

问题：
文档同时要求“不可见/不存在不可区分”，又在 IDL 中保留可直接暴露枚举差异的拒绝码，并且 validator 顺序先 exists 后 visibility。这非常像典型 IDOR/ObjectId 枚举漏洞的设计前兆：玩家可以通过错误码或时序差异枚举隐藏实体、隐藏玩家、房间占领状态或 Overload 目标是否存在。

建议：
- 将 player-facing RejectionReason 与 admin-only detail 类型分离：公开枚举只允许 `NotVisibleOrNotFound`，admin trace 才记录 `ObjectNotFound`/`TargetNotVisible`/`PlayerNotFound`。
- IDL validator 必须支持 `visible_or_opaque_exists(target)` 这种原子校验，不能生成先 exists 再 visibility 的代码。
- 对所有 target 相关拒绝响应做恒定形状、近似恒定耗时处理，避免通过延迟区分“查不到”和“不可见”。
- 增加属性测试：随机隐藏实体 ID，断言玩家输出的 code、body、latency bucket 不泄露存在性。

### H4. seccomp / sandbox OS 边界仍过宽，存在继承 fd、clone、write 滥用风险

位置：
- 04-wasm-sandbox-baseline §4.1：seccomp 允许 `read, write, mmap, mprotect, ... clone (仅 CLONE_VM | CLONE_VFORK)`；sandbox 与引擎通过 Unix domain socket 通信；无网络命名空间。
- 04 §2.3：WASI 禁文件/网络/时钟。

问题：
WASI 禁用不能替代 OS 级 fd 与 syscall 收口。当前 seccomp 允许 `write`，且 sandbox 需要 Unix socket/fd 与引擎通信。如果 fork 后没有严格关闭/封印不必要 fd、限制可写 fd、设置 no_new_privs、阻止 ptrace/process_vm、处理 clone 语义，恶意模块触发 runtime bug 或宿主 glue bug 时可能利用继承 fd 写入非预期通道，或通过线程/clone 增加 DoS 面。

建议：
- 明确 sandbox 进程启动顺序：close-on-exec、关闭除 IPC fd 外所有 fd、IPC fd 协议鉴权、只允许固定 fd 编号读写。
- seccomp 使用参数过滤：`write`/`read` 仅允许 IPC fd；`clone` 原则上禁用，除非 Wasmtime 确认必须并限定 flags；显式禁 `ptrace`、`process_vm_readv/writev`、`prlimit64`、`io_uring_*`、`memfd_create` 等。
- 增加 `no_new_privs`、Landlock/只读 mount namespace、独立 user namespace、`RLIMIT_CORE=0`。
- 恶意样本库补充“继承 fd 写入”“Unix socket fuzz”“clone/futex storm”“mprotect JIT page abuse”类测试。

### H5. MCP simulate / dry-run 是明显的计算放大入口，预算模型需要统一并可执行

位置：
- 03 §4.4：`swarm_simulate` 5/tick，World / Arena 限流；`swarm_get_schema` / docs 无限制。
- 04 §6.1：simulate 最多 100 tick、1000 entities、5s CPU、每玩家每小时 50M fuel、并发 3。
- 09 §2.2 / §6：Simulate 5/tick，Arena 10/tick，budget 0.5×MAX_FUEL。
- 06 §3.1：`swarm_dry_run_commands` 是 MVP 发现型工具。

问题：
simulate/dry-run 是“最小请求产生最大服务端开销”的典型 DoS 面。文档给了多个不一致预算：按 tick、按小时 fuel、按 CPU 秒、按并发、World/Arena 差异都不完全一致。若按最宽松解释，500 AI 玩家每 tick 触发 5 秒模拟会远超引擎实时预算。dry-run 还可能成为状态/校验 oracle：攻击者用批量候选命令探测边界、可见性、冷却、资源状态。

建议：
- 统一单一预算公式：`cost = simulated_ticks × entity_count × action_count × pathfind_factor`，从玩家的独立 simulate quota 扣除，而不是只按调用次数。
- simulate worker 必须与 tick 引擎隔离进程池，低优先级，不能与 authoritative tick 抢 CPU。
- dry-run 输出必须 snapshot-bound，只能针对调用者已可见对象；不可返回比正式 RejectionReason 更详细的信息。
- 为 docs/schema 无认证接口增加 IP 与全局缓存限流，避免作为反射/爬取 DoS 入口。

### H6. RuleMod 能力与“不能绕过 Command Validation Pipeline”表述不完全一致

位置：
- 09 §2.3：RuleMod 允许 `damage_entity/set_entity_flag/deduct_resource/award_resource/emit_event/custom handler`，但不允许触发战斗。
- 07 §5.1：Rhai actions buffer 可写 `effects: Vec<WorldEffect>`，并可注册 action handler。
- 07 §10：规则 System 可修改 ECS 资源/组件，但绝不可绕过 Command 校验管线。

问题：
`damage_entity`、`set_entity_flag`、custom handler 本质上就是世界状态突变，部分效果等价于战斗/控制/资源变更。当前文档说它“不绕过 Command Validation Pipeline”，但 RuleMod 的 actions 显然不是玩家 Command，也不会经过同样的 owner/range/visibility/body part 校验。若不定义 RuleMod 专属 mini-validator 的完整能力模型，模组可以成为“管理员后门式 gameplay 通道”。

建议：
- 明确 RuleMod 不走玩家 Command Pipeline，而走 RuleAction Pipeline；两者共享审计和事务，但校验规则不同。
- 为每个 action 定义 capability token：作用域（world/room/player/entity）、目标选择器、频率、最大影响量、是否可影响 PvP。
- 禁止 `custom handler` 默认任意写 ECS；新 handler 必须声明读写集和确定性预算，并通过安全审计。
- TickTrace 中将 RuleMod actions 与玩家 Commands 分开记录，防止回放和反作弊混淆。

## Medium

### M1. Command schema 限额存在多处数值冲突，易导致实现按错误边界验收

位置：
- 02 §1.1 JSON Schema `maxItems: 100`，文字写 `MAX_COMMANDS_PER_PLAYER (500)`。
- 02 §1.1 总字节数 ≤256KB；02 §6 批级校验写整批 ≤1MB。
- 02 §1.1 对数组说 `additionalProperties: false`，JSON Schema 语义不适用于数组顶层。
- 04 §3.1 CommandIntent JSON 超过 256KB 拒绝。

风险：
边界不一致会直接影响 DoS 防护、SDK 生成、客户端报错与服务器验收。攻击者通常会寻找“网关按 1MB 接受、引擎按 256KB 处理”这类分层差异制造资源浪费或解析差异。

建议：
选定唯一值并放入 IDL/常量表：例如每玩家每 tick 500 commands、单 command 64KB、整批 256KB。网关、MCP、WASM ABI、TickTrace、SDK 均从同一生成源读取。

### M2. JWT 示例缺少 `aud`，与 transport 拆分安全合同不一致

位置：
- 03 §2.1/2.2 要求 token audience 绑定 `{gateway_origin, world_id, browser|cli}`。
- 03 §3.1 JWT 示例仅有 `sub/scope/iat/exp/jti`。

风险：
audience 是防跨端点、跨世界、跨协议 replay 的关键字段。示例缺失会让实现者误以为 aud 可选。

建议：
JWT 示例加入 `aud`、`world_id`、`client_type`、`iss`、`epoch`，并明确网关必须拒绝 aud 缺失或不匹配。

### M3. ClickHouse “不可修改”审计日志表述过强，缺少完整性链

位置：
- 03 §7：mcp_audit 使用 ClickHouse MergeTree，描述“不可修改”。

风险：
ClickHouse 表不是密码学意义的 WORM。管理员、被攻陷服务账号或错误迁移仍可修改/删除审计数据。安全事件响应依赖审计时，这会削弱证据链。

建议：
- TickTrace / MCP audit 增加 hash chain：`entry_hash = H(prev_hash || canonical_entry)`。
- 周期性将 checkpoint hash 写入独立存储或对象锁定 bucket。
- 区分“应用不提供修改 API”和“存储层不可篡改”。

### M4. PRNG 种子轮换在旧种子泄露后不具备前向安全

位置：
- DESIGN §8.8 / 01 §3.1：`new_seed = Blake3(old_seed || current_tick)`。

风险：
如果某个 seed epoch 泄露，攻击者可以推导所有后续 seed，预测玩家顺序。虽然 seed 理论上 admin-only，但安全设计应考虑日志/内存 dump/备份泄露。

建议：
- 轮换时混入服务端 CSPRNG 新熵：`new_seed = Blake3(old_seed || current_tick || fresh_32_bytes)`。
- TickTrace 只记录 epoch id 和 encrypted seed material；回放权限与 seed 解密权限分离。

### M5. Host path_find 缓存与可见性 fingerprint 是正确方向，但需防缓存爆炸

位置：
- 04 §8：`host_path_find` cache key 包含 `(from, to, terrain_hash, player_visibility_fingerprint)`。

风险：
visibility fingerprint 若高基数且每玩家每 tick变化，攻击者可通过不同路径请求制造大量不可复用 cache entries。配合不可达路径更贵，形成内存/CPU 双重放大。

建议：
- 每玩家每 tick 的 path cache 上限、LRU/TTL、不可达结果负缓存上限。
- 对 `from/to` 坐标做 canonical clamp，并按 room 分区缓存。
- `explored_nodes` 额度应在执行前按最坏情况预留，避免中途超限造成不确定行为。

### M6. 玩家/模组原创字符串的 prompt injection 防护未覆盖所有 AI 可见文本

位置：
- 03 §6：玩家原创字符串标注 untrusted，玩家名限制 32 字符。
- DESIGN/07：world rules、mod description、i18n 描述会返回给 MCP/AI。

风险：
第三方模组 README/description/i18n、世界名、房间名、版本标签等也可能是 untrusted 文本。若 AI agent 将 `swarm_get_world_rules` 直接拼入 prompt，模组描述可成为 prompt injection 渠道。

建议：
- 所有非官方/非核心文本统一包裹 `{ value, untrusted, source_type, source_id }`。
- MCP SDK 分隔符合同覆盖 snapshot、world rules、docs snippets、replay explanations，而不只覆盖游戏数据。
- 对官方 docs 与第三方 docs 分级标注。

### M7. Browser/Agent 端点“拒绝携带 browser-style header 的 agent 请求”可能造成误判，需定义更精确的跨协议防护

位置：
- 03 §2.2：Agent 端点拒绝任何携带 browser-style Origin/CSRF header 的请求。

风险：
部分 CLI/HTTP 库、代理或企业网关可能添加 Origin；简单拒绝 header 可能带来兼容性问题。真正安全目标是 agent endpoint 不依赖 Origin/CSRF，而是 mTLS/signed request。

建议：
- 改为：Agent endpoint 忽略 Origin 作为认证依据，但若出现 browser fetch metadata 且缺少 signed request/mTLS，则拒绝。
- 通过路径、audience、client_type、签名 domain separator 防跨协议混淆。

### M8. Rollback 双人审计是亮点，但 Admin 可写世界仍需 break-glass 约束

位置：
- 09 §2.2/2.3：Admin 可写世界，Rollback 需双 admin 签名。

风险：
Admin 命令统一 validate_and_apply 是正确方向，但 Admin “所有权放宽”仍等价于全局写能力。若缺少 break-glass session、审批原因、范围限制和回放标记，可能难以区分合法运维与滥用。

建议：
- 所有 Admin gameplay-affecting 操作都要求 reason、ticket_id、短期 elevated token。
- TickTrace 对 admin-mutated tick 标记 `non_competitive` 或 `operator_intervention`。
- 高风险 Admin 操作（资源发放、实体删除、世界回滚）采用双签或延迟生效。

## Informational / Low

### I1. 安全设计亮点：MCP 非 gameplay 通道

MCP 被明确定位为 AI 的“屏幕和鼠标”，不提供 `swarm_move`/`swarm_attack` 等直接游戏动作。AI 与人类都必须通过 WASM 部署进入世界。这显著降低了权限模型复杂度，避免出现 AI 专属高权限控制面。

### I2. 安全设计亮点：Command Source Model 与服务端注入身份

CommandIntent 只允许 `sequence + action`，`player_id/source/tick/auth` 全由 Source Gate 服务端注入。这是防 mass assignment 和伪造来源的关键设计，应保持为不可变合同。

### I3. 安全设计亮点：Overload 信息泄露处理较成熟

Overload 增加可见性约束、目标全局冷却、fuel 地板静默 no-op、三种结果等价，避免把战术压制工具变成探测对方 fuel 状态的 oracle。后续实现需确保 player-facing trace 也不泄露真实 apply 分支。

### I4. 安全设计亮点：WASM 沙箱采用多层预算

fuel、epoch interruption、线性内存、cgroup、seccomp、模块大小、host function 次数、path_find explored_nodes 等多层预算方向正确。建议将所有预算常量放入同一 generated policy，避免文档漂移。

### I5. 安全设计亮点：可见性缓存统一输出面

每 tick 每玩家计算一次 visibility cache，并要求 snapshot/MCP/WS/REST/replay 共享，是防“一个输出面漏过滤”的正确架构。建议在 CI 中强制跑跨输出面泄露检测。

### I6. 安全设计亮点：部署 nonce + domain-separated signed payload

`swarm_deploy_challenge`、单次 nonce、60s TTL、audience/IP 绑定、payload domain separator、module_hash 校验构成了较完整的防重放链路。只需统一密钥生成模型与 canonical signing 即可。

## 建议的阻塞项清单

进入实现前建议至少完成以下阻塞修订：
1. 统一 Rhai 模组隔离/签名/供应链合同，明确默认进程外 sandbox。
2. 统一客户端 Ed25519 证书模型、证书有效期、JWT aud 示例和部署 payload canonical encoding。
3. 重写 IDL validator 与 RejectionReason：player-facing 不得暴露 ObjectNotFound/PlayerNotFound/TargetNotVisible 差异。
4. 统一所有 command/snapshot/simulate/body size 限额，消除 100 vs 500、256KB vs 1MB 等冲突。
5. 将 simulate/dry-run 放入独立资源池和单一成本模型，避免实时 tick 被查询工具拖垮。
6. 补全 sandbox fd/syscall 收口、no_new_privs、fd allowlist、恶意样本测试。

总体评价：设计已经具备良好的安全骨架，但当前仍是“安全意图强、合同一致性不足”。建议 REQUEST_MAJOR_CHANGES，修复上述 High 项后再进入下一轮评审。