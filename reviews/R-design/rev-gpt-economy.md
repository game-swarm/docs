# R-design Clean-Slate 经济评审 — GPT-5.5

Reviewer: rev-gpt-economy
Scope: 仅阅读 `docs/design/README.md`, `auth.md`, `engine.md`, `gameplay.md`, `interface.md`, `modes.md`, `tech-choices.md` 七个设计文档。

## Verdict: REQUEST_MAJOR_CHANGES

从经济视角看，Swarm 的核心方向成立：可编程 MMO RTS、WASM 公平计算、World/Arena 双模式、轻物流默认、公开规则查询和经济仪表盘，都是能形成长期策略深度的好基础。

但当前设计还缺少“经济守恒与成本归因”的硬合同，且存在几处会直接炸服或破坏长期生态的矛盾：FDB/回放存储预算数字不自洽，World 模式到底是否内置 empire upkeep 前后冲突，PoW 注册成本不足以防 Sybil/free-farm，存储税单位可能高出几个数量级，PvE/资源/全局存储/市场之间没有统一的 faucet-sink ledger。建议在实现前先冻结经济规范，否则很容易得到一个技术上可运行、经济上不可运营的世界。

---

## Strengths / 亮点

1. **World 与 Arena 分离是正确方向**
   - World 接受先发优势和有机不公平；Arena 追求对称、公平、可回放。这避免了 Screeps-like 持久世界常见的“既想 MMO 又想电竞公平”的目标冲突。

2. **AI 与人类同走 WASM 部署路径，经济上公平**
   - MCP 不提供 `swarm_move` / `swarm_attack` 等直接游戏动作，AI 必须生成 WASM，和人类一样受 fuel metering、代码签名、部署规则约束。这能避免 AI player 获得免费控制面优势。

3. **轻物流默认 + 硬核物流可配置，兼顾上手与深度**
   - 模式 B（本地→全局 1%，全局→本地 5%，有时间延迟）是比纯本地物流更易上手、比全局瞬移更有策略性的折中。

4. **反雪球机制方向完整**
   - 累进存储税、维护费、Controller aging、出生安全区、soft_launch、Room cap、SpawnGrace 等机制覆盖了“囤积垄断、帝国无限扩张、新人被堵死、出生即斩”等常见 MMO 经济失败模式。

5. **经济可观测性设计很好**
   - `swarm_get_economy`, `swarm_get_drone_efficiency`, `swarm_get_economy_trend` 和 Web UI 经济仪表盘会显著降低新手学习成本，也方便 AI agent 做宏观策略。

6. **规则可见性与 world.toml 模组模型对经济健康有利**
   - 所有规则对玩家和 AI 完全可见，避免隐藏经济参数导致“黑箱优化”。世界规则可配置也方便社区做不同经济实验。

---

## Concerns / 发现的问题

### A1. Critical — Tick 存储预算与 FDB 事务预算数字严重不自洽

文档给出：
- Tick interval = 3s，所以每天 tick 数 = 28,800。
- FDB transaction size = 16MB。
- `engine.md` 写“Tier1 每日写入预算 ≤ 500GB（按 500 players × 3s tick × 24h × 16MB 估算，含 keyframe）”。

按两种解释计算都不对：
- 如果 16MB 是**每 tick 全局上限**：16MB × 28,800 tick/day ≈ 450GiB/day，接近 500GB，但不应再乘 500 players。
- 如果按文档字面“500 players × 每 tick 16MB”：约 225,000GiB/day，即约 219.7TiB/day。

这不是小数点问题，而是经济模型里的运维成本、回放保留期、服务器最低配置、开服门槛全部会被这个数字支配。

Recommendation:
- 明确区分：`state_delta_per_tick_global`, `snapshot_payload_per_player`, `keyframe_interval`, `ticktrace_retention_days`, `cold_storage_policy`。
- 给出官方 Tier1 的硬预算：例如 `平均 delta <= X KB/tick`, `P99 delta <= Y MB/tick`, `keyframe <= Z MB/100 tick`。
- 加一张“7 天 / 30 天 / 180 天回放保留成本”表，包含 FDB 热存储与对象存储冷归档两层。

### A2. High — World 模式的 empire upkeep 立场前后冲突

`modes.md` 中写：World 领土平衡是 Phase 1+ deferred，不提供硬编码 empire upkeep，社区/模组解决。

但 `gameplay.md` 又把维护费、O(n²) rooms、反雪球合同、帝国维护费示例作为长期经济核心之一，并在 Vanilla / 默认规则附近描述。

这会导致两个严重后果：
- 如果 Phase 1 没有 upkeep，持久世界初期会被先发玩家快速扩张占满，后面再补税会变成“追溯削弱既得利益”。
- 如果 Phase 1 有 upkeep，但文档说 deferred，SDK、UI、经济仪表盘、AI 策略都会对默认世界作出错误假设。

Recommendation:
- 将 empire upkeep 明确分成三层：
  1. Core protocol 支持 `recurring_cost` / `maintenance_ledger`。
  2. Vanilla World 是否默认启用。
  3. 服主是否可关闭或替换。
- 即使不硬编码具体公式，也应在 Tier1 冻结“维护费钩子和账本语义”，否则经济迁移成本太高。

### A3. High — 累进存储税单位疑似高出数量级，可能形成“资产蒸发机”

文档中同时出现：
- “0.20% 每 tick”
- 配置表说明“每10万单位税率”
- 默认 tick interval = 3s

若按“每 tick 百分比”理解：
- 0.20%/tick 的半衰期约 346 tick ≈ 17.3 分钟。
- 0.05%/tick 的半衰期约 1.15 小时。
- 0.01%/tick 的半衰期约 5.78 小时。

这对于持久 MMO 经济过于激进，会把高存储玩家的资产在小时级快速焚毁，玩家感知会接近“服务器偷资源”。如果本意是“每 10 万单位固定税额”，则文案必须重写，否则实现者很容易按百分比做出灾难性经济。

Recommendation:
- 将所有经济参数统一写成 `basis_points_per_10k_ticks` 或 `units_per_100k_storage_per_tick`，禁止“%/tick”和“每10万单位税率”混用。
- 给出典型玩家一天税负示例：30%、60%、85%、100% 容量各存 24h 后剩余多少。
- 税收最好默认进入 sink，不应进入全局池，除非明确设计通胀/通缩目标。

### A4. High — 注册 PoW 无法单独承担 Sybil / free-farm 防护

文档自己估算：默认 `difficulty_bits=24`，每 1000 账号攻击成本约 `$0.10`，且 challenge 申请仅 per-IP 限速。对持久世界来说，只要新账号拥有初始资源、safe_mode、出生空间或 PvE 掉落，攻击者就可以低成本批量创建“资源农场账号”。

PoW 可以挡误用和轻量 spam，但挡不住理性经济攻击。尤其在支持 AI agent 自注册的世界里，批量账号会是自然策略。

Recommendation:
- 明确新账号的经济产出闸门：例如前 N tick 资源不可转移、市场不可挂单、只能本地使用、PvE 掉落绑定、达到 Controller/RCL 门槛后解锁交易。
- 加入 per-server economic quota：同一 trust root / recovery factor / device group 的账号组共享部分冷却或产出上限。
- PoW 难度自适应不应只看注册速率，也要看新账号产出、转移、被封禁、同源行为图。

### A5. High — Faucet/Sink 总账缺失，无法判断长期通胀或通缩

设计里出现多个资源来源和去向：
- Source regeneration。
- NPC/PvE 掉落。
- 全局存储税。
- 建筑与 drone spawn cost。
- deploy cost 默认 0。
- upkeep 可选/冲突。
- market 为 Phase 2，占位但未闭环。

目前没有一个统一的经济账本说明：每 tick 资源从哪里产生、在哪里销毁、以什么速率进入全局流通、哪些是玩家间转移而非 faucet/sink。

Recommendation:
- 新增 `economy-ledger.md` 或在 gameplay 中加入“宏观经济守恒表”。每项规则标注：Faucet / Sink / Transfer / Lockup / Unlock。
- 给 Vanilla World 设定目标：例如在 500 活跃玩家、50k entity 上，资源总量日增长率目标区间是多少。
- PvE `max_pve_output_per_tick <= 世界再生总量 × 30%` 是好开始，但还要定义世界再生总量如何估算，以及是否按区域/玩家分摊。

### A6. Medium — Free deploy + 低 cooldown 可能制造“无成本策略抖动”和存储外部性

World 默认 `code_update_cost=0`，`code_update_cooldown=5 tick`。技术上 WASM 预编译和 module_hash 缓存能处理部署，但经济上免费高频部署会带来：
- 模块存储和审计日志膨胀。
- 玩家可以把策略调参外包给高频 redeploy，而不是在 WASM 内写稳定策略。
- Arena 赛前锁定可以避免，World 模式则没有明确约束。

Recommendation:
- 免费部署可以保留，但需要“存储/审计外部性”预算：每账号保留最近 K 个 module，旧 module 冷归档或 GC。
- 对 World 默认加入 `deploy_version_counter` 与 `module_retention_policy`。
- 可考虑让 deploy cost 不是资源成本，而是冷却、版本槽位、或超额模块存储费，避免惩罚新手。

### A7. Medium — Snapshot cap 的经济归因过于乐观

文档声称“每个玩家 snapshot 大小与自身 drone 数量成正比，不随其他玩家膨胀而增长”，但可见性模型允许当前房间 + 相邻房间，敌方/盟友/NPC/建筑/掉落资源都会进入可见 snapshot。

当敌对玩家在边境堆大量实体，或 PvE 事件在高密度区爆发时，受害玩家的 snapshot 成本会被他人外部化。256KB per-player cap 之后如何截断，会直接影响公平性和策略：看不到敌人是致命的。

Recommendation:
- 定义 snapshot truncation 的经济与公平语义：优先保留什么？敌方攻击者、己方单位、资源、建筑、NPC 的排序规则是什么？
- 将“可见实体造成的 snapshot 压力”纳入反滥用：例如 room entity cap、边境 entity density tax、或攻击者承担部分可见性成本。
- AI/MCP 经济查询不应绕过 truncation，否则 AI 与 WASM 感知会不一致。

### A8. Medium — README 的联邦资产表述与 auth.md 的“身份-only”模型冲突

`README.md` 愿景写：联邦宇宙可“转移资源、共享排名”。

`auth.md` 后文则明确：联邦身份只用于认证 bootstrap，不共享游戏状态、不共享模块、不共享排名，不共享资产。

从经济视角，这是重大产品/协议边界问题。跨世界资源转移一旦存在，就会引入汇率、套利、通胀传染、低规则世界向高规则世界洗资源等问题；如果不存在，README 的愿景会误导后续设计。

Recommendation:
- 先冻结联邦边界为“identity-only”，资源/排名跨世界全部标注 Future/RFC。
- 如果未来允许资源跨世界，必须单独设计 bridge economics：资产白名单、汇率、手续费、延迟、不可逆性、源世界信任等级、撤销策略。

### A9. Medium — Market 被多处引用但又声明 Phase 2，容易渗入 Tier1 经济假设

`gameplay.md` 中 Storage/Terminal/Market order、账号删除的 market order 回滚、全局存储交易、Terminal 建筑等多处已经依赖 market 概念；但经济治理又声明 Market 为 Phase 2 候选，当前只保留接口占位。

如果 Tier1 实现没有 market，这些资源流和建筑价值会失真；如果有半成品 market，会是经济攻击面。

Recommendation:
- Tier1 Vanilla 中将 Terminal/market 字段标为 inert，明确不可用行为。
- 账号删除、资源转移、全局存储说明应避免依赖未启用 market。
- Market RFC 完成前，不应把 market 作为反垄断或物流闭环的组成部分。

### A10. Low — Arena 定位“不做自动匹配/天梯”，但 PvE Challenge 又有全局排行榜

Arena 模式写“无自动匹配、无天梯排名、无赛季”，后文 PvE Challenge 又有 scenario+difficulty 全局排行榜。两者不必冲突，但需要清晰产品语义：PvP 无天梯，PvE 有 leaderboard。

Recommendation:
- 将 Arena 排名表述改为：PvP MVP 无 matchmaking/ladder；PvE Challenge 可有 leaderboard；未来 PvP leaderboard 另走 RFC。

---

## Missing / 缺失项

1. **Economy Ledger（宏观经济总账）**
   - 每个资源动作标注 Faucet/Sink/Transfer/Lockup/Unlock。
   - 给出 Vanilla World 的目标通胀率、资源总量增长曲线、玩家生命周期资源曲线。

2. **Retention & Storage Economy（回放/模块/审计存储经济）**
   - TickTrace、keyframe、module binary、compiled artifact、audit log 的保留期和冷归档策略。
   - “服主开一个 500-player Tier1 世界 30 天需要多少磁盘”的明确表格。

3. **Sybil / Alt-account 经济防护**
   - PoW 之外的新账号产出限制、交易解锁、转移冷却、风险评分。

4. **Default Vanilla 参数校准依据**
   - 存储税、upkeep、source regen、PvE drop、spawn cost、drone lifespan 等参数目前像是合理草案，但缺少目标函数和模拟结果。

5. **Economic Migration Policy**
   - 当世界规则改变（税率、upkeep、资源类型、market 启用）时，既有资产如何迁移？是否需要公告期、快照、补偿、回滚？

6. **World Owner / Server Operator 激励**
   - 开源自托管很好，但持久世界的存储、带宽、CPU 成本需要运营激励或至少成本透明。否则官方默认参数可能让社区服主低估长期成本。

---

## Phase Ordering / 设计冻结顺序建议

这里的 Phase Ordering 不是实现分期，而是“设计应先冻结哪些经济合同，再允许进入编码”。

1. **先冻结经济不变量**
   - Tick 存储预算、资源 faucet/sink ledger、Vanilla World 是否启用 upkeep、市场是否 Tier1 inert。

2. **再冻结玩家生命周期曲线**
   - 新账号前 0/500/1500/5000 tick 的资源产出、保护、交易权限、PvP/PvE 可达性。

3. **再冻结成本归因**
   - Snapshot cap 超限归因、entity cap 归因、module retention、deploy audit 成本。

4. **最后冻结可调参数默认值**
   - 存储税率、upkeep 公式、PvE 掉落、source regen、global/local 转换成本。默认值必须来自模拟或至少来自明确的目标函数。

---

## Recommendations / 总建议

1. 新增一份 `design/economy.md`，不要把经济规则散落在 gameplay/modes/auth/engine 中。
2. 把所有经济数字统一单位：per tick、per 10k ticks、per day、basis points、固定单位，不要混用自然语言百分比。
3. 先把 Vanilla World 定义成一个可模拟的闭环：500 玩家、50k entity、30 天运行，输出资源总量、存储成本、税负、玩家扩张曲线。
4. 把联邦资源转移、market、深度 PvE、Layer3 经济模组全部标为 Future，Tier1 只保留不会影响当前经济闭环的 inert schema。
5. 保留当前强项：AI/人类同 WASM、MCP 只做观察/部署、经济仪表盘、规则完全可见。这些是 Swarm 相比 Screeps 的真正经济差异化。
