# R36 CV Standard — Closure Verification

**Reviewer**: Closure Verification Reviewer (GPT/Standard)  
**Scope**: `/tmp/swarm-review-R36/design/` + `/tmp/swarm-review-R36/specs/` Markdown 全量验证  
**Date**: 2026-06-26  
**Verdict**: REQUEST_CHANGES

## 1. 验证范围与方法

- 发现 Markdown 文件 **34 个**，而任务说明称 33 个；实际包含 `design/README.md`，已纳入检查。
- 执行全量关键字扫描：`TODO|FIXME|XXX|HACK` 无实际标记命中（Action 名称 `Hack` 不计入）。
- 执行 Markdown cross-file link 检查：发现 3 个断链候选。
- 针对 R35 fix wave 的 D/B/High/ML 方向做重点一致性扫描：JSON-RPC error envelope、`host_get_random`、ActionRegistry/CommandAction、Deploy 同步、CSR email、Energy-only、Alliance、经济/资源/调度权威源等。
- 结论：R35 fix wave **未闭合完整**，主要阻塞集中在 ActionRegistry/CommandAction 残留、RejectionReason 计数残留、链接断裂和 stale playtest/路径叙事。

## 2. 阻塞问题

### R36-CV-S1 — `CommandAction` 仍有旧 21/特殊攻击模型残留

**严重级别**: Blocker  
**涉及 R35 项**: D3 Action 通用化 / B consensus blockers / Direction High API 一致性  
**涉及文件**:

- `/tmp/swarm-review-R36/design/interface.md:115`
- `/tmp/swarm-review-R36/specs/gameplay/08-api-idl.md:141`
- `/tmp/swarm-review-R36/specs/gameplay/08-api-idl.md:179`
- `/tmp/swarm-review-R36/specs/gameplay/08-api-idl.md:314`
- `/tmp/swarm-review-R36/specs/gameplay/08-api-idl.md:318`

**发现**:

- `design/interface.md:115` 仍声明“所有 21 个 CommandAction 变体（11 core + 2 economy_operation + 8 special_attack）”，与 R35 D3 后的 canonical 模型冲突。Registry 明确为 **11 个 CommandAction + Action dispatch**，combat/effect action 全部进入 `ActionRegistry`。
- `specs/gameplay/08-api-idl.md:141-154` 仍把 `Attack`、`RangedAttack`、`Heal` 放在顶层 `actions:` 中，表现为独立命令定义，而非 `CommandAction::Action { type, payload }` dispatch。
- `specs/gameplay/08-api-idl.md:179-219` 仍把 `Hack/Drain/Overload/Debilitate/Disrupt/Fortify` 作为“特殊攻击”顶层 action 列表，而非引用 `special-attack-table.md` 的 11 vanilla ActionRegistry 表。
- `specs/gameplay/08-api-idl.md:314-349` 仍声明“所有特殊攻击通过 `[[custom_actions]]` + `[[special_effects]]` 可配置注册”，并列出 `CommandAction` 变体表，与 R35 D3 的“vanilla action（3 basic combat + 8 special）在 ActionRegistry 中 immutable/built-in，mod 额外 action 才通过 registry 扩展”冲突。

**影响**:

- D3 未闭合：同一概念在 Registry / manifest / command-validation 与 interface / API-IDL 中存在双模型。
- 代码生成、SDK schema、MCP schema 的输入源语义不稳定：读者无法判断 `Attack` 是 CommandAction variant、custom action 还是 ActionRegistry vanilla action。

**建议修复**:

- 将 `design/interface.md` 的 21 变体表述改为 11 CommandAction + Action dispatch，并统一“11 vanilla ActionRegistry action”。
- 重写 `specs/gameplay/08-api-idl.md` §2/§5：顶层 CommandAction 仅保留非战斗基础操作 + `Action` dispatch；combat/effect 参数只引用 `special-attack-table.md` 与 `api-registry.md`。
- 删除或改写 `[[custom_actions]]` 作为 vanilla 特殊攻击注册方式的旧叙事，仅保留 mod extension 用法。

---

### R36-CV-S2 — `Leech/Fabricate` 注册方式仍标为 `[[custom_actions]]`

**严重级别**: Blocker  
**涉及 R35 项**: D3 Action 通用化 / Leech-Fabricate vanilla 化  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:716`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:810`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:824`

**发现**:

- 同一文件 `02-command-validation.md:716` 已声明“Leech/Fabricate 的注册方式已从 `[[custom_actions]]` 改为 ActionRegistry vanilla action”。
- 但 `02-command-validation.md:810` 和 `02-command-validation.md:824` 又分别在 Leech/Fabricate 属性表中写“注册方式 | `[[custom_actions]]`”。

**影响**:

- 文件内部自相矛盾，且与 `special-attack-table.md` 的 canonical 11 vanilla action 表冲突。
- D3 fix wave 存在明确残留。

**建议修复**:

- 将 Leech/Fabricate 属性表注册方式改为 `ActionRegistry vanilla action`，或删除该非权威字段，统一引用 `special-attack-table.md`。

---

### R36-CV-S3 — RejectionReason canonical code 计数 47/48 混用

**严重级别**: High  
**涉及 R35 项**: D1 JSON-RPC envelope / D2 canonical error / B consensus consistency  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/reference/api-registry.md:90`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:156`
- `/tmp/swarm-review-R36/specs/gameplay/08-api-idl.md:68`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:154`
- `/tmp/swarm-review-R36/specs/reference/commands.md:149`
- `/tmp/swarm-review-R36/specs/reference/commands.md:151`
- `/tmp/swarm-review-R36/design/interface.md:139`

**发现**:

- `api-registry.md:90` 声明 canonical code 总数为 **48**，并在 `api-registry.md:156` 加入 `NotEligible` 编号 48。
- 多个派生/设计文档仍声明 **47**：`08-api-idl.md:68`、`02-command-validation.md:154`、`commands.md:149-151`、`design/interface.md:139`。

**影响**:

- JSON-RPC envelope 本身已修复为 numeric `error.code` + `error.data.rejection_reason`，但 canonical enum 总数不一致会影响 SDK typed exception、文档生成和 CI 校验。
- D1/D2 的“错误语义单一事实源”未完全闭合。

**建议修复**:

- 以 `game_api.idl.yaml`/`api-registry.md` 的实际生成结果为准，统一所有文档的计数；若 `NotEligible` 是新增 canonical code，则全量更新为 48；若不是，则从 Registry/IDL 中移除。

---

### R36-CV-S4 — `host_get_random` 派生描述仍混用旧 seed 口径

**严重级别**: High  
**涉及 R35 项**: D2 `host_get_random u64` / sandbox + host-functions + interface 一致性  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/core/04-wasm-sandbox.md:221`
- `/tmp/swarm-review-R36/specs/core/04-wasm-sandbox.md:234`
- `/tmp/swarm-review-R36/specs/core/04-wasm-sandbox.md:237`
- `/tmp/swarm-review-R36/specs/core/04-wasm-sandbox.md:427`

**发现**:

- `04-wasm-sandbox.md:221` 的 signature 已是 `host_get_random(sequence: u64, out_ptr, out_len)`，且 `04-wasm-sandbox.md:234-237` 给出新的 length-delimited derive_rng 规范。
- 但 `04-wasm-sandbox.md:427` 的成本表仍写 `seed=(tick_seed, player_id, drone_id, sequence)`，与上方权威 derive_rng 输入 `world_seed, tick, actor_or_entity_id, sequence` / domain separator 描述不一致。

**影响**:

- D2 的 u64 sequence 和 RNG 域隔离修复仍有残留旧口径。
- 实现者可能错误使用 `tick_seed/player_id/drone_id` 旧模型，破坏 replay determinism 或跨调用隔离。

**建议修复**:

- 将成本表说明改为引用同文件 §3.2 / `host-functions.md` 的 canonical derive_rng，不再内联旧 seed tuple。

---

### R36-CV-S5 — cross-file links 存在断链

**严重级别**: High  
**涉及清单**: 链接完整性  
**涉及文件**:

- `/tmp/swarm-review-R36/design/README.md:19`
- `/tmp/swarm-review-R36/design/README.md:208`
- `/tmp/swarm-review-R36/design/auth.md:348`

**发现**:

脚本检测到以下断链：

- `design/README.md:19` → `../RUNBOOK.md` 不存在于 `/tmp/swarm-review-R36`。
- `design/README.md:208` → `../AGENTS.md` 不存在于 `/tmp/swarm-review-R36`。
- `design/auth.md:348` → `../reference/api-registry.md#32-game-api-工具清单-57` 从 `design/` 相对解析为 `/tmp/swarm-review-R36/reference/api-registry.md`，实际文件在 `/tmp/swarm-review-R36/specs/reference/api-registry.md`。

**影响**:

- 链接完整性要求未通过。
- `design/auth.md` 指向 API Registry 的关键引用不可点击/不可解析。

**建议修复**:

- 修正 `design/auth.md` 相对路径为 `../specs/reference/api-registry.md#...` 或使用仓库统一相对路径。
- 对 `RUNBOOK.md` / `AGENTS.md`：若不在审查包中，应改为明确外部/仓库根引用策略，或从审查包补齐文件。

---

### R36-CV-S6 — `PLAYTEST-GATED.md` 存在 stale 路径与已闭合缺口叙事

**严重级别**: Medium-High  
**涉及清单**: 无 stale MVP/Phase/roadmap 叙事 / 无残留矛盾  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:15`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:24`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:61`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:62`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:63`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:64`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:65`
- `/tmp/swarm-review-R36/specs/PLAYTEST-GATED.md:87`

**发现**:

- 文件仍引用不存在路径：`specs/gameplay/resource-ledger.md`、`specs/gameplay/economy-balance-sheet.md`；实际为 `specs/core/08-resource-ledger.md` 与 `design/economy-balance-sheet.md`。
- PG-2 仍写“Hack Neutral 窗口、Overload 多攻击者、Hack 成功率公式、Fabricate 目标结构、Leech/Debilitate 交互矩阵不完整”等“缺失”，但 R35/R33 后多个 canonical 文件已给出 ActionRegistry 表、特殊攻击参数、状态推进、Overload target cooldown、Fabricate/Leech 参数等定义。若这些仍是 playtest-gated，应明确区分“平衡性待验证”与“规范缺失”；当前文字仍呈现为设计缺口。

**影响**:

- stale roadmap/playtest 叙事会让 reviewer 误判 D/High 项未闭合。
- 路径错误也会造成断链/引用失效。

**建议修复**:

- 更新涉及文件路径。
- 将 PG-2 从“缺失”改为“已规范化，待 playtest 验证平衡性”，并逐项引用 `special-attack-table.md` / `02-command-validation.md` / `06-phase2b-system-manifest.md` 的权威定义。

---

## 3. 非阻塞但需同步的问题

### R36-CV-N1 — deploy 反馈模型存在 polling 与 SSE push 叙事不一致

**严重级别**: Medium  
**涉及 R35 项**: D4 Deploy 同步  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/gameplay/06-feedback-loop.md:140`
- `/tmp/swarm-review-R36/specs/gateway-protocol.md:123`

**发现**:

- `06-feedback-loop.md:140` 明确“不提供主动事件推送/MCP 事件订阅”，AI agent 使用 polling。
- `gateway-protocol.md:123` 的 MCP 代理职责仍写 “SSE 事件推送（deploy_accepted, first_tick_executed）”。

**影响**:

- D4 deploy feedback 的语义在 gameplay 与 gateway 之间不一致。若 SSE 仅是底层 transport/内部事件通道，应明确不作为 Agent-facing subscription；若面向 MCP，则 `06-feedback-loop.md` 需同步。

---

### R36-CV-N2 — `special_param: float` 与禁浮点原则冲突

**严重级别**: Medium  
**涉及文件**:

- `/tmp/swarm-review-R36/specs/core/07-world-rules.md:994`
- `/tmp/swarm-review-R36/specs/core/07-world-rules.md:1009`
- `/tmp/swarm-review-R36/specs/core/07-world-rules.md:1042`

**发现**:

- `07-world-rules.md` 的 custom action 示例仍使用 `special_param = 2.0` / `0.5`，字段说明为 `float`。
- 其他设计多处要求禁用 `f64` / 使用 fixed-point integer（例如 `design/gameplay.md` 的数值确定性原则）。

**影响**:

- 可能引入确定性回归风险。

**建议修复**:

- 将 `special_param` 改为 fixed-point / basis points / typed integer 参数，或声明该段为旧示例并替换。

---

## 4. 已通过检查项

- **TODO/FIXME/XXX/HACK**：未发现实际标记；`Hack` action name 命中不计入。
- **JSON-RPC envelope 主体方向**：`api-registry.md`、`mcp-tools.md`、`design/interface.md` 均已采用 numeric `error.code = -32000` + `error.data.rejection_reason` 的标准 JSON-RPC 2.0 error object；但仍受 S3 计数不一致影响。
- **Energy-only 方向**：重点扫描未发现新的 `InsufficientEnergy` 作为 canonical wire enum 残留；多数资源消耗已以 `Energy` resource 表达。
- **CSR no email 方向**：CSR/证书流程重点扫描未发现要求 CSR 必含 email 的残留；email 主要作为绑定/恢复能力出现。
- **Alliance 10 / AlliedTransfer**：Registry 与 Resource Ledger 中的联盟转账语义基本一致；未发现明显 “Alliance 10” 残留矛盾。

## 5. Verdict

**REQUEST_CHANGES**

R35 fix wave 未达到“全量闭合 + 无回归 + 无残留”的标准。至少以下问题必须修复后再进入下一轮 CV：

1. 统一 `CommandAction` / `ActionRegistry` 模型，删除 21 变体、顶层 combat action、vanilla special `[[custom_actions]]` 残留。
2. 修复 Leech/Fabricate 注册方式的文件内矛盾。
3. 统一 RejectionReason canonical code 计数 47/48。
4. 修复 `host_get_random` seed/derive_rng 旧口径残留。
5. 修复 3 个 cross-file 断链。
6. 更新 `PLAYTEST-GATED.md` 的 stale 路径与“规范缺失”叙事。
