# R6 Architect Review — claude-sonnet-4-6

**回合**: R6 | **日期**: 2026-06-14 | **评审者**: claude-sonnet-4-6 (Architect)
**覆盖文档**: DESIGN.md + P0-1 ~ P0-9

---

## VERDICT: CONDITIONAL_APPROVE

零 Critical。零 High。Phase 0 Architecture Freeze 已充分收敛。条件项均为 Phase 1+ 实现细节，无架构阻断。

---

## Issues

### Medium

**M1 — P0-4 §3.1: `tick()` 返回值语义模糊**
- 文件: `specs/p0/04-wasm-sandbox-baseline.md` §3.1
- IDL 中 `tick` 返回 `i32`（"0 = success, pointer to command JSON in WASM memory"），但 WASM 线性内存指针实际上是 32-bit 无符号偏移量，用 `i32` 表示时负值空间（高位指针）语义未定义。当 WASM 模块将内存分配在 >2GB 偏移时，`i32` 截断会导致指针错误。
- 建议: 返回值改为 `u32`（指针偏移），或采用 out-parameter 模式（`tick(snapshot_ptr, snapshot_len, out_ptr_ptr, out_len_ptr) -> i32` 其中 i32 仅表示 error code）。P0-8 IDL 中同步修正。
- 阶段: Phase 1 实现前需确认。

**M2 — P0-2 §3 + P0-8: `Harvest` 命令 `resource` 字段可选性不一致**
- P0-2 §3.3 的 Harvest 校验规范里 `target.source.energy` 是硬编码字段，未引用 `resource` 参数。
- P0-8 IDL 中 `Harvest.params` 含 `resource: ResourceName?`（可选）。
- DESIGN.md §8 已明确支持多资源 Source（`produces: { Crystal: 1, Gas: 1 }`）。
- 当 Source 产出多种资源时，省略 `resource` 字段的行为（采全部？采第一个？报错？）在 P0-2 中没有定义。
- 建议: P0-2 §3.3 补充当 `resource` 为 null 且 Source 产出多种资源时的行为规则（推荐: 若 Source 仅一种资源则默认采该资源，否则 `RejectionReason::AmbiguousResource`）。
- 阶段: Phase 1 实现前需确认。

**M3 — P0-1 §3.4 + P0-9: Tick 放弃时 `RuleMod` fuel 退还行为未定义**
- P0-1 §3.4 规定 FDB commit 失败时 WASM fuel 退还玩家。
- P0-9 中 `RuleMod` 来源有 `Rhai op budget`，但 tick 放弃时 Rhai 模组的执行副作用（`actions.deduct_resource` 已在内存中执行但未提交到 FDB）的回滚语义未说明。
- 建议: P0-1 §6 失败模式矩阵增加一行 `RuleMod execution partial`，明确 tick 放弃时 Rhai actions 自动随 FDB 事务回滚（因为 `actions.apply(world)` 在 FDB 事务内）。
- 阶段: Phase 1 实现前需确认。

### Low

**L1 — DESIGN.md §3.2 + P0-1 §3.3: ECS System 顺序重复定义，存在微小差异**
- DESIGN.md §3.2 的 tick 执行顺序为: `build → harvest → regeneration → movement → combat → decay → death → spawn`
- P0-1 §3.3 的顺序完全相同，但 DESIGN.md 在 `harvest` 和 `regeneration` 之间没有明确谁先的描述，而 P0-1 有 `.chain()` 保证串行。
- 实际上两个文档一致，但若将来修改顺序，两处都要同步——容易出现 drift。
- 建议: DESIGN.md §3.2 加一行注释 `# 权威顺序定义见 P0-1 §3.3`，避免未来维护分叉。

**L2 — P0-7 §7: `damage_multiplier` 校验逻辑错误**
- `validate_config` 中有 `if config.combat.damage_multiplier < 1 { errors.push(...) }`
- 但按照 DESIGN.md §8.2 的表格，`damage_multiplier` 类型为 `fixed<u32,4>`，表示 `× 10000`，默认值 `10000 = 1.0`。小于 1.0 的倍率（如 0.5 = 5000）在游戏设计上是合理的（低伤害和平模式）。
- 校验应为 `< 0` 而非 `< 1`。
- 建议: 修正为 `if config.combat.damage_multiplier == 0 { errors.push("damage_multiplier cannot be zero") }`。

**L3 — P0-9 §2.1: 来源矩阵 Section 编号跳跃（残留问题）**
- R5 Verdict 记录了 B1 修正 "§4→§6"，但当前文档中 Section 编号为 §2、§3、§6（缺少 §4、§5），仍然跳跃。
- 与 R5 修正说明不符——R5 说的是修正 §4→§6 的跳跃，但文档中 §4/§5 实际不存在，数字是 §2、§3、§6、§5（乱序）。
- 建议: 将 P0-9 各 Section 重新按 §1→§2→§3→§4→§5→§6→§7 顺序排列。

**L4 — P0-3 §5.1 vs P0-8 IDL: `swarm_simulate` 限流配置冲突**
- P0-3 §4.4 将 `swarm_simulate` 列为 "按需"（无明确限流）。
- P0-9 §2.2 规定 `Simulate` 来源限流 `5/tick`。
- 两处定义不一致。
- 建议: P0-3 §4.4 的 `swarm_simulate` 限流列更新为 `5/tick（World）/ 3/tick（Arena）`，与 P0-9 对齐。

**L5 — DESIGN.md §8 双重 Section 10**
- 文档中有两个 `## 10.`：一个是 "World 模式 vs Arena 模式"，另一个是 "贡献指南"。
- 建议: 贡献指南改为 `## 11.`。

---

## Strengths

**S1 — 单一管线 + 不可伪造 Auth Context 的架构纪律**
P0-2 的单一校验管线（所有来源走同一 `校验 → 应用` 路径，无绕过）+ P0-9 的服务端注入 auth context，形成了坚实的安全边界。没有给「管理员便捷通道」留后门，架构一致性极高。

**S2 — 确定性合同的完整性**
DESIGN.md §8.8 将确定性约束落实到每一个可能引入非确定性的点：PRNG 算法固定（ChaCha12）、Hash 固定（Blake3）、禁 f64/std::hash/Rhai 浮点、IndexMap 替换 HashMap、ECS `.chain()`。这个合同比同类项目通常看到的要细致得多，是回放和反作弊的坚实基础。

**S3 — Deferred Command Model 的清晰性**
WASM `tick() → Command[]` 模型消除了竞态条件（WASM 无法在执行中途修改世界状态），并使校验和执行完全解耦。P0-8 IDL 驱动代码生成的设计让 WASM/MCP/REST 三个入口共享同一校验逻辑，减少了不一致的根本来源。

**S4 — Fuel Refund 的安全建模**
P0-2 §7 的退还时序（next_tick credit）、上限（MAX_FUEL × 10%）、连续高退还 throttle，三层防护合理覆盖了退还滥用的主要攻击面。尤其是「同 tick 内不得通过竞争失败获取计算预算」这条规则——这是一个不显眼但重要的安全属性。

**S5 — World Rules Engine 的可组合性**
Rhai 模组 + ECS Plugin 注入的规则架构，做到了核心引擎不知道规则的存在。执行预算（10,000 AST 节点、100 actions/tick、100ms 墙钟）+ 连续超限自动禁用，给了模组足够的沙箱而不影响引擎主路径。这是比硬编码规则健壮得多的设计。

**S6 — MCP 与 Web UI 的对等原则**
「MCP 不做游戏动作，AI 必须编写 WASM 代码」这个设计决策在 P0-3 中阐述清晰，且在 P0-9 来源矩阵中形式化。它同时解决了公平性（AI 和人类同一沙箱）和安全性（MCP 无法绕过 Command 校验）两个问题，一个原则解决两个问题，设计优雅。

---

## 综合评估

文档经过 R3→R5 三轮迭代，架构层面已无 Critical 或 High 问题。六个 Medium/Low 问题中：
- M1（指针语义）和 M2（多资源 Harvest 歧义）需要在 Phase 1 实现前补充规范，但不影响现有架构决策。
- M3（RuleMod tick 放弃回滚）实际上已被 FDB 事务语义覆盖，补充说明即可。
- L1-L5 均为文档精度问题，不影响实现。

**Phase 0 Architecture Freeze 状态维持。可以进入 Phase 1 实现。**

---

*Reviewer: claude-sonnet-4-6 (Architect) | Round: R6 | 2026-06-14*
