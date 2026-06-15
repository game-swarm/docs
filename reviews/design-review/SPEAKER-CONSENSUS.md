# Swarm 设计评审 — Speaker 共识报告

> **轮次**: 设计评审（profile-based 统一管线）  
> **日期**: 2026-06-15  
> **评审官**: 9/9 完成（3 方向 × 3 模型）  
> **Speaker**: 当前 session（直接合成）

---

## 1. 裁决概要

本轮为 profile-based 统一管线首次评审。9 名评审官全部完成，无缺位。7/9 给出 CONDITIONAL_APPROVE，2/9 给出 APPROVE_WITH_RESERVATIONS。**未出现 REQUEST_MAJOR_CHANGES 或 REJECT**，说明架构方向被广泛认可。

核心发现集中在两个主题：(1) **确定性契约的执行细节**（墙钟终止、模组隔离、种子保密），(2) **玩家体验的抽象层次**（Vanilla ruleset 缺失、新手 onboarding、进度曲线未验证）。这些不是架构级推翻项，而是冻结前需要收口的边界执行问题。

**收敛状态**: 方向收敛。架构师、安全、设计三个方向在核心关切上高度一致（跨方向 ≥5 个共识 Blocker）。Phase 0 架构冻结在此轮修正后可宣告成立。

---

## 2. 总体 Verdict

**CONDITIONAL_APPROVE** — 设计可进入实现阶段，但须先闭合以下共识 Blocker。

| 方向 | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|------|:---:|:---:|:---:|
| **Architect** | APPROVE_WITH_RESERVATIONS | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| **Security** | Conditional Approve | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| **Designer** | APPROVE_WITH_RESERVATIONS | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

---

## 3. 共识 Blocker（≥2 方向 + ≥2 模型同意）

### B1 — Rhai 墙钟 100ms 终止破坏确定性

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | A1（严重）✅ | — | — |
| Security | C1（Critical）✅ | — | — |
| Designer | — | — | — |

**问题**: DESIGN §8.4 规定 Rhai 脚本以 100ms 墙钟强制终止并回滚。墙钟在不同硬件/负载下不一致 → 同一 tick 的 mod 在不同机器上终止于不同 AST 节点 → 世界状态分叉。这直接违反 §1.5「确定性核心」，使回放再验证（反作弊根基）失效。

**跨评审交叉引用**: Claude Architect A1 + Claude Security C1 独立发现同一问题。

**裁决**: **必须修改。** 墙钟只能用于告警/监控，不能作为世界状态决定因素。改为确定性预算（AST 节点数 / 指令数），匹配 §1.5 的确定性原则。两评审官均建议 AST 节点数（10k），此方案收敛。

**修正要求**:
1. DESIGN.md §8.4: 删除 100ms 墙钟终止逻辑，改为 AST 节点数预算（10k）
2. P0-7: 同步更新 Rhai 执行预算描述
3. §1.5 确定性核心：增加「Rhai 执行预算必须确定性」条款

---

### B2 — Rhai 进程内执行、无隔离、持破坏性 API

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | — | — |
| Security | C2（Critical）✅ | High（RuleMod 能力模型）✅ | — |
| Designer | — | — | — |

**问题**: Rhai 脚本（`damage_entity`/`deduct_resource`/`set_entity_flag`）在引擎核心进程内运行为，"服主可信"假设在模组被分发/复用时崩塌。Rhai 解释器一旦存在逃逸或预算绕过 → 全进程沦陷。

Claude Security 与 GPT Security 独立收敛于同一结论：需要进程/能力隔离 + 模组签名与来源校验。GPT Security 进一步指出 P0-9 将 RuleMod 能力描述为"仅经济+事件"，但 P0-7/DESIGN 实际允许更广能力（damage/effect/attribute/custom handler）→ 跨文档不一致。

**裁决**: **必须修改。** 实现前收口 Rhai 隔离方案 + 模组签名机制 + P0-9/P0-7/DESIGN 能力描述对齐。

**修正要求**:
1. DESIGN.md: 新增 Rhai 隔离方案（进程隔离或能力沙箱，二选一）
2. DESIGN.md: 新增模组签名与来源校验机制
3. P0-7 vs P0-9: 对齐 RuleMod 能力范围描述（经济+事件 → 明确列出允许的 action 类型）
4. tech-choices.md: 补充 Rhai 安全评估（已知 CVE 历史、逃逸风险）

---

### B3 — Command Validation Pipeline 单点收口完整性

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | — | — |
| Security | C3（Critical）✅ | — | HIGH-1（"Trust Downstream"）✅ |
| Designer | — | — | — |

**问题**: Command JSON 完全由不可信 WASM 构造，校验管线是 WASM 与可信世界状态之间的唯一闸口。Claude Security 要求穷举：entity_id 越权、u32 溢出、资源注入、坐标越界、畸形 JSON DoS。DSV4 Security 补充：Admin 命令如果跳过 Validation Pipeline（走 `admin_apply()` 而非 `validate_and_apply()`）→ 存在绕过路径。

**裁决**: **必须修改。** 实现前须有字段级穷举校验表，且 Admin 命令必须走同一 `validate_and_apply()` 路径（仅放宽 RejectionReason 阈值）。

**修正要求**:
1. P0-2: 补充字段级穷举校验表（所有权绑定 + 范围 + 类型三重校验 + DoS 上限）
2. P0-9: Admin 命令必须走同一 `validate_and_apply()`，不可设独立代码路径
3. DESIGN.md §1.4: 增加"校验管线自身不可被指令数量耗尽"条款

---

### B4 — Overload 攻击无范围/可见性限制（跨世界侧信道 + DoS）

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | A5（High）✅ | — |
| Security | — | — | CRITICAL-2 ✅ |
| Designer | — | — | — |

**问题**: Overload 特殊攻击声明"无范围限制 — 逻辑攻击"。这意味着任何玩家可以削减全球任意玩家的 fuel 预算（500k/次），无视 fog-of-war、无视距离、无视可见性。

GPT Architect 指出这是"对参与游戏能力的攻击，不只是单位状态变化"。DSV4 Security 进一步发现：(1) Overload 成功/失败会泄露目标玩家存在性和 fuel 状态（信息泄露），(2) 10 架 RangedAttack drone 可在单 tick 削减单一目标 5M fuel，(3) 这是整个可见性模型（P0-5 `is_visible_to()`）的唯一例外。

**裁决**: **必须修改。** 添加可见性/范围约束，设全局冷却 + 静默失败。

**修正要求**:
1. DESIGN.md §4.4 / P0-2: Overload 添加 `requires_visibility: true`（目标玩家的任意实体在攻击者视野内）
2. P0-2: 添加全局 Overload 冷却（同一目标 N tick 内不可被重复 Overload）
3. P0-2: Overload 失败时返回静默错误（不泄露目标状态）
4. P0-5: 确认 Overload 纳入 `is_visible_to()` 检查

---

### B5 — 默认游戏抽象层次未收敛：缺少 Vanilla Ruleset

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | A2（High）✅ | — |
| Security | — | — | — |
| Designer | G5（High）✅ | G1（High）✅ | D4（MEDIUM）✅ |

**问题**: DESIGN.md 将 Vanilla、Advanced、Modded、Future Expansion 混在同一层级。GPT Architect 指出这是经典的"过早平台化"失败模式；GPT Designer 强调第一个小时的认知负担过重；Claude Designer 指出经济三模式（A/B/C）对新手过重。

三个方向三个模型独立收敛：需要一份明确的 "Official Core Ruleset Contract" 定义默认体验边界。

**裁决**: **必须修改。** 新增 Official Vanilla Swarm Ruleset 章节，将可配置项收束到分层投放模型。

**修正要求**:
1. DESIGN.md: 新增 §X "Official Vanilla Swarm Ruleset" — 明确默认资源、body parts、建筑、战斗、物流模式的固定基线
2. DESIGN.md: 明确三层扩展模型：Core（冻结） / Declarative（参数可配） / Experimental（世界特定）
3. P0-6: 教程/starter bot 需与 Vanilla Ruleset 对齐
4. 经济模式：默认锁定模式 B，A/C 标记为进阶解锁

---

### B6 — RCL 进度曲线 + Controller 续期破坏生命周期约束

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | — | D4（MEDIUM）✅ |
| Security | — | — | — |
| Designer | G1+G2（High）✅ | — | — |

**问题**:
- RCL 7(50k)→8(150k) 是 3 倍跳跃，而 1→2 仅 200 → 中后期墙过陡，RCL8(Nuker) 沦为极少数玩家专属
- 每 Controller/tick 回退 age 0.5，多 Controller 可完全抵消自然衰老 → 永久 drone，消解 lifespan(1500) 约束

Claude Designer 与 DSV4 Architect 独立发现。这是两个独立但互相强化的滚雪球机制。

**裁决**: **必须修改。** 重新定调 RCL 曲线（建议几何增长，相邻级倍率 1.6–2.0x），Controller 续期设硬上限（最多抵消 50% age 增长）。

**修正要求**:
1. DESIGN.md §3.2: 重新设定 RCL 进度曲线（建议近似几何增长）
2. DESIGN.md §2.2: Controller 续期硬上限 `max_age_reduction = 0.5/tick`
3. DSV4 Architect D5: 明确 age floor 行为（`age = max(0, age + 1 - min(1.0, 0.5 * controller_count))`）

---

### B7 — 世界拓扑 / Sharding / 领土模型未定义

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | A2+A3（严重）✅ | A3（High）✅ | D1（MAJOR）✅ |
| Security | — | — | — |
| Designer | — | — | — |

**问题**: 三个架构评审官独立发现同一缺口。
- Claude Architect: 单世界扩展上限未声明，FDB 事务 10MB 硬限，10000 玩家只能靠多世界水平扩展
- GPT Architect: room 尺寸、坐标系、出口、邻接关系、shard 边界、Arena 地图模板对称性未定义
- DSV4 Architect: Multi-Shard MMO model is undefined, cross-shard determinism 不可行

**裁决**: **必须修改。** Phase 1-3 采用 Option B（单引擎垂直扩展），文档化水平分片为 Phase 7+ 关注。

**修正要求**:
1. DESIGN.md: 新增 §"World Topology & Territory" — room graph、坐标模型、出口规则、Controller 生命周期
2. DESIGN.md: 声明单世界扩展策略（垂直扩展 → 先到先上限 → 多世界水平扩展），设定 MVP 实体上限
3. DESIGN.md §7.2: 明确多引擎图为 HA（active-passive），非水平分片
4. P0-1: FDB 事务大小预算（10MB）+ 分片提交策略（若未来需要）

---

### B8 — Bevy World 快照回滚完整性 + FDB 事务原子性边界

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | — | — | D1（CRITICAL）✅ |
| Security | — | — | CRITICAL-4 ✅ |
| Designer | — | — | — |

**问题**: P0-1 §3.5 规定 FDB commit 失败时显式 `world.restore(snapshot)` 恢复 Bevy World。但 Bevy ECS World 非简单 Clone 友好结构——archetype storage、类型擦除 Resources、Change detection ticks 均需完整捕获。快照遗漏任何 component/resource → 回滚后状态分叉 → 确定性合同被打破。DSV4-Security 进一步指出 COLLECT 结果是否跨重试缓存复用、RNG 状态恢复均未定义。DSV4-Architect 提出更优替代方案：「先提交后应用」——FDB commit 成功后才将变更写入 Bevy World，避免回滚需求。

**裁决**: **必须修改。** 显式定义快照范围（Component + Resource 清单），增加 FDB 故障注入 CI 测试。评估「先提交后应用」替代方案。

**修正要求**:
1. P0-1 §3.5: 显式列出快照范围（所有 Component 类型 + TickCounter/RNG state/PlayerOrder/ResourceRegistry 等核心 Resource）
2. P0-1 §6.1: COLLECT 结果跨重试缓存复用策略
3. CI: FDB 故障注入测试（随机 tick 触发 commit 失败 → `state_checksum == snapshot_checksum`）
4. 评估并文档化「先提交后应用」vs「快照回滚」的取舍

---

### B9 — Phase 2a/2b 边界原则缺失 + Spawn 文档矛盾

**方向 × 模型矩阵**:
| 方向 | Claude | GPT | DSV4 |
|------|:---:|:---:|:---:|
| Architect | A5（中）✅ | — | D4+D6（CRITICAL）✅ |
| Security | — | — | — |
| Designer | — | — | — |

**问题**:
1. **2a/2b 无分类原则**: Attack 在 2a 直接减 HP，2b combat_system 再次处理战斗 → 双重伤害风险。Move→Attack→Harvest 的顺序效应在跨阶段时语义变化。
2. **Spawn 文档矛盾**: DESIGN §3.2 ECS chain 中 `spawn_system` 在第 2 位（死亡清理前），P0-2 §3.10 声称「death_cleanup 之后创建」——直接矛盾。新 spawn drone 在同 tick 参与 combat/decay 需显式声明。
3. **Recycle despawn 三处不一致**: P0-2 §10.3「立即 despawn」、DESIGN §3.2「Phase 2a」、实际 death_cleanup 在 2b 末尾。

Claude Architect A5 与 DSV4-Architect D4+D6 独立收敛。

**裁决**: **必须修改。** 定义 2a vs 2b 分类原则，修正 Spawn/Recycle 文档矛盾。

**修正要求**:
1. DESIGN §3.2: 新增分类原则——2a (Inline): 玩家命令，FCFS 竞争；2b (Deferred): 被动系统 + 跨实体协调
2. DESIGN §3.2: 明确 Attack 在 2a 直接应用 damage（含抗性），2b combat_system 仅处理非玩家战斗（Tower/DoT）
3. P0-2 §3.10: 修正为「spawn_system 在 death_mark 后、combat 前——新 drone 同 tick 参与战斗」
4. P0-2 §10.3: Recycle 统一走 death_mark → death_cleanup

---

## 4. 方向专属 High 优先级

### Architect 方向

| ID | 问题 | Severity | 处置 |
|----|------|----------|------|
| A-H1 | 动态 CommandAction / IDL / SDK 边界存在架构级张力（GPT A1） | Critical | 明确三层扩展模型（Core/Declarative/Experimental），`core_abi_version` + `world_api_hash` |
| A-H2 | 新玩家保护 / Safe Mode 仍是字段级设计（GPT A4） | High | 新增 Colony Bootstrap & Safe Mode State Machine |
| A-H3 | Phase 2a/2b 边界未定义原则（DSV4 D2） | MAJOR | 添加分类原则（inline: FCFS 竞争 / deferred: 被动系统 + 跨实体协调） |
| A-H4 | Spawn Room Cap 竞态（DSV4 D3） | MAJOR | 文档化竞态为 intentional，补充 `RoomCapExceeded` + 退款行为 |
| A-H5 | FDB 事务上限 / Bevy World 回滚一致性（DSV4 CRITICAL-4） | Critical | 定义快照粒度 + COLLECT 结果跨重试缓存复用 |

### Security 方向

| ID | 问题 | Severity | 处置 |
|----|------|----------|------|
| S-H1 | 快照序列化未计入 fuel 配额（Claude H1） | High | 对快照大小/序列化成本设上限并计费 |
| S-H2 | MCP 查询工具无频率限制（Claude H2） | High | 配额化所有查询工具 |
| S-H3 | Fuel Refund Timing Attack — 双倍申领（DSV4 CRITICAL-3） | Critical | 跨重试 fuel 消耗上限为 1× MAX_FUEL |
| S-H4 | Pathfinding Algorithm Unbounded — 恶意地图 DoS（DSV4 HIGH-2） | High | A* 预算上界 + 局部目标回退 |

### Designer 方向

| ID | 问题 | Severity | 处置 |
|----|------|----------|------|
| D-H1 | 战斗系统组合爆炸不可平衡（Claude G3） | High | 提供 1 套官方 reference ruleset 作为锚点 |
| D-H2 | Hack/Neutral 5-tick 战术定位模糊（Claude G4 / Security H3） | High | 明确 Hack 策略定位（控场/资源/拖延），否则建议砍掉 |
| D-H3 | Overload 定向压制 AI 的人类/AI 不对称（Claude R2） | High | 与 B4 一起修正 — 添加可见性约束消除不对称 |
| D-H4 | 失败/死亡恢复循环未定义（Claude + GPT Designer） | High | 新增 respawn 重入机制描述 |
| D-H5 | Arena 匹配/段位机制未定义（Claude + GPT Designer） | High | 新增 Arena 匹配设计 |

---

## 5. Medium/Low 处置

| ID | 问题 | 来源 | 负责 Phase | 处置 |
|----|------|------|-----------|------|
| M1 | 转换损耗整数舍入 → 微额拆分规避 | Claude Security M1 | Phase 2 | 向上取整或设最小损耗 |
| M2 | `spectate_delay=0` 默认值构成共谋通道 | Claude Security M2 | Phase 3 | 竞技模式默认 >0 |
| M3 | 自定义动作组合缺乏白名单 | Claude Security M3 | Phase 3 | world.toml 校验加组合白名单 |
| M4 | wasmtime 版本即确定性依赖，回放元数据需记录 | Claude Security M4 | Phase 1 | 回放元数据锁定运行时版本 |
| M5 | COLLECT JSON 序列化在数千玩家下成本爆炸 | Claude Architect A4 | Phase 4 | 评估二进制快照格式（冻结前决策） |
| M6 | 多 mod 执行顺序未规定 | Claude Architect A7 | Phase 3 | mod id 字典序 + 版本/依赖解析器 |
| M7 | in-flight 资源的 ECS 实体模型缺失 | Claude Architect Missing | Phase 3 | 定义 Transport 实体 |
| M8 | 累进税率阈值无模拟支撑 | Claude Designer G6 | Phase 4 | 经济模拟验证后冻结 |
| M9 | Controller 降级计时器 / Claim 机制未定义 | DSV4 Architect D4 | Phase 2 | 新增 Controller Lifecycle 子章节 |
| M10 | MIT 首日开源需明确 wasmtime/Rhai CVE 跟踪 | Claude Security I1 | Phase 5 | 新增 CVE-SLA 策略 |
| M11 | TickTrace 审计日志防篡改 + PII 隐私分级 | Claude Security I2 | Phase 5 | 新增日志签名字段 |
| M12 | `set_entity_flag` 标志命名空间防冲突 | Claude Security I3 | Phase 2 | 标志名前缀注册机制 |

---

## 6. 文档维护项

1. **DESIGN.md**: 合并 Claude Architect findings（A1-A7）与 Claude Security findings（C1-C3/H1-H4）为设计文档内联修正
2. **P0-7 vs P0-9**: 对齐 RuleMod 能力范围描述（当前互相矛盾）
3. **README.md**: 更新评审状态为 "设计评审完成，9 Blocker 待收口"
4. **reviews/README.md**: 新增本轮 Speaker Verdict 索引
5. **Claude reviews 标题残留 4.8**: 三份 Claude 评审文件标题仍写 `Claude Opus 4.8`（模型实际使用 4.7，文本为模型自述），建议修正为 4.7
6. **P0-2 §3.10 vs DESIGN §3.2**: Spawn 文档矛盾（B9）——修正 P0-2 描述
7. **P0-2 §10.3 vs DESIGN §3.2**: Recycle despawn 三处不一致——统一路径

---

## 7. 下一轮入场条件

以下 9 项共识 Blocker 闭合后方可进入下一轮评审（或直接进入实现）：

- [ ] B1: Rhai 墙钟 → 确定性 AST 节点预算
- [ ] B2: Rhai 隔离方案 + 模组签名机制
- [ ] B3: Command Validation 字段级穷举表 + Admin 路径统一
- [ ] B4: Overload 可见性/范围约束 + 全局冷却
- [ ] B5: Official Vanilla Swarm Ruleset 章节
- [ ] B6: RCL 曲线重定调 + Controller 续期硬上限
- [ ] B7: World Topology & Territory 章节 + 扩展策略声明
- [ ] B8: Bevy World 快照范围清单 + FDB 故障注入 CI
- [ ] B9: Phase 2a/2b 分类原则 + Spawn/Recycle 文档修正

---

## 8. 评审统计

### 3×3 Verdict 矩阵

| | Architect | Security | Designer |
|---|:---:|:---:|:---:|
| **Claude Opus 4.7** | APPROVE_WITH_RESERVATIONS | Conditional Approve | APPROVE_WITH_RESERVATIONS |
| **GPT-5.5** | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| **DeepSeek V4 Pro** | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

### 共识强度

| 指标 | 数值 |
|------|------|
| 总评审官 | 9/9 完成 |
| CONDITIONAL_APPROVE | 7/9 |
| APPROVE_WITH_RESERVATIONS | 2/9 |
| REQUEST_MAJOR_CHANGES | 0/9 |
| 跨方向共识 Blocker | 9 个（≥2 方向 + ≥2 模型） |
| 方向专属 High | 14 个 |
| Medium/Low | 17 个 |
| 跨文档矛盾 | 3 个（P0-7 vs P0-9 RuleMod 能力范围、P0-2 §3.10 vs DESIGN §3.2 Spawn、P0-2 §10.3 vs DESIGN §3.2 Recycle） |

### 评审质量评估

- **Claude Opus 4.7 首次 profile-based 运行**: 3/3 完成，无截断。Architect 19 行浓缩版 + 独立 findings 文件；Security 68 行完整 Critical→Informational 分层；Designer 60 行终审。输出质量高，结构清晰。
- **GPT-5.5**: 3/3 完成，评审最详细（Architect 340 行、Designer 380 行），模式匹配能力强。
- **DeepSeek V4 Pro**: 3/3 完成，Security 379 行最详尽（CRITICAL 1-4 深度出色），Architect D1-D6 系统性强。

**结论**: profile-based 统一管线首次运行成功。9/9 完成率，零截断。Claude Opus 4.7 表现优于 4.8（此前多轮需 Stage1→Stage2 管线且有截断）。建议后续评审继续使用此管线。
