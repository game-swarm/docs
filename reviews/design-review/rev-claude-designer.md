# R7 设计评审 — Designer 视角（Claude Opus 4.7）

> 从 kanban 日志提取（原始任务 t_4cb8527d + 重试 t_631cbc50）——write_file bug 导致原始输出丢失。

## Verdict: REQUEST_MAJOR_CHANGES

## 阻塞级别

- **Fabricate**: 经济+领地+反制漏洞未闭合。structure_type 参数、免费建筑配额、RCL/territory/counterplay 窗口全部需要修正。
- **Vanilla Tier 与 Tier 1/2 矩阵跨文档矛盾**: Standard tier 需要自定义动作但 MVP 排除了这个功能，导致 Leech/Fabricate 在 MVP 中不可用，与 "Standard+ 全部可用" 的声明冲突。

## 高优先级

- **Leech**: 缺少冷却时间和反制机制——作为无冷却自动回血技能，每 tick 都能触发且无法被打断或清除，形成对标准 Attack 的策略压制
- **specs/02 缺少 Leech/Fabricate 的完整验证矩阵**
- **specs/08 缺少 Leech/Fabricate 的详细定义**
- **Drone 内存截断顺序不明确**——随机 truncation 对 AI 玩家的确定性策略构成风险
- **gameplay.md 有重复的 Body Part 文档**——Claim 和 Tough 在行 696-710 和 732-746 重复定义

## 中等优先级

- Tutorial Tier 仅禁用特殊攻击但其他 NPC/资源差异未定义
- active_aging 110% 的设计意图不明确
- 全局存储税率上限是否足以反制大帝国囤积
- PvE 软启动 1500 tick 是否足够新手引导
- Tutorial 世界 NPC 强度没有明确弱化

## 低优先级

- Hack Neutral drone 对原所有者保持可见——可能成为信息泄露风险
- Arena PvE 挑战无重复限制
- PvE 事件触发阈值基于哈希余数可能被推断
- Fortify 冷却时间限制使单个 drone 无法更频繁施加效果

## 核心矛盾

Tier 1 MVP 应排除自定义行为注册（engine.md Tier gate 矩阵），但 Vanilla Standard+ 默认包含 Leech/Fabricate 这些特殊攻击。三条可能路径：
1. MVP 的 Vanilla Standard 只包含 6 种特殊攻击，Leech/Fabricate 延后到 Tier 2
2. Tier 1 也支持 [[custom_actions]] 的 6 个内置特殊效果
3. 把 Leech/Fabricate 直接提到核心 IDL 中硬编码
