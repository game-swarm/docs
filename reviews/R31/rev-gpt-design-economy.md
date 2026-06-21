# R31 Design & Economy Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计方向有明确亮点，但从玩法一致性、UX 学习曲线和经济模型直觉看，存在数个必须修复的目标状态冲突。最严重的是 Standard 经济报表显示 1/2/3/5/10/20/50 房间全阶段长期净亏损，却同时要求玩家在免维护期后自维持；这会把 anti-snowball 变成 anti-growth，使新手与中阶玩家都无法形成正反馈学习闭环。另有 global/local transfer 延迟、Allied Transfer 语义、新玩家资源门、特殊攻击解锁状态等跨文档冲突，都会直接影响玩家策略空间、AI agent 决策和实现验收。

## 2. 发现的问题

### DE-1 — Critical — Standard 经济曲线全阶段净亏损，破坏自维持与学习闭环

- 文件引用：`/tmp/swarm-review-R31/design/economy-balance-sheet.md:49`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:69`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:91`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:113`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:123`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:129`
- 文件引用：`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:118`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:139`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:142`、`/tmp/swarm-review-R31/design/gameplay.md:406`、`/tmp/swarm-review-R31/design/gameplay.md:432`
- 问题描述：经济报表中 Standard 1 房间净流量 -30/tick，5 房间 -250/tick，20 房间 -1,940/tick，50 房间 -12,625/tick；汇总表进一步显示 1/2/3/5/10/20/50 房间全部为负流量。但 Resource Ledger 同时声明免维护到期后 Full economy 应自维持，gameplay 又把 empire-upkeep 描述为 anti-snowball 而非全阶段压制。
- 影响分析：这会让玩家的核心动机从“优化算法取得正收益”变成“无论怎么扩张都持续亏损”。新手在 safe/soft_launch 后没有稳定目标，中阶玩家在 5-10 房阶段也看不到可达的 break-even，专家玩家则被维护费硬压死，策略空间退化为寻找漏洞或依赖外部输血。对 AI agent 来说，经济仪表盘会持续给出负反馈，难以形成可学习的 reward loop。
- 修复建议：重做 Standard 收支曲线，明确至少三个可达稳态：新手 1-2 房在 free_upkeep 后可通过 RCL2/基础 harvester 达到略正或接近平衡；中阶 5-10 房通过代码效率/多 Source/PvE 达到正收益但边际收益递减；大帝国 20+ 房开始明显压缩利润，50 房接近 soft cap。维护费公式可以保留超线性，但需要同步提高合理收入项、降低 early base_upkeep，或引入 RCL/效率对收入的可验证放大，使 anti-snowball 只惩罚无脑扩张而不是所有扩张。

### DE-2 — High — Global Storage 转换延迟存在 5/10/100 tick 三套目标状态

- 文件引用：`/tmp/swarm-review-R31/design/gameplay.md:311`、`/tmp/swarm-review-R31/design/gameplay.md:313`、`/tmp/swarm-review-R31/design/gameplay.md:358`、`/tmp/swarm-review-R31/design/gameplay.md:359`
- 文件引用：`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:73`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:75`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:190`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:191`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:144`、`/tmp/swarm-review-R31/design/economy-balance-sheet.md:145`
- 问题描述：gameplay 定义本地→全局 10 tick、全局→本地 5 tick；Resource Ledger 只定义 `global_transfer_delay = 100 tick` 且说明为全局提取延迟；Snapshot Contract 定义 GlobalWithdraw 为 100 tick；Economy Balance Sheet 又列出 deposit 10、withdraw 100。
- 影响分析：物流延迟是资源战略空间的核心。如果 withdraw 是 5 tick，global storage 接近战斗即时补给；如果是 100 tick，它是战略调度资源。当前三套值会导致玩家、AI agent、经济仪表盘、balance sheet 对同一操作产生完全不同的最优策略判断，也会让 No Teleport 反制机制失效或过强。
- 修复建议：以 Resource Ledger 为唯一经济权威，明确拆分 `global_deposit_delay = 10` 与 `global_withdraw_delay = 100`，或统一为一组命名一致的 deposit/withdraw 参数。同步修改 gameplay/API IDL/snapshot/economy-balance-sheet，避免 `transfer_from_global_time = 5` 与 `global_transfer_delay = 100` 并存。

### DE-3 — High — Allied Transfer 在外交层被描述为“直接免延迟”，与 Restricted Allied Transfer 冲突

- 文件引用：`/tmp/swarm-review-R31/design/gameplay.md:2131`、`/tmp/swarm-review-R31/design/gameplay.md:2134`
- 文件引用：`/tmp/swarm-review-R31/design/economy-balance-sheet.md:156`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:77`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:78`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:79`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:80`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:200`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:216`
- 问题描述：外交系统表格写明 allied 可“直接 player↔player transfer，免 convert 延迟”；但经济报表、Resource Ledger 和 Snapshot Contract 均定义 Restricted Allied Transfer：2% fee、200 tick delay、500 tick cooldown、daily cap、联盟时长要求，并且运输最后 50 tick 可被拦截。
- 影响分析：这是资源流的重大玩法冲突。若 allied 真的免延迟直接转移，会绕过大部分 anti-snowball、new player gate 和 No Teleport 约束，联盟将成为资源瞬移网络；若采用 Restricted Allied Transfer，外交 UI/规则说明又会误导玩家和 AI agent，导致错误策略和信任破坏。
- 修复建议：将外交特权改写为“可发起 Restricted Allied Transfer”，并在同表中列出 fee/delay/cooldown/cap/intercept/new-player-lock 的摘要。若想保留本地同房间 ally drone 间即时 transfer，应明确它只是 `LocalTransfer`，受距离/可见性/实体持有资源限制，不是 player global storage 直接转移。

### DE-4 — High — 特殊攻击目标状态仍残留 Tier 2 标记，冲突于“全部 8 种核心能力”

- 文件引用：`/tmp/swarm-review-R31/design/gameplay.md:530`、`/tmp/swarm-review-R31/design/gameplay.md:773`、`/tmp/swarm-review-R31/design/gameplay.md:779`、`/tmp/swarm-review-R31/specs/reference/api-registry.md:87`、`/tmp/swarm-review-R31/specs/reference/api-registry.md:90`
- 问题描述：gameplay 明确 Standard/Arena 全量启用 8 种特殊攻击，且不存在 Tier 2/Phase/Future 语义；但 API Registry 仍将 Leech 与 Fabricate 标为 `⏳ Tier 2`，并说明在 custom_action_def 中已注册但标记 Tier 2。
- 影响分析：特殊攻击是专家策略深度的核心。如果文档一处宣称可用、另一处标记 Tier 2，SDK 生成、world_action_manifest、玩家学习材料和 Arena 规则都会产生歧义。尤其 Leech/Fabricate 是高阶战斗/转化策略，是否可用会显著改变 body planning 和防守经济。
- 修复建议：若 R31 目标状态是 8 种全量核心能力，则 API Registry/IDL 源应移除 Tier 2 标记，并把 Leech/Fabricate 与其他特殊攻击同等注册。若确实需要层级解锁，则 gameplay 的“全部 8 种核心能力、不存在 Tier 2”必须撤回；此项属于目标设计选择，不应同时保留两种状态。

### DE-5 — Medium — 新玩家资源门的方向不一致：禁止发送 vs 禁止接收

- 文件引用：`/tmp/swarm-review-R31/design/gameplay.md:418`、`/tmp/swarm-review-R31/design/gameplay.md:422`
- 文件引用：`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:95`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:133`、`/tmp/swarm-review-R31/specs/core/08-resource-ledger.md:169`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:209`
- 问题描述：gameplay 表格写“新玩家前 N tick 不得向其他玩家 transfer 资源”，但 Resource Ledger 和 Snapshot Contract 多处写“新玩家禁止接收任何转移/双方均非 lock 期”。
- 影响分析：反 smurf 的目标通常是阻止小号接收大号输血；禁止小号向外发送只能防止反向搬运，却不能阻止老玩家给小号加速。若实现者按不同文档理解，会出现刷号经济门失效或过度限制新手合作的两种相反结果。
- 修复建议：统一为“lock 期内该 identity 既不能接收 player-originated transfer，也不能向其他玩家发送可交易资源；PvE bound drop 仅账号内使用”。若希望更温和，则至少明确主要约束是禁止接收，并说明是否允许向系统/本地建筑/自身 drone 转移。

### DE-6 — Medium — 文档仍大量使用 MVP/P0/P1+ 语义，违背“设计即目标状态”的评审原则并干扰产品目标

- 文件引用：`/tmp/swarm-review-R31/specs/gameplay/06-feedback-loop.md:1`、`/tmp/swarm-review-R31/specs/gameplay/06-feedback-loop.md:7`、`/tmp/swarm-review-R31/specs/gameplay/06-feedback-loop.md:340`
- 文件引用：`/tmp/swarm-review-R31/design/modes.md:12`、`/tmp/swarm-review-R31/design/modes.md:88`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:181`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:185`、`/tmp/swarm-review-R31/specs/core/09-snapshot-contract.md:254`
- 问题描述：多个被评审文档仍以 MVP/P0/P1+ 划分设计内容，例如 Arena 房间制为 P0、Tournament/League 为 P1+，Feedback Loop 直接命名为 MVP 反馈循环，Snapshot Contract 定义 MVP 经济边界。
- 影响分析：从设计与经济角度，阶段语义会让玩家目标状态不清晰：Arena 到底是否有赛事层？Challenge Board 是否是最终非资源奖励？市场/商人/合约到底是明确不在设计内，还是未来待补？这会影响玩家长期动机模型和专家生态预期，也容易让评审误把目标设计缺口当成“后续阶段”。
- 修复建议：将阶段标签改写为目标状态分类：Core Ruleset、Optional Module、Out-of-Scope RFC、Official Product Layer 等。若 Tournament/League 不属于当前目标设计，应标为 Optional Product Layer/RFC，而非 P1+；若它属于目标状态，则应给出明确规则和经济边界。

### DE-7 — Low — `global_storage_public` 标记“计划中”，但可见性本身影响经济博弈

- 文件引用：`/tmp/swarm-review-R31/design/gameplay.md:349`、`/tmp/swarm-review-R31/design/gameplay.md:351`、`/tmp/swarm-review-R31/design/gameplay.md:369`
- 问题描述：文档先把“全局存储部分公开、本地存储完全私有”作为 anti-dominant-strategy 的一部分，随后参数表却把 `global_storage_public` 标为“计划中”。
- 影响分析：经济情报可见性不是装饰项，而是市场操纵、威慑、联盟信任和突袭判断的基础。如果公开程度未定，玩家无法评估囤积本地 vs 全局的策略价值。
- 修复建议：删除“计划中”语义，明确目标默认：例如 World 默认仅区间公开、Arena 按赛制公开、Tutorial 全公开；并定义 API/UI/MCP 暴露粒度。

## 3. 亮点

- `design/gameplay.md:5` 到 `design/gameplay.md:27` 的 10 分钟 Golden Path 很清晰，把登录、SDK、编译、部署、观察、调试、首个 PvE 挑战串成可验收的新手动线；这对人类和 AI agent 都是很强的 UX 基础。
- `design/gameplay.md:282` 到 `design/gameplay.md:330` 的全局/本地双层存储模型直觉优秀：它把易用性、物流成本和可掠夺性拆开，为新手模式、标准模式、硬核物流世界提供了同一套设计语言。
- `design/gameplay.md:336` 到 `design/gameplay.md:362` 的累进存储税、本地隐匿性、No Teleport 三件套方向正确，能把“囤积”从单纯正反馈变成有可见成本和情报权衡的策略选择。
- `specs/core/08-resource-ledger.md:9` 到 `specs/core/08-resource-ledger.md:15` 的 Resource Ledger 原则很好，尤其是单一入口、确定性账本和 TickTrace 归因，为经济审计和反作弊提供了强基础。
- `design/modes.md:26` 到 `design/modes.md:84` 的 World PvE 生态层有明确的地理难度梯度、NPC 掉落预算和世界事件，能为非 PvP 玩家提供持续目标，也能降低从 tutorial 到 full PvP 的体验断层。
- `design/gameplay.md:2193` 到 `design/gameplay.md:2239` 的经济反馈循环覆盖 Web UI 和 MCP 双通道，能够让玩家把“为什么亏损/闲置/低效”转化为具体可调策略，是编程游戏学习曲线中非常关键的设计。

## 4. CrossCheck — 需要跨方向检查

- CX-1: API Registry 标注 Leech/Fabricate Tier 2 与 gameplay 目标状态冲突 → 建议 API/IDL 方向检查 `game_api.idl.yaml` 是否仍保留 Tier 2 元数据，以及 registry 是否由旧 IDL 自动生成。
- CX-2: Global transfer delay 命名与数值在 gameplay/API IDL/Resource Ledger/Snapshot Contract 间不一致 → 建议 Core/Economy 方向检查 `TransferToGlobal`/`TransferFromGlobal` 的实际 schema、ledger operation、TickTrace 字段能否表达 deposit/withdraw 两个独立 delay。
- CX-3: Allied Transfer 的拦截 RNG、可见性、事件通知涉及确定性与隐私 → 建议 Core/Determinism 方向检查 `Blake3("intercept" || transfer_id || tick || world_seed)` 的 seed epoch/replay 记录是否足够，以及失败/成功事件是否会泄露不可见攻击者位置。
- CX-4: 经济报表的 Standard 全阶段净亏损可能源于收入模型缺失或单位误差 → 建议 Analytics/Balance 方向用统一参数表重算 source income、controller income、PvE cap share、drone upkeep 与 maintenance，并输出可复算表。
- CX-5: Snapshot Contract 中仍有 MVP/Future RFC 边界，而任务要求设计文档呈现最终目标状态 → 建议 Documentation/Speaker 方向统一术语，把阶段标签替换为 Core/Optional Module/Out-of-Scope RFC 等目标状态分类。
- CX-6: Diplomacy 中 allied “免延迟 transfer”可能来自旧设计残留 → 建议 Gameplay/Rules 方向检查所有 alliance/diplomacy 文档和 MCP tools 是否存在绕过 Resource Ledger 的 player↔player direct transfer 入口。
