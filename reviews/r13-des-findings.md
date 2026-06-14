# R13 Designer Review — Findings

> 零历史上下文评审。仅审 DESIGN.md + specs/p0/。按严重度排列。

## Critical

**D-C1 特殊攻击 vs 指令排序的不可破解循环（Hack 死锁）**
Hack 成功条件为目标 `hits < hits_max × 0.15` 且需连续 10 tick 维持控制信号（P0-7 §8.2）。但被打到 15% 血量的 drone 在这 10 tick 内极可能被任何攻击补刀致死，或自己逃逸（移动即中断）。在 PvP 中没有任何理性玩家会让一个濒死 drone 在原地停留 10 tick 不动。结果：1000 Energy + 200 tick 冷却 + Claim 部件的投入，成功率近乎为零。Hack 作为设计亮点实际上无法触发——要么放宽条件，要么改触发机制（如施加“控制锁”阻止目标行动）。

## High

**D-H1 RangedAttack 伤害/成本严重失衡**
P0-8 body_cost：RangedAttack=150E vs Attack=80E（近2倍），但伤害 RangedAttack=20 < Attack=30（DESIGN L729-730）。同时 RangedAttack 射程3、近战射程1。花更多钱、伤害更低，唯一优势是射程——这让近战在多数对局中严格占优（在 hex 格只需1步贴脸）。需要给 RangedAttack 加 splash/AOE 或降成本，否则它是死参数。

**D-H2 Heal 跨阵营治疗能恢复但伤害类型无治疗对应**
DESIGN 伤害类型有6种（Kinetic/Thermal/EMP/...），但 Heal 只有单一“反向治疗”12点（L732）。特殊攻击 Debilitate 可叠加易伤、Overload 削 fuel，但没有任何手段恢复被 Drain 的资源或解除 Debilitate 的易伤状态。负面状态只能等自然超时（50 tick），缺少“净化/驱散”反制，防御方策略空间被压缩。

**D-H3 Drone lifespan 续期机制制造退化策略**
占领新 Controller 房间时“最老 50% drone 的 age 重置为 0”，500 tick 冷却（DESIGN L499）。这激励玩家把扩张节奏绑定到续期冷却而非战略需要——周期性占一个垃圾房间纯粹为刷新军队寿命。续期应绑定到持续维持（如每 tick 在控制房间内小幅回age），而非一次性占领事件，否则产生“占领-放弃-再占领”的刷新 farming。

## Medium

**D-M1 MoveTo 的 InsufficientMoveParts 与疲劳模型冲突**
P0-2 §3.2 要求 `MOVE 部件数 ≥ 路径长度`，但 Screeps 系疲劳模型本应是“MOVE 抵消身体重量、疲劳逐 tick 恢复”。把 MOVE 数硬性 ≥ 路径长度意味着跨 50 格需 50 个 MOVE 部件（超 MAX_BODY_PARTS=50），长途 MoveTo 在物理上不可能。MoveTo 的多 tick 移动语义与单 tick 校验未对齐。

**D-M2 资源争用对 Heal/Attack “全部执行”可被滥用**
P0-1 §3.2：攻击/治疗同一目标“全部执行”。配合种子洗牌的不可预测顺序，focus-fire 是确定的，但治疗方无法保证治疗在伤害“之后”结算——同 tick 内 combat_system 一次性结算，治疗与伤害的先后取决于 ECS 系统顺序（combat 在 decay 前，但 heal 也在 combat 内？规范未明确 heal 与 damage 在 combat_system 内的相对顺序）。需明确战斗内子结算顺序。

**D-M3 教程世界与正式世界技能不迁移的断层**
P0-6 教程用 1s tick、引导式代码修改，但正式 World 是 3s tick + 完整 fog_of_war + 经济维护费。教程覆盖的概念（spawn/harvest/tower）完全没触及物流模式（全局/本地存储）、维护费、可见性分层——新手从教程毕业后会撞上一堵复杂度墙。教程缺少“硬核物流”和“empire-upkeep”的渐进引导。

**D-M4 Arena 对称性与自定义资源类型未约束**
Arena 强调“对称初始条件”，但 world.toml 可定义任意 resource_types/damage_types/mods。规范未说明 Arena 是否锁定为标准资源集——若允许非对称资源定义或不平衡 mod，Arena 的公平性承诺落空。需要 Arena 模式的“规则白名单/对称校验”。

## Low

**D-L1** Controller 升级表（DESIGN L209-218）RCL7/8 均为 500 drone 硬上限，但 RCL 解锁“最大房间 drone”逐级提升的意义在 L7 后消失——晚期房间扩张激励不足。

**D-L2** `repair_per_hit = { Energy: 1 }` 与建筑 hits_max 未给量级，无法判断维修经济是否合理（Tower 自动攻击50/tick，维修1E/hit 是否跟得上需数值验证）。

**D-L3** Fortify “所有抗性 ×0.5”持续100 tick、冷却300 tick——覆盖率33%，但与 Tough 部件的固定减伤如何叠加（组件×属性）可能产生 0.25 倍叠加，配合 immune 机制需确认无“近乎无敌”组合。
