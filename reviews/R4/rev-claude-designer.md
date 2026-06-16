# R4 Clean-Slate Review — Game Designer 视角 (rev-claude-designer)

**评审员**: rev-claude-designer (Claude Opus 4.7, 游戏设计师视角)
**评审日期**: 2026-06-16
**评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + 9 specs
**视角**: 游戏机制 / 平衡性 / 玩家体验 / 策略深度 / 可玩性

---

## Verdict

**CONDITIONAL_APPROVE**

R4 在游戏机制设计上比 R3 有明显进步——Vanilla 分层（Tutorial/Novice/Standard/Advanced）解决了我在 R3 提出的"新人即被特殊攻击淹没"问题；Arena 房间制取代天梯让"算法对抗"哲学落地；Controller+Depot 共享 RepairTracker 的硬上限设计让"永动 drone 漏洞"被严密堵死。

但仍有 **3 个 Critical / 5 个 High / 7 个 Medium / 4 个 Low** 的设计问题未解决。其中 Critical 集中在三处：(C1) 新生 drone 同 tick 即可被攻击 = "出生即斩"漏洞；(C2) Overload 的恢复速率与全局冷却完美匹配，多攻击者协同可造成永久 fuel 锁死；(C3) Recycle 50% 退还在 lifespan 末期被滥用，绕过"老化死亡"的核心约束。这些必须在编码前修复——一旦实现，meta 会立即向利用这些漏洞的策略坍缩。

设计哲学（Code is Army、Federation Universe、World/Arena 双形态）整体自洽且令人兴奋；但配置数值（特别是冷却/伤害/资源消耗）尚未通过任何模拟验证，存在多处显式失衡。建议**修复 Critical 项 + 补齐数值平衡矩阵**后进入实现。

---

## Strengths（亮点）

### S1. Vanilla 分层模型解决了 R3 主要痛点
Tutorial/Novice 默认禁用全部 8 种特殊攻击，Standard+ 才开放——新玩家不会在不理解 Hack/Overload 机制的情况下被夺取。这是优秀的渐进式引导设计。

### S2. Controller + Depot 共享 RepairTracker 的硬上限
"无论拥有多少 Controller，每 tick 总 age 回退 ≤ 自然增长 50%"——这条规则单独把"永动 drone 经济"漏洞堵死。维修距离随 RCL 增长（1→5 格）+ 每 tick 服务上限（5→80 drone）形成自然的物流瓶颈。这是 R3 G1 系列 Blocker 的优雅终局。

### S3. Fortify 的"净化 + 护盾"复合设计
Fortify 同时清除负面状态 + 提供 100 tick 50% 抗性，且不可刷新（per-target 300 tick 冷却）。这创造了"攻防节奏":
- 攻击方花 3 tick 叠加 Debilitate/Drain/Hack
- 防守方 1 个 Fortify 全部清除
- 但 Fortify 用完后 200 tick 无敌真空期
这是一个有"挪劲"的对抗系统，而非数值堆砌。

### S4. Body Part age_modifier 让 build 设计有取舍
Tough +100、Attack -80、RangedAttack -50、Heal -30、Claim -50——攻击型 drone 短命，肉盾长寿。配合 Recycle 50% 返还，玩家被推向"短期突击 + 长期防御"的复合 build，单一 ATTACK 流被天然惩罚。

### S5. Arena 房间制 + 自我对抗
"同一玩家可占多槽位部署不同算法自我对抗"——这是非常好的设计哲学落地。AI agent 训练循环（提交 v1 vs v2，迭代）和人类调试（A/B 测试策略）走同一接口。

### S6. 全局存储累进税 + 转换时延
30%/60%/85% 三段累进 + 5/10 tick 转换时延——既防止富有玩家无限囤积，又保留"战略储备"的价值。`transfer_to_global_time ≥ 1`（不可为 0）是关键设计——禁止瞬移补给在战斗中即时翻盘。

### S7. 视野与玩家屏幕分离
`fog_of_war` 控制 drone snapshot（公平性），`player_view` 控制玩家观看体验——这个解耦避免了"教学世界 player 看全图但 drone 也透视"的逻辑冲突。

### S8. SDK Manifest Hash 防错部署
`module.target_manifest_hash == world.current_manifest_hash` 编译期检查——防止玩家用 World A 的 SDK 编译的 WASM 部署到 World B 后产生 silent 行为偏差。这个细节在跨世界 modding 场景至关重要。

---

## Concerns

### G1 [Critical] 新生 drone 同 tick 即被攻击 = "出生即斩"漏洞

**位置**: DESIGN.md L393, specs/02 §3.8 L268

**问题**:
> Spawn 时序说明: spawn_system 在 death_mark 之后、combat/decay 之前运行。新 spawn 的 drone **在同 tick 参与 combat**——可能出生即被攻击或受衰减影响。**此行为是有意设计**。

这个"有意设计"创造了灾难性的策略漏洞:

```
对手在我方 Spawn 旁部署 1 RangedAttack drone (range 3)
  ├─ 我方 Spawn drone (cost 200 Energy + body cost)
  ├─ 同 tick 被 RangedAttack 25 dmg/part × N parts
  └─ 5-part 攻击 drone (125 dmg) 直接秒杀新生 100 hits drone

结果：每 5 tick 我方 Spawn 200+ Energy 但获得 0 drone 净增长。
```

**为什么这是 Critical 级**:
1. 没有任何 spawn protection（不像 §3.1a "首次 spawn safe_mode 500 tick" 是房间级，不是 drone 级）
2. Spawn body 已经在 Phase 2a 校验，没有"新生 drone hits = body × 100"的默认护盾
3. 攻击方 RangedAttack drone 不需要进入对方房间——3 格 range + 出口位置确定 = 边境防御网
4. Heal drone 救援也救不回——在同 tick combat_system 末尾才结算 heal

**修复建议**:
- **方案 A（推荐）**: 新生 drone 获得 `SpawningGrace { remaining: 1 tick }`，本 tick 免疫所有伤害（含特殊攻击）。下一 tick 才可被攻击。
- **方案 B**: 把 spawn_system 移到 combat_system 之后，新生 drone 在创建当 tick 完全不参与战斗。但这会延迟"即时反应"——存疑。
- **方案 C（最弱）**: 新生 drone 获得 5 tick 的 50% 抗性。仍可被秒，仅减缓。

我推荐方案 A——简单、确定、与 §3.1a "首次 spawn safe_mode" 哲学一致。

**严重性原因**: 这条规则会立刻让 meta 坍缩为"边境 RangedAttack 巡逻 = 阻止对方扩张" 的单一策略。被打的玩家无解。

---

### G2 [Critical] Overload 恢复速率 = 全局冷却倒数 → 永久 fuel 锁死

**位置**: specs/02 §3.12 L348-360

**问题**:
- Overload 削减 500k fuel
- 恢复 `fuel_budget / 1000` per tick = 10M / 1000 = 10k/tick
- 完全恢复需 50 tick
- **全局冷却 = 50 tick**

数学上：单个攻击者每 50 tick 触发一次 Overload，目标恰好恢复完毕，立即再被打。

更糟：**全局冷却是 per-target 不是 per-attacker**——n 个攻击者轮流 Overload 不受限。但 spec 写"同一目标过去 50 tick 内被 Overload"——读起来似乎是 per-target，但语义是"任何攻击者"。让我重新读...

> 全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限来源）

OK，这是 per-target 全局——那么单点压制确实有上限。但仍然是恢复期 = 冷却期，目标永远在 fuel 地板（MAX_FUEL × 0.2 = 2M）附近徘徊。

**为什么这是 Critical**:
1. 2M fuel/tick 对复杂策略（多 drone、寻路、市场决策）严重不足
2. 攻击者只需 1 个 RangedAttack drone + 300 Energy/200 tick = 几乎免费
3. 防守方需要找到攻击者并 Disrupt/Fortify——但 Overload 是远程，攻击者可以躲在己方房间
4. **Fortify 净化** 是唯一解药，但 Fortify 自身 300 tick 冷却 > Overload 200 tick 冷却

**修复建议（任选）**:
- **方案 A**: 恢复速率 ×2（fuel_budget / 500 = 20k/tick，25 tick 恢复完）。给目标 25 tick 的"完整算力窗口"。
- **方案 B**: 全局冷却 100 tick（不变恢复速率，留 50 tick 完整算力期）。
- **方案 C**: 引入"被压制疲劳"——同一目标连续 3 次被 Overload（150 tick 内）→ 第 4 次开始衰减效果（500k × 0.7^n）。

我推荐方案 B——简单且不破坏其他平衡。

**额外问题**: spec 没说明 Overload 是否触发"被攻击通知"。被压制玩家应该知道自己在被 Overload（否则只看到 fuel 不够，无法定位攻击者）。

---

### G3 [Critical] Recycle 在 lifespan 末期被滥用，绕过老化死亡

**位置**: DESIGN.md L683, specs/02 §3.9

**问题**:
- Drone 自然衰老死亡 → body parts 损失 100%（无返还）
- Drone 在 lifespan 还剩 1 tick 时 Recycle → 返还 50% body parts cost

**结论**: **每个 drone 在死前都应该 Recycle**。这意味着:
1. "drone 自然衰老死亡"事件在最优策略下永远不发生
2. Body part age_modifier 的"减寿"惩罚被部分对消（Attack drone -80 lifespan，但能 50% 返还，等价于"折寿但有遗产")
3. 配合 Forward Depot 把 drone 拖到老 → 远征 drone 的"折寿"机制被弱化

**Meta 演化预测**: 玩家必然在 lifespan 还剩 50-100 tick 时统一 Recycle，这创造了 "Recycle 周期"——每 100 tick 全员回收 + spawn——增加经济波动但不创造策略深度。

**修复建议**:
- **方案 A（推荐）**: Recycle 退还比例与 drone age 挂钩。`refund = body_cost × max(0.1, 0.5 × (1 - age / lifespan))`
  - 新 drone（age=0）→ 50% 退
  - 半寿 drone → 25% 退
  - 末期 drone → 10% 退（仅比 0% 略好，避免"必须 Recycle"）
- **方案 B**: Recycle 强制冷却 200 tick——不能在死前疯狂 Recycle 整支军队。
- **方案 C**: 老化死亡也返还 25% body parts——让"自然死亡 + Recycle"差距缩小。

我推荐方案 A，这让 Recycle 成为"回收无用 build" 的工具，而不是"延寿"的工具。

---

### G4 [High] Drain 经济失衡 — 1 个 drone 偷光对手仓库

**位置**: specs/02 §3.11

**数学**:
- Drain 冷却 50 tick / drone
- 每 tick 转移 `carry_capacity` 单位 = parts × 50
- 50-part Carry drone (max body) → 2500 单位/tick
- 持续 50 tick 不被 Disrupt → 125,000 单位
- Storage 容量 1,000,000——单次 Drain 偷掉 12.5%
- 200 Energy/tick × 50 = 10,000 Energy 成本

**问题**: 50,000 Crystal/Matter 价值 ≫ 10,000 Energy 成本，**ROI 5×+**。

**Disrupt 反制**: 50 tick 冷却，且 Disrupt 也需要近距离（range 1）+ Attack body part。

**建议**:
- 加 **Drain efficiency decay**: 每 5 tick 不离开目标，效率衰减 20%（5 tick 100%→ 25 tick 0%）
- 或限制单次 Drain 总量上限：`max_drain_per_session = carry_capacity × 5 = 一次最多偷 5 tick 的量`，强制中断

---

### G5 [High] 单 Spawn building 速率瓶颈 → 大军必须散开

**位置**: DESIGN.md §3.1 / specs/01

**数学**:
- Spawn cooldown 5 tick
- MAX_DRONES_PER_PLAYER 500
- 单 Spawn 每 5 tick 出 1 个 → 500 drone 需 2500 tick (~125 分钟 = 2 小时)
- 每个房间最多 1 个 Spawn 槽位
- → 必须占领 5+ 房间才能在合理时间内组建满员军队

**问题**: 这强制玩家走"先扩张后军队"，但扩张又依赖 Claim drone（需 Claim body part，单价 600 Energy + 折寿 50）。早期资源紧张时玩家会卡在"出不了 Claim drone → 无法扩张 → 无法多 Spawn → 出兵慢"循环。

**建议**:
- 验证 Spawn cooldown 5 tick 是否合理——可能需要降到 2-3 tick，或允许 RCL 升级减少 cooldown
- 提供数值模拟数据：单房间从 RCL 1 → RCL 4 (300 drone cap) 的最优时间路径，在默认参数下需要多久

---

### G6 [High] Active aging 反直觉 — 越努力越早死

**位置**: DESIGN.md §8.2 "Drone 生命周期"

> idle_aging 100% / active_aging 110%（每 tick 执行命令的 drone 以 110% 速率衰老）

**问题**: 这是为了防"挂机囤兵"，但让玩家陷入两难:
- 让 drone 工作 → 早死 10%
- 让 drone 待机 → 资源浪费

**Meta 演化预测**: 玩家会写"按需启动"的 drone——平时 idle，关键时刻爆发。这违反"代码就是军队，常驻服务"的哲学。

**实际影响**:
- 1500 tick lifespan
- 100% active：1500 tick / 1.1 ≈ 1364 tick 实际寿命
- 损失 ~9% 寿命

**建议**:
- **方案 A**: 移除 active_aging 惩罚，用 fuel budget 限制挂机价值（idle drone 不消耗 fuel 但也不获得 fuel refund credit）
- **方案 B**: 反转——idle drone 衰老 110%，active drone 100%。鼓励"使用即合理"的设计。
- **方案 C**: 保留但降幅减小到 +2%（1500 → 1471 tick，仅 -29 tick）

---

### G7 [High] Hack 5+5 锁定窗口 = 关键单位即时净化

**位置**: DESIGN.md L1217 / specs/02 §3.10

**机制回顾**:
- Hack 施加 5 tick 控制锁（tick 1-2 减速 50%, tick 3-4 不动, tick 5 转 Neutral）
- Neutral 持续 5 tick 后恢复
- 总锁定时间: **10 tick**

**漏洞**: 对方 Healer drone (12 HP/tick) 一次 Hack → 10 tick 不工作 → 我方在这 10 tick 完成攻击。Heal 是"持续治疗"型，断 10 tick = 战斗逆转。

更糟：**Hack 仅 200 tick 全局冷却**——同一 Healer 每 200 tick 锁 10 tick = 5% 时间无效。考虑到 Healer 是高价 drone (250+ Energy 单 part × 多 part)，这个伤害不对称。

**建议**:
- Hack 冷却升至 400 tick (per-target 全局冷却)
- 或 Hack 5 tick 控制锁后立即恢复（无 5 tick Neutral 期），减少总锁定为 5 tick

---

### G8 [High] Fabricate 经济性碾压 - 偷 drone + 出建筑双重收益

**位置**: DESIGN.md L1224 / specs/02 §3.11+

**机制**:
- Fabricate 消耗 2000 Energy + 500 Matter
- 把敌方 drone 转化为己方建筑

**经济**:
- 敌方 50-part drone 价值 ≈ 5,000-10,000 Energy（视 build）
- 转化获得 1 个 Extension 类建筑（建造价 50 Energy）
- 净价值: 我方 -2,500 Energy + 损毁敌方 5,000-10,000 + 建筑 = **+5,000 净收益**

500 tick 冷却看起来是约束，但这是**单 drone 冷却**——多 Fabricate drone 可以并行。

**建议**:
- Fabricate 转化产出的建筑应该是"低 hits 临时建筑"（如 200 hits, 100 tick 后自毁），不是永久建筑
- 或要求目标 drone hits < 50%，不能 Fabricate 满血单位

---

### G9 [Medium] World 模式无排行榜 → 缺乏长期驱动力

**位置**: DESIGN.md L1028 + ROADMAP

> 排行榜：World 模式无排行榜，Arena 模式有排行榜

**理由**（spec 中）: "持久世界天然不公平（老玩家先发优势）"——同意。

**问题**: 但完全无排名意味着 World 模式的长期玩家**没有进度反馈**。Screeps 的成功部分依赖 GCL（Global Control Level）和"看着自己殖民地变大"的成就感。

**建议**:
- World 模式提供"个人里程碑"展示（非全局排名）：殖民地年龄、最大 GCL、最长存活 drone、累计资源采集量
- 或"季度快照排行"：每 4 周冻结当前状态形成历史排行（避免老玩家永久压顶但保留竞争）

---

### G10 [Medium] Tower 数值在早期可能无效

**位置**: DESIGN.md §8.2 "[[structure_types]] Tower"

**数值**:
- damage 50, range 5, cooldown 10
- 200 Energy 建造，RCL 3 解锁

**问题**: Tough drone 每 part 100 hits，5-part = 500 hits，10 tick × 50 dmg = 500 dmg。**Tower 单 cooldown 周期才秒一个 5-Tough drone**。

进攻方 5 个 5-Tough drone（成本 5 × (5×10 Energy) = 250 Energy）→ Tower 需要 50 tick 全部消灭，期间 Tough 队伍可以向 Tower 推进 + 携带的 Attack drone 拆 Tower。

**建议**:
- 验证 Tower vs 各种 drone build 的实战曲线
- 考虑 Tower 衰减伤害公式（距离越近伤害越高），让贴脸 Tough 不能轻松吞 Tower

---

### G11 [Medium] PRNG seed 自动轮换破坏长跑策略

**位置**: tech-choices.md §8 / DESIGN.md §8.8

> 每 10,000 tick 自动轮换（Blake3(旧种子, 当前 tick)）

**问题**: 玩家代码可能依赖 PRNG 序列做策略（如"每 100 tick 改变巡逻路线"），seed 突变 = 行为突变。10,000 tick ≈ 8 小时，对长时间运行的 bot 造成不可预测的逻辑偏差。

**更糟**: spec 没说"轮换通知"——玩家代码不知道何时轮换，只能轮询 `tick % 10000 == 0`。

**建议**:
- 在 snapshot 中暴露 `current_seed_epoch: u32`，玩家代码通过比较检测轮换
- 或提前 100 tick 通过 snapshot 通知"即将轮换"

---

### G12 [Medium] AI 玩家 deploy 频率优势

**位置**: specs/09 §2.2 "MCP_Deploy 10/h"

**问题**: AI agent 可以每小时 10 次部署，全自动迭代——人类玩家手工编译/调试一次需要 5-30 分钟。**AI 玩家在策略迭代速度上有 5-50× 优势**。

虽然 spec 说"AI 和人类同走 WASM 沙箱，公平"——这只在"代码执行公平"层面正确，但**策略迭代速度**才是 Screeps 类游戏的胜负手。

**建议**:
- 设计角度：明确接受这个不对称（"AI 联盟和人类联盟形成自然分化"）。
- 或在排行榜分组（League: Human / AI / Hybrid），让人类不直接和 AI 在同一榜单竞争。

---

### G13 [Medium] Tutorial 到 Standard 跳跃过大

**位置**: DESIGN.md L1024

> Tutorial/Novice 默认禁用全部 8 种特殊攻击。Standard+ 全部可用

**问题**: 玩家从 Novice 升级到 Standard 时，**8 种特殊攻击全部解锁**——学习曲线悬崖。

**建议**: 三段式渐进:
- Tutorial → 0 个特殊攻击
- Novice → 0 个
- **Intermediate** → Hack/Drain/Disrupt（基础 3 个）
- Standard → +Overload/Debilitate/Fortify（防守 3 个）
- Advanced → +Leech/Fabricate（高级 2 个）

新增一个 Intermediate 层级让玩家逐步适应特殊攻击的存在。

---

### G14 [Medium] 多攻击同 tick 命中的优先级未定义

**问题**: 假设我方 drone A 同 tick 收到:
- 玩家 X 的 Attack (Kinetic 30)
- 玩家 Y 的 Debilitate (Thermal ×2)
- 玩家 Z 的 Hack (Claim, 控制锁 stage 1)
- 玩家 W 的 Fortify (友方 +50% 抗性)

执行顺序如何？特别是 Fortify 应该在所有伤害**之前**生效（净化清除 Hack 控制锁吗？还是只清除已存在的？）。

**spec 缺失**: 没有"同 tick 多源效果优先级矩阵"。

**建议**:
- 文档化"buff 先于 debuff，治疗后于伤害"或类似规则
- 添加测试用例覆盖典型多源场景

---

### G15 [Medium] Arena 房间制 — 自我对抗和排行榜的关系不清

**位置**: DESIGN.md §9.1.1

> 同一玩家可占多槽位部署不同算法自我对抗

**问题**: 自我对抗的胜负计入排行榜吗？

- 计入 → 可以"刷胜场"（赢的总是自己）
- 不计入 → 如何区分"邀请朋友 vs 自我对抗"？（朋友也可能是自己的小号）

**建议**:
- 排行榜区分：算法独立 ID（每个 WASM hash 独立排名），而非玩家 ID
- 或要求"非自我对抗"才计入排行榜（通过账号验证）

---

### G16 [Medium] 缺乏紧急停机机制 / Manual Override

**位置**: DESIGN.md L661

> 手动控制不开放：manual_control 与"代码就是军队"的核心哲学冲突

**问题**: "代码就是军队"哲学下，bot 失控/能源耗尽时**玩家无救援手段**。

**实际场景**:
- 部署了 v2 代码 bug，drone 集体涌向资源点然后冻结
- Drone 在敌方房间被围攻，但代码没写撤退逻辑
- 全局存储被税收吸光，drone 即将集体死亡

**建议**:
- 提供 "Panic Button" MCP 工具：`swarm_panic_freeze` 高额代价（如冻结 1000 tick fuel budget）冻结所有自己的 drone 100 tick，给玩家修代码时间
- 这不破坏"代码就是军队"哲学——这是"重启服务器"的等价操作

---

### G17 [Low] DEFAULT_DRONE_LIFESPAN 数值未经模拟验证

**位置**: DESIGN.md L184

> const DEFAULT_DRONE_LIFESPAN: u32 = 1500;

**问题**: 1500 tick = 75 分钟（3s tick），这是 spec 提供的唯一时间尺度参考。但没有模拟数据：
- 平均 drone 在死前完成多少有效工作？
- 一个采集 drone 的"投资回报期"是多少 tick？
- Spawn cost 在 lifespan 内能采回几次？

**建议**: 在 spec 中加一节"基础数值平衡矩阵"，至少给出 5-10 个模拟场景的数值预期（如"1 个 5-Work 5-Carry 5-Move drone 在 1500 tick 内采集约 5000 Energy"）。

---

### G18 [Low] Market 数据被滥用 — 价格欺诈

**位置**: DESIGN.md L909-913

**问题**: 市场订单对所有可见房间玩家可见。富有玩家可挂"假装高价"订单（不打算卖）误导新玩家以高价收购。

**建议**:
- 订单创建时收取 1% 押金，撤单返还 95%（5% 罚金）
- 或限制每玩家活跃订单数（如 10 个）

---

### G19 [Low] Drone 占据同格规则未文档化

**位置**: spec 全文搜索"collision"/"同格"——未找到明确规则

**问题**: 多个 drone 是否可同格？同盟 vs 敌方？Spec 模糊。

- 移动校验中有 `TileBlocked` (specs/02 §3.1)——意味着"占据"是排他的
- 但 Spawn 出生时新 drone 在 spawn 格——是否冲突已有 drone？

**建议**: 明确"每格至多 1 个 drone"或允许同盟共格，并补充 spec。

---

### G20 [Low] 跨房间移动疲劳累积未验证

**位置**: DESIGN.md L314

> 跨房间移动成本 = 房间内路径 cost + 穿越出口 cost（默认 +1 fatigue）

**问题**: 50×50 房间穿越需 50 步移动，每步累积 fatigue（依赖 Move part 数）。从 (-2, 0) 远征到 (2, 0) 跨 4 房间 = 200 步 + 4 个出口 = 204 fatigue。
- 1-Move drone fatigue 上限受限——多少 fatigue 后被迫休息？
- spec 没说 fatigue 上限

**建议**: 文档化 fatigue 累积上限和恢复速率，否则玩家无法计算远征 drone 的 Move part 需求。

---

## Missing（缺失/未明确）

### M1. 特殊攻击同时命中的优先级矩阵
（见 G14）。需要 spec 表格定义。

### M2. Spawn 同房间多个排队规则
当 1 个 Spawn 在 cooldown，另一 Spawn 可用，玩家代码如何选择？是否有"自动负载均衡"？

### M3. 资源类型衰减（decay_rate）的全局影响
spec 提到 Matter `decay_rate = 0.001`——每 tick 衰减 0.01% = 1500 tick 衰减 ~14%。但没说明：
- 衰减应用到全局存储还是本地？
- 衰减是否影响"运输中"状态？
- 玩家如何观察衰减率？

### M4. Replay 隐私的多人协作场景
Arena 双方对战赛后强制 `public`——但如果 4 人混战？某玩家不希望自己策略公开如何处理？

### M5. Tournament 系统设计
ROADMAP 提到 tournament 是 MVP 范围（specs/06），但 specs/06 没有 bracket / 赛季 / 报名机制——这一块完全缺失。

### M6. Modder 经济
模组通过 Rhai 提供，但 spec 没说"模组作者如何获得回报"。完全公益吗？这影响生态健康度。

### M7. 跨世界资产转移机制
DESIGN L34 提到"联邦宇宙 + 玩家可跨世界拥有身份和资产，通过异步方式交互（转移资源、共享排名）"。但 spec 中没有跨世界协议、汇率、转移成本的任何定义。这是 MVP 范围还是远期？

### M8. AI 玩家 prompt 注入防护
specs/02 §6 提到"玩家名 32 字符防 prompt 注入"——但 drone 的 env_vars 内容呢？玩家可以在 drone memory 写入伪装成 system prompt 的内容，期望 AI agent 在读取时被欺骗。

### M9. 经济崩盘的全局回退机制
当所有玩家集体破产（罕见但可能发生于经济模组配置失误），世界进入死锁状态。是否有 admin override 重置经济？

### M10. Drone 衰减系统在 PvE 世界的处理
`pvp_enabled = false` 时，玩家无对手——drone 寿命 + Recycle 浪费成为玩家唯一焦虑来源。是否禁用 lifespan 在 pure PvE 模式？

---

## Balance Risks（平衡风险）— Meta 演化预测

### 短期 meta（新世界 0-1000 tick）
- **优势策略**: 早期速攻 Spawn——RangedAttack 边境部署，秒杀对方 spawn drone（受 G1 影响）
- **反制**: 无（必须修 G1）

### 中期 meta（1000-10000 tick）
- **优势策略**: 多 Drain drone 联合偷袭高价值 Storage——单次攻击 ROI 5×（受 G4 影响）
- **反制**: Disrupt + Fortify 网络，但成本高

### 长期 meta（10000+ tick）
- **优势策略**:
  1. 大军 Recycle 战术——drone 90% 寿命时统一 Recycle + Spawn，规避自然死亡损失（受 G3 影响）
  2. Fabricate 转化奇袭——把对方主力 drone 转成自己建筑（受 G8 影响）
  3. Overload 永久压制——目标 fuel 永远被锁在 20%（受 G2 影响）

### 不健康 meta 倾向（必须警惕）
1. **"防御性瘫痪"**: Overload 太强 → 玩家不敢运行复杂代码 → 简化 bot → 游戏深度降低
2. **"Recycle 周期同步"**: 所有玩家在相似时间窗口大批量 Recycle/Spawn，世界经济 oscillate
3. **"AI 玩家流"**: AI 部署速度优势 → 人类放弃竞争 → 单一玩家群体的 meta

### 健康 meta 期望（设计目标）
1. **多种胜利路径并存**: 经济流（大基地）、突袭流（小精锐）、信息战（侦查+点杀）、模组定制流
2. **counter-meta 自然出现**: 当某 build 流行时，反制 build 经济上有利
3. **新玩家可达成短期目标**: 1 周内能看到自己殖民地从 1 房间 → 3 房间 → 5 房间

---

## 编码前必修清单（Critical/High blockers）

| ID | 问题 | 修复优先级 | 修复复杂度 |
|----|------|----------|----------|
| G1 | 新生 drone 同 tick 即可被攻击 | **必修** | 简单（添加 SpawningGrace 状态） |
| G2 | Overload 永久压制 | **必修** | 简单（调整冷却或恢复速率） |
| G3 | Recycle 末期滥用 | **必修** | 中（age-based refund 公式） |
| G4 | Drain 经济失衡 | 强烈建议 | 中（efficiency decay） |
| G5 | Spawn 速率瓶颈 | 建议 | 简单（数值调整） |
| G6 | Active aging 反直觉 | 建议 | 简单（移除或调整） |
| G7 | Hack 锁定窗口太长 | 建议 | 简单（数值） |
| G8 | Fabricate 收益过高 | 建议 | 中（产出建筑限制） |
| M1 | 特殊攻击优先级矩阵 | **必修** | 中（文档 + 测试） |

---

## 总结

**APPROVE 条件**:
1. 修复 G1/G2/G3 三个 Critical（必须，否则编码后 meta 立刻坍缩）
2. 补充 M1 特殊攻击优先级矩阵（必须，否则同 tick 多源效果行为未定义 = bug 温床）
3. 补充至少一份"基础数值平衡矩阵"（10-20 个典型场景的数值预期）
4. （强烈建议）解决 G4/G5/G6/G7/G8 中至少 3 项

**不修复以上的风险**:
- 实现后 1-2 周内 meta 收敛到"出生即斩 + Drain 偷袭 + Overload 锁死"的单一恶性循环
- 玩家流失率高（特别是新 Standard 升级玩家）
- Arena 比赛失去观赏性（一边倒）

**优秀之处保留**:
- Vanilla 分层、Controller+Depot 共享上限、Body age_modifier、SDK Manifest Hash 这些都是优秀设计，**不要因小修大改而破坏**

---

**评审员签名**: rev-claude-designer (Claude Opus 4.7)
**日期**: 2026-06-16
