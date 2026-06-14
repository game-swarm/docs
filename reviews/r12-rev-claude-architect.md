# R12 架构评审 · Claude Opus 4.8（Architect）

> 零上下文架构评审最终意见。本文档汇总 Stage 1 发现，给出裁决与设计优点。

## VERDICT: REQUEST CHANGES（请求修改）

冻结架构在确定性契约上存在两处 **Critical** 违背，必须修复后方可进入实现阶段。
其中 A1（墙钟预算）与 A2（HashMap）会直接导致跨进程回放分叉，触碰项目最核心的
确定性保证。另有 4 项 **High** 揭示沙箱生命周期、存储模型、分片与状态快照的内部
自相矛盾，属于"冻结但未对齐"的隐藏断点，留到实现期会演变成返工。2 项 **Medium**
为可见性与预算口径的低估，需澄清但不阻塞。

整体方向正确、确定性意识已贯穿设计；问题集中在"契约声明"与"具体机制"之间的
落地缝隙。修订后预计可收敛。

---

## 阻塞项（必须修复）

| 编号 | 等级 | 摘要 |
|------|------|------|
| A1 | Critical | Rhai 模组墙钟预算（100ms/tick）作为终止条件破坏确定性，actions 进世界状态导致 checksum 分叉。终止条件须改为确定性预算（AST 节点/op 计数），墙钟降级为只读监控告警 |
| A2 | Critical | ResourceRegistry `types`/`action_costs` 仍用 std::HashMap，违反 Determinism Contract。改 IndexMap + CI 静态检查禁止模拟路径出现 std::HashMap |
| A3 | High | 每 tick 全量落 FDB（P0-1 §6.3.1）与"每 N tick 快照"（DESIGN §2.1/§3.2）矛盾。统一为 commands+rejections 每 tick、full state 周期快照，回放由 snapshot+commands 重建 |
| A4 | High | Sandbox "每 tick fork→kill" 与模块缓存/epoch 常驻线程/gRPC 长连三处冲突，且 500 玩家进程风暴无可行性核算。统一为常驻 per-player worker（实例级重置）或真 fork 之一并重写生命周期 |
| A5 | High | Phase 7 分片与全局种子洗牌不可调和：跨分片全局玩家顺序、跨房间指令的单一 FDB 事务原子性与确定排序均未定义 |
| A6 | High | Bevy World 每 tick 内存快照/恢复的成本与机制（组件级 diff？双缓冲？）未定义，与 §4.1 delta 的 before/after 关系未规定，可能成为 tick 预算杀手 |

## 澄清项（不阻塞）

| 编号 | 等级 | 摘要 |
|------|------|------|
| A7 | Medium | "按房间序列化一次再过滤"假设站不住：可见性含"R 及相邻房间"视野并集，按玩家动态决定，过滤复杂度被低估 |
| A8 | Medium | Host function 预算两处口径不一致：P0-4 §6 总额 1000/tick 与 P0-2 §4 分项（get_objects_in_range 5、path_find 10）的包含关系未说明 |

---

## 设计优点（Strengths）

1. **确定性被提升为一等契约**。§8.8 Determinism Contract 显式列出"HashMap→indexmap"等
   规则，并贯穿到回放保证（P0-1 §6.3）。本轮 Critical 恰恰是该契约自身的执行缺口而非
   理念缺失——说明评审标尺正确，修复是补齐而非重构。

2. **回滚语义清晰**。EXECUTE 前快照 + FDB 回滚时 `world.restore(snapshot)`（P0-1 §3.4）
   建立了"模拟先行、失败可逆"的正确事务模型；缺的是成本与实现机制，而非方向。

3. **种子洗牌兼顾公平与确定**。P0-1 §3.1 对全部 active_players 排序洗牌，在单引擎下
   同时解决了公平性与可重放性，是经过推敲的设计；A5 只是它在分片维度尚未延拓。

4. **沙箱安全分层到位**。epoch_interruption、host function 调用配额、查询类细分限额
   （P0-2 §4）显示对不可信模组代码的资源滥用面有系统性防护意识。

5. **存储职责分层意识存在**。tick 级 commands/rejections 与周期性 full snapshot 的
   双轨思路在文档中已有雏形，A3 只需把两处描述对齐到同一模型即可。

6. **关注点分离的文档结构**。DESIGN（是什么/为什么）/ROADMAP（怎么做）/tech-choices
   （用什么）三分，使架构契约可被逐条审计——本轮能精确定位到 §/line 即得益于此。

---

## 收敛建议

A1、A2 为机械性修订，改完即闭环。A3 是文档对齐（选定双轨模型并统一措辞）。
A4、A5、A6 需要补一节"实现机制规格"：分别定稿沙箱生命周期、分片下的全局排序协议、
ECS World 快照策略。建议这三项各出一页设计增补后再过一轮 Architect 评审确认收敛。
A7、A8 在对应章节加一段澄清即可。
