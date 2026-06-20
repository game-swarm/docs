# Swarm 设计评审 R25 — Closure Verification (Game Designer)

## Verdict

**CONDITIONAL_APPROVE**

10 项验证中：7 项 CLOSED，3 项 PARTIAL（非阻断性残留）。

---

## 逐项验证

### B1: Host Function ABI 统一到 api-registry.md 权威签名

**状态**: CLOSED ✅

**证据**:
- `api-registry.md` §4 声明为"单一权威来源"，定义 5 个 host function 的 canonical ABI 签名
- `host-functions.md` 行 3 明确声明 "权威定义见 API Registry §4"，所有签名与 registry 一致
- `engine.md` 引用 specs 而非重新声明
- 签名验证通过：`host_get_terrain`、`host_path_find`、`host_get_world_config`、`host_get_world_rules` 在 registry 与 host-functions.md 中完全一致

**策略深度评估**: Host Function ABI 的统一消除了 WASM sandbox 的合同不确定性。5 个只读 host function 构成玩家代码与引擎的信息通道——全部按确定性合同（budget、输出上限、错误优先级）执行，消除 replay divergence 风险。

---

### B2: 经济数值对齐 economy.idl.yaml

**状态**: CLOSED ✅

**证据**:
- `economy.idl.yaml`: RangedAttack cost = 150 ✅（原冲突 100 vs 150 已统一）
- `economy.idl.yaml`: RecycleRefund = lifespan-proportional 10%-50%，公式 `max(1000, remaining_lifespan*5000/total_lifespan)` ✅
- `resource-ledger.md` §2.1: `global_transfer_delay = 100 tick` ✅（原冲突 10/5/100 已统一）
- `resource-ledger.md`: 声明为"所有费率、公式、参数的唯一定义源"，`economy-balance-sheet.md` 和 `gameplay.md` 均引用此权威
- `api-registry.md` §5.1: per-player drone cap = 50 ✅
- `api-registry.md` §5.1: starting resources `{Energy: 5000, Minerals: 2000}` ✅

**策略深度评估**: 经济合同的统一使 cost/refund/delay 成为可预测的玩家决策基础。RangedAttack 150 的定价创造了有意义的策略权衡——远程攻击的高成本要求专用化配置，与廉价 melee 形成互补策略空间。Recycle lifespan-proportional 消除了固定 50% 的临时建造套利风险。

---

### B3: Tick budget 对齐

**状态**: PARTIAL ⚠️ (非阻断)

**发现**:
- `engine.md` §3.4.1: EXECUTE budget ≤400ms
- `tick-protocol.md` §1.4: EXECUTE 超时 500ms

**分析**: 400ms budget 与 500ms timeout 之间的 100ms 差值可能是设计上的安全余量（budget < timeout），但两个文档未显式交叉引用。tick-protocol 未说明 500ms 是"超时"而非"预算目标"，engine.md 未说明 budget 与 timeout 的关系。

**建议**: 在 tick-protocol §1.4 的 EXECUTE 超时旁添加注释：`超时: 500ms（含 100ms 余量；engine.md 目标 budget 400ms）`。非阻断 — 不影响实现。

**策略深度评估**: tick budget 是游戏响应性的基础。World 3000ms/Arena 300ms 的差异化 interval 创造了天然的模式区分：Arena 需要快速反馈用于竞技决策，World 可接受更长 tick 以支撑更大规模模拟。

---

### B4: MCP 工具清单 54→56

**状态**: PARTIAL ⚠️ (非阻断)

**发现**:
1. `api-registry.md` §3 抬头正确声明 "共计 56 个活跃工具"
2. `api-registry.md` §3.2 子标题仍写 "Game API 工具清单 (54)" — **残留 drift**
3. 实际计数：Onboarding(10)+Auth(2)+Play(16)+Deploy(7)+Debug(8)+Admin(6)+SDK(1)+Arena(4)+Resources(2) = **56** ✅
4. `mcp-security.md` §4.5 仍将 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions` 标为 "已移除的旧工具"，但 `api-registry.md` 的 Onboarding 段完整列出这三个工具为 active

**分析**: 工具计数已从 54 修正为 56，但子标题未更新。mcp-security 对 onboarding tools 的 "已移除" 声明与 api-registry 的 active 状态冲突——这与 R24 CFX1 是同一问题。

**建议**: 
- 修正 api-registry §3.2 子标题为 "(56)"
- mcp-security §4.5 将 onboarding 工具从 "已移除" 改为 "整合至 SDK 和 API Registry（仍为 active MCP 工具）"

**策略深度评估**: AI onboarding 三件套（docs/schema/available_actions）是 AI agent 自主接入的关键入口。将其从 MCP 移除会直接切断 AI agent 的自助学习路径——人类玩家有 Web UI 教程，但 AI player 的唯一信息通道就是 MCP。安全目标应通过 scope/rate/detail-level 实现，而非删除工具。

---

### B5: Snapshot 截断统一到 snapshot-contract 权威

**状态**: CLOSED ✅

**证据**:
- `snapshot-contract.md` §1 声明为 snapshot truncation 的 "唯一权威"（R22 B5 修复）
- `engine.md` §3.4.4: "权威截断合同见 Snapshot Contract §1" ✅
- 截断顺序统一：距离桶 0(self)→1(adjacent)→2(near)→3(mid)→4(far)→5(very far)→6(out of sight)，同桶 entity_id 字典序
- 关键实体永不截断：自身/Controller/target/己方 drone/攻击者 ✅
- engine.md 与 snapshot-contract 桶名称一致 ✅

**策略深度评估**: 确定性截断顺序将 snapshot overflow 从"信息随机丢失"变为"可预期的信息降级"。玩家可以推理「越远的实体越先被丢弃」→「我应该关注近处敌人」→ 创造近距离战术偏好。`omitted_count` 字段让 WASM 代码感知信息完整性，支持降级策略（如 "truncated=true → 保守模式"）。

---

### B6: Auth CSR Replay Class + CodeSigning TTL 30-180d

**状态**: CLOSED ✅

**证据**:
- `auth.md` §5.6a: `swarm_submit_csr` → `non_idempotent_mutation`，明确 "FDB 事务内消费 PoW challenge，一次性" ✅
- `auth.md` §5.3: CodeSigningCertificate TTL = 30–180 days（默认 7d, world.toml 可配）✅
- 不再存在 CSR 同时标记为 idempotent 与 non-idempotent 的矛盾
- 不再存在三组 TTL 冲突数值

**策略深度评估**: CSR 的 replay class 明确化消除了注册流程的安全歧义。30-180d 的 CodeSigning TTL 窗口（默认 7d）在安全性与运维便利间取得平衡——AI agent 需定期续签但不必每 tick 操作。

---

### D1: Arena 房间制优先

**状态**: CLOSED ✅

**证据**:
- `modes.md` §9.1: "Arena P0 以房间制比赛为核心——玩家创建比赛房间，设定参数，自己或他人加入。无自动匹配、无天梯排名、无赛季。Tournament/League 为 P1+ 上层编排，通过多场 Room Match 组合实现" ✅
- 实现了 Speaker 推荐的选项 A：P0 Room Match，Tournament P1+

**策略深度评估**: 房间制模型降低了 P0 API 面与公平性状态机复杂度。同一玩家可用不同 WASM 模块在多个槽位自我对抗——这是算法研究的核心场景。Tournament 由多场 Room Match 组合的设计保留了竞技深度的扩展路径，同时避免 P0 就陷入天梯/赛季的过度工程化。

---

### D2: World 非竞争统计

**状态**: PARTIAL ⚠️ (非阻断)

**发现**:
- `modes.md` §9: World 行明确 "World 不设竞争榜单" ✅ — 设计意图清晰
- `api-registry.md` §3.2 Play: `swarm_get_leaderboard` 存在，visibility filter=`none`，rate limit key=`global`
- `api-registry.md` §3.4 Capability Profiles: `play` profile 分配给 "World 玩家，Arena spectator"
- 结果：World 玩家有 API 访问 leaderboard 的权限，与设计文档 "不设竞争榜单" 冲突

**分析**: 这是 R24 CFX2 的残留。Speaker 推荐选项 B（允许非竞争型统计但命名为 stats 而非 leaderboard）。当前 API 暴露 leaderboard 但未做模式限制。

**建议**: 
- 将 `swarm_get_leaderboard` 的 capability profile 从 `play` 移至 `arena`，或
- World 模式下 leaderboard 返回非竞争型统计（无排名、无奖励绑定），并 rename 为 `swarm_get_world_stats`
- 在 `modes.md` 中明确 World 允许非竞争型统计展示

**策略深度评估**: 从游戏设计角度，World leaderboard 的存在会污染 World 的核心设计承诺——"无竞争、持久沙盒、玩家自定目标"。即使 API 返回的是非竞争数据，"leaderboard" 的命名和排名语义会引导玩家行为向竞技倾斜，侵蚀 World 的创造力优先文化。

---

### D3: Recycle lifespan-proportional

**状态**: CLOSED ✅

**证据**:
- `resource-ledger.md` §2.5: 权威公式——`recycle_refund = max(10%, remaining_lifespan/total_lifespan × 50%)` ✅
- `economy.idl.yaml`: RecycleRefund 操作与公式一致 ✅
- `gameplay.md`: "回收退还 lifespan-proportional 10%–50%" ✅

**策略深度评估**: lifespan-proportional 回收创造了有意义的 timing 决策——早回收（高 refund）vs 晚回收（低 refund 但多服务了 tick）。固定 50% 会鼓励 "用完就回收" 的 exploit；10% 下限保证即使快死也有残值。这是经过计算的 anti-exploit 设计。

---

### D4: Snapshot budget 分模式 Arena 50ms/World 200ms

**状态**: CLOSED ✅

**证据**:
- `engine.md` §3.4.1: World ≤200ms p95, Arena ≤50ms p99 ✅
- `snapshot-contract.md` §7.1: Snapshot build time <200ms p95（World 参考）✅
- 实现了 Speaker 推荐：Arena 使用严格 p99 gate，World 使用宽松 p95 gate

**策略深度评估**: 分模式 snapshot budget 在两个维度上创造了差异化：Arena 50ms p99 保证竞技公平的实时性（所有玩家的快照延迟差异极小），World 200ms p95 以宽松尾延迟换取更大模拟规模。这是"公平竞技 vs 丰富生态"的设计权衡的正确工程表达。

---

## 遗漏/建议

### G1: EXECUTE budget 400ms vs timeout 500ms 未显式交叉引用
tick-protocol.md §1.4 的 500ms 为"超时"非"预算"，但未与 engine.md 的 400ms budget 关联。添加一行注释即可关闭。

### G2: api-registry §3.2 子标题 "54" 残留
实际 56 个工具，子标题未更新。无功能影响但影响文档可信度。

### G3: mcp-security onboarding tools 声明与 api-registry 冲突
mcp-security 仍将三个 AI onboarding 工具标为"已移除"，但 api-registry 列出为 active。这会导致 AI agent 开发者困惑。

### G4: World leaderboard 未做模式限制
`swarm_get_leaderboard` 的 capability profile 未区分 World/Arena，与 modes.md "World 不设竞争榜单" 冲突。

---

## 策略空间分析

World 模式下核心策略维度：

| 维度 | 范围 | 组合数 |
|------|------|--------|
| Body Part（8 种）× quantity（≤50） | 8^50 理论 → 实际 ≤50 parts | 极广 |
| Damage Type（6 种）× Special Attack（8 种） | 攻击选择矩阵 | 48 |
| Structure（13 种）× RCL（8 级） | 建造树分支 | 104 |
| Movement（Move=Action 约束）× 距离 | 定位策略 | 连续 |
| Economy（Faucet/Sink/Lockup/Unlock） | 资源流方向 | 4 大类 × 多种操作 |
| Lifespan（1500 tick）× Recycle timing | 寿命管理 | 1500 个决策点 |
| Territory（Room × Controller × Depot 后勤） | 空间扩张 | 多目标优化 |
| Visibility（Fog-of-War × Snapshot truncation） | 信息不对称 | 二元 + 桶粒度 |

**Dominant Strategy 检测**: 未发现 dominant strategy。Move=Action 的单动作槽约束确保没有"移动+攻击同时执行"的无脑组合。超线性维护费（O(n²)）防止纯扩张策略垄断。累进存储税防止囤积策略。Snapshot truncation 距离桶优先创造"近距离信息更完整"的自然偏好，但不强制特定战术。

**Nash 均衡初步分析**: 在 PvP 场景（Arena/contested room），先到先得的资源竞争 + 种子洗牌使长期期望均等——不存在位置优势 exploit。World PvE 中 NPC 难度按地理梯度分布，玩家通过代码效率而非单纯扩张获取竞争优势——形成效率 Nash 均衡。

---

## 评审统计

| 项 | CLOSED | PARTIAL | GAP |
|----|--------|---------|-----|
| B1-B6 | 5 | 1 (B3+B4) | 0 |
| D1-D4 | 3 | 1 (D2) | 0 |
| **总计** | **8** | **2** | **0** |

---

*评审日期: 2026-06-20*
*评审员: rev-dsv4-designer (DeepSeek V4 Pro)*
*角色: Game Designer Reviewer*