# R3 安全评审 — rev-claude-security

> 评审员: rev-claude-security (Claude Opus 4.7)
> 评审日期: 2026-06-16
> 评审范围: DESIGN.md (2364 行) + specs/01-09 + security/CVE-SLA.md
> 视角: 信任边界执行 / 攻击面映射 / 威胁穷举

---

## Verdict

**REQUEST_MAJOR_CHANGES**

设计在玩家 → 引擎方向的攻击面（WASM 沙箱、命令校验、可见性过滤）已经做得相当扎实——deferred command model、单一 `validate_and_apply()` 路径、`is_visible_to` 单一函数、Source Gate 注入身份这几个核心抽象在我看来足够防御\"恶意玩家提交 WASM\"这一类主线攻击。

但当我把视角切到**第三方模组作者**、**MCP 客户端供应链**、**控制面（Auth Service / 部署管线）**、**跨 tick 状态机**这几个方向时，攻击面有大量未明确的灰区——其中 3 项 Critical（模组信任链无撤销、deploy_nonce 跨 audience 复用未禁止、Wasmtime 缓存键不一致）、6 项 High、9 项 Medium。这些不是\"边缘 bug\"——是攻击者会**首先**去尝试的入口。

实现前必须把 Critical 全部闭合，High 至少给出文字答复（哪怕\"已知风险，不修\"也写下来）。

---

## Critical（必须在实现前闭合）

### C1. 模组信任链没有撤销/过期/吊销路径 — specs/07 §5.1, DESIGN §8.7

**攻击者视角：「我是被信任的模组作者，或者我盗了一个被信任的私钥」**

specs/07 §5.1 和 DESIGN §8.7 的设计：
- 服主在 `world.toml` 配置 `[rhai] trusted_keys = ["kagurazaka:ed25519:abc..."]`
- 引擎启动时验签，Ed25519 通过即加载
- `swarm mod update` 走 `git pull` 自动拉取新版本

这个信任模型有 4 个**未定义**的洞：

1. **没有密钥撤销机制**。一旦 `trusted_keys` 加入某把公钥，服主**永远**信任。被盗 → 攻击者可以以那把密钥签名任何 `.rhai` 推到 git → `swarm mod update` 自动拉新 commit → Rhai 沙箱执行恶意 actions。无论沙箱多严格，只要在 actions 白名单内（`damage_entity`、`set_entity_flag`、`emit_event`）就能搞掉所有玩家——比如「全图玩家 drone HP 清零」一行 actions 就能写出来。
2. **没有签名过期时间**。Ed25519 签名本身不带 expires_at，三年前的合法 commit 现在仍然有效。攻击者可以提交一个看起来无害的旧 commit + 一个伪装成 hotfix 的恶意 commit，服主 review 时只看 hotfix。
3. **没有 git rev pinning 强校验**。`mods.lock` 记录 `rev = "a1b2..."` 但 specs/07 §5.1 也写了「`.sig` 文件缺失视为未签名 → 拒绝加载」——可如果攻击者控制了仓库的 force-push 权限，把 `rev a1b2...` 重新指向新的 commit（git tag 是可变指针，commit hash 也可以被 force-push 到 dangling 状态再 GC），服主下次 `git fetch` 拿到的就是新 commit。`mods.lock.checksum` 是**可选的**（DESIGN §8.7 倒数第三段：「可选包含 content hash」）——可选 = 默认不开 = 默认无防护。
4. **没有定义 `swarm mod trust` 的安全模型**。`swarm mod trust my-mod --key <pubkey>` 这条命令意味着什么？是把 pubkey 写到 `world.toml` 的 trusted_keys？那 `world.toml` 本身是怎么保护的？服主自己被钓鱼一次 = 多一个 trusted_key = 整个世界被永久污染。

**为什么是 Critical**：Rhai 模组在沙箱内但仍能调用 `damage_entity` 和 `set_entity_flag` 改任意实体。一个被盗私钥 = 无限游戏破坏权。在玩家 WASM 攻击面上你做了 100 分的隔离，结果留了一个 0 分的后门给\"被信任\"的代码。

**修复要求**：
- `mods.lock.checksum` 改为**必需**字段（不只是 commit hash，要 `Blake3(模组目录 tar)`），引擎启动时校验 checksum 与磁盘一致，不一致拒绝加载。
- 引入 `trusted_keys` 的吊销列表 `revoked_keys`（带 revoked_at timestamp），所有签名 timestamp ≥ revoked_at 的全部拒绝。需要给 Ed25519 签名加上 `signed_at` 字段。
- 模组签名引入 `expires_at`（建议 1 年），过期签名拒绝加载，强制服主重新人工 review + 重新 trust。
- 文档中明确写「服主必须把 `world.toml` 和 `mods.lock` 一并 git 管理 + signed commit + 文件系统权限 0600」——把假设暴露出来。
- `swarm mod trust` 必须要求服主输入二次确认 + 显示该 key 历史签名过的所有模组列表。

---

### C2. `deploy_nonce` 跨 audience 复用未禁止 — specs/03 §2 + specs/09 §3

**攻击者视角：「我是被钓鱼的浏览器」**

specs/09 §3.2 定义 `DeployPayload` 含 `deploy_nonce`，specs/03 §2 把 transport 拆成 Browser（Origin/CSRF）和 AI/CLI（mTLS/signed），但**没有**说 `deploy_nonce` 是否绑定到 audience。

攻击场景：
1. 玩家正常在 Browser 里准备部署 → 前端调 `swarm_deploy_challenge` 拿到 `deploy_nonce`（60s TTL）
2. 玩家被恶意网站 CSRF（或浏览器扩展窃取）→ 攻击者拿到这个 nonce
3. 攻击者把 nonce 用在自己的 CLI 客户端 → mTLS endpoint 接受这个 nonce → 部署攻击者的 WASM

token `aud` field 已经绑定 `{gateway_origin, world_id, "browser"}` vs `"cli"`（specs/03 §2.1/2.2），但 `deploy_nonce` 是从 MCP `swarm_deploy_challenge` 拿的——文档没说这个 challenge 接口本身是 browser-only 还是 cli-only，也没说 nonce 内是否带 audience tag。

**修复要求**：
- `deploy_nonce` 内嵌 audience（`browser` / `cli` / `agent`），server 端在 deploy 验证时校验 nonce.audience == request.audience。
- `swarm_deploy_challenge` 必须返回与本次连接 audience 绑定的 nonce，不允许跨 channel 复用。
- 文档显式声明：「nonce 单次消费 + audience-bound + IP-bound（可选，默认开）」。

---

### C3. Wasmtime 编译缓存键定义不一致 — specs/04 §2.4 vs specs/09 §3.5

**攻击者视角：「我提前编译好恶意 WASM 在我账户下，等服务端升级 security_epoch 后看缓存是否被旁路」**

两份 spec 给出**两个不同的缓存键**：

- specs/04 §7（编译时预算）：「按 (module_hash, wasmtime_version) 缓存」
- specs/09 §3.5：「`blake3(wasmparser_version || validation_policy_version || wasmtime_build_commit || target_arch || security_epoch)`」

两份文档**都是权威**（specs/04 锁版本规则，specs/09 锁 cert/epoch 模型）。这种不一致会导致实现选错——选 specs/04 的版本意味着 `security_epoch` 升级（CVE 紧急响应、validation policy 加固）后**已编译模块的旁路验证不会被触发**，相当于停留在旧规则下。攻击者：在 epoch=N 部署一个看似良性的模块；epoch=N+1 时增加了一条新的 wasmparser 校验规则；缓存命中 → 跳过编译 → 跳过 wasmparser → **跳过新规则**。

specs/04 §7 倒是有一条「每次 tick 执行前校验 player 的证书未过期未吊销——过期/吊销立即终止 WASM 执行」，但**这只校验证书**，不校验缓存条目本身的安全策略 epoch。

**修复要求**：
- 统一权威：缓存键 = `Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)`，**且** validation policy / parser / epoch 任一变更必须 invalidate 全量缓存（不能只 invalidate 单一玩家的）。
- specs/04 §7 表格需要改写为引用 specs/09 §3.5。
- 文档中明确「security_epoch bump 是 emergency 流程，会引发全量重编译，预期窗口期 X 分钟」——把成本暴露给运维。

---

## High（发布前必须答复）

### H1. 可见性缓存的「Phase 2a 内」语义模糊 — specs/05 §5 + specs/01 §3.1.3

specs/05 §5：「每 tick、每玩家可见性计算一次并缓存。缓存键: (tick, player_id)。失效: 下一 tick。」
specs/01 §3.3：「Phase 2a 中 inline 应用——校验基于**当前** Bevy World 状态（非快照）」

**矛盾**：Move 命令在 Phase 2a 立即修改实体位置；可见性缓存按 tick 起始冻结。同 tick 内：
- 玩家 A 的 drone 在 (5,5)，正常对玩家 B 的 (10,5) 不可见（fog of war）
- A 提交 `[Move(drone, East), Move(...), Move(...), RangedAttack(B's drone)]`
- 走完 Move 链 drone 已经到了 (8,5) → B 在 RangedAttack range=3 内
- inline 校验：用「当前 Bevy World 位置」算距离 → 通过
- 但 `is_visible_to` 是用 tick 起始缓存（在 (5,5) 时不可见 → 返回 false）→ Overload `TargetNotVisible`

到底用哪个？从 specs/05 §5 看是缓存（公平、确定性、防侦察）；从 specs/01 §3.3.3 per-drone 1 main action quota 推断 Move 链根本不可能存在（一 tick 一个 main action）。但 quota 限制是 main action ≠ 所有 action，Transfer/Withdraw 不计入，那就有空间走「Transfer 链 + 1 main」。

**修复要求**：
- 在 specs/05 §5 添加：「可见性缓存在 Phase 2a 开始**前**计算一次，整个 EXECUTE 阶段冻结。inline 命令的可见性检查（特别是 Overload 的 `is_visible_to(target_player, attacker)`）使用此缓存——即使 attacker 在同 tick 内移动，可见性不重算。」
- specs/02 §3.12 Overload 检查项里把 `is_visible_to` 标注为「使用 tick 起始可见性缓存」。
- 同步检查：Heal/RangedAttack 的 `friendly_target`/`enemy_target`/`in_range` 是否对应同样语义。

### H2. Snapshot 截断攻击 — specs/01 §2.3 + specs/05 §3.1

specs/01 §2.3：「超限时按距离排序截断（最近优先），保证近距离实体不丢失」

**攻击者视角**：我玩家 A，旁边玩家 B 是我的目标。我大量 spawn 廉价 drone（Tough×1，Energy=10/part），堆在 B 房间出口附近：
- 我自己看自己实体不受 256KB 限制（snapshot.entities 是 visible 的合并集）
- 但 B 看到的 snapshot 中：我的 drone 距离 B 近 → 被纳入 → 把 B 的远端 keep（远房间的 Spawn、Controller、远 drone）挤出 256KB
- B 的 WASM 收到 `truncated=true` 但已经晚了——他看不到自己被攻击的 Spawn

256KB 截断是**攻击者武器**，不是防御措施。距离排序天然偏向\"近邻拥堵\"。

**修复要求**：
- 截断必须分桶：自身实体永不截断（先扣自身 quota）；剩余 quota 内按 `(类型权重 × 距离)` 排序。Spawn/Controller 这种关键建筑权重 ≥ 1000，普通敌方 drone 权重 = 距离。
- 或者：256KB 是\"快照硬上限\"但**结构化数据 + ID 引用**——entities 列表只放 ID + position，详细字段按需 lazy load 走 host_get_objects_in_range。具体留给实现选。
- 文档明确：「攻击者已知可以通过 spawn 廉价 drone 占用快照空间——每玩家 spawn 限额是反制」。把假设暴露出来。

### H3. Auth Service epoch bump 的同步窗口未定义 — specs/09 §3.4

「Auth Service epoch：全局单调递增整数。emergency bump 后所有旧 epoch 证书立即失效」

**未定义**：Engine 进程怎么知道 epoch 变了？
- Pull 模型：每 tick RPC Auth Service 拿当前 epoch → 网络分区时 Engine 选什么 fallback？开放（接受所有）→ 失效；关闭（拒绝所有）→ 整个世界停摆
- Push 模型：Auth Service 推到所有 Engine → 推送丢失的 Engine 在窗口期内继续接受被吊销的证书

specs/09 §3.4 只说「emergency bump 后所有旧 epoch 证书立即失效，强制全量重新认证」——这是 Auth Service 内部状态，不是 Engine 状态。

**修复要求**：
- 选择并写入文档：建议 push（NATS pub）+ epoch 单调递增校验 + Engine 启动时拉一次 + 定期心跳（30s）。心跳超时未收到新 epoch → Engine 进入降级模式（拒绝所有新部署，保留已加载模块）——这是 fail-secure 不是 fail-open。
- 单 Engine 实例可能被网络隔离（specs/01 §6.2 已经定义了\"降级模式\"——可以共用机制）。
- 给运维一个 SLA：epoch bump → 所有 Engine 同步完成 ≤ N 秒。

### H4. Rhai actions buffer 大小无上限 — specs/07 §5.1

specs/07 §5.1 定义了 RhaiActionBuffer（deducts/awards/events/effects 四类），但**没有**定义 buffer 总大小或单类大小上限。

**攻击者视角**：恶意（或有 bug 的）模组在 `for player in state.players()` 中对 3000 玩家每人调一次 `actions.deduct + actions.award + actions.emit_event` → 9000 个 action 装 buffer → 内存膨胀 → 配合 cgroup 256MB → 把 Rhai sandbox 进程顶 OOM → 模组本 tick action 全部丢失（事务性回滚的设计意图相符）但**重启进程**期间所有模组都受影响。

specs/07 §5.1 表格倒是写了「actions 调用次数 100/tick」，但是\"软限制 → 该模组本次 tick 跳过\"，硬限制是 100,000 AST 节点 → 触发硬限前可能已经攒了 100k 个 actions（每个 actions.* 是几节点）→ buffer 大到爆。

**修复要求**：
- 加硬上限：每模组每 tick `RhaiActionBuffer` 总大小 ≤ 1MB（按字段总长度计算），超限触发**模组本 tick 全 buffer 丢弃**（与 AST 超限同语义）。
- 或：actions.* 调用次数硬上限 1000/tick，超限直接拒绝该 action 并标记模组「本 tick suspect」。
- 区分 actions 调用次数的\"软限制 100\"（仅 throttle）和\"硬限制 1000\"（杀模组）。

### H5. swarm_get_replay 没有范围上限 — specs/03 §4.3

`swarm_get_replay` 限流写的是「按需」。结合 specs/06 §1.5.3 keyframe + delta 模型，玩家可以请求 `(from_tick=0, to_tick=current)` → 引擎需要遍历几千 keyframe + delta → CPU/IO 耗尽。

**攻击者视角**：低成本 → 持续高强度查询 → 隐蔽资源耗尽（不计入 fuel budget，不计入 deploy quota）。

**修复要求**：
- 单次 `swarm_get_replay` 范围硬上限 1000 tick（约 50 分钟），超出返回 `RangeTooLarge`。
- 同一玩家每小时累计回放查询 tick 数 ≤ 100,000。
- 异步执行（不在 MCP 同步路径）+ 队列 → 每玩家最多 1 个 in-flight 请求。

### H6. WASM tick 输出大小限制存在 3 处不一致 — specs/02 §1.1, §6, specs/04 §6

- specs/02 §1.1：「总字节数 ≤ 256 KB」
- specs/02 §6（脚注）：「JSON 大小：单条指令 ≤ 64KB，整批（tick 输出）≤ 1MB」
- specs/04 §6：「输出 JSON 体积 256 KB」

到底是 256KB 还是 1MB？1MB 上限对单条 64KB × 500 commands 表面合理，但 256KB 是 specs/02 主体定义。**实现一定会选错一个**。

**修复要求**：选定一个值（建议 256KB——和 snapshot 对称），specs/02 §6、specs/04 §6 的措辞统一。如果保留 1MB，必须解释为什么和 specs/02 §1.1 的 256KB 不冲突。

---

## Medium

### M1. CRL 检查模型未定义规模上限 — specs/03 §3 + specs/09 §3.4

specs/09 §3.4 要求「每 tick 开始前扫描活跃玩家的证书状态」——500 玩家 × 每 3s tick = 167 次/秒 CRL 查询。CRL 走分发点（CDP）的 HTTP 拉取在 P99 时是几百 ms，这个频率会把 CRL 服务打爆。OCSP stapling 或 CRL Bloom filter（短期可吊销）会更现实。

修复：明确 CRL 查询模型——内存中维护增量 Bloom filter（每秒 NATS pub 增量更新），命中再走精确查询。

### M2. swarm_validate_module 作为攻击 oracle — specs/03 §4.4

`swarm_validate_module` 返回\"潜在问题和预估 fuel 消耗\" + 限流 10/h。攻击者用此 oracle 优化恶意 WASM——\"我的 fuel 偏离规范多少？\"—— 二分搜索找到刚好不被静态分析判 reject 但在 runtime 接近 fuel 耗尽的 payload。

修复：returns 不要给精确 fuel 估计——给区间（low/medium/high/exceeds）；不暴露 wasmparser 内部错误信息（仅 yes/no + 类别）；10/h 改 5/h；连续 3 次 reject → 玩家本小时禁止 deploy。

### M3. spectator 推送可能泄露玩家身份 — specs/05 §3.5

`public_spectate=true` 时未登录客户端可订阅 delta，「全地图实体（无 is_visible_to 过滤）」。entity 包含 `owner: PlayerId`——但 `PlayerId` 可能与玩家 OAuth2 sub 关联，旁观者积累 ID 后可以做 timing 关联。

修复：spectator 推送中 PlayerId 必须是\"per-世界一次性别名\"（`Blake3(world_id || real_player_id || world_seed)` 截断 32 bit），不能是全局 ID。

### M4. JWT scope `swarm:deploy` 粒度过粗 — specs/03 §3.2

scope `swarm:deploy` 同时授权 `swarm_deploy` 和 `swarm_rollback`。被盗 token 可以 rollback 到任意旧版本——攻击者可以选择最弱的旧版本（已知 bug 的 v0.1）作为 rollback target。

修复：拆分为 `swarm:deploy` 和 `swarm:rollback` 两个 scope，rollback 默认不在 AI agent 标准 scope set 里。或：rollback 走 specs/09 §2.2 `Rollback` source，强制双人审计（但 specs/09 §2.2 写的是 Admin Rollback——玩家自己的 rollback 怎么办？文档没说。）

### M5. Tower 自动攻击与 Phase 2b 时序 — DESIGN §3.2 + specs/01 §3.4

Tower 在 Phase 2b combat_system 中执行。Tower 冷却（10 tick）的检查时间点是\"主线 chain\"内，但 specs/01 §3.4 矩阵里 combat_system 不写 `Cooldown`——`decay_system` 写 `Cooldown: W` 且 decay 与主线**并行**。

**潜在数据竞争**：combat_system 在 t 时刻读 cooldown=0 → 攻击 → combat 完毕；同 tick decay_system 把 cooldown 减 1 → 但 t 时刻 cooldown 已经是 0 了，减 1 = u32::MAX wrapping？还是 saturating？文档没说。

修复：specs/01 §3.4 的 Cooldown 列在 combat_system 里也写 R（Tower 攻击需要读 cooldown）。规定 Cooldown 算术为 `saturating_sub(1)`。

### M6. Spawn entity_id 可预测 — specs/01 §2.5 + DESIGN §6.1

specs/01 §2.5 没说 entity_id 怎么分配。如果是单调递增，玩家 A 在 t1 看到自己 drone id=5001，在 t2 之间没事发生，下一次 spawn 就是 5002——能预测对方 spawn 何时发生。

更危险：A 看不到 B（fog），但 A 提前提交 `Attack(target_id=5050)`——服务端 `ObjectNotFound`（id 不存在）→ 不退 fuel；多 tick 后 B spawn → id 真的=5050 → A 此时看不到也打不到，但能确认 \"B 在某 tick spawn 了\" 这个 timing 信息。

修复：entity_id 用 64 位含 32-bit 随机 nonce + 32-bit 序号（per-world）；或 Blake3(world_seed || sequential_id) 截 64 位。让外部预测不可能。

### M7. Sec-Fetch-* 老浏览器降级策略 — specs/03 §2.1

specs/03 §2.1 要求支持 `Sec-Fetch-Dest`/`Sec-Fetch-Site`/`Sec-Fetch-Mode`，但**没说**老浏览器（Chrome <76, Safari <16.4）缺这些 header 时怎么办：拒绝 = 一部分玩家进不来；接受 = 攻击者伪造 User-Agent 假装老浏览器绕过校验。

修复：设白名单 User-Agent 列表（明确支持的浏览器版本下界），超出范围拒绝；或显式接受缺 header 但要求强 CSRF token + Origin 双校验。

### M8. Audit 日志 untrusted string 注入 — specs/04 §6.2 + specs/03 §7

specs/03 §7 ClickHouse `parameters` 字段存 String，specs/04 §6.2 写「所有 untrusted string 在写入 TickTrace 前经过 escaping」——但 ClickHouse audit 没复述这条。`tool_name` 是受信的，`parameters` 来自玩家 → 玩家在 deploy version_tag 里塞 SQL/log injection payload → ClickHouse log search 被污染。

修复：在 specs/03 §7 显式说明：所有玩家可控字段（version_tag, room_id 当字符串、deploy_nonce、player_name 等）写入前 JSON-escape；Grafana/Logs 视图显示前再次 HTML-escape。

### M9. Rhai 进程 IPC 协议未定义 — specs/07 §5.1

specs/07 §5.1：「Rhai engine 运行于独立 sandbox 进程，通过 IPC 与核心引擎通信」+ seccomp 白名单 read/write/sendmsg/recvmsg。**没说**：
- IPC 走什么协议？bincode？protobuf？JSON？
- 反序列化时的大小限制？
- Sandbox 侧反序列化漏洞 → 直接 sandbox 进程内执行 → 但 Sandbox 已经在 cgroup 内，看似安全
- **Engine 侧反序列化** action buffer 时如果有漏洞 → engine 被直接攻陷（这是真正危险的方向）

修复：明确 IPC 协议（建议 length-prefixed bincode + Engine 侧严格 schema 校验 + actions buffer 反序列化前先解析 outer envelope，校验大小/类型/计数都在限内才进行内层反序列化）。

---

## Informational

### I1. Blake3 XOF 加密强度足够，但用法需声明
specs/01 §3.1 用 Blake3(tick || world_seed) 做种子洗牌。Blake3 是 keyed hash 安全的——但没说 `seed` 怎么和 `tick_number` 拼接（`||` 是直接 concat 还是 keyed 模式）。建议显式 `blake3::keyed_hash(world_seed, tick_number.to_le_bytes())`，避免 length extension 在变体哈希上的疑虑。

### I2. WASM `_start` section 与 active element/data segments
specs/04 §2.4 显式拒绝 StartSection（好），但 active element/data segments **也**会在实例化时执行赋值——可能在 fuel 计量启动前。step 7 写了「Store fuel/epoch 在 Instance::new() 前生效」——把这条标为 MUST，CI 加测试 wasm 含 active segment 触发越界写。

### I3. Tutorial → Production 帐号污染
specs/09 §2.4：「Tutorial 来源的指令仅可在 `world.mode = "tutorial"` 的世界中接受」——但同一玩家可以在多个世界。Tutorial 世界里可以用免费部署练手 → Tutorial 内培养出的 WASM 模块 hash 可以直接被同账号 deploy 到 production world——这是 feature 还是 bug？文档没说。

### I4. fuel refund 退还周期与 deploy-reset 例外的「同 session_id」
specs/02 §7.2：「同一 session 内的迭代部署（同 session_id）不清除 credit」——session_id 谁分配？玩家自报？那\"同 session\"完全可控 → 攻击者总声明 session_id=1 → deploy-reset 永不触发。如果服务端分配，文档要说怎么分配 + 怎么过期。

### I5. `swarm_simulate` 总配额无全局上限
specs/04 §6.1：「max_fuel_per_hour: 50,000,000 每玩家」+ 500 玩家上限 = 全局 25 G fuel/h。simulate 是 CPU 重负载，没有全局上限会被多账号联合刷爆。

### I6. Phase 2a 内 Spawn 校验通过但 Phase 2b spawn 时 room cap 已变
specs/01 §3.3.1：「Spawn 命令只校验不入队」+ Phase 2b 顺序 `death_mark → spawn → combat`——Phase 2a 校验时 room cap 已经把死亡 drone 算上了吗？还是 Phase 2a 看「当前 World」（含未死的 drone）→ 校验通过 → Phase 2b death_mark 释放槽位 → spawn_system 真创建 drone：等于校验时和实际创建时 room cap 数值不同。如果校验时偏紧（包含未死的 drone）问题不大；偏松（漏掉未死的 drone）可能 spawn_system 二次拒绝——这条「二次拒绝」流程没写。

### I7. Hack 控制锁 5 tick 内的所有权一致性
specs/02 §3.10 写 stage=5 dronere 转 Neutral。在 stage=1-4 期间 owner 仍是受害者，但 specs/02 §3.10 也说「Hack 不立即转移所有权」——5 tick 内 victim 的 WASM tick() **正常执行**？还是 victim 看到自己 drone 进入 hacking 状态后无法控制？文档可以再清楚一点（攻击者关心：hacking 期间 victim 能否 Recycle 自救？）。

### I8. specs/02 §6 表格里 MAX_BODY_PARTS 列出 50，但 specs/07 §1 配置 max_body_parts=50 是 world 可配项
如果服主把 max_body_parts 配成 1000，specs/02 §6 表格中的硬限制需要被 override——这条可配置需要在 specs/02 §6 注释「值由 world.toml 决定，表中为默认」。

### I9. Determinism contract 中的 Rhai 浮点禁用
DESIGN §8.8：「Rhai 模组脚本同样禁用浮点」——但 §8.7 mod.toml `[config]` 类型表中有 `fixed<u32,4>`，没问题。需要 CI 测试：随机生成 Rhai 脚本，含 `1.5`/`f64::PI`/`Math.sin` → 加载时拒绝。验证浮点确实被关。

---

## 评审员注

我的视角已经压得相当极限——3 Critical + 6 High + 9 Medium + 9 Info 是对一份未实现的设计文档我能挤出的全部攻击面。

可能的盲点（需要其他评审员补位）：
- **gameplay 平衡** 不在我视角——Hack 5 tick / Overload -500k fuel 是不是平衡，Designer 答。
- **Bevy ECS 内部并行模型**的实现细节（不是 spec 写得对不对，而是 Bevy 实际行为是否符合 specs/01 §3.4 矩阵）——Architect 答。
- **DeepSeek security review** 应该会从协议数据流（Token 生命周期、跨服务事务边界）切入，与我互补。

如果 Speaker 在 Phase 2 看到我和 dsv4-security 都标了相同 Critical，那是**真正的**。如果只有我标，可能是我的 paranoia bias，请用我的具体修复要求作为讨论起点。

