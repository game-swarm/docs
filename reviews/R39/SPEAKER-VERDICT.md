# R39 SPEAKER-VERDICT

角色：R39 Speaker  
输入：10 份 reviewer 报告（5 GPT + 5 DSv4）  
输出：共识分析、CrossCheck、表决统计、全体 verdict、D-items

## 0. Speaker 总结

**最终 Verdict：REQUEST_CHANGES**

R39 的总体设计方向在架构、安全、经济、API/DX、确定性/性能五个方向均被认可；但 10 份报告中没有任何一票无条件通过，且多项问题被跨 reviewer、跨模型独立命中。按 Speaker 规则：**同一问题被 2+ reviewer 独立命中即提升为 Blocker**。本轮至少存在 13 个共识 Blocker，覆盖 replay-critical 持久化、Phase 2b manifest、Deploy 签名边界、未认证 CSR 防护、经济账本公式、API schema drift 与确定性执行顺序。

结论：R39 **不应直接冻结为实现合同**。建议先完成本文列出的 Blocker 与 D-items 裁决，再做窄范围 Closure Verification。

## 1. 表决统计

| Reviewer | 方向 | 模型 | 表决归类 | 原报告结论 |
|---|---|---:|---|---|
| R39-CV-ARCH-GPT | Architecture | GPT | RequestChanges | 不建议直接进入实现冻结；存在 4 个阻断级问题 |
| R39-CV-ARCH-DSV4 | Architecture | DSv4 | Conditional | Conditional Pass；需修 Blocker/High 后冻结 |
| R39-CV-SEC-GPT | Security | GPT | RequestChanges | 不建议直接冻结；至少修 B1/B2/H1/H2 |
| R39-CV-SEC-DSV4 | Security | DSv4 | RequestChanges | REQUEST_CHANGES |
| R39-CV-DE-GPT | Design/Economy | GPT | Conditional | 有条件通过；合入前修 P0/P1 |
| R39-CV-DE-DSV4 | Design/Economy | DSv4 | RequestChanges | REQUEST_CHANGES |
| R39-CV-API-GPT | API/DX | GPT | RequestChanges | 多个 P0/P1 drift，不能直接作为实现依据 |
| R39-CV-API-DSV4 | API/DX | DSv4 | RequestChanges | REQUEST_CHANGES |
| R39-CV-DP-GPT | Determinism/Performance | GPT | RequestChanges | 不建议直接冻结为实现合同 |
| R39-CV-DP-DSV4 | Determinism/Performance | DSv4 | RequestChanges | REQUEST_CHANGES |

统计：

- **Approve**：0
- **Conditional / Conditional Pass**：2
- **RequestChanges**：8

## 2. 每份 reviewer finding 汇总

### 2.1 R39-CV-ARCH-GPT

**P0 / Blocker**

1. ECS Manifest “31 systems” 与实际清单不一致：A01、S22a、S22b 是否计入 manifest/hash 不清，导致 CI 与 replay verifier 分叉。
2. S22 Leech 写 `PendingDamage` 但 S15 已执行：status damage 可能丢失、跨 tick 或破坏唯一 HP writer。
3. Spawn “validate only / 不入队” 与 `PendingSpawn` 合同冲突：S08 需要 S06 写入 pending spawn。
4. TickCommitRecord FDB 同事务与 WAL fallback 语义冲突：replay-critical 审计不可降级为本地 WAL 成功路径。

**High / Medium / Low**

- TickCommitRecord 10 字段与扩展 envelope 权威边界不清。
- `05-persistence-contract.md` replay 流程仍依赖对象存储 blob，弱化“对象存储非 replay-critical”。
- Shadow Write 与旧 “直接 UPDATE persistent rows” 表述不一致。
- COLLECT snapshot 与 execution rollback snapshot 概念混用。
- Manifest 版本表仍残留 R35 旧 action/status intent 路径。

### 2.2 R39-CV-ARCH-DSV4

**Blocker**

1. TickCommitRecord 与 RichTraceBlob replay-critical 边界自相矛盾：FDB 10 字段、对象存储 rich trace、`audit_gap`/`unreplayable` 语义未唯一化。

**High**

1. Shadow Write 模型与旧 FDB commit 序列并存，生产提交路径不唯一。
2. 性能预算硬合同、SLO、benchmark gate 数值冲突，CI gate 不可执行。
3. Cross-room intent 在 staging 后裁决，可能与已 content-addressed room payload 不一致。

**Medium**

- COLLECT snapshot clone/restore benchmark 500 vs 50k entities 口径冲突。
- Seed “不可预测”表述容易被误读为安全性质。
- TickCommitRecord 字段清单跨文档不一致，需字段矩阵。

**Low**

- 文档引用路径错误或不稳定。
- 示例测试伪代码变量与断言语义有瑕疵。

### 2.3 R39-CV-SEC-GPT

**Blocker**

1. CSR admission control 在同一文档内自相矛盾：§5.2 多层限流 vs §10.8 “PoW 自身限速 / 无额外 IP 限制”。
2. DeployPayload 把服务端计算的 `compiled_artifact_hash` 放入客户端签名载荷，破坏代码签名与 artifact hash 权威边界。

**High**

1. WebSocket 握手 canonical payload 在 auth 与 MCP spec 中不一致，短 payload 未绑定 transport/server/world/audience。
2. WASM sandbox seccomp 对 `clone/vfork` 允许/禁止语义冲突。
3. Browser endpoint 的 certificate signature 与 token 兼容路径工具级边界不清。

**Medium**

- Auth Service 架构仍出现 “Engine 内或独立服务” 歧义。
- Admin reset API 参数缺少枚举型 `recovery_reason`。
- 联邦 CRL fallback 枚举残留旧默认与旧值。

### 2.4 R39-CV-SEC-DSV4

**Blocker**

1. `DeployPayload` 签名字段包含 `compiled_artifact_hash`，与“服务端计算 / 客户端不得自报”矛盾。

**High**

1. CSR 提交限流合同冲突，可能退化为仅 PoW 防护。
2. Agent endpoint 与 HTTP 安全表的 Origin 规则可能互相覆盖，破坏 Browser/Agent transport 分离。
3. seccomp `clone` 允许项与 “fork/vfork 禁止” 表述不精确。

**Medium**

- Deploy hash 命名残留 `module_hash`，与 `wasm_module_hash` / `compiled_artifact_hash` 分层不一致。
- Gateway/Engine 证书验证缓存职责略模糊。
- Spectator WebSocket audience 在无证书场景下应降级为 endpoint label。

**Low**

- `swarm_list_modules` 旧变更记录像状态追踪。
- `03-mcp-security.md` 出现字面 `\n\n` 残留。

### 2.5 R39-CV-DE-GPT

**P0**

1. 存储税数值与 Resource Ledger 权威 tiered 公式不一致。
2. 新玩家转移锁语义冲突：gameplay 只禁发送，ledger 定义双向禁发送/接收。
3. Resource Ledger 执行顺序文字与列表冲突：`WorldStartupSubsidy` vs `UpkeepDeduction` 第一步。

**P1 / High**

1. PvE Merchant / trade event 与 Resource Ledger out-of-scope 冲突。
2. PvE drop 绑定缺少账本级 `bound/unbound` 或 taint 约束。
3. 联盟转移防滥用不完整：退盟/中转/rolling cap/in-transit 状态未定义。
4. PvE faucet 预算方向正确但竞争分配、Zone 口径、Resource Boom 基线不清。

**P2 / Medium**

- 经济曲线依赖代码效率乘数，应标为设计假设而非协议保证。
- 维护费只按 rooms 计算，drone 规模约束不清。
- Tutorial/Novice/Standard repair cap 默认值需统一。

### 2.6 R39-CV-DE-DSV4

**Blocker**

1. Controller repair/age 维护模型存在三套互斥权威：免费物理吞吐、全局/比例 cap、按 body_cost 收费公式。

**High**

1. StorageTax tiered 公式以百分比作为 taxable，示例却按资源单位计算，单位会导致数量级错误。
2. Merchant NPC 在 modes 中作为当前 World PvE 内容出现，但 Resource Ledger 明确 Out-of-Scope。
3. Arena PvE 评分公式使用浮点/小数语义，与全局定点合同不一致。

**Medium**

- Balance Sheet “权威公式见 Resource Ledger”与自身收入假设不可完全重算。
- Tutorial → Standard 资产隔离缺失。
- PvE budget 与 World 事件奖励边界仍偏概念化。

**Low**

- `gameplay.md` Markdown 强调未闭合。
- Economy Balance Sheet 引用 Resource Ledger §6 的位置过期。

### 2.7 R39-CV-API-GPT

**P0**

1. Registry 与 IDL 版本/计数不一致：`game_api`、`auth_api`、`economy` 版本漂移。
2. MCP 工具总数存在三套口径：declared、active、RFC/feature-gated 未机器化定义。
3. RejectionReason Registry 与 Auth IDL code→name 绑定不一致，wire compatibility 风险高。

**P1 / High**

1. CommandAction 示例字段与 Registry schema 漂移：缺 `object_id`，`structure` vs `structure_type`。
2. Error envelope 基本一致，但派生页引入未注册错误码。
3. Host function 返回语义内部冲突：`ret >= 0 = bytes_written` vs `0=success`。
4. Codegen 文档输入输出章节映射过期。

**P2 / Low**

- `mcp-tools.md` 标题版本、Registry changelog 当前口径与历史记录容易误导。

### 2.8 R39-CV-API-DSV4

**High**

1. `commands.md` CommandAction 示例与 Registry schema 不一致：缺 `object_id`，Build 字段名错误。
2. `commands.md` Global Storage 费用/延迟说明与 Registry / Resource Ledger 经济权威冲突。
3. `design/interface.md` 工具计数仍写 57 game + 11 auth，Registry 已为 57 game + 12 auth。

**Medium**

- `design/interface.md` 保留旧 token/auth 工具迁移说明，暗示不存在的 `swarm_auth_refresh`。
- `design/interface.md` SDK 错误名使用非 canonical RejectionReason。
- `mcp-tools.md` 标题仍同步自 Registry 0.4.0。

**Low**

- `codegen.md` Auth 输出映射章节号漂移。

### 2.9 R39-CV-DP-GPT

**P0**

1. HP writer contract 中 S22 → `PendingDamage` 与 S15 顺序矛盾。
2. TickCommitRecord same-transaction 合同与 WAL 降级语义冲突。

**P1 / High**

1. Shadow write manifest-only 与 “state/tick/N 同事务写世界状态” 表述冲突。
2. RNG / shuffle seed 公式存在多处不一致表述。
3. Snapshot 构建时点在 snapshot-contract 与 tick-protocol 中表述不一致。

**P2 / Medium/Low**

- Snapshot truncation schema 字段名不一致。
- Snapshot critical entity 内部降级排序缺少完整定义。

### 2.10 R39-CV-DP-DSV4

**High**

1. Phase 2a/A01 调度语义仍有“双系统顺序”歧义：per-command dispatch loop vs S01→A01 批阶段。
2. TickCommitRecord 写失败语义自相矛盾。

**Medium**

- system 数量与编号残留不一致：31 systems、A01、S22a/S22b、6+25 口径不统一。
- `design/engine.md` 保留 `IndexMap` 作为确定性依据，可能被误解为充分条件。

**Low**

- FDB 故障注入测试示例断言变量/语义错误。

## 3. 共识分析：2+ reviewer 命中即 Blocker

### C-BLOCKER-01：TickCommitRecord / RichTraceBlob / WAL / FDB replay-critical 边界不唯一

**命中 reviewer**：ARCH-GPT、ARCH-DSV4、DP-GPT、DP-DSV4  
**升级原因**：跨方向（Architecture + DP）、跨模型（GPT + DSv4）重复命中。

问题集合：

- TickCommitRecord replay-critical subset 应与世界状态同一 FDB 事务提交。
- `01-tick-protocol.md` 中 WAL fallback “不阻塞 tick 执行”与同事务 abandon 语义冲突。
- `05-persistence-contract.md`/相关段落仍混淆 FDB 10 字段、RichTraceBlob、对象存储 replay 流程。
- `audit_gap`、`unreplayable`、rich debug unavailable 的 terminal state 边界未唯一化。

**Speaker 判定**：Blocker。必须统一为：FDB replay-critical 写失败 = transaction fail = tick abandon/retry；WAL 不得作为 committed tick 的 replay-critical 替代源。

### C-BLOCKER-02：S22 status / Leech `PendingDamage` 与 S15 damage_application 顺序矛盾

**命中 reviewer**：ARCH-GPT、DP-GPT  
**升级原因**：独立命中，且影响 replay deterministic HP writer。

**Speaker 判定**：Blocker。必须二选一：

- S22 不写 `PendingDamage`，所有 HP 变化 buffer 在 S15 前完成；或
- 新增/改写后置 status damage writer，并更新唯一 writer 合同与 manifest hash。

### C-BLOCKER-03：ECS manifest system count / A01 / S22a/S22b 口径不一致

**命中 reviewer**：ARCH-GPT、DP-DSV4  
**升级原因**：manifest hash、CI 注册、replay verifier 根合同被重复命中。

**Speaker 判定**：Blocker。必须明确 “31 systems + pseudo A01” 或 “32 manifest entries”，并同步 `system_id_N`、6+25 口径、R/W matrix 与 hash 输入。

### C-BLOCKER-04：Phase 2a A01 dispatch 语义与 per-command canonical queue 可能分叉

**命中 reviewer**：ARCH-GPT（manifest/A01 计数与 S01 关系）、DP-DSV4（A01 双系统顺序歧义）、API-GPT（Action dispatch schema 与 registry 方向）  
**升级原因**：跨 Architecture/DP/API 触及 Action dispatch 合同。

**Speaker 判定**：Blocker。Phase 2a 应写成 `for cmd in sorted(global_queue): dispatch(cmd.kind)`；A01 是 per-command handler 还是 system 必须最终裁决。

### C-BLOCKER-05：Shadow Write / GlobalTickCommit 与旧直接更新世界状态表述并存

**命中 reviewer**：ARCH-GPT、ARCH-DSV4、DP-GPT  
**升级原因**：跨架构与确定性重复命中。

**Speaker 判定**：Blocker。生产路径必须唯一：staging payload + manifest-only publish；旧 `UPDATE entity/resource/controller rows` 或 `state/tick/N` 直接世界状态写入只能作为 dev/test profile 或删除。

### C-BLOCKER-06：DeployPayload 中 `compiled_artifact_hash` 的签名边界错误

**命中 reviewer**：SEC-GPT、SEC-DSV4  
**升级原因**：安全双模型独立命中，同一 root cause。

**Speaker 判定**：Blocker。客户端签名 payload 只能覆盖 `wasm_module_hash`、metadata、身份、slot/version/audience 等提交前可知字段；`compiled_artifact_hash` 是服务端派生 manifest/cache 字段。

### C-BLOCKER-07：CSR admission control / 未认证端点限流冲突

**命中 reviewer**：SEC-GPT、SEC-DSV4  
**升级原因**：安全双模型独立命中。

**Speaker 判定**：Blocker。必须以多层 admission control 为唯一权威；删除 “PoW 自身限速 / 无额外 IP 限制” 或改为引用 §5.2/§10.7。

### C-BLOCKER-08：seccomp `clone` / `vfork` policy 不精确

**命中 reviewer**：SEC-GPT、SEC-DSV4  
**升级原因**：安全双模型独立命中。

**Speaker 判定**：Blocker。必须给出精确 clone flags matrix；默认禁止 `CLONE_VFORK`，除非提供 Wasmtime 版本证据与 BPF mask。

### C-BLOCKER-09：StorageTax 公式、单位与 Balance Sheet 数值不可重算

**命中 reviewer**：DE-GPT、DE-DSV4  
**升级原因**：经济双模型独立命中。

**Speaker 判定**：Blocker。Resource Ledger 公式必须以资源单位计税；Balance Sheet 每个数值必须可由 `capacity_units` + `stored_total` 重算，或明确降级为示意。

### C-BLOCKER-10：Merchant 当前范围与 Resource Ledger Out-of-Scope 冲突

**命中 reviewer**：DE-GPT、DE-DSV4  
**升级原因**：经济双模型独立命中。

**Speaker 判定**：Blocker。Merchant 必须二选一：R39 out-of-scope 并从当前 World PvE 可交互经济内容移除/标 RFC；或纳入 Ledger `MerchantTrade`。

### C-BLOCKER-11：CommandAction 示例与 Registry/IDL schema 漂移

**命中 reviewer**：API-GPT、API-DSV4  
**升级原因**：API 双模型独立命中。

**Speaker 判定**：Blocker。所有示例必须补 `object_id`，Build 改 `structure_type`，Spawn 明确 actor `object_id` 与 target `spawn_id`。

### C-BLOCKER-12：API Registry / IDL / derived docs 单事实源漂移

**命中 reviewer**：API-GPT、API-DSV4  
**升级原因**：版本、工具计数、auth tools、mcp-tools 标题、codegen 映射均被重复命中。

**Speaker 判定**：Blocker。必须重新确立 IDL 为机器权威，并用 generator/check 更新 Registry、mcp-tools、interface、codegen；不得手工维持多套计数。

### C-BLOCKER-13：Non-canonical / unregistered RejectionReason 出现在派生文档

**命中 reviewer**：API-GPT、API-DSV4  
**升级原因**：API 双模型独立命中。

**Speaker 判定**：Blocker。wire `error.data.rejection_reason` 只能使用 IDL/Registry canonical enum；其它 SDK 本地分类必须明确非 wire。

## 4. 非共识但高风险项（Speaker Watchlist）

这些问题未达到 2+ reviewer 独立同根命中，或只在单方向内出现，但仍建议在 Blocker 修复时一并处理。

1. **Controller/Depot repair/age 经济模型三套权威**：DE-DSV4 评为 Blocker；DE-GPT 也触及 repair cap 默认与 drone upkeep，但未同根表述。建议列入 D-item。
2. **Cross-room intent staging 后裁决一致性**：ARCH-DSV4 High。需 DP/Architecture 复查 state_checksum 与 room payload 合成规则。
3. **Performance hard deadline / SLO / benchmark gate 分层**：ARCH-DSV4 High，DP 间接涉及 snapshot benchmark。需工程 profile 裁决。
4. **RNG / shuffle seed 公式漂移**：DP-GPT P1。若未修会影响 replay golden fixture。
5. **Snapshot 构建时点与 truncation schema 漂移**：DP-GPT P1/P2，DP-DSV4认为部分已收敛但仍需查当前文本。
6. **Browser/Agent endpoint Origin/auth mode 分离**：SEC-DSV4 High，SEC-GPT H3 相关。需 API Registry per-tool auth mode 配合。
7. **WebSocket handshake canonical payload 不一致**：SEC-GPT High。建议以 `SWARM-WS-HANDSHAKE-V1` 为唯一格式。
8. **PvE bound drop / Tutorial asset isolation / Resource Boom cap 基线**：DE 两份均分别指出相关缺口，但根因分散。建议进入经济 closure checklist。
9. **Arena PvE score 使用浮点**：DE-DSV4 High。需 DP 确认 determinism contract 是否覆盖排行榜/score。
10. **Host function 返回语义冲突**：API-GPT P1。虽单独命中，但影响 ABI。

## 5. CrossCheck：方向专属发现需跨方向验证的补漏

### X1. Security ↔ API：per-tool auth mode 与 browser endpoint

SEC 报告要求 browser endpoint 对敏感工具仍需 application certificate signature；API Registry 当前需要增加或校验 per-tool auth mode：`web_session_ok`、`app_cert_required`、`admin_cert_required`。

需验证：

- `swarm_deploy`、证书吊销、恢复确认、admin、profile/security settings 是否全部标为 app/admin cert required。
- Browser HTTP 与 Agent/CLI HTTP 是否拆分 Origin/CSRF/audience 规则。
- `browser-http` audience 是否在 auth 与 MCP security 中同步。

### X2. Security ↔ Core WASM：Deploy 签名与 sandbox cache key

`compiled_artifact_hash` 移出客户端签名后，Core WASM sandbox 文档仍可用它作为 cache key，但必须明确其为服务端派生字段。

需验证：

- acceptance 验证永远绑定 `wasm_module_hash == Blake3(wasm_bytes)`。
- deploy manifest 同时记录 signed payload hash 与 compiled artifact hash。
- replay/audit 字段矩阵不把 compiled artifact 当作客户端权威输入。

### X3. Architecture ↔ DP：S15/S22 HP writer 与 manifest hash

调整 S22/S15 顺序或新增 status damage writer 会改变 manifest order、R/W matrix、hash fixture 与 HP writer conformance test。

需验证：

- `StatusState` unique writer 与 `HitPoints` unique writer 同时成立。
- Leech/status damage 生效 tick 被 golden fixture 固化。
- buffer tick-end clear 规则不丢失 damage。

### X4. Architecture ↔ Persistence/DP：Shadow Write 与 replay terminal state

统一 Shadow Write 后，需要同时更新 persistence contract、tick protocol、fault injection tests。

需验证：

- GlobalTickCommit 只发布 committed manifest/head/hash-chain。
- staging payload 在 publish 前不可见，publish 失败可 GC。
- TickCommitRecord 10 字段与 manifest pointer 同事务提交。

### X5. Design/Economy ↔ API：commands.md 手写经济数值

API-DSV4 指出 `commands.md` 手写 Global Storage fee/delay；DE 报告指出 Ledger 是经济唯一权威。

需验证：

- 派生 API docs 不重复写经济参数，除非从 Ledger/IDL 生成。
- AlliedTransfer、GlobalDeposit/Withdraw、bound drop、transfer lock 在 API schema 与 Ledger 操作一致。

### X6. Design/Economy ↔ DP：Arena PvE score 浮点与 deterministic replay

DE-DSV4 指出 score 公式使用浮点；DP 合同禁止 replay-critical 浮点。

需验证：

- Arena score、leaderboard、match_result 是否 replay-critical。
- 若是，改为 fixed-point integer；若仅 UI 展示，明确 canonical stored score 为整数。

### X7. API ↔ Codegen：IDL 权威与 generated docs check

API 两份均指出 derived docs 漂移。

需验证：

- `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 的版本、tool count、RejectionReason 均由 generator 输出。
- `hermes codegen generate --check` 与实际脚本/输出路径一致。
- Registry、mcp-tools、interface 不再手写当前计数。

### X8. Architecture ↔ Design/Economy：Spawn pending 与 resource deduction/refund

ARCH-GPT 指出 Spawn “只校验不入队”与 PendingSpawn 冲突；DE 报告涉及 SpawnCost、BuildCost、PvE bound resources 的账本属性。

需验证：

- S06 validate + reserve/deduct + enqueue `PendingSpawn`。
- S08 创建实体，same-tick 可见性边界明确。
- SpawnCost 对 bound/unbound 资源的消费、失败 refund 与 TickTrace 归因一致。

## 6. D-items：需要最终裁决的二选一议题

### D1. A01 是 manifest system 还是 command-loop handler？

- **选项 A**：A01 是独立 manifest entry，进入 system count/hash/RW matrix；全局改为 32 entries。
- **选项 B**：A01 是 Phase 2a per-command dispatcher handler，不计入 ECS system count/hash；manifest 保持 31 systems。
- **Speaker 建议**：选 B。Phase 2a 本质是 sorted command loop，A01 作为 handler 更能避免 “S01 批处理后 A01 批处理” 歧义。

### D2. S22 status damage 如何进入 HP writer？

- **选项 A**：禁止 S22 写 `PendingDamage`；所有 status damage buffer 在 S15 前产出，由 S15 同 tick 统一结算。
- **选项 B**：新增/改写后置 status damage writer，S15 不再是全部 HP 变化唯一 writer。
- **Speaker 建议**：选 A。保留单一 HP writer 最利于 conformance test 与 replay verifier。

### D3. TickCommitRecord WAL 是否可作为 committed tick 成功路径？

- **选项 A**：不可。FDB same-tx replay-critical 写失败即 tick abandon/retry；WAL 仅 debug/forensics。
- **选项 B**：可。但必须引入全局复制/共识化 WAL，并重写 terminal_state/replay authority。
- **Speaker 建议**：选 A。B 会推翻当前 FDB 单一权威源设计。

### D4. RichTraceBlob / Object Store 缺失是否可导致 deterministic `unreplayable`？

- **选项 A**：不可。对象存储缺失只产生 `audit_gap` / `rich_debug_unavailable`。
- **选项 B**：可。则 RichTraceBlob 含 replay-critical 字段，必须纳入权威提交路径。
- **Speaker 建议**：选 A。FDB TickCommitRecord 10 字段为 deterministic replay minimum。

### D5. Shadow Write 生产提交路径是什么？

- **选项 A**：生产统一为 per-room staging payload + GlobalTickCommit manifest-only publish。
- **选项 B**：生产允许直接在 commit txn 更新 entity/resource/controller rows。
- **Speaker 建议**：选 A。B 只能作为 dev/test small profile，且必须明确不适用于 production。

### D6. Cross-room intent 裁决在 staging 前还是 staging 后？

- **选项 A**：先在 Bevy World 内裁决并应用跨房间状态，再对 affected rooms 写最终 staging payload。
- **选项 B**：先 staging base payload，再由 GlobalTickCommit manifest overlay 合成最终状态。
- **Speaker 建议**：选 A。实现和 replay 简单，避免 overlay 读取路径复杂化。

### D7. `compiled_artifact_hash` 是否属于客户端 Deploy 签名 payload？

- **选项 A**：不属于；客户端签名 `wasm_module_hash` 与 metadata/identity/audience，服务端编译后生成 artifact hash。
- **选项 B**：属于；客户端必须提供或预知 compiled artifact hash。
- **Speaker 建议**：选 A。B 不可实现且破坏 cache/auth 边界。

### D8. CSR 未认证端点是否允许“PoW 自身限速 / 无额外 IP 限制”？

- **选项 A**：不允许；PoW 只是成本门槛，仍强制 per-IP/per-ASN/semaphore/queue/audit throttle。
- **选项 B**：允许，仅 PoW 防护。
- **Speaker 建议**：选 A。

### D9. Wasmtime seccomp 是否允许 `CLONE_VFORK`？

- **选项 A**：默认禁止 `CLONE_VFORK`，只允许精确线程 clone flags。
- **选项 B**：允许 `CLONE_VFORK`，但提供版本证据、BPF mask 与 CI matrix。
- **Speaker 建议**：选 A，除非实现团队提供硬证据。

### D10. Merchant 是否属于 R39 当前经济范围？

- **选项 A**：Out-of-Scope / RFC-MERCHANT，当前 World PvE 不提供可交互交易经济。
- **选项 B**：In-Scope，新增 Ledger `MerchantTrade`、预算、费率、TickTrace、transfer lock 交互。
- **Speaker 建议**：选 A。先保住 Ledger 单一入口与 R39 收敛范围。

### D11. Controller/Depot age repair 经济模型采用哪一个？

- **选项 A**：Controller 免费但受 `repair_range`、`repair_capacity`、实体位置/队列限制；Depot repair 消耗本地资源。
- **选项 B**：全局 `repair_cap` / `repair_cost` / `distance_decay_bp` 作为 Ledger 权威公式。
- **Speaker 建议**：选 A，并删除或降级 B 为可选 mod/历史残留。

### D12. StorageTax Balance Sheet 数值是权威还是示意？

- **选项 A**：权威可重算；每行给出 `storage_capacity`、`stored_total`、tier formula。
- **选项 B**：示意目标曲线；不可作为实现/CI 数值。
- **Speaker 建议**：优先选 A；若短期无法重算，则明确选 B 并禁止实现按表硬编码。

### D13. API tool count 统计口径是什么？

- **选项 A**：`all_declared`、`active_only`、`rfc/feature_gated` 三套机器化口径并列，文档引用具体口径。
- **选项 B**：只保留一个总数，手工解释 RFC 是否计入。
- **Speaker 建议**：选 A。

### D14. Non-canonical SDK error names 是否可出现在 wire `RejectionReason` 文档中？

- **选项 A**：不可；wire 只允许 IDL canonical enum，SDK 本地分类必须另名并标非 wire。
- **选项 B**：可作为非规范示例混写。
- **Speaker 建议**：选 A。

### D15. Arena PvE score 使用 fixed-point 还是浮点？

- **选项 A**：canonical score 使用整数/定点，UI 可显示浮点。
- **选项 B**：核心评分公式使用浮点。
- **Speaker 建议**：选 A。

## 7. 建议修复顺序

1. **Replay / persistence 根合同**：TickCommitRecord same-tx、RichTraceBlob/Object Store、WAL 降级、Shadow Write production path。
2. **Manifest / deterministic execution**：A01 口径、system count/hash、S22/S15 HP writer、R/W matrix、RNG/snapshot 残留。
3. **Security 边界**：DeployPayload hash 分层、CSR admission control、seccomp clone policy、Browser/Agent auth mode。
4. **Economy Ledger**：StorageTax 单位与表格、Merchant scope、repair/age 模型、new player/bound drop/transfer lock。
5. **API/DX 单事实源**：IDL/Registry/tool count/RejectionReason、commands examples、non-canonical errors、codegen mapping。
6. **Closure Verification fixtures**：manifest hash fixture、HP writer fixture、TickCommitRecord failure injection、shadow write fault injection、IDL/docs generator `--check`。

## 8. 最终裁决

**REQUEST_CHANGES**

R39 不建议合入为冻结实现合同。理由：

- 0/10 reviewer 给出无条件 Approve。
- 8/10 表决归类为 RequestChanges。
- 至少 13 个问题达到“2+ reviewer 独立命中”的 Speaker Blocker 标准。
- Blocker 覆盖 replay-critical 持久化、manifest hash、security trust boundary、resource ledger、API wire schema，均属于实现后返工成本高的根合同。

建议修复本文 Blocker 与 D-items 后，开展一轮窄范围 CV：Architecture + Security + DE + API + DP 各自只验证修复项与 generated/check fixtures，不再扩展新范围。

## 9. D-items 最终裁决

| D | 议题 | 裁决 | 关键理由 |
|:--:|------|:--:|------|
| D1 | A01 身份 | **B** — per-command handler（31 system） | 消除 C-BLOCKER-04 根因——A01 作为 "system" 引入语义分裂（"S01 批处理后 A01 批处理"），作为 handler 消除歧义 |
| D2 | S22 HP writer | **A** — 禁写 PendingDamage | 单一 HP writer 是确定性合同基石；多 writer 需定义顺序/冲突解决→引入不可判定性 |
| D3 | WAL committed 路径 | **A** — 不可 | FDB 单源权威是 persistence 唯一正确架构；双源引入冲突裁决无解 |
| D4 | RichTraceBlob unreplayable | **A** — 不可 | RichTraceBlob 非 replay-critical；提升为 critical 将对象存储变为可用性依赖 |
| D5 | Shadow Write 生产路径 | **A** — staging→publish | 两阶段提交是唯一保证 manifest hash 覆盖全部变更的方式 |
| D6 | Cross-room 裁决时机 | **A** — staging 前 | 先裁决后写入=合同面最小；先写后 overlay=合并算法即合同（扩大合同面） |
| D7 | compiled_artifact_hash | **A** — 不属于 | 逻辑不可实现——客户端无法签名服务端编译产物 |
| D8 | CSR PoW 单层 | **A** — 不允许 | 纵深防御是安全基本原则；单层 PoW 违反 defense-in-depth + 文档内部矛盾 |
| D9 | seccomp CLONE_VFORK | **A** — 禁止 | WASM 不需要 vfork；开放增加攻击面无功能收益→违反最小权限 |
| D10 | Merchant 范围 | **A** — Out-of-Scope | Merchant 设计未完成，纳入 Ledger 引入未定义操作→不完整 spec 比 out-of-scope 更损害一致性 |
| D11 | Repair 模型 | **A** — 物理约束 | 与 R35 已收敛 Economy 方向一致；B 引入新定价公式→多权威冲突 |
| D12 | StorageTax BS | **A** — 权威可重算 | C-BLOCKER-09 彻底闭合；示意曲线留下"公式有值无"的后门 |
| D13 | Tool count 口径 | **A** — 三口径并列 | 消除计数漂移根因；单一口径手工维护已被 R35/R39 两轮证明不可靠 |
| D14 | SDK error 混写 | **A** — 不可 | Wire contract 必须单一权威枚举；混写→wire compatibility 破坏 |
| D15 | Arena score 类型 | **A** — 定点整数 | Canonical score 必须跨平台确定；浮点 IEEE 754 跨实现有微小差异 |

**统计**：14/15 与 Speaker 建议一致。D1 裁决从 Speaker 的 A→B，其余均采纳 Speaker 推荐。

**执行顺序**（纳入 §7）：
1. Blocker 修复按 §7 原序
2. D1 (A01 handler) 优先 — 影响 §7 第 2 组 Manifest 修复
3. D7 (Deploy hash) 优先 — 影响 §7 第 3 组 Security
4. D10 + D12 优先 — 影响 §7 第 4 组 Economy
5. 其余 D-items 随各组 Blocker 修复一并处理