# R44 Design-Economy Review — gpt-5.5

Reviewer: rev-gpt-design-economy
Scope: Gameplay coherence, UX design quality, economy intuition, resource flow, maintenance curve, anti-snowball, learning curve, player motivation.
Documents reviewed: all markdown documents under `/data/swarm/docs/`, excluding `/data/swarm/docs/reviews/` per task rule.

## 1. Verdict

REQUEST_MAJOR_CHANGES

核心玩法方向是成立的：Swarm 的“代码即军队”、World/Arena 双模式、Resource Ledger 单入口、maintenance curve、soft_launch、经济反馈仪表盘等构成了有潜力的 MMO-RTS 设计。但当前文档存在多处会直接改变玩法体验和经济平衡的 canonical 冲突：默认经济到底是单 Energy 还是 Energy+Matter、World/Arena 可见性、特殊攻击参数/抗性/冷却、建筑成本与 RCL 解锁、初期保护时间与 10 分钟/first-hour 承诺均不一致。作为目标状态文档，这些不是实现细节问题，而是玩家学习路径、策略空间和经济曲线的阻塞性歧义。

---

## SS1 Critical Findings (blockers)

### SS1-1 [Critical] Vanilla 默认经济在“单 Energy”与“Energy+Matter 多资源”之间冲突，导致上手、starter bot、Fabricate 与 balance sheet 无法同时成立

文件引用：
- `/data/swarm/docs/design/gameplay.md:519-523`：Vanilla Ruleset 声明资源为单一 `Energy`，并说明 Tutorial/Novice 禁用 special action、Standard/Arena 全量启用。
- `/data/swarm/docs/specs/core/resource-ledger.md:124-127`：Standard 初始资源包为 `{Energy: 5000}`，free upkeep 参数以单 Energy 经济为基础。
- `/data/swarm/docs/design/economy-balance-sheet.md:33-39`：收支平衡表假设 Source income、Controller income、PvE drop 均用 Energy 表达。
- `/data/swarm/docs/specs/core/world-rules.md:43-70`：`world.toml` 示例却定义 `Energy` + `Matter` 两种默认资源，`starting_amount = 1000/500`，`spawn = { Energy = 200, Matter = 50 }`，body part 与 Tower 也消耗 Matter。
- `/data/swarm/docs/specs/reference/special-attack-table.md:26`：Fabricate 消耗 `2000 Energy + 500 Matter`，而 Standard/Arena 全量启用 special attack。

问题描述：
Vanilla/Standard 的默认经济在多个核心文档中被定义成单 Energy，但 `world-rules.md` 的配置 schema 示例和 canonical-looking 默认配置引入 Matter，且 Fabricate 依赖 Matter。若 Standard 只有 Energy，Fabricate 在默认 Standard/Arena 中不可支付；若 Standard 有 Matter，则所有 balance sheet、starting resources、starter bot、10 分钟 Golden Path 都低估了复杂度并缺少 Matter faucet/sink/UX 教程。

影响分析：
- 新手学习曲线断裂：文档承诺“无需配置即可开始”的 Vanilla 单资源体验，但默认 schema 暗示玩家必须理解双资源。
- 经济模型不可重算：maintenance curve、2-10 房间自维持区间没有把 Matter 的采集、存储、转换、税、PvE 掉落纳入账本。
- special attack 策略空间失真：Fabricate 是 8 个 Standard special attack 之一，但在单 Energy 默认世界中会成为不可用 action，破坏“Standard 全量启用”的承诺。
- starter bot 与 tutorial 风险：basic-harvester / tower-defense 若按 Energy-only 写，面对 Matter-gated spawn/build 会失败或偏离 Golden Path。

修复建议：
1. 明确 Vanilla/Novice/Standard/Arena 默认资源只保留 `Energy`，将 `Matter` 示例移动到“mod/advanced world 示例”，并在 `world-rules.md` 中显式标注“非 Vanilla 示例”。
2. 若坚持 Fabricate 需要 Matter，则必须把 Matter 提升为 Vanilla 默认资源：补齐 Source、starting resources、transfer fee、storage tax、PvE drop、starter bot、tutorial 和 balance sheet。基于当前学习曲线目标，我建议选择 Energy-only，并将 Fabricate 成本改为纯 Energy 或引用 ActionRegistry 中的 world-configurable cost。
3. `specs/reference/special-attack-table.md` 对 Fabricate cost 改成与 Vanilla resource model 一致；若 Matter 是 mod-only，则 Fabricate 在 Vanilla 的 cost 不应包含 Matter。
4. 在 `Resource Ledger §2.1` 增加“Vanilla resource set = Energy-only；multi-resource worlds are advanced/modded”一句，避免后续漂移。

### SS1-2 [Critical] 初期时间曲线把“10 分钟 Golden Path / First-Hour 过渡 / 100 分钟保护期 / 7.5 分钟亏损缓冲”混在一起，形成新手经济悬崖

文件引用：
- `/data/swarm/docs/design/gameplay.md:5-26`：10 分钟 Golden Path 要求登录到首个 PvE 击杀 ≤10 分钟。
- `/data/swarm/docs/specs/core/world-rules.md:25`：World `tick_interval_ms = 3000`，即 1 tick = 3 秒。
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:83-92`：First-Hour 过渡写成 Tick 0-500 safe_mode、500-2000 soft_launch、2000+ 正常 PvP。
- `/data/swarm/docs/design/gameplay.md:528-530`：Vanilla 默认首次 spawn 后 500 tick safe_mode，safe_mode 后 1500 tick soft_launch。
- `/data/swarm/docs/design/economy-balance-sheet.md:191-197`：free_upkeep 结束后 1 房净亏 -33/tick，初始 5000 Energy 只能覆盖约 151 tick。
- `/data/swarm/docs/specs/core/resource-ledger.md:137-144`：Growth Path 又声称 tick 2000+ Full economy “自维持”，但前文经济表要求玩家此时已有 ≥2 rooms + 5 drones + 完整 faucet 管道。

问题描述：
按 `tick_interval_ms = 3000` 计算，500 tick = 25 分钟，1500 tick = 75 分钟，safe+soft_launch = 100 分钟，不是 “First-Hour”。同时，free_upkeep 在 tick 2000 到期，PvP 也在 tick 2000 开启；若玩家仍是 1 房，5000 Energy 只覆盖 151 tick ≈ 7.55 分钟亏损。也就是说，新手在保护结束时同时面对 PvP、维护费恢复、经济亏损和可能的扩张失败惩罚。

影响分析：
- 新手动机模型有断崖：10 分钟内能完成教程/PvE，但真正进入 World 后 100 分钟才 PvP，期间可能体验真空；若没有完成扩张，又在保护结束后数分钟内资源枯竭。
- 玩家目标不清：文档要求“首小时过渡”，但实际设计是 100 分钟；这会影响 tutorial pacing、UI 提醒和服务器默认 tick 选择。
- 经济 anti-snowball 与 onboarding 冲突：maintenance curve 本来用于限制大帝国，却在新玩家第一个转折点制造硬性扩张 check。
- PvP 开启与 upkeep 到期同 tick 发生，会让老玩家首攻、经济亏损和调试压力叠加，违背 soft_launch 渐进过渡意图。

修复建议：
1. 所有 onboarding 表格同时写 tick 与真实时间，并以 `tick_interval_ms` 派生，不只写 tick。
2. 将 safe_mode / soft_launch / free_upkeep 解耦：free_upkeep 不应与 Full PvP 同 tick 到期。建议 free_upkeep 至少覆盖 soft_launch 后的一个适应窗口，或让 Standard 1-room 在 free_upkeep 后不立即净亏到死亡螺旋。
3. 明确 10 分钟 Golden Path 只适用于 Tutorial 世界，World Standard 的 first-hour 目标另列，避免把 Tutorial pacing 套到持久世界经济。
4. 对 `1→2 rooms transition` 增加失败恢复机制：例如首次 expansion refund、delayed upkeep ramp、或 RCL2 前维护费渐进爬坡，而不是 2000 tick 一次性恢复全维护费。

### SS1-3 [Critical] Special attack canonical 参数在多个文档互相冲突，直接破坏 counterplay 与策略空间

文件引用：
- `/data/swarm/docs/specs/reference/special-attack-table.md:14-26`：canonical table 声明 11 个 vanilla action 的 body part、resistance、cost、cooldown、range、counterplay。
- `/data/swarm/docs/design/gameplay.md:741-750`：Gameplay 中重新列出 Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate 参数。
- `/data/swarm/docs/design/gameplay.md:1048-1096`：同一文件的 `[[special_effects]]` 又给出另一组 resistance；例如 Debilitate resistance = Kinetic，Leech resistance = Corrosive。
- `/data/swarm/docs/specs/core/world-rules.md:657-685`：World Rules 也把 Debilitate resistance 写为 Kinetic，Leech resistance 写为 Corrosive。
- `/data/swarm/docs/specs/core/world-rules.md:877-886`：World Rules 的特殊攻击表中 Leech cooldown = 100 tick、Fabricate cost = `2000E + 500 Matter`。
- `/data/swarm/docs/design/gameplay.md:749`：Gameplay 表中 Leech cooldown = 150 tick。
- `/data/swarm/docs/specs/reference/special-attack-table.md:21-25`：Canonical 表中 Overload range = 5 LOS、Debilitate resistance = Corrosive、Leech resistance = Kinetic、Leech cooldown = 100。

问题描述：
特殊攻击是 Standard/Arena 的核心策略层，但同一 action 的抗性、冷却、range、cost、counterplay 在 design/gameplay、world-rules、special-attack-table 之间不一致。最严重的是 resistance 归属：Debilitate 到底被 Corrosive 还是 Kinetic 抵抗、Leech 到底被 Kinetic 还是 Corrosive 抵抗，会改变 body composition、Fortify 价值和战斗 meta。

影响分析：
- 玩家无法形成可学习的 counterplay mental model：同一技能在不同文档里有不同弱点。
- AI agent 生成策略会错误优化，例如针对 Debilitate 堆错抗性。
- Arena 公平性受损：若 SDK/API 以 canonical table 生成，而教程/文档描述另一套参数，玩家会以错误直觉参赛。
- 经济消耗不可平衡：Fabricate 的 Matter cost、Leech cooldown、Overload global/per-drone cooldown 都影响资源 sink 与战斗节奏。

修复建议：
1. 保留 `/specs/reference/special-attack-table.md` 为唯一参数表；其他文档只保留概念描述和链接，不得重新声明冷却、cost、resistance、range。
2. 在 `design/gameplay.md` 和 `world-rules.md` 中删除重复数值表，改成“参数以 special-attack-table.md 为准”。
3. 若需要示例 TOML，也应从 canonical table/codegen 生成，避免手写漂移。
4. Fabricate 的 resource cost 必须与 SS1-1 的 Vanilla resource model 同步。

### SS1-4 [Critical] 建筑列表、成本和 RCL 解锁不一致，导致 progression 与 economy balance sheet 不可实施

文件引用：
- `/data/swarm/docs/design/gameplay.md:112-229`：默认世界提供 13 种基础结构；PowerSpawn cost = 5000，Nuker cost = 100000，Depot cost = 5000；没有 Road/Wall/Rampart/Container。
- `/data/swarm/docs/specs/core/world-rules.md:439-588`：默认结构包含 Road/Wall/Rampart/Container；PowerSpawn cost = 1200，Nuker cost = 5000，Depot cost = 600。
- `/data/swarm/docs/specs/core/world-rules.md:610-619`：RCL 表在 RCL2 解锁 Road/Container，RCL3 解锁 Depot，RCL8 解锁 Nuker。
- `/data/swarm/docs/design/gameplay.md:222-228`：Depot `rcl_required = 2` 且 cost = 5000。
- `/data/swarm/docs/design/economy-balance-sheet.md:31-199`：balance sheet 只按 room/source/controller/maintenance 建模，没有把低价 Depot/Container/Road 或高价 Nuker/PowerSpawn 的差异纳入 progression。

问题描述：
同一 Vanilla 默认世界的建筑 roster 和成本在 design 与 spec 中差异巨大。Depot 在 gameplay 是 RCL2、5000 Energy 的战略前线节点；在 world-rules 是 RCL2/3 周边、600 Energy 的早期维修节点。Nuker 从 100000 降到 5000，PowerSpawn 从 5000 降到 1200，完全改变 late-game sink 与目标追求。

影响分析：
- Progression 曲线无法评审：RCL2/3 到底是解锁轻物流、道路、容器，还是昂贵前线维护节点，会改变 2-5 房自维持难度。
- Economy sinks 严重错位：Nuker 100000 是终局资源目标；5000 则只是中期可支付建筑。两者对应完全不同的长期动机。
- Depot 成本决定前线战争节奏：600 Energy 会让前线 repair 网络早期普及，削弱“物流是玩法”的权衡；5000 Energy 则是明确战略投资。
- 新手教程和 starter bot 不知道应该教哪些建筑。

修复建议：
1. 设定单一 canonical structure table（建议在 API Registry 或 world-rules 生成表），并让 design/gameplay 只引用。
2. 明确 Depot 的目标定位：若是“前线战略节点”，成本应与该定位匹配；若是“早期轻维修节点”，则需要重新评估 anti-snowball 与 age repair 拥堵。
3. 为 Road/Wall/Rampart/Container 决定是否属于 Vanilla 默认；若属于，必须加入 gameplay 的结构列表、10 分钟/first-hour 教程、balance sheet 与 RCL progression。
4. 将 Nuker/PowerSpawn 这类 late-game sinks 纳入 long-term goals 与 economy-balance-sheet 的高房间阶段说明。

---

## SS2 Design Tensions (inconsistencies, conflicts)

### SS2-1 [High] Arena fog-of-war / player_view 规则冲突，可能让 Arena 从“算法对抗”变成全图信息优化题

文件引用：
- `/data/swarm/docs/design/gameplay.md:525`：核心默认值声明可见性为 `fog_of_war = true`, `player_view = drone`, `public_spectate = false`。
- `/data/swarm/docs/design/gameplay.md:1236-1241`：竞技观战示例写 `fog_of_war = true`, `player_view = drone`，通过 `public_spectate + spectate_delay` 观看延迟全图。
- `/data/swarm/docs/specs/core/world-rules.md:316-326`：World vs Arena 默认值表写 Arena `visibility.fog_of_war = false（全场可见）`。
- `/data/swarm/docs/design/modes.md:146-149`：Arena 赛后回放支持双视角切换和公开访问。

问题描述：
Arena 的 drone 感知到底是 fog-of-war 还是全图可见不一致。若 `fog_of_war=false` 作用于 WASM snapshot，Arena 策略会从侦察/信息不完全博弈变成全图最优化，削弱 scout、Observer、隐蔽路径、伏击等玩法。

影响分析：
- Arena 公平性不是问题，但策略深度会被压缩：对称全知只测试宏观优化和战斗微操，不测试侦察与 deception。
- World 与 Arena 技能迁移变差：World 需要 fog-of-war 策略，Arena 练出来的全知算法不适用于 World。
- 观战需求与 gameplay 感知被混淆：观众延迟全图不等于参赛 WASM 全图。

修复建议：
将 Arena 拆成两层默认：`drone_fog_of_war = true`（参赛 WASM 输入受限）与 `spectator_view = delayed_full`（观众/赛后回放可全图）。如果需要 full-information Arena，作为房间配置变体显式标注，不作为默认。

### SS2-2 [High] Allied Transfer 的 anti-snowball 约束分散，联盟级 cap 与拦截玩法未进入 Resource Ledger 权威参数表

文件引用：
- `/data/swarm/docs/specs/core/resource-ledger.md:73-78`：定义 `allied_transfer_fee/delay/cooldown/daily_cap`。
- `/data/swarm/docs/specs/core/resource-ledger.md:173-178`：Allied transfer 附加约束只包含联盟时长、新玩家锁、cooldown、daily cap。
- `/data/swarm/docs/design/gameplay.md:1741-1747`：外交安全写多联盟上限、`alliance_transfer_cap_per_tick`，但该行存在乱码且没有进入 ledger 参数表。
- `/data/swarm/docs/specs/core/snapshot-contract.md:208-222`：Restricted Allied Transfer 描述了 fee/delay/cooldown/daily cap，但没有 alliance-level throughput cap。
- `/data/swarm/docs/specs/core/snapshot-contract.md:224-270`：延迟 transfer 可被拦截，成功率 60% + part bonus - escort penalty。

问题描述：
设计意图是联盟转移可用但受限，防止大联盟绕过 anti-snowball。但“同一 tick 内同一 alliance 的总流量 cap”只出现在 gameplay 的外交段落，未进入 Resource Ledger 的权威参数表，也未出现在 snapshot-contract 的 Restricted Allied Transfer。拦截机制虽然有策略潜力，但它改变 GlobalDeposit/Withdraw/AlliedTransfer 的风险收益，却也不在 Resource Ledger §2 统一参数中体现。

影响分析：
- 大联盟可通过多发送方、多接收方、多联盟边绕开 per-receiver daily cap，形成资源集中策略，削弱 maintenance curve 的自然天花板。
- 拦截风险对物流模式 B 的玩家体感很重要；若 UI/经济表未呈现“运输中风险”，玩家会把 1%/5% fee 理解成唯一成本。
- Standard 默认 allied transfer enabled + restricted + intercept enabled 是强玩法承诺，分散定义会让实现或玩家文档漏掉关键约束。

修复建议：
1. 将 `alliance_transfer_cap_per_tick`、alliance aggregate daily cap、multi-alliance anti-circumvention 写入 Resource Ledger §2.1 统一参数表。
2. 在 Economy Balance Sheet 的模式差异中增加 AlliedTransfer 风险/吞吐维度，而不只写 enabled/disabled。
3. 为 transfer intercept 增加玩家可读 UX 规则：运输路线/目的房间提示、escort 推荐、拦截事件解释，否则它会成为“资源消失的黑箱”。

### SS2-3 [High] New Player Transfer Lock 的语义在 send-only 与 send+receive 之间冲突，影响 smurf 防护和新手互助

文件引用：
- `/data/swarm/docs/design/gameplay.md:413-419`：限制表写“新玩家在前 N tick 不得向其他玩家 transfer 资源”，描述偏 send-only。
- `/data/swarm/docs/specs/core/resource-ledger.md:93`：`new_player_transfer_lock` 写“禁止发送与接收”。
- `/data/swarm/docs/specs/core/resource-ledger.md:129-134`：反 smurf 约束明确新身份不得发送，也不得接收资源。
- `/data/swarm/docs/specs/core/resource-ledger.md:171`：锁覆盖 AlliedTransfer、本地 player transfer、ContractSettlement RFC，不影响自身 local↔global。
- `/data/swarm/docs/specs/core/snapshot-contract.md:219`：Restricted Allied Transfer 表只写“新玩家禁止接收任何转移”。

问题描述：
同一机制在 design/gameplay 是 send-only，在 resource-ledger 是 send+receive，在 snapshot-contract 是 receive-only。三者对应完全不同的社交经济：send-only 允许老玩家资助新人；receive-only 防止老玩家 funnel 到新号；send+receive 则防 smurf 最强但牺牲新手互助。

影响分析：
- 新手动机模型不同：允许接收援助会增强社交 onboarding；禁止接收会保护经济但让 friend onboarding 更孤立。
- Smurf 防护不同：只禁发送无法防老号把资源灌给新号；只禁接收无法防小号打金后转出。
- Allied/contract/future economy surfaces 都依赖该语义，必须唯一。

修复建议：
采用 Resource Ledger 的 send+receive 作为 canonical（最符合 anti-abuse），并在 gameplay/snapshot-contract 中同步措辞。同时给新手互助另设非资源型渠道：tutorial mentor、replay/code sharing、Arena challenge、非资源 bounty point，而不是直接资源资助。

### SS2-4 [Medium] “playtest-gated” 项中仍有玩家可理解性缺口，尤其 storage tax 与 PvE 收益定位

文件引用：
- `/data/swarm/docs/specs/gameplay/PLAYTEST-GATED.md:59-72`：PG-3 明确缺少 bp/tick 的 per-hour/per-day 人类可读单位、PvE 阶段收入表、1% vs 5% 费率解释、storage tax 资源流失曲线。
- `/data/swarm/docs/design/gameplay.md:338-363`：Progressive Storage Tax 只给锚点概念和默认表。
- `/data/swarm/docs/specs/core/resource-ledger.md:96-112`：存储税公式精确但以 ppm/bp/tick 表达。
- `/data/swarm/docs/design/economy-balance-sheet.md:93-117`：个别 storage tax 数值给出 tick 级结果，但没有转成人类时间尺度或 UX warning 阈值。

问题描述：
存储税和 PvE faucet 在公式层足够精确，但玩家理解层仍不足。作为设计目标文档，不应只把“可理解性”留给 playtest 之后；至少需要目标状态下 UI 如何解释税、PvE 在 early/mid/late 的定位、何时建议玩家转本地/消费/扩张。

影响分析：
- 玩家会把 storage tax 视为惩罚而非战略权衡，尤其当 bp/tick 放大到小时/天后可能非常显著。
- PvE 的定位不清：catch-up、risk/reward、skill test、还是主经济来源？不同定位会改变玩家动机和 World 生态。
- AI agent 可通过公式优化，但人类玩家缺少直觉，会扩大 AI vs human 体验差距。

修复建议：
在 `economy-balance-sheet.md` 增加“Player-facing economy intuition”小节：把 30/60/85/100% storage utilization 转换为每小时/每天损耗示例；给 early/mid/late PvE 收益占比目标；解释 1% deposit / 5% withdraw 的设计理由（防即时前线补给、鼓励本地规划）。

### SS2-5 [Medium] MCP onboarding 文档仍使用“可用动作”语言和过期 action 名称，弱化“代码即军队”的核心哲学

文件引用：
- `/data/swarm/docs/design/interface.md:47-49`：明确 MCP 不做游戏动作，AI 必须编写 WASM。
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:45-50`：AI 教程步骤包含 `swarm_get_available_actions`，描述为“了解可用的游戏 API 函数”。
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:187`：Starter bot CI 示例提到 `MoveTo`，但 `design/interface.md:117-119` 明确 Move 是 4方向，8方向/MoveTo 为 Out-of-Scope RFC。
- `/data/swarm/docs/specs/gameplay/feedback-loop.md:193-198`：`swarm_get_available_actions` 被描述为“我现在能做什么？返回当前状态下的可能动作列表”。

问题描述：
MCP onboarding 虽然多次声明 AI 不直接操作 drone，但 `available_actions` 与 `MoveTo` 的措辞容易让玩家/agent 误以为 MCP 提供实时动作选择，而不是 SDK/IDL 能力发现与 WASM 代码生成。

影响分析：
- AI agent 可能尝试把 MCP 当 controller，而不是编译部署 WASM，破坏核心学习路径。
- 人类玩家也会误解 AI 是否有“外挂机械臂”式优势。
- 过期 action 名称会导致 starter bot smoke test 与 IDL 不一致。

修复建议：
将 `swarm_get_available_actions` 重命名/解释为 `swarm_get_available_action_schema` 或“当前世界 ActionRegistry/Command schema 能力发现”，明确它不返回可执行动作列表。删除 `MoveTo` 示例，改为 IDL 当前 canonical `Move` 或路径规划 helper（SDK 本地函数，不是 CommandAction）。

---

## SS3 Suggestions (improvements, simplifications)

### SS3-1 [Medium] 为 2-10 房间自维持曲线增加“玩家选择分岔”而不仅是单一效率乘数

文件引用：
- `/data/swarm/docs/design/economy-balance-sheet.md:175-199`：自维持区间依赖 1.5x-2.0x 代码效率、RCL、PvE 补充。
- `/data/swarm/docs/design/gameplay.md:441-453`：长期目标系统列出殖民地年龄、GCL/RCL、Arena 段位、PvE 里程碑、Replay 声誉。

问题描述：
当前中期经济主要用“代码效率乘数”解释正流量。这对 AI/code 玩家合理，但策略空间可以更丰富：玩家应该能在扩张、RCL 深耕、PvE 风险收益、联盟物流、本地隐匿存储之间形成不同 viable builds。

建议：
在 balance sheet 增加 2-10 房间的 3 条 archetype 曲线：
- Tall RCL：少房间高 RCL、低 maintenance、高 controller income。
- Wide Harvest：多房间 source 并行、高 logistics/upkeep。
- PvE Raider：中等房间 + 高 combat sink + PvE faucet。
这样比单一“优化代码 ×1.5/2.0”更能体现 emergent strategy。

### SS3-2 [Medium] 为 Depot/Controller age repair 增加玩家可读的拥堵反馈

文件引用：
- `/data/swarm/docs/design/gameplay.md:102`：Controller/Depot 维修受 range/capacity/queue 限制，大量 drone 排队形成物流拥挤。
- `/data/swarm/docs/design/engine.md:531-542`：Controller repair 公式与物理约束。
- `/data/swarm/docs/design/gameplay.md:1795-1841`：经济反馈循环已有 idle、净流入、storage tax、建筑 HP 告警。

问题描述：
age repair 是很好的 anti-hoarding 和 logistics 机制，但反馈循环没有明确展示“维修队列长度、预计等待 tick、Depot 资源耗尽时间”。玩家可能只看到 drone 老化死亡，而无法理解是 repair queue 饱和还是 depot logistics 失败。

建议：
在 `swarm_get_economy` 或 `swarm_get_drone_efficiency` 增加 maintenance/repair subsection：repair queue length、avg wait tick、depot stockout ETA、drones aging beyond threshold。Web UI 在 Controller/Depot 上显示队列环或拥堵图标。

### SS3-3 [Low] 将 Tutorial/Novice/Standard/Arena 的“允许 special action”做成一张玩家可见解锁表

文件引用：
- `/data/swarm/docs/design/gameplay.md:752-761`：Tutorial/Novice 禁用 special，Standard 全量启用，Advanced 加 mod action。
- `/data/swarm/docs/specs/reference/special-attack-table.md:10`：Standard/Arena 全量启用，Tutorial/Novice 可通过 allowlist 覆盖。

问题描述：
特殊攻击数量多、反制关系复杂，是专家深度来源。但新手需要知道自己为什么看不到这些 action、什么时候会出现。

建议：
保留渐进解锁设计，并在 UI/SDK docs 输出 `world_action_manifest` 时展示：Locked because world tier = Novice / Enabled in Standard / Modded action. 这能让禁用不是“缺功能”，而是清晰的学习曲线。

### SS3-4 [Low] World PvE 的地理难度梯度很好，但需要标注新手出生与高 Zone 的空间距离保证

文件引用：
- `/data/swarm/docs/design/modes.md:71-83`：PvE 难度随房间距世界中心越远提高。
- `/data/swarm/docs/design/gameplay.md:434-435`：安全区出生，密度优先 + 反包围。

问题描述：
PvE 地理梯度能自然驱动探索，但如果新手出生点与世界中心/Zone 关系不清，会出现新手直接落在高威胁区或老玩家围堵低威胁区的风险。

建议：
在 spawn policy/安全区章节增加 Zone placement contract：新玩家默认出生在 Zone 1/2 边界内，周边 N 房间不生成 Guardian/Ruin，soft_launch 事件只使用 T1/T2 PvE。

---

## 3. 亮点

1. Resource Ledger 单入口设计很强：`LocalTransfer / GlobalDeposit / GlobalWithdraw / AlliedTransfer / PvEAward / RecycleRefund / BuildCost / SpawnCost / UpkeepDeduction / StorageTax` 统一审计，能支撑玩家信任、replay 和经济调参。

2. 维护费 O(n²) + storage tax + local/global logistics 的组合比单一税率更有策略深度。它不是简单惩罚大玩家，而是鼓励在“扩张、效率、本地隐匿、物流规划”之间权衡。

3. Tutorial → safe_mode → soft_launch → staged PvP 的意图正确。First-Attack Shield、PvE-only 期、PvP 警告广播都服务于“从学习到真实冲突”的心理过渡，只需要时间/经济参数对齐。

4. World 与 Arena 的产品定位清晰：World 是持久沙盒，不追求公平；Arena 是算法对抗、对称起点、赛后回放。这能同时服务 MMO 玩家和策略算法玩家。

5. 经济反馈循环设计到位：`swarm_get_economy`、efficiency dashboard、idle warning、storage tax warning、net flow 预测都能显著降低“代码游戏”的黑箱感。

6. Depot/Controller age repair 是优秀的 anti-snowball 机制：用空间、队列和物流拥堵限制兵力囤积，比抽象全局 cap 更有可玩性，也能产生打击补给线的战术目标。

7. 受限 Allied Transfer + intercept 的方向有趣：既保留联盟协作，又避免联盟仓库直接变成无风险资源瞬移。若同步到 ledger 与 UI，会形成很好的护航/伏击/补给博弈。

8. “人格只影响表现、不影响数值”的选择正确：增强情感连接但避免 roll 出强人格造成经济/战斗优势。

---

## SS4 Cross-Reference Matrix

| ID | Finding | Primary files | Severity | Required action |
|---|---|---|---|---|
| SS1-1 | Vanilla resource model conflicts with multi-resource examples and Fabricate Matter cost | `design/gameplay.md`, `specs/core/world-rules.md`, `specs/core/resource-ledger.md`, `specs/reference/special-attack-table.md`, `design/economy-balance-sheet.md` | Critical | Choose Energy-only vs multi-resource Vanilla; sync all costs, starter bots, balance sheet |
| SS1-2 | New-player time/economy curve creates 100-minute protection but 7.5-minute post-upkeep deficit cliff | `design/gameplay.md`, `specs/gameplay/feedback-loop.md`, `design/economy-balance-sheet.md`, `specs/core/resource-ledger.md`, `specs/core/world-rules.md` | Critical | Express real time, decouple PvP start from upkeep expiry, add recovery/ramp |
| SS1-3 | Special attack parameters conflict across canonical and design docs | `specs/reference/special-attack-table.md`, `design/gameplay.md`, `specs/core/world-rules.md` | Critical | Make canonical table the only parameter source; remove duplicate hand tables |
| SS1-4 | Structure roster/cost/RCL unlock conflicts | `design/gameplay.md`, `specs/core/world-rules.md`, `design/economy-balance-sheet.md` | Critical | Create one canonical structure table and sync progression/economy |
| SS2-1 | Arena fog-of-war conflicts | `design/gameplay.md`, `specs/core/world-rules.md`, `design/modes.md` | High | Separate participant WASM fog from spectator/replay full view |
| SS2-2 | Allied Transfer aggregate cap/intercept not fully canonicalized | `specs/core/resource-ledger.md`, `design/gameplay.md`, `specs/core/snapshot-contract.md` | High | Move alliance caps and intercept risk into ledger/economy UX |
| SS2-3 | New player transfer lock send/receive semantics conflict | `design/gameplay.md`, `specs/core/resource-ledger.md`, `specs/core/snapshot-contract.md` | High | Canonicalize send+receive or explicitly choose alternative |
| SS2-4 | Storage tax/PvE player intuition still under-specified | `specs/gameplay/PLAYTEST-GATED.md`, `specs/core/resource-ledger.md`, `design/economy-balance-sheet.md` | Medium | Add player-facing time-scale examples and PvE role table |
| SS2-5 | MCP onboarding wording suggests direct actions / stale MoveTo | `design/interface.md`, `specs/gameplay/feedback-loop.md` | Medium | Rename/explain schema discovery; remove stale action names |

---

## 4. CrossCheck

CX-1: `world-rules.md` 示例中仍出现浮点字段（`decay_rate = 0.0/0.001`, `transfer_to_global_cost = { Energy = 0.01 }`, `damage_multiplier = 1.0`），与 Resource Ledger 定点/bps 合同冲突 → 建议 Determinism/Tech reviewer 检查所有 TOML schema 是否仍允许 float，以及 codegen 是否拒绝浮点配置。

CX-2: Arena fog-of-war 冲突可能不只是设计问题，还会影响 snapshot filtering、replay privacy 和 spectator delay → 建议 Security/Visibility reviewer 检查 `visibility.md`、snapshot contract 与 Arena room config 的信息泄露边界。

CX-3: Special attack canonical table 与 command validation/IDL 是否一致超出本方向完全验证范围 → 建议 API/Implementation reviewer 检查 `game_api.idl.yaml`、`command-validation.md`、`api-registry.md` 的 action indices、cooldown、range、resistance 是否与 `special-attack-table.md` 一致。

CX-4: Resource Ledger 的 `allied_daily_cap` 按 24h 定义，但 tick-based engine 需要明确 day length、reset boundary、timezone/epoch → 建议 Core/Determinism reviewer 检查 daily cap 的 deterministic reset 与 replay 输入。

CX-5: `feedback-loop.md` 中 `swarm_get_available_actions` 若继续存在，可能与 MCP security scope/rate-limit/detail-level 产生歧义 → 建议 MCP/Security reviewer 检查该工具是否只返回 schema，不返回隐藏状态推导出的“可执行动作”。

CX-6: `snapshot-contract.md` 的 transfer intercept 成功率使用百分比公式，需确认最终实现使用 basis points/ppm 定点而非 float → 建议 Determinism reviewer 检查 RNG 与 success formula 的定点化。
