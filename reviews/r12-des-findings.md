# R12 Designer Reviewer — Stage 1 Findings

零历史上下文评审。方向: Game Designer。聚焦平衡性、玩家体验、涌现玩法与退化策略。

## D-CRITICAL

**D1. Hack 与「代码即军队」哲学冲突 (DESIGN §8.7 特殊攻击表)**
Hack「夺取目标 drone 控制权」根本性破坏核心模型。所有 drone 行为来自所有者部署的 WASM——被夺取后它执行谁的代码？若仍跑原 WASM，则「控制权」无意义；若改跑攻击者代码，则攻击者无法为单个敌方 drone 编写代码（部署是玩家级的）。机制未定义、与设计原则矛盾。建议改为「禁用/转中立/限时瘫痪」等可实现语义。

**D2. Overload 可造成不可恢复锁死 (DESIGN §8.7)**
Overload 削减目标 *玩家级* fuel budget 500k。多个 Overload drone 叠加可将对手 fuel 清零→对手 WASM 无法运行→无法响应→更易被继续 Overload。这是自我强化的死亡螺旋 + griefing 向量。需设 fuel 削减下限（如永不低于 MAX×30%）或改为针对单 drone 而非玩家全局。

## D-MAJOR

**D3. 续期机制使 lifespan 形同虚设 (DESIGN §8 Drone 生命周期)**
占领新 Controller 重置全军 age=0，冷却仅 500 tick，而 lifespan=1500。扩张型玩家每 ~500 tick claim 一个弃用房间即可循环重置，老化约束对积极玩家失效，仅惩罚龟缩新手。建议：续期改为部分重置（如 age×0.5）或冷却 ≥ lifespan。

**D4. 特殊攻击命中判定未定义 (DESIGN §8.7 通用规则)**
「取决于 body part 数量与目标防御的差值」无具体公式。Disrupt 仅 100 Energy / 50 tick 冷却即可打断 Drain/Hack（200-500 Energy 持续动作），成本极不对称，可能使所有 channeled 攻击废弃。需给出可平衡的数值模型与成功率曲线。

**D5. 同 tick 资源争用以 seeded shuffle 决胜 (DESIGN §3.2 EXECUTE)**
「先到先得」由 hash(tick, seed) 洗牌顺序决定，而非玩家决策。与「胜负取决于算法思维而非手速/运气」(§1.1) 的核心承诺张力明显——近距离争夺源点/战斗结果带随机性。建议明确：争用是否可被玩家策略（优先级、预测）影响，或在文档中坦承这是公平随机仲裁。

## D-MINOR

**D6. 新手断崖 (P0-6 §2)**
教程止于「改一个变量」，正式游戏要求手写+编译 WASM，中间无过渡。对非程序员是陡坡。建议 starter bot 之上加「配置式 bot」(参数化预制策略) 作为缓冲层。

**D7. 离线衰减导致挂机即流失 (DESIGN §8 + empire-upkeep)**
World 持久世界中 drone 75min 死亡 + 超线性维护费，玩家睡觉时殖民地若代码不够自治则持续萎缩。这是设计意图但对休闲玩家留存不友好。建议 World 默认提供「休眠保护」可配置项。

**D8. 本地存储完全隐匿削弱侦察反制 (DESIGN §8 反制机制 2)**
硬核物流模式 + 本地存储完全私有，敌方经济实力完全不可知。情报玩法缺失可读性。建议侦察/占领可揭示存储估值区间。
