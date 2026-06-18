# R18 Phase 1 Clean-Slate Review — Economy (GPT-5.5)

## 1. Verdict

REQUEST_MAJOR_CHANGES

R18 相比 R17 明显推进了 API 单源化：`game_api.idl.yaml` 与生成出的 `api-registry.md` 在 CommandAction、MCP tools 数量、API version 上基本闭合；我用脚本抽取验证：CommandAction 19/19 一致，active MCP tools 46/46 一致，`api_version=0.3.0` 一致。

但从经济系统角度，仍不能通过设计冻结。核心问题不是 API Markdown 是否由 YAML 生成，而是“经济机器事实源”仍分裂：`Resource Ledger` 宣称所有资源流动由统一 `ResourceOperation`/Transfer Gateway 结算，但 YAML/API Registry 中的 `resource_operation` 只覆盖 6 个 CommandAction 子集，未覆盖 Upkeep、StorageTax、PvEAward、RecycleRefund、BuildCost、SpawnCost、AlliedTransfer 等真正决定经济平衡的操作。与此同时，维护费、存储税、联盟转账、教程/反馈工具仍存在跨文档冲突，足以产生绕账、通胀或新手经济断裂。

## 2. 发现问题（severity）

### E1 — BLOCKER — Resource Ledger 的“唯一资源入口”没有被 YAML 单源闭合

`specs/core/08-resource-ledger.md` 宣称所有资源流动都通过统一 Resource Ledger API 结算，并列出操作：

- `LocalTransfer`
- `GlobalDeposit`
- `GlobalWithdraw`
- `AlliedTransfer`
- `PvEAward`
- `RecycleRefund`
- `BuildCost`
- `SpawnCost`
- `UpkeepDeduction`
- `StorageTax`
- `MarketTrade` / `ContractSettlement`（Future RFC）

但 `specs/reference/game_api.idl.yaml` 的 `resource_operation` 只列出：

- `Harvest`
- `Transfer`
- `Withdraw`
- `TransferToGlobal`
- `TransferFromGlobal`
- `Drain`

这意味着生成式单源并没有覆盖最关键的经济 ledger 操作。API Registry 只是忠实生成了 YAML 的 6 项 CommandAction 子集，而不是 Resource Ledger 的经济账本操作集合。

经济影响：

- Upkeep / StorageTax / PvEAward / RecycleRefund 等不会被机器源统一枚举，后续实现很容易各写一套路径。
- CI 只能验证 API 文档漂移，不能验证经济账本闭合。
- “所有资源变动写 TickTrace 并可验证 Σ inflows - Σ outflows = Δ storage”缺少可生成的 schema 合同。
- 模组 `actions.award_resource` / `actions.deduct_resource` 与 Ledger operation 类型没有机器级绑定，容易出现不归因的 faucet/sink。

建议：

- 在 YAML 中新增独立的 `ledger_operation` 或扩展 `resource_operation` 为 Ledger 权威枚举。
- 明确区分：`command_resource_operation`（玩家命令子集） vs `ledger_operation`（所有经济账本操作）。
- `api-registry.md`、TickTrace schema、ResourceBalance schema 都应由该 YAML 枚举生成。

### E2 — BLOCKER — 存储税 tiered 公式量纲错误，数值表也无法由权威公式一致导出

`Resource Ledger §2.2` 写道：

```text
storage_tax(tick) = Σ over each tier i where storage_pct > tier_threshold[i]:
    taxable_in_tier = min(storage_pct - tier_threshold[i], tier_width[i])
    tax = taxable_in_tier × tier_rate[i] × global_storage_capacity / 10000
```

这里 `taxable_in_tier` 是“容量百分比点”，但公式直接乘 `global_storage_capacity` 后只除以 10000，少除了一次 100。文档下方示例却按“资源单位”计算：

- 75% 存储：Tier1 300,000 × 1 bp = 30；Tier2 150,000 × 5 bp = 75；总税 105/tick。

按正文公式代入会得到：

- Tier1: 30 × 1 × 1,000,000 / 10000 = 3,000，而非 30。
- Tier2: 15 × 5 × 1,000,000 / 10000 = 7,500，而非 75。

经济影响：

- 实现若照公式写，存储税放大 100 倍，轻中型玩家进入 60% storage 后会被瞬间清空。
- 实现若照示例写，公式和 CI/实现合同不一致。
- `economy-balance-sheet.md` 中 20 房/50 房存储税数值也无法从 tier 表稳定复现。例如容量 1,000,000、满仓 100% 时，按示例口径总税应为 30 + 125 + 300 = 455/tick，而 balance sheet 写 50 房 `storage_tax=600`。

建议：

```text
taxable_units_in_tier = (min(storage_pct, tier_upper) - tier_lower) * global_storage_capacity / 100
tax = taxable_units_in_tier * tier_rate_bp / 10000
```

并为 30%、45%、75%、100% 四个点给出固定测试向量，作为 CI golden tests。

### E3 — HIGH — 维护费曲线文档仍有两套模型，Standard 小/中帝国实际为长期负流

`economy-balance-sheet.md` 与 `Resource Ledger` 当前统一为：

```text
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
Standard: base_upkeep=50, room_soft_cap=10
```

我验证得到：

- 1 房：55/tick
- 5 房：375/tick
- 20 房：3000/tick
- 50 房：15000/tick

这些数值与 balance sheet 表格一致，但与 `design/gameplay.md §8.7` 仍残留的旧叙述冲突：

- “小帝国（1 房, 20 drone）：维护费 ≈ 40/tick”
- “中帝国（5 房, 100 drone）：维护费 ≈ 275/tick”
- “大帝国（20 房, 500 drone）：维护费 ≈ 2100/tick”
- “巨帝国（50 房, 500 drone）：维护费 ≈ 3150/tick”
- 且随后解释旧参数 `drone_cost=2, room_base=10, room_superlinear=1`。

经济影响：

- 文档一处说 50 房 3150/tick，一处说 15000/tick，差距接近 5 倍。
- Standard 1 房收入 25/tick、支出 55/tick，净 -30；5 房收入 140/tick、支出 390/tick，净 -250。表格却标注“新手轻松”“可承受”。
- 若玩家从 Tutorial/Novice 迁移到 Standard，早期扩张是结构性负流，必须依赖初始资源包，但初始资源包规模、持续 tick、RCL 收益曲线没有闭合。

建议：

- 删除 gameplay 中旧的 drone_cost/room_base/room_superlinear 维护费模型，统一引用 Resource Ledger。
- 为 1/5/20/50 房给出 break-even 目标：需要多少 source、多少 harvester 效率、多少 RCL income 才能转正。
- 明确 Standard 是否故意“早期负流”。若是，需要定义 starting resources 与预期转正时间；若否，降低 1–5 房区间 base upkeep 或给新手 upkeep grace。

### E4 — HIGH — Allied transfer 在不同文档中既是免延迟特权，又是受费率/延迟/配额约束的 Ledger 操作

`design/gameplay.md §9.2` 的 Allied 特权表写：

- allied 可直接 `player↔player transfer`
- “免 convert 延迟”

但 `Resource Ledger §2.1/§2.3` 写：

- `allied_transfer_fee = 200 bp`
- `allied_transfer_delay = 200 tick`
- `allied_transfer_cooldown = 500 tick`
- `allied_daily_cap = 10,000 units`
- 需要联盟成员 ≥100 tick、非 new player lock、同目标冷却、24h cap。

经济影响：

- 如果实现按 gameplay 表做“免延迟直接转账”，将绕过全局↔本地转换损耗和延迟，联盟可成为免费 teleport 网络。
- 如果实现按 Ledger 做，玩家文档中的 allied 价值被高估，策略文档误导。
- 这也是先发大联盟滚雪球的典型漏洞：老玩家通过联盟网络把资源即时输送给前线/小号，规避 StorageTax、GlobalTransferDelay、new-player gate。

建议：

- gameplay Allied 表改为引用 Ledger：Allied transfer 是受限 ledger op，不是免延迟。
- 若确实要给 allied 特权，可只降低费率或提高 cap，但不得完全免 delay，除非明确这是 Tutorial/Novice 专用且不进入 Standard。

### E5 — HIGH — PvE faucet 有预算框架，但缺少实际注入基准与区域/玩家维度的可计算闭环

优点是当前文档已经有 `max_pve_output_per_tick ≤ 世界再生总量 × 30%`，并在 Resource Ledger 中定义 Global/Zone/Player/Event 四维预算。但仍缺：

- 世界再生总量如何从 source 数量、source_regeneration_rate、地图规模计算。
- Zone budget 与地理难度梯度的绑定公式。
- Player cap `player_controller_level × 1000 / tick` 量级偏大，可能远超普通 source income（例如 RCL4=4000/tick）。
- NPC Wreckage “body_cost ×20% Energy”是 Unlock 还是 Faucet 没有完全闭合：如果 Guardian 的 body_cost 没有先从世界池锁定，则仍是 faucet。

经济影响：

- PvE 掉落可能成为主经济源，压倒采集/物流/PvP。
- 玩家可在高效 farm route 上无限刷怪，只受事件刷新限制而非全局经济预算约束。
- 若 NPC spawn 不消耗预算、death drop 才消耗预算，可能出现“未掉落但击杀收益/蓝图收益”口径不一致。

建议：

- 定义 `world_regen_budget_per_tick = Σ source_type.regeneration × active_sources × source_regeneration_rate`。
- PvE drop、blueprint、wreckage 都进入同一预算表；blueprint 虽非 Energy，也应有经济价值权重或独立稀缺预算。
- 给 1/5/20/50 房的 PvE 期望收益上限，而不是只写 balance sheet 中的 100/500。

### E6 — MEDIUM — Recycle 权威公式修复了部分漏洞，但与部分描述仍有“固定 50%”残留

`Resource Ledger §2.3` 的 Recycle 公式较好：按剩余 lifespan 线性折算，10%–50% 区间，Tutorial 前 500 tick 可 100%。但 `design/gameplay.md` 和 `specs/gameplay/08-api-idl.md` 仍有“Recycle 回收 drone 获得 50%资源退还”的简化描述。

经济影响：

- 如果实现或 SDK 注释照旧 50%，玩家可用接近死亡的 drone 回收套利，降低 spawn sink 强度。
- 如果实现按 lifespan 公式，文档会误导玩家策略。

建议：

- 所有“50% refund”改成“最高 50%，按 remaining_lifespan 折算，最低 10%；Tutorial 特例 100%”。
- YAML/API Registry 应暴露 refund policy 或至少在 generated docs 引用 Ledger §2.3。

### E7 — MEDIUM — 反馈循环文档引用的经济/调试工具未进入 YAML active tools，单源验证范围仍不完整

`specs/gameplay/06-feedback-loop.md` 多处引用：

- `swarm_get_available_actions`
- `swarm_get_docs`
- `swarm_get_schema`
- `swarm_explain_last_tick`
- `swarm_dry_run_commands`

但 YAML/API Registry 当前 active tools 是 46 个，其中没有这些名称；相近工具是 `swarm_dry_run`、`swarm_simulate`、`swarm_get_tick_trace`、`swarm_get_economy` 等。

经济影响：

- AI agent 经济优化闭环依赖 explain/dry-run/available-actions；如果工具名漂移，AI onboarding 无法闭合。
- 经济仪表盘和趋势工具虽已在 API Registry 中，但反馈循环的“为什么失败/为什么亏损”仍没有对应 canonical explain 工具。

建议：

- 要么把这些工具作为 RFC/alias 写入 YAML；要么修改反馈循环文档引用 active tool 名。
- 对经济方向，建议 `swarm_get_economy` 输出 schema 不只含 `{income, expenses, storage_tax, maintenance}`，还应包含 ledger operation breakdown、projected runway、tax tier next threshold。

## 3. 亮点（Strengths）

1. YAML → api-registry 生成链本身有实质进步。抽取验证显示：CommandAction 19 个一致，active MCP tools 46 个一致，API version 0.3.0 一致，Market 工具已从 active 移到 RFC 区。
2. Resource Ledger 的设计方向正确：单一入口、TickTrace 归因、定点费率、每 tick ResourceBalance 摘要，都是 MMO 经济避免“隐形 faucet/sink”的正确基础设施。
3. StorageTax、EmpireUpkeep、GlobalTransferLoss、PvE cap、NewPlayerGate 这些 anti-snowball 机制都已出现，说明设计已经从“功能清单”进入“经济治理合同”。
4. Market 被明确降级为 Future RFC，避免在当前阶段引入订单簿、价格发现、跨玩家套利、通胀调控等额外复杂度。
5. Tutorial / Novice / Standard / Arena 已有不同参数口径：Tutorial 宽松、Arena 隔离且不影响 World 资产，这有助于避免教学经济污染持久世界。

## 4. Economy Balance Issues

- 小帝国压力过高：Standard 1 房 `income=25`、`expense=55`，净 -30/tick；若这是正式世界默认，不符合“新手轻松”的表述。
- 中帝国压力也偏高：5 房净 -250/tick，不只是“需要优化”，而是必须依赖 RCL/source 升级或外部补贴。当前缺少转正曲线。
- 大帝国/巨帝国的 soft cap 目标成立，但数值过于跳跃：20 房 -1940/tick，50 房 -12625/tick，若无明确高阶 source/PvE/联盟补给模型，会变成“维护费硬墙”而非“效率竞争”。
- 存储税公式/表格不一致，使囤积上限无法校准。当前无法判断 85–100% tier 是温和 sink 还是毁灭性 sink。
- Allied transfer 若免延迟，将成为大帝国绕过 global withdraw delay 的首选通道，直接削弱 No Teleport 原则。
- PvE faucet 的 30% cap 是好方向，但缺少世界再生总量定义和 per-player 上限合理性证明，仍可能成为主要通胀源。

## 5. Resource Loop Gaps

1. LedgerOperation 未机器化：YAML 只覆盖玩家命令资源操作，不覆盖系统级 sink/faucet/unlock/lockup。
2. BuildCost / SpawnCost / RecycleRefund 的 lockup/sink/unlock 归类需要更精确：建筑建造在 balance sheet 中写 Lockup，但 Resource Ledger 表中 `BuildCost` 方向是 Owner → Structure；需要定义结构被摧毁/回收时的返还比例和是否进入 TickTrace。
3. Controller upgrade 是永久 Lockup，但 YAML/API Registry 没有对应 Operation；`ClaimController` 不是升级/进贡。RCL 进贡收入/支出链条不完整。
4. 全局↔本地转换在 gameplay 默认写 `transfer_to_global_time=10`、`transfer_from_global_time=5`，Resource Ledger 权威写 `global_transfer_delay=100` 且只列一个 delay。需要统一 deposit/withdraw delay。
5. `Drone P2P Offer` 在 Ledger 中列为 Future RFC，但 gameplay 的 drone messages 已允许玩家实现 P2P 资源交换协议。需要明确：消息可以协商，但实际资源移动仍必须走 LocalTransfer/AlliedTransfer，不存在 escrow/contract settlement。
6. `Merchant NPC` 在 modes.md 是 NPC 类型，但 Resource Ledger Future RFC 写 Merchant NPC；若 Merchant 可触发交易事件，必须明确当前是否产出资源、是否进 PvE/Event budget。
7. 经济 dashboard 输出尚不足以验证账本：`swarm_get_economy` 只给 income/expenses/storage_tax/maintenance，缺少各 ledger operation 的 breakdown 与 checksum。

## 6. CrossCheck

### YAML ↔ api-registry.md

通过抽取验证：

- `api_version`: YAML `0.3.0`，Markdown `0.3.0`。
- CommandAction: YAML 19，Markdown 19，名称集合一致。
- Active MCP tools: YAML 46，Markdown 46，名称集合一致。
- `swarm_list_market_orders` 已在 RFC/Future tools，不计入 active tool count。

结论：API Registry 作为 YAML 生成物的局部闭环基本成立。

### YAML/API ↔ Resource Ledger

未闭合。

- YAML `resource_operation` 是 CommandAction 子集；Resource Ledger 的 `ResourceOperation` 是全账本操作集合。二者同名但语义不同。
- Upkeep/StorageTax/PvEAward/RecycleRefund 等经济关键操作没有进入 YAML 机器源。
- 这会导致“API 文档无漂移”但“经济账本仍漂移”。

### Resource Ledger ↔ Economy Balance Sheet

部分闭合，但仍有错误。

- Upkeep 1/5/20/50 的 Standard 数值与公式一致。
- StorageTax 数值无法从 §2.2 公式稳定导出，且公式本身量纲错误。
- 1/5 房净流量为负，与“新手轻松/可承受”的解释冲突。

### Resource Ledger ↔ Gameplay

未闭合。

- Gameplay 中维护费旧模型残留，与 Ledger/balance sheet 新模型冲突。
- Allied transfer 的“免 convert 延迟”与 Ledger 的 fee/delay/cap/cooldown 冲突。
- Recycle 固定 50%描述与 lifespan 10%–50%公式冲突。
- Gameplay 的 global transfer time 10/5 tick 与 Ledger 的 `global_transfer_delay=100` 冲突。

### Feedback Loop ↔ API Registry

未闭合。

- Feedback loop 引用多个未在 YAML active tools 中注册的工具名。
- 经济可观测性工具已出现，但 schema 过粗，无法支撑 ledger-level 调试与 AI 经济优化。

## 7. Required Fixes Before Approval

1. 在 YAML 中建立 ledger operation 权威枚举，并生成到 API Registry/TickTrace/ResourceBalance 文档。
2. 修正 StorageTax tiered 公式量纲，并补 30/45/75/100% golden vectors。
3. 删除 gameplay 中旧维护费模型，统一引用 Resource Ledger；补 1/5 房 Standard 转正证明。
4. 统一 Allied transfer：不得在 Standard 中免延迟绕过 Ledger；所有 allied resource movement 必须走 fee/delay/cap/cooldown。
5. 统一 global transfer delay：明确 deposit/withdraw 是 10/5 tick 还是 100 tick，且只保留一个权威源。
6. 修正 Recycle 文案为 lifespan-based 10%–50%，Tutorial 特例另列。
7. 将 feedback-loop 中引用的工具名纳入 YAML（active 或 RFC），或改为当前 active tool 名称。
