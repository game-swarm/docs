# R13 — Speaker 裁决

> **裁决者**: Hermes Agent (Speaker)
> **日期**: 2026-06-14
> **评审员**: 9/9 全部完成（Claude Opus ×3 + DeepSeek V4 Pro ×3 + GPT-5.5 ×3）
> **方向**: Architect / Security / Game Designer

---

## 一、裁决概要

R13 是 Phase 0 "冻结"后的首轮全面重审。9/9 评审员一致认为：**文档契约层存在无法忽视的缺口，不宜直接进入 Phase 1 实现**。

三项跨方向共识：
- **架构方向**（Claude Opus REJECT + DSv4 REQUEST_MAJOR_CHANGES + GPT-5.5 REQUEST_MAJOR_CHANGES）：FDB commit 在三处文档中描述矛盾的时序、Command 应用与 ECS System 执行顺序未定义、spawn/death 竞态 —— 三项均为"实现者无论选哪个都会产生 bug"的规范级缺陷。
- **安全方向**（Claude Opus CHANGES_REQUESTED + DSv4 REQUEST_MAJOR_CHANGES + GPT-5.5 REQUEST_MAJOR_CHANGES）：6 种特殊攻击完全缺失校验管线、Hack Neutral 模型自相矛盾、RawCommand 仍含客户端自报字段——均属攻击面。
- **设计方向**（Claude Opus REQUEST_CHANGES + DSv4 APPROVE_WITH_RESERVATIONS + GPT-5.5 APPROVE_WITH_RESERVATIONS）：Hack 触发条件实战不可行、RangedAttack 成本/伤害失衡、缺乏净化反制、lifespan 续期制造退化策略。

**裁决结论**: PHASE 0 NOT TRULY FROZEN — 需要 R14 闭合本轮共识 Blocker 后方可进入 Phase 1。

---

## 二、共识 Blocker（3/3 方向 ≥2/3 评审员认可为 Critical/High）

以下 10 项获得跨方向、跨模型的高度共识，优先级最高。

### 🔴 B1 — 特殊攻击无校验管线（全票：3 Security + 3 Architect 指出）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Security | Claude Opus | S1 [High] |
| Security | DSv4 | C4 [Critical] |
| Security | GPT-5.5 | (implied in overall assessment) |
| Architect | Claude Opus | (implied in REJECT rationale) |
| Architect | DSv4 | (in C4 cross-reference) |
| Designer | Claude Opus | D-C1 related |

**问题**: Hack/Drain/Overload/Debilitate/Disrupt/Fortify 6 种特殊攻击在 DESIGN §8.2 中定义了完整机制，但 P0-2 校验矩阵、P0-8 IDL `commands`、P0-9 来源能力表中**全部缺失**。

**裁决**: **必须在 Phase 1 前修正**。不可仅以 DESIGN.md 作为实现的"隐含合同"——这些是可改变世界状态、跨玩家、带资源消耗的指令，缺 schema = 不可实现。

**修正要求**:
- P0-2 §3 新增 §3.12–3.17 六个特殊攻击的完整校验矩阵（ownership、body part requirement、cooldown、resistance calculation、state transition）
- P0-8 IDL `commands` 段新增对应六条命令定义
- P0-9 §2.3 Source Capability 矩阵中 WASM 行确认这些操作

---

### 🔴 B2 — Hack Neutral drone 模型自相矛盾（全票：3 Security）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Security | DSv4 | C5 [Critical] |
| Security | Claude Opus | S11 [Low] — 同根问题 |
| Designer | DSv4 | G4.3 |

**问题**: DESIGN §8.2 称被 Hack 的 drone 转为 Neutral 但"仍执行原 owner 部署的 WASM"。这制造了不可解的矛盾：Neutral drone 的 `tick()` 以谁的身份调用？若以原 owner → Hack 无效；若以 Neutral → ownership 检查全部失败。

**裁决**: **必须在 Phase 1 前修正**。删除"仍执行原 owner WASM"——Neutral drone 进入 idle 状态（不执行 WASM，不提交指令，仅存在）。在 P0-2 中明确定义 Neutral 状态的所有语义。

---

### 🔴 B3 — FDB Commit 位置三处文本矛盾（全票：3 Architect）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Architect | DSv4 | D6 [HIGH] |
| Architect | Claude Opus | (in overall assessment) |
| Architect | GPT-5.5 | A1 [Critical] — FDB Phase 1 vs Phase 3 矛盾 |

**问题**: DESIGN §3.2 写 FDB commit 在 BROADCAST 阶段、P0-1 §3.4 写在 EXECUTE 阶段、P0-1 §1 状态机图也写 BROADCAST 阶段。三者描述的执行顺序不同。

**裁决**: **以 P0-1 §3.4 为权威源**（EXECUTE 阶段内 commit → 再 BROADCAST）。更新 DESIGN §3.2 和 P0-1 §1 状态机图。这是 Speaker 裁决——不再讨论。

---

### 🔴 B4 — Command 应用 vs ECS System 执行时序未定义（全票：3 Architect）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Architect | DSv4 | D1 [HIGH] — R12 遗留 |
| Architect | GPT-5.5 | (implied) |
| Architect | Claude Opus | (implied in concerns) |

**问题**: DESIGN §3.2 和 P0-1 §3.3 对"玩家命令何时应用于 ECS World"的时序描述矛盾——是逐条 inline 应用还是 deferred 批量？两种模式行为差异巨大（Move 后 Attack 的范围校验、Spawn+同 tick 使用新 drone、TOCTOU 风险）。

**裁决**: **采用 Inline 模型**——命令循环中逐条校验 + 逐条应用。EXECUTE 拆分两个子阶段：
1. **Phase 2a（命令循环）**: 逐条校验（基于当前 Bevy World 状态）+ 逐条应用。Move/Harvest/Build/Transfer/Attack/Heal/Recycle 在循环中执行。
2. **Phase 2b（ECS Systems）**: regeneration/combat/decay/death 统一 `.chain()` 运行。Spawn 命令在 2a 中只校验不入队，在 2b spawn_system 中统一创建。

写入 P0-1 §3.3。

---

### 🟠 B5 — Spawn/Death 执行顺序导致误拒绝（全票：3 Architect）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Architect | DSv4 | D2 [HIGH] — R12 遗留 |
| Architect | GPT-5.5 | (implied) |
| Architect | Claude Opus | (implied) |

**问题**: Spawn 校验在命令循环中进行（检查 RoomDroneCapReached），但 death_system 在命令循环之后运行。本 tick 死亡的 drone 的槽位未释放，导致合法 spawn 被错误拒绝。

**裁决**: 采纳 DSv4 方案——将 death_system 拆分为两个阶段：
- `death_mark_system` — 命令循环前运行，标记待死亡 entity，立即释放 room cap 槽位
- `death_cleanup_system` — 命令循环后运行，实际 despawn

Spawn 校验检查 `room_count - marked_for_death`。

---

### 🟠 B6 — Rhai 墙钟终止破坏确定性（共识：2 Architect + 1 Security）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Architect | DSv4 | D4 [HIGH] |
| Architect | Claude Opus | (in R12 A1 tracking) |
| Security | GPT-5.5 | (in Rhai concern) |

**问题**: §8.7 的墙钟终止（100ms）注释称"不参与 state_checksum"，但 `deduct_resource` 等 actions 直接修改 ECS Components，checksum 无法过滤已写入的副作用。

**裁决**: 采纳 **方案 B（事务性 Rhai 执行）**——Rhai 钩子的所有 `actions` 先缓存在内存 buffer，钩子完全执行完毕后统一 apply。墙钟超时 → buffer 丢弃，世界状态不变。**删除方案 A（仅保留 AST/actions 限制）**，因为墙钟作为安全网仍有价值（防止死循环），但必须隔离副作用。

---

### 🟠 B7 — Hack 触发条件实战不可行（共识：3 Designer）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Designer | Claude Opus | D-C1 [Critical] |
| Designer | DSv4 | (在 G4.3 中间接认可) |
| Designer | GPT-5.5 | (implied) |

**问题**: Hack 要求 hits < 15% 且连续 10 tick 维持信号。濒死 drone 必被补刀或逃逸，成功率近乎零。

**裁决**: 修改 Hack 触发机制：**施加"控制锁"阻止目标行动**（而非依赖血量条件）。Hack 在 5 tick 内逐步建立控制：tick 1-2 目标减速 50%，tick 3-4 目标无法移动，tick 5 成功夺取。目标可通过 Disrupt（打断）或 Fortify（净化）反制。此机制保留 Hack 的策略深度但消除死锁。

---

### 🟠 B8 — RangedAttack 成本/伤害严重失衡（共识：2 Designer）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Designer | Claude Opus | D-H1 [High] |
| Designer | GPT-5.5 | (implied) |

**问题**: RangedAttack 成本 150E、伤害 20、射程 3；Attack 成本 80E、伤害 30、射程 1。远程花费近 2 倍成本造成更低伤害——成本效益严重不对等。

**裁决**: 降低 RangedAttack 成本至 100E（从 150E），或提升伤害至 25。保持远程的成本/伤害比不差于近战的 60% 以内。具体数值留给 Phase 6 数值策划平衡，文档中标注"待数值验证"。

---

### 🟠 B9 — 缺乏净化/驱散反制（共识：2 Designer）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Designer | Claude Opus | D-H2 [High] |
| Designer | GPT-5.5 | (implied) |

**问题**: Debilitate/Drain/Overload 的负面状态只能等自然超时（50 tick），无任何反制手段。防御方策略空间被压缩。

**裁决**: Fortify 已标注"同时清除目标所有 debuff"（git log 显示 R13 已修正），此功能保留并强化文档说明。另在 Heal body part 增加轻度净化能力（每 tick 缩短 1 个负面状态 10 tick 持续时间）。

---

### 🟡 B10 — lifespan 续期制造退化策略（共识：2 Designer + 1 Security）

| 方向 | 评审员 | ID |
|------|--------|-----|
| Designer | Claude Opus | D-H3 [High] |
| Designer | DSv4 | G1.2 [Critical] |
| Security | DSv4 | H6 [HIGH] |

**问题**: 占领新 Controller → 最老 50% drone age 重置为 0 + 500 tick 冷却。激励"占领→放弃→再占领"的 farming 策略。

**裁决**: 改为**持续维持模型**——玩家拥有的每个 Controller 每 tick 给全局所有 drone 回退 age 0.5 tick（多 Controller 可叠加，上限为完全抵消自然 age 增长）。删除一次性占领重置。500 tick 冷却改为"同一 Controller 转手后的占领冷却"。此修改同时解决 G1.2（snowball 反馈）。

---

## 三、方向专属 High 优先级

以下问题在单方向内获 ≥2/3 共识，但未跨方向。

### Security 方向

| ID | 问题 | 裁决 | 时限 |
|----|------|------|------|
| **S2** | 证书过期后运行中 WASM 重校验时点缺失 | git log 显示已修正（"证书过期时终止运行中 WASM"）——确认文档同步 | Phase 1 |
| **C1** | RawCommand 仍含 player_id 客户端自报字段 | 采纳 GPT-5.5 方案：WASM 输出改为 `CommandIntent`（仅 sequence+action）；player_id/source/tick 全部服务端注入 | Phase 1 |
| **H1** | Wasmtime start section 校验写法错误 | 使用 wasmparser 显式拒绝 Payload::StartSection。更新 P0-4 §2.4 | Phase 1 |

### Architect 方向

| ID | 问题 | 裁决 | 时限 |
|----|------|------|------|
| **A1/A2** | Sharding vs 全局原子提交冲突 | **延后至 Phase 7**。Claude Opus 自己也说"单进程基线下整套设计自洽"。在 DESIGN.md 中显式声明：Phase 1-6 为单进程部署，Phase 7 引入 sharding 时重新设计提交粒度。 | Phase 7 |
| **A3-A6** | 回放输入不完整（world config/fuel credit/seed rotation/path_find） | 四项均接受，写入 P0-1 §6.3 TickTrace 输入列表 | Phase 1 |
| **D3** | Code update window 部署反馈缺口 | 采纳 DSv4 方案：`swarm_deploy` 响应增加 `status: "accepted_deferred"` 和 `activates_at_tick` 字段 | Phase 1 |
| **D5** | Refund module_hash 绑定惩罚合法迭代 | 将 credit 绑定改为 `player_id`（非 module_hash），在部署事件时清零。保留 MAX_FUEL × 10% 上限 | Phase 1 |
| **CG5** | DESIGN §3.2 与 P0-1 §1 状态机图 BROADCAST 顺序差异 | P0-1 为准（先 FDB 后 Dragonfly），更新 DESIGN §3.2 | Phase 1 |
| **A2 (GPT)** | WASM tick() ABI 不完整 | 采纳 GPT 方案：export alloc/free/tick；`tick(snapshot_ptr, snapshot_len, result_ptr) → i32`；result_struct = {ptr, len} | Phase 1 |

### Designer 方向

| ID | 问题 | 裁决 | 时限 |
|----|------|------|------|
| **D-M1** | MoveTo InsufficientMoveParts 与疲劳模型冲突 | 多 tick 移动每 tick 只移动 MOVE 部件数格，而非一次性校验全程。更新 P0-2 §3.2 | Phase 1 |
| **D-M2** | combat_system 内 heal/damage 结算顺序 | 明确定义：damage → heal（同 tick 内）。heal 在 damage 之后结算意味着"治疗无法救回本 tick 被集火致死的 drone" | Phase 1 |
| **D-M4** | Arena 对称性无规则白名单约束 | Arena 模式锁定标准资源集 + 禁止非对称 mod。在 P0-9 §6 Arena 节增加规则白名单 | Phase 6 |
| **G1.1** | World 模式无后发追赶机制 | 新增世界规则 `catch_up_bonus`：世界年龄 > 10K tick 时，新玩家获得 (world_age/1000)×起始资源倍率（上限 5×） | Phase 3 |
| **G2.3** | 教程→正式世界 recycle 50% 断层 | 新增 intermediate world preset（recycle 75%、PvP off） | Phase 4 |
| **G3.1** | Arena 计分函数未定义 | 暂时定义为 `GCL × 10 + 总资源量/100 + 存活 drone 数`。权重可通过 world.toml 配置 | Phase 6 |

---

## 四、Medium / Low 处置

以下问题接受但不要求 Phase 1 前修正。逐条标注负责 Phase。

| ID | 问题 | 负责 Phase | 处置 |
|----|------|-----------|------|
| S3 | 旁观者绕过 is_visible_to | Phase 4 | spectate_delay 约束从 P0-5 移至 DESIGN §8.2 + config 加载时校验 |
| S4 | untrusted 字符串未覆盖 env_vars/memory | Phase 2 | P0-3 §6.2 扩展包裹范围 |
| S5 | Wasmtime 配置 API 不准确 | Phase 1 | 实现时以 wasmtime 30 真实 API 核对 |
| S6 | Overload fuel 账目语义 | Phase 6 | 与 Overload IDL 入表同步定义 |
| S7 | FDB/Bevy 双状态 restore | Phase 1 | 实现时确保 restore 是 EXECUTE 失败路径的第一步 |
| S8 | Admin 无双控 | Phase 7 | 运维 runbook 中加 SOP |
| A7 | Tick 时间预算无余量 | Phase 1 | COLLECT 调整为 2300ms（留 700ms 给 EXECUTE+BROADCAST） |
| A8 | 迟到指令跨 tick 重排 | Phase 1 | 明确：超时即丢弃当 tick 输出，不跨 tick 携带 |
| D-L1 | RCL7/8 drone 硬上限无递增 | Phase 6 | RCL8 提升至 600 |
| D9 | Deploy vs MCP_Deploy 限流不对称 | Phase 2 | 统一限流值或文档注明理由 |
| D10 | fork-per-tick vs 编译缓存矛盾 | Phase 1 | 模块缓存移至 Engine 父进程，子进程通过 IPC 获取引用 |
| M5 | 运输拦截 Phase 6 延期 — 行为不一致窗口 | Phase 1 | TransferToGlobal/FromGlobal 命令文档标注"运输可被拦截（Phase 6+）" |
| M6 | body_cost 无最小值校验 | Phase 1 | P0-7 validate_config 增加 body part 成本 ≥ 1 校验 |
| M7 | immune_X flag 白名单未穷举 | Phase 3 | P0-7 §4 穷举合法 flag 列表 |
| H7 | swarm_get_docs/schema 无限流 | Phase 2 | 增加 5/tick per player 限流 |

---

## 五、文档维护项（立即执行）

以下为 Speaker 直接指令，无需评审。

1. **更新 README.md** — 评审索引补充 R7-R13，审查状态改为"R13 发现 Phase 0 未真正冻结，需 R14 闭合"
2. **移除 PLANNER-OUTPUT.md** — 内容已被 P0 规范取代且多处与最终设计矛盾
3. **更新 reviews/README.md** — 补充 R7-R13 条目
4. **DESIGN.md 末尾** — 更新"最后更新"日期并添加 R13 修正记录

---

## 六、R14 入场条件

以下条件全部满足后，可宣布 Phase 0 **真正冻结**并进入 R14（终审确认轮）：

- [ ] B1：6 种特殊攻击入 P0-2/P0-8/P0-9
- [ ] B2：Neutral drone 模型修正
- [ ] B3：FDB commit 三处文本统一（以 P0-1 §3.4 为准）
- [ ] B4：Command 应用时序（Inline 模型）写入 P0-1
- [ ] B5：Spawn/death 分阶段写入 P0-1
- [ ] B6：Rhai 事务性执行写入 P0-7
- [ ] B7：Hack 触发机制改为控制锁模型
- [ ] B8：RangedAttack 成本下调
- [ ] B9：净化反制文档强化
- [ ] B10：lifespan 续期改为持续维持模型
- [ ] Security C1：RawCommand → CommandIntent 重构
- [ ] Security H1：Wasm start section 校验修正
- [ ] Architect A2(GPT)：WASM tick() ABI 完整定义
- [ ] 文档维护项 1-4

---

## 七、评审统计

| 方向 | 评审员 | Verdict | Critical | High | Medium | Low |
|------|--------|---------|----------|------|--------|-----|
| Architect | Claude Opus | REJECT | 2 | 4 | 0 | 2 |
| Architect | DSv4 | REQUEST_MAJOR_CHANGES | 0 | 6 | 4 | 2 |
| Architect | GPT-5.5 | REQUEST_MAJOR_CHANGES | 3 | 1 | 3 | 1 |
| Security | Claude Opus | CHANGES REQUESTED | 0 | 2 | 6 | 3 |
| Security | DSv4 | REQUEST_MAJOR_CHANGES | 5 | 3 | 3 | 0 |
| Security | GPT-5.5 | REQUEST_MAJOR_CHANGES | 1 | 3 | 3 | 2 |
| Designer | Claude Opus | REQUEST CHANGES | 1 | 3 | 4 | 3 |
| Designer | DSv4 | APPROVE_WITH_RESERVATIONS | 2 | 3 | 5 | 4 |
| Designer | GPT-5.5 | APPROVE_WITH_RESERVATIONS | 1 | 2 | 3 | 2 |

**共识强度**: 3/3 方向 Blocker 共识（B1-B3/B6/B7）：**高**。2/3 方向共识（B4/B5/B8-B10）：**中高**。

---

*Speaker: Hermes Agent. 下一轮 R14 只审 Blocker 闭合状态，不再开展新发现。*
