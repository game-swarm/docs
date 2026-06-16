# R4 Clean-Slate 安全评审 — rev-claude-security

**评审日期**: 2026-06-16
**评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + 9 份 specs
**评审视角**: 信任边界、攻击面、权限模型、协议安全性、数据完整性
**评审者**: Claude Opus 4.7（独立评审，无跨评审员协商）

---

## Verdict: **REQUEST_MAJOR_CHANGES**

R4 相比 R3 在 specs/01-04 的安全语义上有显著进步——Phase 2a TOCTOU 合同、Component RW 矩阵、Browser/Agent transport 拆分、Overload 三种结果等价合同——这些都是真正的硬化。

但**模组信任体系**和**前向保密性**的核心问题在 R4 没有解决，并且 R4 引入了一个新的 Critical（CommandIntent 字段注入）。在这些问题修复前，**不应进入实现阶段**——任何一个 Critical 落地都意味着整个世界数据可被攻陷。

| 严重度 | 数量 |
|-------|------|
| Critical | 4 |
| High | 6 |
| Medium | 7 |
| Low / Informational | 6 |

---

## Critical 问题（必须在 R5 前修复）

### C1. 模组信任链无吊销机制 + 默认运行模式文档矛盾 → 服主级 RCE

**信任边界分析**:
```
模组开发者 (私钥)
    │  签名 .rhai
    ▼
git 仓库 (任何人可拉)
    │  swarm mod update
    ▼
服主 (trusted_keys 白名单)
    │  Ed25519 验签 → 加载
    ▼
引擎进程内 / 或 sandbox 进程
```

**漏洞链**:

1. **trusted_keys 是静态白名单，无吊销机制**（specs/07 §5.1）
   - 服主一旦把公钥加入 `trusted_keys`，该公钥**永久**有效
   - 没有 CRL、没有过期时间、没有 emergency rotation runbook
   - 对比 spec/09 §3.4 的玩家证书有 90 天过期 + CRL + epoch bump——**模组签名体系完全没有这些保护**

2. **私钥泄露场景**:
   - 攻击者获取模组开发者私钥（钓鱼、内部威胁、git history 误提交）
   - 攻击者 force-push 一个新 tag（v1.2.1）到模组 git 仓库，包含恶意 `tick_end.rhai`
   - 服主 `swarm mod update` → 拉取新版本 → 签名校验通过 → 加载
   - **mods.lock 不能拯救**：`swarm mod update` 本身会更新 mods.lock 的 commit hash

3. **运行模式文档矛盾**:
   - DESIGN §8.7 line 1993: 「Rhai 模组在**引擎进程内**运行——服主安装的模组是受信代码。不引入进程隔离的复杂性和性能开销。」
   - specs/07 §5.1: 「**进程隔离模式**（默认配置）：Rhai engine 运行于独立 sandbox 进程」
   - 两份核心文档对默认运行模式定义相反

4. **若 in-process 模式生效（按 DESIGN）**:
   - 恶意 Rhai 脚本可通过 Rhai 的 native function call 漏洞触发引擎进程任意代码执行（参考 Rhai issue tracker，历史 CVE）
   - 进程内可读取 FDB 凭证 → 整个世界数据库沦陷
   - 影响范围：单世界 → 所有世界（共享 FDB cluster）

5. **若 isolated 模式生效（按 specs/07）**:
   - cgroup 256MB + seccomp 仍允许执行任意确定性逻辑
   - 调用全部 `actions.*` API：`damage_entity`、`set_entity_flag`、`deduct_resource` ——一次 tick 可摧毁所有玩家殖民地
   - 修改世界经济模型 → 撑爆储存 → 触发反制机制 → 全员 throttle

**修复要求（必须）**:
- 统一文档：明确默认必须是 isolated 模式，DESIGN §8.7 与 specs/07 §5.1 必须一致
- 引入 trusted_keys 过期机制（≤180 天，与玩家证书逻辑对齐）
- 引入 CRL：`mods/crl.toml` 列出已吊销 (key, mod_name, since_commit)
- 引入 emergency runbook：trust key 泄露 → bump `mod_signing_epoch` → 所有旧 epoch 签名立即失效
- mods.lock 必须额外记录签名时的 epoch
- 启用 isolated 模式时，actions API 必须有 per-tick 数量上限（不是 100/tick——damage_entity 100 次足以摧毁多个玩家）

---

### C2. world_seed 前向保密性失败 → 一次 admin 凭据泄露 → 永久去随机化

**信任边界分析**:
```
world_seed (entropy)
    │  Blake3(old_seed || current_tick) [forward-only KDF]
    ▼
new_seed (10000 tick 后)
    │
    ▼
RNG state (admin trace 可见 — DESIGN §5.3)
```

**漏洞链**（DESIGN §8.8、specs/01 §3.1）:

1. **Forward-only KDF**: `new_seed = Blake3(old_seed || current_tick)`
   - 任意单 tick 的 world_seed 一旦泄露，**所有未来 seed 全部可推导**
   - 没有 forward secrecy（旧密钥泄露应不影响未来）

2. **泄露面**:
   - `Admin trace` 数据分级（DESIGN §5.3）保留**完整 detail**，包括 RNG 状态
   - admin 凭据被入侵（OAuth refresh token 泄露、内部威胁、备份未加密）→ 一次性获取当前 seed → 永久预测

3. **可预测的内容**:
   - 玩家洗牌顺序（specs/01 §3.1）→ 每 tick 谁先执行
   - 资源点 regeneration 触发位置/数量
   - 房间/出口生成（specs/01 §1.2）
   - 新玩家分配房间（DESIGN §3.1a）

4. **攻击场景**:
   - 攻击者获取 seed（一次性）+ 注册大号
   - 在指定 tick 大号被分配到 victim 邻近房间（攻击者已预测）
   - victim 的洗牌位置在所有竞争场景都是「后到」（攻击者已预测）→ resource refund 永远拿不到 → fuel budget 缓慢枯竭

**修复要求（必须）**:
- 替换 KDF 为 forward-secure 方案：每次轮换从独立熵源（OS getrandom）获取，不从旧 seed 派生
- 旧 seed 立即从内存擦除（zeroize crate）
- TickTrace 中记录 `seed_epoch_id`（不可逆 ID）而非 seed 本身，admin trace 也只包含 epoch_id
- seed 本身仅在 secrets vault 中，与 admin trace 隔离
- CI 测试：取一个 tick 的 admin trace，验证无法从中恢复 seed

---

### C3. public_spectate + spectate_delay 完全绕过 fog_of_war

**信任边界分析**:
```
玩家 A 的 drone (受 fog_of_war 限制)
    │
    ▼
Snapshot (经 is_visible_to 过滤)
    │
    ▼
WASM tick() ← 受限视野
    
但是同时:
    │
未登录旁观者
    │
    ▼
WebSocket 旁观流 (NO is_visible_to 过滤, 仅 50 tick 延迟)
    │
    ▼  
攻击者 (= 玩家 A 的对手)
    │
    ▼  
Hostile WASM redeploy
```

**漏洞链**（specs/05 §3.5）:

1. **直接矛盾的两条规则**:
   - specs/05 §1: 「无绕过。不存在『这只是调试数据所以没关系』的例外。」
   - specs/05 §3.5: 「**旁观者 WebSocket**：当 `public_spectate = true` 时，未登录客户端可订阅世界 delta。**推送内容为全地图实体（无 `is_visible_to` 过滤）**」

2. **Arena 模式默认开启**:
   - DESIGN §9.1.2: Arena 默认 `allow_spectate = true`, `spectate_delay = 100 tick`
   - 100 tick @ 300ms tick = 30 秒延迟
   - World 模式可由服主开启 spectate

3. **攻击场景**:
   - Arena 1v1 比赛：玩家 X 以两个身份进入
   - 身份 A 作为参赛者
   - 身份 B 作为旁观者（未登录），订阅同一房间 spectate 流
   - X 自动化地：每 30 秒读取 spectate 流的「30 秒前全地图」→ 推断对手 Y 当前可能位置 → 重新部署反制 WASM
   - WASM 部署是即时的（DESIGN §6.1：下一 tick 自动切换），30 秒内可完成多次迭代
   - 5000 tick 比赛 = 25 分钟，足够 50 次以上策略迭代

4. **replay_privacy 与 spectate 的互锁未明确**:
   - specs/05 §3.5: 「旁观者推送的实体信息受 `replay_privacy` 过滤——`private` 时旁观者仅见地形和公开元数据」
   - 但 `replay_privacy=public` 是 Arena 赛后强制
   - 比赛**进行中**，replay_privacy 是什么状态？文档未定义
   - 默认 `replay_privacy=private`，但 Arena 默认 `public_spectate=true` → 矛盾

**修复要求（必须）**:
- spectate WebSocket 流必须经 `is_visible_to(spectator_pseudonym, tick)` 过滤
- 引入「中立观战者」可见性级别：与未登录玩家等同，但仍受 fog 影响（仅看到所有玩家可见的实体并集？或更严格：仅可见无主中立实体）
- 比赛进行中明确禁止 spectate 任何 entity 详情，仅推送：tick number、各方资产汇总（drone count、room count）、聚合事件（"player A killed player B's drone"）
- 比赛结束后才允许 full replay
- spectate_delay 至少 = match_duration / 10（不是绝对值 50）

---

### C4. CommandIntent additionalProperties 不一致 → 字段注入

**信任边界分析**:
```
WASM tick() 输出 (untrusted)
    │
    ▼
JSON Schema 验证
    │  spec/02 §1.1: additionalProperties: false
    │  spec/02 §2.1: 仅列举禁止字段
    │  spec/08 IDL: 无显式约束
    ▼
RawCommand (server-injected envelope)
```

**漏洞链**:

1. **specs 自身不一致**:
   - specs/02 §1.1: tick 输出顶层 schema 「`additionalProperties: false`」
   - specs/02 §2.1: CommandIntent 仅说「禁止字段：`player_id`、`source`、`tick`、`auth`」，未明确 `additionalProperties: false`
   - specs/08 §2 IDL 中 commands 定义没有 additionalProperties 字段
   - 同时 specs/02 §6 「JSON 深度 ≤ 10」放宽了 schema 严格度

2. **未列举的字段命运不明**:
   - 攻击者注入 `room_id`、`tick_target`、`override_owner`、`fee_waiver`、`audience` 等
   - 实现侧任何代码路径——日志、metric、debug print、内置 trait 自动派生——可能被这些字段触发
   - 序列化框架（serde_json）默认行为依赖 `#[serde(deny_unknown_fields)]`，若忘加 → 静默接受未知字段

3. **横向攻击面**:
   - Action enum 是 tagged union（`{"type": "Move", ...}`）
   - 攻击者可注入：`{"type": "Move", "object_id": 1001, "direction": "North", "_admin_override": true}`
   - 引擎主流程拒绝 `_admin_override`（schema 严格） → ✅
   - 但 audit log 模块可能 base64 整个 JSON 入库 → 不可信字段进入数据库 → 后续查询时反序列化 → 触发新代码路径

4. **类似漏洞模式**:
   - GitHub 2024 GHSA-rj9g-x9qc-77fr (`reqwest` middleware) — 未知字段绕过验证
   - 多个 web 框架的 mass-assignment 漏洞

**修复要求（必须）**:
- 所有 schema（CommandIntent、RawCommand、Snapshot、所有 IDL 定义）必须显式 `additionalProperties: false`
- IDL 代码生成器必须为生成的 Rust struct 加 `#[serde(deny_unknown_fields)]`
- CI 测试：fuzz 注入未知字段（`__proto__`、`_admin`、`tick_override` 等 50 个候选）→ 所有 endpoint 必须返回 schema 拒绝错误
- audit log 写入路径必须只记录已验证字段，不可 base64 整个 JSON

---

## High 问题

### H1. 模组进程隔离规范矛盾 + IPC 协议未定义

specs/07 §5.1 定义 isolated 模式但缺少:
- IPC 协议的 wire format 定义
- 模组 sandbox 的初始 fd 集合（哪些 fd 在 seccomp lock 前传入）
- 单世界多模组的 sandbox 复用策略（每模组独立进程？共享一个进程？）
- IPC race condition：宿主进程 fork sandbox 的时序保证
- 模组 OOM kill 后世界状态如何同步（partial actions buffer 是否回滚）

修复：
- 明确 IPC wire format（推荐 cap'n proto 或 length-prefixed binary）
- 每模组独立进程（共享会有状态污染）
- sandbox 启动检查：fd 0/1/2 必须重定向到日志，非 IPC fd 全部关闭

### H2. Rhai actions.set_entity_flag 无命名空间隔离

DESIGN §8.7 / specs/07 §2.3:
- 多模组同时启用时，flag key 是全局的
- 模组 A 设 `slow=true`，模组 B 设 `slow=false` → 互相覆盖
- 模组 B 主动设 `immune_Thermal=true` → 在攻击战术中破坏战斗平衡

修复：
- 引擎自动为 flag key 加前缀：`{mod_name}:{flag}`（不可省略，不可由模组自行覆盖）
- 查询 flag 时必须指定 mod_name（模组无法读取其他模组设置的 flag）
- 但「全局」flag（如全引擎 immune flag）需要专用 API：`actions.set_global_flag()` 仅 admin 模组可用

### H3. swarm_simulate 资源放大攻击 — 单玩家可消耗 2.5× MAX_FUEL/tick

specs/03 §4.4 + specs/04 §6.1:
- simulate: 5/tick 调用 × 0.5 MAX_FUEL/调用 + concurrent_simulates=3
- 主 tick: 1 × MAX_FUEL/tick
- 总计: 玩家正常调用上限 = 2.5 × MAX_FUEL/tick
- 每小时 simulate 配额 50M fuel ≈ 5x 单玩家正常预算
- 富玩家可大量消耗 sandbox worker pool → 影响其他玩家 collect 阶段超时（2500ms）

修复：
- simulate 与 main tick 共享 fuel budget（单玩家总预算 = 1 × MAX_FUEL/tick）
- 或：simulate 在专用低优先级 worker pool（与 main tick 物理隔离），不挤占 main tick 资源
- per-player concurrent_simulates 应 ≤ 1（多个并发对单玩家无意义，只对 DoS 有用）

### H4. Source Gate 关于 Tutorial/Admin/Replay 路由不一致

specs/09:
- §2.1: Admin rate_limit 「无限制」，§2.2 Admin gameplay 「✅」
- specs/02 §6: Admin 也计入 500 cmd/tick——矛盾
- §2.4: Tutorial 在非 tutorial 世界「静默丢弃 + 审计」
- 但 Tutorial token 签发流程未定义（哪个 endpoint？谁验证？scope 怎么限制？）

漏洞：
- 攻击者获取 Tutorial token → 在生产世界发指令 → 静默丢弃 → 不计限流
- 通过 timing 推断「是否为 tutorial 世界」（响应延迟差异）

修复：
- Admin 必须计入 fuel budget（无限制是反作弊空白）
- Tutorial token 必须包含 `world_id` claim，token 与 world_id 不匹配立即拒绝（401，不是静默丢弃）
- 所有 source/audience mismatch 必须返回明确错误码（`AudienceInvalid`），不静默

### H5. NotVisibleOrNotFound 状态码信息泄露

specs/02 §5 要求可见性优先，但各命令拒绝码暴露存在性:
- `AlreadyHacked` (Hack §3.10) — 暴露目标存在 + 处于 hack 状态
- `AlreadyDebilitated(damage_type)` (Debilitate §3.13) — 暴露具体 damage_type
- `TargetFortifyCooldown` (Fortify §3.15) — 暴露目标曾被 Fortify
- `SpawnOnCooldown` — 暴露目标 Spawn 存在

攻击者向不可见目标发指令 → 区分 NotVisibleOrNotFound（不存在/不可见）与上述具体码（存在但状态 X）→ 推断对手活动

修复：
- 所有「目标存在但不满足条件」的拒绝码，对**不可见**目标必须先返回 NotVisibleOrNotFound
- 顺序：visibility check → existence check → state check → other validation
- admin trace 中保留完整状态码用于审计，玩家 trace 仅 NotVisibleOrNotFound

### H6. 网关 Browser/Agent listener 启动时无强制校验

specs/03 §2.3 要求 gateway bind 到 unix socket 或 127.0.0.1，但:
- 没有定义启动时强制校验（环境变量配错 → 0.0.0.0 监听）
- 编程错误 → bypass nginx → 直连 gateway → 无 origin/CSRF 检查

修复：
- 启动时硬编码 listener 检查：`bind_addr in ["unix://", "127.0.0.1", "::1"]`
- 任何其他地址 → fatal error，不启动
- CI 测试启动时尝试 0.0.0.0 → 必须 panic

---

## Medium 问题

### M1. 审计日志保留 90 天 vs GDPR 删除权冲突

specs/03 §7 + DESIGN §6.1:
- MCP audit 90 天
- WASM 模块历史 FDB 永久不可变
- 玩家提交 GDPR 删除请求 → 模块代码、IP、player_id 都在审计日志中
- 没有 PII pseudonymization 流程

修复：
- player_id ↔ profile (姓名、邮箱) 分离，profile 可独立删除
- 审计日志中只存 pseudonymous player_id（hashed）
- 删除请求 → profile 删除 + pseudonym mapping 销毁，审计日志中的 player_id 变成不可追溯

### M2. path_find cache 不可在玩家间共享

specs/04 §8 缓存键含 `player_visibility_fingerprint` → 不同玩家不同 cache key → 协调多玩家 path_find 攻击导致大量 cache miss

修复：
- 缓存分两层：地形层（公共，按 terrain_hash）+ 可见性掩码层（按 player）
- 公共层共享，掩码层每玩家独立
- 公共层命中后，掩码层只检查 path 是否经过不可见格子（更便宜）

### M3. trust_keys 配置无统一管理面板

服主在 5 个世界各自管理 `trusted_keys` → 不一致 → 一个世界吊销了 key，其他世界仍信任 → 混乱

修复：
- 提供 `swarm trust list/add/remove --all-worlds` CLI
- 引擎启动时同步检查所有世界 trust keys 一致性，输出警告

### M4. 全局冷却存储未限定清理策略

specs/02 §3.12 Overload 「全局冷却：(world_id, target_player_id)」状态:
- 玩家下线后仍占用内存
- 没有 GC 策略（specs 未定义）
- 长期运行的世界 → 内存缓慢泄漏

修复：
- per-target 状态在 7 天 inactivity 后清理（玩家 7 天不上线自动 GC）
- 类似问题：HackControlLock、Debilitated、Fortified 状态都需 cleanup TTL

### M5. WASM 编译期内存放大 — zip-bomb 类攻击

specs/04 §2.4: 上传 5MB；§7: 编译 cgroup 512MB
- 但 wasmparser 不预估编译后体积
- 5MB 恶意 WASM（深嵌套类型、巨大 indirect call table） → 100-500MB 编译内存
- 配合 10/h 部署 + 多账号 → 编译队列阻塞合法部署

修复：
- 部署前用 wasmparser 估算 expanded module size，超过 50MB 直接拒绝
- 编译内存 cgroup 应严格 256MB（512 太宽）
- 编译失败的 module 进入 abuse list，对应账号编译速率降至 1/h

### M6. Replay 依赖第三方 git 仓库可用性

DESIGN §6.1: 回放需要 checkout 到 mods.lock 的精确 commit
- 仓库被作者删除/私有化/forced push（即使 commit 还在，gc 后会消失）
- 历史回放失效 → 反作弊审计能力丧失

修复：
- 服主必须本地缓存模组 git history（`mods/.archive/{name}/{commit}.tar.gz`）
- 引擎启动时校验所有 mods.lock 中的 commit 在本地 archive 存在，否则拒绝启动

### M7. TickTrace 写入失败仅告警 → 不可审计的状态变更

specs/01 §6.1: TickTrace 失败 → 「告警；标记为不可回放」，但 tick 仍提交到 FDB
- 攻击者诱导 TickTrace 失败（FDB key conflict、磁盘竞争）→ 状态变更不留痕
- 反作弊证据丢失

修复：
- 连续 N=3 tick TickTrace 失败 → 进入降级模式，禁止新部署 + 暂停 commit
- TickTrace 写入与 World state commit 必须同一 FDB 事务（atomic 保证）

---

## Low / Informational

### L1. spectate_delay 50 tick = 150 秒不足

L1 已合并到 C3 修复要求中。

### L2. CommandIntent sequence 无 wraparound 与 monotonicity 校验

specs/02 §2.1: sequence 单调递增 WASM 自管，未定义服务端校验逻辑
- 攻击：sequence=0 后 sequence=u32::MAX（wrap 攻击）
- 攻击：tick N 用 sequence=100，tick N+1 用 sequence=50（重排攻击）

修复：服务端记录每玩家每 tick 最大 sequence，下 tick 必须严格大于。wrap 通过显式拒绝 u32::MAX 防止。

### L3. Wasmtime 版本升级跨版本回放兼容性测试缺失

specs/04 §2.1 + specs/01 §6.3.3 声明回放只重放 commands，但缺少明确的「Wasmtime 30.0 → 30.1 升级」CI 流程。

修复：CI matrix 增加旧 trace + 新 Wasmtime 版本的 replay 验证。

### L4. Hack 控制锁 stage 1-5 对原 owner 可见性未定义

specs/02 §3.10 stage 状态对原 owner snapshot 是否可见未明确。

修复：明确 stage 对 owner 可见（防御反应时间 = 5 tick），attacker 看不到任何 progress 反馈。

### L5. state_checksum 算法未定义

各 spec 多处提到 state_checksum 但无定义。

修复：specs/01 §7 应包含完整定义：`Blake3(canonical_serialize(World)) ` 其中 canonical_serialize 用 IndexMap + 字段排序。

### L6. AI prompt unicode 注入面（玩家名以外）

specs/02 §6 玩家名 ASCII 限制 OK，但模组可注册的资源名 / damage_type / special_effect 名进入 description → 进入 AI prompt 上下文。

修复：所有进入 AI prompt 的字段必须 ASCII 白名单（`[a-zA-Z0-9 _-]`），与玩家名同标准。

---

## R4 亮点（相比 R3 的真实进步）

1. **Phase 2a TOCTOU 合同**（specs/01 §3.3）— 5 条规则把 inline 执行的所有时间窗口攻击形式化了，这是 R3 完全缺失的
2. **Component RW 矩阵**（specs/01 §3.4）— 用矩阵证明 regeneration/decay 与主线无数据竞争，可审计的并行安全证明
3. **Browser/Agent transport 拆分**（specs/03 §2）— 解决了 R3 的 mTLS / Origin header 混淆，AI agent 不再被强制依赖浏览器安全上下文
4. **Overload 三种结果等价合同**（specs/02 §3.12）— 防止攻击者通过 timing/return value 推断目标 fuel 状态，是真正的「不可区分性」设计
5. **WorldRules + ManagedActions IDL 拆层**（specs/08 §1）— core 与 world-specific 边界清晰，hash 校验路径明确
6. **FDB 故障注入 CI 测试**（specs/01 §3.5）— 把回滚一致性变成可执行的测试
7. **deploy_nonce + audience binding**（specs/09 §3.2-3.4）— B4 修复合理，nonce 单次消费 + 60s TTL + audience 字段都是必要的硬化

R4 的设计**结构上**远比 R3 健壮，绝大多数中下层接口已经达到可实现质量。但**信任根**（模组签名）和**密码学基础**（forward secrecy）的问题仍然在那里，必须在 R5 闭合。

---

## R5 进入条件（建议）

R5 必须包含以下 4 个 Critical 的修复方案：

- [ ] C1: 模组 trusted_keys 引入过期 + CRL + signing_epoch
- [ ] C2: world_seed 轮换改为独立熵源 + zeroize 旧 seed
- [ ] C3: spectate 流必须经 is_visible_to 过滤，比赛进行中只推送聚合事件
- [ ] C4: 所有 schema 强制 additionalProperties: false + IDL codegen 加 deny_unknown_fields

H1-H6 应在 R5 同步修复。M 级别可在实现阶段处理但需在 ROADMAP 中显式列出。

---

**评审者备注**: R3 → R4 的 spec convergence patch（B1-B7）质量很高，反映了团队对反馈的认真处理。但安全评审的本质是「我是攻击者，我能怎么钻空子」——上面 4 个 Critical 都不需要复杂攻击路径，只需要利用文档的不一致或缺失。在 specs 收敛到一致并补齐密码学基础前，进入实现是不可接受的风险。
