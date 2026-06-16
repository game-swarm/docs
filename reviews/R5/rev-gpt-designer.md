# R5 闭合验证评审 — rev-gpt-designer

## 总体 Verdict

CONDITIONAL_APPROVE

9/10 项已充分闭合；D-4 仍为轻微但明确的文档缺口：当前文档对 Tier 2/3 快照扩展给出了技术方向和必须补 spec 的门槛，但尚未达到“spec-ready”。该缺口不阻止 Tier 1/MVP 实现，但应在进入 Tier 2/3 或宣称冻结前修正。

## 逐项判定表

| ID | 状态 | 证据/缺口 |
|----|------|----------|
| B1 | CLOSED | `specs/07-world-rules-engine.md:313` 定义 Rhai actions 事务缓冲；`specs/07-world-rules-engine.md:353`-`specs/07-world-rules-engine.md:359` 明确不能绕过 Command Validation、不能直接写 ECS、RuleMod 是世界规则系统；`specs/07-world-rules-engine.md:377`-`specs/07-world-rules-engine.md:385` 定义 Ed25519 签名、版本锁定、trusted_keys、CRL、epoch、回滚与唯一生产 inprocess 模式。|
| B2 | CLOSED | `specs/04-wasm-sandbox-baseline.md:291`-`specs/04-wasm-sandbox-baseline.md:301` 给出 WASM fuel/内存/墙钟/host function/path_find/输出上限；`specs/04-wasm-sandbox-baseline.md:303`-`specs/04-wasm-sandbox-baseline.md:316` 给出 `swarm_simulate` 的 max_ticks、max_entities、CPU、hourly fuel、并发限制；`specs/04-wasm-sandbox-baseline.md:346`-`specs/04-wasm-sandbox-baseline.md:350` 定义 `host_path_find` 按实际工作量计费、调用/节点上限和 deterministic fail。|
| B3 | CLOSED | `specs/01-tick-protocol-spec.md:130`-`specs/01-tick-protocol-spec.md:171` 定义 snapshot 256KB 上限、分桶截断、确定性排序、truncated/omitted/snapshot_len 输出；`specs/01-tick-protocol-spec.md:173`-`specs/01-tick-protocol-spec.md:179` 定义实体膨胀、出口视野扩展、截断频率、path_find 膨胀的滥用响应；`specs/01-tick-protocol-spec.md:465`-`specs/01-tick-protocol-spec.md:470` 定义 FDB commit 失败时 Bevy World snapshot/restore 对称性。|
| B4 | CLOSED | `specs/01-tick-protocol-spec.md:181`-`specs/01-tick-protocol-spec.md:200` 明确 WASM tick 与 MCP query 读取同一份 COLLECT 快照且不能观察 EXECUTE 中间态；`specs/05-unified-visibility-policy.md:124`-`specs/05-unified-visibility-policy.md:138` 定义 spectator/player_view 与 drone snapshot 分离、WASM 始终按 `is_visible_to`、public_spectate 延迟约束；`specs/05-unified-visibility-policy.md:140`-`specs/05-unified-visibility-policy.md:154` 限制旁观者不能看到资源、env、代码、调试、指令和策略指标。|
| B5 | CLOSED | `specs/09-command-source-model.md:15`-`specs/09-command-source-model.md:33` 定义 WASM、MCP_Deploy、MCP_Query、RuleMod、Simulate 等 source 的 auth_context/gameplay/audit/rate/visibility/budget；`specs/09-command-source-model.md:36`-`specs/09-command-source-model.md:53` 定义来源能力矩阵与统一 validate_and_apply 管线；`specs/02-command-validation-spec.md:99`-`specs/02-command-validation-spec.md:127` 定义 CommandIntent 禁止携带身份字段、source/身份/tick 服务端注入与 source ordering。|
| B6 | CLOSED | `specs/02-command-validation-spec.md:270` 定义 `SpawningGrace { remaining: 1 }`，本 tick 免疫所有伤害含特殊攻击和衰减；`specs/02-command-validation-spec.md:286`-`specs/02-command-validation-spec.md:307` 定义 Hack 控制锁、Neutral、自动恢复和免疫再次 Hack；`specs/02-command-validation-spec.md:333`-`specs/02-command-validation-spec.md:362` 定义 Overload 下限、可见性约束、全局冷却、静默 no-op 和恢复；`specs/05-unified-visibility-policy.md:220`-`specs/05-unified-visibility-policy.md:261` 闭合特殊攻击 oracle/可观察性。|
| D-1 | CLOSED | `specs/07-world-rules-engine.md:385` 明确 Rhai inprocess 是唯一生产运行模式且所有模组必须签名；`specs/07-world-rules-engine.md:393`-`specs/07-world-rules-engine.md:441` 定义 `.rhai`/`mod.toml` Ed25519 签名、trusted_keys 验证、缺签拒绝和无未签名宽松模式。|
| D-2 | CLOSED | `design/DESIGN.md:2330`-`design/DESIGN.md:2349` 将 World 定义为持久世界，与 Arena 并列；`design/DESIGN.md:2347` 明确 World 无胜利条件、类似 MMO 持续沙盒、玩家自行设定目标且不存在游戏结束状态。|
| D-3 | CLOSED | `design/DESIGN.md:393` 和 `specs/02-command-validation-spec.md:270` 均明确新生 drone 获得 `SpawningGrace { remaining: 1 }`，本 tick 免疫所有伤害、特殊攻击和衰减，下一 tick 正常参与。|
| D-4 | GAP | `design/DESIGN.md:404`-`design/DESIGN.md:407` 和 `design/tech-choices.md:227`-`design/tech-choices.md:252` 只给出 Tier 2/3 快照扩展方向与“必须补充完整 spec”的要求；尚未在 specs/01-09 中形成可实现的 Tier 2/3 增量差异协议、CoW 页大小、分片键、跨分片引用、分布式 combat/FDB 多区域合同。|

## GAP

D-4 的缺口在于“必须 spec-ready”尚未闭合为正式 spec；现有文字仍是技术路线和待决策清单。建议新增或扩展 `specs/01-tick-protocol-spec.md` 的 snapshot scaling 小节，至少冻结 Tier 2 增量差异格式、CoW/page 或 modification-set 选择、truncation 排序语义，以及 Tier 3 分片键/跨分片实体引用/跨分片 combat 结算边界。修正后 D-4 可转为 CLOSED。