# R3 Review: Game Designer — DeepSeek V4 Pro

**Document**: `/data/swarm/docs/design/DESIGN.md` + `/data/swarm/docs/specs/p0/` 全部
**Reviewer**: DeepSeek V4 Pro (Game Designer)
**Date**: 2026-06-14

---

## Verdict: CONDITIONAL_APPROVE

★★★★☆ — 策略深度和模组生态设计出色，两个 freeze blocker 须在 Phase 0 锁定前解决。

---

## Strengths

**S1 — 物流系统作为战略支点**
物流模式 NONE/GLOBAL/LOCAL→GLOBAL 的递进设计是 Swarm 最鲜明的战略特征。LOCAL 模式下玩家的后勤决策不是附属品而是核心博弈——每单位物资的运输成本塑造了领土扩张的真正边界。信用系统 (credit) 为短期操作提供灵活性同时形成长期激励。

**S2 — Rhai 模组系统的社区乘数效应**
Rhai 模组设计打开了引擎与玩家共创的通道。Tier 0/1/2 分级 + wasmtime 审计 + 签名信任模型给出了可实施的社区扩展安全框架。模组的 fork/PR 流授予了社区"培育"模组的权力，这是 mod.io/Steam Workshop 不可能做到的。

**S3 — 信息不对称的多层设计**
fog-of-war 分层（视觉/听觉/嗅觉）不是简单的"隐藏信息"，而是让不同侦察手段产生不同粒度的情报。结合多输出面一致性检查，侦察成为一种需要组合传感器的技能而非单纯的视野半径。

**S4 — Arena 模式的锦标赛基因**
种子洗牌 + 均衡开局 + 延迟公开排行榜 + 客户端重放验证，构成了完整的不对称信息锦标赛基础设施。这是电子竞技级别的设计严谨性。

**S5 — 双模式（World/Arena）分工清晰**
World 是持久经济沙盒，Arena 是零和博弈锦标赛。两个模式的玩家心流完全不同，但共享同一套核心机制（构建、物流、巡逻、战斗），显著降低学习成本。

---

## Concerns

**G1 — 全局存储的 dominant strategy 风险 🔴 Freeze Blocker**

全局存储（Global Storage）可以被垄断玩家囤积关键资源、切断新玩家供给、操纵市场价格。当 PvP 允许时，全球经济基础设施成为战略控制点而非公共服务。需要反制机制：累进存储税、存储上限、或本地存储独有的隐匿性/速度优势。

**G2 — 物流信用系统的无限杠杆**
credit_limit=5000 且 repayment_ticks=100 的设计下，高 rank 玩家可能通过循环借贷将信用系统转变成永久杠杆。需要更严格的信用乘数公式（如 `min(rank * 500, base_credit)`）或动态利率。

**G3 — 信息经济缺失定价机制**
fog-of-war 设计强调信息分层，但未定义信息本身的交易机制。玩家能否出售侦察数据？Arena 模式下公开发布日志的延迟是否可被购买绕过？信息市场缺失使不对称信息无法成为可交易资产。

**G4 — PvE 主导可能导致 World 模式"殖民疲劳"**
当前设计以 PvE 为主、PvP 为辅。在持久 World 中，一旦 PvE 内容被核心玩家耗尽，游戏退化为纯经济博弈。需要 PvE 内容生成机制（Rhai 驱动的动态事件、NPC 派系领土变化）。

**G5 — Rhai f64 非确定性 🔴 Freeze Blocker**

Rhai 的 f64 运算在不同平台/编译器可能产生不同结果，直接破坏确定性回放。必须：禁用 Rhai 浮点运算、或将所有 f64 参数转换为定点整数（如 `Fixed<u64, 4>`）传递。

---

## Fresh Ideas

**I1 — 物流税作为一种领土控制工具**

不只是向物流者收费，而是让领土控制者获得税收分成：

```toml
[logistics.tax]
    rate = 0.05
    controller_share = 0.50
    sink_share = 0.50
```

经过领土 X 的每单位物资，X 的控制器获得 2.5% 价值。这创造了一个新的博弈层：领土争夺不仅是资源获取，也是物流节点控制。

**I2 — 模组能力分级（Tier 0/1/2）与安全审查**

| Tier | 允许的 actions | 安装门槛 | 示例 |
|---|---|---|---|
| **Tier 0** (Economy) | deduct/award_resource, emit_event | 任何服主 | empire-upkeep |
| **Tier 1** (Mechanics) | modify_entity | Tier 0 + 代码审查签名 | alliance-system |
| **Tier 2** (World Gen) | 注册新 ECS component/entity/system | 引擎版本白名单 + 核心签名 | fog-of-war, mutation |

**I3 — "世界基因"（World DNA）——让每个世界实例可复现**

一个世界实例的完整配置（world.toml + 全部已安装模组及版本 + Rhai 脚本 + wasmtime/Rhai 锁定版本）的 Blake3 哈希。用于锦标赛规则引用、模组兼容性测试、策略分享。

**I4 — 季节性世界（Seasonal World）——World 与 Arena 之间的第三模式**

定期重置的持久世界（如每 30 天），但保留跨赛季遗产。解决 World 模式「后来者无法竞争」和 Arena 模式「没有持久感」之间的空白：

```toml
mode = "seasonal"
duration_ticks = 864000            # 30 天
legacy_bonus_per_season = 0.05
fresh_start_bonus = 200
season_leaderboard = true
```

---

## Missing (未覆盖的设计缺口)

1. **全局/本地存储的 IDL 覆盖** — transfer_to_global / from_global 需进入 P0-8 IDL 和 Command Validation Matrix
2. **Rhai mod 执行预算** — 每 mod 的 CPU 时间/指令计数限制
3. **模组依赖解析的版本语义** — dependencies 需要 semver 约束语法
4. **i18n 覆盖率工具链** — `swarm mod i18n-coverage` 命令
5. **World 模式自然资源消耗** — Source 再生 vs 玩家消耗速率的平衡点
6. **多房间市场套利** — 需明确市场是 per-room, per-world 还是 per-shard

---

## Verdict Summary

| 维度 | 评级 | 关键信号 |
|---|---|---|
| 策略深度 | ★★★★☆ | 物流+构建+信息+时序四轴交织；全局存储 dom 风险待解 |
| 信息不对称 | ★★★★★ | fog-of-war 分层 + 多输出面一致性 + Arena 延迟公开 |
| PvE/PvP 均衡 | ★★★☆☆ | PvE 主导是设计结果非缺陷；全局存储需修正 |
| 社区扩展性 | ★★★★★ | Rhai 模组 + 市场 + fork/PR 模型是生态乘数器 |
| 博弈公平性 | ★★★★☆ | 种子洗牌 + 先到先得 + 部分 refund 成熟 |
| 设计可复现性 | ★★★★☆ | 缺少 World DNA / Seasonal world 机制 |

**Freeze Blockers (Phase 0 锁定前必须解决)**:

1. **G1 — 全局存储 dominant strategy**：需要反制机制使本地存储与全局存储之间存在非平凡的策略权衡。

2. **G5 — Rhai f64 确定性风险**：必须禁用 Rhai 浮点或将所有 f64 参数转换为定点整数传递。

这两个问题触及核心设计合同：G1 影响 World 模式的 PvP 经济基础，G5 影响确定性回放保证。其余 concerns 可在 Phase 1-2 解决。

---

*评审人: DeepSeek V4 Pro (Game Designer Reviewer)*
*文件: /data/swarm/docs/reviews/r3-rev-dsv4-designer.md*
