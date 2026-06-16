# R1 安全审计评审 — rev-gpt-security

Reviewer: rev-gpt-security (GPT-5.5)
视角: 已知漏洞模式匹配 / API 滥用检测 / 供应链风险嗅探 / DoS 向量
输入文档:
- `/data/swarm/docs/design/DESIGN.md`
- `/data/swarm/docs/design/tech-choices.md`
- `/data/swarm/docs/ROADMAP.md`
- `/data/swarm/docs/specs/` 下 P0 规格文档（用户给出的 `/data/swarm/docs/specs/p0/` 当前不存在；本次实际读取 `01`–`09` specs）

## Verdict

REQUEST_MAJOR_CHANGES

设计方向总体正确，尤其是“AI 与人类同走 WASM”、“MCP 不做 gameplay action”、“Source Gate + server-injected auth context”、“WASM 进程隔离 + fuel + cgroup/seccomp”、“统一可见性函数”等安全基线都抓住了核心风险。

但在进入实现冻结前，仍有几个需要阻断的安全设计问题：

1. `Overload` 在不同文档中的安全约束不一致，部分规格仍允许无 range / 无 visibility 的 player-level 逻辑攻击。这是典型远程 DoS / griefing 放大器。
2. MCP HTTP/SSE 安全合同对 browser/non-browser Origin、loopback MCP、DNS rebinding 的边界还不够闭合；结合 rmcp/MCP 已出现过 DNS rebinding 类 advisory，必须把 Host/Origin/mTLS/token 绑定写成不可绕过的 transport contract。
3. WASM 部署签名模型把“服务端签发证书”和“私钥签名 WASM bytes”描述混在一起，存在密钥托管边界不清的问题；如果服务端生成并持有/下发私钥，会把认证系统变成高价值密钥集中点。
4. 输入大小、命令数量、JSON batch 限制在不同 specs 中互相冲突，会直接导致实现时选择较宽松值，形成 DoS 面。

结论：不是 REJECT。核心架构可救，而且已有大量好设计。但必须先修正文档合同中的高危不一致与边界模糊，否则实现会把“安全意图”稀释成多个绕过路径。

## Critical

无明确 Critical。

未发现“设计本身必然导致沙箱逃逸 / 任意代码执行 / 跨玩家直接接管”的不可修复问题。WASM mutating host function 禁止、进程隔离、Source Gate、统一可见性、Admin 统一管线这些关键防线都已存在。

## High

### H-1: `Overload` 约束不一致，可能成为跨地图 fuel DoS / griefing 原语

证据:
- `DESIGN.md` 特殊攻击表中写明 Overload 必须满足 `is_visible_to(target, attacker)`、同一目标 50 tick 全局冷却、静默结果，防信息泄露。
- `specs/02-command-validation-spec.md` §3.12 写成“无 range 限制——Overload 是逻辑攻击”，校验表仅包含 `target_player`、`enemy_target`、`target_fuel_above`、`fatigue`、`OnCooldown`，没有 visibility requirement。
- `specs/08-game-api-idl.md` 的 Overload validator 同样没有 `visible_target` / `is_visible_to` / target global cooldown。

攻击模式:
- 最小请求: 一个拥有 RangedAttack 的 drone 每 tick/每冷却提交 Overload。
- 最大服务端影响: 直接削减目标玩家 fuel budget，影响目标所有 WASM 执行，而不是单个实体局部战斗。
- 如果不要求可见性/空间关系，攻击者可在地图任意处通过 player_id 选择目标，形成“排行榜查人 → 逻辑打击”的跨地图骚扰。
- 如果只有 per-drone cooldown，没有 per-target global cooldown，大号玩家可用大量 drone 对同一目标叠加压力；即使有 20% 下限，也足以持续压制新手或竞赛对手。

影响:
- Gameplay 层面是 DoS primitive。
- 安全层面是计算资源预算被敌方远程操纵，破坏 fuel metering 的公平性。
- 信息侧信道: `TargetFuelTooLow`、不同效果量、冷却反馈都可能泄露目标 fuel 状态或是否在线。

建议:
- 在所有 specs 中统一 Overload 合同:
  - 必须 `is_visible_to(target_player_or_target_entity, attacker_player)`。
  - 最好绑定到可见实体目标，而不是裸 `PlayerId`；例如 `target_id: ObjectId`，由实体 owner 推导 player。
  - 同一 target player 每 50 tick 最多受一次 Overload，跨来源全局冷却。
  - 结果对攻击者恒定返回 `Accepted` 或泛化拒绝，不暴露目标当前 fuel / 是否已低于阈值。
  - Arena 中 Overload 是否允许应赛制锁定；World 中建议默认关闭或大幅提高成本。
- `specs/02`、`specs/08`、`DESIGN.md` 必须同步，IDL validator 增加 `visible_target` 与 `target_global_cooldown`。

### H-2: MCP transport 安全边界仍可能落入已知 DNS rebinding / loopback tool server 攻击模式

证据:
- MCP Server 默认绑定 `127.0.0.1:{port}`，经 nginx/gateway 暴露 HTTP/SSE。
- `specs/03-mcp-security-contract.md` 有 Host header 强制、CORS Origin 白名单、JSON-RPC batch 禁用。
- 但同一表写“非浏览器客户端拒绝缺失 Origin”，这和 mTLS/CLI/agent 客户端的实际 HTTP 行为冲突，容易诱导实现者做例外分支。
- Web 搜索显示 MCP/Rust SDK 生态已有 DNS rebinding 类 advisory（恶意公共网站向 loopback/private-network MCP server 发送 authenticated requests）。这与“本地绑定 + HTTP/SSE + 浏览器可触达”的风险形态高度相似。

攻击模式:
- 恶意网页利用浏览器访问 `localhost` 或私网地址的能力，尝试命中 MCP endpoint。
- 如果 token 存储在浏览器上下文、Origin 校验实现有例外、Host header 被代理重写不严谨，可能触发 AI 工具调用、读取 snapshot/debug 信息或部署恶意 WASM。
- SSE/HTTP 长连接还可用于连接耗尽。

影响:
- AI/玩家账号被跨站驱动读取调试数据或部署代码。
- MCP debug scope 可能泄露 tick explanation、profile、replay 等策略情报。
- 如果 `swarm_validate_module` / `swarm_deploy` 走同一 gateway，可能成为供应链植入入口。

建议:
- 明确拆分 browser 与 non-browser transport:
  - 浏览器 Web UI: CSRF token + SameSite=strict cookie 或 Authorization header 禁止自动附带；严格 Origin + Fetch Metadata (`Sec-Fetch-Site`)。
  - MCP agent/CLI: mTLS 或 signed request；不依赖 Origin；明确拒绝带 browser fetch metadata 且 Origin 不在白名单的请求。
- Host header、SNI、audience、token `aud` 必须绑定到同一 public origin；gateway 不得仅依赖 upstream 的 rewritten Host。
- 对 loopback/private-network MCP endpoint 增加 DNS rebinding 防护测试：恶意 Origin、缺失 Origin、伪造 Host、proxy rewritten Host、CORS preflight 绕过、SSE reconnect。
- `swarm_get_docs/schema` 虽然“无 scope”，仍需全局限流和 body/response caps，防止文档接口成为反射/带宽放大器。

### H-3: WASM 代码签名/短期证书模型混淆，私钥边界不清

证据:
- `specs/03` 认证流程写“服务端签发证书”，证书含 `public_key`，但也写“服务端生成的临时密钥对”。
- 部署 WASM 时要求“客户端附带证书 + 私钥签名(Blake3(WASM bytes))”。
- `specs/09` 又写“为何不用客户端 keypair：新手友好”，但仍要求客户端用私钥签名。

风险:
- 如果服务端生成密钥对并把 private key 下发给客户端，则服务端成为所有玩家短期私钥的生成者/潜在持有者；一旦 auth service compromise，可签任意玩家部署。
- 如果客户端不真正持有私钥，只是 bearer token，则“WASM bytes signature”提供的是伪安全感。
- 如果证书和 signing key 生命周期与 OAuth refresh token 混在一起，吊销/轮换语义会混乱。

影响:
- 凭证泄露响应困难：到底撤销 jti、证书 fingerprint、session、module hash 还是 signing key？
- 审计不可否认性弱：服务端生成过私钥时，签名不能证明客户端实际授权了某个 WASM。
- 实现者可能退化为“token + unsigned wasm”，与设计中签名审计目标不一致。

建议:
- 二选一并写死合同:
  1. 客户端生成 Ed25519 keypair，服务端只签 public key 证书；private key 永不离开客户端。部署由客户端私钥签 `BLAKE3(wasm_bytes || player_id || world_id || nonce || exp)`。
  2. 不做客户端签名，采用短期 bearer token + TLS/mTLS + server-side module hash audit；删除“私钥签名”表述，避免误导。
- 每次部署加入 nonce / replay protection，证书 `aud = world_id/gateway_origin`，签名覆盖 `module_hash`、`player_id`、`world_id`、`version_tag`、`timestamp`。
- Tick 执行阶段检查 `module_hash` 与已认证部署记录绑定，而不是只看玩家当前模块。

### H-4: 输入大小和命令数量限制冲突，会导致 DoS 防线实现漂移

证据:
- `specs/02` §1.1: `maxItems=100`、总字节数 ≤ 256KB。
- 同一文件 §6 批级校验: 单条指令 ≤64KB，整批 ≤1MB，每 tick 每玩家 ≤500 条指令（含 Admin）。
- `specs/04` ABI: CommandIntent JSON `len <= 256KB`。
- MCP HTTP max body size 5MB 与 WASM module size 一致，但工具如 `swarm_simulate`、`swarm_dry_run_commands` 的请求体上限未独立定义。

攻击模式:
- 玩家构造接近 1MB / 500 commands / 深度 10 的 JSON，触发 serde parse、schema validation、rejection detail 生成、TickTrace 写入、ClickHouse audit 写入。
- 如果每玩家 500 commands × 500 players，单 tick 可形成 250k command validation 压力，与 3s tick 目标冲突。
- Rejection detail 若记录完整 RawCommand，攻击者可放大存储与日志成本。

影响:
- CPU / 内存 / FDB write / ClickHouse audit 多层放大。
- 实现团队可能按更宽松值落地，因为文档中都出现过。

建议:
- 选择一个权威上限并全仓统一。建议 P0:
  - `MAX_COMMANDS_PER_PLAYER = 100/tick`。
  - `MAX_TICK_OUTPUT_BYTES = 256KB`。
  - `MAX_COMMAND_BYTES = 16KB` 或更低。
  - `MAX_REJECTION_DETAIL_BYTES` 单独限额，RawCommand 在审计中 hash + truncated body。
- Admin 不应默认 500/tick；Admin bulk operation 应走离线 maintenance job，不进入实时 tick pipeline。
- 对 `swarm_simulate`、`swarm_dry_run_commands` 设置独立 body cap、CPU cap、output cap。

## Medium

### M-1: Wasmtime 版本策略过于乐观，`=30.0` pin 与 2026 级 sandbox escape 风险需要更硬的升级/隔离合同

证据:
- 技术选型选择 Wasmtime，依赖锁定 `wasmtime = "=30.0"`，CI `cargo audit`，严重 CVE 72h SLA。
- Web 搜索显示 Wasmtime 生态存在 2026 年 Critical sandbox escape / Cranelift miscompile 类 advisory，且部分与 aarch64 后端相关。

风险:
- Wasmtime 是高价值 TCB。即使有 cgroup/seccomp，JIT/runtime sandbox escape 仍可能落到 OS 进程边界；seccomp profile 若允许 `mmap/mprotect` 等 JIT 必需 syscall，逃逸后攻击面仍非零。
- pin 版本可保证确定性，但会延迟安全更新。文档虽写 SLA，但缺少“紧急禁用玩家 WASM / 切换 interpreter / 禁用特定 backend/arch”的运行时开关。

建议:
- 在 DESIGN/ops 中加入 Wasmtime emergency playbook:
  - 可按世界/全局暂停新部署、暂停所有 WASM tick、切换到安全版本重编译缓存。
  - 记录 runtime backend/arch，aarch64/x86_64 分开评估。
  - 若使用 Cranelift JIT，明确禁用 Winch 或其他 backend（除非评估通过）。
  - 预编译缓存必须包含 `wasmtime_version + target_arch + compiler_backend + config_hash`。
- seccomp profile 需要按“编译进程”和“执行进程”分离；执行进程不应拥有编译/JIT 所需的更宽 syscall。如果 tick 时只实例化已预编译模块，尽量把编译放在独立更高风险 sandbox。

### M-2: `swarm_simulate` / dry-run 是典型最小请求最大开销接口，预算不足

证据:
- MCP tools 中 `swarm_simulate` 为 `swarm:read`，World 5/tick / Arena 3/tick。
- MVP 文档鼓励本地模拟 5000 tick，但 MCP simulate 的未来 tick 数、实体数、输出大小没有明确上限。

攻击模式:
- 发送一个合法 snapshot-bound simulate 请求，请求预测大量 tick 或复杂路径/战斗，服务器消耗远高于普通 read。
- 如果 simulate 复用真实 validator / ECS systems，可能抢占 tick CPU 或引发缓存污染。

建议:
- MCP 线上 `swarm_simulate` 只允许小步 dry-run，例如 `max_ticks <= 10`、`max_entities <= visible_entities_cap`、`max_output <= 256KB`。
- 5000 tick 模拟只允许本地 CLI 或异步 job queue，不应在实时 engine process 内执行。
- simulate 必须运行在 snapshot copy + separate worker pool，不能占用 tick scheduler 的 runtime。

### M-3: RuleMod/Rhai “可信服主”模型与第三方 git 模组供应链仍有缺口

证据:
- 第三方模组通过任意 git 仓库安装，mods.lock 记录 rev，可选 checksum。
- 后续 spec 增加 `.sig` Ed25519 签名，未签名拒绝加载。
- 但 DESIGN 主文仍说 checksum 可选，安装命令示例默认 `git pull + checkout tag`。

风险:
- tag force-push / repo compromise / transitive dependency 模组更新仍可能进入世界。
- `mod.toml` config 的 min/max/type 若被篡改，可能把资源、cooldown、budget 调到 DoS 或经济破坏状态。

建议:
- 将 checksum 从“可选”改为“必需”。`mods.lock` 必须包含每个文件 Merkle hash 或 tarball hash。
- `swarm mod update` 默认只更新 lock，不自动启用；需要 diff review。
- 签名覆盖 `mod.toml`、所有 `.rhai`、生成的 normalized manifest，以及 declared permissions。
- 增加 mod capability manifest：每个模组声明需要哪些 actions（deduct/award/damage/set_flag），默认最小授权。

### M-4: 可见性策略总体好，但 `player_view=full` + MCP 只读查询需要更强隔离声明

证据:
- `specs/05` 写 `player_view = full` 时玩家屏幕 / MCP 可见全地图，但 WASM snapshot 仍按 `is_visible_to`。
- 教学/合作世界使用 full。

风险:
- 如果 MCP agent 同时是代码生成者，给它 full map 只读信息，即使 WASM snapshot 受限，agent 可把全图信息编译进下一版 WASM 策略，形成 out-of-band 情报注入。
- 这在教学世界可接受，在任何与正式世界互通的世界不可接受。

建议:
- 明确: 任何 `player_view=full` 的世界不得与正式 World/Arena 互通，不计排名，不允许资源/资产迁移。
- MCP `swarm_get_snapshot` 应默认返回 drone-equivalent view；full view 应是单独 tool/scope，例如 `swarm:spectate`，且禁止 deploy scope 同时持有 full realtime spectate scope。
- Arena 赛后 full replay 与 deploy token 必须时间隔离。

### M-5: FDB TickTrace / audit 记录完整参数，存在隐私与日志注入风险

证据:
- MCP audit 表记录 `parameters String`、`result String`。
- TickTrace 记录 RawCommand / rejection detail。
- 玩家原创字符串允许有限字符集，但 WASM 输出、version_tag、module metadata、docs/query 参数等仍可能进入日志。

风险:
- 日志注入 / ClickHouse 查询污染 / 大字段 DoS。
- WASM module metadata 或 version_tag 可能包含敏感信息或恶意 payload。

建议:
- 审计日志字段结构化，所有 untrusted string 做 length cap + escaping。
- 大字段只存 hash + truncated preview。
- `version_tag` 使用严格字符集与长度限制。
- 对 ClickHouse retention 与玩家隐私写明数据分级。

## Informational

### I-1: Bevy 作为 ECS 不是主要安全 TCB，但版本漂移会影响 determinism

Bevy 本身更像调度/数据模型依赖，不直接暴露网络或 untrusted code。当前最大风险不是 CVE，而是小版本 API/调度行为变更影响 determinism。技术选型文档已承认 Bevy 年轻、API 变动较快。

建议:
- pin Bevy minor/patch。
- 每次升级跑 replay determinism corpus。
- 不依赖未指定顺序的 query iteration；文档已有 IndexMap 思路，应扩展到 ECS query ordering contract。

### I-2: rmcp 供应链需纳入 cargo audit + advisory watch

rmcp 是 MCP 协议实现层，风险集中在 HTTP/SSE、JSON-RPC parsing、tool schema、auth integration。当前 docs 有 transport contract，但 ROADMAP 只点名 Wasmtime CVE SLA，未显式覆盖 rmcp。

建议:
- 安全 SLA 覆盖 wasmtime、rmcp、tokio/hyper/axum、serde_json、rhai、bevy、nats client、foundationdb binding。
- CI 使用 `cargo audit` + `cargo deny`，并对 duplicate versions / yanked crates fail。

### I-3: `Prompt injection delimiter` 字符集限制是亮点，但还需要覆盖所有 player-controlled text

玩家名称限制 `[a-zA-Z0-9 _-]` 很好，能降低 AI snapshot prompt injection。但还需确认以下字段同样受控或标注 untrusted:
- room name / structure name / version_tag / market order memo / mod description / chat/tutorial text。

## 亮点

1. MCP 定位正确：明确不提供 `swarm_move` / `swarm_attack` 等 gameplay tool，AI 与人类同样必须部署 WASM。这个设计直接避免了“AI 控制通道绕过游戏规则”的大类漏洞。

2. Source Gate + server-injected auth context 是正确的 IDOR 防线：`player_id`、`source`、`tick` 不由客户端自报，CommandIntent 只包含 `sequence + action`。这对防止 mass assignment / identity spoofing 很关键。

3. 单一 `validate_and_apply()` 管线覆盖 WASM、Admin、TestHarness 等来源，避免“管理接口另写一套绕过校验”的常见事故。

4. WASM 沙箱采用多层防御：Wasmtime fuel、epoch interruption、内存限制、WASI 默认全禁、StartSection 拒绝、OS 进程隔离、seccomp、cgroup、无网络、只读 FS。即使 Wasmtime 有 bug，也不只依赖一层沙箱。

5. Deferred Command Model 清晰：WASM 只能返回命令，mutating host function 明确禁止。这个设计比直接 host_move/host_attack 更容易审计和回放。

6. 统一可见性函数 `is_visible_to` 作为所有输出面的唯一过滤点，是防信息泄露的正确抽象。尤其覆盖 snapshot、MCP、WebSocket、REST、replay，避免“调试接口泄露隐藏实体”。

7. Tick 原子性与 Bevy World restore 被明确写入规格。FDB rollback 不会自动恢复内存状态这一点被点名，是非常好的工程安全意识。

8. Refund anti-amplification 设计有安全意识：refund 只进下一 tick、上限 10%、deploy-reset 规则，可防止通过竞争失败刷同 tick fuel。

9. Rhai 模组引入事务性 action buffer、节点预算、进程隔离、能力白名单、签名机制，方向正确。相比“服主脚本可直接改 ECS World”，当前设计可审计得多。

10. Prompt injection 作为 AI 玩家安全问题被显式建模：untrusted 字段标注、玩家名字符集、SDK delimiter contract，这在 MCP 游戏里非常必要。

## 必须修改清单（建议作为 R1 blocking items）

1. 统一 Overload 规格：visibility/range/global target cooldown/side-channel-safe result 写入 DESIGN、specs/02、specs/08。
2. 统一所有输入大小与命令数量上限，删除 100 vs 500、256KB vs 1MB 的冲突。
3. 重写 MCP transport contract：browser/non-browser 分离、DNS rebinding 测试、Host/SNI/aud/token 绑定。
4. 澄清代码签名模型：客户端私钥还是 bearer token，二选一；签名覆盖 nonce/world_id/module_hash。
5. 给 `swarm_simulate` / dry-run 增加明确 tick/entity/output/CPU 上限与隔离 worker。
6. 将 mod checksum/signature 从“可选/后补”升级为 P0 必需，并引入 capability manifest。
7. 将 Wasmtime CVE SLA 扩展为完整 runtime emergency playbook，并覆盖 rmcp/rhai/bevy 等关键依赖。
