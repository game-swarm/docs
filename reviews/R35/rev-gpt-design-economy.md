# R35 Phase 1 Clean-Slate Review — Design & Economy

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：当前设计方向整体已经具备清晰的玩法目标、资源流和反雪球意图，但存在会直接改变经济曲线的权威公式错误，以及新玩家资源门、联盟上限、指定 spec 路径等跨文档合同不一致。这些问题会影响 resource flow、anti-snowball 强度、联盟经济滥用边界和评审/实现可执行性，需在合并前修复。

## 2. 发现的问题

### D&E-1 — Critical — 存储税 tiered 公式量纲错误，实际税额会放大 100 倍

- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:102`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:105`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:112`
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:868`

问题描述：Resource Ledger 的公式写成 `taxable_in_tier = min(storage_pct - tier_threshold[i], tier_width[i])`，再执行 `tax = taxable_in_tier × tier_rate[i] × global_storage_capacity / 10000`。但 `storage_pct` 是百分比点，若容量 1,000,000、Tier 1 宽度 30%、税率 1 bp，该公式得到 `30 × 1 × 1,000,000 / 10000 = 3000`，而同文档示例期望 `300,000 × 1 bp = 30`。也就是说公式比示例与 bp 语义大 100 倍。

影响分析：这是经济系统数学权威文件中的公式级错误，会把全局存储税从轻度 anti-hoarding 机制变成极重惩罚。中期玩家一旦进入 30%+ 存储区间，税负会远超 balance sheet 中的假设，破坏 2–10 房间自维持区间，并把策略空间从“本地/全局存储权衡”压成“避免全局存储”。

修复建议：将公式拆成两步并统一量纲：`taxable_pct = min(storage_pct - threshold_pct, tier_width_pct)`；`taxable_units = global_storage_capacity × taxable_pct / 100`；`tax = taxable_units × tier_rate_bp / 10000`。同步修正 `api-registry.md` 生成源中的 Canonical Formula，确保示例 75% 存储仍得到 105/tick。

### D&E-2 — High — 指定评审 spec 文件不存在，Phase 1 输入集不可完整执行

- 位置：task body 指定 `/tmp/swarm-review-R35/specs/gameplay/07-feedback-loop.md`
- 位置：task body 指定 `/tmp/swarm-review-R35/specs/gameplay/10-api-idl.md`
- 位置：`/tmp/swarm-review-R35/design/gameplay.md:3`
- 位置：`/tmp/swarm-review-R35/design/interface.md:9`
- 位置：`/tmp/swarm-review-R35/design/gameplay.md:2188`

问题描述：task body 要求读取 `specs/gameplay/07-feedback-loop.md` 与 `specs/gameplay/10-api-idl.md`，但这两个路径不存在。文件系统仅提示存在相似文件 `06-feedback-loop.md` 与 `08-api-idl.md`；由于本轮明确禁止读取未列出的设计/spec 文件，我未读取替代路径。与此同时，design 文档内部也引用了旧编号：`gameplay.md` 指向 `06-feedback-loop.md` / `08-api-idl.md`，`interface.md` 指向 registry 但不是 task body 中的 `10-api-idl.md`。

影响分析：这会让评审、实现和 CI 自动化无法以同一输入集复现结论。对 Design & Economy 来说，feedback loop 与 API IDL 是玩家学习曲线、经济反馈可见性、MCP 工具可用性的关键合同；缺失会导致“文档声称有经济仪表盘/API，但评审输入中无对应权威 spec”的断层。

修复建议：统一文件编号和引用：要么恢复/重命名为 task body 指定的 `07-feedback-loop.md`、`10-api-idl.md`，要么更新任务模板和所有文档引用到实际存在的 canonical 文件。修复后重新运行本方向评审，确保反馈循环与 API IDL 被纳入同一白名单输入集。

### D&E-3 — High — New Player Transfer Lock 方向语义冲突，刷号经济边界不闭合

- 位置：`/tmp/swarm-review-R35/design/gameplay.md:407`
- 位置：`/tmp/swarm-review-R35/design/gameplay.md:413`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:99`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:137`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:171`

问题描述：`gameplay.md` 将新玩家限制描述为“前 N tick 不得向其他玩家 transfer 资源”，即禁止新号作为发送方外流资源；Resource Ledger 则多处写成“新玩家禁止接收资源”或“等待 lock 满后方可接收任何资源”。Allied Transfer 又要求双方均非 lock 期。发送方向锁、接收方向锁、双向锁三种语义同时存在。

影响分析：这是 anti-smurf 和新手经济保护的核心边界。如果只禁发送，新号仍可被大号输血后快速发育；如果只禁接收，新号仍可把初始资源/PvE drop 外流给主号；如果 Allied Transfer 才双向禁，普通 local/global/player transfer 仍可能有逃逸路径。当前文档无法让玩家、实现者或服主判断哪些 resource flow 被锁定。

修复建议：在 Resource Ledger 中定义唯一 canonical 语义，例如 `new_player_transfer_lock` 同时禁止 player↔player 的发送与接收，且覆盖 AlliedTransfer、Local player transfer、未来 ContractSettlement，不影响玩家自身 local↔global 转换和非交易式建造/Spawn。然后把 `gameplay.md` 表述改为同一语义，并列出 Tutorial 关闭该限制的例外。

### D&E-4 — High — Active alliance 上限 5 vs 10 冲突，影响联盟经济规模与转移上限

- 位置：`/tmp/swarm-review-R35/design/gameplay.md:2132`
- 位置：`/tmp/swarm-review-R35/design/gameplay.md:2137`
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:633`

问题描述：外交系统写明“每玩家最多同时 5 个 active alliance”，但 API Registry / economy limits 写明 `Max active alliances = 10`。联盟数量直接影响 Allied Transfer 可用关系数、资源互助网络密度、间谍风险和联盟图谱复杂度。

影响分析：若实现按 10，Standard 的 Restricted Allied Transfer 可被扩展成更密集的资源网络，削弱 maintenance curve 和 no-teleport 的约束；若设计/UI按 5，玩家预期与服务端校验不一致。这个值不是纯技术限制，而是联盟经济与外交策略空间的设计参数。

修复建议：将 `max_active_alliances` 作为 Resource Ledger / economy IDL 的唯一参数，并在外交段引用同一值。若保留 10，需要补充为什么 10 不会放大联盟输血；若保留 5，需要更新 IDL 生成源与 registry。

### D&E-5 — Medium — Resource Ledger 中仍出现 float 参数，违反定点经济合同

- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:15`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:70`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:84`
- 位置：`/tmp/swarm-review-R35/design/gameplay.md:2004`
- 位置：`/tmp/swarm-review-R35/specs/reference/api-registry.md:20`

问题描述：Resource Ledger 原则和统一参数表声明全部使用 basis points / fixed-point，`gameplay.md` 也明确所有游戏引擎与 Rhai 模组数值禁浮点；但 `allied_daily_cap_world_multiplier` 的单位写为 `float`，值为 `1.0`。

影响分析：单个 float 参数看似小，但它位于经济权威表，会削弱“经济计算全定点、可回放”的设计合同。世界模式乘数若参与 Allied Transfer daily cap，会直接影响联盟经济上限，必须可确定、可审计、可序列化。

修复建议：改为 `allied_daily_cap_world_multiplier_bp` 或 `*_ppm`，例如 Standard=10000 bp、Arena=5000 bp、Tutorial=50000 bp；公式写成 `cap = max(10_000, receiver_gcl × 20_000) × multiplier_bp / 10000`，并同步 IDL type registry。

### D&E-6 — Medium — PvE 掉落表与 Ledger PvEAward tier 数值不一致，早期奖励预期不稳定

- 位置：`/tmp/swarm-review-R35/design/modes.md:30`
- 位置：`/tmp/swarm-review-R35/design/modes.md:34`
- 位置：`/tmp/swarm-review-R35/design/modes.md:62`
- 位置：`/tmp/swarm-review-R35/design/modes.md:70`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:194`
- 位置：`/tmp/swarm-review-R35/specs/core/08-resource-ledger.md:198`

问题描述：World PvE 表中 Creep 掉落 `Energy 10-30`，Guardian 掉落 `Crystal 5-15 + 蓝图`；Resource Ledger 的 PvEAward tier 表则给 T1 低级 NPC `100–500`、T2 `500–2000`。两者都在描述 NPC 击杀奖励，但量级差距明显，且未说明 design 表是 flavor/示意还是必须映射到 tier 后再受 budget 裁决。

影响分析：PvE 是 10 分钟 Golden Path 的第一个正反馈，也是中大型帝国收入表的一部分。早期奖励如果按 10–30，首杀反馈偏弱；若按 100–500，又可能显著影响新手起步经济和 PvE farming 收益。当前不一致会导致玩家动机模型和经济 faucet 校准失真。

修复建议：在 `modes.md` 中把 NPC 掉落改为引用 Ledger tier，例如 Creep=T1 low roll、Guardian=T2/T3，并明确具体掉落由 `PvEAward` 预算裁决。若保留小数值，应在 Resource Ledger 增加 T0.5/tutorial-tier 或说明这些是 pre-budget illustrative estimates。

### D&E-7 — Low — Balance Sheet 仍使用“实施/playtest 阶段”措辞，容易被误读为阶段路线图

- 位置：`/tmp/swarm-review-R35/design/economy-balance-sheet.md:5`
- 位置：`/tmp/swarm-review-R35/design/economy-balance-sheet.md:180`
- 位置：`/tmp/swarm-review-R35/design/economy-balance-sheet.md:192`
- 位置：`/tmp/swarm-review-R35/design/economy-balance-sheet.md:200`

问题描述：任务原则明确设计文档呈现目标状态，不按 Phase/MVP/迭代评审。Balance Sheet 多处写“推迟至实施/playtest 阶段”“playtest-gated”。虽然 task body 允许 design 数值作为估值插图、精确参数见 spec，但这里的措辞容易被理解为当前设计尚未闭合。

影响分析：这不是阻塞性经济问题，因为文档已经给出清晰的目标曲线：2–10 房间自维持、20 房后递减、50 房软上限。但措辞会给后续实现/评审留下“可以先不定义目标参数”的歧义。

修复建议：保留 playtest 校准事实，但改写为目标状态语言：当前表是 canonical target curve 的初始参数化，后续 playtest 仅用于校准参数，不改变机制目标。避免“推迟至实施阶段”这类路线图语义。

## 3. 亮点

- `design/gameplay.md:5` 的 10 分钟 Golden Path 非常重要：它把新手从登录、SDK、部署、反馈、调试到首个 PvE 击杀的动机链明确串起来，降低了“编程游戏只服务专家”的风险。
- `design/gameplay.md:282` 的全局/本地双层存储模型提供了清晰策略张力：全局存储方便但公开、税收和延迟；本地存储隐蔽但需要物流与防守。
- `design/gameplay.md:423` 的 Anti-Snowball Contract 方向正确：明确 World 不追求个体公平，而追求生态可持续，避免把持久 MMO 错误设计成完全竞技场。
- `design/economy-balance-sheet.md:178` 的 1/2/3/5/10/20/50 房间收支表是优秀的设计验证材料；它把维护曲线、代码效率、RCL、PvE 补充和存储税放进同一个直觉模型。
- `specs/core/08-resource-ledger.md:20` 的 Transfer Gateway 统一资源入口是经济系统的关键优点，能防止 local/global/allied/PvE/recycle 多入口造成资源逃逸。
- `design/gameplay.md:2186` 的经济反馈循环覆盖 Web UI 与 MCP 双通道，对 AI 玩家和人类玩家公平学习非常关键；idle、净流入、税率预警等反馈能把经济调参转化为可学习体验。
- `design/modes.md:86` 的 Arena 房间制定位克制且清晰，把 Arena 定义为算法测试场而不是强行引入完整天梯/赛季，有利于保持 World 与 Arena 的动机分离。

## 4. CrossCheck — 需要跨方向检查

- CX1: `api-registry.md` 标注“57 game tools + 12 auth tools”，但变更记录写 “56 active”，且 task 指定的 API IDL 文件缺失 → 建议 API/IDL 方向检查 IDL 源、生成器、registry 工具计数与文件编号是否一致。
- CX2: `specs/core/09-snapshot-contract.md:5` 仍出现 “MVP 经济边界”措辞 → 建议 Documentation/Speaker 方向检查全仓是否仍残留 MVP/Phase/Future 语义，并判断是否只是历史标签还是目标状态污染。
- CX3: `specs/core/09-snapshot-contract.md:358` 的训练模式错误示例使用浮点距离 `12.53` / `5.0`，而确定性合同要求定点数 → 建议 Determinism/Core 方向检查所有 debug/detail 输出是否允许展示层浮点，或必须统一为 `milli_distance`。
- CX4: `design/gameplay.md:1568` 的 Rhai API 注释写“状态查询经可见性过滤”，但 `design/gameplay.md:594` 又写经济/维护类 Rhai 模组以 global view 运行 → 建议 Engine/Rules 方向检查 Rhai state view 是否按模组 capability 分层，避免规则模组看不见全局经济状态。
- CX5: `design/modes.md:143` 的 Arena fixed_ticks 胜负按 drone数→建筑数→资源量判定，但 `design/gameplay.md:520` 默认 Arena 也可能启用轻物流/全局存储 → 建议 Gameplay/Arena 方向检查 Arena 资源量判定是否计入 in-transit/global/local，并防止临近结算的资源隐藏策略。
