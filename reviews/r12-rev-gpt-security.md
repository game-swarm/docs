# R12 — rev-gpt-security 安全设计评审

Reviewer: rev-gpt-security (GPT-5.5)
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/design/tech-choices.md`, `/data/swarm/docs/specs/p0/`

## Verdict

REQUEST_MAJOR_CHANGES

总体方向正确：P0 已经修正了最危险的架构误区——MCP 不直接下发 gameplay 指令，AI 与人类都必须通过 WASM；同时引入 Source Gate、统一可见性、WASM fuel、JSON schema、refund anti-amplification、TickTrace 审计，这些都是安全设计的正确骨架。

但当前冻结版仍有数个安全合同不一致或可被实现者误解的点。最需要在进入实现前修正的是：

1. WASM 模块预校验对 start function / ctor 的检测方式不充分，可能破坏 “tick() 是唯一执行入口” 的安全边界。
2. RawCommand / Source Gate / IDL 三份文档对 `player_id`、`tick`、`source` 的服务端注入关系不一致，存在典型 IDOR / mass assignment 实现风险。
3. `swarm_simulate` / dry-run / Tick transaction 的成本模型不足，存在最小请求放大服务端计算的 DoS 面。
4. 认证与签名模型在 Ed25519 证书、服务端生成 keypair、Blake3 MAC “代码签名”之间语义冲突，需要收敛。
5. Rhai 模组市场/安装链缺少供应链安全合同。

建议：不要直接按当前文本开工。先做一次 P0 security contract patch，把下面 Critical/High 项写成不可歧义的规范和验收测试。

---

## Critical

### C1. WASM start function / constructor 检测不充分，可能绕过 `tick()` 唯一入口

位置：`specs/p0/04-wasm-sandbox-baseline.md` §2.4, §3

当前模块校验写的是：

- 检查无 `_start` export
- 检查无 `__wasm_call_ctors` export
- 要求导出 `tick`

问题：

WebAssembly 的 start section 不需要以 `_start` 形式 export。仅检查 export 名称无法证明模块没有 instantiation-time 执行路径。某些工具链也可能通过 start section、constructor glue、imported init pattern 在实例化阶段运行逻辑。设计目标是 “WASM 不在 `tick()` 前执行任何玩家代码”，所以校验必须针对 WASM module start section 和允许 import 集合本身，而不是只看 export 名。

攻击/失败模式：

- 恶意模块在实例化时进入死循环或高成本初始化，使成本发生在 `tick()` 调用前。
- 如果 host functions 在实例化前已链接，start path 可能调用查询 host function，制造额外 DoS 或绕过 tick 输出语义。
- 实现者以为“没有 `_start` export 就安全”，实际留下前置执行路径。

要求修正：

- 明确拒绝 WASM start section：用 wasmparser/wasm-tools 检测 `StartSection`，不是检查 `_start` export。
- 明确所有 host function 必须在 store 已配置 fuel/epoch/limits 后才可调用；instantiation 也必须受同一 fuel/epoch/cgroup 限制。
- 若允许语言运行时构造器，必须把 constructor 执行也计入同一 budget，并把其行为定义为只可初始化线性内存、不可调用任何 Swarm host function；否则一律拒绝。
- 恶意样本库增加：start section 调用 loop、start section 调 host import、`__wasm_call_ctors` 非 export 形态、含 data/element 初始化的大模块。

---

## High

### H1. RawCommand 允许客户端提供 `player_id` / `tick`，与 P0-9 “服务端注入不可自报” 冲突

位置：

- `specs/p0/02-command-validation-spec.md` §2
- `specs/p0/09-command-source-model.md` §3.2, §4
- `specs/p0/08-game-api-idl.md` commands

P0-2 的 RawCommand 示例包含：

```json
{
  "player_id": 42,
  "tick": 4521,
  "sequence": 3,
  "action": { ... }
}
```

并写 `player_id` 必须匹配已认证玩家。P0-9 则写：禁止客户端在 Command body 中自报 `player_id`，服务端注入 auth context，并覆盖任何客户端自报 ID。

这是典型 IDOR / mass assignment 风险：实现者如果按 P0-2 的 schema 接收 `player_id`，再做“匹配”检查，未来某个 REST/MCP/Admin/TestHarness 入口很容易漏检查，变成替别人提交命令。

要求修正：

- 玩家 WASM 输出 schema 中删除 `player_id`、`tick`、`source`、`module_hash`、`session_id` 等所有 auth/context 字段。
- 玩家只可输出：`sequence` + `action`。甚至 `sequence` 也可由 host 读取数组顺序生成，避免重复/跳号歧义。
- 服务端在 Source Adapter 层生成 `ServerRawCommand { auth, tick_target, sequence, action }`。
- P0-2、P0-8、P0-9 必须共享同一 schema 名称，区分：
  - `PlayerCommand`：不可信 WASM JSON
  - `ServerRawCommand`：服务端注入 auth 后的内部结构
  - `ValidatedCommand`：通过 Source Gate/Auth/Validation 后的结构
- 加测试：客户端提交 `player_id` 字段时必须因 `additionalProperties=false` 被拒绝，而不是覆盖或忽略。

### H2. `swarm_simulate` / dry-run 是高放大 DoS 面，预算定义不足

位置：

- `specs/p0/03-mcp-security-contract.md` §4.4
- `specs/p0/06-mvp-feedback-loop.md` §3.1
- `specs/p0/09-command-source-model.md` §2.2

`swarm_simulate` 允许 “给定世界快照，预测未来 N tick”，限流 5/tick（World）/3/tick（Arena），budget 写 0.5× MAX_FUEL。这里没有定义 N 的上限、实体数量上限、是否会运行 WASM、是否会执行 pathfinding、是否会复制完整 ECS world、是否可并发。

攻击模式：

- 单个 AI token 每 tick 5 次 simulate，每次 N 很大或 snapshot 很大，服务端执行远超一次正常 tick 的计算。
- 攻击者构造大量 commands 触发 pathfinding/validator/visibility 计算，simulate 成为免费 oracle 和 CPU 放大器。
- 多账号绕过 per-player 限流，形成 compile/simulate farm。

要求修正：

- `swarm_simulate` 必须默认 Phase 2 不进入 P0，或限定为本地 CLI 离线功能；线上 MCP 版本推迟到有完整 budget 后。
- 若保留线上 MCP：定义 `max_ticks`、`max_entities`、`max_commands`、`max_pathfinds`、`max_output_bytes`、`max_wall_ms`、`max_concurrent_per_player`、`global_concurrency`。
- simulate 不得运行任意 WASM；只接受已通过 schema 的 `PlayerCommand[]` 或使用当前已部署 module_hash 且计入同一 budget。
- snapshot 必须绑定 `snapshot_id`，服务端从权威状态复制；不接受客户端上传任意大 snapshot。
- 返回必须截断，且只返回玩家可见结果；不能输出 hidden state 作为“预测解释”。

### H3. Tick transaction 可被最大合法输入打爆，导致 abandon loop / 降级模式

位置：

- `specs/p0/01-tick-protocol-spec.md` §3.4, §6
- `specs/p0/02-command-validation-spec.md` §6

设计允许：500 AI 玩家 × 100 commands/player/tick = 50,000 commands/tick。EXECUTE 预算 500ms，且整个阶段二包裹在 FoundationDB transaction 中提交。还要记录 commands/rejections/metrics/state。

风险：

- FoundationDB 单事务有大小、冲突、延迟现实限制；即使不引用具体数值，50k command + state delta + trace 很容易超过“一个事务里全世界提交”的安全余量。
- 恶意玩家只需提交合法但高冲突/高拒绝/高 trace 的命令，即可让 tick commit fail，触发 tick abandon；连续触发后引擎进入 degraded mode，暂停部署/新玩家。
- “放弃后 1s 重试同一 tick” 如果输入不变，会重复失败，形成自保持 DoS。

要求修正：

- 定义每 shard/room 的 tick command budget，而不是全世界一个 FDB transaction。
- TickTrace 大对象与权威 state commit 分离：权威状态最小事务；trace 使用分块/异步但带完整性 hash，失败不应导致 gameplay commit 失败，除非处于审计强一致模式。
- 对每 tick 总 command 数、总 rejection detail 字节、总 state delta 字节设硬上限；超过时按玩家公平截断。
- tick abandon 的重试必须能改变输入：例如 drop non-essential trace、进入 safe execution mode、或二分隔离导致冲突的 shard；不能盲重放同一大事务。
- 增加压力测试：500 players × 100 invalid commands、500 players × max path commands、max rejection detail、FDB conflict storm。

### H4. 认证/签名模型语义冲突：Ed25519 证书、服务端生成私钥、Blake3 MAC “代码签名”混用

位置：

- `specs/p0/03-mcp-security-contract.md` §1.1
- `specs/p0/09-command-source-model.md` §3
- `design/tech-choices.md` §8, §9

当前文本同时出现：

- OAuth2 后服务端签发短期证书。
- 证书包含 public_key，且写 “服务端生成的临时密钥对”。
- 客户端部署 WASM 时用私钥签名 Blake3(WASM bytes)。
- 技术选型把 “代码签名”列为 Blake3 MAC/keyed hash。
- Ed25519 用于证书签发。

问题：

- 如果服务端生成 keypair 并把私钥交给客户端，本质上服务端和客户端都知道私钥，签名不具备清晰的持有者证明/不可抵赖语义；还增加私钥传输和存储面。
- Blake3 MAC 是对称认证，不是代码签名；如果用作部署认证，需要定义 key 分发、scope、rotation、replay protection。不能与 Ed25519 “签名”混称。
- 对 WASM 部署而言，真正需要的是“请求来自已认证 session + module_hash 绑定 player_id + 防重放 + 审计”，不一定需要客户端长期签名。但文档必须唯一。

要求修正：

- 选择一个模型并写死：
  1. 简化模型：OAuth/JWT bearer + TLS/mTLS + 服务端计算 module_hash，部署请求不需要客户端签名；审计绑定 session/jti。
  2. 或签名模型：客户端本地生成 Ed25519 keypair，服务端只签 public key 证书，客户端用 private key 签 module_hash + nonce + exp + audience。
- 不要把 Blake3 MAC 称为代码签名。Blake3 可用于 `module_hash`；签名用 Ed25519。
- 部署 payload 必须包含 nonce/jti 或使用短期 one-shot challenge，防 replay。
- 明确 token/cert revoke 后：已部署 module 是否继续运行、下一 tick 是否停用、缓存何时清除。

### H5. 可见性策略对 MCP / player_view / spectator 的边界仍有信息泄露歧义

位置：

- `specs/p0/05-unified-visibility-policy.md` §3.5
- `specs/p0/03-mcp-security-contract.md` §4.2, §6
- `DESIGN.md` §8.2 visibility

P0-5 写：`player_view = "full"` 时 “玩家屏幕 / MCP” 可看全地图，但 WASM snapshot 仍按 `is_visible_to`。P0-3 又写 MCP 提供的信息量与 Web UI 等量，不更多不更少；`swarm_get_snapshot` 是玩家可见世界快照，同 WASM tick 输入。

风险：

- 如果 MCP `swarm_get_snapshot` 在某些世界返回 full view，而 AI 生成 WASM 时能使用这些数据，就等价于给 AI 策略一个带外全知输入。即使 WASM tick snapshot 被过滤，AI 可以把全图信息写进下一版 WASM 策略，破坏 fog-of-war。
- 人类 Web UI 若能 full view 而代码不能，会造成“人工带外侦察”；AI MCP 同理。

要求修正：

- 明确区分三个 API：
  - `swarm_get_game_snapshot`：永远等于 WASM tick snapshot，受 `is_visible_to`，可用于策略输入。
  - `swarm_get_view_snapshot`：人类屏幕/MCP UI 视图，可能受 `player_view` 影响，仅在非竞技/教程等模式开放。
  - `swarm_get_spectator_snapshot`：旁观视角，延迟且去内部状态。
- 在 World PvP/Arena 中，任何实时 full view 都必须禁止或延迟，不能对已登录玩家实时开放。
- MCP docs 必须提醒：AI agent 用于生成代码的上下文只能来自 `game_snapshot`，除非世界规则显式允许全知。

### H6. Rhai 模组供应链安全合同不足

位置：

- `DESIGN.md` §8.7
- `specs/p0/07-world-rules-engine.md`
- `tech-choices.md` §3

Rhai 规则模组被定义为“服主可信”，但同时有模组市场、版本号、dependencies/conflicts、社区 review/rating。模组 action 可 deduct/award/damage/set flag，并影响确定性模拟。

风险：

- 模组市场被投毒或依赖被劫持，服主安装后可改变经济、破坏公平、制造隐藏后门。
- 只有 `name/version` 没有内容 hash/签名/lockfile，回放时无法证明历史 tick 使用的是哪个脚本内容。
- dependencies/conflicts 无版本约束和 resolution 规则，容易出现 “同名不同内容” 或 transitive dependency confusion。

要求修正：

- `world.toml` 或 lockfile 必须记录每个模组的 content hash（建议 Blake3）、来源 URL、签名者、依赖解析结果。
- 模组市场包必须签名；至少支持 trust-on-first-use + hash pin。
- TickTrace 记录 active mod set 的 hash root；回放按 hash 加载，不按 mutable name/version。
- 模组权限分级：economic、entity_flags、damage、spawn、visibility 等 capability 显式声明，安装时审批。
- 模组 action mini-validator 必须在规范中列出完整 allowlist、参数上限、审计字段和失败语义。

### H7. `swarm_get_docs` / `swarm_get_schema` 无认证无限制，可能成为带宽/CPU 放大入口

位置：`specs/p0/03-mcp-security-contract.md` §4.4, §5

开发辅助工具中：`swarm_get_schema` scope 无，限流无限制；`swarm_get_docs` scope 无，限流无限制。HTTP 安全合同只限制 max body size，未限制响应大小、缓存策略、匿名 IP 限流。

风险：

- 匿名客户端反复拉取大 docs/schema，消耗序列化/带宽。
- 如果 docs 支持 i18n、搜索、动态 schema 生成，CPU 成本可能高于普通读请求。

要求修正：

- 匿名 docs/schema 必须 CDN/static cache；服务端返回 ETag/Cache-Control。
- 即使无需 auth，也要 per-IP rate limit 和 response size 上限。
- MCP 工具层禁 JSON-RPC batch 是对的，但还需要匿名全局 token bucket。

---

## Medium

### M1. “所有入口走同一校验管线”措辞与 Source Gate 有冲突

位置：`specs/p0/02-command-validation-spec.md` §1, `specs/p0/09-command-source-model.md`

P0-2 写所有入口（WASM tick、MCP tool、REST API、admin CLI）走同一 “校验→应用” 路径。P0-9 又写 gameplay 指令默认只来自 WASM，MCP_Deploy/MCP_Query 不可提交 gameplay。

建议改为：所有“会写世界状态的内部 ServerRawCommand”走同一 validation/apply；外部入口先经过 Source Gate，不是所有外部入口都能构造 ServerRawCommand。

### M2. Host function buffer 写入合同需要更硬

位置：`DESIGN.md` §5.1, `specs/p0/04-wasm-sandbox-baseline.md` §3.2

当前写 `out_ptr/out_len` “host 写入结果后再次校验边界”。安全实现应在写入前验证 guest memory range：`out_ptr + out_len` 溢出检查、range within memory、alignment 若需要、响应截断策略、错误码。

建议增加 host ABI 安全规则：

- 所有 ptr/len 用 `u32`，先做 checked_add。
- 写入前验证 memory range；写入后只可验证实际 bytes_written ≤ out_len。
- 响应超过 out_len 返回 `BUFFER_TOO_SMALL(required_len)`，不得部分写入产生歧义。
- host function 不得 panic；错误转负数错误码并记审计。

### M3. seccomp/cgroup 规则偏实现级，但缺少“启动失败即安全失败”的验收

位置：`specs/p0/04-wasm-sandbox-baseline.md` §4

seccomp 白名单列得很细，但 Wasmtime/Cranelift/glibc/allocator 在不同内核和版本下需要的 syscall 可能变化。实现时常见失败是为了跑通而放宽 seccomp。

建议：

- 明确 seccomp profile 是 deny-by-default，新增 syscall 必须安全评审。
- CI 在目标 Linux kernel 上跑 sandbox smoke + malicious corpus。
- 生产启动时打印并 hash seccomp profile；profile 不匹配拒绝启动。

### M4. “无网络命名空间”表述有歧义

位置：`specs/p0/04-wasm-sandbox-baseline.md` §1, §4.3

“无网络命名空间”可能被理解为“不创建独立 netns”，也可能是“没有网络能力”。安全语义应为：sandbox 进程处于无外网接口的 isolated network namespace，且 seccomp 禁 socket/connect。

建议改文案为：`独立 network namespace，只有 loopback down 或无接口；不挂载宿主网络；seccomp 禁止 socket family`。

### M5. Prompt injection 字符集限制不足以覆盖所有 AI SDK 注入面

位置：`specs/p0/02-command-validation-spec.md` §6, `specs/p0/03-mcp-security-contract.md` §6

限制玩家名 `[a-zA-Z0-9 _-]` 是好的，但游戏内还会有 room name、version_tag、mod description、event text、chat/alliance name、market order note 等未来字段。只对玩家名做限制不够。

建议：

- 定义 `UntrustedString` 类型，所有玩家/服主/模组可控文本统一标注。
- AI SDK prompt renderer 必须结构化渲染 JSON，不拼自然语言摘要。
- 对所有 untrusted text 执行 length、charset 或 escaping contract。

### M6. 可见性缓存 HashSet per player 可能成为内存放大器

位置：`specs/p0/05-unified-visibility-policy.md` §5

每 tick、每玩家缓存 `HashSet<EntityId>`。500 玩家、500 drone/player、未来多房间/观战者情况下，内存可能膨胀。攻击者可通过扩张实体/视野源增加每 tick cache 成本。

建议：

- 定义 visibility cache 的内存上限和 eviction 策略。
- 优先缓存 room/region visibility bitmap 或 RoaringBitmap，而非每玩家 HashSet 无界增长。
- 观战者不应创建 per-spectator full visibility cache。

### M7. 部署编译队列缺少多账号/全局滥用控制

位置：`specs/p0/04-wasm-sandbox-baseline.md` §7, `specs/p0/03-mcp-security-contract.md` §5

每玩家 deploy 10/h，并发编译最多 5 个。但攻击者可注册大量账号；每个 5MB module、30s compile、512MB memory，会形成编译农场。

建议：

- 增加 per-IP / per-ASN / per-payment-or-trust-tier deploy 限流。
- 编译队列全局 admission control：队列长度、优先级、冷却、失败指数退避。
- 相同 module_hash 去重编译；恶意 hash blacklist。
- `swarm_validate_module` 与 `swarm_deploy` 共享编译预算，不能作为免费预编译通道。

### M8. Replay / TickTrace 隐私保留期与删除策略未定义

位置：`specs/p0/01-tick-protocol-spec.md` §6.3, `specs/p0/03-mcp-security-contract.md` §7, `specs/p0/05-unified-visibility-policy.md` §3.6

MCP audit 保留 90 天，但 TickTrace/FDB replay 的 retention、用户删除、封禁后访问、公开 Arena replay 的内部状态剥离没有统一数据保留策略。

建议：

- 为 TickTrace 定义 retention policy：World private trace、Arena public replay、admin trace 分别保留多久。
- 公开 replay 必须生成 sanitized artifact，不直接暴露原始 TickTrace。
- 删除/封禁/隐私请求如何影响 replay，需要产品和法律层面决策。

### M9. RuleMod 的 `state.players()` 聚合语义和可见性过滤矛盾

位置：`DESIGN.md` §8.7, `specs/p0/07-world-rules-engine.md`

模组状态查询写 “经可见性过滤——模组不能看到隐藏实体”，同时 `state.players()` / upkeep 示例需要遍历所有玩家扣维护费。若模组真的只看可见范围，会导致全局规则无法执行；若模组能看全局，则要承认它是 privileged world logic。

建议：

- 把 RuleMod 分为 `global_rule` 与 `player_visible_rule` 两类。
- `global_rule` 可看全局，但必须具备 capability、完整审计、不能把 hidden info emit 给玩家。
- `player_visible_rule` 才使用 `is_visible_to`。

---

## Informational

### I1. Wasmtime 版本锁定策略方向正确，但需要自动化依赖策略覆盖 rmcp / Bevy / Rhai

当前 P0-4 对 Wasmtime 有 CVE SLA 和 `cargo audit`。建议扩展到：

- `cargo audit` + `cargo deny` 覆盖 Rust workspace。
- 对 rmcp、bevy、rhai、wasmtime、wasmtime-wasi 设置 review owner。
- 记录 “允许 duplicate crate / banned crate / license” 策略。
- 对 npm/TS SDK 也要有 lockfile audit（pnpm/npm audit 或 osv-scanner）。

### I2. JSON schema `additionalProperties=false` 应在每个 command variant 上重复声明

P0-2 顶层写了拒绝额外字段，但每个 action variant 的 schema 也必须拒绝额外字段，否则 action 内可塞入未来实现误读的字段。

### I3. Error detail 字段不要把隐藏实体信息泄露给攻击者

P0-2 的 rejection detail 示例包含精确位置、距离。对自身实体/可见目标可以；对不可见或刚失去视野目标，应返回泛化错误，例如 `ObjectNotFoundOrNotVisible`，避免用 rejection reason 做探测 oracle。

### I4. Admin / Rollback 双人审批是好设计，但需要 break-glass 流程

P0-9 对 Rollback 需要两个 admin Ed25519 签名，这是好方向。还需定义紧急修复时的 break-glass、审计、事后复核，否则生产事故中容易被绕过。

### I5. Arena 与 World 的安全默认值应分别写成 profile

当前很多配置用文字说明 World/Arena 差异。建议提供两个 machine-readable 默认 profile，并在 CI 中验证：Arena 禁热更新、公开 replay 延迟、World public_spectate delay ≥ 50、Tutorial namespace 隔离等。

---

## 建议的阻断修复清单

进入实现前至少完成这些文档 patch：

1. 重写 P0-2/P0-8/P0-9 的 command schema 分层：`PlayerCommand` vs `ServerRawCommand` vs `ValidatedCommand`。
2. 修正 P0-4 WASM validation：检测 start section，定义 instantiation budget，补恶意样本。
3. 冻结认证模型：JWT-only 或 client-generated Ed25519 cert 二选一；Blake3 只做 hash，不称签名。
4. 给 simulate/dry-run/compile/tick transaction 增加全局预算、大小上限和压力测试。
5. 统一 MCP/game snapshot/view snapshot/spectator snapshot 的可见性边界。
6. 给 Rhai mod market 增加 hash pin、签名、lockfile、capability、TickTrace mod hash root。

修完以上 High/Critical 后，安全视角可降为 APPROVE_WITH_RESERVATIONS。当前不建议把 Phase 0 视作真正冻结。
