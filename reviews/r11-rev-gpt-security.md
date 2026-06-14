# R11 — rev-gpt-security 安全评审

评审范围：
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/design/tech-choices.md
- /data/swarm/docs/specs/p0/*.md

评审视角：已知漏洞模式匹配、API 滥用检测、供应链风险、DoS 放大面、REST/WS/MCP/沙箱边界。

## Verdict

REQUEST_MAJOR_CHANGES

总体方向正确：
- MCP 已从 gameplay controller 收敛为管理/查看/部署界面，不再暴露 `swarm_move` / `swarm_attack` 等直接动作工具。
- gameplay 指令默认只来自 WASM，且 Source Gate + server-injected auth context 的方向正确。
- WASM sandbox 有 fuel、epoch interruption、cgroup、seccomp、WASI 禁用、模块体积/输出大小限制等基本防线。
- 可见性策略尝试统一到 `is_visible_to()`，避免常见 REST/WS/MCP 输出面不一致导致的信息泄漏。

但 P0 仍有数个必须在实现前修正的安全设计缺口。最严重的是：
1. FoundationDB 事务与 Bevy 内存世界的原子性边界仍不清晰，当前伪代码暗示在 FDB 事务内按命令修改内存世界，提交失败再 restore；这在重试/副作用/Trace/缓存/模组 actions 存在时很容易产生不可回放或双执行。
2. `player_id` 同时出现在 RawCommand schema 中，而 P0-9 又要求客户端不可自报 `player_id`；若实现者照 P0-2 写，会形成经典 auth-confusion / IDOR 入口。
3. MCP / Web / REST 可见性与 `player_view=full` 的说明存在互相矛盾，可能让 AI MCP 查询拿到超过 WASM snapshot 的信息，形成 AI 玩家信息优势。
4. WASM sandbox baseline 中有若干 Wasmtime API/隔离假设过于乐观或可能不可实现，容易让实现退化为“看似沙箱，实际未启用限制”。
5. 供应链和 untrusted mod/script 模型还缺少可执行的依赖锁定、cargo-deny/audit 策略、Rhai 模组安装信任链与 capability manifest。

在修正 Critical / High 项前，不建议进入实现冻结。

---

## Critical

### C1. RawCommand 中允许客户端提供 `player_id`，与 Source Gate 设计冲突，存在 auth-confusion / IDOR 风险

位置：
- P0-2 §2 RawCommand: `player_id` 是字段，规则为“必须匹配已认证玩家”
- P0-9 §3.3 明确禁止客户端在 Command body 中自报 `player_id`，服务端覆盖

问题：
P0-2 的 RawCommand 示例把 `player_id` 放在命令体内。P0-9 则说 player_id 必须由服务端注入。两者如果分别被不同实现者参考，很容易出现：
- WASM 输出 `{ player_id: victim, ... }`，validator 读取 body player_id 而非 auth context。
- MCP/REST/Tutorial/TestHarness 复用同一 JSON schema 时，出现“客户端自报身份 + token 身份”双源身份。
- 审计日志记录 auth.player_id，但实际 validator 使用 command.player_id，导致审计显示无异常而世界状态被越权修改。

已知漏洞模式：IDOR / confused deputy / mass assignment。这里属于游戏引擎核心权限边界，不能靠“必须匹配”这类文字约束解决，必须在类型层面消除。

建议：
- Command body 中删除 `player_id` 字段；RawCommand 只包含 `{tick, sequence, action}`。
- 服务端封装为 `AuthenticatedCommand { auth: AuthContext, raw: RawCommand }`。
- Validator 所有 ownership 判断只读 `auth.player_id`。
- JSON schema 对 WASM 输出显式 `additionalProperties: false`，并拒绝 `player_id`、`source`、`scope`、`auth` 等保留字段。
- P0-2、P0-8 IDL、P0-9 三处统一改名，避免 RawCommand/AuthenticatedCommand 混用。

### C2. Tick 原子性设计把 FDB 事务、Bevy 内存世界、RuleMod actions 混在一起，失败/重试时可能双执行或产生不可回放状态

位置：
- P0-1 §3.4 “整个阶段二包裹在 FoundationDB 事务中”，同时 `validate_and_apply(txn, command, world_state)` 修改世界状态
- P0-1 §3.4 提到 FDB rollback 不自动恢复 Bevy，需要 `world.restore(snapshot)`
- DESIGN §8.7 / P0-7 RuleMod actions 在 ECS system 中 `actions.apply(world)`，且记录 TickTrace

问题：
FDB 事务只覆盖 FDB 写入，不覆盖：
- Bevy World 内存突变
- RuleMod actions 的内存突变
- TickTrace 生成/审计副作用
- Dragonfly/NATS/ClickHouse 等外部副作用
- retry 时对随机数、events、metrics、refund credit 的重复计算

当前设计靠 `world.restore(snapshot)` 补救，但没有定义：
- 事务重试时是否重新执行全部 ECS systems / RuleMod hooks。
- RuleMod `actions.emit_event`、metrics、refund credit、degraded 标记是否随 rollback 一起回滚。
- FDB commit unknown（网络断开，客户端不知道提交是否成功）时如何避免同一 tick 被再次提交。
- TickTrace write fail 时 P0-1 又允许 tick 执行完成但审计日志不完整，这与“可回放/反作弊”核心安全目标冲突。

攻击/故障后果：
- 玩家可通过触发边界故障制造 fuel refund、resource award、RuleMod award 的重复执行。
- FDB commit unknown 后重复执行同一 tick，可能造成经济复制或 TickTrace 不一致。
- Replay 无法证明世界状态，因为记录的 command 与实际 RuleMod/side-effect 序列不一致。

建议：
- 把 EXECUTE 改为纯函数式 staging：`WorldBefore + OrderedCommands + RuleSet + Seed -> ExecutionPlan { world_after, tick_trace, metrics, cache_delta }`。
- FDB 事务只写入 staged result，且必须包含幂等键：`/tick/{N}/commit_id`、`/tick/{N}/state_checksum`，使用 compare-and-set 防重复提交。
- 事务提交成功前禁止任何外部副作用；ClickHouse/NATS/Dragonfly 只能消费已提交 tick record。
- FDB commit unknown 时先按 tick key 查询是否已提交，不得盲目重放。
- TickTrace 必须与 state 同事务提交；若 TickTrace 不可写，本 tick 应 abandon，而不是“tick 完成但不可回放”。
- RuleMod actions 必须进入 ExecutionPlan，不得在 commit 前直接产生不可回滚副作用。

### C3. WASM `tick()` 返回指针 ABI 不足以安全读取输出，可能导致越界读/悬垂指针/输出混淆

位置：
- P0-4 §3.1 / P0-8 host_functions.tick: `tick(ptr, len) -> i32`，返回值是指令 JSON 指针

问题：
返回单个 `i32` 指针没有输出长度，也没有 allocator/free 协议。Host 无法可靠知道：
- JSON 输出长度在哪里。
- 指针是否在 linear memory 内。
- 指针是否指向未初始化/已释放/可变区域。
- 玩家是否返回超长输出但诱导 host 扫描内存直到 256KB。

这类 ABI 错误常见于 WASM embedding 安全事故：host 以为在读受限 buffer，实际进行了 OOB 检查缺失、长度推断、重复 borrow 或 DoS 扫描。

建议：
- ABI 改为 host-owned output buffer：`tick(snapshot_ptr, snapshot_len, out_ptr, out_cap) -> i32 len_or_error`。
- 或返回 `u64` 打包 `(ptr:u32,len:u32)`，并强制 `len <= 256KB`、`ptr+len` checked_add 后在 memory bounds 内。
- 定义 memory ownership：WASM 不需要 free host buffer；若 WASM 分配，则必须导出 `alloc`/`dealloc` 且 host 检查。
- 恶意样本库加入：返回负数、返回最大 i32、ptr+len overflow、len=256KB+1、返回指向 snapshot 输入区、返回非 UTF-8。

---

## High

### H1. MCP/Web/REST 可见性与 `player_view=full` 存在矛盾，可能给 AI 玩家超过 WASM 的信息

位置：
- DESIGN §8.2: `player_view="full"` 表示玩家实时看到全地图
- P0-5 §3.5: `player_view` 影响“玩家屏幕 / MCP”，但 WASM snapshot 始终 `is_visible_to(player)`
- P0-3 §1: MCP 提供的信息量与 Web UI 等量，不更多不更少
- P0-3 §4.2: MCP `swarm_get_snapshot` 获取玩家可见世界快照，同 WASM tick 输入

问题：
文档同时表达了三件互斥的事：
1. MCP snapshot 与 WASM tick 输入完全相同。
2. `player_view=full` 影响 MCP。
3. WASM snapshot 始终受 `is_visible_to` 过滤。

如果实现让 AI 通过 MCP 在 `player_view=full` 世界看到全地图，但其 WASM tick 只看到 fog-of-war，AI 玩家可以在每 tick 通过 MCP 获取全图，再生成/部署代码或调整策略，形成超出人类/沙箱公平模型的信息优势。

建议：
- 拆分 API：`swarm_get_drone_snapshot` 必须与 WASM tick 输入完全一致；`swarm_get_player_view` 是 UI/观战视图，永不用于 AI 决策保证公平的模式。
- World 默认下 MCP_Query 不得超过 WASM snapshot；若某世界允许 full view，必须在世界规则中明确“这是非公平/教学/合作模式”。
- `swarm_get_available_actions`、`dry_run`、`simulate` 也必须绑定 snapshot_id，不能使用 full-view 数据。

### H2. `swarm_simulate` / `swarm_dry_run_commands` 可能成为高放大 DoS 与信息推断通道

位置：
- P0-3 §4.4 `swarm_simulate` 5/tick，World；3/tick，Arena
- P0-6 §3.1 `swarm_dry_run_commands`
- P0-9 Simulate budget: `0.5× MAX_FUEL`

问题：
Simulate/DryRun 是典型 DoS 放大接口：最小请求可触发路径搜索、validator、ECS、规则系统、甚至多 tick 预测。当前只给“5/tick”这类频率限制，未限制：
- 每次 simulate 的 tick 数、实体数、command 数。
- 是否执行 path_find / RuleMod / visibility recompute。
- 是否可并发。
- snapshot 是否由用户选择历史 tick 造成缓存穿透。
- dry-run rejection detail 是否可用于探测隐藏实体或资源。

建议：
- `swarm_simulate` MVP 阶段不对在线服务器开放；只做本地 CLI。
- 若必须开放：限制 `max_ticks <= 10`、`max_entities <= visible_entities`、`max_commands <= 100`、每玩家单飞（no concurrent simulate）、全局 worker pool。
- dry-run 必须只基于调用者当前可见 snapshot，不得返回隐藏实体存在性差异；对不可见目标统一 `ObjectNotFoundOrNotVisible`。
- 对 simulate/dry-run 单独计费/冷却，失败也计费。

### H3. Wasmtime sandbox 配置含疑似不可用/过时 API 和危险假设，可能导致限制未真正生效

位置：
- P0-4 §2.2 Wasmtime config 伪代码
- tech-choices §2 选择 Wasmtime，强调 fuel/epoch/per-tick fork

问题：
若实现者照抄伪代码，可能出现编译不过后“临时删掉限制”的风险。可疑点包括：
- `fuel_consumed_callback` 不是常见稳定 Wasmtime Config API；fuel 通常通过 Store fuel/limiter 管理。
- `dynamic_memory_reserved_for_growth(0)`、`max_wasm_memory_pages` 等 API 需按具体 Wasmtime 版本核实。
- `wasm_simd(true)` 开启 deterministic 风险需进一步论证；不同 CPU SIMD 路径是否完全确定要测试。
- `epoch_interruption` 需要宿主线程定期 increment epoch；只开启 config 不会自动超时。
- “每 tick fork -> kill” 与 “模块缓存按 module_hash 缓存编译结果”并存，需要定义 cache 在父进程还是 worker，避免每 tick JIT 编译 DoS。

建议：
- P0-4 改成版本钉死后的真实可编译配置片段，并在 CI 中编译验证。
- 明确 Store fuel 初始化、fuel 耗尽 trap 处理、epoch increment 线程、timeout 后 worker kill 顺序。
- 默认关闭 SIMD，直到跨平台 determinism 测试覆盖 x86_64/aarch64 后再开启。
- 沙箱 baseline 增加“限制生效测试”：fuel 超限、epoch 超时、memory 超限、table 超限必须在 CI 断言。

### H4. seccomp 白名单与 Wasmtime/JIT 实际需求不匹配，存在上线时放宽到危险配置的风险

位置：
- P0-4 §4.1 seccomp whitelist

问题：
Wasmtime/Cranelift/JIT 运行时可能需要比文档更多 syscall，例如 `rt_sigprocmask`、`gettid`、`sched_yield`、`prlimit64`、`close`、`fcntl`、`readlink`、`getrandom`（某些初始化路径）、`clock_gettime`（runtime/parking_lot/tokio 路径）等。文档中直接禁 `clock_gettime`、`getrandom` 是合理目标，但必须验证实际 binary 在 seccomp 锁定前完成所有初始化。

如果实现阶段发现崩溃，常见结果是“临时允许 open/socket/clock_gettime”，安全边界被破坏。

建议：
- 把 sandbox worker 分成 pre-seccomp 初始化阶段和 locked execution 阶段。
- 用 `strace`/seccomp notify 生成最小 syscall profile，纳入 P0 文档。
- CI 对恶意 WASM 断言：open/socket/clock/random 均返回拒绝或 trap。
- 明确 Unix socket fd 是否在 seccomp 后仍允许 read/write，但禁止 connect/socket。

### H5. `__wasm_call_ctors` / active data segments 描述错误，模块初始化边界不清

位置：
- P0-4 §2.4 “检查无 init 函数（__wasm_call_ctors, active data segments 预执行）”

问题：
active data segments 不是“预执行函数”，而是实例化时初始化 linear memory。禁止 `__wasm_call_ctors` export 也不足以禁止 start section；WASM start function 是模块 section，不一定以 `_start` export 形式出现。若目标是“实例化不得执行用户代码”，需要检查 start section/imports，而不只是 exports。

建议：
- 使用 wasmparser 显式拒绝 StartSection。
- 区分 `_start` export、WASI command 模式、`__wasm_call_ctors`、start section、active/passive data segments。
- 若允许 active data segments，限制总 data size 且计入模块体积/内存初始化预算。

### H6. Rhai RuleMod 信任边界过宽，供应链风险没有闭环

位置：
- DESIGN §8.7 / P0-7 World Rules Engine
- tech-choices §3 Rhai “服主信任”

问题：
文档将 Rhai 定位为“服主信任”，但又有模组市场、社区安装、版本依赖。实际风险是供应链：恶意/被接管模组通过 `actions.award_resource`、`damage_entity`、`set_entity_flag` 操纵经济或植入后门。当前缺少：
- 模组签名与发布者身份。
- capability manifest：模组声明可调用哪些 actions、作用于哪些 entity/player/resource。
- 安装前 diff/review 流程。
- semver pin / lockfile / reproducible package hash。
- 冲突/依赖解析安全策略。

建议：
- 每个 mod 包含 `capabilities = [...]`，默认最小授权；例如只读 state、经济扣费、伤害实体分别授权。
- world.toml 锁定 `name/version/hash/publisher_key`，启动时校验签名与 hash。
- 模组市场只分发不可变版本；更新必须显式批准。
- RuleMod actions 经过 mini-validator 还不够，应进入同一 ExecutionPlan 与 TickTrace。

### H7. HTTP/MCP Origin 策略会误伤非浏览器客户端，且缺少 CSRF / token binding 细节

位置：
- P0-3 §5.3 “非浏览器客户端拒绝缺失 Origin”
- P0-3 §2 HTTPS + mTLS

问题：
Origin 是浏览器安全信号，CLI/AI agent/mcp client 通常没有 Origin。文档说“非浏览器客户端拒绝缺失 Origin”，这会迫使客户端伪造 Origin，削弱语义。另一方面，如果 token 存在 cookie 中，仅靠 Origin 白名单也不足以覆盖 CSRF/SSE 重连等情况。

建议：
- 浏览器路径：SameSite=Lax/Strict cookie + CSRF token + Origin/Referer 校验。
- 非浏览器路径：Authorization: Bearer 或 mTLS client cert，不要求 Origin，但要求 audience、scope、jti、rate limit。
- SSE 只读连接也要认证，禁止 token 出现在 query string，防日志泄漏。

### H8. 部署签名方案文字混乱：服务端生成临时 Ed25519 私钥不符合常规威胁模型

位置：
- P0-3 §1.1 “public_key: Ed25519 — 服务端生成的临时密钥对”
- P0-3 §1.1 部署 WASM 时“客户端附带证书 + 私钥签名”

问题：
如果私钥由服务端生成再交给客户端，需要安全传输/存储私钥；如果服务端持有私钥，客户端如何签名不清楚。更常见模型是客户端生成 keypair，服务端签发 certificate 绑定 public key；或者完全不使用客户端签名，直接用 bearer token + TLS 上传。

建议：
- 二选一明确：
  1. 客户端生成 ephemeral Ed25519 keypair，服务端签 public key 证书；客户端用私钥签 WASM hash。
  2. 不做客户端签名，服务端基于 OAuth token 接收 WASM，计算 module_hash 并绑定 session。
- 不要写“服务端生成私钥给客户端”，除非有专门密钥交付协议。

---

## Medium

### M1. JSON Schema 描述有误：数组没有“顶层字段”，`additionalProperties` 需放在 Command object 上

位置：
- P0-2 §1.1 顶层数组 schema + `additionalProperties: false`

问题：
顶层是 array，`additionalProperties` 对 array 无效。应在 Command / Action object definitions 上定义 `additionalProperties: false`。

建议：
- P0-8 IDL 生成 draft 2020-12 schema，并测试未知字段被拒绝。
- 对 Action union 使用 discriminator，避免 `{type:"Move", target_id:...}` 这类混合字段被吞掉。

### M2. `sequence` 单调递增规则未定义重复/缺口/溢出行为

位置：
- P0-2 §2 `sequence` 每玩家每 tick 单调递增

风险：
重复 sequence、缺口、u32 溢出、同 sequence 不同 commands 如果处理不一致，会破坏 determinism 或造成 replay mismatch。

建议：
- 明确：每 tick sequence 必须唯一；重复 sequence 全部拒绝或保留第一条，必须 deterministic。
- 排序 key 加入 `command_hash` 作为最终 tie-breaker 或在 schema 阶段拒绝重复。

### M3. Blake3 keyed hash 被称为“代码签名/MAC”容易误导为可公开验证签名

位置：
- tech-choices §8 “代码签名: Blake3 MAC”

问题：
MAC 需要共享密钥，不能替代 Ed25519 这种公开可验证签名。文档后面又使用 Ed25519 证书，概念混用。

建议：
- 把“代码签名”改为“module_hash/content MAC（服务端内部完整性）”。
- 对客户端/发布者可验证身份一律使用 Ed25519 signature。

### M4. `world_seed = Blake3(32随机字节)` 与“不可预测当前 tick 顺序”依赖 seed 保密，但 seed 泄露后的公平性未定义

位置：
- DESIGN §8.8 / P0-1 §3.1

问题：
如果 world_seed 在 admin trace、crash dump、replay、logs 中泄露，玩家可预测未来 tick ordering。虽然不是直接越权，但影响公平。

建议：
- 每 tick shuffle seed 使用 server secret + world_seed + tick，通过 HMAC/Blake3 keyed hash 派生。
- world_seed 可用于 replay，secret 不公开；公开 replay 可延迟揭示或记录 per-tick committed seed。
- 或明确 Arena 赛后才公开 seed，World 永不公开。

### M5. PathFind / visibility cache 需要防 cache key 被隐藏信息污染

位置：
- P0-2 §4.3 path cache `(from,to,terrainhash)`
- P0-5 §5 可见性缓存

风险：
如果 path cache 不包含 world rules、dynamic blockers、player visibility mode，可能返回穿越隐藏动态障碍的路径或泄露敌方单位阻挡信息。

建议：
- PathFind 对 WASM 查询默认只基于公开 terrain + visible blockers；不可见 enemy 不应影响结果，或统一作为 unknown cost。
- cache key 包含 `tick`、`player_id`、`visibility_hash`、`terrain_version`、`rules_hash`。

### M6. Tutorial source 与正式玩家身份/资源的隔离还需更硬的 namespace 约束

位置：
- P0-9 §2.4

建议：
- Tutorial world 使用独立 FDB prefix、独立 auth audience、独立 module namespace。
- 禁止 Tutorial module_hash 被 promote 到 World，必须重新 deploy/validate。

### M7. `swarm_get_docs` / `swarm_get_schema` 无限制可能成为带宽和 prompt-injection 载体

位置：
- P0-3 §4.4 schema/docs 无 scope 或无限制

风险：
大文档重复拉取是低成本带宽 DoS；docs 中如果含社区内容或 mod 描述，也可能成为 AI prompt injection carrier。

建议：
- 对 unauthenticated docs/schema 也加 IP 限速、ETag、压缩、最大响应大小。
- 社区/模组文档字段标记 untrusted，不与 system/developer 指令混合。

### M8. NATS / WS broadcast 缺少 backpressure 和 per-subscriber 队列上限

位置：
- P0-1 §4.2 / DESIGN §7

风险：
慢 WebSocket 客户端可造成内存积压；NATS delta fanout 在断线/重连风暴中放大。

建议：
- 每连接 bounded queue，超过后丢弃并要求 client fetch snapshot。
- delta 消息含 sequence/tick，客户端 gap 后主动 fetch。
- 网关按 player/session 做订阅权限过滤，避免 wildcard subject 泄露。

---

## Informational

### I1. Bevy 供应链风险主要是成熟度/API churn，而非已知 CVE 历史

Web 检索未发现 Bevy 本体有显著 CVE 记录；主要风险是引擎年轻、API 变化快、插件生态质量不均。建议：
- 锁定 Bevy minor 版本。
- 不在 authoritative simulation 中使用 Bevy rendering/input/audio 子系统。
- `cargo deny` 禁止重复版本和 yanked crates。

### I2. Wasmtime 有持续安全公告历史，版本 pin 是必要但不充分

Web 检索显示 Wasmtime/RustSec 有多条安全公告，且 2026 年仍有批量 advisories。P0-4 的 CVE SLA 是正确方向，但还需要：
- `cargo audit` / RustSec advisory DB 在 CI 中强制执行。
- 安全升级演练：升级 Wasmtime 后 replay 不依赖重新执行 WASM，这是正确设计，应保留。
- 对 JIT/sandbox 逃逸类 CVE 准备临时停服/禁部署/切 interpreter backend 的应急策略。

### I3. rmcp 是新兴 SDK，风险在协议栈和默认 transport 配置

未检索到明确 rmcp CVE，但新 SDK 风险包括：默认暴露 prompts/resources、tool schema 宽松、HTTP/SSE CORS、batch handling。当前 P0-3 禁 JSON-RPC batch 是好决定。建议额外：
- MCP server 默认绑定 127.0.0.1，仅经 gateway 暴露。
- rmcp 版本锁定，生成 SBOM。
- 所有 tool params 走 JSON schema + size limit + unknown-field reject。

### I4. FoundationDB 运维安全未展开

建议后续补充：
- FDB TLS、cluster file 权限、backup/restore 演练。
- Tenant/prefix ACL，防 dev/test/tutorial/world 互相污染。
- Snapshot backup 加密与 replay privacy 绑定。

### I5. ClickHouse 审计日志“不可修改”需要 WORM/权限设计支撑

ClickHouse MergeTree 表本身不是不可篡改。若审计日志用于反作弊，需要：
- append-only service account。
- 定期 hash chain / external notarization。
- 管理员查询与删除权限分离。

---

## 必须修改清单（进入实现前）

1. 统一 Command 类型：删除 body `player_id`，引入 `AuthenticatedCommand`，validator 只读 auth context。
2. 重写 Tick commit 协议：staged ExecutionPlan + FDB 单事务提交 state/trace/metrics + commit unknown 幂等处理。
3. 修正 WASM ABI：返回 `(ptr,len)` 或 host-owned buffer，并定义内存 ownership。
4. 明确 MCP `get_snapshot` 与 `player_view=full` 的关系，保证 AI MCP 不获得超过 WASM snapshot 的公平信息。
5. 给 `simulate/dry_run` 设硬预算、snapshot-bound、并发上限和隐藏信息统一错误。
6. 用真实 Wasmtime 30.0 API 写可编译 sandbox config，并在 CI 验证 fuel/epoch/memory/seccomp 限制真的生效。
7. RuleMod 增加签名、lockfile、capability manifest，并让 actions 进入 tick ExecutionPlan。
8. 修正客户端代码签名模型，不再使用“服务端生成私钥给客户端”的模糊描述。

结论：设计已避开了“AI 通过 MCP 直接操控游戏”的最大架构坑，但安全边界仍需要类型化、事务化和可执行化。现在的问题不是方向错，而是多个关键边界仍停留在文字约束；实现时一旦由不同模块分别解释这些文档，很容易出现 IDOR、信息泄漏、DoS 放大和不可回放状态。
