# R30 Clean-Slate 独立评审 — Design & Economy

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计方向整体有潜力：核心 fantasy（代码即军队）、World/Arena 双模式、Resource Ledger 单入口、反馈循环与新手保护都有清晰目标。但从 Design & Economy 视角看，仍存在数个必须修复的重大问题：经济权威源之间出现参数/状态边界冲突，Standard 世界的 balance sheet 与新手自维持目标相互矛盾，Arena/World 的当前设计仍夹带阶段路线图语言，部分关键玩法（allied transfer、drone message/P2P、PvE/market/merchant）在“当前设计 vs Future RFC”之间摇摆。这些问题会直接影响 resource flow、anti-snowball 曲线、玩家学习曲线和实现可执行性，因此建议 REQUEST_MAJOR_CHANGES。

## 2. 发现的问题

### D&E-1 — High — Standard 经济曲线证明与新手成长目标冲突

- 文件引用：`/tmp/swarm-review-R30/design/economy-balance-sheet.md:33`、`/tmp/swarm-review-R30/design/economy-balance-sheet.md:51`、`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:135`、`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:144`
- 问题描述：Standard balance sheet 中 1/5/20/50 房间全部为负流量：1 房间 -30/tick、5 房间 -250/tick、20 房间 -1,940/tick、50 房间 -12,625/tick；但 Resource Ledger growth path 又宣称 2000+ Full economy “✅ 自维持”，并说明免维护到期时玩家应有 ≥2 rooms + 5 drones + 完整 faucet 管道。现有表格没有给出任何一个正流量稳定点。
- 影响分析：这会破坏学习曲线与玩家动机。新玩家从 safe/soft_launch 进入正式经济时，看见的不是“优化后可活”，而是所有示例规模都在亏损；专家玩家也无法判断扩张边际收益，因为文档没有展示 room count、RCL、source level、drone count 之间的正收益窗口。anti-snowball 设计应制造“扩张可行但边际递减”，而不是“所有展示点均长期亏损”。
- 修复建议：补一张 authoritative break-even table：至少覆盖 1/2/3/5/10/20/50 rooms，列出 rooms、sources、平均 RCL、harvester count、source yield、controller income、PvE expected value、upkeep、tax、spawn amortization、net/tick。目标应明确：新手在免维护到期前能达到一个小而正的稳定点；中型帝国通过效率/物流获得正流；大帝国在 20+ 或 50 附近进入强递减。若 Standard 目标是“1 房必亏”，则需要同步改 growth path，不应再宣称 2000+ Full economy 自维持。

### D&E-2 — High — 全局转移时间/延迟存在三套互相冲突的权威值

- 文件引用：`/tmp/swarm-review-R30/design/gameplay.md:310`、`/tmp/swarm-review-R30/design/gameplay.md:312`、`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:75`、`/tmp/swarm-review-R30/specs/gameplay/08-api-idl.md:277`、`/tmp/swarm-review-R30/specs/gameplay/08-api-idl.md:283`
- 问题描述：gameplay 文档写本地→全局 `transfer_to_global_time = 10` tick、全局→本地 `transfer_from_global_time = 5` tick；Resource Ledger 统一参数表只定义 `global_transfer_delay = 100` tick；API IDL 又让 `TransferToGlobal.duration = transfer_to_global_time`、`TransferFromGlobal.duration = transfer_from_global_time`，没有映射到 Ledger 的 100 tick。
- 影响分析：global/local 的转换延迟是 “No Teleport” 和物流策略空间的核心。如果实现按 5/10 tick，会支持近实时补给；如果按 100 tick，会变成战略级预调度；两者对前线 Depot、allied transfer、storage tax、战斗补给完全不同。当前文档无法指导经济调参，也会让玩家 UI、SDK、MCP 反馈口径不一致。
- 修复建议：在 Resource Ledger 中拆分并权威定义 `global_deposit_delay` 与 `global_withdraw_delay`，或明确统一为单个 `global_transfer_delay`。然后同步 gameplay、API IDL 和 snapshot economy boundary，不得在描述性文档重新声明不同默认值。建议按玩法目标选择：轻物流模式可为 deposit 10 / withdraw 100，表达“入库较快、出库补给慢”；若保持 10/5 tick，则需要降低 “No Teleport” 声称强度。

### D&E-3 — High — Allied Transfer 当前设计边界冲突：默认禁用、MVP 必须实现、Future/Final 同时存在

- 文件引用：`/tmp/swarm-review-R30/design/economy-balance-sheet.md:126`、`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:198`、`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:214`、`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:167`
- 问题描述：模式差异表写 Standard `allied_transfer_enabled = false (默认)`；Snapshot Contract 又写 Allied Transfer 在 MVP 中以 Restricted Cooperation 模式实现，并且运输中拦截是最终设计；Resource Ledger 则把 Allied Transfer 约束列为当前账本规则。三者合起来无法判断 Standard 当前目标状态到底是“默认关闭但功能存在”、“Standard 可用但受限”，还是“仅联盟世界可用”。
- 影响分析：allied transfer 是联盟经济、反小号、物流战和 anti-snowball 的高影响入口。默认关闭会让联盟玩法缺乏经济意义；默认开启则必须承担 smurf、feeding 和联盟雪球风险。当前冲突会影响玩家外交动机：结盟是为了 visibility/heal，还是能形成真实资源合作？也影响新手被老玩家资助的门控逻辑。
- 修复建议：做一个明确目标状态决策并写成单一表：World Standard 是否启用 Allied Transfer、Novice 是否启用、Tutorial 是否启用、Arena 是否禁用。若 Standard 默认禁用，则 Snapshot Contract 不应说 MVP/current 必须实现为可用玩法；若 Standard 默认启用，则 economy-balance-sheet 模式表应改为 enabled，并列出 fee/delay/cap/intercept 对联盟雪球的抑制。

### D&E-4 — Medium — 文档仍含大量 Phase/MVP/P0/P1+ 路线图语言，违背“设计即目标状态”

- 文件引用：`/tmp/swarm-review-R30/design/modes.md:88`、`/tmp/swarm-review-R30/design/modes.md:149`、`/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:5`、`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:181`、`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:254`
- 问题描述：多个文件仍以 MVP/P0/P1+/当前不实现/Future RFC 作为设计边界。例如 Arena “P0 以房间制比赛为核心”、Tournament/League 为 P1+；Snapshot Contract 有 “MVP Economy Boundaries”；Feedback Loop 标题即 “MVP 反馈循环规范”。这与本轮评审原则“文档呈现最终设计，不区分阶段路线图”冲突。
- 影响分析：设计评审无法判断哪些是当前目标、哪些只是临时实现裁剪。尤其是经济/社交系统中，Future RFC 与当前玩法边界会改变玩家动机：市场、合约、Merchant、P2P offer 若不是目标设计，就不应出现在当前核心反馈循环中；若是目标设计，就需要完整经济约束。
- 修复建议：将阶段词替换为目标状态语言：`Core Design`、`Optional Mod Surface`、`Out of Scope`、`Non-goal`、`Product Extension`。对确实不属于核心的系统，明确“非核心引擎设计，作为 Rhai mod / 外部编排实现”，而非 P1+/MVP 留白。

### D&E-5 — Medium — Drone P2P 资源交换与 Resource Ledger Future RFC 冲突

- 文件引用：`/tmp/swarm-review-R30/design/gameplay.md:2043`、`/tmp/swarm-review-R30/design/gameplay.md:2046`、`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:279`、`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:260`
- 问题描述：gameplay 将 drone message payload 明确用于 peer-to-peer 资源交换协议，并把“不可信协议”作为 game theory element；但 Resource Ledger 和 Snapshot Contract 将 Drone P2P Offer 标为 Future RFC，不进入当前资源账本/当前经济边界。
- 影响分析：消息系统本身不转移资源，但文档鼓励用它设计资源交换协议，会让玩家以为可以实现点对点交易；然而没有 escrow/contract/settlement 的当前 ledger，只能靠 local transfer 手动履约，风险模型与可玩目标没有闭合。若这是有意的“信任博弈”，需要明确它只能协调已有 LocalTransfer/AlliedTransfer，不提供原子交换；否则会造成玩家期望落差。
- 修复建议：在 gameplay §2.9 明确区分：Message = 协议协商层；资源实际流动只能通过 Ledger 已有操作。把示例从“交换协议”改为“非原子 offer/intent 协议”，并明确没有担保、没有自动履约、没有 P2P Offer operation。若希望它成为核心玩法，则需要从 Future RFC 移入 Resource Ledger 并定义结算/失败/审计规则。

### D&E-6 — Medium — Arena 胜利条件和竞技产品定位不一致

- 文件引用：`/tmp/swarm-review-R30/design/modes.md:22`、`/tmp/swarm-review-R30/design/modes.md:143`、`/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:334`
- 问题描述：modes 文档写 Arena 胜利条件为“一方 drone=0 > 认输 > tick 上限按剩余资产判定（drone数→建筑数→资源量）> 平局”；Feedback Loop 则写“摧毁敌方 Spawn，或时限结束时分高者胜”。两个目标导致完全不同的竞技策略：消灭 drone、狙击 Spawn、资产最大化、还是分数优化。
- 影响分析：Arena 是算法竞技的核心出口，胜利条件不统一会直接影响 starter bot、排行榜、观战理解和 meta。若目标是展示算法对抗，应该避免玩家不知道“保 Spawn”“保 drone”“刷资源”哪一个才是目标函数。
- 修复建议：建立单一 Arena scoring contract。建议采用优先级制并显式公开：Primary = enemy active drone count 归零或 Spawn destroyed（二选一需裁决）；Timeout tiebreaker = weighted score，列出权重（active drones、spawn alive、structures、resources、damage dealt、map control）。然后同步 modes 与 feedback-loop。

### D&E-7 — Low — 特殊攻击解锁表与 API Registry 的 Tier 2 标记仍有体验口径差异

- 文件引用：`/tmp/swarm-review-R30/design/gameplay.md:530`、`/tmp/swarm-review-R30/design/gameplay.md:779`、`/tmp/swarm-review-R30/specs/reference/api-registry.md:81`、`/tmp/swarm-review-R30/specs/reference/api-registry.md:84`
- 问题描述：gameplay 写 Standard 全部 8 种特殊攻击可用；API Registry 将 Leech/Fabricate 标为 `⏳ Tier 2`，并说明已注册但标记 Tier 2。虽然可解释为解锁层级/实现标记，但对玩家学习曲线而言，“Standard 全可用”与“Tier 2”会造成是否可用的疑问。
- 影响分析：特殊攻击是专家层深度的主要来源，若 Standard 玩家在 SDK/Registry 看到 Tier 2 标记，会不确定是否应学习/依赖 Leech/Fabricate。对新手→专家过渡不利。
- 修复建议：删除或重命名 `⏳ Tier 2` 这种阶段感标记。若表示玩法层级，改为 `advanced_unlock_group = tier2`，并在 Standard 规则中明确“默认启用”；若表示未来未完成，则不应出现在 Standard 全可用表中。

### D&E-8 — Low — 新手保护时间轴存在 10 分钟 Golden Path、5 分钟教程、safe/soft_launch 多套目标但缺少统一体验漏斗

- 文件引用：`/tmp/swarm-review-R30/design/gameplay.md:5`、`/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:25`、`/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:83`、`/tmp/swarm-review-R30/design/gameplay.md:535`
- 问题描述：gameplay 定义 10 分钟 Golden Path；Feedback Loop 定义 5 分钟教程；safe_mode 500 tick + soft_launch 1500 tick + PvP 渐进过渡又形成更长的新手体验。它们各自合理，但没有一张 unified onboarding funnel 说明每段的目标、玩家掌握的概念、经济状态、威胁类型。
- 影响分析：新手学习曲线可能碎片化：前 5/10 分钟学会部署，随后进入 500/1500 tick 经济期，却不清楚何时学习物流、维修、PvE、PvP、联盟。AI agent 的 onboarding 同样需要分阶段目标，否则会只闭合部署，不闭合战略成长。
- 修复建议：增加一张 Onboarding Funnel 表：0–5min IDE/部署、5–10min PvE first kill、safe_mode 0–500 tick 经济基础、soft_launch 500–2000 tick 物流/PvE/低风险冲突、post-soft-launch PvP transition。每段列出 UI/MCP feedback、经济目标、失败保护和毕业条件。

## 3. 亮点

- Resource Ledger 单入口方向正确：`/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:9` 到 `/tmp/swarm-review-R30/specs/core/08-resource-ledger.md:15` 明确资源流必须通过统一账本、定点费率和 TickTrace 审计，能有效防止经济逃逸路径。
- Anti-snowball 机制组合有策略潜力：累进存储税、O(n²) rooms upkeep、Controller/Depot age 维护、Room drone cap、soft_launch 共同构成了多层制动，而不是单一硬 cap。
- UX 反馈循环非常到位：`/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:9` 到 `/tmp/swarm-review-R30/specs/gameplay/06-feedback-loop.md:21` 把 Learn/Decide/Act/Understand 闭环讲清楚，且同时覆盖人类和 AI 玩家。
- Deferred Command Model 保持玩法一致性：MCP 不直接 move/attack/build，AI 与人类都必须写 WASM，这很好地维护了“代码就是军队”的核心承诺。
- Overload 反馈透明度是好设计：`/tmp/swarm-review-R30/design/gameplay.md:798` 到 `/tmp/swarm-review-R30/design/gameplay.md:852` 将压力、来源贡献与可见性约束结合，避免静默挫败感，同时保留 fog-of-war。
- Tutorial/Novice/Standard 的难度分层方向合理：特殊攻击禁用、物流模式、safe/soft_launch、经济仪表盘构成了从新手到专家的自然坡度。
- World PvE 常驻层设计优秀：`/tmp/swarm-review-R30/design/modes.md:26` 到 `/tmp/swarm-review-R30/design/modes.md:84` 把 PvE 作为地理/经济生态而非副本消耗品，有利于持久世界的长期动机。
- Snapshot truncation 的 UX 诚信处理扎实：`/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:30` 到 `/tmp/swarm-review-R30/specs/core/09-snapshot-contract.md:103` 明确 truncated 标记、关键实体不可截断和 degraded tick，有助于竞技可信度。

## 4. CrossCheck — 需要跨方向检查

- CX-1: Economy 权威源冲突可能来自 IDL/codegen 生成链未完全同步 → 建议 Technical Spec 方向检查 `economy.idl.yaml`、api-registry 生成产物与 Resource Ledger 的参数一致性，尤其 global transfer delay、storage tax、AlliedTransfer。
- CX-2: `api-registry.md` 声称 57 game tools，但 changelog 写 MCP tools 总数 56 active → 建议 API/Tooling 方向检查生成器计数、auth shortcut 去重和文档自动生成一致性。
- CX-3: Snapshot Contract 中训练模式 debug 示例使用 `distance: 12.53`、`required_range: 5.0`，与全项目禁浮点原则可能冲突 → 建议 Determinism/Engine 方向检查 debug payload 是否允许浮点展示或必须以 milli_distance 输出。
- CX-4: Rhai 模组 state view 在 gameplay 前后出现“global view”和“经可见性过滤”两种说法 → 建议 Engine/Rules 方向检查模组 API 可见性合同，避免经济模组漏扣或信息泄露。
- CX-5: Arena toolset 中存在 tournament_create/status/precommit，而 modes/feedback-loop 又说无 Tournament/League 当前核心 → 建议 Product/API 方向检查 Arena 当前目标是否包含 tournament 编排，或是否应标为外部 orchestrator 能力。
- CX-6: Allied Transfer 拦截使用 `Blake3("intercept" || transfer_id || tick || world_seed)`，若 world_seed 已在 replay/keyframe 可见，赛前预测风险需确认 → 建议 Security/Determinism 方向检查 Arena/World seed disclosure 与 transfer intercept 可预测性。
