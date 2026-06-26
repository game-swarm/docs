# R39-CV-DE-GPT — 设计经济评审报告

评审范围：
- `/tmp/swarm-review-R39/design/gameplay.md`
- `/tmp/swarm-review-R39/design/economy-balance-sheet.md`
- `/tmp/swarm-review-R39/design/modes.md`
- `/tmp/swarm-review-R39/specs/core/08-resource-ledger.md`

评审重点：经济曲线、转移锁、联盟、PvE、反雪球。

## 总体结论

**有条件通过（建议 R39 合入前修正 P0/P1）。**

整体设计方向成立：`Resource Ledger` 作为单一经济权威、全局/本地/联盟/PvE/回收/建造统一入账，配合超线性维护费、存储税、全局转移延迟、PvE faucet 预算，能够支撑“2–10 房间自维持、20 房后递减、50 房软上限”的目标曲线。

但当前文档存在几处会直接影响实现与平衡校验的冲突：
1. Balance Sheet 的存储税示例数值与 Resource Ledger tiered 公式不一致。
2. 新玩家 transfer lock 在 gameplay 与 ledger 中语义不同，且 PvE drop 绑定没有完整落到账本约束。
3. Resource Ledger 执行顺序文字与列表不一致。
4. PvE Merchant / trade event 与 Resource Ledger 的 out-of-scope 边界冲突。
5. 联盟转移已有 fee/delay/cap，但缺少联盟拆分、资源中转、in-transit 拦截的明确账本状态。

## P0：必须修正

### 1. 存储税数值与权威公式不一致

`Resource Ledger §2.2` 的 tiered 公式和示例表示税应按“各 tier 内的实际资源量 × tier rate”计算。例如容量 1,000,000、存储 75% 时税为 105/tick。

但 `economy-balance-sheet.md` 汇总表和分段表中的税值明显偏高或不匹配：

| 场景 | 文档税值 | 按 Ledger tier 估算 | 问题 |
|---|---:|---:|---|
| 5 房，约 40% 存储 | 15 | 10 | tier1 仅 100k 资源应纳 1bp |
| 10 房，约 55% 存储 | 45 | 25 | tier1 仅 250k 资源应纳 1bp |
| 20 房，约 70% 存储 | 120 | 80 | tier1 30 + tier2 50 |
| 50 房，约 90% 存储 | 600 | 255 | tier1 30 + tier2 125 + tier3 100 |

影响：
- 反雪球证明的净流量数值被污染。
- 实现方可能按 Balance Sheet 数值反推错误税率。
- 后续 playtest 无法判断是公式错还是参数错。

建议：
- 将 Balance Sheet 中所有存储税值重算，或明确这些税值使用了不同容量/存储额假设。
- 在表格中补充 `storage_capacity` 与 `storage_amount`，避免只写百分比。
- 将 `Resource Ledger §2.2` 公式中的 `taxable_in_tier` 明确为资源量而非百分比：`taxable_amount_in_tier = capacity × pct_width / 100`。

### 2. 新玩家转移锁语义冲突

`gameplay.md` 表述为：新玩家前 N tick “不得向其他玩家 transfer 资源”。

`Resource Ledger §2.1/§2.5` 表述为：`new_player_transfer_lock` 是 player↔player 双向锁，禁止发送与接收，覆盖 AlliedTransfer、本地 player transfer、未来 ContractSettlement。

影响：
- 如果实现按 gameplay，只禁止发送，则小号仍可接收老玩家输血，破坏反 smurf。
- 如果实现按 ledger，产品文档会误导玩家与服主。

建议：
- 以 Ledger 为准，统一所有文档表述为“双向锁：禁止发送与接收”。
- `gameplay.md` 的 New Player Resource Gate 增加：锁定期内不可接收 AlliedTransfer / player transfer / contract settlement。
- 明确 lock 不影响自身账户内 GlobalDeposit/GlobalWithdraw、PvEAward、RecycleRefund、BuildCost、SpawnCost。

### 3. Resource Ledger 执行顺序存在自相矛盾

`economy-balance-sheet.md` 说维护费对应 Resource Ledger `UpkeepDeduction` 操作“执行顺序第 1 步”。

但 `Resource Ledger §4` 列表中第 1 步是 `WorldStartupSubsidy`，第 2 步才是 `UpkeepDeduction`。

影响：
- 首 tick 新玩家是否先拿 starting resources 再扣 upkeep 会影响死亡螺旋与免费期边界。
- TickTrace 回放与经济报表可能出现 off-by-one 分歧。

建议：
- 统一为：`WorldStartupSubsidy` 是首次进入的一次性前置操作；常规每 tick 的第一个周期性操作是 `UpkeepDeduction`。
- 在 Balance Sheet 中改成“周期性结算第 1 步”或“总序第 2 步”。

## P1：高优先级问题

### 4. PvE Merchant 与 Ledger out-of-scope 冲突

`modes.md` 定义 Merchant NPC：不可攻击，与之交互触发交易事件。

但 `Resource Ledger §7` 将 `Merchant NPC` 标为 Out-of-Scope，替代方案为空。

影响：
- 如果 Merchant 交易产生资源或兑换，就绕开当前 Resource Ledger 的已定义入口。
- 如果 Merchant 只是叙事/非资源事件，当前文档没有说明，容易被实现成隐藏 faucet/transfer。

建议：
- R39 内将 Merchant 明确为“无资源结算，仅非经济事件”，或从当前 PvE 表中移除。
- 若保留交易，必须新增 `MerchantTrade` ResourceOperation，并定义 fee、budget、执行顺序与 TickTrace 归因。

### 5. PvE drop 绑定缺少账本级约束

`gameplay.md` 写有 `new_player_pve_drop_bound = true`，前 N tick PvE 掉落绑定账号不可交易/转移。

`Resource Ledger` 只说明 transfer lock 不影响 `PvEAward`，但没有定义“绑定资源”的数据模型、解锁规则、消费范围。

影响：
- 新玩家可通过 PvE 获取资源后用于 Spawn/Build，这合理；但是否可 GlobalDeposit、Recycle 变换后转移不清楚。
- 绑定资源如果和普通 Energy 混合，会丢失可审计性。

建议：
- 在 Ledger 中定义 `bound_until_tick` 或 `resource_bucket = bound/unbound`。
- 明确绑定资源可用于自身 Build/Spawn/Upkeep，禁止 AlliedTransfer/player transfer/contract settlement。
- 明确经过 GlobalDeposit/Withdraw、RecycleRefund 后是否保持绑定属性，建议保持 taint 直到锁期结束。

### 6. 联盟转移防滥用还不完整

当前 Allied Transfer 已有：2% fee、200 tick delay、500 tick cooldown、receiver daily cap、同盟 ≥100 tick、双方非新手锁。

仍缺少：
- 多联盟/退盟/重入盟绕过冷却的处理。
- 通过中间号链式转发规避 daily cap 的策略约束。
- `allied_daily_cap` 的“每日”在 tick 制中的窗口定义（rolling 24h / UTC day / server epoch）。
- in-transit 资源是否可被拦截、取消、过期、部分送达的账本状态。

建议：
- 将 cap key 定义为 `(receiver_player_id, resource_type, rolling_window_ticks)`，而非联盟关系本身。
- 加入 `allied_transfer_recent_sender_set` 或对 receiver 总入口限额，避免多发送方分摊绕过。
- 定义 `InTransitTransfer` 状态：created_tick、arrival_tick、source、target、fee_paid、interceptable、cancel_policy。

### 7. PvE faucet 预算方向正确，但缺少竞争分配细节

`Resource Ledger §3` 定义 Global/Zone/Player/Event 四维预算，方向正确。`modes.md` 也声明 NPC 掉落总量 ≤ 世界再生总量 ×30%。

主要缺口：
- 同 tick 多玩家击杀贡献比例中，“先到先得、overkill 不额外产出”与“按贡献比例分配”并列，语义略冲突。
- Zone budget 的 `区域基础再生` 如何计算未定义。
- PvE 事件 `Resource Boom` 会使全局再生 ×2，但 PvE cap 是基于 boom 前还是 boom 后再生没有说明。

建议：
- 明确贡献分配顺序：先计算有效伤害贡献，再按预算裁剪，不用“先到先得”。
- 定义 Zone 口径：固定地理 zone / room ring / dynamic density zone。
- 明确 PvE cap 基于“事件修正后的实际世界再生”还是“基础世界再生”，建议基于基础再生，避免 boom 同时放大 PvE faucet。

## P2：中等优先级问题

### 8. 经济曲线依赖代码效率乘数，需标记为设计假设而非协议保证

Balance Sheet 的 2–10 房自维持依赖 1.5×–2.0× 代码效率。该设计合理，但不属于引擎保证。

建议：
- 保留“canonical target curve”描述。
- 在实现验收中不要要求所有玩家 2–10 房自动盈利，而是要求“在假设效率样本下曲线成立”。
- 后续 playtest 指标应采集 idle ratio、path length overhead、harvest uptime，而不只看房间数。

### 9. 维护费只按 rooms 计算，drone 规模约束不够清晰

Ledger 的 Empire Upkeep 公式按 rooms 超线性计算；Balance Sheet 中 50 房额外写了 Drone upkeep 1000，但 Ledger 的默认公式没有显式 drone upkeep 项。

影响：
- 如果 drone upkeep 来自其他模组或 body age 维护，应注明权威位置。
- 否则大帝国可以用极高 drone 密度提高局部收益，只受 room cap 与 age 维修限制。

建议：
- 在 Ledger 中明确默认 Vanilla 是否包含 `drone_count` 项。
- 若不包含，Balance Sheet 的 `Drone upkeep` 应改名为 “drone replacement/repair amortization” 并引用公式。

### 10. Tutorial/Novice/Standard 参数整体合理，但部分默认值需统一

观察到：
- `gameplay.md` 核心默认值写 Controller 维修硬上限 50%。
- `economy-balance-sheet.md` 模式表写 Vanilla/Standard `repair_cap = 3500 bp (35%)`，Tutorial 50%。
- `Resource Ledger §2.4` 权威公式写默认 `repair_cap = 3500 bp`。

建议：
- `gameplay.md` Vanilla 核心默认值改为 Standard/Vanilla 35%，Tutorial 50%。
- 避免“硬上限 50%”被理解为所有模式默认值。

## 正向结论

### 经济曲线

- 超线性维护费 `base_upkeep × rooms × (1 + rooms / room_soft_cap)` 能形成明确递减边际收益。
- 1 房 free upkeep + starting resources 能覆盖新手死亡螺旋风险。
- 2–10 房小幅盈余、20 房后亏损、50 房软上限的目标语义清晰。
- 存储税 + 全局转移损耗 + withdraw delay 能抑制“无限全局仓库即刻补给”。

### 转移锁

- Ledger 将 new player lock 设计为双向锁是正确方向。
- 锁不影响自身 GlobalDeposit/Withdraw/PvEAward/Build/Spawn，避免新玩家被经济系统误伤。
- 需要把 gameplay 文案统一到该强语义。

### 联盟

- Restricted Allied Transfer 的 fee/delay/cooldown/cap 组合合理。
- “双方均非新手锁 + 同盟 ≥100 tick”能挡住基础小号输血。
- 需要补充 rolling cap 与中转规避规则。

### PvE

- PvE 作为 World 常驻层，且通过 4 维 budget 控制 faucet，是健康设计。
- Arena PvE Challenge 与 World 资产隔离，避免排行榜挑战污染持久经济。
- 需要处理 Merchant out-of-scope 与 bound drop 的账本建模。

### 反雪球

- 维护费 O(n²) 趋势、存储税、global transfer delay、soft_launch、safe spawn、room drone cap 组合足够形成生态级 anti-snowball。
- 设计明确“不保证个体公平，只保证生态可持续”，与 World 模式定位一致。
- Arena 另行追求竞技公平，模式边界清楚。

## 建议的合入门槛

R39 合入前建议至少完成：
1. 重算或修正 `economy-balance-sheet.md` 所有存储税数值。
2. 统一 `new_player_transfer_lock` 为双向锁，并同步 gameplay/modes/ledger 文案。
3. 修正 Resource Ledger 执行顺序描述。
4. 决定 Merchant 是否进入 R39 经济范围；若进入，补 ResourceOperation。
5. 为 PvE bound drop 增加账本级绑定/taint 规则。

完成以上后，设计经济层可以进入实现/IDL 对齐阶段。