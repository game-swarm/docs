# R7 Designer 视角评审 — rev-claude-designer

> 评审范围：/data/swarm/docs/ 全量设计文档（design/ + specs/）
> 视角：Game Designer（玩法完整性、平衡性、可玩性、规则清晰度）
> 评审时间：2026-06-17
> 评审员：rev-claude-designer (Claude Opus 4.7)
> 性质：clean-slate 全量评审，不限于 R6 closure

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

R7 相对 R6 仅修复了 1 个 Critical（G1 OUTPUT TRUNCATED 占位符已移除，8 种 body part 完整回归）。但 R6 designer 提出的另外 2 个 Critical 与 8 个 High/Medium 中绝大多数**没有任何文档变化**——经 grep + diff 比对，Fabricate 漏洞、Drain swarm 经济、Hack 恢复矛盾、Tutorial 退还冲突、Tier 断崖、`[vanilla]` schema 缺失、Heal 语义模糊全部维持原状。同时 G1 修复过程中引入了一处新的卫生回归——`design/gameplay.md` 行 696-710 与行 732-746 是同一组 `[[body_part_types]]` (Claim + Tough) + 字段说明表的重复粘贴，且第二份的代码块围栏配对错位（缺少前置 ```toml）。

本轮 Designer 视角发现 **3 个 Critical 阻塞 + 6 个 High + 4 个 Medium + 2 个 Low**——其中：
- G1（Fabricate 经济崩盘）继承自 R6 G2，未修复
- G2（Drain swarm 群攻不对称）继承自 R6 G3，未修复
- G3（Hack 5-tick 自动恢复 vs 永久夺取跨文档矛盾）继承自 R6 G4，未修复
- G4（design/gameplay.md 行 696-746 重复定义块 + markdown 围栏错位）是 R6 G1 修复时引入的**新回归**

修复路径明确，工作量约 2-3 天，但必须在进入实现前合上——否则 MVP 编码会卡在 "Fabricate 怎么校验？" "Hack 后 drone 是否永久消失？" "Drain swarm 怎么防？" 这些战略级问题上。

---

## 2. Strengths（设计中做得特别好的部分）

### S1. Overload 抗永久锁死的数学证明（specs/02 §3.17）
依然是全文档最闪耀的章节。500k 削减 + MAX_FUEL × 0.2 下限 + fuel_budget/1000 恢复速率 + 50 tick per-target 全局冷却串成的不等式证明，把 game balance 上升到可验证的 design contract。

### S2. 特殊攻击状态机矩阵（specs/02 §3.16）
8 种特殊攻击 × 同 tick 多命中优先级 + 同类型多次叠加 + 反制窗口三张表完整定型。Drain/Leech 累加、Hack/Overload/Fortify 限一次的不对称设计在矩阵里清楚标出。

### S3. SpawningGrace 1-tick 无敌帧 + Recycle 比例退还（specs/02 §3.18）
两个机制配合关上了 R4 G1（出生即斩）和 R4 G3（末期回收套利）。`refund_pct = max(0.1, 0.5 × (remaining/total))` 数学干净。

### S4. World/Arena/PvE 三模式资源边界
Arena PvE Challenge 明确 "不影响 World 状态、不产出 World 资源、不消耗 World 资产" ——三个模式各自的设计意图和经济围栏清晰。AI 玩家与人类玩家走完全相同 WASM 部署路径继承了 R3 之后的正确设计。

### S5. 全局存储反制三件套（design/gameplay.md §314-352）
累进存储税 + 本地存储 stealth advantage + 转换需物流时间——三层叠加防止富有玩家垄断经济。Stealth Advantage 把"信息不对称"变成战略选择，是少见的非数值化反 dominant strategy 设计。

### S6. soft_launch 渐进式威胁曲线（specs/06 §2.4）
500 tick safe_mode → 1500 tick PvE-only soft_launch → 全 PvP，PvP 解除前 50 tick 广播警告。新手不会从"绝对安全"突然跳到"被老玩家碾压"。

### S7. NPC 难度按地理梯度分层（design/modes.md §9.0）
Zone 1-4 以世界中心为原点的 NPC 等级 + 资源据点密度梯度——"PvE 难度是地理属性，不是副本入口"。把 Screeps 的 inter-shard 思想移植到了同一世界内，自然鼓励玩家扩张并自我选择难度。

### S8. SDK 三层扩展模型（design/gameplay.md §430-457）
Layer 1 IDL 冻结 → Layer 2 world.toml 数值调参 → Layer 3 实验性自定义 schema + ABI hash 校验。把 90% 服主需求压在 Layer 2 不动 SDK，把模组世界标识 `[MOD]` 排名隔离做对了——保证官方排行榜的统一基线。

---
