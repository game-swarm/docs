# R41 Design & Economy Review — rev-dsv4-design-economy

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

经济平衡表的算术错误使 anti-snowball 证明不可信；Controller 老化「硬上限 50%」在多个文档间存在矛盾定义；global↔local 运输拦截仅定义了 Allied Transfer 而未覆盖 global transfer 路径。此外存在若干中低严重度问题需修复。修齐后重新评审。

---

## 2. 发现的问题

### 2.1 Critical

#### C1 — economy-balance-sheet.md 存储税算术错误（多处）

- **文件**: `/tmp/swarm-review-R41/design/economy-balance-sheet.md`
- **位置**:
  - L120: 10-room scenario（capacity=3,000,000, stored=1,650,000, pct=55%）
  - L143: 20-room scenario（capacity=2,000,000, stored=1,440,000, pct=72%）
  - L167: 50-room scenario（capacity=3,000,000, stored=2,700,000, pct=90%）
  - L188: 汇总表 10-room / 20-room / 50-room 列值
- **问题描述**: 存储税计算按照 Resource Ledger §2.2 tiered 公式重算后，与表中数值不一致：

  | Scenario | 表值 | 公式推导值 | 差异 |
  |----------|:----:|:---------:|:----:|
  | 10-room | 45 | 75 | −30 |
  | 20-room | 120 | 180 | −60 |
  | 50-room | 600 | 765 | −165 |

  以 10-room 为例（capacity=3,000,000, stored=1,650,000, pct=55%）：
  - Tier 1 (30%–60%): `min(1,650,000 − 900,000, 900,000) = 750,000`, `750,000 × 1bp / 10000 = 75`
  - 表值 45 与公式结果矛盾；表中文字推导 `750,000 × 1bp / 10000` 本身已得出 75，但列值却写为 45
- **影响**:
  - `economy-balance-sheet.md` §4「Anti-Snowball 证明」依赖这些数值论证自然天花板
  - 若真实税负高于表中值 33%–67%，anti-snowball 效果更强（实际更有利），但设计文档的可信度受损
  - 汇总表（L182–190）的「净流量趋势」列（如「优化小幅盈余」「优化收支平衡」）需要基于正确数值重新评估——正确定税后部分场景的 net flow 会更低
- **修复建议**:
  1. 以 Resource Ledger §2.2 tiered 公式为唯一权威源逐行重算全部 6 个 scenario（含汇总表）
  2. 重算后重新评估各场景的「盈亏判断」和 §4 的 anti-snowball 证明论证
  3. 建议添加 CI 自动校验脚本：从 Resource Ledger 参数出发程序生成 balance sheet 数值

#### C2 — Controller 老化「硬上限 50%」概念矛盾

- **文件**: 多文件
  - `design/gameplay.md` L437: 「Controller 老化: age 增长 → 修缮成本上升 → 硬上限 50%」
  - `specs/core/08-resource-ledger.md` §2.4: Controller repair 免费，受 range/capacity/queue 约束
  - `design/economy-balance-sheet.md` §3: `controller_repair_cost = 0`
  - `design/gameplay.md` L503 (Vanilla Ruleset 汇总): 「硬上限：每 tick 总 age 回退 ≤ 自然增长的 50%」
- **问题描述**:
  - 「Controller 老化」在 anti-snowball 表中暗示修缮成本随 age 增长而上升
  - 「Controller repair」（resource-ledger §2.4）定义的是 **drone age** repair（Controller 作为修理设施），且明确免费
  - Vanilla Ruleset 汇总中的「硬上限 50%」是对 **repair bandwidth** 的限制（每 tick 最多回退自然增长量的 50%），但仅在 Vanilla 汇总表中出现——三个权威经济文档正文中均无此限制
  - 读者无法区分「Controller 自身 age/level 老化」与「Controller 为 drone 提供 age repair」两个完全不同概念
- **影响**: 
  - 实现者若按「Controller 老化 → 修缮成本上升」理解，会在 Controller repair 路径引入成本逻辑——但 resource-ledger 明确这是免费功能
  - 若「硬上限 50%」是一个真实限制，它需要出现在 Resource Ledger 权威定义中；若只是过时表述，应从 anti-snowball 表中移除或改写
- **修复建议**:
  - **D-item**：请裁决以下两项
    - (a)「硬上限 50%」是否应作为 Controller drone-age-repair 的 bandwidth limit 进入 Resource Ledger §2.4？若是，应定义精确的「自然增长」基线（全局/每玩家/每 drone 口径）
    - (b) anti-snowball 表中的「Controller 老化: age 增长 → 修缮成本上升」应改写为何种表述？建议：「Controller repair bandwidth: 每 tick 总 age 回退量 ≤ 自然增长量的 50%，随玩家规模增大 repair queue 自然拥堵」
  - 裁决后，确保 gameplay.md anti-snowball 表、resource-ledger.md §2.4、economy-balance-sheet.md §3 三者一致

#### C3 — Global↔local 运输拦截未覆盖非 Allied 路径

- **文件**:
  - `design/gameplay.md` L353: 「转换期间资源处于'运输中'状态——可被敌方巡逻 drone 拦截（需 PvP 启用）」
  - `specs/core/09-snapshot-contract.md` §3.2a (L222–261): **仅**定义 Allied Transfer 拦截机制（200 tick 窗口最后 50 tick）
- **问题描述**:
  - gameplay.md §8 承诺 global↔local transfer 的运输中资源可被拦截
  - snapshot-contract.md §3.2a 的拦截机制仅覆盖 Allied Transfer（200 tick delay, last 50 tick intercept window）
  - Global deposit 延迟仅 10 tick，global withdraw 延迟 100 tick——这些延迟窗口内是否有拦截机制？若有，哪些 tick 可拦截？成功率公式是否与 Allied 拦截相同？
  - 若 Global transfer 不可拦截，则 gameplay.md 的承诺为虚假陈述；若可拦截，则缺失设计
- **影响**: 物流战的战术深度取决于运输中资源的可攻击性。若只有 Allied Transfer 可拦截而 Global transfer 不可拦截，global 存储成为无风险物流通道
- **修复建议**:
  - **D-item**：请裁决 global transfer intercept 是否在核心范围内
    - 选项 A：Global deposit/withdraw 延迟期间均可拦截（窗口定义、成功率公式同 Allied）
    - 选项 B：仅 Allied Transfer 可拦截，gameplay.md 修正为「仅联盟转移可被拦截」
    - 选项 C：Global transfer 不可拦截但后续通过 Rhai mod 实现（此为最终设计延迟）
  - 裁决后 snapshot-contract.md §3.2a 标题改为「Transport Intercept Contract」，覆盖全部三条运输路径

### 2.2 High

#### H1 — 1-room 玩家 free_upkeep 结束后的死亡螺旋窗口过窄

- **文件**: `design/economy-balance-sheet.md` §2.1
- **位置**: L61–62
- **问题描述**:
  - Standard 模式下，free_upkeep 结束后基础收入 22/tick vs 维护费 55/tick → 净亏损 −33/tick
  - 初始资源 5,000 Energy 仅支撑 ≈152 tick
  - 从 1 room 扩展到 2 rooms 需要：进入新房间 → Claim Controller → 等待 Claim 成功 → 升级 RCL 到可维持 drone → 部署 harvester。此过程很可能 >152 tick，尤其对新玩家
  - economy-balance-sheet.md 未分析此过渡路径的资源储备需求
- **影响**: 新手在 free_upkeep 结束后若未能及时扩张，将面临资源枯竭导致 drone 饥饿死亡 → 进一步无法扩张 → 死亡螺旋。这背离「中期自维持可达」设计目标
- **修复建议**:
  - 在 balance sheet 中增加「1→2 room 过渡路径」的资源需求分析（Claim 成本 + Spawn 成本 + 运输时间内的 maintenance deficit）
  - 考虑延长 Standard 模式的 `free_upkeep_ticks` 至使 1→2 room 过渡在时间窗口内可达的值（如 2500–3000），或以 `starting_resources` 的规模弥补

#### H2 — AlliedTransfer 日志写入 TickTrace 但未定义归因格式

- **文件**: `specs/core/09-snapshot-contract.md` §3.2a L260 vs `specs/core/08-resource-ledger.md` §5
- **问题描述**: 
  - snapshot-contract.md L260: 「每次拦截尝试记录：(transfer_id, attacker_player_id, ...)」
  - resource-ledger.md §5: TickTrace 归因格式仅定义 `op: LocalTransfer` 等标准操作，不含拦截产出的 `InterceptSuccess` / `InterceptFail` 操作类型
  - 拦截成功后攻击方获得的 50% 资源（steal 模式）需要进入 Resource Ledger 作为收入（`Faucet`？`Transfer`？），但 §1 操作表中无对应 `ResourceOperation` 变体
- **影响**: 实现时拦截的资源流入没有标准账本入口，破坏「确定性账本」原则
- **修复建议**: 在 resource-ledger.md §1 新增 `InterceptAward` 操作类型，归类为 `Transfer`（从被拦截的 transfer 中转出至攻击方），并在 §5 TickTrace 归因中补充拦截操作格式

#### H3 — Per-player snapshot 粒度与实际 WASM tick 执行粒度矛盾

- **文件**: `specs/core/09-snapshot-contract.md` §1 vs `design/gameplay.md` §2.5
- **问题描述**:
  - snapshot-contract.md §1.1: 「引擎在每 tick 结束时为每个 **player** 生成感知快照」
  - gameplay.md §2.5 / interface.md §5: WASM tick(snapshot) 的 snapshot 交付粒度是 per-drone 还是 per-player？
  - 若为 per-player，一个玩家的所有 drone 共享同一 256KB snapshot——这符合「actor context」设计（§1.1 含 active_drones 列表）
  - 但 §1.4 关键实体包含「自身 drone」「己方所有 drone」，若多个 drone 分布在不同房间，视野集合远超 256KB 怎么办？
- **影响**: snapshot 截断合同的设计合理性取决于粒度——per-player snapshot 在 drone 分布广时更容易触发截断
- **修复建议**: 在 snapshot-contract.md §1.1 显式声明「per-player perception snapshot」是否意味着每个 WASM tick() 调用接收基于该 player 全部活跃 drone 的合并视野快照；并评估 multi-room player 的截断触发频率

### 2.3 Medium

#### M1 — economy-balance-sheet.md §2.1「总收入 77」表头误导

- **文件**: `design/economy-balance-sheet.md` L49
- **问题**: 表列「总收入 77」实际含 free_upkeep benefit（55/tick 免维护），而基础收入仅 22/tick。表头未区分「income + free_upkeep_benefit」和「true income」
- **修复**: 表增加「free_upkeep 覆盖」独立行，将「总收入」拆为「基础收入」+「免维护收益」=「可用余额」

#### M2 — Vanilla Action 成本数值在 gameplay.md 与 ActionRegistry 间的冗余

- **文件**: 
  - `design/gameplay.md` L759–766（8 special attack 成本表）
  - `design/gameplay.md` L1158–1218（ActionRegistry vanilla action 配置块）
- **问题描述**: 
  - L759 表中 Hack cost = 1000 Energy，L1163 action_registry.vanilla.Hack cost = { Energy = 1000 }——两表一致 ✓
  - 但 Fabricate：L766 表中 cost = 800 Energy，L1218 action_registry.vanilla.Fabricate cost = { Energy = 2000 }——**不一致！**
  - L765 Fortify：表中 cost = 400 Energy，L1199 cost = { Energy = 400 }——一致 ✓
  - L764 Disrupt：表中 cost = 100 Energy，L1192 cost = { Energy = 100 }——一致 ✓
- **影响**: Fabricate cost 800 vs 2000 是 2.5x 差异，直接影响经济平衡
- **修复**: 统一 Fabricate 成本为单一值；若以 ActionRegistry canonical 值为准（2000），修正概念表 L766

#### M3 — allied_daily_cap GCL 缩放公式仅在 gameplay.md 和 resource-ledger.md 中一致，balance-sheet 未提

- **文件**: `design/economy-balance-sheet.md` §3 L226 vs `specs/core/08-resource-ledger.md` §2.1 L82–84
- **问题**: balance-sheet 仅写 `allied_transfer: enabled (Restricted)` 及 fee/delay/cooldown，未提 GCL 缩放
- **修复**: balance-sheet §3 补充 `allied_daily_cap = max(10,000, receiver_gcl × 20,000)` 并说明不同模式 multiplier

#### M4 — Resource Ledger §6「Recycle 权威公式见 §2.5」重复声明

- **文件**: `specs/core/08-resource-ledger.md` L301
- **问题**: §2.5 已定义 Recycle 公式，§6 末尾再次重复——但 §6 标题是「ResourceAmount/ResourceRate 定点建模」，与 Recycle 无关
- **修复**: 删除 §6 末尾重复的 Recycle 段落（L301），该内容移至 §2.5

#### M5 — 10-minute golden path 未体现 free_upkeep 结束后的经济现实

- **文件**: `design/gameplay.md` §1
- **问题**: Golden path 描述 「登录 → 10分钟 → 首个 PvE 挑战」，但 Tutorial 世界 `code_update_cost = 0`、`fog_of_war = false`、`new_player_transfer_lock_ticks = 0`——这描述了 Tutorial 世界的体验，玩家在 Tutorial 中不会感知到经济压力
- **修复**: 在 golden path 末尾添加过渡说明：「Tutorial 完成后，玩家进入 Standard World 时将面对经济约束（维护费、存储税、代码部署成本），建议在 Tutorial 中练习经济效率优化」

### 2.4 Low

#### L1 — `Direction` vs `Direction4` 术语歧义

- **文件**: `specs/gameplay/08-api-idl.md` L62 vs `specs/reference/api-registry.md` §7
- **问题**: IDL 用 `Direction` 作为 enum 名，API Registry 用 `Direction4`——两者一致（4 方向），但名称不统一
- **修复**: 选择 `Direction4` 为 canonical 名称，IDL 同步更改

#### L2 — economy-balance-sheet.md 缺少 Tutorial / Vanilla 数值验证

- **文件**: `design/economy-balance-sheet.md`
- **问题**: §2 仅覆盖 Standard 模式的 1/2/5/10/20/50 房间，Tutorial (base_upkeep=10, soft_cap=20) 和 Vanilla (base_upkeep=30, soft_cap=15) 的收支表未验证
- **修复**: 添加 Tutorial 和 Vanilla 模式的简化收支验证（至少 1/5/10 房间），确认各模式经济曲线符合预期

#### L3 — Healer body part「只能恢复 HP，不能降低 age」与 active_aging 的交互未明确定义

- **文件**: `design/gameplay.md` L102
- **问题**: Healer 不能降低 age——那么「active drone 的 age 加速」是不可逆的（只有 Controller/Depot 维修可降低）。这是否是设计意图？若一个 drone 从未靠近 Controller/Depot，其 lifespan 严格为 1500/1.1 ≈ 1364 ticks
- **修复**: 在 drone lifecycle 段明确确认：age 加速不可逆（仅 Controller/Depot 可降 age），Healer 仅处理 HP。这不是 bug，但需要明确声明作为设计约束

---

## 3. 亮点

1. **单一权威分层架构设计优秀**：Resource Ledger 作为经济唯一数学权威、API Registry 作为所有接口的单事实源、Snapshot Contract 作为截断唯一权威——三层权威明确且交叉引用清晰，大幅降低跨文档不一致风险。这是 R15/R22/R33 多轮修复的成果体现。

2. **Anti-snowball 机制层次分明**：累进存储税 + O(n²) empire upkeep + 物流延迟 + 拦截窗口 + room drone cap 形成多层反雪球网，每层覆盖不同滥用路径（囤积、扩张、物流规避、局部碾压）。设计有博弈论深度。

3. **经济分类账 (Faucet/Sink/Transfer/Lockup/Unlock) 清晰**：五分类法使得资源总量守恒验证变得可机械化检查——每 tick 可审计 `Σ faucets − Σ sinks = Δ total`。这是「确定性账本」的重要基础设施。

4. **PvP 渐进过渡（First-Attack Shield）设计精良**：分 Phase 1/2/3 的 soft_launch 过渡 + shield/cooldown/visible_attacker 三机制设计用心，有效缓解「保护期结束瞬间被清场」的经典 MMO 痛点。

5. **Arena PvE Challenge 与 World PvE 平行设计**：Arena 的 PvE 挑战是隔离沙盒、不影响 World 经济——避免了「通过 Arena 刷 PvE 资源注入 World」的逃逸路径。设计有经济整体性意识。

6. **Allied Transfer 拦截的确定性 RNG**（`Blake3("intercept" || transfer_id || tick || world_seed)`）与 escort 防御机制为物流战提供了可回放的博弈基础——这是「最终设计」而非 MVP 占位的正确态度。

---

## 4. CrossCheck — 需要跨方向检查

以下问题超出 Design & Economy 方向范围，需要对应方向 reviewer 确认：

- **CX-1**: 存储税 tier 边界（30/60/85/100%）在各文档中一致，但 Resource Ledger §2.2 的 `floor(stored_pct)` 与 gameplay.md 的 `storage_pct` 计算细节（是否 floor、是否用 capacity 百分比 vs 单位）存在微妙差异 → 建议 **Security reviewer** 检查 `storage_pct` 的精确整数运算是否能被玩家通过微调存储量操纵 tier 边界（即「threshold gaming」）
- **CX-2**: snapshot-contract.md §1.5「degradation」标记的设计意图是通知竞技平台 tick integrity——但此信息的暴露是否会被攻击者利用（如故意触发 degradation 来干扰竞技裁判）→ 建议 **Security reviewer** 检查 degradation 信号的滥用路径
- **CX-3**: Fabricate cost 800 vs 2000（M2）的差异已标记——需确认 `special-attack-table.md`（不在本次评审范围内）中的权威值 → 建议 **Gameplay reviewer** 检查 special-attack-table.md 并裁决最终值
- **CX-4**: economy-balance-sheet.md 中 10-room 的 efficiency multiplier 用「×1.33 效率 (= ×2.0 总计)」表示法令人困惑——`source × efficiency × efficiency = 2× source` 的双重乘数含义 → 建议 **Technical Writer / Consistency reviewer** 统一所有文档的效率乘数表示法