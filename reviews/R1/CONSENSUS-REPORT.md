# Swarm 设计评审 — 共识报告

## 总体 Verdict

REQUEST_CHANGES

## 用户裁决（5 个分歧）

| ID | 问题 | 裁决 |
|----|------|------|
| D1 | MCP 工具设计 | **体验优先** — 丰富 UX verbs，内部单一 validation pipeline |
| D2 | WASM 进程隔离 | **进程隔离** — MVP 起 sandbox worker process + OS isolation |
| D3 | Replay 公开性 | **公开** — safe view（owner/opponent/delayed omniscient），非 raw traces |
| D4 | FoundationDB | **直接依赖** — FDB 是唯一真相来源，docker-compose 一键部署 |
| D5 | 排行榜与公平性 | **公平性仅 Arena 有意义** — World 模式无排行榜，Arena 分 league（Human/AI） |

## 评审共识

6/6 评审员均给出 REQUEST_CHANGES。共同结论不是"方向错误"，而是：Swarm 的核心方向被广泛认可（WASM 多语言、ECS 确定性、MCP-first AI 玩家、可回放模拟），但当前设计在 Phase 1/2 前缺少若干必须固化的基础契约。尤其是 tick 生命周期、命令验证、可见性/信息边界、MCP 授权、WASM 沙箱、AI 公平性与调试/新手反馈循环。

当前最重要的共同线程：

1. 不应在未定义 MCP 授权、限流、可见性和隔离模型前开放 Phase 2 MCP action tools。
2. 不应在未实现真实 Wasmtime 沙箱、资源配额和恶意模块测试前接受玩家 WASM。
3. 不应在未明确 tick collect/execute/broadcast 屏障、超时、失败隔离、排序与 Bevy ECS 调度顺序前进入多人逻辑。
4. 不应把 debug/replay/onboarding 当作后期 polish；它们分别是安全边界、可解释性和游戏可玩性的核心。

## 方向分组与交叉结论

### Architect 组

评审员：rev-claude-architect, rev-dsv4-architect

AGREEMENT：
- ECS 组件拆分方向正确，Position 与 Drone 等组件解耦，适合 Bevy 查询与并行化。
- 三阶段 tick 抽象（Collect -> Execute -> Broadcast）概念正确，但当前设计/代码没有足够机制保障它。
- Phase 1 skeleton 与 7 阶段目标之间差距很大；tick lifecycle、Bevy system ordering、PlayerExecutor/MCP 执行模型必须在 Phase 2 前定清。
- 持久化一致性、tick 原子性、失败处理不能再停留在“稍后实现”。

DISAGREEMENT：
- MCP 架构优先级：rev-claude-architect 强烈建议 Phase 3 前抽出独立 MCP service；rev-dsv4-architect 更集中于 tick/Bevy/算法正确性，没有直接反对 sidecar，但将 MCP 公平性和异步输入视为 tick 语义问题。
- FoundationDB：rev-claude-architect 关注 FoundationDB 对自托管和架构可移植性的耦合；rev-dsv4-architect 关注 FDB + Dragonfly 写入路径和 crash recovery 的一致性。两者焦点不同但不冲突。

COMPLEMENTARY：
- rev-claude-architect 补充了 PlayerExecutor 能力模型、Hybrid 玩家、async command queue、MCP 进程边界、WorldStore trait、跨 shard transfer。
- rev-dsv4-architect 补充了 Bevy system ordering、Command/Query 分离、TOCTOU 失败语义、路径/视野复杂度、AI 非确定性 replay 记录。

### Security 组

评审员：rev-dsv4-security, rev-claude-security, rev-gpt-security

AGREEMENT：
- MCP 是远程游戏命令接口，必须先定义认证、授权、scope、token 生命周期、撤销、CORS/SSE、限流和审计。
- AI-visible game state 是 prompt injection 通道；“sanitize strings”不足以解决语义注入，必须使用 typed JSON、untrusted provenance、长度/字符限制、AI SDK 模板和回归测试。
- WASM 沙箱目前只是设计愿景；缺少 wasmtime 依赖、明确 WASI allowlist、fuel/memory/output/depth limits、恶意 WASM corpus 和 runtime CVE 策略。
- 可见性/fog-of-war 必须成为统一策略，REST/WS/gRPC/MCP/debug/replay 不能各自实现过滤，否则必然出现信息泄漏。
- debug/replay/trace 是敏感数据，可能泄漏策略、隐藏状态、rejected commands、prompt/model data 或 tokens；必须默认 self-only/admin-only/redacted。
- rate limiting、command validator invariants、JSON/parser bounds、pathfinding/query helper budget 都必须提前定义。

DISAGREEMENT：
- WASM 隔离强度：rev-claude-security 和 rev-dsv4-security 主要要求 Wasmtime 配置和测试具体化；rev-gpt-security 进一步要求 untrusted WASM 在独立 worker process + OS isolation（seccomp/cgroup/no network/read-only FS）中运行。分歧点是 MVP 是否必须进程隔离，还是先在 engine 内配置 Wasmtime。安全组整体倾向至少要把进程隔离作为生产目标和设计边界。
- MCP tool 形态：rev-dsv4-security 建议减少工具面，甚至用单一 `swarm_submit_commands` 降低攻击面；Game Designer（跨方向）希望 player-facing verbs 更易用。安全组内部主要强调最小攻击面，不直接处理 UX。

COMPLEMENTARY：
- rev-dsv4-security 给出具体 host-side DoS：PathFind 未限界、GetObjectsInRange range 泄漏、Spawn body Vec 无界、serde_json depth、i32 overflow、GameError unbounded strings。
- rev-claude-security 补充 auth spec、prompt injection contract、debug/replay scope、session TTL、AI registration throttling、secret management。
- rev-gpt-security 补充 threat-model 级别要求：private/default MCP bind、capability checks per tool、strict Origin/CORS/SSE、shared visibility policy、supply chain/SBOM、incident response、data classification。

### Game Designer 组

评审员：rev-gpt-designer

AGREEMENT：
- 单人方向，无组内交叉一致性。但它与其他组在若干主题上形成跨方向共识：MCP 是 AI 玩家核心界面；deterministic replay/debug 对可解释性关键；公平性不能只靠 equal command limits；fog-of-war/information policy 必须明确；onboarding/debug/replay 不能后移到很晚。

DISAGREEMENT：
- 与 Security 在 MCP tool design 上存在张力：Game Designer 倾向更丰富、语义清晰的 player-facing tools（如 `swarm_move_unit`, `swarm_get_available_actions`, `swarm_validate_plan`, `swarm_explain_last_tick`）；Security 倾向减少工具数量或统一 submit path 以降低攻击面。
- 与 Security 在 replay 公开性上存在张力：Game Designer 希望 public replay URLs、clips、observer/tournament UX 尽早成为社区传播核心；Security 要求 debug/replay 默认 self-only/admin-only/redacted，避免策略和隐藏状态泄漏。

COMPLEMENTARY：
- Designer 补充了其他方向较少覆盖的可玩性缺口：AI first-hour tutorial、MCP capability manifest、starter bots、local simulation/test harness、dry-run API、explainable rejection、strategy metrics、league separation、progression depth、spectator story。

## 共识发现

### C1: 核心方向正确，但必须 REQUEST_CHANGES 后再推进

来源：rev-claude-architect ✓, rev-dsv4-architect ✓, rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-gpt-designer ✓

内容：所有评审员都认可 Swarm 的方向：ECS + deterministic tick + WASM sandbox + MCP-first AI players 有潜力。但 6/6 都认为当前设计缺少 Phase 2 前必须明确或实现的安全/一致性/体验基础，因此总体 verdict 为 REQUEST_CHANGES。

### C2: MCP 是关键玩家接口，也是最高优先级攻击面

来源：rev-claude-architect ✓, rev-dsv4-architect ✓, rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-gpt-designer ✓

内容：MCP 不是旁路 API，而是 AI 玩家的主控制面。Architect 关注嵌入 engine 的耦合和异步执行；Security 关注远程命令、authz、rate limit、prompt injection、visibility；Designer 关注 MCP 工具/文档是否构成可玩的 AI UX。共同结论：Phase 2 MCP action tools 必须以明确的 auth、scope、限流、可见性、工具契约、审计和 UX contract 为前置条件。

### C3: Tick 生命周期必须从注释变成可执行的确定性协议

来源：rev-claude-architect ✓, rev-dsv4-architect ✓, rev-dsv4-security ✓, rev-gpt-security ✓

内容：Collect -> Execute -> Broadcast 是正确抽象，但当前 `app.update()` 单 pass 与 Bevy Update 模型不够。必须定义：per-player timeout、fail-open/zero commands、late MCP command queue/rejection、collect/execute barrier、tick atomicity、command ordering key、idempotency/sequence、replay metadata，以及 Bevy system ordering。否则 multiplayer determinism 和 replay 都不可信。

### C4: WASM sandbox 不能只停留在 DESIGN 文本

来源：rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-claude-architect ✓, rev-dsv4-architect ✓

内容：WASM 安全模型被广泛认可，但当前缺少 wasmtime 集成、明确 WASI allowlist、fuel mode、memory/output/table/stack limits、host function budget、start/_initialize 禁止、pool zeroing、malicious module tests、dependency audit/CVE response。安全组认为这是 Phase 1/2 blocker。

### C5: 可见性/fog-of-war 是统一信息边界，不是 UI 细节

来源：rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-gpt-designer ✓, rev-dsv4-architect ✓

内容：Snapshot、GetObjectsInRange、MCP inspect、REST room API、WebSocket deltas、debug traces、replay、ClickHouse logs 都可能泄漏隐藏信息。必须定义一套共享 policy：“player P at tick T may know X”，并让所有输出 surface 复用同一 filtered view model。

### C6: Query/helper APIs 也是资源消耗和公平性边界

来源：rev-dsv4-security ✓, rev-gpt-security ✓, rev-claude-security ✓, rev-dsv4-architect ✓, rev-gpt-designer ✓

内容：PathFind、GetObjectsInRange、inspect、docs/helper tools 不是无害读操作。它们可能造成 host-side DoS、越权信息访问、AI/MCP 相对 WASM 的能力不对称。必须有坐标/范围上限、response size cap、per-player-per-tick query budget、fuel/compute accounting、visibility filtering，以及 WASM/MCP 等价能力说明。

### C7: Debug/replay 是核心功能，但默认必须安全、可解释、可裁剪

来源：rev-claude-security ✓, rev-gpt-security ✓, rev-gpt-designer ✓, rev-dsv4-architect ✓, rev-claude-architect ✓

内容：所有相关评审都认为 replay/debug 很重要，但原因不同：Architecture 需要 trace 支撑 multi-player 调试；Security 要防策略和隐藏状态泄漏；Designer 要把 replay 变成“可调试的故事”。共识：提前设计，但 raw traces admin-only，player replay redacted/self-scoped，错误和 tick 过程要解释清楚。

### C8: AI vs WASM 公平性不能只写“同样 command limit”

来源：rev-dsv4-architect ✓, rev-gpt-security ✓, rev-gpt-designer ✓, rev-claude-security ✓

内容：MCP AI 玩家有外部模型、私有记忆、网络延迟和可能无限计算；WASM 玩家受 fuel 限制。只限制输出 command 数量不能保证公平。需要定义 competitive classes/league separation、latency deadline、tool/query budgets、model/provider disclosure、accepted command ordering，以及哪些信息/工具对所有玩家等价。

### C9: Phase ordering 需要前移安全、调试、onboarding 的基础部分

来源：rev-claude-architect ✓, rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓, rev-gpt-designer ✓

内容：多名评审认为当前路线把一些基础内容放太晚：安全 hardening、authz、visibility、rate limiting、tick traces、state inspection、onboarding/tutorial、starter templates、dry-run/validation。它们不是 Phase 7 polish，而是 Phase 1/2 的可行性前提。

## 方向共识

### A1: Architect 共识 — ECS 和三阶段 tick 方向正确，但调度/原子性/失败语义必须设计化

来源：rev-claude-architect ✓, rev-dsv4-architect ✓

内容：两位 Architect 都认可 ECS decomposition 与 Collect/Execute/Broadcast 概念，但共同要求在 Phase 2 前解决 tick partial failure、Bevy system ordering、command injection timing、deterministic order、tick atomicity、async executor late commands。建议形成一份 `Tick Protocol Spec`。

### A2: Architect 共识 — PlayerExecutor/MCP 异步模型不完整

来源：rev-claude-architect ✓, rev-dsv4-architect ✓

内容：MCP/AI 与 WASM executor 的执行时序、错误恢复、late response、Hybrid player、公平 replay 不应靠临时 glue code。需要明确 synchronous/asynchronous/hybrid capability、per-player command queue、retry/fatal error contract，以及 replay 时记录 AI command 而不是重放 LLM。

### A3: Architect 共识 — Persistence/cache/sharding 需要一致性协议

来源：rev-claude-architect ✓, rev-dsv4-architect ✓

内容：FoundationDB、Dragonfly、cross-shard room transfer 都涉及状态一致性。需要定义 WorldStore 抽象、write order、persist frequency N、crash recovery data loss contract、cache invalidation per tick phase、cross-shard entity transfer protocol。

### S1: Security 共识 — MCP authz/threat model 是 Phase 2 blocker

来源：rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓

内容：三位 Security 都认为 MCP action tools 等价远程命令接口。Phase 2 前必须完成：private/default bind、gateway entry、per-player/per-session credentials、audience binding、scopes、expiry、revocation、tool-level capability checks、Origin/CORS/SSE、rate limits、audit logs、negative tests。

### S2: Security 共识 — WASM sandbox 要有真实实现与恶意测试

来源：rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓

内容：三位 Security 都要求 Wasmtime 配置具体化。最低要求包括 pinned wasmtime、explicit WASI allowlist/no clock/no random/no fs/no network、fuel eager 或明确模式、max memory、host budget、bounded outputs、pool zeroing、panic containment、malicious WASM corpus、cargo audit/RustSec。

### S3: Security 共识 — Prompt injection 和 untrusted player text 需要专门安全契约

来源：rev-dsv4-security ✓, rev-claude-security ✓, rev-gpt-security ✓

内容：玩家命名、日志、房间文本、错误、replay annotation 等都可能进入 AI prompt。需要 AI snapshot safety contract：typed JSON, provenance/untrusted flags, field length/charset policy, no natural-language wrapping of hostile fields, official AI SDK delimiter template, adversarial regression fixtures。

### S4: Security 共识 — Command validation 是反作弊核心边界

来源：rev-dsv4-security ✓, rev-gpt-security ✓, rev-claude-security ✓

内容：所有 command 必须经过同一 validator path；MCP 不得绕过 WASM validation。需要 RawCommand -> ValidatedCommand -> Applied/Rejected 类型化流程；每个 command 的 ownership、visibility、range、cooldown、resource、body-part、target-state、room/tick freshness invariant 必须成文并测试。

### G1: Designer 方向共识 — MVP 必须包含“完整反馈循环”，不是只有 engine

来源：rev-gpt-designer ✓

内容：可玩的最小单位是“学习规则 -> 做决策 -> 看到结果 -> 理解错误 -> 改进 bot -> 分享故事”。因此 onboarding/tutorial、starter bots、MCP handbook、dry-run validation、explainable rejection、local simulation、replay/spectator、metrics dashboard 应尽早纳入 MVP/launch 定义。

## 未解决分歧

### D1: MCP 工具应最小化为单一 submit path，还是提供丰富 player-facing verbs？

立场 A（rev-dsv4-security, rev-gpt-security）：工具数量越多攻击面越大。应考虑把 11 个 action tools 收敛为单一 `swarm_submit_commands(Vec<Command>)` 或确保所有 tools 只是同一 validation/enqueue path 的薄 wrapper。

立场 B（rev-gpt-designer）：AI 玩家需要像 UI 一样清晰的 MCP verbs、available actions、plan validation、explain-last-tick，否则 first-hour experience 会退化为猜 schema。

可能共识方案：内部只允许单一 command validation/enqueue pipeline；外部可以暴露 rich verbs，但每个 verb 必须是 schema-checked、scope-checked、rate-limited、audited 的 thin wrapper，并与 `swarm_submit_commands` 等价。高风险/debug/inspect tools 默认关闭或 admin-only。

需要用户裁决：Phase 2 MVP 是否优先实现单一 `swarm_submit_commands`，还是同时提供 UX-friendly tool wrappers？若同时提供，是否接受更高测试矩阵成本？

### D2: WASM 是否必须从 MVP 起独立进程隔离？

立场 A（rev-gpt-security）：untrusted WASM 不应在 main tick engine process 内运行；需要 worker processes + OS isolation（seccomp/cgroup/no network/read-only FS/no secrets）。

立场 B（rev-dsv4-security, rev-claude-security）：当前最紧急是 Wasmtime 配置、WASI allowlist、fuel/memory limits、恶意测试；未明确要求 MVP 必须 process isolation，但认可生产需要更强边界。

可能共识方案：Phase 1/2 至少把 `SandboxWorker` 进程边界作为设计接口，不把 engine 与 Wasmtime 紧耦合；MVP 可先单进程 behind feature flag 用于本地开发，但任何 public/multitenant deployment 必须 worker isolation。

需要用户裁决：Phase 2 public test 是否允许单进程 Wasmtime sandbox，还是必须先实现 sandbox worker service？

### D3: Replay/spectator 应早期公开促进社区，还是默认封闭防泄漏？

立场 A（rev-gpt-designer）：public replay URLs、shareable clips、observer/tournament UX 是社区增长和可玩性核心，应作为 launch feature。

立场 B（rev-claude-security, rev-gpt-security）：debug/replay/traces 容易泄漏策略、hidden state、rejected commands、RNG seed、private module errors；默认应 self-only/admin-only/redacted。

可能共识方案：分离 raw trace 与 player-safe replay。Raw trace admin-only；player replay 使用同一 visibility policy 和延迟/赛后 omniscient 模式；public sharing 只能发布 redacted 或 match-completed views。

需要用户裁决：Swarm 首个 public build 是否支持公开 replay？若支持，是 owner-view/opponent-view/redacted-view 还是赛后 omniscient-view？

### D4: FoundationDB 是否应作为早期硬依赖？

用户裁决：**FoundationDB 作为直接依赖**，不需要 WorldStore trait 抽象层。FDB 的 strict serializable 事务和 versionstamp 天然匹配 tick 原子性需求，不再维护多 backend。

原讨论：
- 立场 A（rev-claude-architect）：FDB 对社区自托管门槛高，应定义 WorldStore trait
- 立场 B（rev-dsv4-architect）：关注 FDB + Dragonfly 一致性

最终方案：FDB 直接集成。Dragonfly 仅作为非权威读缓存，FDB 是唯一真相来源。自托管用户需要运行 FDB（提供 docker-compose 一键部署）。

### D5: 竞技公平需要分 league 还是统一榜？

用户裁决：**公平性和排行榜仅在 Arena 模式有意义**。World 模式地图随机生成、玩家加入时机不同，天然不存在公平，不设排行榜。Arena 模式对称起点，分 league 确保公平竞争。

原讨论：
- 立场 A：WASM 与外部 AI 的决策过程不等价，应分 league
- 立场 B：same command limits + identical validation 可能足以让它们在同一世界交互

最终方案：Arena 模式按执行方式分 league（Human/WASM、AI-assisted、AI tournament），World 模式不设排行榜——转而用殖民地年龄、GCL、房间数等作为趣味展示，非竞争排名。

## 行动建议

### P0 — Phase 2 前必须完成的阻断项

1. 编写 `Tick Protocol Spec`
   - 定义 Collect/Execute/Broadcast 状态机、per-player timeout、fail-open zero commands、late command policy、tick atomicity、command ordering key、replay metadata、idempotency/sequence、Bevy system ordering。
   - 来源：rev-claude-architect, rev-dsv4-architect, rev-dsv4-security, rev-gpt-security

2. 编写并实现 `Command Validation Spec`
   - 每个 command 的 ownership、visibility、range、cooldown、resource、body size、target state、room boundary、tick freshness、failure code。
   - 使用 RawCommand -> ValidatedCommand -> Applied/Rejected 类型流；MCP/WASM/REST/admin 均走同一路径。
   - 来源：rev-dsv4-security, rev-gpt-security, rev-dsv4-architect

3. 定义 MCP Security Contract
   - private bind by default；gateway-only public entry；per-player/session JWT 或等价凭证；audience/scope/tool binding；expiry/revocation；strict Origin/CORS/SSE；per-token/player/IP/global rate limit；bounded queues；audit log；negative tests。
   - 来源：rev-claude-security, rev-gpt-security, rev-dsv4-security

4. 实现真实 WASM sandbox baseline
   - wasmtime pinned dependency；explicit WASI allowlist/no fs/no network/no random/no clock；fuel/memory/output/depth limits；host function compute budget；module validation；panic containment；malicious WASM corpus。
   - 同时决定是否 Phase 2 public test 必须 sandbox worker process。
   - 来源：rev-dsv4-security, rev-claude-security, rev-gpt-security

5. 定义统一 Visibility Policy
   - 一套函数/模型回答 “player P at tick T may know what”。REST/WS/MCP/debug/replay/trace/docs examples 全部复用。Snapshot struct 不得只是 `tick` placeholder；必须设计 fog-of-war-safe view model。
   - 来源：rev-dsv4-security, rev-claude-security, rev-gpt-security, rev-gpt-designer

6. 限界所有 query/helper/JSON 输入输出
   - PathFind MAX_PATH_LENGTH/map bounds/fuel or host budget；GetObjectsInRange max range/response cap/fog-of-war；Spawn MAX_BODY_PARTS；JSON depth/size/string/duplicate/numeric bounds；i32 coordinate overflow 策略。
   - 来源：rev-dsv4-security, rev-dsv4-architect, rev-gpt-security

### P1 — Phase 2/3 前应完成的高优先级设计

7. PlayerExecutor v2
   - 支持 synchronous/asynchronous/hybrid capability、AI late command queue/rejection、retryable/fatal error、player suspension、AI replay records accepted commands not LLM recalls。
   - 来源：rev-claude-architect, rev-dsv4-architect

8. MCP tool UX 与安全折中方案
   - 内部单一 submit/validate/enqueue pipeline；外部 rich verbs 仅作为薄 wrapper。增加 `swarm_get_available_actions`, `swarm_validate_plan`, `swarm_explain_last_tick` 时必须同样受 scope/rate/visibility/audit 控制。
   - 来源：rev-gpt-designer, rev-dsv4-security, rev-gpt-security

9. AI Snapshot Safety Contract
   - typed JSON only, untrusted provenance tags, field policies, no untrusted natural language instructions, official AI SDK prompt delimiters, prompt-injection regression fixtures。
   - 来源：rev-claude-security, rev-gpt-security, rev-dsv4-security

10. Debug/replay data classification
   - raw traces admin-only；player-safe replay redacted/self-scoped；public replay only through explicit safe view；ClickHouse retention/access logs/redaction。
   - 来源：rev-claude-security, rev-gpt-security, rev-gpt-designer

11. Persistence contract（FDB 直连）
   - FDB 作为唯一真相来源直接集成；Dragonfly 仅作为非权威读缓存（不可失效缓存），不在 FDB 之前写入。persist frequency N=1（每 tick 提交）；data-loss contract 明确；schema versioning/migrations。
   - 来源：rev-claude-architect, rev-dsv4-architect, rev-dsv4-security

12. Rate-limit policy matrix
   - MCP tools, docs, replay, room reads, WS subscriptions, AI registration, login, code upload, module status, debug endpoints, per-IP/per-player/per-token/global。
   - 来源：rev-claude-security, rev-gpt-security, rev-dsv4-security

### P2 — MVP/launch 可玩性与社区基础

13. Move onboarding into MVP
   - human 5-minute tutorial；AI 5-minute MCP tutorial；tutorial room；starter bots TS/Rust/MCP；opening book；MCP capability manifest。
   - 来源：rev-gpt-designer

14. Explainable failure and dry-run APIs
   - command rejection with exact failed precondition and suggested fix；`swarm_validate_plan`; `swarm_explain_last_tick`; per-unit “why idle?”。
   - 来源：rev-gpt-designer, rev-dsv4-architect

15. Local simulation/test harness and bot versioning
   - players can run thousands of ticks locally, import/export replay fixtures, compare strategy versions, rollback deployments。
   - 来源：rev-gpt-designer, rev-claude-architect

16. League/fairness policy
   - Define Human/WASM, AI-assisted, AI tournament, sandbox/exhibition classes; publish decision latency, invalid rate, model/provider label, tool usage class。
   - 来源：rev-gpt-designer, rev-dsv4-architect, rev-gpt-security

17. Spectator/replay product with safe modes
   - launch with safe replay view if possible: owner-view, opponent-view, delayed/redacted public clips, post-match omniscient mode only after hidden-state value expires。
   - 来源：rev-gpt-designer, rev-claude-security, rev-gpt-security

18. Progression and objective clarity
   - define immediate/strategic/seasonal goal layers; add strategy metrics dashboard; plan progression diversity beyond Screeps basics。
   - 来源：rev-gpt-designer

## 最终建议

不要把本轮 REQUEST_CHANGES 解读为否定项目方向。评审议会的共同判断是：Swarm 的技术与游戏愿景值得继续，但必须先把“多人可编程 MMO 的基础契约”写清并落地测试。

推荐下一步不是直接进入 Phase 2 MCP 工具实现，而是开一个短的 Design Hardening Sprint，产出并验证以下 6 个可审查工件：

1. Tick Protocol Spec
2. Command Validation Spec
3. MCP Security Contract
4. Wasm Sandbox Baseline + malicious corpus
5. Unified Visibility Policy
6. MVP Feedback Loop Spec（onboarding/debug/replay/dry-run）

这些工件完成后，再进入 Phase 2，风险会显著下降，且 Architect/Security/Designer 三个方向的主要反对意见都能被追踪关闭。
