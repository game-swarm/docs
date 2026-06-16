# R3 Review — Game Designer (Claude Opus 4.7)

> 评审员: rev-claude-designer  
> 视角: 游戏机制 / 平衡性 / 进度系统 / 玩法漏洞  
> 评审范围: design/DESIGN.md (R2 Convergence Patch 后), specs/01-09, ROADMAP.md  
> 日期: 2026-06-16

---

## Verdict

**APPROVE_WITH_RESERVATIONS**

设计在 R2 后已显著收敛——Vanilla 分层、Arena 房间制、特殊攻击经济（B7+B1）、Overload 全局冷却、Spec Convergence（命令上限 500、spectate_delay≥50）等关键问题已闭合。但**作为玩法系统**仍存在 3 个 Blocker 级问题（G1/G2/G5），4 个高优先级数值/边界缺失（G3/G4/G6/G8），以及若干需在 MVP 后观察 meta 演化才能裁决的疑虑。

具体而言：
- ✅ 核心架构 + 经济双层（全局/本地存储）+ 累进税设计**思路正确**
- ⚠️ **数值未填充**（Harvest rate、Spawn cooldown、Tower 充能、Source 上限计算）使设计无法在没有补丁的情况下进入实现
- 🔴 **Fortify 永动护盾**（多 drone 轮换）**几乎完全废掉所有持续型特殊攻击**——这是 R3 评审中最重要的玩法 blocker
- 🔴 **Controller 维修硬上限的语义未定义**——50% 的"自然增长"是 1.0 的 50% 还是 active aging 的 1.1 的 50%？影响所有长期帝国
- 🔴 **age_max 没有下限**——`Drone::new` 用 `i32` 累加 age_modifier，纯 Attack body 算下来是负数，spawn 即死

未解决的 5 个数值/语义缺陷如果在编码前补齐，这套设计可以直接进入实现阶段。

---

## Strengths

### S1: World/Arena 双模并行核心玩法
两种模式共享引擎与 IDL，但通过 `world.toml` 拆分价值取向：World 不追求公平（持久、涌现），Arena 追求公平（房间制、对称地图、Vanilla-only 排名）。R2 后将 Arena 简化为房间制（去天梯/赛季/匹配），承认"对抗主体是算法而非玩家"——这避免了 ELO 系统与 WASM 锁定窗口的内在矛盾，也解决了"AI 玩家是否影响人类排名"的争议。**这一简化是正确的取舍。**

### S2: 经济双层模型（全局/本地 + 三种物流）
- Mode A（无物流）/ Mode B（轻物流，1%+5%）/ Mode C（硬核 Factorio 式）三档可配，让同一引擎承载完全不同的玩法节奏
- 累进存储税 + 本地隐匿性 + 转换需运输时间——三项反垄断机制是**真正考虑了 meta 演化**的设计，不是单纯抄 Screeps
- Drone 必须移动到 Controller / Forward Depot 才能降 age，相邻格只有 6 个 → 物流拥挤是涌现玩法

### S3: 特殊攻击的克制循环（potential）
8 种特殊攻击 + 6 种伤害类型 + 抗性矩阵的设计，理论上能形成"石头剪刀布 × N"的克制深度。Disrupt 打断 Drain/Hack、Fortify 净化 Debilitate、Hack vs Psionic 抗性等链路在概念上自洽。但请见 G1。

### S4: 进度曲线主框架（RCL 1→8）
Controller 升级表的累计 progress（0/200/400/800/1500/3000/6000/12000）是几何递增，对应的解锁内容（Spawn → Tower → Storage/Depot → Link → Terminal/Observer → Lab/Factory → PowerSpawn → Nuker）是渐进的能力扩展。**这一曲线本身合理**，模仿了 Screeps 的成功经验。

### S5: Vanilla 分层（Tutorial/Novice/Standard/Advanced）
B7 后将特殊攻击在 Tutorial/Novice 默认禁用，Standard+ 才开启——这是正确的"复杂度梯度"。但请见 G7。

### S6: 模组化分发模型
"一个模组 = 一个 git 仓库 + 一个签名"——无中心化市场、无审核瓶颈、模组与 mods.lock 配对保证回放确定性，这套设计在工程性和分发自由度上都是漂亮的解。Layer 1/2/3 扩展模型也明确了哪些改动需要 SDK 重生成。

---

## Concerns

### G1 (BLOCKER): Fortify 多 drone 轮换 → 永动护盾，废掉所有持续型特殊攻击

**问题**：
- Fortify 持续 100 tick，冷却 300 tick
- **target_id 是任意己方/盟友 drone**——同一目标可被不同 caster drone 反复 Fortify
- 玩家堆 3 个 Tough drone 轮流 Fortify 同一核心战术单位 → 该单位**永久 50% 减伤 + 永久免疫所有负面状态**（Hack 控制锁、Debilitate 易伤、Drain、Overload 效果）

**数学**：3 个 Tough drone × 100 tick / 300 tick cooldown = 100% uptime。

**后果**：
- Hack 完全失效——5 tick 控制锁会被 Fortify 净化
- Debilitate 失效——50 tick 易伤会被净化
- Drain 失效——Disrupt 之后有 50 tick 真空，但 Fortify 可在该真空净化所有附带状态
- Overload 失效——300 Energy 一发 vs 400 Energy 净化，攻击者亏

整个特殊攻击克制循环的"持续型攻击"分支（Hack/Debilitate/Drain/Overload）在中后期帝国（≥3 Tough drone）之前**没有任何价值**。

**修复方向**（任选其一或组合）：
1. **per-target Fortify cooldown**：同一 target 在 200 tick 内不可被再次 Fortify（即使来自不同 caster）
2. **Fortify uptime cap**：单一 target 的 Fortify buff 在 100 tick 后自动免疫 200 tick（强制 vulnerability 窗口）
3. **净化分级**：Fortify 只清除"低强度"负面状态（Disrupt 触发的中断、Drain），**不清除** Hack 控制锁与 Debilitate（这些需 Disrupt 或被动等待）
4. **更激进**：Fortify 自身不可被刷新，残余 buff 时间内再次施加直接拒绝（`AlreadyFortified`）

**推荐**：方案 1 + 3（per-target cd + 分级净化）。最简且语义最自洽。

---

### G2 (BLOCKER): Controller 维修硬上限语义未定义

**问题**：DESIGN §3.1 与 §8.2 的描述：

> "Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 `max(0, age + 1 - min(0.5, controller_count * 0.5))`）"

**具体疑问**：
1. 自然增长是 idle 的 `+1/tick` 还是 active 的 `+1.1/tick`？整个 active_aging 机制依赖此区分
2. 公式 `min(0.5, controller_count * 0.5)` 意味着 1 个 Controller 已达上限——**多 Controller 完全无加成**？这与 §3.1 维修表 RCL 1→8 容量从 5/tick 增长到 80/tick 矛盾
3. `repair_per_drone`（每 drone 回退量）与"总 age 回退 ≤ 0.5"如何关联？是 per-drone 的硬上限，还是玩家全局的硬上限？
4. age 是 u32，"+1.1" 和 "-0.5" 怎么落到整数？需要小数累加器还是定点数？

**后果**：
- 如果 active drone 真实 aging = +1.1/tick，且 Controller 只能回退 0.5/tick → drone 净 aging = +0.6/tick
- 1500 lifespan 的 active drone 实际寿命 = 2500 tick（看上去合理）
- 但如果 Controller 可叠加 → 实际寿命可达 +∞（不合理）

**修复方向**：明确以下三件事，写进 specs/07：
1. 自然增长定义（active vs idle）
2. 硬上限是 **per-player 全局**（推荐）还是 per-Controller
3. age 内部存储为 `fixed<u32, 4>` 还是引入 `age_accumulator: u32` 字段，跨 tick 累计后整数化

---

### G3 (BLOCKER): age_max 无下限保护 → 极端 body 配置 spawn 即死

**问题**：DESIGN §8.2 / G8a/G8b：

> `lifespan = DEFAULT_DRONE_LIFESPAN + sum(age_modifier)`

按表：Attack=-80, RangedAttack=-50, Heal=-30, Claim=-50。

**反例**：50 个 ATTACK part 的 drone（满 body 极端攻击型）：
- `lifespan = 1500 + 50 × (-80) = -2500`
- `i32` 不会 panic，但语义上 `age >= lifespan` 第 1 tick 即满足 → spawn 即死
- 即使是 20 ATTACK + 30 MOVE：`lifespan = 1500 - 1600 = -100`——同样 spawn 即死

**后果**：
- ROADMAP.md G8a/G8b 标记为 ✅，但测试只覆盖了"4 scenarios"——没覆盖负数 case
- 玩家会发现这个边界，并将其作为"自杀单位"机制（极端攻击 + 自动 Recycle 50% 退还 = 一次性消耗弹）—— 这可能是想要的玩法，但应明确

**修复方向**：
1. 强制 `lifespan = max(MIN_LIFESPAN, BASE + sum(age_modifier))`，建议 `MIN_LIFESPAN = 100`（够走完一次远征）
2. 或者：在 spawn validate 阶段拒绝 `body_cost(body)` 导致 `lifespan ≤ 0` 的组合，返回 `BodyTooShortLived`
3. 选 1 的话，相应增加"短命 drone 警告"——SDK 编译时给提示

**推荐**：方案 2。让玩家在 spawn 阶段就拿到清晰拒绝，比 spawn 即死更尊重玩家。

---

### G4: 关键数值缺失——Harvest rate 未定义

**问题**：通读 DESIGN + specs 02/07/08，**Work part 每 tick 采集多少资源** 未定义。

- DESIGN §3.1 的 `Source.produces = { Energy: 1 }` 是 source 的产出
- DESIGN §8.2 `[[source_types]] regeneration = 300` 是再生总量
- specs/02 §3.2 Harvest 校验提及 `target.source.energy > 0` 但无 rate
- specs/08 IDL 仅声明 action 形状

**后果**：
- 整个采集经济无 baseline——一个 5-Work drone 每 tick 采几能量？
- Source capacity=3000、regeneration=300 意味着每 10 tick 满载——但如果 drone 每 tick 采 50（per Work part），那 60 个 drone 同时采集就抢空了
- 没有这个数字，根本无法估算 spawn 时间、回本时间、扩张曲线

**修复方向**：补一行进 specs/07（建议默认）：

```toml
[harvest]
energy_per_work_per_tick = 2    # Screeps 也是 2，平衡好的起点
```

---

### G5 (BLOCKER): Spawn cooldown 默认值与机制未定义

**问题**：
- specs/02 §3.8 Spawn 校验提到 `spawn.cooldown == 0` 才能 spawn
- 但没说每次 spawn 后 cooldown 设多少
- DESIGN §3.1 Structure 字段有 `cooldown: u32`，但没定义 Spawn 的填充规则
- ROADMAP G5b 提到 Depot 维修，但 Spawn 本身的速率限制未定

**后果**：
- 若无 cooldown，1 个 Spawn 每 tick 出 1 drone，5 tick 出 5 个 → 超过房间能量限制前没有任何节流
- 早期"洗大量小 drone 抢资源点"会成为唯一最优策略
- 与 Screeps 的"spawn 时间 = body parts × 3 tick"完全不同，但 spec 没写

**修复方向**：
- 明确 `spawn.cooldown_after_spawn = body.len() * 3`（Screeps 经验值）
- 或更简单：`spawn.cooldown_after_spawn = max(10, body.len())`
- 写进 specs/02 §3.8 + DESIGN §3.1

---

### G6: Tower 自动攻击的"充能"机制未定义

**问题**：
- specs/05 §2.2 提到 "Tower vision_range = 3（充能后 6）"
- DESIGN §8.2 [[structure_types]] Tower 中无充能字段
- specs/02 没有 Tower 自动攻击的校验路径（因为不是玩家命令）
- DESIGN §3.2 提到 combat_system 处理 Tower 自动攻击，但无规则

**疑问**：
- 充能消耗什么？Energy？
- 充能持续多少 tick？
- 充能时 attack 加成多少？damage 翻倍？range 翻倍？
- 玩家如何触发？还是自动维持？

**修复方向**：在 DESIGN §8.2 Tower 字段补：
```toml
charge = { cost = { Energy = 50 }, duration = 100, damage_mul = 2, range_bonus = 0 }
```
或者：删除这个特性（它在 R2 之前提过但 R2 没收尾）。

---

### G7: Tutorial→Standard 难度梯度过陡

**问题**：Vanilla 分层（B7）：
- Tutorial: 全部 8 种特殊攻击禁用、Recycle 100% 退还、500 tick safe_mode
- Novice: 部分禁用（spec 未细化哪些）
- Standard: **全部 8 种特殊攻击全开**

玩家从"和平 Tutorial"直接跳进"Hack/Overload/Drain 全开"的 Standard，认知负担巨大。

**建议梯度**：
| 层级 | 启用特殊攻击 | 难点说明 |
|------|------------|---------|
| Tutorial | 全部禁用 | 学采集/建造/spawn |
| Novice | Disrupt + Fortify | 学防御 + 净化 |
| Intermediate (新增) | + Hack + Debilitate | 学单体控制 |
| Standard | + Drain + Overload | 学经济战 + 算力战 |
| Advanced | + Leech + Fabricate | 顶级 PvP |

或至少把 8 种攻击的启用顺序在 specs/07 里写死，避免实现时随意。

---

### G8: 累进存储税在大帝国阶段无效

**问题**：DESIGN §8.2 累进税表：

| 容量% | 税率 |
|-------|------|
| 0-30% | 0% |
| 30-60% | 0.01% per tick |
| 60-85% | 0.05% |
| 85-100% | 0.20% |

**数学验证**（基于 `global_storage_capacity = 100000`）：
- 60% 储量（60,000 Energy）每 tick 税 = 60,000 × 0.0001 = **6 Energy/tick** ❌ 太低
- 85% 储量（85,000）每 tick 税 = 85,000 × 0.0005 = **42.5 Energy/tick** ❌ 仍可忽略
- 100% 顶额（100,000）每 tick 税 = 100,000 × 0.002 = **200 Energy/tick** ⚠️ 仍仅相当于 100 个 drone × 2 energy/tick 的产出

对一个 RCL 8、产能 2000+ Energy/tick 的中后期帝国，200 税几乎等于零。

**修复方向**：
1. 累进系数 ×10（变成 0.1% / 0.5% / 2.0%）—— 100% 顶额每 tick 2000 税，对中等帝国有意义
2. 或者税基变为"超过阈值的部分平方"——`tax = (excess / 10000)² × rate`
3. 或者：完全删除税收，改为 Storage 容量软上限 + 超量自动腐烂（更直观）

**推荐**：方案 1。最简且与现有公式兼容。

---

### G9: Hack 后的 Neutral drone 行为未定义

**问题**：DESIGN §8.2 / specs/02 §3.10：
- Hack 第 5 tick 目标转 Neutral，停止执行 WASM
- 5 tick 后自动恢复原 owner

**疑问**：
- Neutral drone 是否仍占该玩家的 `MAX_DRONES_PER_PLAYER` 槽位？是否仍占房间 cap？
- Tower 自动攻击是否攻击 Neutral drone？（如果不攻击 → Hack 是临时撤离敌方力量；如果攻击 → 5 tick 内可能被己方 Tower 误伤）
- Neutral drone 能否被 RangedAttack 攻击？被 Heal？被 Disrupt？被再次 Hack？（spec 说"恢复前免疫再次 Hack"，但其他动作呢？）
- Neutral drone 携带的资源是否仍属于原 owner？被 Drain？

**修复方向**：在 specs/02 §3.10 补一张表：

| 动作 | Neutral drone 是否可被作用 |
|------|--------------------------|
| Attack/RangedAttack | ✅ 可，按 hostile 处理 |
| Heal | ❌ 不可（无 owner 即非 ally） |
| Hack | ❌ 免疫（spec 已写） |
| Disrupt | ✅ 可——可加速恢复（设计选择） |
| Drain | ❌ Neutral drone 携带资源属于原 owner，Drain 不工作 |
| 占用 cap | ✅ 仍占原 owner 的 player cap 与 room cap |

---

### G10: Drain 与 Carry 容量交互的边界 case

**问题**：specs/02 §3.11：
> "效果: 从目标建筑/存储中窃取资源，每 tick 转移 carry_capacity 单位"

**疑问**：
1. 若 drone 已携带其他资源（如 Energy），Drain Crystal 时按"剩余 carry"还是"总 carry_capacity"？
2. 若 carry_capacity = 200，目标剩 50 Crystal——是窃取 50 还是失败？
3. 持续型 Drain，drone carry 满了后是中断还是停留？
4. Drone 移动是否打断 Drain？（spec 说"移动或被 Disrupt 时中断"）—— 那 drone 一边 Drain 一边由其他 drone 抢运 carry 内容算不算"移动"？Transfer 给其他 drone 是？

**修复方向**：specs/02 §3.11 加 4 行说明，或干脆把 Drain 改为"瞬时单次窃取 carry_capacity 单位，不持续"——这样消除整个状态机。后者更简单，但失去"持续物流压制"的玩法味道。

---

### G11: Recycle 50% 退还 vs Tutorial 100% 退还的边界

**问题**：DESIGN §8.2：
> "标准世界回收退还 50%。Tutorial 世界前 500 tick 回收退还 100%。"

specs/02 §3.9 校验只提了"返还 50%"，没提分支。

**疑问**：
- 500 tick 后突然变 50% 是硬切换？玩家在 tick 499 提交、tick 501 执行 → 退多少？
- 是否针对 spawn 后立即 recycle 的"白嫖"做防护？比如同 tick spawn + recycle 算不算 100%？

**修复方向**：specs/02 §3.9 加分支：
```
if world.mode == "tutorial" && tick < 500:
    refund_pct = 100
else:
    refund_pct = 50
```
+ 拒绝同 tick spawn 后立即 recycle（`spawn_cooldown` 同时作 recycle gating）。

---

### G12: Arena 平局判定循环

**问题**：DESIGN §9.1.3：
> "终止条件: 一方 drone=0 > 一方认输 > tick 到上限按剩余资产判定（drone数→建筑数→资源量）> 平局"

**疑问**：
- "平局"具体怎么发生？三层判定都相等才平局？这在房间制（map_seed 确定，初始资源对称）下**几乎必然发生**——双方完全镜像策略 = 全程对称
- Arena 默认 5000 tick——双方都不主动进攻是合法策略吗？turtle 战术是否被允许？
- 旁观体验：如果 5000 tick 都没打就平局，回放观赏价值为 0

**修复方向**：
1. Arena 引入"侵略性指标"：tick 达上限时 drone 数相同 → 看 PvP damage dealt 总量，少者负
2. 或：从 tick 4500 开始，地图缩圈（每 100 tick 边界向内 1 格 + 资源点产能 ×0.5），强制交战
3. 或：默认 Arena 启用 [[mods]] empire-upkeep 类型的"timer 维护费"，turtle 越久代价越大

---

### G13: 命令上限 500/tick 与 drone 数 500 的隐含约束

**问题**：
- specs/02 MAX_COMMANDS_PER_PLAYER = 500
- specs/07 max_drones_per_player = 500（默认）
- 一个 drone 通常需要 1-2 命令/tick（Move + Action 经常分开）

**后果**：
- 500 drone × 2 cmd/tick = 1000 commands → **直接超 cap**
- 玩家会被迫"每 drone 平均 ≤1 cmd/tick"——意味着不能同时移动 + 攻击

**修复方向**：选一：
1. 提高 MAX_COMMANDS_PER_PLAYER 到 1000 或 2000
2. Move + Action 合并为单 command（如 `{type: "MoveAttack", path, target}`）—— 但这增加 IDL 复杂度
3. 降低 MAX_DRONES_PER_PLAYER 到 250

**推荐**：1。命令 cap 的初衷是防 MCP 滥用，1000 仍然防住，且对正常玩家更宽松。

---

### G14: Source 抢占的"先到先得"在大量并发下的公平性

**问题**：DESIGN §3.2 Phase 2a 说命令按 `(shuffle_order, player_id, cmd_seq)` 串行 inline 应用，资源竞争先到先得。

**场景**：30 个 drone 同 tick 都 Harvest 同一个 Source（capacity=3000，每 tick 产 1）：
- 第一个 drone 拿 2 energy（假设 G4 修复后），第二个拿 2，... 第 1500 个 drone source 已空
- 实际上 Source 每 tick 只产 1 → 几乎所有 drone 都拿 0 或 1
- shuffle_order 决定谁吃肉谁喝汤——这是公平的，但**玩家无法知道自己排第几**

**潜在 exploit**：
- "提交 30 个 Harvest，期望命中 1-2 个" 与 "提交 1 个 Harvest，期望命中" 在 fuel 消耗上几乎一致（命令序列化便宜），但前者期望收益更高
- 玩家批量发送同样动作来对抗 shuffle 不利位置 → MCP/MAX_COMMANDS_PER_PLAYER 被刷爆

**修复方向**：
- 同 source 同 tick 同 drone 重复 Harvest 应去重（仅保留 sequence 最小的）
- 或：Harvest 收益按 `tick_production / harvesters_in_range` 分摊（合作模型，但削弱"先到先得"竞争）

第一种保留竞争味道，推荐。

---

### G15: 部署 cooldown 与 session_id 例外的语义模糊

**问题**：specs/02 §7.2：
> "若玩家在 tick N+1 执行了任何部署操作，tick N 及之前累计的 refund credit 清零。例外: 同一 session 内的迭代部署（同 session_id）不清除 credit"

**疑问**：
- session_id 由谁生成、生命周期多长？MCP session？WASM 部署 session？
- 玩家可以反复 deploy v1→v2→v1 在同 session 内规避清零？（虽然 R2 已加 update_cooldown=5，但还是想钻）
- 跨 MCP client（一个 AI agent + 一个手动 deploy）—— session_id 不同但同玩家，credit 被清，是否合理？

**修复方向**：
- 删除 session 例外，改为"每 N tick 内（如 100）的累计 deploy 次数 ≤ 5"（窗口式）
- 或：明确 session_id = OAuth2 access token + 部署时间窗口（30 min），写进 specs/03

---

## Missing

> 必须在编码前补齐的设计缺失。

| ID | 项 | 严重度 | 落点 |
|----|------|--------|------|
| M1 | Harvest rate（每 Work part 每 tick 采几） | 🔴 Blocker | specs/07 |
| M2 | Spawn cooldown 公式 | 🔴 Blocker | specs/02 §3.8 + DESIGN §3.1 |
| M3 | Tower 充能机制（或删除） | ⚠️ High | DESIGN §8.2 |
| M4 | age_max 下限 + Spawn 校验 | 🔴 Blocker | specs/02 §3.8 |
| M5 | Controller 维修硬上限的精确语义 | 🔴 Blocker | specs/07 + DESIGN §3.1 |
| M6 | Fortify per-target cooldown 或净化分级 | 🔴 Blocker | specs/02 §3.15 |
| M7 | Neutral drone 状态下各动作的可用性矩阵 | ⚠️ High | specs/02 §3.10 |
| M8 | Harvest 同源去重规则 | ⚠️ High | specs/02 §3.2 |
| M9 | Vanilla 分层各 tier 启用的特殊攻击列表 | ⚠️ High | specs/07 |
| M10 | MAX_COMMANDS_PER_PLAYER 与 MAX_DRONES 的约束关系 | ⚠️ High | specs/02 §6 |
| M11 | Arena 平局回退（缩圈 / 资产倾向） | 🟡 Medium | DESIGN §9.1.3 |
| M12 | session_id 定义 + refund credit 范围 | 🟡 Medium | specs/02 §7.2 + specs/03 |
| M13 | Drain 持续状态机的边界（Carry 满 / 移动定义） | 🟡 Medium | specs/02 §3.11 |
| M14 | Tutorial Recycle 100% 的边界 tick 处理 | 🟢 Low | specs/02 §3.9 |
| M15 | 累进税系数重新校准（×10 或非线性） | 🟡 Medium | DESIGN §8.2 |

---

## Balance Risks

> 短期看上去可玩、长期 meta 演化后可能失衡的隐患。MVP 后需观察。

### BR1: Tough 50 part 超级肉盾

**数学**：
- 50 Tough × 10 Energy/part = 500 Energy spawn 成本（极便宜）
- HP = 50 × 100 = 5000（接近 RCL 8 Tower 满血）
- Lifespan = 1500 + 50 × 100 = **6500 tick**（超长寿）
- age_modifier 总和 +5000，远超平均

**问题**：
- 这种 drone 没有任何主动能力（无 Move 走不动、无 Attack 打不了），但作为"挡子弹"在 chokepoint 几乎无解
- 配合 Fortify 永动护盾（G1）→ 永久不死、永久免疫负面状态、堵在敌方 Spawn 出口

**短期不严重**（无 Move 不能堵敌方门口）但**Tutorial→Standard 玩家发现这个 cheese 后会引发 nerf 呼声**。需要观察。

**潜在缓解**：限制单 drone 最大 Tough part 数（如 ≤ 20）；或者 lifespan 公式改为 `min(LIFESPAN_CAP, BASE + sum)`，cap 设 5000。

---

### BR2: Overload 长期消耗战

按 R2 后 spec：Overload 全局冷却 50 tick，下限 MAX_FUEL × 0.2。

**最优攻击模式**：
- 1 个 RangedAttack drone 每 50 tick 打一次 Overload（300 Energy）→ 永久把目标压在 fuel ≤ 20% 上限
- 防守方需要 Fortify 净化或避免可见——但如果防守方 drone 数多于 attacker 视野，Fortify 维护昂贵
- 攻击方只需 6 Energy/tick × 50 tick = 300 Energy 即维持永久压制

**Meta 演化预测**：
- 中期玩家会建专门的"哨兵 drone"——RangedAttack body 蹲点 Overload 高价值目标（敌方主帅 drone）
- 防守方被迫所有重要 drone 都配 1 个 Tough（Fortify 资格）—— 推高所有 body 成本

**这是 R2 后已经有意识地通过"全局冷却 50 tick + 静默结果"缓解**，但仍可能成为"Camping meta"。需要 MVP 后观察。

---

### BR3: Forward Depot 黑产链——前线烧资源换永久 drone

**机制**：
- Depot maintenance = 10 Energy/tick，repair_aging = 5
- 即每 10 Energy 换 1 个 drone 减 5 age = **2 Energy/age 折算**
- Active drone aging = 1.1/tick → 维持需 2.2 Energy/tick/drone
- 1500 lifespan 的 drone "永生"成本 = 2.2 × 1500 = 3300 Energy

而原本一个 5-part drone（如 Move×2 + Work×2 + Carry×1）的 spawn 成本 = 50+50+100+100+50 = 350 Energy。

**结论**：花 3300 Energy 让一个 350 Energy 的 drone 永生 = **不划算**。除非 drone 是高价值（30+ parts）。

**例外**：50-part 战斗 drone（成本 5000+ Energy） + 永生（3300 Energy） = 8300 → 比 spawn 三只（15000）省。**这是设计有意为之**（高价值单位有维护意义），不是 exploit。

**风险**：如果 G2 修复后 Controller 维修真的有意义，则 Forward Depot 在敌方领地建立的"飞地永生区"成为攻防核心。这是好的设计风险——但需要 specs/02 加上 Depot 被 Drain 的特殊处理（敌方占领后，Depot 内资源算谁的？）。

---

### BR4: Rhai 模组的"信任放大"链

**问题**：DESIGN §8.7 + specs/07 §5.1：
- 模组分发 = git clone + Ed25519 签名
- "信任的公钥列表"由服主配置

**演化**：
- 流行模组（如 empire-upkeep）的作者公钥被大量服主信任 → 该公钥的私钥泄露 = 大规模回放篡改
- "信任"传递无机制（A 信任 B，B 加新公钥 C —— A 不自动信任 C）—— 短期安全，长期生态建设缓慢

**这是 Security review 的范畴**（rev-claude-security 应详查），但从游戏设计角度提一句：模组信任难度高 → 模组生态弱 → 世界规则单一化 → meta 趋同。需要在 MVP 后观察。

---

### BR5: World 模式无排行榜的留存风险

**问题**：DESIGN §8.2 / Vanilla 默认值表：
> "World 模式无排行榜，Arena 模式有排行榜"

**长期 meta**：
- 持久 World 没有"成就"（只有 GCL/房间数/drone 数等"展示性指标"）
- 玩家发展到一定规模后**没有目标**——Screeps 当年正是因此流失大量玩家
- Arena 有排行榜但是限时房间制 → 重赛季感弱

**缓解建议**：
- World 加入"事件性目标"——每月一次的世界事件（小行星陨落带来稀有资源点 / boss 入侵），玩家协作 + 竞争
- 或：World 每年一次"snapshot ranking"，所有玩家在某一 tick 的快照对比，有官方记录但不持续

这是远期设计议题，不是 R3 blocker。

---

## 评审摘要

| 类别 | 数量 |
|------|------|
| Strengths | 6 |
| Concerns - Blocker (G1, G2, G3, G5) | 4 |
| Concerns - High (G4, G6, G7, G8, G13, G14) | 6 |
| Concerns - Medium (G9-G12, G15) | 5 |
| Missing - Blocker | 6 |
| Missing - High | 5 |
| Missing - Medium/Low | 4 |
| Balance Risks | 5 |

**Blocker 总数：10（4 Concerns + 6 Missing）**——必须在编码前补齐 specs。其余可在 MVP 实现并观察 meta 后迭代。

**最关键的 3 件事**（按影响力排序）：
1. **修复 Fortify 永动护盾**（G1 + M6）—— 不修复则 Standard 模式所有持续型攻击废掉
2. **明确 Controller 维修硬上限语义**（G2 + M5）—— 不明确则 active aging + lifespan 整套机制无法实现
3. **补齐 Harvest rate / Spawn cooldown / age_max 下限**（M1 + M2 + M4）—— 任一缺失都让设计无法进入实现阶段

---

> rev-claude-designer · R3 · 2026-06-16
