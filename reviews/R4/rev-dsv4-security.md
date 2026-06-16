# R4 Security Review — rev-dsv4-security

> 审计日期: 2026-06-16
> 审计员: DeepSeek V4 Pro (rev-dsv4-security)
> 审计范围: /tmp/swarm-review-R4/ 下全部 12 份文档
> 审计视角: 信任边界 / 攻击面 / 权限模型 / 协议安全性 / 数据完整性

---

## Verdict: CONDITIONAL_APPROVE

**概述**: 设计在安全架构层面高度一致。单一 validate_and_apply() 管线、WASM 沙箱三层隔离、可见性统一过滤、MCP 只读约束 构成了坚实的安全基线。发现 3 个 High 问题（快照截断武器化、Adversarial 寻路 DoS、确定性假设未强制执行）、5 个 Medium 问题、3 个 Low 问题。建议收敛 High 问题后 Approve。

---

## 安全亮点 (Strengths)

1. **单一指令管线** — 所有来源 (WASM / MCP / Admin / Rhai) 走同一个 `validate_and_apply()` 路径。Admin 不享有独立代码路径，编译期通过 `WorldMutate` trait 防止绕过。这是安全设计的黄金标准。

2. **三层 WASM 沙箱** — Wasmtime fuel metering + seccomp(bpf) 白名单 + cgroup v2 资源限制 + 每 tick fork-kill 生命周期。跨 tick 无状态残留，消除持久化恶意模块风险。

3. **Deferred Command Model** — WASM 不得调用任何 mutating host function。所有游戏动作通过 `tick() → JSON` 返回，由引擎统一校验和应用。杜绝了沙箱内直接修改世界状态的可能。

4. **可见性优先原则** — `is_visible_to()` 单函数覆盖所有输出面 (snapshot / MCP / WS / REST / replay)。不可见目标统一返回 `NotVisibleOrNotFound`，无法区分"不存在"与"不可见"——防 oracle 攻击的标准做法。

5. **MCP 治理边界清晰** — MCP 明确不提供 `swarm_move/attack/build` 等游戏动作。AI agent 必须编写 WASM 代码，与人类走相同路径。公平性天然保证。

6. **种子洗牌 + FDB 原子提交** — 每 tick 玩家执行顺序由 Blake3 XOF 确定随机，无法预测。FDB 严格可序列化事务保证每 tick 全提交或全回滚。

7. **DNS rebinding 防御** — 端到端覆盖了 loopback / private network / container escape / SSE rebind / SSRF 五个向量。

8. **Rhai 模组签名机制** — Ed25519 签名强制验证，无"允许未签名"模式。compilation cache key 包含 security_epoch 支持全量吊销。

9. **refund 防滥用机制** — 同源重复失败仅首次退 50%，连续高退还率 throttle 至 50% fuel，deploy 时跨版本 reset refund credit。

10. **Prompt injection 防御** — AI SDK 使用分隔符包裹游戏数据，所有玩家原创字符串标注 `_untrusted_game_data` + `source_player`。

---

## Critical 级问题

无。

---

## High 级问题

### H1: 快照截断可被武器化 (Snapshot Truncation Weaponization)

- **文件**: specs/01 §2.3, specs/04 §6
- **严重程度**: High
- **类别**: 数据完整性 / 信任边界

**问题描述**:

当玩家 snapshot 超过 256KB 时，系统按分桶权重截断：
1. 关键桶（Spawn/Controller/己方 depot）—— 无条件保留
2. 高优先桶（己方 drone/建筑）
3. 中优先桶（敌方可见实体/资源点）
4. 低优先桶（友方/中立实体）

攻击者可故意在敌方视野边缘部署大量廉价 drone（低 body part 成本如 [MOVE]），推动敌方 snapshot 超过 256KB 阈值。由于"关键桶无条件保留"未设置数量上限，而"中优先桶"中的敌方实体可能被截断，攻击者的实际威胁单位（如带 Hack 的 drone）可隐藏在截断边界之外。

**攻击场景**:
1. 攻击者生产 200 个 [MOVE] drone，将其散布在目标玩家视野边缘
2. 目标玩家 snapshot 达到 256KB → 触发截断
3. 关键桶保留 Spawn/Controller，但中优先桶中攻击者的特殊攻击 drone (Hack/Overload) 被 distance 排序挤出
4. 目标玩家的 WASM 代码看不到这些威胁，无法做出防御响应
5. 攻击者发起特殊攻击 → 目标玩家只能在 Phase 2a 校验时发现（为时已晚，无法主动规避）

**建议**:
- 为"关键桶"设置明确的数量上限（如最多 50 个实体），剩余也参与截断
- 截断时优先保留标记为"敌对"或"最近发生过 hostile action"的实体
- 在 snapshot metadata 中明确列出被截断的实体类别统计（而不仅是一个 `truncated=true` 标志）
- 考虑将 snapshot 大小上限设为可配置项，而非硬编码 256KB

---

### H2: Adversarial 地图可导致寻路 DoS (Pathfinding DoS via Adversarial Maps)

- **文件**: specs/04 §8, specs/08 (IDL path_find)
- **严重程度**: High
- **类别**: 攻击面 / 资源耗尽

**问题描述**:

`host_path_find` 的成本模型为 `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`，per-player per-tick 上限为 10 次调用 + 100,000 explored_nodes 总额度。

但 A* 的最坏情况行为可被精心设计的地形触发：
- 长蛇形走廊 + 死胡同组合：A* 会探索死胡同的全部节点后才回溯
- 迷宫地形：explored_nodes 可达 O(N²) 其中 N 是走廊长度
- `MAX_PATH_LENGTH = 100` 防止了搜索爆炸，但攻击者可以在 100 格范围内构造"几乎不可达"的地形

**攻击放大**: 一个有 500 drone 的玩家，每 drone 调用 10 次 path_find（最大值），即 5000 次调用。即使每次调用消耗 1000 fuel，总额外 fuel 消耗为 5M——对引擎的计算负载接近单玩家总 fuel 预算的一半。

结合 H1 的快照截断，攻击者可以让目标玩家的 drone 在不知情的情况下反复尝试寻路到"看起来可达但实际不可达"的目标。

**建议**:
- 对 `host_path_find` 增加 per-drone 调用上限（当前仅 per-player）
- 对不可达目标的快速失败检测：若 A* 在 explored_nodes < 100 时确定不可达，跳过剩余节点探索
- 对 cache_miss_penalty 设明确上限值
- 增加 per-tick 全局 path_find fuel 消耗监控指标

---

### H3: 确定性保证依赖未强制执行的假设 (Determinism Depends on Unenforced Assumptions)

- **文件**: specs/01 §7, DESIGN §3.3
- **严重程度**: High
- **类别**: 数据完整性 / 回放安全

**问题描述**:

确定性合同声明: "相同初始状态 + 相同 seed + 相同指令 + 相同 world_config + 相同模组版本 → 相同 state_checksum"。这一合同依赖以下未在协议层强制执行的假设：

1. `indexmap` 迭代顺序必须在所有平台上一致（spec 声明但版本差异未被检测）
2. 定点数运算必须使用相同实现（spec 声明使用 `fixed` crate 但未锁定版本）
3. Blake3 实现的跨版本输出一致性（Blake3 本身保证但 Rust crate 的 API 变更可能引入差异）
4. Bevy ECS 的 `.chain()` 和 `.before()/.after()` 调度在不同 Bevy 版本间可能改变

当前设计通过 `manifest_hash` 在部署时做版本匹配，但这仅覆盖编译期。若引擎在运行时加载了不同版本的依赖（如系统级动态链接），manifest_hash 无法检测。

**回放断裂场景**:
- 引擎升级 Wasmtime 版本（CVE 修复）→ Wasmtime =30.0 的回放数据在 =31.0 下可能产生不同结果
- 文档声明回放时执行存储的 Command[] 不重新调用 WASM——这绕过了 Wasmtime 兼容性问题
- 但如果引擎本身的 ECS 调度因 Bevy 版本变化而改变，Command[] 回放仍然会 diverged

**建议**:
- 对 `state_checksum` 计算中包含的依赖项版本做显式记录（Bevy / indexmap / fixed / Blake3 crate version）
- CI 中加入跨版本回放验证（使用上一版本的 keyframe + delta 链在新版本引擎上回放）
- 考虑将引擎二进制本身的 hash 纳入回放元数据
- FDB 中 keyframe 应与 `wasmtime_version + bevy_version + engine_commit` 绑定存储

---

## Medium 级问题

### M1: Rhai "inprocess" 隔离模式风险 (Rhai Inprocess Isolation Risk)

- **文件**: specs/07 §5.1
- **严重程度**: Medium
- **类别**: 信任边界 / 沙箱逃逸

**问题描述**:

`[rhai] isolation = "inprocess"` 允许 Rhai 脚本在引擎进程内运行。文档标注"需信任所有模组来源"，但：
- 服主可能不理解"信任"的安全含义
- Rhai AST 解释器本身的 sandbox 保证不如 WASM 严格
- 恶意模组可通过 CPU 耗尽、栈溢出、或 Rhai 引擎的未知漏洞影响核心引擎进程
- 进程内模式绕过了进程隔离模式下的 cgroup/seccomp 保护

**建议**:
- 将 `inprocess` 标记为 deprecated 或仅在 debug builds 中可用
- 若保留，启动时输出显式安全警告（STDERR 红色文本）
- 为 `inprocess` 模式添加独立的 AST 节点预算和墙钟超时

---

### M2: Snapshot 构建时序可能与 WASM 执行并发 (Snapshot-WASM Concurrency Edge)

- **文件**: specs/01 §2.3, DESIGN §3.2
- **严重程度**: Medium
- **类别**: 协议安全性 / TOCTOU

**问题描述**:

两阶段快照架构声明"快照构建在玩家 WASM 执行前完成，天然确定"。但 spec 同时说 COLLECT 阶段对每个玩家是并行的（sandbox worker pool）。

如果快照按房间分片构建，而玩家 WASM 在快照完全构建前开始读取——这理论上不会发生（快照构建是同步的），但文档未明确快照构建的原子性保证：是所有玩家的 snapshot 一次性构建完成，还是每个玩家独立构建？

如果快照是"一次性构建"的（COLLECT 开始时），那么在快照构建和 WASM 执行之间的 gap 没问题（快照是 immutable）。但如果快照是 per-player 延迟构建的，不同玩家的 snapshot 可能反映略微不同的世界状态。

**当前解读**: DESIGN §3.2 说"tick 开始时一次性构建完整世界快照"，这暗示所有玩家的 snapshot 来自同一时刻。但"按房间分片"和"按玩家拼接"的描述在实现中可能引入不一致。

**建议**:
- 在 spec 中明确：snapshot 的根数据来自 tick 开始时的一次性序列化，所有玩家的 snapshot 是此根数据通过 `is_visible_to` 过滤的子集
- CI 中加入断言：同一 tick 内不同玩家的 snapshot 中对同一 public 实体的表示完全一致

---

### M3: Overload 三种结果等价合同的信息泄露风险 (Overload Result Indistinguishability)

- **文件**: specs/02 §3.12
- **严重程度**: Medium
- **类别**: 协议安全性 / 信息泄露

**问题描述**:

Overload 的"三种结果等价合同"从攻击者视角不可区分成功/触及地板/已在地板。但从**目标玩家**视角：

- 目标玩家在下 tick 获取 snapshot 时会看到自己的 fuel budget
- 如果 fuel budget 从 5M 降到 4.5M（成功被 Overload），目标知道发生了 Overload
- 如果 fuel budget 保持在 2M 不变（已在地板），目标也知道自己被 Overload 但对方白费了

目标玩家可以通过分析自身 fuel 变化推断攻击者的 Overload 是否"成功"——这创造了间接的 oracle。

**实际影响**: 低。目标知道被攻击是预期行为（"战术压制"），但"攻击者是否触及地板"这个额外信息位在设计中未被考虑。攻击者可以通过观察目标后续行为变化间接推测（spec 承认此点），但 timing side-channel 可能更精确。

**建议**:
- 在 Overload response 中加入随机延迟（0-2 tick）再反映 fuel 变化
- 或在文档中明确承认此信息位，列为可接受的战术情报

---

### M4: COLLECT 缓存复用时的非确定性风险 (COLLECT Cache Non-Determinism)

- **文件**: specs/01 §3.5, ROADMAP §S1
- **严重程度**: Medium
- **类别**: 数据完整性

**问题描述**:

FDB commit 失败后重试时复用 COLLECT 阶段的缓存结果（相同命令序列 + fuel 扣费）。spec 声明"跨重试 fuel 消耗上限 = 1 × MAX_FUEL"。

未明确的问题：
1. 若 COLLECT 阶段的快照在首次执行时包含了某实体，但该实体的可见性在后续 tick 会改变——由于不重新 COLLECT，被缓存的命令基于"可能已过时"的 visibility 状态提交
2. 重试时直接进入 EXECUTE 阶段，但 EXECUTE 开始前的 Bevy World snapshot 是基于**当前**状态的——与缓存的命令基于的快照状态可能不一致

**现有保护**: Bevy World 快照在 Phase 2a 前捕获。COLLECT 缓存的命令是"在原始快照可见性下的合法意图"。若 FDB commit 失败 → Bevy World 恢复 → 使用缓存命令重新执行 → 命令在新快照上可能因 entity 状态变化而被拒绝。这是安全的（拒绝而非错误执行），但导致了非确定行为（有些 tick 命令被接受，有些被拒绝）。

**建议**:
- 在 COLLECT 缓存中同时记录快照的 `state_checksum`
- 重试时若当前 state_checksum 与缓存不一致，丢弃缓存并重新 COLLECT
- 或在文档中明确此行为为"acceptable non-determinism（仅影响拒绝/接受，不影响正确接受的结果）"

---

### M5: 种子轮换边界未明确定义 (Seed Rotation Boundary Ambiguity)

- **文件**: specs/01 §3.1
- **严重程度**: Medium
- **类别**: 协议安全性 / 确定性

**问题描述**:

`world_seed` 每 10,000 tick 轮换：`new_seed = Blake3(old_seed || current_tick)`。spec 说 TickTrace 记录每 tick 使用的 seed epoch。

问题：种子轮换发生在 tick 的哪个阶段？
- 若在 tick 开始时轮换 → tick N=10000 使用新种子，tick N=9999 使用旧种子
- 若在 tick 结束时轮换 → 相反

这直接影响 `seeded_shuffle` 的结果，从而影响回放确定性。TickTrace 记录 seed epoch 是正确的，但轮换时机必须在 spec 中明确定义。

**建议**:
- 明确声明：种子轮换在 tick_counter 递增后、下一 tick COLLECT 阶段开始前发生
- 即 tick N 使用 `epoch = floor(N / seed_rotation_interval)` 对应的种子

---

## Low 级问题

### L1: 回放指令注入风险 (Replay Command Fabrication)

- **文件**: specs/01 §6.3
- **严重程度**: Low
- **类别**: 数据完整性

**问题描述**: 回放时引擎直接执行 FDB 中存储的 Command[]。若攻击者获取 FDB 写入权限（如通过引擎漏洞），可注入伪造 Command[] 到历史 tick 记录中，制造虚假的回放历史。当前设计信任 FDB 中的数据完整性（假设 FDB 访问受控），但未在存储层加入 Command[] 的完整性校验（如每个 tick 的 command_merkle_root）。

**建议**: 可选。在 TickTrace 中为每 tick 的 Command[] 计算 Merkle root，使回放验证可检测篡改。

---

### L2: WASM 模块编译超时 30s 的解耦风险 (Compilation Timeout Decoupling)

- **文件**: specs/04 §7
- **严重程度**: Low
- **类别**: 攻击面

**问题描述**: WASM 编译超时设为 30s，但 deploy nonce TTL 仅为 60s。若编译接近 30s 完成，客户端需在剩余 30s 内提交 deploy_token。对于网络延迟高的 AI agent（如通过卫星连接的 MCP 客户端），此窗口可能不足。

**建议**: deploy_token TTL 保持 30min（spec 已定义），但编译完成后主动通知客户端（通过 MCP push/SSE），而非依赖客户端轮询。

---

### L3: 教程世界隔离声明的边界模糊 (Tutorial World Isolation Boundary)

- **文件**: specs/09 §2.4
- **严重程度**: Low
- **类别**: 权限模型

**问题描述**: Tutorial source 指令仅可在 `world.mode = "tutorial"` 的世界中接受。但 Tutorial 世界的全局存储使用独立 namespace `tutorial_{world_id}`。如果两个 Tutorial 世界使用相同的 world_id（如配置错误），它们的存储 namespace 会冲突。

**建议**: Tutorial namespace 应使用 `tutorial_{world_id}_{instance_id}` 或包含随机后缀。world_id 唯一性由部署运维保证，但纵深防御更好。

---

## 审查覆盖矩阵

| 维度 | 覆盖文件 | 关键发现 |
|------|---------|---------|
| 信任边界 | DESIGN, 03, 04, 07, 09 | H3 (确定性), M1 (Rhai inprocess) |
| 攻击面 | 01, 02, 04, 08 | H1 (快照截断), H2 (寻路 DoS), L2 (编译超时) |
| 权限模型 | 03, 05, 09 | L3 (tutorial 隔离), 亮点 #5 (MCP 边界) |
| 协议安全性 | 01, 02, 03, 08, 09 | M2 (快照原子性), M3 (Overload oracle), M4 (COLLECT 缓存), M5 (种子轮换) |
| 数据完整性 | 01, 06, 07 | H3 (确定性假设), L1 (回放完整性) |

---

## 交叉引用依赖

| 本报告问题 | 可能被以下 spec 章节影响 |
|-----------|----------------------|
| H1 (快照截断) | specs/01 §2.3, specs/05 §3, specs/04 §6 |
| H2 (寻路 DoS) | specs/04 §8, specs/08 path_find |
| H3 (确定性) | specs/01 §7, DESIGN §3.3, ROADMAP |
| M1 (Rhai 隔离) | specs/07 §5.1 |
| M2 (快照原子性) | specs/01 §2.3, DESIGN §3.2 |
| M3 (Overload oracle) | specs/02 §3.12 |
| M4 (COLLECT 缓存) | specs/01 §3.5, ROADMAP §S1 |
| M5 (种子轮换) | specs/01 §3.1 |

---

## 与 R3 评审的连续性问题追溯

| R3 发现 | R4 状态 |
|---------|--------|
| C1: Rhai isolation 矛盾 | M1: inprocess 模式仍存在，但已文档化风险。风险降级至 Medium |
| C2: Overload side-channel | M3: 三种结果等价合同已实现，但从目标视角的间接 oracle 仍存在。降级至 Medium |
| H1: refund session 歧义 | 已收敛: refund credit 按 session_id 作用域明确 |
| H2: path_find fuel/cost 不匹配 | H2: R4 改为按实际工作量计费（explored_nodes × 500 + edges × 200），更精确但 adversarial 地图风险仍存在 |
| H3: simulate 资源边界 | 已收敛: specs/04 §6.1 定义了完整的 simulate caps |

---

## 结论

R4 设计在安全层面是成熟的。11 个高亮点的设计质量达到生产级标准（尤其是单一指令管线、WASM 三层沙箱、可见性统一过滤）。3 个 High 问题均可通过 spec 级别的约束或配置调整解决，不涉及架构重构。

**建议收敛路径**:
1. H1 (快照截断武器化) — 为关键桶设数量上限 + 截断统计明细 → spec 修改
2. H2 (Adversarial 寻路) — per-drone path_find 上限 + 不可达快速失败 → spec 修改
3. H3 (确定性假设) — 跨版本回放 CI + 依赖版本绑定 → CI + spec 修改

收敛上述 3 个 High 问题后 → APPROVE。
