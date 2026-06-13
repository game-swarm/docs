# Swarm 设计评审 — Round 2 共识报告

## 总体 Verdict

REQUEST_CHANGES

9 份 Round 2 评审中，2 份为 CONDITIONAL_APPROVE（rev-dsv4-designer, rev-claude-designer），7 份为 REQUEST_CHANGES / REQUEST_MAJOR_CHANGES。议会共同判断：方向正确，P0 规范化进展明显，但 Game API IDL、Command Source Model、确定性合同、MCP/手动控制边界、WASM 编译/运行预算、World Rules Engine 与关键游戏循环仍未冻结，不能直接进入 Phase 2 大规模实现。

本轮不是否定项目方向，而是要求先完成 Architecture Freeze / Design Hardening。尤其是：

1. Game API IDL 必须成为 host functions、commands、validators、SDK、MCP schema 的单一真相来源。
2. Command Source Model 必须冻结：默认 gameplay commands 是否只能来自 WASM，MCP/manual_control/tutorial/admin/debug 分别属于什么权限域。
3. Determinism Contract 必须冻结：PRNG、排序、HashMap/ECS query 顺序、f64/整数模型、TickTrace、FDB commit timing、replay schema 都要可验证。
4. MCP 与 WASM 边界必须闭合：不能一边宣称 MCP 不做游戏动作/唯一执行器是 WASM，一边允许 RawCommand 或 manual_control 绕过同一校验路径。
5. Designer 方向认为技术骨架已经更清晰，但 World 目标、新手保护、经济 sink、战斗数值、Arena meta 与首小时体验仍未闭环。

## 方向分组与交叉结论

### Architect 组

评审员：rev-claude-architect, rev-gpt-architect, rev-dsv4-architect

AGREEMENT：
- 架构方向正确，P0 规范已比 R1 更接近可执行，但仍缺少冻结级别的核心合同。
- Game API IDL 必须统一。host ABI、Command enum、validator、SDK、MCP schema、Replay/TickTrace 不能多处手写、各自演化。
- Determinism 仍被实现细节侵蚀：f64、HashMap/std::hash、ECS query 顺序、seeded shuffle、PRNG 未指定、移动冲突、tick abandon、FDB commit timing 等都需要明确。
- World Rules Engine 不能是任意 ECS plugin；必须是 deterministic capability model，并且要贯穿校验层、组件层、host ABI 与规则配置。
- Persistence/tick contract 需要收敛：FDB commit 到底在 EXECUTE 还是 BROADCAST、每 tick 事务大小、cache/FDB 双状态恢复、cross-shard tick sync 都不能留到实现时猜。
- Phase 2 前需要先做原型验证：50K commands/500ms EXECUTE 可行性、sandbox process pool vs fork/kill、FDB transaction sizing。

DISAGREEMENT：
- 进度阻断程度不同：rev-gpt-architect 和 rev-claude-architect 明确 REQUEST_CHANGES；rev-dsv4-architect 对算法方向更接近 APPROVE_WITH_RESERVATIONS，但仍列出 Phase 2 blockers。
- Command 来源是否应严格“默认只来自 WASM”：rev-gpt-architect 强烈建议统一 gameplay commands only from WASM；其他 Architect 更关注 Raw/Validated/Applied/Replayed 语义和 deterministic validation，不一定完全排除 tutorial/admin/manual path，但都要求不能绕过同一校验和审计路径。
- FDB 策略焦点不同：rev-gpt-architect 反对“全世界每 tick 一个大 FDB transaction”的隐含假设；rev-dsv4-architect 关注 FDB commit timing、10MB transaction limit 与恢复校验；rev-claude-architect 关注规则引擎与 gateway 背压等架构闭合。

COMPLEMENTARY：
- rev-claude-architect 补充：World Rules Engine 未贯穿、safe_mode 字段悬空、移动目标冲突未定义、gateway 背压未处理。
- rev-gpt-architect 补充：Game API IDL 单一真相、Command Source Model、TickTrace Schema、Phase 0 Architecture Freeze、manual_control 哲学冲突、Replay 术语分层。
- rev-dsv4-architect 补充：FDB commit timing contradiction、fork/kill 成本、50K commands 性能、seeded shuffle bias、world_seed 泄漏、cross-shard sync、PRNG/Blake3 固定算法。

### Security 组

评审员：rev-claude-security, rev-gpt-security, rev-dsv4-security

AGREEMENT：
- 当前最大安全问题是承诺与规范细节互相打架：MCP 不做游戏动作 vs RawCommand from MCP；唯一执行器 WASM vs manual_control 跳过 WASM；prompt injection 只靠字符集 vs 文本字段进入 AI 上下文。
- Command Source Model/Auth Context 必须是 Phase 2 blocker。任何 RawCommand 都必须携带不可伪造的 server-side actor/session/capability context，player_id 不得由客户端自报。
- MCP 是高危远程控制面，需要 Host/Origin/CORS/CSRF/DNS rebinding/SSE 防护、token binding、scope、rate limit、审计、private/default bind。
- WASM 上传、验证、编译和运行都是攻击面。不只是 runtime fuel，compile-time DoS、module validation、host function compute budget、process isolation/process pool、panic containment 都必须定义。
- Prompt injection taint model 必须扩展到所有玩家可控文本字段，不能只靠字符集或少数字段 sanitize。
- 可见性/调试/回放/explain 是统一信息边界，必须与 Command validation、snapshot、replay、logs、AI prompts 使用同一 policy。
- 经济/数值错误也可能是安全问题：溢出/下溢、资源硬编码、M5/M6 类经济漏洞会导致作弊或状态污染。

DISAGREEMENT：
- 安全组内部没有实质方向分歧，差异主要是侧重点：rev-claude-security 关注规范自相矛盾和 prompt/source model 破口；rev-gpt-security 关注 threat model、MCP HTTP/SSE 与边界闭合；rev-dsv4-security 关注实现级阻断、host budget、auth context 注入和 taint model 覆盖。
- 对 manual_control 的处理强度可能需要用户裁决：删除、仅 Tutorial、本地 dev-only，还是保留但作为 admin/debug capability。安全组一致要求它不得伪装成普通 gameplay path。

COMPLEMENTARY：
- rev-claude-security 补充：C1 注入模型破口、C2 信任模型破口、API 正确性、player_id 强制、编译 DoS、可见性不变量、经济/数值下溢。
- rev-gpt-security 补充：MCP/RawCommand/手动控制之间的文档冲突、WASM 编译 DoS、DNS rebinding/Host/Origin/CSRF、debug/replay/explain 信息边界。
- rev-dsv4-security 补充：动作入口边界不闭合、RawCommand auth context 注入、MCP 实现级防护契约、WASM host function cost model、所有文本字段 taint propagation。

### Game Designer 组

评审员：rev-claude-designer, rev-dsv4-designer, rev-gpt-designer

AGREEMENT：
- 技术方向与“可编程 MMO / AI 玩家”愿景有吸引力，但核心游戏设计尚未闭环。
- 玩家首小时旅程不清晰：为什么继续玩、如何学习、失败如何理解、目标如何递进，仍需要具体设计。
- World 模式需要目标结构和新手保护/社交缓冲，否则先发优势、雪球效应与弱者体验会破坏长期生态。
- 资源经济需要更强战略张力与 sink；内存/CPU/fuel/资源失败不能变成惩罚性复杂度或浪费外溢。
- Arena 模式需要 meta 演变、观赏性和 league/season 设计，否则容易退化成一次性求解或静态最优策略。
- 战斗数值模型仍缺关键决策，应尽早提供求解器/模拟器/可解释工具，而不是把可玩性留给后期 polish。

DISAGREEMENT：
- 结论强度不同：rev-claude-designer 与 rev-dsv4-designer 给 CONDITIONAL_APPROVE，更像“可继续但需补设计”；rev-gpt-designer 给 REQUEST_MAJOR_CHANGES，认为核心游戏设计尚未闭环，不能只靠技术规范推进。
- World Rules Engine 是否应引入 seasonal modifier：rev-dsv4-designer 明确建议作为官方运行 policy；其他 Designer 未反对，但更关注目标结构、新手保护、经济 sink、战斗数值与首小时体验。

COMPLEMENTARY：
- rev-claude-designer 补充：World 目标结构、新手保护、战斗数值模型、经济 sink；提出战斗求解器、人机协作 league、RejectionReason 游戏化成就系统。
- rev-dsv4-designer 补充：资源竞争先到先得的浪费外溢、World 雪球缺乏制衡、Arena 一次性博弈均衡退化、seasonal modifier。
- rev-gpt-designer 补充：首小时 retention、资源经济战略张力、内存经济复杂度、World 社交缓冲、Arena 观赏性与 meta 层。

## 共识发现

### C1: Round 2 方向正确，但必须先冻结核心合同再进入 Phase 2

来源：rev-claude-architect ✓, rev-gpt-architect ✓, rev-dsv4-architect ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓, rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：9/9 认可 Swarm 的总体方向没有跑偏：P0 规范、ECS/tick/WASM/MCP/AI player/world/arene 方向都值得继续。但共同结论是，Phase 2 前必须先冻结 Game API IDL、Command Source Model、Determinism Contract、Visibility/Replay/TickTrace、World Rules Engine capability model 与基础游戏循环。当前总体 verdict 为 REQUEST_CHANGES。

### C2: Game API IDL 必须成为单一真相来源

来源：rev-gpt-architect ✓, rev-claude-architect ✓, rev-dsv4-architect ✓, rev-dsv4-security ✓, rev-gpt-security ✓

内容：host functions、RawCommand/ValidatedCommand、validators、SDK ABI、MCP schema、Replay/TickTrace、docs/examples 不应各自定义。否则会产生 validator bypass、SDK 与 runtime 不一致、MCP schema 漂移、Replay 无法验证等问题。需要一个可生成代码和测试的 IDL/spec，作为 Phase 0/Phase 1 的冻结工件。

### C3: Command Source Model 是跨架构与安全的最高优先级阻断项

来源：rev-gpt-architect ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓, rev-claude-architect ✓

内容：文档同时出现“指令只来自 WASM / MCP 不做游戏动作 / manual_control 跳过 WASM / RawCommand 来自 MCP”等互相冲突的表述。必须定义所有 command 来源：WASM gameplay、MCP plan/query、manual/tutorial、admin/debug、replay/import、test harness。每个来源都要有 server-side auth context、capability、scope、audit、rate limit，并统一进入 RawCommand -> ValidatedCommand -> Applied/Rejected 流程。

### C4: 确定性合同必须覆盖 PRNG、排序、数值、ECS、持久化和 replay

来源：rev-claude-architect ✓, rev-gpt-architect ✓, rev-dsv4-architect ✓, rev-gpt-security ✓

内容：当前 determinism 仍被多处细节侵蚀：f64、HashMap/std::hash、ECS query 顺序、seeded shuffle bias、PRNG 未指定、移动目标冲突、world_seed 泄漏、tick abandonment、FDB commit timing、TickTrace schema 混淆。必须定义固定算法（如 ChaCha12/Blake3 或等价选择）、稳定排序键、整数/定点数模型、ECS schedule/order、replay command lifecycle、checksum 与恢复校验。

### C5: MCP/WASM/Manual 控制边界必须闭合，不能存在平行执行器

来源：rev-gpt-security ✓, rev-claude-security ✓, rev-dsv4-security ✓, rev-gpt-architect ✓

内容：MCP 可用于 AI UX、计划验证、状态查询和辅助解释，但不能默默成为绕过 WASM/validator 的第二套 gameplay executor。manual_control 若保留，必须明确是 Tutorial/dev/admin capability，并接受同一 validation/audit/visibility/rate-limit contract。否则“代码就是军队”的核心哲学、安全模型与 replay determinism 都会被破坏。

### C6: World Rules Engine 必须从插件愿景收敛为 deterministic capability model

来源：rev-claude-architect ✓, rev-gpt-architect ✓, rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：World Rules Engine 既是架构扩展点，也是游戏体验和经济平衡工具。不能允许任意 ECS plugin 直接修改规则。应定义 deterministic capability、允许的规则参数、seasonal modifier/官方运行 policy、资源/战斗/新手保护/经济 sink 如何进入 validator 与 host ABI。

### C7: WASM 安全不只在 runtime；上传、验证、编译和 host functions 都是攻击面

来源：rev-dsv4-security ✓, rev-gpt-security ✓, rev-claude-security ✓, rev-dsv4-architect ✓

内容：Round 2 安全组一致要求补齐 WASM compile-time DoS、module validation、host function compute cost、fuel/memory/output budget、process pool vs fork/kill、sandbox worker、panic containment、supply-chain/audit。尤其是 host function budget 不能只写“燃料”，每个 API call 的成本和 response bounds 都要定义。

### C8: Visibility/Debug/Replay/Explain 必须共享同一信息边界

来源：rev-gpt-security ✓, rev-claude-security ✓, rev-dsv4-security ✓, rev-gpt-architect ✓, rev-dsv4-architect ✓, rev-gpt-designer ✓

内容：debug、replay、explain、TickTrace、AI prompt、ClickHouse logs、MCP state queries 都可能泄漏 hidden state、world_seed、策略、拒绝原因、private errors 或 prompt 内容。需要统一 data classification 和 view policy：raw trace admin-only；player-safe replay/explain 只暴露该玩家在 tick T 可知的信息；public replay 必须 redacted/delayed/post-match 并经过同一过滤模型。

### C9: 游戏设计闭环仍是 Phase 2 风险，不应视为后期 polish

来源：rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓, rev-gpt-architect ✓

内容：Designer 组一致认为，技术规范不能替代“为什么玩、如何成长、如何失败、如何竞争、如何观看”的设计闭环。首小时体验、World 目标结构、新手保护、资源经济、memory/CPU/fuel 成本、战斗数值、Arena meta、season/league/replay 都应形成 MVP Feedback Loop Spec。

### C10: Phase 规划需要重排为先冻结、再垂直切片、再加固扩展

来源：rev-gpt-architect ✓, rev-claude-architect ✓, rev-dsv4-architect ✓, rev-gpt-security ✓, rev-gpt-designer ✓

内容：当前 Phase 规划与 P0 状态不一致。建议先增加 Phase 0 Architecture Freeze，产出核心合同；Phase 1 做单人垂直切片并验证 gameplay loop；Phase 2 再做 sandbox/MCP/public multiplayer 加固。不要在核心 API/command/determinism 未冻结时并行展开 SDK、MCP action tools 和多人世界。

## 方向共识

### A1: Architect 共识 — Architecture Freeze 是 Phase 2 前置条件

来源：rev-claude-architect ✓, rev-gpt-architect ✓, rev-dsv4-architect ✓

内容：三位 Architect 均认为方向正确但关键合同未收敛。Phase 2 前必须冻结 Game API IDL、Command Source Model、Determinism Contract、TickTrace schema、Persistence commit timing、World Rules capability model、Failure Mode Table。

### A2: Architect 共识 — 确定性要从原则变成可测试实现约束

来源：rev-claude-architect ✓, rev-gpt-architect ✓, rev-dsv4-architect ✓

内容：必须消除 f64、HashMap/std::hash、ECS query 非确定顺序、PRNG 未指定、seeded shuffle bias、移动冲突、tick abandonment、FDB/Broadcast commit 矛盾等不确定来源。每个 tick 应可生成 checksum/TickTrace，并可用 sampling + checksum 做 CI 验证。

### A3: Architect 共识 — Persistence 与 scale 需要原型验证

来源：rev-gpt-architect ✓, rev-dsv4-architect ✓, rev-claude-architect ✓

内容：不能假设全世界每 tick 一个大 FDB transaction。需要定义每 room/shard/tick 的 commit boundary、FDB 10MB transaction limit 应对、EXECUTE vs BROADCAST commit timing、Dragonfly/Bevy/FDB 状态恢复校验、cross-shard tick sync、NATS gateway ack/recovery。

### A4: Architect 共识 — World Rules Engine 必须贯穿 validator/component/host ABI

来源：rev-claude-architect ✓, rev-gpt-architect ✓

内容：资源、战斗、移动、spawn、safe_mode、新手保护、seasonal modifiers 不能散落在硬编码系统里。规则引擎要成为 deterministic configuration/capability，且直接影响 Command validation、组件约束、host function 可用性与 replay。

### S1: Security 共识 — Command/Auth Context 不闭合是 Phase 2 blocker

来源：rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓

内容：RawCommand 入口必须不可伪造。所有 command 都应由服务器注入 actor/session/player/capability context，禁止客户端自报 player_id；manual/MCP/admin/tutorial/replay/test 来源必须显式建模并审计。

### S2: Security 共识 — MCP 需要实现级防护契约

来源：rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓

内容：MCP 默认 private bind，经 gateway 暴露；必须有 Host/Origin/CORS/CSRF/DNS rebinding/SSE 防护、audience-bound tokens、scope/tool binding、expiry/revocation、per-token/player/IP/global rate limit、bounded queue、audit log、negative tests。

### S3: Security 共识 — WASM compile/runtime 双阶段预算必须定义

来源：rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓

内容：WASM 上传、验证、编译、实例化、运行和 host calls 都有 DoS 风险。需要 module size/section/function/table/global/string limits、compile timeout/process isolation、cache policy、host function cost table、fuel/memory/output bounds、panic containment、malicious corpus。

### S4: Security 共识 — Prompt injection/taint model 必须覆盖所有文本字段

来源：rev-claude-security ✓, rev-gpt-security ✓, rev-dsv4-security ✓

内容：不能只靠字符集或少数字段 sanitize。所有 player-controlled text、names、logs、errors、replay annotations、chat、module metadata、RejectionReason 展示都应有 provenance/taint 标记、长度/字符/语义边界、AI prompt 模板隔离和 adversarial regression fixtures。

### S5: Security 共识 — 经济/数值错误属于安全边界

来源：rev-claude-security ✓, rev-dsv4-security ✓, rev-gpt-security ✓

内容：资源硬编码、下溢/溢出、body cost、spawn/repair/harvest 边界、refund、失败时 fuel/资源处理、tick abandon 都可能造成作弊和状态污染。需要在 Command Validation Spec 中以 invariant + property tests 固化。

### G1: Designer 共识 — 首小时体验和目标结构必须进入 MVP

来源：rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：玩家需要明确第一小时目标、反馈、失败解释、下一步成长路径。World 模式必须有目标层级、教程、新手保护、社交缓冲；不能只提供 engine 和 API。

### G2: Designer 共识 — World 模式需要反雪球和新手保护机制

来源：rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：World 不是公平竞技场，但仍需要长期生态健康。需要处理先发优势、资源垄断、弱者被锁死、新手出生/保护/迁移、seasonal modifiers 或官方 world policy。

### G3: Designer 共识 — 经济、战斗和资源竞争需要可解释数值模型

来源：rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：资源竞争的先到先得可能造成失败者 CPU/fuel 浪费；经济 sink 不足会导致目标枯竭；战斗数值未定会使策略空间不可评估。需要战斗求解器/模拟器、经济 sink、失败 refund/penalty policy、资源争用反馈。

### G4: Designer 共识 — Arena 需要 meta/观赏性/league 设计

来源：rev-claude-designer ✓, rev-dsv4-designer ✓, rev-gpt-designer ✓

内容：Arena 若只是一次性对称开局，容易快速收敛到静态最优策略。需要 season/ban/地图池/规则轮换/league、人机协作 league、spectator/replay、meta 演变机制。

## 未解决分歧

### D1: Gameplay commands 是否必须“默认只来自 WASM”？

立场 A（rev-gpt-architect, rev-gpt-security, rev-claude-security, rev-dsv4-security）：默认 gameplay commands 应只来自 WASM；MCP/manual_control 不能成为第二执行器。RawCommand from MCP 与 manual_control 会破坏“代码就是军队”、安全边界和 replay determinism。

立场 B（部分架构/设计需求隐含）：Tutorial、人类教学、admin/debug、AI-assisted UX 可能需要非 WASM 控制路径；Designer 方向希望降低首小时门槛并支持人机协作 league。

可能共识方案：默认生产 gameplay path 只允许 WASM-submitted commands；manual_control 仅 tutorial/dev/admin capability，强制同一 validation/audit/rate-limit/replay 标记；MCP action tools 不直接 apply，只能 submit plan/commands 到同一 validator 或仅查询/解释。

需要用户裁决：Phase 2 是否删除 manual_control，还是保留为 Tutorial/dev/admin-only capability？MCP 是否允许 submit gameplay commands，还是只做 query/plan/validate/explain？

### D2: World Rules Engine 是官方运行 policy，还是用户/服务器可扩展插件？

立场 A（rev-claude-architect, rev-gpt-architect）：规则引擎必须收敛为 deterministic capability model，避免任意 ECS plugin 破坏 determinism、validation 和 replay。

立场 B（rev-dsv4-designer, Designer 方向）：World 需要 seasonal modifiers、反雪球、新手保护、经济/战斗调参作为长期运营工具，不能过度冻结成不可演化规则。

可能共识方案：允许规则演化，但只通过版本化、可 replay、可 diff、可验证的 RuleConfig/Capability 集合；官方 seasonal modifier 是数据化规则，不是任意代码插件。

需要用户裁决：Swarm 是否支持第三方/自托管自定义 World Rules？如果支持，是数据化 RuleConfig 还是代码插件？官方 World 是否采用 seasonal modifier？

### D3: Arena 与 World 的优先级如何排序？

立场 A（Designer 方向）：World 目标结构、新手保护和长期生态是核心 MMO 体验，不能只做 Arena 技术验证。

立场 B（Architect/Security 隐含）：Arena/单人垂直切片更适合验证 deterministic tick、Command validation、WASM sandbox、replay 和性能，风险更可控。

可能共识方案：Phase 1 做单人/小规模 Arena-like 垂直切片验证核心合同；同时编写 World MVP Feedback Loop Spec。World public launch 延后到新手保护、经济 sink、seasonal policy 和社交缓冲冻结之后。

需要用户裁决：Phase 1 垂直切片的产品目标是 Arena prototype、World tutorial room，还是二者并行但范围极小？

### D4: WASM sandbox public test 是否必须进程池隔离？

立场 A（rev-gpt-security, rev-dsv4-security 倾向）：public/multitenant 场景不应在 engine 主进程直接编译/运行 untrusted WASM；至少需要 worker process/process pool、resource limits、no secrets/no network、compile-time isolation。

立场 B（实现进度考虑，rev-dsv4-architect 提出性能原型）：fork/kill per tick 成本巨大，process pool 需要先 prototype；本地/dev/single-player 可短期单进程 Wasmtime，但不能误认为生产安全。

可能共识方案：接口上从一开始抽象 SandboxWorker；本地 dev 可 feature-flag 单进程；任何 public test 前必须完成 process pool prototype 和 compile/runtime budget。

需要用户裁决：首个外部测试是否允许单进程 sandbox？还是必须等 process pool worker 完成？

### D5: 资源竞争失败是否 refund CPU/fuel/动作成本？

立场 A（rev-dsv4-designer）：先到先得导致失败者浪费 CPU fuel 无回报，是负外部性，会惩罚探索和弱势玩家。

立场 B（系统/安全隐含）：完全 refund 可能被滥用作免费探测、拥塞攻击或竞争压力规避；失败成本也是战略信息和反 spam 机制。

可能共识方案：区分 deterministic invalid、contention-lost、late/stale、blocked-by-visibility 等 RejectionReason；对可预期 invalid 不 refund，对同 tick 资源争用失败给部分 refund 或低成本失败；所有策略进入 Command Validation Spec。

需要用户裁决：资源争用失败的 fuel/CPU/resource refund policy 是 none、partial、还是按 RejectionReason 分类？

### D6: Replay/Explain 应偏产品可见性还是偏安全最小暴露？

立场 A（Designer 方向）：replay/explain/观战是学习、传播和 Arena meta 的关键，应尽早作为产品体验。

立场 B（Security 方向）：debug/replay/explain 会泄漏 hidden state、seed、策略、prompt、拒绝原因和 private errors，应默认最小暴露。

可能共识方案：raw trace admin-only；player explain 只显示 self-view + typed rejection；public replay 仅 delayed/redacted/post-match；Arena 可启用更开放的 spectator mode，但必须在赛前规则中声明。

需要用户裁决：MVP 是否支持 public replay？如果支持，哪些模式默认打开：self-only、opponent-view、delayed public、post-match omniscient？

## 行动建议

### P0 — Phase 2 前必须完成的阻断项

1. 产出并冻结 `Game API IDL Spec`
   - 覆盖 host functions、Command schema、validator inputs/outputs、SDK ABI、MCP schema、TickTrace/Replay command lifecycle、error/RejectionReason。
   - 要求从 IDL 生成 Rust/TS schema、validator tests、MCP tool schemas、docs examples。
   - 来源：rev-gpt-architect, rev-claude-architect, rev-dsv4-architect, rev-dsv4-security, rev-gpt-security

2. 产出并冻结 `Command Source Model`
   - 明确 WASM gameplay、MCP、manual_control、tutorial、admin/debug、replay/import、test harness 的来源、权限、auth context、capability、audit、rate limit、可见性和 replay 标记。
   - 决定 manual_control 删除、降级或 admin/tutorial-only。
   - 来源：rev-gpt-architect, rev-claude-security, rev-gpt-security, rev-dsv4-security

3. 产出并冻结 `Determinism Contract`
   - 指定 PRNG、hash、排序键、ECS schedule/query ordering、整数/定点数模型、禁止/限制 f64、movement conflict resolution、seed handling、tick abandonment、checksum。
   - 明确 RawSubmitted -> Validated -> Applied/Rejected -> TickTrace -> Replay 的生命周期。
   - 来源：rev-claude-architect, rev-gpt-architect, rev-dsv4-architect

4. 修正 Persistence/Tick contradictions
   - FDB commit timing 统一到 EXECUTE 或明确两阶段语义；不要同时写 EXECUTE 与 BROADCAST。
   - 定义 room/shard/tick transaction boundary、FDB 10MB transaction limit、recovery checksum、Dragonfly/Bevy/FDB 双状态校验、NATS gateway ack/recovery。
   - 来源：rev-dsv4-architect, rev-gpt-architect, rev-claude-architect

5. 编写 `MCP Security Contract v2`
   - private/default bind、gateway-only public entry、Host/Origin/CORS/CSRF/DNS rebinding/SSE、audience-bound tokens、scope/tool binding、expiry/revocation、rate limits、audit logs、negative tests。
   - 明确 MCP 是否能 submit gameplay commands，若能必须进入同一 validator。
   - 来源：rev-claude-security, rev-gpt-security, rev-dsv4-security

6. 编写 `WASM Upload/Compile/Runtime Budget Spec`
   - module size/section/function/table/global limits、compile timeout/isolation、process pool prototype、host function compute cost table、fuel/memory/output bounds、panic containment、malicious corpus。
   - 来源：rev-dsv4-security, rev-gpt-security, rev-claude-security, rev-dsv4-architect

7. 编写 `Unified Visibility + Replay/Explain Data Classification`
   - 定义 player P at tick T may know X；debug/replay/explain/AI prompt/logs/MCP/REST/WS 复用同一过滤器。
   - raw trace admin-only；player explain self-view；public replay delayed/redacted/post-match。
   - 来源：rev-gpt-security, rev-claude-security, rev-dsv4-security, rev-gpt-designer

8. 收敛 `World Rules Engine Capability Model`
   - 从任意 plugin 改为版本化 RuleConfig/Capability；贯穿 validator/component/host ABI/replay。
   - 覆盖 safe_mode、新手保护、seasonal modifier、资源/战斗/经济 sink。
   - 来源：rev-claude-architect, rev-gpt-architect, rev-claude-designer, rev-dsv4-designer, rev-gpt-designer

### P1 — Phase 1 垂直切片必须验证的工程风险

9. Prototype EXECUTE 性能
   - 用目标规模（例如 50K commands / 500ms）验证 serial/parallel execute、command ordering、validator cost、host function budgets。
   - 来源：rev-dsv4-architect

10. Prototype sandbox process pool
   - 比较 fork/kill per tick、long-lived worker pool、compile cache、crash recovery、module eviction、resource accounting。
   - 来源：rev-dsv4-architect, rev-gpt-security, rev-dsv4-security

11. Prototype FDB transaction sizing
   - 测试每 room/shard/tick 写入大小、10MB limit、versionstamp、conflict ranges、recovery checksum、cache invalidation。
   - 来源：rev-gpt-architect, rev-dsv4-architect

12. 建立 deterministic replay CI
   - full replay 太慢时使用 sampling + checksum；覆盖 PRNG、movement conflict、resource contention、tick abandon、recovery after crash。
   - 来源：rev-dsv4-architect, rev-gpt-architect

13. 建立 Command validation property tests
   - ownership、visibility、range、cooldown、resource、body cost、player_id injection、numeric overflow/underflow、refund policy、duplicate/late commands。
   - 来源：rev-claude-security, rev-dsv4-security, rev-gpt-security

14. 建立 prompt-injection/taint regression suite
   - 覆盖 names、logs、errors、module metadata、replay annotations、chat、RejectionReason、AI snapshots。
   - 来源：rev-claude-security, rev-dsv4-security

### P2 — MVP/产品设计闭环

15. 编写 `MVP Feedback Loop Spec`
   - 覆盖首小时目标、教程、starter bot、失败解释、RejectionReason、dry-run/validate_plan、local simulation、metrics dashboard。
   - 来源：rev-claude-designer, rev-gpt-designer

16. 编写 `World Onboarding + Anti-Snowball Spec`
   - 新手出生/保护/迁移、社交缓冲、先发优势衰减、seasonal modifiers、非竞技展示指标。
   - 来源：rev-claude-designer, rev-dsv4-designer, rev-gpt-designer

17. 编写 `Economy + Combat Model Spec`
   - 资源 sink、memory/CPU/fuel 成本、body/repair/spawn 数值、战斗求解器、资源争用失败/refund policy。
   - 来源：rev-claude-designer, rev-dsv4-designer, rev-gpt-designer, rev-claude-security

18. 编写 `Arena Meta + League Spec`
   - 地图池、规则轮换、season、league、人机协作 league、AI tournament、观战/replay、meta 演变机制。
   - 来源：rev-dsv4-designer, rev-gpt-designer, rev-claude-designer

19. 将 RejectionReason 产品化但保持安全边界
   - typed rejection codes、suggested fix、achievement/learning hooks、no hidden-state leakage、no untrusted text injection。
   - 来源：rev-claude-designer, rev-gpt-designer, rev-claude-security, rev-dsv4-security

## 最终建议

Round 2 的共同结论可以压缩为一句话：Swarm 已经有足够强的方向和技术野心，但还没有足够冻结的“可编程多人游戏宪法”。现在最危险的不是某个模块没写完，而是核心合同未冻结时直接进入 Phase 2，导致 SDK、MCP、WASM、validator、replay、World rules、游戏体验各自生长，后续很难重新收敛。

建议立即插入一个短周期 Design Hardening / Architecture Freeze Sprint，交付 8 个可审查工件：

1. Game API IDL Spec
2. Command Source Model
3. Determinism Contract
4. Persistence/Tick Commit Contract
5. MCP Security Contract v2
6. WASM Upload/Compile/Runtime Budget Spec
7. Unified Visibility + Replay/Explain Data Classification
8. World Rules Engine Capability Model + MVP Feedback Loop Spec

这 8 个工件冻结后，再进入 Phase 1 单人/小规模垂直切片，并用真实性能、安全和 replay 测试验证。只有当这些合同被代码和测试证明可执行后，才建议进入 Phase 2 MCP/public/multiplayer 扩展。
