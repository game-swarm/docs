# R6 Security Review — Claude Opus（rev-claude-security）

**评审范围**：`/data/swarm/docs/` 全量文档（design/ 6 文件 + specs/ 12 文件，约 8,093 行）
**视角**：Security（信任边界、攻击面、威胁穷举）
**形式**：Clean-slate 全量评审（不限于前轮 Blocker 闭合验证）

---

## Verdict

**`CONDITIONAL_APPROVE`**

设计的安全骨架是扎实的——单一 `validate_and_apply()` 管线、可见性优先（`NotVisibleOrNotFound`）、Ed25519 + deploy_nonce + 证书 + CRL + epoch 五层防御链、Rhai 强制签名 + AST 节点预算事务回滚、特殊攻击三结果等价合同 + Overload 永久锁死证明、Phase 2a TOCTOU 合同、确定性回放契约——这些核心安全模型在 R3-R5 几轮闭合后已基本就绪。

但本轮全量审计仍识别出 **2 个 High、5 个 Medium、6 个 Informational** 等级的设计合同缺失/矛盾——主要集中在「跨文档语义不一致」「side-channel oracle」「资源预算约束未穷举到边界场景」三个领域。这些不是阻塞实现，但若不在编码前修正，将直接 leak 到代码层并产生难以审计的实现分叉。

---

## 信任边界总览（Security 视角整理）

```
Untrusted ─────────── Trusted（递增）

[1] WASM 玩家代码         ←── 最低信任，进程隔离 + fuel + seccomp + cgroup
[2] CommandIntent (WASM 输出) ←── 仅 sequence + action 两字段
[3] MCP Browser 端点       ←── Origin/CSRF/Fetch-Metadata
[4] MCP Agent/CLI 端点      ←── mTLS 或 Ed25519 signed
[5] Rhai 模组（服主信任）    ←── Ed25519 签名 + trusted_keys 白名单 + AST 预算
[6] Auth Service           ←── 全局信任锚点，签发证书 + epoch
[7] Engine Core (Rust)     ←── 不可变核心
[8] FDB / Bevy World       ←── 权威世界状态
[9] Admin                  ←── 同 validate_and_apply 路径，仅放宽 RejectionReason
```

每条边界都是攻击者可着力的潜在武器——下文按严重度穷举。

---

## Critical

无。R3-R5 已闭合：模块信任链吊销、deploy_nonce 跨 audience 复用、Wasmtime 缓存键不一致、`world_seed` 前向保密风险（已通过 epoch bump 接受为运维风险）、`public_spectate` 绕过 fog_of_war、CommandIntent additionalProperties 字段注入、RuleMod inprocess 强制签名、Overload 锁死、TOCTOU。

---

## High

### H1 — JWT 与 Ed25519 证书的双重身份系统跨文档语义不一致

**位置**：
- `specs/security/03-mcp-security.md` §1.1（证书：24h 有效期）
- `specs/security/03-mcp-security.md` §3.1（JWT：`exp = iat + 900`，即 15 分钟）
- `specs/security/09-command-source.md` §3.4（证书：默认 90 天有效期）

**问题**：
同一系统中并存三个不同的身份过期窗口（15 min / 24 h / 90 d）。三者的关系（哪个签哪个、哪个用于什么操作、哪个先过期、哪个负责签 deploy_payload）从未在任何文档中显式定义。

攻击者视角下的具体疑问：
1. JWT 15 分钟过期后，部署还能用吗？JWT 是否仅控制 MCP transport，证书才控制部署？两者过期窗口重叠时谁拥有最终决定权？
2. 90 天的客户端 Ed25519 私钥泄露后，攻击者持有合法证书 90 天——仅依赖 JWT 撤销（jti）能否阻止？
3. JWT 中 `sub: "player:42"` 与证书中 `player_id: 42` 不匹配时如何处理？

**修正建议**（合同级，非编号建议）：
明确三层身份的职责矩阵——JWT（transport 鉴权，15 min）、证书（部署能力 + 长期身份，可配置 24h-90d，默认 90d）、player_id（不可变，从证书提取）。在 `specs/security/03-mcp-security` 增加 §1.2「身份层次」表格：

| 凭证 | 用途 | 默认有效期 | 撤销机制 | 谁签发 |
|------|------|----------|---------|-------|
| JWT | transport 鉴权（aud 绑定） | 15 min | jti 黑名单 + auth epoch | OAuth2 服务 |
| 客户端证书 | 部署签名验证 + player_id 锚定 | 90 天（可配置） | CRL + auth epoch | Auth Service（Ed25519 签发） |
| Player Ed25519 keypair | 部署 payload 签名 | 与证书等同 | 证书吊销自动失效 | 客户端本地生成 |

并明确：JWT `sub` 与证书 `player_id` 不一致 → 一律 `403 IdentityMismatch`，刷入安全审计。

---

### H2 — `omitted_count` 字段直接暴露被截断的可见实体数量，破坏 fog-of-war 隐蔽性

**位置**：`specs/security/05-visibility.md` §3.1，`specs/core/01-tick-protocol.md` §2.3

**问题**：
快照截断时，引擎向 WASM 返回 `truncated: true` + `omitted_count: N` 字段。设计意图是让 WASM 知道信息不完整。但 `omitted_count` 是**精确计数**——攻击者将其作为 oracle：
- 推断敌方在远房间的活动密度（`omitted_count` 突增 = 远端有大规模 drone 移动）
- 敌方 drone 是否进入了某个特定房间（通过对比 `omitted_count` 增量）
- 配合 `host_get_objects_in_range` 的返回 `total_visible_count` 字段，可重构整张地图的实体分布

这违反 §2.4「隐藏信息」表中「其他玩家 drone 数量 = 隐藏」的设计目标——即使无法看到具体 drone 位置，也能推断其总量。

**修正建议**：
将 `omitted_count` 改为「分桶模糊计数」：
- 0 (truncated=false 时)
- 1 (1-9 个被截断)
- 10 (10-99)
- 100 (100-999)
- 1000+ (≥ 1000)

或者，仅在 `truncated == true` 时返回固定值 `unknown`。同样适用于 `host_get_objects_in_range` 返回的 `total_visible_count`——应仅返回 `truncated` 布尔，不暴露具体差值。

---

## Medium

### M1 — Hack 校验拒绝码 `AlreadyHacked` 暴露目标已被他人攻击

**位置**：`specs/core/02-command-validation.md` §3.10

**问题**：
Hack 校验链中包含 `AlreadyHacked`（目标未被其他玩家 Hack 中）单独错误码。攻击者可以用此构建侦察 oracle：
- 对每个可见敌方 drone 尝试 Hack
- 若返回 `AlreadyHacked` → 该 drone 正在被第三方攻击（可能是盟友或新威胁）
- 若返回 `OnCooldown` → 自身 drone 上次成功 Hack 仍在冷却

`NotVisibleOrNotFound` 的"可见性优先"原则在 §5 中已声明，但此处对 `AlreadyHacked` 没有应用——它直接告诉攻击者"目标被 Hack 中"是其他玩家正在做的事。

**修正建议**：
将 `AlreadyHacked` 合并为 `OnCooldown` 或 `NotEligible`，配合 `target_global_cooldown` 模式（同 Overload 处理）——同一 drone 在被 Hack 期间对所有攻击者返回相同错误。Admin trace 仍保留 `detail = "target_already_hacked_by:player_X"` 用于审计。

---

### M2 — Drain 命令的 `TargetEmpty` 拒绝码可重构敌方建筑资源存量

**位置**：`specs/core/02-command-validation.md` §3.11

**问题**：
Drain 校验序列中 `target.has_resource` 与 `TargetEmpty` 是不同错误码。攻击者通过试探性 Drain 不同 resource 类型（Energy/Crystal/Matter/...）：
- 返回 `TargetEmpty` → 该资源类型为 0
- 返回 `OnCooldown` → 该资源类型有库存（drone 已开始 drain）

虽然单次试探仅消耗 200 Energy + 50 tick 冷却，但每个 drone 可对每个 target 多次试探（不同 resource type 各 1 次），可有效重构敌方 storage 内的资源分布——与 §2.4「其他玩家资源数量 = 隐藏」设计目标冲突。

**修正建议**：
统一返回 `NotEligible`，admin trace 保留具体原因。或将 `target_has_resource` 检查移到 apply 阶段：「校验阶段允许，apply 时若资源 = 0 则静默 no-op」（同 Overload 三结果等价合同模式）。

---

### M3 — `swarm_dry_run_commands` / `swarm_simulate` 缺少结果脱敏要求

**位置**：`specs/security/03-mcp-security.md` §4.2-4.4，`specs/gameplay/06-feedback-loop.md` §3.1

**问题**：
`swarm_dry_run_commands`（在 design/interface.md 中已列入 MCP 工具集）和 `swarm_simulate` 接收**玩家可控的 snapshot 副本**，返回模拟结果。对返回结果有以下设计缺失：

1. dry_run 返回的拒绝原因未声明是否走 player-facing 脱敏（NotVisibleOrNotFound）—— 攻击者可以用 dry_run 试探敌方 drone 位置，因为不消耗 fuel，单次成本远低于真正提交 RawCommand。
2. simulate 返回的「N tick 后世界状态」是否应用 `is_visible_to(caller, tick)` 过滤？若否，攻击者可在 simulate 中查看自己 drone 移动到敌方区域后的 snapshot——绕过 fog_of_war 实时观察。
3. simulate 在线（5/tick）和离线（CLI 离线模拟）的执行环境应该明确——离线模拟使用本地 SDK 复制的 snapshot，但若 snapshot 来自 MCP `swarm_get_snapshot` 已经过 fog 过滤，离线 simulate 也只能模拟可见部分（这是合规的，需要明确文档化）。

**修正建议**：
在 `specs/security/03-mcp-security` 增加 §4.6「Dry-Run 与 Simulate 安全合同」：
- dry_run 拒绝码必须经 player-facing 脱敏（同 RawCommand）
- simulate 返回的每帧 snapshot 必须经 `is_visible_to(caller, sim_tick)` 过滤
- simulate 不能模拟「我看不到的玩家的反应」——只能模拟自己提交命令后的世界投影
- 试探性命令（dry_run + 不同 target_id）必须计入审计日志，相同模式的高频试探触发限流

---

### M4 — Rhai `actions.damage_entity` 能力未限定目标范围

**位置**：`specs/core/07-world-rules.md` §5.1，`design/gameplay.md` §8.7

**问题**：
能力命名空间表中 `actions.damage_entity(entity_id, amount, reason)` 标记「允许范围：仅全局实体」，但全局实体（Source、Controller）通常不是常规伤害目标。Rhai 模组的真实使用场景是给 NPC、玩家 drone、玩家建筑造成伤害（如帝国维护费 → drone 受损）。

矛盾点：
- 矩阵说允许范围是「仅全局实体（Source、Controller）」
- 但 design/gameplay.md §9.0「PvE 生态层」描述 NPC 行为完全由引擎内置 AI 驱动（非 Rhai 模组）—— 那么 RuleMod 究竟能否对玩家实体造成伤害？
- §8.2「资源不足处理」提到 `onshortfall = "damage"` 选项（建筑受损），这显然是 Rhai 模组对**玩家建筑**造成伤害

如果允许伤害任何 entity（含玩家 drone/建筑），就需要明确：
- 能否绕过抗性？（破坏战斗平衡）
- 能否伤害 spawning_grace 状态的 drone？（破坏新生 drone 保护）
- 单 tick 累计伤害上限是多少？（DoS 攻击：恶意 RuleMod 一次清空所有玩家）

**修正建议**：
明确 Rhai damage_entity 的边界合同：
1. 允许的 entity 类型：`["Drone", "Structure", "Source", "Controller"]`（不含 NPC——NPC 由内置 AI 管理）
2. 必须经过抗性计算（同 combat_system 路径）—— 不允许 Rhai 绕过 damage_type / resistance
3. 禁止伤害带 `SpawningGrace` 或 `Fortify` 状态的 drone
4. 单 tick 累计伤害上限 ≤ MAX_PLAYER_HP × 5%（防止全屠杀模组）
5. 每次调用记录到 TickTrace，含 reason 字段

---

### M5 — `swarm_explain_last_tick` 详细拒绝信息可被作为侦察 oracle

**位置**：`specs/gameplay/06-feedback-loop.md` §5.1

**问题**：
explain_last_tick 返回示例：
```
"detail": "你的 drone 在 (5,3)，目标在 (5,8)。距离 5，最大 1。"
```

`specs/core/02-command-validation.md` §5 明确「player trace 仅返回脱敏信息」、「admin trace 保留完整 detail」。但 explain_last_tick 是**player-facing** 接口，却返回了 `target_id=1002, position=(5,8)` 这种坐标级精度——若目标在不可见房间，这就是泄漏。

攻击者攻击模式：
- WASM 中提交「Attack target_id=1002」（猜测 ID）
- 通过 explain_last_tick 获取「目标在 (5,8)」反馈
- 即使 target_id=1002 在不可见房间，也能从 detail 中读出位置坐标

`OutOfRange { distance, max }` 错误码已在 IDL 定义中包含 `distance` 字段——这本身就是 oracle。

**修正建议**：
explain_last_tick 接口必须遵循同一脱敏策略：
- 不可见目标 → 返回 `NotVisibleOrNotFound`，不返回 `distance`/`position`
- 可见目标但超出范围 → 仅返回 `OutOfRange`，不暴露 `distance` 数值（或用「far」「medium」「close」桶代替具体数字）
- IDL 定义中的 `OutOfRange { distance, max }` 仅用于 admin trace，player trace 删除 `distance` 字段

「为什么闲置？」调试（§5.2）类似——若 drone 因目标不可见而闲置，仅返回 "no_visible_target"，不暴露最近敌方目标的距离。

---

## Informational

### I1 — Tutorial 来源在非 Tutorial 世界「静默丢弃」可作为世界类型 oracle

**位置**：`specs/security/09-command-source.md` §2.4

**问题**：客户端发送 Tutorial source 命令，正式世界静默丢弃 + 审计；Tutorial 世界正常处理。攻击者可通过观察响应延迟（静默丢弃 vs 实际处理）推断目标世界类型。**修正建议**：所有世界对 Tutorial source 命令返回相同的 `403 SourceNotAllowed`（与正常 Source Gate 拒绝同样响应）。

---

### I2 — `mods.lock` 的 checksum 字段标记为可选，但与 Ed25519 签名共存时职责未明

**位置**：`design/gameplay.md` §8.7「安装与配置」，`specs/core/07-world-rules.md` §5.1「模组签名机制」

**问题**：
- `mods.lock` 的 checksum 是 sha256
- `.rhai.sig` 文件是 Ed25519 签名（对 sha256 摘要）
- 两者保护对象不同：checksum 防 git pull 篡改，签名防作者私钥外的伪造

但文档中「可选 checksum 提供完整性校验」的措辞容易让服主忽略——若 checksum 缺失，仅依赖 git commit hash（`rev`）和文件级 .sig 签名，那么单 .rhai 文件被替换 + 重新签名（攻击者用同一签名密钥）就能绕过 commit hash。

**修正建议**：明确「checksum 字段在 mods.lock 中**强制必需**」，且 checksum 应覆盖整个模组目录的 Merkle hash（而不是单文件）。

---

### I3 — `target_manifest_hash` 嵌入位置与 WASM 完整性校验顺序未明

**位置**：`specs/gameplay/08-api-idl.md` §6.2，`specs/security/09-command-source.md` §3.2-3.3

**问题**：
WASM 模块在 `[package.metadata.swarm].target_manifest_hash` 中声明目标世界 manifest_hash。这通常存储在 WASM custom section 中。但部署验证流程：
1. Blake3(WASM bytes) == module_hash（payload 中声明的）
2. Ed25519 签名验证
3. ??? target_manifest_hash 验证 ???

target_manifest_hash 的提取与验证发生在校验链的哪一步？若发生在 Blake3 之后，攻击者无法篡改（hash 改变会导致 sig 失败）。但若引擎在解析 custom section 时使用 wasmparser，wasmparser 解析的 custom section 是否会因 wasmparser 版本变化而产生不同结果？

**修正建议**：明确 target_manifest_hash 的提取在 wasmparser 预校验阶段完成（§04 §2.4），并将该 hash 加入编译缓存键——`Blake3(module_hash || target_manifest_hash || ...)`。当 world.toml 变更（manifest_hash 变化）时，所有依赖该 hash 的模块自动失效。

---

### I4 — Replay viewer 端点（specs/12 §2）的 audience 隔离不足

**位置**：`specs/12-gateway-protocol.md` §2

**问题**：
Replay 端点 audience = `replay:{world_id}:{match_id}`，但允许「匿名（public replay）」。匿名 token 的格式、生成机制、是否包含 match_id binding、能否跨 match 复用——均未定义。攻击者可能：
- 用过期 player token 访问 replay（aud 不匹配应拒绝，但匿名分支可能绕过）
- 用一个 match 的 replay token 访问另一 match（缺少 match_id binding）

**修正建议**：明确「匿名 replay 访问」的具体实现——是 cookie + IP 限流，还是临时 token，token 必须 bind 到 match_id 且短 TTL（≤ 1h）。

---

### I5 — FDB Wasmtime CVE 的 Component Model / WASI Preview2 验证未明

**位置**：`specs/security/CVE-SLA.md`

**问题**：CVE-SLA 检查 `WASI 文件/网络/时钟、wasm threads、relaxed SIMD`，但 Wasmtime 30+ 引入了 Component Model 和 WASI Preview2，其安全表面与传统 WASI Preview1 不同。当前 spec 不涉及 Component Model——若未来 Wasmtime 默认开启某些 component 能力，CVE-SLA 检查可能漏覆盖。**修正建议**：增加「禁用 Component Model」一项作为编译期断言；CVE-SLA §2 assess 步骤中加入「Component Model 能力变化检查」。

---

### I6 — `world_seed` 32 字节熵的存储位置与 Auth Service epoch 联动未规范

**位置**：`design/engine.md` §3.3，`specs/core/01-tick-protocol.md` §3.1

**问题**：
- world_seed 是「服主级秘密——与 TLS 私钥同级保护」
- 但具体存储位置（文件系统、秘密管理服务、cgroup 隔离）未规范
- world_seed bump 与 Auth Service epoch bump 是否独立？两者协同的运维 runbook 缺失

**修正建议**：明确 world_seed 存储在引擎进程内存中，启动时从加密的 KMS 或 vault 加载；轮换 runbook 在 RUNBOOK.md 增加专节，包含「KMS 凭证泄露 → Auth epoch + world_seed 双重 bump」流程。

---

## 亮点（Security 视角）

1. **可见性优先原则的彻底执行**：`NotVisibleOrNotFound` 统一拒绝码 + admin/player trace 分级 + 单一 `is_visible_to` 函数控制所有输出面（snapshot/MCP/WS/REST/replay/host function）—— 这是教科书级别的正确做法，消除了"调试数据没关系"的常见漏洞。

2. **Overload 三结果等价合同 + 永久锁死证明**：通过形式化分析得出 fuel 下限不可突破，并明确 attacker 不可区分「成功 / 地板 / no-op」三态。这是少数我看到「明确证明 + 边界分析」的特殊攻击设计。

3. **Source Gate 模型 + Auth Context 不可伪造**：CommandIntent 仅 sequence + action 两字段，所有身份/时序由服务端注入——彻底消除了 player_id/source/tick 字段注入的所有可能。

4. **Rhai 进程内 + 强制签名 + AST 节点预算事务回滚**：单模组超限不影响其他模组（事务隔离）+ AST 节点是确定性度量（替代墙钟）+ 连续 10 tick 超限自动禁用——这是对 Rhai 解释器风险的成熟应对。

5. **Phase 2a TOCTOU 合同 + 编译期 trait 强制**：`WorldMutate` trait 唯一实现者是 `validate_and_apply()`——任何试图直接持有 `&mut World` 的代码会编译失败。这是把「不能绕过校验」用类型系统强制住，远比 runtime 检查可靠。

6. **deploy_nonce 五维度绑定**：`{player_id, world_id, wasm_slot, IP, single-use, 60s TTL}`+ 编译超时升级 deploy_token（30min TTL）+ refund credit 跨部署清零 + Wasmtime 缓存键含 `security_epoch`——重放保护链路完整。

7. **可见性缓存的「单一函数 + 缓存」设计**：每 tick 每玩家计算一次 + 所有输出面读同一缓存——彻底防止「snapshot 隐藏但 WebSocket 增量泄露」的实现分叉 bug。

---

## 总结

R6 全量评审下，Swarm 的安全设计已超越多数同等规模游戏引擎——核心攻击面（沙箱逃逸、信任链、可见性 oracle、特殊攻击 oracle、TOCTOU、确定性 reach-around、Rhai 注入）已系统性闭合。剩余问题集中在「跨文档语义对齐」「side-channel 边界场景」「细节级合同未穷举」三类——属于细化工作而非架构缺陷。

**建议处置**：
- H1（身份层级矩阵不一致）应在编码前显式对齐——这直接 leak 到 OAuth2 实现和证书签发逻辑，矛盾不解决会产生权限边界 bug
- H2（omitted_count oracle）需修改 schema —— 实现成本低，但若不修改将永久泄露分布信息
- M1-M5 建议在 R6+ 修复后进入 Phase 1 实现
- I1-I6 可在实现过程中逐步收敛

设计层面已达到「可进入实现」的标准——余下问题是细化清单，不是阻塞清单。

---

*评审者：rev-claude-security （Claude Opus 4.7）*
*评审时间：tick @ R6*
*评审范围：8,093 行，6 design + 12 spec*
*识别问题数：H×2、M×5、I×6*
