# R18 Game Design Review — DeepSeek V4 Pro (rev-dsv4-designer)

> Review date: 2026-06-18 | Phase 1 Clean-Slate
> Profile: Game Designer Reviewer — 博弈论分析、策略深度评估、算法公平性

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 2 Critical, 4 High, 4 Medium

设计体系在 R17 YAML IDL 单事实源化后大幅改善，gameplay 深度出色（logistics ladder、progressive PvP transition、anti-snowball triad）。但 **YAML↔Markdown 闭合不完整**：`specs/gameplay/08-api-idl.md` 的 RejectionReason enum 与权威 YAML IDL 完全偏离（42 vs 35 variants），且 CommandAction 参数签名不一致——这违反了 D1/A 单事实源原则。此外，drone 寿命系统的防御偏置与 progressive unlock 的 player-facing 透明度存在策略空间缝隙。

---

## 2. Findings

### Critical (2)

**C1 — YAML IDL ↔ specs/gameplay/08-api-idl.md 闭合断裂 (D1/A violation)**

`specs/gameplay/08-api-idl.md` 声称 "同 IDL 生成所有绑定——不一致即编译错误"，但其 RejectionReason enum (lines 65-110, 42 variants: `NotMovable`, `Fatigued`, `MissingBodyPart{part}`, `TileBlocked`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `AlreadyHacked`, `InvalidDamageType`, `AlreadyDebilitated`...) 与权威 YAML IDL 的 35 canonical codes (ObjectNotFound, NotOwner, InsufficientResource, OutOfRange, NotVisibleOrNotFound, CooldownActive...) **完全不同**。

此外 CommandAction 参数签名也不一致：
- `08-api-idl.md` Move: `{object_id, direction}` vs YAML: `{direction: Direction4}`
- `08-api-idl.md` Transfer: `{object_id, target_id, resource, amount}` vs YAML: `{target_id, resource, amount}`

**Severity: Critical** — 这违反 D1/A "YAML IDL 是唯一的机器可读权威源"原则。markdown specs 文档应被 YAML 生成覆盖，但 08-api-idl.md 未被替换/同步。漂移范围涉及 42 个 RejectionReason variant 和至少 5 个 CommandAction 参数签名。下游 SDK/MCP codegen 若读取此文件将产生错误绑定。

**Remediation**: 将 `08-api-idl.md` 的 §2-§4 替换为从 YAML IDL 生成的引用，或在 YAML IDL 的 codegen pipeline 中纳入此文件作为生成目标。

**C2 — Drone 寿命系统产生结构性防御偏置 (Defensive Dominance)**

Controller aging 维修 50% hard cap（`max(0, age + 1 - min(0.5, controller_count * 0.5))`）的数学约束与 body part `age_modifier`（TOUGH +100）之间存在未被分析的策略交互：

- 一个 TOUGH-heavy drone（10×TOUGH = +1000 age）在 lifespan=1500 基础上获得 ~2500 有效 lifespan
- Controller 维修的 hard cap 对所有 drone 等同——大 lifespan drone 的维修价值被等比放大
- 防御方的 drone 长期停留在 Controller 范围（维修可达），攻击方 drone 深入敌后无法维修 → 攻击方 drone 先死
- 这导致 **防御方兵力质量优势** 随 empire 规模累积——攻击方需要数倍兵力才能突破

**Severity: Critical** — 这不是单纯的"先入者优势"（World 模式接受的），而是 **系统性 bias 叠加**：lifespan+维修+soft_launch+安全区出生，四层叠加使新玩家攻击老玩家的 ROI 接近 0。与 "World 不追求公平" 的哲学一致，但当攻防比超过 3:1 时，PvP 交互退化为纯防御博弈——这损害 World 模式的 emergent gameplay 承诺。

**Remediation**: 评估维修 hard cap 是否应与 drone body 复杂度挂钩（如 `max(age_recovery) ∝ 1/total_body_parts`），或在 Controller 范围外提供更多 Depot 部署点位。

### High (4)

**H1 — Controller/Dual Storage 的长期目标方向矛盾 (Progression Alignment)**

两个永久资源沉没的终点不同：
- Controller 升级 (RCL 1-8)：资源锁入不可回收的 Controller → 永久沉没
- Global Storage 累进税：鼓励将资源留在 Local Storage（Stealth Advantage）

这创建了一个策略分叉：新建玩家天然倾向 RCL rush（解锁高级建筑），但 RCL rush 消耗的资源永久消失；而有经验的玩家囤积 Local Storage 避税 → 资产保护 vs 纵向进度的冲突在 500-2000 tick 区间最尖锐。设计未明确说明新玩家应被引导到哪条路。

**Severity: High** — Golden Path 文档 (§2.1-2.4) 推荐 harvester→PvE challenge，但未提及玩家在 RCL vs Storage tradeoff 上的决策引导。AI agent 无此引导可能随机选择次优策略。

**H2 — Fog-of-War 与 Overload 反馈的信息不对称间隙**

OverloadPressure 组件 (gameplay.md §Overload 反馈透明度) 在 competitive 模式下暴露"总压力 + 可见 source 的 contribution"，但：
- 不可见攻击者的 contribution 不暴露 → 被攻击者知道被 Overload 了但不知道是谁
- 被攻击者可通过反向推导排除法缩小攻击者范围（"房间内可见 A、B、C，都不是攻击者 → 攻击者是 D"）
- `NotVisibleOrNotFound` 的设计意图是防止 oracle inference，但 Overload 反馈创建了新的侧信道

**Severity: High** — 在 competitive 模式下，这等价于一个有限的定位 oracle。与 D2/B 的 `debug_detail` 模式分级设计有张力。

**H3 — Progressive Unlock 的 Player-Facing 透明度不足 (New Player Decision quality)**

特殊攻击的 Progressive Unlock (gameplay.md §特殊攻击方式表格) 按世界层级渐进：Tutorial/Novice 全部禁用 → Standard 全部 8 种可用。但：
- 从 Novice 进入 Standard 世界的玩家在 **没有任何渐进学习** 的情况下突然面对全部 8 种特殊攻击
- Hack 的 5-stage 控制锁、Drain 的资源窃取、Overload 的燃料压制——这些机制的复杂度远高于基础 Move/Harvest/Build
- 当前设计中缺失 "Standard 世界的前 200 tick 限制特殊攻击可用种类" 或 "特殊攻击 tutorial challenge" 的引导机制

**Severity: High** — 从 Novice(0 特殊攻击) → Standard(8 特殊攻击) 的硬切换是 player experience cliff。类比 soft_launch→PvP 的分阶段过渡设计得很好，但特殊攻击的学习曲线同样需要渐进。

**H4 — Alliance 背叛冷却 (24h) 对短 session 玩家形同虚设**

外交系统 (gameplay.md §9.2) 的 break alliance → 24h cooldown 设计意图是防止"结盟→偷袭→立刻重结盟"循环。但以 tick 为单位的世界（3s/tick），24h = 28,800 ticks——对于只玩 2-3 小时的 casual 玩家，背叛者可以在同一 session 内完成结盟→偷袭→下次登录时冷却已结束。冷却以 wall-clock 而非 effective play time 计量，与 Sandbox CPU 的 fuel metering 哲学不一致。

**Severity: High** — 虽然外交是表现层、不影响 tick 确定性，但 unequal cooldown perception（hardcore 玩家觉得 24h 短，casual 玩家觉得无意义）可能影响社区信任。

### Medium (4)

**M1 — Drone 消息协议的博弈论逃逸**

Drone 间消息系统 (gameplay.md §8.9) 标记为"不可信协议"且引擎不校验语义——这是正确的设计。但缺少对 **sybil 攻击** 的分析：一个玩家可用多个 drone 伪装成多个独立交易对手方，建立虚假声誉。信誉系统完全依赖 WASM 层自建，引擎不提供任何 sybil resistance。

**M2 — PvE 经济注入上限 (30%) 的均衡分析缺失**

PvE drop 经济约束 `max_pve_output_per_tick ≤ 世界再生总量 × 30%` (modes.md §NPC 掉落经济) 的 30% 阈值缺乏数学推导。若世界再生总量随玩家数量增长（更多 source 被激活），PvE 注入上限线性增长——可能在高人口世界使 PvE farming 成为 dominant income strategy。

**M3 — 回放隐私与观战延迟的矛盾**

`spectate_delay=0` 默认值 (gameplay.md §可见性与观战) 与 `replay_privacy=private` 默认值存在矛盾：实时观战无延迟意味着竞技信息可即时泄露，但回放默认私有意味着分析工具受限。Arena 模式需要明确的 spectator policy——特别是 AI agent 可作为 spectator 实时学习对手策略。

**M4 — First-Attack Shield 的 per-attacker scope 可能被多账号滥用**

soft_launch→PvP 过渡的 First-Attack Shield (gameplay.md §First-Attack Shield 详细规则) 设计为 per-attacker scope——仅免疫触发盾牌的攻击者。但同一玩家可通过多 drone/多账号同时对目标发起攻击——盾牌只阻挡第一个攻击者，其余攻击正常造成伤害。多账号攻击的协同成本低于防御方预期。

### Low (—)

无显著的 Low 级问题。设计文档质量整体高。

---

## 3. Strengths

1. **Soft_launch→PvP 分阶段过渡 (D6/B)** 是杰出的新手保护设计——First-Attack Shield → Soft PvP (50% damage) → Full PvP 的 700 tick 渐进式开启，避免了传统 MMO 的"保护期结束瞬间清场"问题。参数全部可配置，保持了 World Rules Engine 哲学。

2. **Global↔Local 双重存储 + 物流阶梯 (三种模式)** 为不同 skill level 的玩家提供不同策略深度。模式 B (轻物流) 的新手友好与模式 C (硬核物流) 的 Factorio 式深度共存于同一引擎——这是可配置性的典范应用。

3. **NotVisibleOrNotFound 安全合并码** — 将"不存在"和"不可见"合并为单一 RejectionReason 防止 oracle inference，是经典的信息安全博弈论应用。配合 detail_level 三级阶梯 (competitive/practice/training)，竞技公平与调试可用性兼顾。

4. **反雪球三柱石**: 累进存储税 + 超线性维护费 + Controller 老化硬上限形成互锁反垄断机制。三者各自不足以防垄断，但叠加后形成 1+1+1>3 的 emergent constraint——即使老玩家也无法无限囤积/扩张。

5. **Drone 人格系统 (gameplay.md §9.1)** 是罕见的"纯表现层深度"设计——Blake3 确定性种子保证 replay 一致，0 gameplay 影响但增加情感连接。aggression/curiosity/loyalty/efficiency 四维人格的 idle 动画差异化是低成本高回报的 immersion 投资。

6. **WASM fuel metering + Host function 独立预算** 的公平核算模型——C 和 Python 玩家在相同指令数配额下获得同等算力，这是"代码即军队"哲学的数学基础。

7. **Determinism Contract**: Blake3 XOF PRNG + indexmap + 定点数 + 固定排序键 + 种子轮换 (每 10,000 tick)，全方位保证跨平台/跨编译器 replay 一致性。

8. **AI/Human 同路径**: MCP 不做游戏动作——AI agent 必须编写 WASM，与人类走完全相同路径。这消除了 AI vs Human 的公平性质疑根源。

---

## 4. CrossCheck — YAML IDL ↔ Markdown 单事实源验证

### 通过项

| 检查项 | 结果 |
|--------|:--:|
| `api_version: "0.3.0"` — YAML 与 api-registry.md 一致 | ✅ |
| CommandAction 19 variants — YAML 与 api-registry.md 一致 | ✅ |
| RejectionReason 35 canonical codes — YAML 与 api-registry.md 一致 | ✅ |
| total_tools: 46 — YAML 与 api-registry.md 一致 | ✅ |
| Host Functions 5 — YAML 与 api-registry.md 签名一致 | ✅ |
| game_limits 全部参数 — YAML 与 api-registry.md 一致 | ✅ |
| terminal_state 7 variants — YAML 与 api-registry.md 一致 | ✅ |
| Direction4 — YAML 与 api-registry.md 一致 | ✅ |
| design/interface.md MCP 工具分类与 api-registry 映射 | ✅ |
| modes.md Arena 房间参数与 YAML limits 一致 | ✅ |
| swarm_deploy 幂等性 (module_hash) — design/interface.md §5.7 ↔ gameplay.md §8.2 ↔ YAML deploy_mutation 一致 | ✅ |
| swarm_simulate isolation — specs/core/09-snapshot-contract.md 与 design/interface.md §5.7 一致 | ✅ |

### 断裂项 (CAP)

| 断裂点 | 文件 A | 文件 B | 描述 |
|--------|--------|--------|------|
| **RejectionReason 完全偏离** | `specs/gameplay/08-api-idl.md` §2 (42 variants) | `game_api.idl.yaml` (35 codes) | 08-api-idl.md 包含 NotMovable, Fatigued, MissingBodyPart, TileBlocked, CarryFull, NotSource, SourceEmpty, TargetFull, NotYourRoom, AlreadyFullHealth, FriendlyTarget, NotYourSpawn, BodyTooLarge, ExceedsRoomCapacity, AlreadyHacked, InvalidDamageType, AlreadyDebilitated 等——这些在权威 YAML IDL 中不存在 |
| **CommandAction Move 参数** | `08-api-idl.md`: `{object_id, direction}` | YAML: `{direction: Direction4}` | object_id 不在 YAML Move 参数中 |
| **CommandAction Transfer 参数** | `08-api-idl.md`: `{object_id, target_id, resource, amount}` | YAML: `{target_id, resource, amount}` | object_id 多余；YAML 有 resource type/amount |
| **CommandAction Build 参数** | `08-api-idl.md`: `{object_id, x, y, structure}` | YAML: `{structure_type, x, y}` | 参数名不一致，object_id 多余 |
| **CommandAction Spawn 参数** | `08-api-idl.md`: `{spawn_id, body}` | YAML: `{body_parts, spawn_id}` | 参数名不一致 |
| **Recycle refund 值** | `08-api-idl.md`: `0.5` | `gameplay.md`: `50%` | 一致，但 gameplay.md 无 refund 定义在 Command 表 |

**结论**: `specs/gameplay/08-api-idl.md` 是 R17 之前的 IDL 草稿，未被 YAML IDL 生成的 api-registry.md 覆盖。此文件需要被标记为 deprecated 或重新生成为 YAML IDL 的引用摘要。

### CAP Notation

- `08-api-idl.md` §2 RejectionReason enum → 标记为 `⛔ SUPERSEDED`，指引到 YAML `rejection_reason.variants`
- `08-api-idl.md` §commands → 标记为 `⛔ SUPERSEDED`，指引到 YAML `command_action.variants`

---

## 5. Strategy Depth Analysis

### 策略空间维度

| 维度 | 状态 | 分析 |
|------|:--:|------|
| Body Part 组合 | 丰富 | 8 parts × 50 max = 极大组合空间；age_modifier 创造 lifespan vs power tradeoff |
| 物流策略 | 3 层 | Mode A/B/C 提供 0→hardcore 物流深度阶梯 |
| 特殊攻击 counter-play | 良好 | Hack↔Disrupt↔Fortify 形成 counter 三角；Overload↔Defensive positioning |
| 领土扩张 | 递减回报 | Empire upkeep + Controller aging 创造自然收敛点 |
| 时间维度策略 | 丰富 | RCL/GCL progression + 殖民地年龄 + Arena 段位形成非线性目标 |
| 外交博弈 | 有限 | Alliance 仅 5 上限，无联盟资源池或层级结构 |

### Dominant Strategy 检查

| 候选 Dominant Strategy | 遏制机制 | 有效性 |
|--------|------|:--:|
| TOUGH-stacking 不朽 drone | Controller 维修 50% hard cap + active_aging 110% | ⚠️ 部分（见 C2） |
| 无限囤积 Global Storage | 累进税率 (0→20bp) | ✅ 有效 |
| 无限扩张房间 | O(n²) empire upkeep + Global entity cap 50,000 | ✅ 有效 |
| PvE 刷怪经济 | max_pve_output ≤ 再生量 × 30% | ⚠️ 线性增长门限（见 M2） |
| 多账号 sybil 攻击 | PoW CSR (difficulty_bits 24) + same_origin quota 5 | ✅ 基本有效 |
| 代码部署刷退费 | swarm_deploy 幂等性 (module_hash 去重) | ✅ 有效 |

### 纳什均衡分析 — World 模式 (Human + AI 共存)

在持久 World 中，Human 和 AI agent 的均衡点：
- **资源采集**: 共同 Nash equilibrium 在 source 容量限制——所有玩家都最大化采集 → source 枯竭加速 → 采集效率下降 → equilibrium 在 source 再生率附近
- **领土竞争**: 不完全信息博弈——Local Storage Stealth 创造私人信息优势，阻止 perfect competition
- **PvP 交互**: 防御偏置 (C2) 使 "先扩张后防守" 成为弱 dominant strategy → 扩张动力被 empire upkeep 抑制 → equilibrium 是中等规模 empire + high efficiency
- **AI vs Human**: 同 WASM 沙箱消除算法层面的不公平——但 AI 可通过 MCP 的 `swarm_simulate` (100 tick offline) 获得更快的策略迭代速度。这是设计接受的：AI 的 "APM" 优势被 fuel budget 限制。

### Arena 模式均衡

Arena 1v1 对称初始条件，WASM 锁定：
- 纯策略纳什均衡可能不存在（rock-paper-scissors 式 counter）
- 混合策略均衡存在于 body part 组合的 probability distribution
- Leaderboard 按 league 分区 (Human/WASM, AI-assisted, AI tournament) 防止 AI 与人类混合排名的不公平

---

## 6. R15-R18 问题追踪

| R15/R16/R17 Issue | R18 Status |
|------|:--:|
| R15 C1: free deployment | ✅ RESOLVED — gameplay.md `code_update_cost` configurable, swarm_deploy 幂等性 |
| R15 C2: drone lifespan defensive bias | ⚠️ PARTIAL — aging 50% cap + TOUGH age_modifier 交互仍存(C2), 但 active_aging 110% + Depot logistics 有缓解 |
| R16 C1: World motivation vacuum | ✅ RESOLVED — §长期目标系统: GCL/RCL/Arena段位/PvE里程碑/观战 |
| R16 H3: defensive play bias | ⚠️ PARTIAL — D6/B soft_launch progressive PvP 缓解了新玩家 Cliff, 但 C2 的 lifespan 维修偏置仍存 |
| R17 C1: soft_launch→PvP cliff | ✅ RESOLVED — D6/B 分阶段过渡 (First-Attack Shield → Soft PvP → Full PvP) |
| R17 H1: World motivation vacuum | ✅ RESOLVED — R16 的长期目标系统已覆盖 |

---

## 7. 总结

R18 设计在 gameplay 深度和机制完整性上达到了可实施阶段。YAML IDL 单事实源化 (D1/A) 在 YAML↔api-registry.md 通路上闭合良好，但 `specs/gameplay/08-api-idl.md` 的残留漂移必须解决——它在当前状态下被读取将产生错误的 SDK codegen。两个 Critical 问题均可通过文档修复 + 参数调整解决，无需架构重构。

建议优先处理 C1 (文档闭合) 后 approve 进入实现阶段。

---

*Reviewer: Game Designer (DeepSeek V4 Pro)*
*Profile: rev-dsv4-designer*
