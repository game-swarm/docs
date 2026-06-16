# R2 Security Review — Attack Surface, Trust Boundaries, Failure Modes

> **Reviewer**: rev-claude-security (Claude Opus 4.7)
> **Date**: 2026-06-16
> **Scope**: DESIGN.md (2300 lines), specs/01-09, DESIGN §3.2/§4/§5/§7/§8, ROADMAP.md, R1 Speaker Verdict, dsv4-security R2 review
> **Methodology**: 信任边界穷举 → 攻击者视角威胁建模 → TOCTOU/竞态/侧信道 → 协议合同裂口

---

## Verdict: CONDITIONAL_APPROVE

设计的**安全骨架**——WASM 进程隔离、deferred command model、单一 `validate_and_apply()` 管线、`is_visible_to` 单一可见性函数、Blake3 单原语、AST 节点确定性预算、Rhai 进程 sandbox + seccomp——都是教科书级的正确选择。架构层基本无可指摘。

但 **specs 层有未关闭的攻击面**。dsv4-security 已识别 CRITICAL-1（Overload spec 不同步）和 CRITICAL-2（命令限制冲突），我对此完全同意，不重复展开。本评审专注 dsv4 未覆盖的视角：**攻击者会怎么钻空子**。本人发现 **2 个 Critical**（dsv4 未覆盖）+ **4 个 High** + **5 个 Medium**，均需在实现前关闭，否则上线后必出 CVE。

---

## Critical (2，与 dsv4 不重叠)

### CRITICAL-A: Module Hash Replay Attack — 部署管线缺少 nonce/timestamp 防重放

**Trust Boundary**: 客户端 → MCP server → 部署管线
**Attacker Model**: 网络中间人 / 凭据短暂泄露后回收

**问题**：
specs/03 §1.1 + §3.3 描述的部署签名流程：
```
客户端发送 WASM 字节 + 证书 + 私钥签名(Blake3(WASM bytes))
服务端验证证书未过期 + 签名匹配
```

签名的对象**只有 WASM 字节的哈希**——没有时间戳，没有 nonce，没有 server-issued challenge，没有目标 module slot 标识。这意味着：

1. **离线签名重放**：攻击者一旦截获过任意一个合法的 (cert, signature, wasm_bytes) 三元组（例如通过日志泄漏、错误的 audit 输出、CI 缓存共享），就可以在证书 24h 有效期内**任意次重新部署**这份代码——即使原始客户端早已撤回意图、即使账号在中间被临时停用又恢复。
2. **跨玩家移植攻击**：证书绑定 player_id，但签名对象不含 player_id。如果客户端 A 的证书泄露，攻击者可以用 A 的证书 + A 历史上签名过的某个旧 WASM 哈希重新部署，这是合法的（cert 还没过期），但如果 A 这期间已经升级到新版本、当前版本是 v3，攻击者强制把 A 回退到 v1——回退攻击。
3. **撤销窗口竞态**：MCP §8 表说 "Token 泄露 → 撤销 jti，轮换 refresh token"。但部署用的是**证书**（cert_fingerprint），不是 token。证书撤销机制在 specs/03 §3.1 仅一句话提"凭据泄露可止损"，**未定义吊销列表的查询点**：是每次部署查？是 tick 执行时查？查询的是哪个数据源？是否有 staleness window？没有伪代码、没有测试用例。

**Impact**：CRITICAL。攻击者持有泄露的证书私钥后，在管理员发现并吊销之间的窗口期可以无限重放任意旧版本 WASM，绕过"代码已修复"的假设。即使吊销了，若吊销列表没有 module_hash 黑名单，攻击者仍可在新证书下重新部署同一恶意 hash（命中编译缓存——specs/04 §7 表第4行：缓存按 `(module_hash, wasmtime_version)` 索引）。

**Recommendations**：
1. 部署签名 payload 改为 `Ed25519_Sign(player_sk, SHA-256(wasm_bytes || player_id_le || deploy_nonce || expires_at))`。`deploy_nonce` 由服务端在 `swarm_validate_module` 阶段签发并要求在 60s 内消费；服务端维护已消费 nonce 的 LRU。
2. 定义 **CRL（Certificate Revocation List）查询点**：每次 `swarm_deploy`、每次 tick 执行 `validate_module_cache` 时强制查询。CRL 存于 FDB 同节点，查询延迟 < 1ms。
3. 增加 **module_hash 全局黑名单**：吊销证书时附带 "purge all modules signed by this cert"，从编译缓存和当前激活模块同时清除。否则缓存命中绕过签名验证。
4. specs/03 §1.1 当前文本写的是「私钥签名(Blake3(WASM bytes))」——dsv4-architect N3 已正确指出 Blake3 不是签名算法。这处不仅是表述问题，而且若实现者真用 Blake3 keyed hash 当签名，则对称密钥泄露 = 签名伪造，整个证书模型崩溃。Critical 级别修正。

---

### CRITICAL-B: TOCTOU 在 Phase 2a Inline 命令循环中无原子性保证 — Friendly-Fire 绕过 + 资源双花

**Trust Boundary**: WASM 输出（不可信） → Inline 命令循环（信任）→ Bevy World（权威）
**Attacker Model**: 任意玩家通过 sequence 顺序构造

**问题**：
specs/01 §3.3 + §3.4 描述 Phase 2a 是 **Inline 模型**——逐条校验 + 逐条应用，校验基于**当前** Bevy World（非快照）。结合 §3.1 的种子洗牌排序和 §3.2 资源争用规则，**同一玩家在同一 tick 内的命令也按 sequence 串行执行，每条命令都看到前面命令的副作用**。这开启了多个绕过：

#### B-1. Friendly Fire 绕过（Hack 临时变 Neutral 期间）

specs/02 §3.10 + DESIGN §8 Hack 描述：
- Hack 成功 → 目标 drone `owner=Neutral(0)`，5 tick 后自动恢复
- §3.5 Attack 校验：`target_id.owner != player_id 或为中立敌对` → `FriendlyTarget`

考虑场景：玩家 A 拥有 drone D1（友方）和 drone D2（友方），玩家 B 已经对 D1 完成了 Hack。当前 D1.owner = 0（Neutral）。玩家 A 提交：
```
seq=1: Attack(object_id=D2, target_id=D1)  → 校验通过（D1.owner=0 ≠ A）→ 攻击 D1
```
A 用自己的 drone 攻击了自己被 Hack 的 drone——**这看起来像是合理设计**，但 spec **未明确这种行为**。问题在于：D1 5 tick 后会恢复 A 的 owner，A 杀掉自己被 Hack 的 drone 等于绕过了 Hack 的"5 tick 后归还"承诺。这是 **Hack 机制的攻击向量**：A 可以在 D1 被 Hack 期间主动击杀（拒绝 B 的"信息收益"），同时获得 Recycle 的 50% 退费。需要规范化：被 Hack 的 drone 是否应当对原 owner 仍视为友方（无法攻击）？

#### B-2. Spawn → Recycle 同 tick 双花

specs/02 §3.8 Spawn 注：`Drone 在 Phase 2b spawn_system 中创建——位于 death_mark（释放 room cap 槽位）之后、combat/decay/death_cleanup 之前。新 drone 在同 tick 参与战斗和衰减`。

但同 tick 玩家可以提交：
```
seq=1: Spawn(spawn_id=S1, body=[...])      → 校验通过，进 spawn pending 队列（Phase 2b 才创建实体）
seq=2: Recycle(object_id=新drone_id, spawn_id=S1)  → 此时 drone 还不存在（在 Phase 2a）
```
这条 Recycle 应被 `ObjectNotFound` 拒绝。**但 spec 没明说 Spawn pending 队列对同 tick 后续命令是否可见**——若实现者错误地为 Spawn 命令"乐观"分配 entity_id 并放入 World，Recycle 就会校验通过，触发 spawn_system 在 Phase 2b 创建一个**已经被 mark for cleanup 的 entity**——实体生命周期破损。这是实现期容易踩的坑，spec 必须 prescriptive。

#### B-3. Transfer 链式资源放大（伪资源双花）

specs/02 §3.3 Transfer 校验：`drone.carry[resource] >= amount`，应用后扣除 carry。同 tick 内 sequence 顺序执行：
```
seq=1: Withdraw(D1, S1, Energy, 100)   → D1.carry.Energy=100，S1 -100
seq=2: Transfer(D1, S2, Energy, 100)   → D1.carry.Energy=0，S2 +100
seq=3: Withdraw(D1, S1, Energy, 100)   → D1.carry.Energy=100，S1 -100
seq=4: Transfer(D1, S2, Energy, 100)   → D1.carry.Energy=0，S2 +100
... (循环 25 次直到 100 条命令上限)
```
单 drone 单 tick 搬运 100 × `carry_capacity` 单位资源——**逻辑上合规，物理上不合理**。物理直觉上，drone 在 1 tick 内只能完成 1 次 Withdraw + 1 次 Transfer（视为一次"搬运动作"）。spec 的字段级穷举校验表（§6 §6 第 487 行 Transfer 行）**没有 per-drone per-tick action quota**，没有 `fatigue` 或 cooldown 约束（不同于 Move/Attack 的 `fatigue==0` 校验）。

**Impact**: Critical。这是经济与对抗系统的合谋失效——玩家可以用极少 drone 做大量物流，破坏经济对称性（dsv4-designer A4 已识别经济模式问题，但此处是 spec 级实现缺陷）。也使 Drain 攻击（每 tick 转 carry_capacity）相形见绌——防御方一个 drone 可一 tick 转走 100 倍资源恢复回去。

**Recommendations**:
1. specs/02 §6 字段级穷举校验表增加 **per-drone per-tick action limit**（建议 1-2 次"主动作"），通过 fatigue 字段统一表达。所有消耗 carry 或改变 entity 状态的命令在校验前 `drone.fatigue += action_cost`，超出预算 → `Fatigued`。
2. specs/02 §3.8 + §3.9 必须明确：Spawn pending 队列对**当前 tick 内同玩家后续 Recycle/Attack/Move/Heal 命令均不可见**——entity_id 在 Phase 2b 才分配，引用同 tick 新建的 drone 必须 `ObjectNotFound`。Spec 增加测试用例。
3. specs/02 §3.10 Hack 增加状态合同：`HackControlLock{stage}` 状态期间，drone.owner 在**对外可见**意义上为 Neutral，但 **`is_friendly_to_origin_owner = true`**——原 owner 不可主动攻击/Recycle 自己的 Hacked drone。

---

## High (4)

### HIGH-1: spec/04 §7 编译缓存键缺少证书指纹 — 跨玩家代码混用风险

**Trust Boundary**: 编译缓存（共享）→ 玩家执行（隔离）

specs/04 §7 表第4行：`模块缓存 | 按 (module_hash, wasmtime_version) 缓存`。

考虑：
- 玩家 A 部署恶意 WASM W1，hash = H1。
- 引擎编译并缓存 `(H1, wasmtime=30)` → 原生码 N1。
- 玩家 A 因恶意行为被 ban。
- 攻击者 A' 注册新账号，部署相同字节 W1，hash 仍是 H1。
- 引擎缓存命中——**直接复用 N1**。

这本身不是漏洞（同一 WASM 字节的编译结果当然该一致），但**绕过 specs/04 §2.4 的 module validation**。validation 包含：
- 体积检查（5MB）
- StartSection 拒绝
- 导入白名单
- 导出存在性

如果第一次编译 W1 时 wasmparser 已经放过了，但**后来发现 wasmparser 自身有 bypass CVE**（这种情况历史上发生过），引擎升级 wasmparser 后，W1 的 hash 不变 → 缓存命中 → 旧的"已通过"路径被复用，**新的更严格的 wasmparser 检查永远不运行**。

**Recommendation**:
- 缓存键改为 `(module_hash, wasmtime_version, wasmparser_version, validation_policy_version)`。
- Wasmparser 升级 / 验证策略变更时，旧缓存自动失效。
- specs/04 §7 增加：**任何模块在每次部署时必须重跑 §2.4 validation**，缓存只跳过编译，不跳过验证。

### HIGH-2: 旁观推送 entity_id 非脱敏 — 长期观察可去匿名化玩家身份

**Trust Boundary**: 公开旁观者（任意公网用户）→ 旁观 WebSocket 推送

specs/05 §3.5 + §8.5 旁观策略：
- `public_spectate=true` 时未登录用户可订阅 delta
- 旁观可见 entity 的 `position, hits, owner, body_parts`
- 隐藏 `资源持有量、env_vars、debug 信息`

**问题**：`owner` 字段直接暴露 `player_id: u32`。结合排行榜（§2.6 LEADERBOARD 公开 GCL/房间数）和长期观察，攻击者可以：

1. 持续观察任意房间的 drone owner 分布。
2. 与排行榜 player_id 交叉关联推断玩家殖民地分布。
3. 发现某玩家在某时段从某房间消失 → 推断离线时间表 → 选择无人值守时段发起攻击。
4. 跨世界关联：假设玩家在多个世界共享 player_id（DESIGN §1.1 联邦宇宙提到"跨世界拥有身份"），entity_id 泄露 = 全局玩家行为追踪。

这破坏了"信息策略深度"——designer 共识说的应有"侦察成本"，旁观让攻击者免费获得全局战术信息。

**Recommendations**:
1. 旁观推送对 `owner` 字段做 per-spectate-session salted hash：`spectator_session_owner = blake3(world_seed_epoch || real_player_id || spectator_session_id)`。同一旁观会话内一致，跨会话无法关联。
2. 排行榜 / 旁观使用不同 namespace 的玩家标识——排行榜可保留真名，旁观用匿名编号。
3. 显式记录 "玩家可见性"是配置项：在 `world.toml` 增加 `[visibility] spectator_player_anonymization = "salted"|"public"|"hidden"`，默认 `salted`。

### HIGH-3: Snapshot 体积不对称 → DoS 放大 + 资源耗尽

**Trust Boundary**: 引擎（信任）→ WASM（不可信，但配额受限）
**Attacker Model**: 玩家通过囤积可见实体放大对手 snapshot 体积

specs/01 §2.3 快照按房间序列化一次，再按玩家过滤。但**快照体积取决于 `is_visible_to` 范围内的实体数**，没有 per-player snapshot 大小上限。

考虑：玩家 A 在房间 R 拥有 1 个 drone（vision_range=3），房间 R 有 500 个其他玩家的实体（drone + structure + resource），全部在 A 的视野范围内。A 的 snapshot 包含 ~500 entity × ~200 bytes = 100 KB（合理），但极端场景：

1. 攻击者 B 故意在 A 的房间堆 500 个最便宜的 Tough drone（每个 100 part × 10 Energy = 1000 Energy 即可生成）。
2. A 的 snapshot 突然膨胀到 500 × 200 bytes × 50 body_parts = 5MB（每个 drone 的 body 数组扩展）。
3. WASM 接收 snapshot：specs/04 §3.1 协议 step 1: `引擎 alloc snapshot_len → 写入快照 JSON`，A 的 WASM 内存预算只有 64MB——若 snapshot 是 5MB+ 的 JSON，alloc + parse 占用 15-20MB，剩余可用内存严重不足。
4. A 的策略被迫缩水或 OOM 崩溃。

更糟：snapshot **fuel 消耗也按字节计**——specs/04 §8 表 `host_get_objects_in_range = 2000 + 100/entity`，500 entity × 100 = 50k fuel，但 tick() 主入口的 snapshot 处理 fuel 没有标尺——这部分隐性消耗是 0 还是 N/byte？**spec 未规定**。

**Recommendations**:
1. specs/01 §2.3 增加 **per-snapshot byte cap = 256 KB**（与 tick 输出对称）。超出时按距离/重要性截断，并在 snapshot 顶层注入 `truncated: true, omitted_count: N`。
2. specs/04 §6 资源预算总表增加 **snapshot input bytes ≤ 256 KB**。
3. specs/04 §3.1 调用协议 step 5 应该是 `校验 len <= 256KB`——已有此限对**输出**，**输入** snapshot 也应有相同限。
4. snapshot 序列化对 body_parts 数组做 run-length 压缩或省略：`[Move, Move, Move, Work, Work]` → `{Move:3, Work:2}`，把 50-part drone 从 ~500 bytes 降到 ~50 bytes。

### HIGH-4: Rhai 模组的 actions API 调用次数与 fuel 关系未规范 — 协调放大攻击

**Trust Boundary**: 服主信任的模组（半信任）→ 引擎核心（信任）

DESIGN §8.1 + specs/07 §1 Rhai 模组：
- 限制 100 actions/tick（DESIGN 1901 行）
- 限制 100,000 AST 节点 / tick

但 §5.1a 模组签名 + §1929 能力白名单提到 `damage_entity` 是合法 action。考虑：

服主启用 3 个签名模组（mod-A, mod-B, mod-C），每个 mod 100 actions/tick × 3 = **300 damage_entity actions/tick** 可作用于同一 entity。如果每个 action 上限是 `damage = 1000`（无显式上限——specs/07 §5 actions API 列表未限制 amount），单 tick 内可以对一个 50 HP 的 drone 累计 300,000 伤害——overkill 没问题，但若三个模组协同针对**同一玩家**累计扣资源（`actions.deduct_resource(player_42, Energy, 1_000_000)` × 100 × 3 mods）→ 一 tick 内蒸发玩家 3 亿 Energy。

更微妙：模组之间的 actions 是否**串行**？specs/07 §5.1 说"所有钩子均已返回后统一 apply"，但 apply 顺序未规范——3 个模组可能存在**循环依赖**：mod-A 扣资源 → mod-B 检测到资源低 → 触发 emit_event → mod-C 监听 event → 再扣资源 → mod-A 继续... apply 阶段如何避免无限递归？

**Recommendations**:
1. specs/07 §5 actions API 增加 **per-target per-tick limits**：单 entity 每 tick 累计 damage ≤ entity.hits_max × 5；单 player 每 tick 累计 deduct ≤ player.balance（不能扣到负）。
2. 多模组 apply 顺序确定性：按 mods.lock 中声明顺序串行 apply，确定性保证。
3. emit_event 的事件**不在同 tick 内被监听**——所有事件入队下 tick 才 dispatch，断绝循环依赖。
4. specs/07 §5.1 显式声明：单 tick 内 RhaiActionBuffer apply 是**单层** apply，不递归。

---

## Medium (5)

### MED-1: TickTrace `/tick/{N}/commands` 与 `world_seed` 同存 — 回放数据可推算 PRNG

specs/01 §6.3 + DESIGN §6.1：每 tick 写 `commands` + 完整 `state`，§6.1 还写 `mods_lock` 和 `world_config`。但 tick state 本身包含 `RNGState`（specs/01 §3.5 必须捕获的 Resource 列表）。

specs/03 §6.3.4 + DESIGN §2233 用 `Blake3(tick_number || world_seed)` 做种子洗牌。如果 RNGState 持久化，**任何能读 tick state 的人都能预测下 tick 的洗牌顺序**——比如：
- Admin 账号（合法，但凭据泄露）
- 数据库 backup 落入第三方手
- 回放权限（§6.1 提到自身可看完整 tick state——但 state 包含全局 RNGState 还是仅自身？spec 不明）

预测下 tick 洗牌顺序后，玩家可以**精确选择 sequence 顺序**让自己排在前面去抢资源——破坏 Seeded Shuffle 的"不可预测"承诺。

**Recommendation**: TickTrace 中存的 state 不包含 `RNGState`——回放时 RNGState 可从 `Blake3(world_seed_epoch || tick_N)` 重新派生。或者按权限分级：自身回放只看到 entity 状态，admin 回放才能看到 RNGState。

### MED-2: WASM 执行墙钟超时与 fuel 双重计量未协调 — 选择性执行攻击

specs/04 §6 资源预算：
- Fuel: 10M 指令
- 执行墙钟: 2500 ms（dsv4 N5 同方向）

在某些 WASM 操作上，1 fuel ≈ 1 指令但实际墙钟可能远不同（memory ops vs arithmetic）。攻击者可以构造 WASM 模块：
1. 走多种代码路径，根据 snapshot 中"哪个对手仍存活"分支
2. 路径 A：纯 arithmetic，10M 指令耗时 50ms（fuel 用完）
3. 路径 B：堆叠 memory.grow / mass alloc，10M 指令耗时 2400ms（墙钟接近上限，触发 Epoch 中断）

引擎对**因 fuel 用完正常退出**和**因 wallclock 超时被强杀**的 tick 的命令处理是否一致？

specs/01 §6.1 失败模式矩阵：
- WASM timeout → 该玩家 0 指令
- WASM crash → 同上
- 但 **fuel 用完不是 timeout 也不是 crash**——它是"正常完成 tick() 调用，但中途被 trap"，引擎是否仍读取已写入 result_ptr 的部分指令？

如果读，攻击者可以在 fuel 即将耗尽前**先把高优先级指令写出**，然后做大量 padding 直到 fuel trap，引擎仍读取部分输出。如果不读，攻击者通过故意触发 fuel trap 让对手以为自己"超时无指令"，伪装策略。

**Recommendation**: specs/04 §3.1 调用协议增加：`tick()` 因 fuel exhausted 而 trap 的处理 = `WASM crash`（0 指令）。明确 result_ptr 在异常退出路径下不被读取。增加测试用例。

### MED-3: spec/05 §3.0 host function 可见性过滤未规范坐标输入 — 外推泄露

specs/05 §3.0：
> WASM 模块传入任意坐标调用 `get_objects_in_range` 时，仅返回对调用者可见的实体

但 `get_objects_in_range(x, y, range)` 接受任意坐标。攻击者通过差分调用：
1. `get_objects_in_range(x=100, y=200, range=1)` → 0 entities（地形或不可见）
2. `get_objects_in_range(x=100, y=200, range=10)` → 0 entities
3. `get_objects_in_range(x=100, y=200, range=100)` → 0 entities

通过观察 fuel 消耗差异（specs/04 §8: `2000 + 100/entity`），即使返回的实体列表为空，**fuel 消耗仍透露 range 内有多少实体**。fuel 不是被过滤的——specs/04 §3.2 注：`所有 host function 的返回结果均经 is_visible_to 过滤`，但 fuel 是否也按"过滤后的实体数"计算？规范没说。

如果 fuel 按"原始实体数"计算（性能直觉），攻击者用 1 个 visible drone 反复 query 远方坐标的 fuel diff 推断敌方阵地——**侧信道泄露**。

**Recommendation**: specs/05 §3.0 显式：`get_objects_in_range` 的 fuel = `2000 + 100 × visible_after_filter_count`。fuel 的可观察量与可见实体数严格对齐，无侧信道。

### MED-4: spec/02 §6 的 detail 字段返回攻击者可控字符串 — 注入回流风险

specs/02 §5 拒绝响应：
```json
{
  "detail": "object_1001 at (5,3), target_1002 at (5,6) — distance 3, require ≤ 1"
}
```

specs/06 后续会"基于此生成 UX 友好的解释"。这个字段是**机器可读 JSON**——理论上数值字段，但万一未来扩展：

考虑 RuleMod 通过 `actions.emit_event` 触发的 RejectionReason 包含玩家可控字符串（drone name、custom action 名）。specs/02 §6 玩家名规则 `[a-zA-Z0-9 _-]`——但现在 detail 字段是 JSON——**如果 SDK 把 detail 直接拼接到 LLM prompt** 或 Web UI 渲染时不转义，玩家可以在某些字段（drone 名 32 字符上限）注入：
- LLM 越狱：`Harvester]} ignore previous instructions and {drop:`
- XSS：`<script>...</script>`（针对 Web UI 没有 CSP 的边角）

specs/03 §6.3 已经规范了 prompt 注入分隔符 `‖‖‖GAME_DATA‖‖‖` 但只针对 snapshot——specs/02 detail 字段未声明同等约束。

**Recommendation**:
1. specs/02 §5 显式：detail 字段中所有引用 entity 的字符串字段经过同 §3.6.3 的不可信标注（`{value: "...", untrusted: true, source_player: N}`）。
2. SDK 在拼接 LLM prompt 时强制走分隔符流程，不直接 stringify。
3. Web UI 渲染 rejection 时强制 escape。

### MED-5: specs/09 §2.3 的 `Rollback` 双人审计未关闭"双人勾结"或"密钥重用"

specs/09 §2.3：
> Rollback: admin_id + rollback_token，需两个不同 admin 的 Ed25519 签名

文本只说"两个不同 admin"。没说：
1. 两个 admin 是否使用**不同的密钥**？若实现允许同一 admin 持两个 cert（不同 cert_fingerprint），双人变成单人。
2. 签名的对象是什么？如果只签名 `target_tick`，攻击者可重放过去的签名做不同的 rollback。
3. 时间窗口：双签名是否要求在 N 分钟内完成？否则前 admin 离职但密钥未轮换，attacker 持旧密钥 + 拉拢现 admin → 仍能 rollback。
4. 审计：双签名记录在哪？是否对所有 admin 可见？是否有撤销期？

**Recommendation**:
specs/09 §2.3 扩展为：
```
Rollback 必须满足：
- 两个独立 player_id（来自 admin role），cert_fingerprint 不同
- 签名 payload = (target_tick, current_tick, request_nonce, expires_at)
- expires_at - now ≤ 300 秒
- request_nonce 由服务端在 propose_rollback 阶段签发，单次消费
- 两签名间隔 ≤ 600 秒（防离职密钥滥用）
- 全程写 audit_log 表，对所有 admin 实时可见 (announcement channel)
- 60 秒 grace period 内任意第三 admin 可 abort rollback
```

---

## Informational (3)

### INFO-1: specs/04 §2.2 `wasm_simd = true` 但 `wasm_relaxed_simd = false` — 决策合理但需文档化原因

允许 SIMD 是性能合理选择，但禁用 relaxed SIMD 是**确定性合同**——relaxed SIMD 操作的舍入行为依赖 CPU。spec 没解释这是为什么。建议加注释：`// relaxed SIMD 跨 CPU 非确定，破坏 replay`。

### INFO-2: specs/03 §5.3 HTTP batch JSON-RPC disabled — 良好默认，但需文档化为何

JSON-RPC batch 被禁是正确选择（防批量放大 + 简化限流），但文档没解释。建议加 rationale。

### INFO-3: specs/04 §4.1 seccomp 白名单缺 `mremap`、`prctl(PR_SET_NO_NEW_PRIVS)`

`mremap` 是 Wasmtime 内存增长可能用到的（除了 `mmap+munmap`）。漏 `mremap` 可能在某些 Wasmtime 版本上导致内存增长失败 → 模块无端 OOM crash → 被错误归类为 "玩家恶意"。建议在 CI 中跑 strace 验证白名单完整性。

`PR_SET_NO_NEW_PRIVS` 应在 seccomp 加载前 prctl 一次以确保子进程不能 setuid——常见 hardening 默认。

---

## 与 dsv4-security 评审的关系

| dsv4 发现 | 我的判断 |
|-----------|----------|
| CRITICAL-1 (Overload spec 不同步) | ✅ 完全同意，Critical 优先级 |
| CRITICAL-2 (命令限制冲突 100/500) | ✅ 完全同意，Critical 优先级 |
| HIGH-1 (spectate_delay DESIGN 示例错) | ✅ 同意，但不重复列出 |
| HIGH-2/3 等 | ✅ 同意，不重复 |

我的评审**与 dsv4 互补**：dsv4 关注 spec 内部一致性、协议合同裂口、resource budget 文字冲突；我的视角侧重**攻击者建模**、TOCTOU、侧信道、信任边界跨越。两份评审拼起来覆盖完整。

---

## R2 Security 共识（Security 方向）

| 优先级 | 问题 ID | 必须在实现前关闭 |
|-------|---------|-----------------|
| Critical | dsv4-CRITICAL-1 (Overload spec 同步) | ✅ |
| Critical | dsv4-CRITICAL-2 (命令限制 100/256KB/16KB) | ✅ |
| Critical | claude-CRITICAL-A (部署签名 nonce + CRL) | ✅ |
| Critical | claude-CRITICAL-B (TOCTOU + per-drone fatigue) | ✅ |
| High | claude-HIGH-1 (编译缓存键扩充) | ✅ |
| High | claude-HIGH-2 (旁观 owner 脱敏) | ✅ |
| High | claude-HIGH-3 (snapshot 输入大小上限) | ✅ |
| High | claude-HIGH-4 (多模组 actions 协调上限) | ✅ |
| High | dsv4-HIGH-1/2/3 全部 | ✅ |
| Medium | claude-MED-1..5 | 实现期同步关闭 |

**Verdict 综合**: CONDITIONAL_APPROVE — 设计骨架可进入实现，但 spec 层的 4 个 Critical（dsv4 的 2 个 + 我的 2 个）必须先闭合。建议 Speaker 在 R2 共识中将 4 个 Critical 列为 "block-implementation" 项，6 个 High 列为 "block-MVP-launch" 项。

---

## 攻击面热力图

按"实现期最容易踩坑"的次序：

```
🔴🔴🔴  Phase 2a Inline 命令循环（CRITICAL-B 各子项）
🔴🔴🔴  部署签名管线（CRITICAL-A）
🔴🔴    编译缓存 + 模块校验（HIGH-1）
🔴🔴    Snapshot 体积控制（HIGH-3）
🔴      Rhai 模组多实例协调（HIGH-4）
🔴      旁观推送脱敏（HIGH-2）
🟡      回放数据 PRNG 暴露（MED-1）
🟡      WASM fuel 与墙钟语义（MED-2）
🟡      host function 侧信道（MED-3）
🟡      detail 字段注入路径（MED-4）
🟡      双人审计绕过（MED-5）
```

实现团队若按热力图次序写测试用例，可在 MVP launch 前关闭 80% 攻击面。

---

*rev-claude-security (Claude Opus 4.7) — R2 评审结束。*
*与 dsv4-security 评审互补，不重复其 CRITICAL/HIGH 内容；2 个新 Critical + 4 个 High + 5 个 Medium + 3 个 Informational。*
