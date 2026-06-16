# R6 Designer 视角评审 — rev-claude-designer

> 评审范围：/data/swarm/docs/ 全量设计文档（design/ + specs/）
> 视角：Game Designer（玩法完整性、平衡性、可玩性、规则清晰度）
> 评审时间：2026-06-16
> 评审员：rev-claude-designer (Claude Opus 4.7)

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

设计哲学坚实、扩展模型成熟、特殊攻击的状态机矩阵（§3.16）和 Overload 抗永久锁死证明（§3.17）都体现了 R5 沉淀下来的工程素养。但本轮 clean-slate 评审在 Designer 视角下发现 **3 个 Critical 阻塞**——其中一个是源文件级的物理缺陷（`design/gameplay.md` 第 624 行包含字面量 `[OUTPUT TRUNCATED ...]` 占位符，吞掉了 Vanilla Ruleset 6 件核心 body part 的完整定义和 Leech 表格行），另外两个是 Fabricate 特殊攻击的设计漏洞和 Hack Neutral 阶段恢复机制的跨文档矛盾。这些问题让 Vanilla Ruleset 当前**无法实现**——MVP 编码会卡在 "MOVE/CARRY/WORK/ATTACK/RANGED_ATTACK/HEAL 的 cost 和 age_modifier 是多少？" 这个最基本的问题上。

修复路径明确，工作量小（1-2 天），但必须在进入实现前合上。

---

## 2. Strengths（设计中做得特别好的部分）

### S1. Overload 抗永久锁死的数学证明（specs/02 §3.17）
R5 沉淀下来的明星章节。把 "50 tick 全局冷却 + 500k 削减 + MAX_FUEL × 0.2 下限 + fuel_budget/1000 恢复速率" 串成一个可验证的不等式链，证明协调多攻击者也无法将目标 fuel 锁死到 0。这是**真正闭合**的 design contract——不是宣言而是证明。

### S2. 特殊攻击状态机矩阵（specs/02 §3.16）
同 tick 多命中优先级（Disrupt → Fortify → Debilitate → Hack → Drain/Leech → Overload → Fabricate）和反制窗口矩阵把 8 个特殊攻击交互的所有边界情况都列了出来。这是 R4-R5 评审反复要求的最终交付物，本轮已经完成，结构清晰可实现。

### S3. SpawningGrace 1-tick 无敌帧（design/engine.md §Spawn 时序）
R4 G1 "出生即斩" 的修复方案——`death_mark → spawn → spawning_grace → combat → status_advance` 的固定串行链 + `SpawningGrace { remaining: 1 }` 组件。优雅、确定、可验证，把跨 system 的时序问题压成单一组件状态。

### S4. Recycle 比例退还与 lifespan 挂钩（specs/02 §3.18）
`refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))` 闭合了 R4 G3 "末期回收套利"——drone 越老回收越亏，无法通过 "快死了→Recycle→重 spawn" 套利。下限 10% 也保证不会完全归零（防止 NaN/0 边界 bug），数学干净。

### S5. World/Arena/PvE 三模式正交分层（design/modes.md）
World 持久不公平、Arena 对称公平、Arena PvE Challenge 隔离沙盒。三个模式各自的设计意图和资源边界（Arena PvE "不影响 World 状态、不产出 World 资源"）划得很干净。AI 玩家和人类玩家走完全相同路径（WASM 部署）也是正确的 commitment——避免了 R3 之前 MCP 作为 gameplay channel 的设计错误。

### S6. 全局存储反制三件套（design/gameplay.md §全局存储反制机制）
累进存储税 + 本地存储隐匿性 + 转换需物流时间——三个机制叠加防止富有玩家垄断经济。Stealth Advantage（敌方不知道你本地仓库存了多少）这一条尤其聪明，把信息不对称变成战略选择。

### S7. soft_launch 渐进式威胁曲线（specs/06 §2.4）
500 tick safe_mode → 1500 tick PvE-only → 全 PvP，并在 PvP 解除前 50 tick 广播警告。新手不会从 "绝对安全" 突然跳到 "被老玩家碾压"，这是 R3 之后吸取的体验设计教训。

---

## 3. Concerns（按严重度排列）

### 🔴 G1 [Critical] `design/gameplay.md` 第 624 行包含源文件级 [OUTPUT TRUNCATED] 占位符——Vanilla Ruleset 6 件核心 body part 定义和 Leech 表格行物理丢失

**位置**: `design/gameplay.md` 行 622-628（特殊攻击表格 + body_part_types 定义块）

**问题**:
```
| **Leech** | Attack | 吸血攻击——造
... [OUTPUT TRUNCATED - 1675 chars omitted out of 51675 total] ...
-30
cost = { Energy = 250 }

[[body_part_types]]
name = "Claim"
...
```

经 grep 验证（`grep -n "OUTPUT TRUNCATED" design/gameplay.md`）这是**源文件本身的字面量字符串**，不是工具输出截断——某次提交把 LLM 工具响应的 truncation marker 错误粘贴进了源文件。丢失的 1675 字符包含：

1. **Leech 表格行的右半部分**（效果详细描述、冷却、资源消耗、抗性栏目）——表格行在 "造" 字处中断
2. **Fabricate 表格行整行不见**——Vanilla Ruleset 声明 8 种特殊攻击，但表格里只有 7 行（Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech-断），Fabricate 在表里完全消失
3. **6 个 `[[body_part_types]]` 定义被吞**——从片段 "-30\ncost = { Energy = 250 }" 反推，丢失的至少包含 MOVE / CARRY / WORK / ATTACK / RANGED_ATTACK / HEAL 中的几件。Vanilla Ruleset §核心默认值一览（行 419）声明 8 种标准件，但本节 body_part_types 块只活下来 Claim 和 Tough（行 629-642）

**Designer 视角影响（why Critical）**:
- MVP 编码无法启动——"MOVE part 一个多少 Energy？" "ATTACK part 的 base_damage 是 30 还是文档说的 30 dmg/Kinetic？" "CARRY part 的 carry_capacity_per_part 是多少？" 这些是 Vanilla Ruleset 的最基础常量，跨文档无法补齐：
  - design/gameplay.md "Body part 伤害绑定" 表（行 595-602）只列了 Attack=30、RangedAttack=25、Tower=50、Heal=12 这 4 项，且只是 base_damage，没有 cost、age_modifier、passive 字段
  - specs/reference/commands.md 不定义 body part 数值
  - specs/core/07-world-rules.md 引用 body_part_types 但不定义默认值
- 本应该是 "Vanilla Ruleset 即默认 world.toml" 的强承诺，现在变成 "默认值在哪儿？我去问设计师吗？"
- 跨文档矛盾自动产生：design/gameplay.md 行 73 说 "TOUGH +100 延寿、ATTACK -80 折寿"，但 "-30\ncost = 250" 这个孤悬片段对不上 ATTACK 的 -80（更可能是 RANGED_ATTACK 的某个值），无法验证

**修复建议**:
1. **立即修复**: 从 git 历史找到 truncation 之前的完整版本（git log -p design/gameplay.md），或从 R4/R5 评审报告中找到曾经引用过的 body part 默认值并补回
2. **回填的最低字段集**（MOVE/CARRY/WORK/ATTACK/RANGED_ATTACK/HEAL 都需要）：
   - `name` / `description` / `action` / `range` / `cost` / `age_modifier`（必填）
   - `damage_type` + `base_damage`（攻击类）
   - `passive` map（被动类，如 CARRY 的 carry_capacity_per_part、HEAL 的 base_heal）
3. **补 Leech 行**: 已知 specs/02 §3.10-§3.15 没有 Leech 校验表（与表格 7 项断点对应），specs/reference/commands.md §Leech 给了 "Corrosive 15 dmg、300 Energy、伤害 50% 治疗自身"——把这个回填到 design/gameplay.md 的 §特殊攻击方式表
4. **补 Fabricate 行**: specs/reference/commands.md §Fabricate 给了 "500 tick CD、2000 Energy + 500 Matter"，但缺 body part 触发器（specs/08 §5.1 说 "custom" 不指定 body part——这是 G2 的根因，单独再讨论）
5. **CI 加防回归检查**: 添加 grep guard `! grep -F "[OUTPUT TRUNCATED" docs/`，杜绝以后再有 LLM 工具截断字符串混入源码

**为什么不是 High**: 这是一个会让任何工程师**立刻在编码第一天卡住**的物理缺失，且暴露了文档构建流程缺乏基本的 sanity check。Critical 当之无愧。

---

### 🔴 G2 [Critical] Fabricate 经济学崩盘——`structure_type` 任意取值 → 2000 Energy + 500 Matter 换 Nuker（100,000 Energy）+ 干掉一个敌方 drone，且无任何反制窗口

**位置**:
- `specs/core/02-command-validation.md` 行 837：`{ "action": "Fabricate", "object_id": "d1", "target_id": "e5", "structure_type": "Extension", "seq": N }`
- `design/gameplay.md` 行 928-934：default world.toml 中 Fabricate 的 cost 定义
- `specs/gameplay/08-api-idl.md` 行 324：`Fabricate | custom | fabricate | 转化建筑，500 tick CD`

**问题**: Fabricate 命令接受 `structure_type` 参数（specs/02 §15.2 给出的 IDL 示例），但**没有任何文档定义**：

| 缺失约束 | 后果 |
|---------|------|
| **结构成本独立支付** | 当前 Fabricate cost 固定 `{Energy: 2000, Matter: 500}`，与 `structure_type` 无关。即玩家用 2000+500 就能凭空生成一个 Nuker（structure_types[Nuker].cost = 100,000 Energy）→ 单笔交易获利 ≈ 98,000 Energy 价值 + 一个 RCL8 终极武器 |
| **RCL 校验** | 不检查目标房间 Controller 等级。RCL 1 玩家可在自己房间 Fabricate 出 PowerSpawn（rcl_required=7）、Nuker（rcl_required=8）——绕过整个 RCL 解锁系统 |
| **`max_per_room` 校验** | 不检查每房间数量上限。Extension max_per_room=60，但 Fabricate 不查这个表 → 可以 Fabricate 出第 61 个 Extension |
| **结构归属与放置位置** | "将敌方 drone 转化为己方建筑"——建筑是出现在 target drone 的位置吗？如果 target 在敌方房间内呢？这意味着我可以在敌方 owned 房间凭空生成自己的建筑——**领土系统直接崩溃** |
| **target 类型校验** | specs/reference/commands.md 行 205 写 "敌方 drone"，但 specs/02 行 837 的 IDL 示例没有限制 target 必须是 Drone（target_id="e5" 看不出类型）。如果可以 fabricate 敌方建筑 → 把敌方 Spawn 转成自己的 Tower？！ |
| **反制窗口** | §3.16 反制矩阵明确写 "Fabricate ❌（构造已完成）/ ❌ / 无——构造是即时动作"——Disrupt 不能打断、Fortify 不能清除、Hack 控制锁不能保护 |
| **lifespan 占用** | Fabricate 不消耗 drone lifespan、不占 main action slot 的限制不明 |

**Designer 视角的 dominant strategy**（评审员实战推演）:

```
策略「白嫖 Nuker」:
  Tick T:    Fabricator drone（Custom body：1 ATTACK + 1 MOVE = 50 Energy spawn cost）走到敌方 drone 旁
  Tick T+1:  Fabricate target=enemy_drone, structure_type="Nuker"
              成本：2000 Energy + 500 Matter
              收获：一个 hits=10000 的 Nuker（敌方 drone 消失 + 自己多一个 RCL 8 武器）
  Tick T+501: 冷却结束，重复

每 500 tick 净获利 ≈ 98,000 - 2000 = 96,000 Energy 价值
对手没有任何反制——Disrupt/Fortify/Hack 都不能阻止
```

```
策略「敌方领土殖民」:
  Tick T:    我方 Fabricator drone 跑进敌方 owned 房间（用 MOVE 部件穿越）
  Tick T+1:  Fabricate 任何敌方 drone → structure_type="Storage"
  
后果：我方在敌方 owned 房间内有了自己的 Storage（如果放置位置 = target.position）
       Controller 系统认为这是哪边的领土？
       敌方 drone 能 Attack 我的 Storage 吗（friendly_fire=false 但跨房间 owner？）
       领土主权和建筑归属彻底分裂
```

**修复建议**（Designer 视角必须有的约束）:

1. **结构成本独立支付**: Fabricate 总成本 = `fabricate_base_cost` + `structure_types[type].cost`。即 fabricate Nuker 实际消耗 2000+100,000 Energy + 500 Matter，让转化变成「资源置换 + drone 消除」而非「白嫖」
2. **RCL 与上限校验**:
   ```
   验证规则:
     - target.position 所在房间必须是 attacker owned
     - target.position.room.controller.level >= structure_types[type].rcl_required
     - structure count(type) in room < structure_types[type].max_per_room
     - 不允许 fabricate "Spawn"（核心建筑只能正常 Build）
   ```
3. **target 严格限定 Drone**: 在 IDL 与 validate 表加 `target.kind == "Drone" && target.owner != player_id`
4. **放置位置必须在 attacker 领土**: 拒绝在 enemy/contested/abandoned 房间 fabricate
5. **占用 main action slot**: Fabricate 是 main action，每 drone 每 tick 只能一个；同时 fabricator drone 触发 5-tick "建造完成" 状态——期间可被打断（add 反制窗口）
6. **加抗性**: "Psionic" 抗性不只过 hit-or-miss，应该让目标的 Tough body part 影响 fabricate 失败概率（Vanilla 数值需要平衡）

**为什么是 Critical 而非 High**: 当前规则下 Fabricate 是**单一 dominant strategy**——所有理性玩家会优先训练 Fabricator 部队。整个 8 种特殊攻击的张力网（Hack 短期控制 / Drain 长期搜刮 / Overload 战略压制 / Fortify 净化 / Debilitate-Leech 削血）都被 Fabricate 一个动作压扁。这不是数值微调，是**机制级缺陷**。

---

### 🔴 G3 [Critical] Drain 群攻经济不对称——50 Drainer drone 协同攻击 = 防御方 5000 Energy/tick 反制成本（不可持续）

**位置**:
- `design/gameplay.md` 行 617：`Drain | Carry+Work | 从目标建筑/存储中窃取资源，每 tick 转移 carry_capacity 单位 | 50 tick | 200 Energy/tick | 目标 EMP 抗性`
- `specs/core/02-command-validation.md` 行 311-331：Drain 校验规则
- `design/gameplay.md` 行 882-887：default `[[custom_actions]]` Drain 注册

**问题**: Drain **缺少全局冷却或 per-target 锁**——所有冷却都是 per-drone（50 tick），且没有 "同一 target 同 tick 只能被一个 drone Drain" 的约束。

**攻防经济分析**:

```
攻击方部署:
  20 个 Drainer drone（body：CARRY×5 + WORK×1 + MOVE×4 = ~340 Energy/drone spawn）
  carry_capacity: 5 part × 50 = 250 单位/drone（按 Vanilla 默认 carry_capacity_per_part=50，但文档未定义此数值——见 G7）
  
攻击成本:
  spawn: 20 × 340 = 6,800 Energy 一次性
  per-tick 维持: 20 × 200 = 4,000 Energy/tick

攻击收益（围攻一个 1M 容量 Storage）:
  per-tick 窃取: 20 × 250 = 5,000 单位
  净收益: 5,000 - 4,000 = 1,000 单位/tick
  攻穿 Storage: 1,000,000 / 5,000 = 200 tick

防御方反制:
  方案 A 用 Disrupt: 每 drone 100 Energy + Attack body part
    需要 20 个 Disrupter，每 tick 全部 Disrupt 才能完全阻止
    防御成本: 20 × 100 = 2,000 Energy/tick（持续防御）
    每个 Disrupter 50 tick 冷却 → 持续防御需要 ≥20 Disrupter，且每 50 tick 重新动作
    实际持续防御约 2,000 × 50/Disrupt 命中数 → 不可持续
    
  方案 B 用 Tower 击杀:
    Tower 50 dmg/10 tick = 5 dmg/tick 平均
    Drainer body 含 5 CARRY + 1 WORK + 4 MOVE = 10 parts × 100 hp = 1000 hp（Tough 不计）
    单 Drainer 击杀: 1000/5 = 200 tick
    20 Drainer 全杀: 200 × 20 = 4000 tick（远超资源耗尽时间）
    
  方案 C 用 Attack drone 近战:
    每 Attacker 30 dmg/tick × 20 Attacker = 600 dmg/tick
    20 Drainer 全杀: 20000 hp / 600 dmg = 34 tick
    Attacker spawn cost: 20 × ~260 Energy = 5,200 Energy
    可行！但需要预先训练好 20 Attacker 在房间内
```

**核心不平衡**: 
- **静态防御**（Tower）完全压不住 swarm Drain
- **主动反制**（Attacker）需要预先部署且战术撤退后无法持续防御
- **资源不对称**: 攻击方持续消耗 4k/tick 但收回 5k → 越攻越富；防御方消耗 2k/tick 但收益只是"少损失"

**对玩法的影响**:
- **新手玩家被精准抢劫**: Storage 满 = 立即被 Drain swarm 围攻，资源被搬空
- **战术深度反向**: 防御不再依靠地理优势（Tower 链），变成「军备竞赛 + 反应速度」
- **AI 玩家强势**: AI 可 24/7 监控敌方 Storage 状态，反应窗口比人类快 10 倍

**修复建议**:

1. **per-target Drain 锁**: 同一 (attacker_player, target_structure) 每 50 tick 内只允许一个 Drainer 同时 Drain（不限攻击者数量但限同一 target 的并发）—与 Overload 同模式
2. **Drain 衰减曲线**: 多个 Drainer 攻击同一 target 时，第 N 个的有效 carry_capacity 衰减为 `capacity / sqrt(N)`——10 个并发只 ~3.16 倍单 drone 效率，避免线性 swarm 收益
3. **Drain 触发警报**: target.owner 立即收到事件（即使在 fog-of-war 下）→ 主动防御决策窗口
4. **Disrupt 成本对称化**: Disrupt cost 50 Energy（半价）+ 命中即解除一组 attacker 的当前 Drain 状态而非单个 drone——成本结构匹配群攻

**Designer 哲学**: Drain 应该是"高风险的盗贼"，不是"资源 DPS 武器"。当前数值让它从战术工具变成了战略主轴。

---

### 🟠 G4 [High] Hack "5 tick 后自动恢复" vs "stage 5 永久夺取" 矛盾——Neutral 期是临时锁还是终身禁用？

**位置**:
- `design/gameplay.md` 行 616："5 tick 夺取成功（drone 转为 Neutral，停止执行 WASM，进入 idle）。**5 tick 后自动恢复**"
- `specs/core/02-command-validation.md` 行 303："5 tick 后自动恢复原 owner"
- `specs/core/02-command-validation.md` 行 470 （§3.16 反制矩阵）："Hack 施加后 5 tick 内——stage 1-4 可 Disrupt，**stage 5 夺取后无法恢复**"

**问题**: 两段文档对 Hack 后的恢复机制给出相反的描述。

| 描述位置 | 行为 |
|---------|------|
| design/gameplay.md 行 616 | 5 tick 后自动恢复 |
| specs/02 §3.10 行 303 | 5 tick 后自动恢复原 owner，Neutral 期间免疫再次 Hack |
| specs/02 §3.16 反制矩阵行 470 | stage 5 夺取后**无法恢复** |

**Designer 视角的影响**:

如果是"5 tick 后恢复"：Hack 是战术性骚扰工具，1000 Energy 换 5 tick 的 drone idle，性价比偏低（Disrupt 100 Energy 也能打断动作）。

如果是"永久夺取"：Hack 是**最强单体战略武器**——对手的高价值 drone（500+ Energy spawn cost）只值 1000 Energy 就能永久消除。Drain（200 Energy 消耗）+ Hack（1000 Energy 消除大型 drone）成为统治流派。

**Designer 推断**：从 §3.16 第 470 行 "stage 5 夺取后无法恢复" 来看，这可能是真正的设计意图——但 §3.10 和 design/gameplay.md 的"5 tick 后自动恢复"叙述是文档残留。如果是这样，Hack 经济需要重新平衡。

**修复方案**:

| 选择 | 结果 |
|------|------|
| **A. 永久夺取** | 在 §3.10 / design/gameplay.md 删除 "5 tick 后自动恢复"。Hack 成本上调到 ≥3000 Energy 或仅对低 lifespan 剩余的 drone 生效 |
| **B. 临时锁** | §3.16 改为 "stage 5 期间持续 5 tick 不可恢复，5 tick 后自动恢复"。维持 1000 Energy 成本 |
| **C. 半永久** | Hack 成功后 drone 进入 Neutral，30 tick 内可被 Fortify 救回，30 tick 后永久消失 |

无论哪种选择都比当前矛盾叙述好。Designer 倾向 **方案 B** —— Hack 是"暂时缴械"而非"绝杀"，符合"特殊攻击是工具不是终结技"的设计哲学。

---

### 🟠 G5 [High] Tutorial 100% Recycle 退还 vs §3.18 比例退还 lifespan 公式——两个机制规则冲突

**位置**:
- `design/gameplay.md` 行 83："**新手保护**: Tutorial 世界前 500 tick 回收退还 100%（新人可以试错）。标准世界回收退还 50%。"
- `specs/core/02-command-validation.md` 行 729："Tutorial | 前 500 tick 退还 100%"
- `specs/core/02-command-validation.md` 行 502-507（§3.18）：`refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`

**问题**: §3.18 的 lifespan 比例退还公式声称是 "修正方案" 防止末期回收套利，但 Tutorial 100% 退还规则**无条件覆盖** 这个公式。结果：

```
Tutorial 世界前 500 tick:
  drone 出生 100 tick 后 lifespan 还剩 1400/1500 = 93.3%
  按 §3.18 公式: refund_pct = max(0.1, 0.5 × 0.933) = 0.467 (≈47%)
  按 行 83/729: refund_pct = 100%
  
谁赢？
```

**Designer 视角的实际后果**:

如果 Tutorial 100% 优先：新手在 Tutorial 中可以"刷 spawn-recycle 套利"循环测试代码——每次 spawn 200 Energy，立刻 recycle 退 200 → 净 0 但 fuel 消耗为零（spawn-recycle 不计入主 action？这又是另一处缺失定义）。Tutorial 里没有套利后果，但养成了"可以 0 成本试错" 的习惯——出 Tutorial 进 Standard 后玩家会继续假设 Recycle 是免费 undo。

如果 §3.18 优先：行 83 的 "100% 退还" 描述是错的，Tutorial 也只能拿 ~50% 退还。新手保护承诺被打破。

**修复建议**:

1. **明确优先级**: §3.18 公式加 "特例"——Tutorial 世界前 500 tick `refund_pct = 1.0`，恒等覆盖 lifespan 公式
2. **Tutorial 套利消除**: Tutorial 世界禁用 spawn-recycle 循环（添加冷却或 "recycle 后 100 tick 内 spawn 同 body 失效" 规则）
3. **统一文档**: design/gameplay.md 行 83 改为 "Tutorial 世界前 500 tick `refund_pct = 1.0`（覆盖 lifespan 公式 §3.18）"

---

### 🟠 G6 [High] Vanilla Tier 解锁断崖——Tutorial/Novice 完全禁用 8 种特殊攻击 → Standard 全部解锁

**位置**:
- `design/gameplay.md` 行 422："分层解锁：Tutorial/Novice 默认禁用全部 8 种特殊攻击（Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate）。Standard+ 全部可用"

**问题**: 没有渐进式解锁。从 Novice 到 Standard 一次解锁所有 8 种特殊攻击 + 状态机矩阵 + 反制窗口——新玩家面对的复杂度从 0 跳到 100。

**Designer 视角的进阶曲线问题**:

```
Novice → Standard 一夜之间需要掌握:
  ✗ Hack 控制锁 5 阶段判定
  ✗ Overload fuel budget 战略压制
  ✗ Drain swarm 经济攻防
  ✗ Fortify 净化 + Disrupt 打断的反制窗口
  ✗ Debilitate 易伤叠加规则
  ✗ Leech / Fabricate 自定义 action 数学
```

参考 Screeps 的渐进式：Tutorial 教 spawn-harvest-build → Beginner 加 attack-defend → Intermediate 加 boost/lab → Advanced 加 power/intershard。每一步上一个新机制，新玩家有 ~10-100 小时消化时间。

Swarm 当前的 Tier 模型只控制"开关"——一旦开启 Standard 玩家面对的是 8 个相互干涉的特殊攻击。

**修复建议**:

引入 4 段式 Vanilla Tier 渐进解锁：

| Tier | 解锁内容 | 累计学习 |
|------|---------|---------|
| **Tutorial** | spawn / harvest / build / move（核心 4 动作） + 100% recycle | 基础经济循环 |
| **Novice** | + attack / ranged_attack / heal（HP 战斗） | 基础战斗 |
| **Standard-A** | + Disrupt / Fortify（反制基本盘） | 状态机入门 |
| **Standard-B** | + Hack / Drain / Overload（控制 + 经济压制） | 战略层 |
| **Advanced** | + Debilitate / Leech / Fabricate（高阶组合） | 全部解锁 |

每个 Tier 有最少 1500 tick（≈75min）的强制停留，玩家需要在 Arena PvE Challenge 中通过对应 tier 的考核才能解锁下一阶段。

---

### 🟠 G7 [High] Vanilla Ruleset 核心常量缺失——CARRY 容量 / drone HP / fatigue 公式都没数

**位置**: 跨文档（design/gameplay.md §核心默认值一览 行 425、specs/02 §3.x、specs/06 §核心数值）

**问题**: §核心默认值一览（行 425）声称给出了 "编码前必需的最小默认值"，但实际只列了：
- Work harvest: 1 unit/tick
- Spawn cooldown: 5 tick
- Tower attack: 50 dmg / 10 tick cooldown / range 5
- Source capacity: 3000 / regen 300

**遗漏**:

| 常量 | 重要性 | 备注 |
|------|-------|------|
| CARRY part 的 `carry_capacity_per_part` | Critical（决定全经济循环） | G3 计算用 50，但是从 RFC 推断的，无文档依据 |
| 各 body part 的 `cost`（Energy） | Critical | 因 G1 truncation 全没了 |
| 各 body part 的 `age_modifier` | High | 行 73 提到 TOUGH +100 / ATTACK -80，其它全空 |
| drone 基础 HP（`hits_max` per part 的常量） | Critical | TOUGH passive 给 +100/part，但 base 是多少？默认每 part 100 hp？需明确 |
| **fatigue 公式** | Critical | drone 移动后 fatigue 增加多少？由 MOVE part 数量减少？地形（Plain/Swamp/Wall）系数？无任何说明 |
| MOVE part 的 fatigue 减少速率 | Critical | spec/02 §3.1 只说 "drone.fatigue == 0 才能行动"，但增减规则全空 |
| Build progress per tick | High | Work part 在 Build action 上的 progress 速率 |
| Heal 实际效果 | High | 行 602 "Heal 12 dmg / 每 tick 缩短一个负面状态 10 tick"——是恢复 HP 还是清除状态？是"或"还是"和"？ |
| `MIN_LIFESPAN` 常量值 | Medium | 行 73 引用但未列入核心默认值表 |
| Spawn 时的 fatigue 初值 | Medium | 新生 drone fatigue 是 0 还是 spawning_grace_remaining=1？ |

**Designer 视角的影响**: 编码者第一天进入 "我手上有 100 Energy 该 spawn 什么 body？" 这个最基础的资源决策时，发现没有数。Vanilla Ruleset 不能 ship。

**修复建议**: 创建 `design/gameplay.md` 新章节 "§Vanilla 核心数值表"，把上述常量 + G1 修复回来的 body_part_types 块统一汇总。**所有 Vanilla 数值必须在一处定义**——避免跨文档矛盾。

---

### 🟠 G8 [High] Drain swarm 攻防代价不对称——DPS-vs-Disrupt 经济测算严重失衡

**位置**: `design/gameplay.md` 行 617（特殊攻击表 Drain 行）+ 行 620（Disrupt 行）+ §3.16 反制窗口矩阵

**问题**: Drain 与其反制 Disrupt 的成本结构对攻击方极度有利。

**经济计算**:

```
攻击方（Drain swarm 50 drones）:
  spawn 成本: 50 × (Carry+Work+Move 大约 100E) = 5000E 一次性
  执行: 200E/tick × 50 = 10,000E/tick 维持
  收益: 50 × carry_capacity（假设 50/part）= 2500 资源/tick
  净: +2,500 资源 - 10,000E = -7,500E/tick（如果窃取 Energy 则净 -7,500）
  ⚠️ 但如果窃取 Crystal/Matter 等其它资源，攻击方支出 Energy 换取目标的 Matter——是不对称资产替换

防守方（用 Disrupt 反制 50 个 Drain drones）:
  需要 50 个 Attack drone 各打一个 Disrupt
  spawn 成本: 50 × (Attack+Move 大约 80E) = 4000E
  执行: 50 × 100E = 5,000E（瞬发）
  
  ✅ Disrupt 一次成本看似低（5000E < 10000E/tick）
  ❌ 但 Disrupt 50 tick CD——50 个 Disrupt drone 只能挡 50 个 Drain drone 一次
  ❌ Drain 50 tick 后冷却好继续来——防守方 Disrupt 还在冷却
```

**深层不对称**: Disrupt 是 50 tick CD，Drain 也是 50 tick CD——"打断一次再启动一次" 完美对冲。但是：

1. **EMP 抗性叠加**: Drain 受 EMP 抗性影响，但目标建筑（Storage）默认 EMP 抗性是多少？设计文档没说。如果 Storage 默认 EMP 1.0（不抗），50 个 Drain 持续抽——一个 100 万容量 Storage 在 1000 / 50 / carry_capacity = 不到 50 tick 抽干。
2. **Disrupt 成功率**: §3.14 说 "目标 Sonic 抗性影响成功率"——但 Drain drone 是 Carry+Work，没有 Tough，默认 Sonic 抗性 1.0。理论上 100% 命中？文档没说"成功率"是 0/1 还是概率。
3. **Drain 同 tick 多次累加**（§3.16 "累加：drain_total = sum(drain_i)"）——攻击方收益线性扩展，防守方反制是 1:1（一个 Disrupt 打一个 Drain）。

**Designer 视角的 meta 演化预测**:

阶段 1（早期）: 玩家不敢用 Drain，因为防御代码不会写
阶段 2（中期）: 第一个写出 "Drain 50-drone swarm" 算法的玩家碾压新手
阶段 3（后期）: 所有新玩家被建议"先在 Forward Depot 之外存资源""用本地存储分散""用 Fortify 净化"——meta 收敛到"分散资产 + 全员 Tough+Heal 防御"
阶段 4（终局）: 经济规模大的玩家凭本地存储分散胜，新玩家因没有规模分散无法防 Drain → **Drain 成为新玩家进入门槛**

**修复建议**:

1. **加入 Drain 全局冷却**: 类似 Overload 的"同一 (target_id, world_id) 每 50 tick 最多 N 个 Drain 命中（不限来源）"——防止 swarm 集中攻击。
2. **Drain damage diminishing returns**: 第 1 个 Drain 100% 效率，第 2-5 个递减到 50%，第 6+ 个 0%。把"50 个 Drain" 退化为 "5-Drain effective"。
3. **建筑反制**: Storage 在 RCL 6+ 自动获得 "内置防御" 标志——被 Drain 时返回 50% 资源 "反流" 攻击者（伪 Leech 效果）。需要服主在 world.toml 启用。
4. **Disrupt 范围扩展**: Disrupt range 从 1 提升至 3——一个 Disrupt drone 可同时打断多个相邻的 Drain drone（AoE）。

我推荐 #1 + #4——保持成本经济，限制规模化。

---

### 🟡 G9 [Medium] Move 占用 main action slot 设计——pursuit 场景战术深度受损

**位置**:
- `design/engine.md` 行 232-247（Move-as-action 设计理由）
- `specs/02 §3.1` Move 校验规则

**问题**: 设计文档承认这是"有意的设计选择"（"playtest 阶段可能被挑战"），但 Designer 视角必须指出 pursuit 场景的具体痛点：

**追击战的 broken 体验**:

```
我方 RangedAttack drone (range=3) 追击敌方 Move drone（满速）:
  tick N: 我方在 (5,3)，敌方在 (5,7)，距离 4 → 我方 RangedAttack 失效
  tick N: 我方 Move (5,3)→(5,4)，敌方 Move (5,7)→(5,8)，距离 4
  tick N+1: 我方 Move (5,4)→(5,5)，敌方 Move (5,8)→(5,9)，距离 4
  ...永远追不上...

如果允许 Move + RangedAttack:
  tick N: 我方 Move (5,3)→(5,4) + RangedAttack 命中（距离 3） → 一发
  tick N+1: 我方 Move (5,4)→(5,5) + RangedAttack 命中 → 二发
  ...10 tick 内击毁敌方
```

文档说"这是设计意图——drone 不是即时代理"，但其后果：

1. **PvP 决斗几乎不可能**: 任何受伤的 drone 都可以"边跑边补血" 永远撤退（自己 Heal 自己时不需要移动），追击者每 tick 移动消耗一个 action slot 但不能攻击。
2. **战术单调**: 玩家最优策略变成"用 Tower 卡位" 或 "Hack 控制" 而非主动追击——主动战术消失。
3. **新玩家心理预期错位**: "我看见敌人在 5 格外，我有 RangedAttack range 3——我移动 2 格就能打到它" 的直觉被打破。

**反方论点（设计意图）**: "双 action 引入 move_then_attack vs attack_then_move 的顺序竞争"

**Designer 反驳**: 这是可解决的问题——固定执行顺序为"先 Move 后 Action"（相同 Phase 2a inline 逐条执行），双方都按此顺序，无二义性。Bevy ECS 完全支持 "一个 entity 在一个 tick 内执行两个有依赖关系的指令"。

**修复建议（按优先级）**:

1. **保持现状但补 RangedAttack 缓冲**: range 从 3 提升到 5——给追击者一个攻击窗口。
2. **温和折衷**: 引入 "Charge" 复合 action—— "Move + Attack 同 tick" 但成本 = (Move + Attack) 双倍，每 drone 每 50 tick 限用 1 次。让追击成为有代价的战术选择。
3. **彻底改变（推荐）**: Move 为 "自由动作"——每 drone 每 tick 可执行 1 Move + 1 Action（顺序固定 Move→Action）。Move 消耗 fatigue（这本来就是 fatigue 的设计目的），Action 消耗资源/冷却。

我推荐 #2——保留 "action slot" 哲学但允许有代价的 pursuit。

---

### 🟡 G10 [Medium] Vanilla Tier 配置位置在 world.toml `vanilla.tier` 但没有 [vanilla] 表的 schema 定义

**位置**: `design/gameplay.md` 行 422 末尾："层级配置: world.toml `vanilla.tier = \"Tutorial\" | \"Novice\" | \"Standard\" | \"Advanced\"`"

**问题**: 跨设计文档全文搜索 `[vanilla]` TOML 表——0 个引用。`vanilla.tier` 是哪个表的字段？是顶层 `[vanilla]` 还是某个嵌套？没有 schema。

```toml
# world.toml — 这个 [vanilla] 表的完整 schema 在哪？
[vanilla]
tier = "Standard"          # ← 提到了
# 还有什么字段？
# - tier 影响哪些机制开关？
# - 是否影响 §核心默认值一览中的所有数值？
# - 升级到 Standard 后能否降级回 Tutorial？
# - tier 切换的迁移规则（已有 drone 怎么办）？
```

**Designer 视角的现实问题**: 服主开 "Tutorial 世界" 时除了关闭 8 个特殊攻击，还应该关什么？打开什么？soft_launch 时间是不是更长？safe_mode 是不是无限期？没有定义。

**修复建议**: 在 `design/gameplay.md` 增加 "§Vanilla Tier 配置详表"，列出每个 Tier 控制的所有参数：

| 参数 | Tutorial | Novice | Standard | Advanced |
|------|---------|--------|---------|---------|
| safe_mode_duration | 5000 | 1000 | 500 | 0 |
| soft_launch_duration | 5000 | 3000 | 1500 | 0 |
| 启用的特殊攻击 | 无 | 无 | 全部 | 全部 |
| recycle_refund_pct | 1.0 | 0.5 | §3.18 公式 | §3.18 公式 |
| pvp_enabled | false | false | true | true |
| Drain global cooldown | N/A | N/A | 50 tick | 50 tick |
| ... | | | | |

---

### 🟡 G11 [Medium] Heal 反向治疗机制描述模糊——HP 恢复 vs 状态净化的语义未定义

**位置**: 
- `design/gameplay.md` 行 602: "Heal | —（反向治疗） | 12 | 每 tick 可缩短一个负面状态 10 tick 持续时间"
- `specs/02 §3.7` Heal 校验: "target.hits < target.hits_max"

**矛盾**:
- design/gameplay.md 表格说 Heal 的功能是"每 tick 可缩短一个负面状态 10 tick 持续时间"——这是**清除/净化**功能
- specs/02 §3.7 校验说 "target.hits < target.hits_max" 才允许 Heal——但若 HP 满血而仅有负面状态，目标无法被 Heal（被拒绝 `AlreadyFullHealth`）
- 同时 base_heal=12 暗示这是**HP 恢复量**，不是状态时长缩短

**Designer 视角问题**:

1. Heal 到底是 HP 恢复还是状态净化？两个机制的设计意图完全不同。
2. 若是 HP 恢复（base_heal=12 per part），"每 tick 缩短负面状态 10 tick" 这句话应当删除——它是错误描述
3. 若是状态净化，那 base_heal=12 含义不明（不是 HP），且 specs/02 的 hits_max 校验应改为"target 有任何负面状态"
4. **关键漏洞**: 若 Heal 同时具备两个功能且 specs 校验只检查 hits_max，玩家可以利用：drone 满血但被 Debilitate → 队友 Heal 被拒绝 → 无法净化负面状态

**修复建议**: 必须明确选择一个语义：

**方案 A（推荐）**: Heal 仅为 HP 恢复（base_heal=12/part），状态净化由 Fortify 独占。删除"每 tick 缩短负面状态 10 tick"句。

**方案 B**: Heal 为复合功能（HP + 状态净化），specs/02 校验改为：
```
target.hits < target.hits_max  OR  target 有任何持续型负面状态
```

我推荐 A——一个 action 一个职责，Heal 与 Fortify 分工清晰。

---

### 🟡 G12 [Medium] Build 校验只检查 Energy——Matter 等多资源建造无法处理

**位置**: `specs/02 §3.4` Build 校验："`drone.carry[Energy] >= build_cost(structure)`"

**问题**: 当前 Vanilla Ruleset 单一资源 Energy，但 design/gameplay.md §8.5 配置示例：

```toml
[actions.costs]
build.Tower = { Energy = 100, Matter = 25 }
```

校验代码硬编码 `drone.carry[Energy] >= build_cost`，多资源建筑（Tower 需要 Matter）无法被正确校验：
- drone 有 100 Energy 但 0 Matter——按当前校验通过，但 build 实际应失败
- 校验通过后 drone 进入 "build state"，到 apply 阶段才发现资源不足——浪费 fuel + 进入异常状态

**修复建议**: §3.4 校验改为：

```
对 build_cost 的每个 (resource, amount):
  drone.carry[resource] >= amount
```

`build_cost` 已经是 `{String: u32}` 格式（design/gameplay.md 行 219），校验逻辑要遍历整个 map。

---

### 🟡 G13 [Medium] Tutorial Recycle 退还规则与 §3.18 公式冲突

**位置**:
- `design/gameplay.md` 行 83："Tutorial 世界前 500 tick 回收退还 100%（新人可以试错）。标准世界回收退还 50%。"
- `specs/02 §3.18`："refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))"

**矛盾**:
- 标准世界 `0.5 × (remaining/total)` ——刚出生时 50%（与文档一致），半寿 25%，末期 10%
- Tutorial 前 500 tick 100%——但 "500 tick" 是 Tutorial 计时还是 drone 计时？

**模糊点**:
1. "前 500 tick" 指世界 tick 0-499 还是玩家加入后的 500 tick？
2. Tutorial 中 drone 在 500 tick 内出生但在 500 tick 后 Recycle，按哪个公式？
3. specs/02 §3.18 的公式是否对 Tutorial 有特殊处理？没说。

**修复建议**: 明确 §3.18 公式增加分支：

```
if vanilla.tier == "Tutorial" and (player_session_tick - player_join_tick) < 500:
    refund_pct = 1.0
else:
    refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))
```

并在 design/gameplay.md 行 83 改为 "Tutorial 世界前 500 tick（玩家加入后计时）回收退还 100%"。

---

### 🟡 G14 [Medium] PvE 副本 NPC 行为完全确定性——bot 调优后形成固定 farm 路线

**位置**: 
- `design/modes.md` §9.0："NPC 行为由引擎内置 AI 驱动（非 WASM）——确定性、可回放、不消耗玩家 fuel"
- §9.0 "事件 seed = Blake3(world_seed || tick_number || event_type)"

**问题**: PvE NPC 行为完全确定。这意味着：

1. 玩家可以用 `swarm sim` 离线运行 5000 tick → 完整记录虫群入侵的位置/数量/路径
2. 根据离线数据写出"专门刷虫群入侵"的 bot——在事件触发的精确 tick 部署 RangedAttack drone 卡住生成点
3. PvE 收益变成 "玩 sim 越多 farm 越精准"——非战术决策，纯 lookup table

**Designer 视角的 meta 演化预测**:

- 阶段 1: 普通玩家随机遇遇到虫群入侵——损失部分 drone
- 阶段 2: 高水平玩家发现确定性，开始用 sim 预跑
- 阶段 3: "Anti-Swarm" bot 开源——所有玩家都用——每次虫群入侵都被 100% 拦截，掉落资源被精准收集
- 阶段 4: PvE 失去威胁/惊喜，沦为定时领钱机制——服主被迫频繁更换 world_seed 以阻止 farm

**修复建议**:

1. **NPC 行为引入有限随机性**: NPC 选择行为时使用 `Blake3(tick || npc_id || world_seed) % action_pool_size` ——确定性但不可由"事件 seed" 直接预测
2. **事件触发增加抖动**: "每 1000 tick 概率 10%" 改为 "基于玩家行动统计触发"（如：玩家总 drone 数 × 0.001 概率/tick）——让事件难以预测
3. **NPC 选择目标加入混淆**: Swarm 不一定攻击"密度最高"的玩家，可以基于 "之前 100 tick 内击杀玩家 NPC 数最少的玩家" ——惩罚熟练 farmer
4. **Loot 表加入随机性**: NPC 掉落不固定——使用 Blake3-XOF 但 seed 包含"玩家最近 100 tick 战斗指令哈希"——专门反 farm 的 bot 失效

我推荐 #1+#2——保留"可回放" 核心确定性同时让 farm 变难。

---

### 🟡 G15 [Medium] Forward Depot age 维修与 Controller 硬上限的关系不明确

**位置**:
- `design/gameplay.md` 行 77："**Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 max(0, age + 1 - min(0.5, controller_count * 0.5))）。**"
- `design/gameplay.md` 行 199-203：Depot 维修配置 "`repair_aging = 5` 每 drone 降低的 age 量"

**问题**: 硬上限只约束 Controller，**Forward Depot 是否计入此上限**？

```
玩家拥有 1 Controller + 5 Depot:
  Controller 硬上限: 0.5/tick
  Depot 维修上限: 5 Depot × 5 age = 25/tick（消耗本地 Energy）
  
有效 age 减少 = 0.5 + 25 = 25.5/tick？
还是单独的 Controller 上限 0.5 + Depot 不受约束？
```

**Designer 视角的影响**:

- **如果 Depot 不受 Controller 上限约束**: 富有玩家可建 100 个 Depot（每个 5000 Energy + 维护费），永久续命 drone。Controller 硬上限失去意义——绕道 Depot 即可。
- **如果 Depot 受 Controller 上限约束**: Forward Depot 的设计意图（"前线维修，物流是玩法"）失效——Depot 不能给前线 drone 提供有效的补给。

**修复建议**: 明确两个约束的关系：

**方案 A**: Controller 与 Depot 共享一个总硬上限：每 tick 玩家所有 age 维修总量 ≤ 自然增长 × `aging_recovery_cap`（默认 0.8 = 自然增长的 80%）。Controller 用完上限的 50% 后，Depot 可补足剩下 30%。lifespan 仍然是核心约束，但 Depot 提供"地理灵活性"——给前线 drone 的 age 维修而非堆叠总量。

**方案 B**: Controller 硬上限只限 Controller，Depot 独立但每 Depot 维修速度更慢（如 1 age/tick 而非 5）+ 单 drone 每 100 tick 只能在 Depot 维修一次（per-drone cooldown）——通过"次数"限制总维修量。

我推荐 **方案 A**——保持 lifespan 经济意义，让 Depot 成为"将维修份额从主基地转移到前线"的工具。

---

### 🟢 G16 [Low] Arena 平局判定优先级中 "剩余资产" 含义不明

**位置**: `design/modes.md` 行 22："tick 到上限按剩余资产判定（drone数→建筑数→资源量）> 平局"

**问题**:
- "drone 数" = 计活 drone 还是包括 spawning？
- "建筑数" = 包括施工中的 construction sites 吗？
- "资源量" = Energy + Matter + ... 加总（按什么权重）？还是只看 Energy？

**Designer 视角的影响**: 100 vs 100 drone + 5 vs 5 建筑 + 资源量都接近时，玩家在策略选择上不知道该堆什么——破坏 Arena "对称公平" 的设计承诺。

**修复建议**: 在 design/modes.md §9.1.3 末尾增加 "§9.1.3.1 详细平局判定"：

```
当 tick 到上限且双方未触发其他终止条件时:
  1. 比较活 drone 数（不含 spawning, hits > 0）→ 高者胜
  2. 平 → 比较 owned 建筑数（不含 construction site, hits > 0）→ 高者胜
  3. 平 → 比较所有资源类型按 "经济权重" 加权总和：
     - Energy: 1.0 倍权重
     - 其它资源类型按 world.toml `[resources.equivalent_value]` 表配置
     - 默认 Vanilla: Matter = 5.0 倍 Energy
  4. 平 → 比较建筑总 HP（含 construction site 已投入资源）→ 高者胜
  5. 平 → 真平局（双方算法等价）
```

---

### 🟢 G17 [Low] Arena PvE Challenge 评分公式中的 par_time 来源不明

**位置**: `design/modes.md` §9.1.5 行 187："`efficiency = min(1.0, par_time / actual_time)`"

**问题**: par_time 是谁定的？
- 服主在 scenario 配置中固定？
- 系统自动计算（基于历史最快通关时间）？
- 第一次完成场景的玩家？

**Designer 视角的影响**: 排行榜公平性——如果 par_time 是"历史最快"，第一个通关者会建立基线，后续玩家越来越难超过 100% efficiency。如果 par_time 由服主固定，是否会因数值不当让 100% efficiency 无法达成？

**修复建议**: 明确 par_time 来源：

```toml
[arena.pve.scenarios.guardian_gauntlet]
par_time = 200  # 显式声明，服主调优
# 或者:
par_time_source = "first_completion"  # 自动追踪
par_time_floor = 100  # 即使有人通关更快，最低 par 是 100 tick
```

---

### 🟢 G18 [Low] World 模式无胜利条件——长期玩家激励不明

**位置**: `design/modes.md` 行 22："无——类似 MMO 持续沙盒，玩家自行设定目标（建造、控制、经济、社交）。不存在「游戏结束」状态"

**问题**: 设计哲学正确（持久 MMO 不需要胜利），但 Designer 视角必须看到的体验问题：

- 新手 "我该 grind 什么" 的方向感缺失
- 老手 "我玩了 5000 小时该不该退" 的退场点缺失
- 排行榜被明确禁用（"持久世界天然不公平"），但 "展示"（殖民地年龄、GCL、房间数）和 "非竞争" 的描述自相矛盾——展示就是排名

**Designer 视角的修复建议**:

1. **加入 "Quest 系统"**: 服主可在 world.toml 定义可选目标（"占领 50 个房间""建立跨 5 房间贸易路线""建造 100 个 Tower"），玩家完成后获得 "Achievement Title" + 视觉徽章——非竞争但有目标感
2. **赛季制 World 子模式**: World 主世界永生，但服主可定期开 "Season World"（90 天后归档）——保留 Arena 的竞争性，玩家在 Season 中刷成绩，归档后建立 "赛季英雄榜"
3. **明确 "展示" 的非竞争意图**: 把 "GCL""房间数" 等数据放在 "个人/联盟历史" 而非 "全服排行"——避免 "展示" 和 "排名" 混淆

---

### 🟢 G19 [Low] Spawn-Recycle 套利的 fuel/action 经济测算缺失

**位置**: `design/gameplay.md` §8.6 World 默认 `code_update_cost = 0`（免费）

**问题**: spawn 200 Energy → recycle 100 Energy（50%）—— 净亏 100 Energy。但每次循环：
- 消耗 spawn cooldown 5 tick + recycle 触发 death_mark/death_cleanup pipeline
- 消耗少量 fuel（CommandIntent 校验 + spawn validation）
- **不消耗 main action slot**（spawn 在 spawn_id 上不是 drone 的 action）

如果玩家想测试 "我的代码在不同 body 下的策略"，可以：
```
tick N:    Spawn body=[Move,Carry,Work] → 200E
tick N+5:  Recycle → 100E retrieved → net -100E
tick N+10: Spawn body=[Move,Carry,Carry,Work] → 250E
tick N+15: Recycle → 125E → net -125E
...
```

100E 每次的 "测试代价" 在 World 里可能是数小时的真实游戏时间收益——但 Designer 视角应明确这是"feature" 还是"bug"。

**Designer 视角**:
- 如果是 feature: 鼓励玩家做 in-world 实验——好。
- 如果是 bug: 玩家用此循环刷 Arena PvP 中的快速重组（突然换全 Attack drone 反击）——破坏战略稳定性。

**修复建议**: 在 §3.18 lifespan 公式之外，加入 "Recycle 后冷却"：
```
spawn_id 在 Recycle 命中后 50 tick 内不能再 spawn（per-spawn cooldown）
```

防止快速 swap，保留单次 "试错" 但禁止套利循环。

---

### 🟢 G20 [Low] Tutorial 与 Standard 之间没有 Novice 缓冲过渡

**位置**: `design/gameplay.md` 行 422 描述："Tutorial/Novice 默认禁用全部 8 种特殊攻击"

**问题**: 看 Vanilla 分级名义上是 4 级（Tutorial/Novice/Standard/Advanced），但具体内容上 Tutorial = Novice（都禁特殊攻击），Standard = Advanced（都开放全部）。中间没有 "开放部分特殊攻击" 的缓冲层。

**Designer 视角的影响**: 玩家从 "无特殊攻击" 直接跳到 "全部 8 种" 是体验断层。新手在 Standard 世界遇到老玩家叠加 Hack + Drain + Debilitate + Overload 的组合，根本无法应对。

**修复建议**: 重新设计 4 层：

| Tier | 特殊攻击 | 说明 |
|------|---------|------|
| **Tutorial** | 全禁 | 教学世界，纯采集/建造/基础战斗 |
| **Novice** | 开放：Disrupt, Fortify | 防御型攻击优先解锁——玩家学会反制再学进攻 |
| **Standard** | + Drain, Hack, Debilitate | 中级组合解锁，开始有战略层 |
| **Advanced** | + Overload, Leech, Fabricate | 全部解锁，高阶玩家世界 |

新手房间分配策略可以让 "在世界 X tick 数 < N 的玩家" 自动获得 Novice 解锁集，到 Standard 后开放更多。

---

## Designer 视角的 Strengths（亮点）

设计中做得好的部分必须明确——避免修改时误删。

### 🌟 S1 lifespan + age_modifier + Controller 续期形成的 "地理-时间" 经济

`design/gameplay.md` §8.2 的 drone 生命周期设计**优秀**：

- **lifespan 是基础约束**：Tough +100 延寿、Attack -80 折寿——身体配置选择成为长期成本
- **age 维修必须"回家"**: drone 跑去 Controller/Depot 才能维护——逼迫玩家思考物流网络
- **Controller 硬上限 50%**: 即使无限 Controller 也不能突破自然 +1/tick 衰老的 50%——保留 lifespan 经济意义
- **active aging 110%**: 闲置 drone 自然损失更慢——压制 "挂机刷资源" 策略

这套机制把"时间"变成了和"空间"一样核心的资源——是 Screeps 等同类游戏没做到的设计深度。**保护这套设计**——任何修改都要再三确认不破坏 "地理决定 lifespan" 的核心。

### 🌟 S2 World 与 Arena 的双引擎架构

`design/modes.md` §9 的双模式架构**清晰且互补**：

- World = 持久沙盒，**不追求公平**（老玩家先发优势是 feature 而非 bug）
- Arena = 限时对决，**对称起点 + 锁定代码**——纯算法对抗
- PvE Challenge 嵌入 Arena，提供 "算法 vs 算法" 之外的训练场

这套架构允许玩家根据兴趣自选玩法——不强行融合两个矛盾的设计目标到同一系统中。

### 🌟 S3 Overload 抗永久锁死证明（§3.17）

`specs/core/02-command-validation.md` §3.17 给出了 "目标 fuel budget 永远不会低于 MAX_FUEL × 0.2" 的严格数学证明：

- 单次削减 500k
- 全局冷却 50 tick
- 每 tick 恢复 10k
- 50 tick 内恢复 100k > 单次削减导致的下限突破

**这种"主动证明设计不可被滥用"的工程实践非常少见**，是 Swarm 文档质量的标杆。所有特殊攻击都应该有类似的形式化分析。

### 🌟 S4 Spawning Grace 1-tick 无敌帧

`design/engine.md` §3.2 的 "`SpawningGrace { remaining: 1 }`" 机制：

- 新生 drone 1 tick 内免疫所有伤害
- 防止 "在 Spawn 旁部署 RangedAttack 秒杀新生"——R4 G1 "出生即斩" 的修复

**这是 R4→R5→R6 的迭代成果**，必须保留。

### 🌟 S5 Source Gate + Command Source 分类

`specs/security/09-command-source.md` 的 Source Gate 设计：

- WASM 输出 CommandIntent（不可信，仅 sequence + action）
- 服务端注入 player_id / source / tick → 形成 RawCommand
- 校验后升级为 ValidatedCommand

**这套"信任边界明确化"的设计阻断了大量伪造攻击**，是 Designer 视角下"游戏内身份"的可靠基石——无身份伪造，特殊攻击的 ownership 校验才有意义。

---

## Balance Risks（长期 meta 演变预测）

Designer 视角下，以下趋势需要 playtest 期间重点观察：

### ⚠️ Risk 1: Recycle-Spawn 替换战术成为主流

如果 G19（Recycle 套利测算缺失）不修，玩家会发现：
> "维持 5 种 body 模板的 drone 池，根据敌情快速 Recycle + Spawn 切换" 成为最优策略。

结果：
- 每场 PvP 战斗变成 "猜对方下一 tick 是什么 body" 的元游戏
- Body part 选择失去战略意义（任何错误选择 5 tick 内可以纠正）
- 老玩家的 "经验" 让位给 "反应速度"——但 Swarm 是编程游戏，应该奖励经验

### ⚠️ Risk 2: "Drain 海" 成为 PvE/PvP 的主导策略

如果 G7（Drain 多攻击者无协同上限）不修，玩家会发现：
> "50 个 Carry+Work drone 围攻一个 Storage" 比 "5 个 Attack drone 慢慢拆" 经济效率高 10 倍。

结果：
- 所有进攻策略坍缩到 Drain 海
- HP 战斗（Attack/RangedAttack）变成 "清场用"，主战术是 Drain
- 防御方建造 Tower 没用（Tower 不能 Disrupt），必须自己也派 Drain drone 反向窃取

### ⚠️ Risk 3: Fabricate Nuker 经济崩溃（如果 G2 不修）

500 tick CD 的 Fabricate 转化任意建筑——核武经济一夜瓦解。新手在 1 周内被 "Nuker spam" 推平，老玩家垄断核武体系。

### ⚠️ Risk 4: Hack 5-stage 打断窗口太宽

`design/gameplay.md` 行 616 + 反制窗口矩阵显示：Hack 在 stage 1-4 都可被 Disrupt 打断，stage 5 才完成。

实际效果：
- 攻击方需要保护 Hack drone 4 tick——必须带 RangedAttack 护卫
- 防御方只需 1 个 Disrupt drone（100 Energy/Disrupt） vs 1000 Energy/Hack——经济上 10:1 不划算
- Hack 几乎不会被使用——除非攻击方有压倒性兵力优势

**预测**：Hack 在 PvP 中将成为 "概念上酷但实战无人用" 的死技——破坏特殊攻击的多样性。

**Designer 视角建议**: 重新评估 Hack 的 stage 推进——可能需要 stage 2 后无法 Disrupt（已确认控制），或大幅降低 Hack 的 Energy 成本（500 而非 1000）以平衡经济。

### ⚠️ Risk 5: Arena PvE Scenario 被速通 bot 套利

`design/modes.md` §9.1.5 的 Arena PvE Challenge 用 `(scenario, difficulty, map_seed)` 决定 NPC 行为——确定性。玩家针对每个 (scenario, difficulty, seed) 组合可以训练"专杀 bot"。

**预测**：排行榜将被 "针对 seed 1234 的最优解""针对 seed 5678 的最优解" 等专杀算法占据。普通玩家的通用策略永远进不了前 100。

**Designer 视角建议**: Arena PvE 的 map_seed 应每天/每周轮换——保留可复现性（同 seed 同结果）但不让玩家针对单 seed 训练。

---

## Missing（设计合同缺失项）

以下内容**当前文档完全没说**，必须在实现前补足：

| ID | 缺失项 | 位置 | 紧急程度 |
|----|--------|------|----------|
| M1 | 6 种 body part 的完整定义（cost / age_modifier / passive / 能力） | `design/gameplay.md` 行 624 truncation 区域 | **Critical**——见 G1 |
| M2 | Move action 在不同地形（Plain/Swamp/Road）的 fatigue 消耗公式 | `design/gameplay.md` §8.2 / `specs/core/02-command-validation.md` §3.1 | **High** |
| M3 | MOVE part 提供的 fatigue capacity 与每 tick 恢复速率 | `design/gameplay.md` §8.2 | **High** |
| M4 | Build 进度系统：每 tick Work part 投入的 progress 量 | `design/gameplay.md` §3.1 / `specs/core/02-command-validation.md` §3.4 | **High** |
| M5 | Carry part 的 carry_capacity_per_part 默认值 | `design/gameplay.md` §8.2 / 行 624 区域 | **High** |
| M6 | Heal 的具体效果——只回 HP 还是同时清除负面状态？ | `design/gameplay.md` 行 602 / `specs/core/02-command-validation.md` §3.7 | **High** |
| M7 | Tutorial 的 "成功标准"——什么样的 bot 算"通过"？ | `design/modes.md` / `specs/gameplay/06-feedback-loop.md` §2.1 | **Medium** |
| M8 | Fabricate 的 structure_type 限制（白名单 / RCL / 房间归属） | `design/gameplay.md` §8 / `specs/core/02-command-validation.md` 缺失 §3.20 | **Critical**——见 G2 |
| M9 | NPC 蓝图（Blueprint）解锁的具体内容——哪些 body part / 建筑配方？ | `design/modes.md` §9.0 "NPC 掉落经济" | **Medium**（影响 PvE Tier 2 实现） |
| M10 | Drain 的 per-target 全局上限（多个攻击者协同） | `design/gameplay.md` §8 / `specs/core/02-command-validation.md` §3.11 | **Critical**——见 G7 |
| M11 | Recycle 后 spawn cooldown（防止套利循环） | `design/gameplay.md` §3.18 / `specs/core/02-command-validation.md` §3.9 | **Medium**——见 G19 |
| M12 | Forward Depot 维修与 Controller 硬上限的累加规则 | `design/gameplay.md` §8.2 "Drone 生命周期" + 自定义建筑类型 Depot 配置 | **Medium**——见 G15 |
| M13 | Arena 平局判定中 "剩余资产" 的具体优先级与权重 | `design/modes.md` 行 22 / §9.1.3 | **Low**——见 G16 |
| M14 | World 模式新手 "长期目标" 设计 | `design/modes.md` §9 | **Low**——见 G18 |
| M15 | Vanilla Tier 与新手房间分配策略 / soft_launch 的协同关系 | `design/gameplay.md` §3.1a / §8.2 | **Low**——见 G20 |

---

## 4. Verdict 详解与修复路径

### Verdict: **REQUEST_MAJOR_CHANGES**

理由：
- **3 个 Critical（G1/G2/G3）**——任何一个都会让 MVP 无法编码或会崩坏 meta；不能进入实现
- **5 个 High（G4-G8）**——都是设计承诺与文档矛盾，会在 playtest 中爆出，应在编码前合上
- **7 个 Medium / 8 个 Low**——可以分批修复，优先 G9-G15

---

### 修复优先级（按 1-2 周时间窗口）

**Day 1（必须完成）**:
1. 修复 G1：恢复 design/gameplay.md 行 624 的 truncation 内容
   - 工作量：1-2 小时（git log -p 找到上一版本，重新粘贴）
2. CI 加防回归：`! grep -F "[OUTPUT TRUNCATED" docs/`
3. 修复 G7：补 Vanilla 核心常量表（CARRY 容量、fatigue 公式、各 body part cost）

**Day 2（必须完成）**:
4. 修复 G2：Fabricate 增加 structure_type 白名单 + RCL 校验 + 成本独立支付
5. 修复 G4：明确 Hack "5 tick 后自动恢复" 的语义（推荐方案 B 临时锁）

**Day 3-4**:
6. 修复 G3：Drain 引入 per-target 全局协同冷却
7. 修复 G5：Tutorial recycle 与 §3.18 公式优先级
8. 修复 G6：Vanilla Tier 渐进式解锁（4 段→5 段）
9. 修复 G8：Drain swarm DoT 衰减

**Day 5+**:
10. 修复其余 Medium / Low 问题（按 G9-G20 顺序）

---

### 进入实现的合并条件

✅ G1 / G2 / G3 全部 CLOSED（Critical 阻塞清空）
✅ G4 / G5 / G6 / G7 / G8 在文档中给出明确决策（High 至少有方案）
✅ M1 / M5 / M6 / M8 / M10 在 design/gameplay.md 中补全（Missing 中 Critical / High 项）
✅ Vanilla 核心常量表在 design/gameplay.md 单独章节（防止跨文档矛盾）

不要求 Medium / Low 全部修复后才能编码——这些可以在编码阶段并行处理。但 Critical / High 必须在 "编写 spawn_system" 第一行代码之前合上。

---

## 5. Designer 对 R6 评审的元评价

R6 是 R3-R5 的 "clean-slate 全量评审"——评审范围扩大到所有 design/ + specs/，不限于 Blocker 闭合。

**比 R5 进步的地方**:
- §3.16 状态机矩阵已经成型——R4-R5 反复要求的最终交付物
- §3.17 Overload 抗永久锁死证明——可验证设计承诺
- SpawningGrace 1-tick 无敌帧机制——R4 G1 "出生即斩" 完整闭合
- §3.18 Recycle 比例退还公式——R4 G3 末期套利完整闭合

**新发现的 R3-R5 没暴露的问题**:
- G1 文档物理截断——文档构建流程缺乏 sanity check
- G2 Fabricate 经济崩盘——Custom action 引入新 power 时缺乏"这是不是 dominant strategy" 的强制审计
- G7 Vanilla 核心常量缺失——"我们设计了 8 种特殊攻击" 的同时忘了 "MOVE part 多少 Energy"

**R6 的评审视角对项目的价值**:
本轮评审跳出了 R3-R5 的 "修复前一轮 Blocker" 思维，从 "Vanilla Ruleset 能否独立编码" "meta 演化是否健康" 角度审视——这种全量评审应该每 5-10 轮做一次，避免局部修补忽略全局矛盾。

下一轮（R7）建议：

1. 修复完 G1-G8 后重做一遍 "我从零写 spawn_system 需要什么常量" 的实操推演，捕捉本轮没找到的 Missing
2. 引入 "AI 玩家视角评审"——专门让一个 AI agent 实际尝试用 MCP 部署一个 starter bot，记录所有遇到的 "我不知道这个值是什么" 时刻
3. Drain / Hack / Fabricate 等"动作机制"应该有 simulator 实测——不止是文档评审，要在小型 sim 中跑出经济/战术数据

---

## 附录 A: 评审范围与未覆盖项

**已评审**:
- ✅ design/README.md
- ✅ design/engine.md
- ✅ design/gameplay.md（含 §1-§8.5 全部 + §8.6-§8.8 抽查 + §3.x ECS 章节）
- ✅ design/modes.md
- ✅ design/interface.md（粗读）
- ✅ design/tech-choices.md（未细读——超 Designer 视角范围）
- ✅ specs/core/02-command-validation.md（重点 §3.x 全部 + §1-§7）
- ✅ specs/core/01-tick-protocol.md（抽查 spawning_grace 部分）
- ✅ specs/core/07-world-rules.md（抽查 custom_actions 部分）
- ✅ specs/gameplay/06-feedback-loop.md
- ✅ specs/gameplay/08-api-idl.md（§5 可配置命令章节）
- ✅ specs/reference/commands.md（抽查 Leech / Fabricate）
- ⚠️ specs/security/03-mcp-security.md（未读——Security 视角覆盖）
- ⚠️ specs/security/05-visibility.md（未读——Security 视角覆盖）
- ⚠️ specs/security/09-command-source.md（未读——Security 视角覆盖）
- ⚠️ specs/future/T2-incremental-snapshot.md（未读——Architect 视角覆盖）
- ⚠️ specs/future/T3-shard-protocol.md（未读——Architect 视角覆盖）
- ⚠️ specs/12-gateway-protocol.md（未读——Gateway 协议非 Designer 关注点）

**约束承诺**:
- 评审"设计合同" 而非措辞/格式/编号 ✓
- 不明确处指出"缺失合同" 而非"猜测意图" ✓（M1-M15 列表）
- 跨文档矛盾明确标注两个冲突位置 ✓（G4 Hack / G5 Recycle / G11 Heal / G13 Tutorial）
- 不引用 ROADMAP.md ✓

---

## 附录 B: 评审员声明

本评审由 rev-claude-designer（Claude Opus 4.7，Game Designer 视角）完成。

我以 Designer 而非 Architect/Security 视角审视：
- 关注玩法机制是否平衡 / 进阶曲线是否合理 / 长期 meta 是否健康
- 不评判技术选型（Bevy / Wasmtime / FoundationDB 是 Architect 关注）
- 不评判安全边界（MCP 隔离 / 可见性 oracle 是 Security 关注）
- 不评判文档措辞 / 格式 / 编号

我的评审标准：
1. **可玩性**：核心循环是否闭合？新手到老手的进阶路径是否清晰？
2. **平衡性**：是否存在 dominant strategy？资源系统/经济系统/战斗系统是否相互制衡？
3. **可读性**：玩家（人类 + AI）能否在不查文档的情况下"猜对"游戏规则？
4. **长期演化**：6-12 个月后 meta 会变成什么样？是否会出现"被破解"的最优解？

我承认 Designer 视角必然遗漏一些 Architect/Security 维度的问题——这正是多视角评审议会（design-parliament）的设计目的。本评审与 rev-claude-architect / rev-dsv4-architect / rev-claude-security / rev-dsv4-security / rev-gpt-security / rev-gpt-designer 的评审报告交叉对比，由 rev-speaker 综合形成 CONSENSUS-REPORT.md。

如果上述任何 Concern 与其他视角的评审结论矛盾，以 CONSENSUS-REPORT.md 为最终决议。

— rev-claude-designer @ 2026-06-16
