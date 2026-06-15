# Architect 评审 — Swarm DESIGN.md

> 评审员: Claude Opus 4.8 (Architect) | 视角: 边界/耦合/爆炸半径/扩展性

## Verdict

**APPROVE_WITH_RESERVATIONS（带保留批准）**

架构内核扎实且自洽——确定性核心 + WASM 沙箱 + ECS + 延迟指令构成清晰的可信边界。可进入实现，但两处**确定性契约自相矛盾**（A1 墙钟终止、A7 模组顺序）必须在 ABI/IDL 冻结前解决，否则将导致世界状态分叉，是不可回退的根因缺陷。单世界扩展上限（A2/A3）须显式声明为「多世界水平扩展」策略，不能假装大世界可无限增长。

## Strengths

- **延迟指令模型 + 只读 host function**：可信边界清晰，审计面收敛，玩家代码无法直接写世界状态。
- **fuel metering（指令数计核）**：以确定性指标核算 CPU，回放/重模拟一致——这是确定性设计的正确锚点。
- **ECS `.chain()` 组合性**：新机制以低耦合方式扩展，系统间依赖显式可控，爆炸半径受限于单个 system。
- **三阶段 tick（COLLECT/EXECUTE/COMMIT）边界干净**：读写分离明确，并行收集与串行执行的职责划分合理。
- **WASM 单执行器统一**：AI 与人类玩家共享同一公平性模型，无特权旁路通道。

A1–A7 完整发现见 claude-architect-findings.md。关键路径：确定性契约 + ABI 冻结须最先，Rhai 集成不可与之并行。
