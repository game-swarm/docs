# Swarm R2 设计评审 — Game Designer 视角

Reviewer: rev-claude-designer (Claude Opus 4.7)
Task: t_79aa9d9f / review-R2-designer-claude
Date: 2026-06-16
Scope: `/data/swarm/docs/design/DESIGN.md`, `/data/swarm/docs/specs/01-tick-protocol-spec.md`, `/data/swarm/docs/specs/02-command-validation-spec.md`, `/data/swarm/docs/specs/05-unified-visibility-policy.md`, `/data/swarm/docs/specs/06-mvp-feedback-loop.md`, `/data/swarm/docs/specs/07-world-rules-engine.md`, `/data/swarm/docs/specs/08-game-api-idl.md`, `/data/swarm/docs/api/{commands,host-functions,mcp-tools}.md`, `/data/swarm/docs/GETTING-STARTED.md`, R1 速览 `R1-SPEAKER-VERDICT.md` 与 R1 designer review。
Perspective: 游戏机制 / 平衡性 / 进度曲线 / meta 演化 / 数值漏洞。

---

## Verdict

**APPROVE_WITH_RESERVATIONS**（与 R1 同档；范围已大幅收窄，但仍有平衡盲点）

R2 在我 R1 标记的三个共识前必修项上做出实质修复，骨架可以进入实现：

- **R1 G1 — RCL 进度曲线断崖**：已重定调为近似几何增长（200 / 400 / 800 / 1500 / 3000 / 6000 / 12000，倍率 1.88–2.0），曲线已从「3 倍最终跳跃」收敛到我建议的 1.6–2.0 区间。✅
- **R1 G2 — Controller 续期破坏 lifespan**：`§3.1` 明确写入硬上限「每 tick 总 age 回退 ≤ 自然增长 50%」，且公式给定（`max(0, age + 1 - min(0.5, controller_count * 0.5))`）。永久 drone 攻击向量被关闭。✅
- **R1 R2 — Overload 人/AI 不对称**：`§8` Overload 行已加 `is_visible_to(target, attacker)` 与 50 tick per-target 全局冷却，并明确「静默返回，不可推断目标 fuel」。基本对齐 Speaker B4。✅（但见 G1）

骨架层（WASM 同路径、tick 驱动、World/Arena 双模式、Body 不可逆 + 50% recycle、Vanilla Ruleset 三层扩展）现在足够自洽，可以开实现工。但 R2 引入或保留了 4 个仍然会决定 meta 形态的平衡空洞，外加 3 个 R1 时遗留至今的体验缺口（onboarding / 失败恢复 / 长期身份）。这些不阻塞实现启动，但**必须在第一次公开测试前定型**——它们直接决定首发能否留住人。

进入实现可以；首发体验不可冻结。

---

## Strengths（R2 相对 R1 的进步）

### S1 — RCL 曲线现在是几何增长，不再是「悬崖」

R1 时 RCL7→8 是 50k→150k = 3.0× 跳跃，且 1→2 仅 200。这是结构性中后期墙，绝大多数玩家会被卡在 RCL6-7、RCL8 沦为 1% 玩家专属。R2 已重写为：

```
RCL1→2:  ×∞   (200, 起步)
RCL2→3:  ×2.00
RCL3→4:  ×2.00
RCL4→5:  ×1.88
RCL5→6:  ×2.00
RCL6→7:  ×2.00
RCL7→8:  ×2.00
```

倍率收敛在 1.88–2.0，进度曲线从 RCL2 开始可预期，玩家每升一级的「投入是上次的两倍」是一个强可学习信号。这条修正的份量比看上去重——它把「RCL8 = 1% 玩家专属」改成「RCL8 = 持续投入到一定 tick 总量的玩家都能到」，这才是 Vanilla 该有的形状。

### S2 — Controller 续期硬上限把 G2 的滚雪球向量关掉了

`§3.1` Controller 升级表下面的 Age 恢复段落明确写：

> Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 `max(0, age + 1 - min(0.5, controller_count * 0.5))`）。

且公式可执行。这堵住了我 R1 最在意的单点漏洞——「堆 N 个 Controller = 永久 drone」。lifespan(1500) 重新成为有效约束，战术轮换重新有意义。

我必须强调：R1 时这是一个**结构性 dominant strategy**——任何博弈论建模都会得出「最优行动 = 单调堆 Controller」，与对手行为无关。它现在被关掉了，R2 的 meta 才有混合策略空间。

### S3 — Vanilla Ruleset 三层扩展把「平台 vs 游戏」边界写清了

R1 时 Vanilla / Modded / Future 混在同一层级，新手第一小时面对的是「整个引擎」而不是「一个具体游戏」。R2 引入了：

- Layer 1（Core，IDL 冻结） / Layer 2（Declarative，world.toml 调参） / Layer 3（Experimental，世界 SDK + ABI hash）
- `[MOD]` 标记 + 不计入官方排名
- Vanilla 默认值表（资源 / body / 伤害 / 物流 / 特殊攻击 / Controller / 可见性 / 排行榜 / 新玩家保护）一行一行明确

这是一个非常清楚的「平台默认 vs 模组扩展」分界。一个新玩家加入官方 Vanilla 世界时，规则集是固定的、可学习的、有合同的；想换花样的服主有清楚的 Layer 2/3 通道。这对 long-tail meta 的健康至关重要——避免出现「每个世界规则都不一样，玩家无法迁移经验」的崩盘形态。

### S4 — 新玩家保护从「无」补到 500 tick safe_mode

R1 我把 onboarding 列为 Missing 第 1 项。R2 在 Vanilla Ruleset 里写入：

> 首次 spawn 后 500 tick safe_mode | 房间内无敌，不可被攻击/Claim/Hack

这是必要止血，配合 §3.1a 新手房间分配策略，避免「新手第一分钟被老玩家 rush 出局」的劝退场景。但只是必要不是充分——见 G6（Missing 已部分缩小，但 onboarding 主体仍缺）。

### S5 — Overload 设计合同 + spec 起码在 DESIGN 层对齐

R1 时 Overload 是裸的 fuel 削减，没有可见性约束、没有目标冷却、没有静默语义。R2 的 §8 Overload 行加齐：

- `is_visible_to(target, attacker)` 必要条件
- 50 tick per-target 全局冷却（不限来源）
- 静默返回（不泄露目标 fuel 状态）
- 下限 MAX_FUEL × 0.2

**但 specs/02 §3.12 的实现合同还没跟上 DESIGN**（见 G1）。这是文档同步问题，不是设计问题；不过对评审来说，DESIGN 与 specs 的不一致就是一个真问题。

---

## Concerns（按对实现期影响排序）

### G1 — High — Overload 三件事修了两件半，第三件在 specs/02 仍然漏 fuel 状态

DESIGN.md §8 Overload 行已经写好，但 `specs/02-command-validation-spec.md §3.12` 的拒绝码表仍保留：

```
target_player.fuel_budget > MAX_FUEL × 0.2 → TargetFuelTooLow
```

这是 Speaker R1 报告 B1 的核心 finding——`TargetFuelTooLow` 拒绝码本身就是侧信道：攻击者只要尝试 Overload 就能从 `Accepted` vs `TargetFuelTooLow` 推断目标 fuel ≤ 2M。DESIGN 写「静默返回」，specs/02 写「拒绝码 TargetFuelTooLow」，两者矛盾。任一方实现的引擎都会泄露设计意图反对的信息。

而且 specs/02 §3.12 的校验矩阵（L492）也未列出 `is_visible_to` 与 `target_global_cooldown` 检查，意味着 IDL 校验器未必会在 deploy 时拒绝违反条件的 command。

**建议**：

- specs/02 §3.12 删除 `TargetFuelTooLow` 拒绝码，改为「对已在下限的目标，Overload 静默 noop（仍返回 Accepted）」。
- specs/02 §3.12 校验矩阵补 `visible_target` + `target_global_cooldown` 行。
- specs/08 IDL validator 同步补这两个字段。

修改面积小，但**不修就是 R2 的设计合同被实现层悄悄逆转**。

### G2 — High — 协同 Overload 仍可在 800 tick 内把目标 fuel 打到下限，仅花 4800 Energy

DESIGN 写「per-target 全局冷却 50 tick」，意思是同一目标每 50 tick 接受 1 次 Overload。每次 -500k fuel，从 10M 到 2M 下限需要 16 hits。优化情形（4 个 Overload 攻击者轮流，刚好饱和 50 tick 节奏）：

```
ticks_to_floor    = 16 hits × 50 tick   = 800 tick
energy_cost_total = 16 hits × 300       = 4,800 Energy
```

而 fuel 没有显式恢复机制：specs/02 §7.2 写的 `next_tick_fuel_credit` 是**退款机制**（被拒绝指令的退款，上限 MAX_FUEL × 1.1），不是「降到下限后逐步爬回」的恢复曲线。换句话说，目标一旦被打到 2M（80% 算力被永久压制），他在剩余比赛 / session 时间里都是这个状态，除非攻击者全部停手。

这是一个非对称攻击——攻方付 4800 Energy，使守方在长期内只剩 2M fuel/tick 的算力。在 World 模式（持久）场景下，**4 个攻击者用一台 Forward Depot 就能把一个 RCL7 玩家踩死**。

**建议（按优先级）**：

- 选项 A（最小改动）：明确 fuel budget 的恢复机制——例如「每 tick 自然回升 100k，从下限向 MAX_FUEL 恢复」。这样 16 hits 攻击窗口结束后 80 tick 即恢复，使 Overload 成为短期压制而非长期降维。
- 选项 B：加 per-attacker-pair 累计上限（同一攻防对每 1000 tick 累计扣减 ≤ MAX_FUEL × 50%）。
- 选项 C：把 50 tick 全局冷却放宽到 200 tick（与 drone 冷却对齐），削弱协同攻击。

3 选 1 都可，但**当前合同里「降到下限就停在那里」是错误的稳态**。

### G3 — High — 战斗组合空间仍然不可平衡，reference ruleset 仍是「未来工作」

R1 G3 我提的：6 伤害类型 × 2 层抗性 × 6 特殊攻击 × 11 handler + 自定义 = 指数级平衡空间。R2 没有给出官方校验过的 reference matchup 表——所有 body part / weapon / resistance 数值都是单独定义，没有「这套配置在 100 场对战测试下平衡」的承诺基线。

DSV4 R1 review 也独立得出「策略空间 ~2.6×10^8 种 body 组合」。这种空间不可能靠直觉调平。

**为什么仍然是 P0 阻塞前提**：服主使用 Layer 2 调参时，没有锚点。任何调整都是相对「隐含的官方默认」做 delta，但官方没显式宣称「以下数值经过对战验证」。结果是每个世界的 meta 都是凭直觉收敛，最坏情况下 90% 服都收敛到同一个退化 meta（参见 R4）。

**建议**：

- 在 docs/design/ 下新增 `reference-ruleset.md`（或 `vanilla-balance-targets.md`）：列 8×8 body part vs damage type 的期望胜率矩阵 + 6 种特殊攻击的「典型反制」表。
- 标注每一行的来源：「直觉 / 内部对战 / 公开 PVP 测试」，给玩家与服主一个透明度。
- 这是 P0 还是 P1：取决于 MVP 是否包含 PvP。如果 MVP 含 Arena → P0；如果 MVP 仅 World 且 PvP 大概率不发生 → 可推到 P1。

### G4 — Medium — 累进存储税 30/60/85/100 阈值仍没有模拟支撑

§5.4 写：

```
0–30%   免税
30–60%  0.01% / tick
60–85%  0.05% / tick
85–100% 0.20% / tick
```

R1 我标记这是直觉值，R2 没改。问题不在于值本身好不好，而在于**没有任何人验证过**：

- 中型玩家（典型 60-85% 区间）每 tick 维护费 0.05% × 全局存储 ≈ 几千 Energy/tick——这是否可承受？
- 大型玩家（85-100%）0.20% × 全局存储 ≈ 数万 Energy/tick——是否真的会驱动他卸货？还是因为他已经有大量产出可以覆盖？
- Storage 总容量 100,000 默认值 vs 高 RCL 玩家产出曲线——他们会不会在到税阈值之前就因为别的原因（building cap / drone cap）封顶？

**建议**：

- 实现期跑一次 agent-based 经济模拟（200 tick × 50 agents × 不同档位玩家）。
- 模拟通过/失败标准：85-100% 档玩家在 1000 tick 内能否被驱动到 60-85% 档；中型玩家是否被误伤至流出。
- 在结果发布前，把 30/60/85/100 标记为「pending validation」，不冻结。

这不是阻塞实现的问题，但**在第一次公开测试前必须完成**——否则反垄断机制可能完全失效（大玩家无所谓）或过度伤害（中型玩家被误伤退坑）。

### G5 — Medium — 经济三模式（A/B/C）的认知投放仍然过早

R1 G5。R2 的修复方向是把 Vanilla 锁定为模式 B（轻物流），这是对的（与 GPT G1 / DSV4 G1 全票一致）。但 §5.3 的展示**仍然在第一阶段就把 A/B/C 三模式平铺呈现**。从读者动线看，玩家在读 §5（资源系统）时就被告知有三种模式可选——但 Vanilla Ruleset 在 §5.6（DESIGN 内位置较后）才揭示「默认锁定 B」。

**建议**：

- §5 资源系统的开头，先用一句话锚定「以下默认即 Vanilla 模式 B；模式 A/C 见 §5.x 高级选项」。
- 把模式 A/C 的详细描述移到 §5 末尾的「Advanced Logistics（高级物流）」子节，加 Vanilla/Advanced 标签。

这是文档结构问题，不是设计问题，但它直接影响一个**潜在玩家或服主第一次读 DESIGN 时形成的复杂度认知**。

### G6 — Medium — Hack 的策略价值仍然没有可玩性测试

R1 G4。R2 没改：Hack 5 tick neutral，期间 drone idle、不消耗 lifespan、5 tick 自动归还。我 R1 时建议「砍掉或重设计」，DSV4 cross-review 列为 D2 内部分歧。

我在交叉评审里读到 GPT 的立场（「重命名 Jam/Disable 或区分 temporary/permanent」）和 DSV4 的立场（「保留作为 Psionic 唯一的特殊攻击有体系价值」）。两者都比「直接砍」更建设性，我接受调整为：

**修订建议**（取代 R1 「砍掉」）：

- 不在 Phase 2 删除 Hack。先给一个明确的战术定位：「拖延 / 控场 / 信息获取」三选一。
- 允许攻方在 Neutral 期间对目标 drone 发出 1 条只读命令（如读取目标 inventory），把它从「无操作惩罚窗口」转成「短暂信息获取」。
- 或者把 Neutral 期延长至 20 tick，让攻方有窗口 reposition。
- Vanilla 默认禁用，作为 Advanced ruleset 启用项——让玩家在系统已经稳定后再接触它。
- 实现期做 1 次 internal playtest，如果仍无玩家用，下个版本删除。

### G7 — Low-Medium — Direction 枚举在 specs/08 仍是六边形，破坏 mental model

GPT G9 已经独立指出。我同意：specs/08 IDL 第 42 行：

```yaml
Direction: [Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft]
```

而 DESIGN §3.1a 与 specs/01 都写的是方形房间 + N/S/E/W 出口。这不是技术不一致——对编程游戏而言，**类型系统就是教程的一部分**。SDK 自动补全暴露 6 方向，新手第一小时直接学错地图模型；所有 starter bot / AI docs 都会被污染。

**建议**：

- specs/08 立即统一为 `Direction: [North, South, East, West]`。
- 如果未来要切六边形，反向修改 DESIGN / specs/01 / terrain / pathfinding——不要两套 mental model 并存。

这是一个 5 分钟的修订，**不修就在 IDL 层种下永久 bug**。

---

## Missing（决定首发留存，不阻塞实现启动）

R1 时我列了 4 项 Missing。R2 的进展：

| Missing 项 | R1 | R2 | 备注 |
|---|---|---|---|
| Onboarding（前 30 分钟）| 完全缺失 | 部分（safe_mode + GETTING-STARTED.md） | 仍缺情绪曲线脚本，见 M1 |
| 失败/死亡恢复循环 | 完全缺失 | 仍缺 | 见 M2 |
| 获胜条件 / 长期目标 | 完全缺失 | 仍缺 | 见 M3 |
| Arena 匹配/段位 | 完全缺失 | 仍缺 | 见 M4 |

四项 Missing 中三项进展不大。**这些是首发体验决定项**——骨架可以现在开实现，但这四块如果不在第一个公开版本里至少有 V1，留存曲线会断在第一周。

### M1 — First Hour 情绪/认知曲线（GPT G1 + Claude R1 Missing 合并）

`06-mvp-feedback-loop.md` 和 `GETTING-STARTED.md` 已有功能流程，但缺一条按分钟设计的玩家旅程：

- 0-2 min：spawn + starter bot 自动跑，玩家什么都没改也看到 drone 在工作
- 2-5 min：改一个安全参数（如 spawn_count）立即看到效果——「我能影响系统」的第一次成就感
- 5-15 min：刻意制造一个简单 bug（如 `OutOfRange`），用 `swarm_explain_last_tick` 修复
- 15-30 min：本地 sim 对比两个策略
- 30-60 min：进入 Novice World，达成第一次可分享里程碑（RCL2 / 挡住 scripted raid）

**位置**：在 `docs/design/` 或 `docs/` 下新增 `first-hour-journey.md`，引用现有 §06 与 GETTING-STARTED 的具体功能。GPT 的 5 段式时间线可作为基线。

### M2 — 失败/死亡恢复循环

drone 死光、房间被夺、殖民地全灭——玩家有没有重入路径？现在文档没有合同。Screeps-like 游戏失败成本高，恢复路径不写就是高流失场景：

- 失败原因归类（经济断粮 / 路径拥堵 / 防御不足 / 被 Overload / 补给线断裂）
- Bot Autopsy：自动切出关键 tick + 3 个根因
- Novice rebuild grant：新手首次全灭后给一次受限重建资源
- 保留 colony chronicle / bot lineage（接 M3）

**位置**：新增 `docs/design/failure-recovery-loop.md`，作为 Vanilla 默认体验的一部分。

### M3 — World 长期目标 / 身份体系

World 模式无排行榜（这个决定我同意，理由 §6.6 写得很清楚——持久世界天然不公平），但**没有排行榜就更需要别的长期驱动力**。GPT 的五维体系可以直接借用：

- Competitive：Arena rating / tournament titles / challenge bot records
- Mastery：无 rejection 运行 / energy/tick milestones / sim benchmark
- Creative：公开 world preset / mod preset / starter bot / 教程 replay
- Social：mentor badges / 联盟贡献 / co-op event
- Identity：colony banner / colony chronicle / bot lineage / hall of fame

**最小可行版本**：先做 Identity 维度（数据模型 = colony chronicle + bot lineage 两张表）。其他四维可以后置。

### M4 — Arena 匹配/段位机制

现在 §06 与 §8.6 只写了 Arena 模式的运行时规则（对称起点、赛前锁定、replay 公开）。一个真正可持续的竞技模式还需要：

- Quick match / ranked / custom lobby / tournament 四类入口
- 新手保护 matchmaking（避免第一局对冠军）
- Rating / league / season reset
- Human-written / AI-assisted / fully autonomous AI league 边界

**最小可行版本**：先做 Quick Match + ELO rating + Replay 公开。Tournament / League 可后置。

如果 MVP 含 Arena 但没有这套，**Arena 应降级为「Experimental」入口**而不是与 World 平级展示——避免给玩家一个无法形成稳定对局质量的入口。

---

## Balance Risks（meta 长期演化推断）

### R1（最高）— Overload 仍可在 800 tick 协同打到下限 + 没有 fuel 恢复 → 高 RCL 玩家被压制后无出路

见 G2 数值分析。**修复 G2 是降低 R1 风险的前提**。

如果不修，World 模式中长期 meta：
- 4 人小联盟可专门「打掉一个 RCL6+ 玩家」——花 4,800 Energy，让他剩 80 % 不可用算力
- 被压制玩家失去算力 → 失去防御 → 失去房间 → 失去 Controller → 失去 RCL → 螺旋死亡
- 这反向变成新形态的滚雪球：领先者用 Overload 锁死追赶者，与 R1 时的「资源滚雪球」结构相同，只是换了攻击向量

### R2 — 单资源（Energy）经济下所有 body part 同币种 → 策略空间塌缩

R1 R3 我提的，R2 没改。Vanilla 默认仅 Energy，意味着：

- 所有 body part 成本（Move / Work / Carry / Attack / RangedAttack / Heal / Claim / Tough）都是 Energy
- 没有 trade-off：「我多造攻击 drone vs 多造采集 drone」是同一个 budget 问题
- meta 大概率收敛到「单一最优 body 配比」

**真正的策略深度需要至少 2 种资源 + 差异化成本曲线**：例如 Combat parts 需 Energy + Mineral，Economy parts 仅需 Energy。这强制玩家在「军事产能 vs 经济产能」做真实权衡。

**建议**：Vanilla 默认仍 Energy（认知负担），但 §5.5 加一段「为什么我们仍然认为单资源是临时方案」。在 Phase 2/3 引入第二资源（Crystal / Mineral / 任意）作为 Combat tax。

### R3 — 战斗 meta 大概率收敛到「Tough 堆叠 + 单一最优伤害类型」

R1 R4 我提的，R2 没改（直接对应 G3 reference ruleset 缺失）。如果没有官方校验过的对战矩阵：

- 服主只会在直觉值之间调
- 大部分服主直觉收敛到「攻防平衡」=「数值近似 attack/defense 1:1」
- 玩家直觉收敛到「最便宜的有效防御」= Tough 堆叠
- 攻击端收敛到「能吃掉最多 Tough 的伤害类型」= 单一伤害类型 dominant

最终 meta：所有玩家造 Tough+少量主伤害类型。6 维伤害空间塌缩为 1 维。

**建议**：见 G3。

### R4 — Vanilla Ruleset 八种特殊攻击全部默认开启 → 第一小时认知超载

GPT G4 已经标记。我从平衡角度补充：

- 8 种特殊攻击 × 各自 cooldown / cost / counter → 新玩家无法形成 mental model
- Vanilla 第一小时最该证明的是「代码驱动后勤循环好玩」，不是「特殊攻击表很丰富」
- 一旦新玩家被 Hack/Drain/Overload 打过又看不懂为什么，他不会想「我要学这个系统」，他会退坑

**建议（GPT 方案的修订版）**：

- Tutorial Vanilla：仅 Move / Work / Carry / 基础攻击，无特殊攻击
- Novice Vanilla：Move / Work / Carry / Attack / Heal / Tough + Disrupt / Fortify（防御性的特殊攻击先放）
- Standard Vanilla（当前 §11 的 Vanilla）：8 种全开
- Advanced：Hack / Leech / Fabricate（最复杂的）需用户主动启用

这与 §11 的三层扩展模型不冲突——它是在 Vanilla 内部再做一层「教学曲线」分层。

---

## 实现序列建议（融合三位 designer 意见）

### Phase 0（实现启动前必须）

- **G1 Overload spec 同步**：specs/02 §3.12 删除 `TargetFuelTooLow`，加 visible_target + target_global_cooldown 校验（5 行修改）。
- **G7 Direction 枚举统一**：specs/08 改 N/S/E/W（5 行修改）。

### Phase 1（实现期第一阶段必须到位）

- **G2 Overload 长期压制修复**：fuel 自然恢复机制（选项 A 推荐）。
- **G3 Reference ruleset**：8×8 body × damage 矩阵 + 特殊攻击反制表。
- **M1 First Hour 旅程**：`first-hour-journey.md`。
- **M2 失败恢复循环**：`failure-recovery-loop.md`。

### Phase 2（首次公开测试前）

- **G4 累进税模拟**：agent-based 经济模拟，验证 30/60/85/100 阈值。
- **G6 Hack 重设计**：明确战术定位 + 1 次 internal playtest。
- **M3 长期身份**：先做 Identity 维度数据模型（colony chronicle + bot lineage）。
- **R4 Vanilla 内部分层**：Tutorial / Novice / Standard / Advanced 子集。

### Phase 3（首次公开测试后）

- **R2 第二资源 / 差异化成本**：避免单资源塌缩。
- **M4 Arena 完整运营**：matchmaking + ELO + tournament（如 MVP 含 Arena 则前移到 Phase 1）。
- **G5 经济文档结构调整**：把 A/C 模式移到 Advanced 子节。

---

## 与 Speaker R1 共识报告对齐情况

| Speaker R1 Blocker | R2 状态 | Designer 视角 |
|---|---|---|
| B1 Overload 信息泄露 + 跨文档冲突 | DESIGN 修；specs/02 仍漏 | **G1 仍 High** |
| B2 spectate_delay 强制校验 | DESIGN 改默认；validate_config 仍未写伪代码 | 与 R2-architect/R2-security 高度重合，由其负责优先 |
| B3 命令数量/JSON 限制冲突 | 非 Designer 方向 | — |
| B4 Overload 可见性约束 | DESIGN 已加 | ✅ + DSV4/Claude 补 fuel recovery（见 G2） |
| B5 Vanilla Ruleset 分层 | DESIGN §11 已写三层 | ✅ S3 |
| B6 RCL + Controller | DESIGN 全修 | ✅ S1 + S2 |
| B7 World Topology | 非 Designer 方向 | — |
| B8 Bevy 快照 | 非 Designer 方向 | — |
| B9 Phase 2a/2b | 非 Designer 方向 | — |

R2 在 Designer 方向上推进了 B4 / B5 / B6 三个核心。B1 在 spec 层未完成（G1）。

---

## 最终裁决

**APPROVE_WITH_RESERVATIONS** — 骨架通过，进入实现可以；首发体验不可冻结。

通过条件（必须在第一次公开测试前定型，不阻塞实现启动）：

1. ✅ G1 Overload specs/02 同步（5 行修改，Phase 0）
2. ✅ G2 Overload fuel 恢复机制（Phase 1）
3. ✅ G3 Reference ruleset（Phase 1）
4. ✅ G7 Direction 枚举统一（5 行修改，Phase 0）
5. ✅ M1 First Hour 旅程（Phase 1）
6. ✅ M2 失败恢复循环（Phase 1）

可在实现期并行迭代：

- G4 累进税模拟（Phase 2）
- G5 经济文档结构（Phase 3）
- G6 Hack 重设计（Phase 2）
- M3 长期身份（Phase 2）
- M4 Arena 运营（取决于 MVP 是否含 Arena）
- R2 第二资源（Phase 3）
- R3 Reference ruleset → 见 G3
- R4 Vanilla 内部分层（Phase 2）

R2 相对 R1 的进步是真的。三个我 R1 共识前必修项（G1 RCL / G2 Controller / R2 Overload AI 不对称）全部至少在 DESIGN 层得到修复。但 R2 引入或保留的 4 个体验空洞——如果在第一次公开测试前不补，首发数据会告诉你它们不可忽视。

Final Designer Verdict: **APPROVE_WITH_RESERVATIONS**. 实现可以开工；首发不可冻结。

---

*评审完成时间: 2026-06-16*
*评审员: rev-claude-designer (Claude Opus 4.7) — Game Designer Profile*
*输出: /data/swarm/docs/reviews/R2/rev-claude-designer.md*
