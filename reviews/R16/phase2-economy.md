# R16 Phase 2 CrossCheck — Economy 补充验证

本文件只做 Phase 2 补充阅读与交叉核查，不重跑完整经济评审。输入以 R16 Phase 1 reports 的 CrossCheck / 经济相关 findings 为主，并对照当前设计文档中的 economy-balance-sheet、empire-upkeep、Resource Ledger、storage tax、AlliedTransfer / messages / Market RFC 等口径。

## CrossCheck item -> Finding -> disposition

### 1. economy-balance-sheet 与 empire-upkeep mod 公式是否必须统一为 blocker

Finding:
- 必须统一，且应维持为 blocker。两个经济权威对象当前不是同一模型：
  - `economy-balance-sheet` 使用 `maintenance = base_upkeep x rooms x (1 + rooms / room_soft_cap)`，Standard 参数 `base_upkeep=50, room_soft_cap=10`，得到 1/5/20/50 房维护费 55 / 375 / 3,000 / 15,000 per tick。
  - `empire-upkeep` mod 使用 `total_cost = drones * drone_cost + rooms * (room_base + rooms * room_superlinear / FIXED_SCALE)`；默认参数 `drone_cost=2, room_base=10, room_superlinear=1 fixed<u32,4>`。按该默认参数，50 房的房间项约 500.25/tick，且还有 drone 维护项。
- 这不是“同一公式的不同展示”，而是参数空间、变量含义和曲线强度均不同：balance-sheet 有 `room_soft_cap`，mod 无；mod 有 `drone_cost`，balance-sheet 主公式无；balance-sheet 的二次项强度比 mod 默认高数个数量级。
- Economy 两个模型一致指出该冲突（rev-gpt-economy E1、rev-dsv4-economy D1），Speaker 已将其纳入 B5，并要求 “Resource Ledger + empire-upkeep mod 参数为经济实现权威，balance sheet 只验证该公式，不自创公式”。Designer 的 X4 也指出 mod 默认 `room_superlinear=0.0001` 在 50 房几乎不可见，可能削弱 anti-snowball 目标。
- 结论：若不统一，维护费曲线、anti-snowball proof、1/5/20/50 房 balance sheet、经济 dashboard 与服主调参都会各自引用不同事实源，无法进入实现冻结。

Disposition: blocker

Required closure:
1. 明确 empire-upkeep mod / Resource Ledger `UpkeepDeduction` 为实现权威，或明确 balance-sheet 公式如何成为 mod 参数化实例。
2. 删除 `base_upkeep` / `room_soft_cap` 作为未实现权威参数的表述，或把它们加入 mod config 并说明映射。
3. 用唯一公式重算所有示例与 anti-snowball proof。

---

### 2. 1/5/20/50 房全尺度净亏是否缺少可行 break-even 场景

Finding:
- 是，当前缺口足以阻塞经济冻结，但严重度可作为 B5 内的 blocker 子项而非单独新 blocker。
- balance sheet 给出的四个规模均为长期净亏：
  - 1 房：收入 25/tick，支出 55/tick，净 -30/tick；
  - 5 房：收入 140/tick，支出 390/tick，净 -250/tick；
  - 20 房：收入 1,220/tick，支出 3,160/tick，净 -1,940/tick；
  - 50 房：收入 3,975/tick，支出 16,600/tick，净 -12,625/tick。
- 文档给出的解释是“初始资源包支撑”“优化 Harvester 代码效率”“多 Source 并行 + PvE 收益”“联盟交易”。这些都是可能的玩法方向，但不是可复算的 break-even 场景：未给 starter 资源包大小、RCL/source 升级时间、优化带来的可达增益倍数、PvE cap share 计算、联盟交易是否是外部补贴还是正常收入。
- 对经济系统而言，所有规模的 baseline 都净亏会把 anti-snowball 变成 universal negative economy。玩家会依赖一次性补贴、PvE faucet 或联盟输血；这反而可能绕开个人规模曲线，使“顶尖玩家维持 50 房”不再是效率证明，而是外部资源动员证明。

Disposition: blocker

Required closure:
1. 至少补三条可复算场景：新手安全线、中期优化线、扩张上限线。
2. 每条场景给出公式输入：房间数、drone 数、body 成本/维护、source 等级与数量、RCL/controller income、PvE budget share、storage utilization/tax、spawn amortization、global/local transfer loss。
3. 每条场景明确结论是 non-negative、near break-even，还是“可维持 N tick 后必须收缩”。

---

### 3. Recycle fixed 50% vs lifespan depreciation 10%-50% 的推荐权威

Finding:
- 推荐以 Resource Ledger 的 lifespan depreciation 10%-50% 为权威；fixed 50% 只可作为简写或 Tutorial/特殊世界 override。该裁决已被 Speaker D2 记录为 B：`Recycle lifespan 比例 10%-50%（Resource Ledger 公式为权威）`。
- 当前冲突来源：
  - `specs/gameplay/08-api-idl.md` 写 `refund: registry.body_cost(body) * 0.5`；
  - `specs/reference/commands.md` 与部分 gameplay 文案写“退还 50%”；
  - `specs/core/08-resource-ledger.md` 写 `recycle_refund = body_cost * remaining_lifespan * 5000 / total_lifespan / 10000`，并以 `recycle_refund_min=1000 bp` 保底 10%。
- 经济直觉：fixed 50% 会鼓励玩家把 Recycle 当作临终前固定回收期权，使用成本恒定为 50% body cost；lifespan depreciation 让“早回收高退还、晚回收长使用期”形成真实 trade-off，也更符合折旧和防高频换装的设计目标。
- API-DX 仍需同步，因为 IDL/codegen 不能生成 fixed 50%，否则 SDK 与 Ledger 会发生实现分叉。

Disposition: high

Required closure:
1. Resource Ledger 公式成为唯一权威。
2. IDL 的 Recycle 字段改为引用 Ledger 公式，而不是手写 `*0.5`。
3. gameplay/commands 中的“50%”改为“上限 50%，按剩余 lifespan 折旧，最低 10%；Tutorial 可配置 override”。
4. 如保留 Tutorial 前 500 tick 100% 退还，必须写成 world-rule override，并进入 ledger trace。

---

### 4. storage tax tier/base/mode table 口径与 equilibrium proof

Finding:
- 当前口径不闭合，应列为 high；若与 balance sheet freeze 绑定，可作为 B5 的高优先级必修项。
- 三套口径同时存在：
  - gameplay 的 `global_storage_tax_tiers`: 0-30% 0bp、30-60% 1bp、60-85% 5bp、85-100% 20bp；
  - Resource Ledger 的 `storage_tax_rate = 10 bp/tick` 固定税；
  - economy-balance-sheet 的模式表：Tutorial 0bp、Vanilla 5bp、Standard 10bp。
- 三者可以通过“base + tier”设计统一，但当前没有说明是固定税、边际累进税、平均累进税，还是模式表用于选择整套 tier。对玩家和服主来说，固定 10bp 与 top tier 20bp 的行为激励完全不同。
- Equilibrium proof 目前不足。rev-dsv4-economy 已指出需要 `S_eq = I / tax_rate`、各阶梯最大可持续收入、阶梯边界振荡/稳定性证明。rev-dsv4-designer G3 进一步指出 85% 后 20bp 会使 1M storage 在 500 tick 左右大量流失，可能导致玩家永远规避 85% 以上区间，战略储备功能被削弱。

Disposition: high

Required closure:
1. 统一命名：建议以 `global_storage_tax_tiers` 为权威；删除固定 `storage_tax_rate`，或改名为 `storage_tax_base_bps` 并明确是否叠加。
2. 明确 tier 是 marginal tax（只对超出区间征税）还是 average tax（对全量按当前 tier 征税）。经济上推荐 marginal，以减少边界跳变。
3. 在 balance sheet 中补 worked examples：capacity、storage、utilization、tier、tax per tick。
4. 补 equilibrium proof：对给定收入 I，分段计算净流 `dS/dt = I - tax(S)`，证明均衡存在/收敛，或说明边界振荡幅度与 damping 规则。
5. 重评 top tier 20bp：若目标是“紧急储备可短期使用但不能长期囤积”，应给出 85-100% 区间可承受 tick 数；若不是，应平滑为更细 tier 或连续曲线。

---

### 5. AlliedTransfer / messages / Drone P2P / Market RFC 当前范围是否会绕过税和物流

Finding:
- 当前文本仍有绕过风险；需要 high 级别收敛，但在 Speaker B5 中已作为 blocker 的组成部分处理。
- AlliedTransfer 已进入 Resource Ledger，并有 2% fee、200 tick delay、500 tick cooldown、daily cap、新玩家锁、联盟成员时长限制。这个方案本身可接受。
- 风险来自边界叙述不一致：
  - 某些 gameplay 外交/联盟描述可被读作 player<->player 直接 transfer 且“免 convert 延迟”；
  - Drone messaging 被描述为可承载不可信 P2P 协议，容易被读成可通过 WASM 层完成资源交换；
  - Resource Ledger 把 Drone P2P Offer、Market Orders、Contract Settlement 标为 Future RFC；
  - API registry 仍出现 `swarm_list_market_orders`，会给实现侧误开市场入口的信号。
- 经济裁决应区分“通信协议”和“结算协议”：messages 可以承载谈判、承诺、报价 payload，但不得改变资源归属；任何资源归属变化只能通过 Resource Ledger 当前操作（LocalTransfer / GlobalDeposit / GlobalWithdraw / AlliedTransfer 等）发生。

Disposition: high

Required closure:
1. 当前版本冻结：Market Orders、Drone P2P Offer、Contract Settlement、Escrow、Auction、Merchant 均为 Future RFC，不能结算资源。
2. Messages 明确为非执行 payload：不 escrow、不锁资源、不自动 settlement、不绕过 Ledger。
3. AlliedTransfer 文案改为“免 global<->local convert，但仍走 AlliedTransfer fee/delay/cap/new-player-lock/audit”。
4. `swarm_list_market_orders` 等市场 API 若保留在 registry，必须显式 `FeatureGate::FutureRfc`，并不进入默认 MCP capability。
5. 小号/联盟银行风险需与 Security 继续核查 same-origin quota、daily cap 是否合并按 source account group / alliance group 计数。

---

### 6. defensive bias 与存储税 top tier 参数是否需调整

Finding:
- 需要调整或至少补参数证明；当前应定为 medium/high 之间。考虑 Designer 两个模型均指出玩家体验风险，建议标 high，但不升级为独立 blocker，除非后续数值 proof 显示攻击策略严格劣势。
- Defensive bias 来源于多机制叠加：ATTACK/RANGED_ATTACK age_modifier 为负、active aging 110%、Controller/Depot 修理、Fortify 100 tick shield + 全 debuff cleanse + x0.5 resistance。rev-dsv4-designer G4 指出这可能形成“repair fortress”：攻击者在行军和交战中被年龄/修理距离/部件寿命三重惩罚，防守者则享受 TOUGH、repair range、Fortify。
- 经济层影响：若防守过强，大玩家可以把资源转成防御基础设施和本地隐匿存储，降低被掠夺风险；此时 storage tax 的反囤积压力可能只推动“全球存储 -> 本地堡垒”迁移，而不产生真实消耗或冲突。
- storage top tier 20bp 同时可能过强：它能防无限囤积，但会让 85-100% 储备成为不可用区间，鼓励人为 churn（转本地、浪费消费、拆分到盟友）而非健康战略储备。若 AlliedTransfer/本地存储不合并纳入风险模型，还会鼓励用联盟或本地仓绕过全局税。

Disposition: high

Required closure:
1. 做最小 combat-economy sanity table：攻击方/防守方在相同资源投入下的 drone lifespan、repair throughput、Fortify uptime、行军损耗、资源消耗。
2. 对 Fortify 默认值做调参候选：例如 resistance 从 x0.5 调至 x0.7，或增加 Energy cost / cooldown / shared target cooldown。
3. 降低 ATTACK/RANGED_ATTACK age penalty 或给攻击后返航 repair surge，避免攻击策略被年龄系统二次惩罚。
4. storage top tier 改为 marginal + smoother tiers，或保留 20bp 但说明它是“overflow panic tier”，并给出可持续 tick 与玩家预期。
5. 明确本地存储不缴全局税是策略选择，但必须承担可被侦察/攻击/运输成本；否则会成为税制绕过路径。

---

## Consolidated disposition table

| # | CrossCheck item | Disposition | Reason |
|---|---|---|---|
| 1 | balance-sheet vs empire-upkeep 公式统一 | blocker | 维护费是核心 sink；当前公式/参数空间不同，所有经济证明不可复算 |
| 2 | 1/5/20/50 房 break-even 场景 | blocker | 全尺度净亏且无可行正流/近均衡场景，无法证明经济可持续 |
| 3 | Recycle 50% vs lifespan 10%-50% | high | Speaker D2 已裁决 Ledger 折旧公式为权威；IDL/gameplay 必须同步 |
| 4 | storage tax 口径与 equilibrium proof | high | tier/fixed/mode 三口径冲突，缺分段均衡与 top tier 稳定性证明 |
| 5 | AlliedTransfer / messages / P2P / Market 范围 | high | 结算入口必须只走 Ledger；messages/Market/P2P 需 FeatureGate 或非结算化 |
| 6 | defensive bias + storage top tier 参数 | high | 可能形成防守/本地囤积 dominant strategy；需 combat-economy sanity proof 与参数平滑 |

## Overall Economy addendum

R16 的经济方向已经有正确的结构：Resource Ledger、PvE budget、global/local storage、upkeep、storage tax、transfer fee/delay 都是可闭环的组件。但 Phase 2 复核确认，当前最大风险不是缺少组件，而是“经济事实源过多且数值示例未用实现公式验证”。因此 Economy 方向建议维持 Speaker 的 B5 blocker：先统一 `Resource Ledger + empire-upkeep + IDL` 的权威关系，再重算 balance sheet、storage tax proof、Recycle 策略和 transfer 边界；否则实现会把冲突固化进代码与 SDK。
