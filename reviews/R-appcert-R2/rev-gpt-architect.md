# R-appcert-R2 Clean-Slate 架构评审 — rev-gpt-architect

## Verdict

CONDITIONAL_APPROVE

R-appcert-R2 的主架构方向成立：它已经从“AI/MCP 直接玩游戏”的高风险形态，收敛为“所有玩家统一通过 WASM 沙箱产生命令，MCP/Web 只是同级控制面与观察面”的正确模型。Auth 独立控制面、应用层证书、Transport Auth Matrix、Source Gate、CommandIntent/RawCommand 分层、Tick 原子提交、可见性单函数、IDL 单一真相源，这些都是可以支撑后续实现的骨架。

但它还不应直接进入实现。当前风险不是“概念错”，而是几个关键边界仍以候选项、分散权威表或跨阶段承诺存在：Tick 成功后缓存/广播/回放的权威语义、FDB+Dragonfly 读一致性边界、RuleMod/动态 action 的扩展能力、Tier2/Tier3 snapshot/shard entry gate、以及 transport audience 字符串在不同文档中的 canonical 形式。建议在实现前做一次 R2.5 文档冻结：只收敛协议，不新增玩法。

## Strengths

- 统一执行路径正确：WASM 是唯一 gameplay executor，MCP 不含 move/attack/build 等动作工具，避免了 AI 玩家特权通道；这类似成功的“控制面/数据面隔离”架构，而不是早期 MMO bot API 常见的旁路控制器。
- Source Gate + CommandIntent/RawCommand 分层清晰：`player_id/source/tick/auth` 由服务端注入，客户端只提交 intent，这个边界对新人也直观，能显著降低伪造身份和跨来源重放风险。
- Tick 生命周期比常见 ECS+DB 设计更成熟：COLLECT/EXECUTE/BROADCAST 三阶段明确，inline validate+apply、FDB commit 失败后 Bevy World restore、COLLECT 结果跨重试复用、TickTrace 与状态同事务等设计能闭合大部分 determinism 和 TOCTOU 风险。
- Auth 模型已从“token 到处飞”收敛为独立控制面：Server Root/Intermediate CA、用途隔离证书、canonical request signature、证书签发审计、CRL/epoch emergency bump 的边界清楚。
- 可见性设计有单一函数：`is_visible_to(player,tick)` 被要求覆盖 WASM snapshot、MCP query、REST、WebSocket delta、replay，避免“调试接口泄露战争迷雾”的典型失败模式。
- IDL / World Action Manifest 的方向正确：Core IDL 稳定，world.toml 扩展生成 manifest/hash，SDK/MCP/schema/replay 由同源生成，能减少手写 Command enum、validator、MCP schema 三套漂移。

## Concerns

### A1 — High — Phase 3 BROADCAST 与 query 读源语义仍可能造成“已提交但不可观察”的长尾不一致

设计明确 `BROADCAST failure never rolls back committed tick`，Dragonfly/NATS 失败不影响 FDB 中的权威状态；查询读源优先级又规定当前 snapshot 来自 Bevy、历史 tick 来自 FDB、高频读取可来自 Dragonfly 且允许滞后 ≤2 tick。这是合理的方向，但缺少一个统一的 `state_version/tick_version` 合同来约束所有输出面。

看起来没问题但会炸的模式是：tick 已 commit，NATS 发布失败，Dragonfly 更新滞后，WebSocket 客户端 gap fetch 走 REST，而 REST 某些路径读 Dragonfly 或 Bevy 快照缓存，最终玩家看到 tick N+1 的局部状态和 tick N 的缓存状态混合。对游戏来说这不是权威状态错误，但会变成调试、回放、AI 策略输入和用户 UI 的一致性噩梦。

建议：R2.5 冻结一个 Output State Contract。每个响应必须携带 `state_tick`、`source={bevy,fdb,dragonfly,nats}`、`cache_lag_ticks`、`visibility_epoch`；当请求指定 `min_tick` 时，Dragonfly 不满足则必须 fallback FDB，不允许返回旧缓存。WebSocket delta、REST gap fetch、MCP snapshot 应共用同一个 tick-indexed read API。

### A2 — High — Tier2/Tier3 文档仍是候选协议，但主设计已经把它们当扩展承诺

Tier2 incremental snapshot 文档仍保留关键待定项：CoW page size vs modification-set、keyframe interval、FDB atomic mutation mapping。Tier3 shard protocol 也保留一致性哈希、动态重平衡、跨分片 replay/anti-cheat 审计链、FDB multi-region topology 等待定项。与此同时 engine 文档已把 Tier2/Tier3 写进扩展路线和 entry gate。

这很像成功项目里的“扩展路线图”，但也像失败项目里的“未来会支持水平扩展”陷阱：早期 API、entity id、TickTrace、snapshot hash、room ownership、module deployment 一旦没按未来分片约束设计，后面补 shard 会撕裂所有边界。

建议：把 Tier2/Tier3 从“设计承诺”改为硬 gate。Tier1 实现允许只支持单节点，但必须冻结对未来不可逆的字段：global entity id 格式、snapshot hash chain、TickTrace schema、room/shard ownership 字段、cross-room combat 禁止或延迟语义、module deployment scope。Tier2/Tier3 具体算法可 later，但不可逆 schema 不能 later。

### A3 — High — Dynamic CommandAction / RuleMod 能力边界过宽，容易侵蚀 Command Validation 单一路径

R2 已明确 RuleMod 不能直接写 ECS，只能通过 `actions.*` buffer；也规定新增 CommandAction 需要注册 validate/apply handler + IDL 暴露。这是正确边界。但文档同时允许 custom actions、special effects、actions.add_body_part_type、custom handler、RuleMod damage/effect/attribute/event/resource 能力。扩展面正在逼近“第二套引擎”。

失败案例模式是：核心引擎保持 deterministic，插件系统却拥有过多可组合写能力，最终每个世界都产生自己的命令语义，回放、反作弊、SDK 和 MCP schema 难以验证。尤其 `RuleMod` 被列为 source 且允许 damage/effect/custom handler，即使它“不算 gameplay command”，也仍会改变同一世界状态。

建议：冻结 RuleMod Capability Lattice。每个 capability 必须声明读集、写集、执行阶段、deterministic budget、replay encoding、visibility effect、是否允许影响玩家私有状态。新增 custom action 必须先进入 World Action Manifest，并生成 TickTrace schema；未进入 manifest 的 Rhai action 只能改全局环境参数，不得改实体战斗/所有权/资源归属。

### A4 — Medium — Transport audience / canonical auth 字符串存在跨文档漂移风险

auth.md 的 audience 示例为 `transport:server_id:world_id:player_id`，03-mcp-security 使用 `{server_id, world_id, "cli"}`，09-command-source 定义 `mcp:{server_id}:{world_id}:{player_id}` / `ws:` / `rest:`，12-gateway-protocol 又给出 Transport Auth Matrix。R2 已经比早期版本好很多，但仍有多个“看似同义”的 canonical 形式。

这类问题实现时通常不会立刻炸；它会在 SDK、Gateway、Engine、MCP client 分别实现后才出现 401/403 难排查故障，或者更坏：某条路径接受了宽松 audience，从而允许跨 transport replay。

建议：指定唯一 ABNF/JSON canonical form，例如 `aud = { transport, server_id, world_id, subject_player_id, optional_match_id }`，禁止自由字符串拼接。所有文档引用同一节，不再各写示例。Transport Auth Matrix 应成为唯一权威表，并加上 negative examples。

### A5 — Medium — ECS 调度顺序有清单，但“并行安全证明”覆盖范围不足

01-tick-protocol 给出了 20 系统链和部分 Component/Resource 读写矩阵，这是好事。但矩阵只覆盖少数组件字段；实际系统链包含 RuleMod tick_start/tick_end、pvp_block、global_storage、controller、repair、room_state、NPC AI/combat、world_event/effect 等多个会改变全局或实体状态的系统。

风险是 Bevy `.before/.after` 看起来指定了顺序，但新增系统或 optional mod system 后产生隐式并行、读写冲突或非确定迭代顺序。尤其 RuleMod、NPC、world_event 与 combat/decay 的相对顺序将直接影响 replay determinism。

建议：把“ECS Schedule Manifest”作为生成物冻结：每个 system 必须声明 phase、reads、writes、ordering dependencies、determinism hazards、是否允许并行。CI 应从 manifest 检查 Bevy schedule，而不是人工读表。所有 optional systems / RuleMod hooks 必须挂到固定 slot，不能自由 before/after 核心系统。

### A6 — Medium — Snapshot truncation 语义在 Tier1 与 Tier2 之间不一致，会影响 AI 策略可迁移性

Tier1 截断按 priority bucket + distance + entity_id；Tier2 推荐 `(bucket,last_modified_tick DESC,entity_id)`。两者都 deterministic，但对玩家策略的语义完全不同：Tier1 保近处实体，Tier2 保最近变化实体。玩家代码会把 snapshot 缺失当作战术信息的一部分；迁移 Tier2 后同样 256KB 限制下，AI 可能突然看不见附近静态防御或资源点。

建议：除非有强基准证明，否则 Tier2 也应保持 Tier1 的玩家语义，内部可用 modification-set 优化构建，但最终可见集/截断排序对玩家应稳定。若必须改变，需 manifest 标记 `snapshot_truncation_semantics_version`，并让 SDK/World Rules 明示。

### A7 — Low — “Admin 统一管线但放宽所有权检查”还需要更细的爆炸半径控制

09-command-source 说 Admin 命令走标准 `validate_and_apply()`，仅 RejectionReason 阈值放宽；Rollback 需要双人审计。这比独立 admin path 安全。但 Admin 允许写世界、全局存储、部署代码、查询全局、触发战斗，权限面过宽。

建议：AdminCertificate scope 拆分为 `admin:read_trace`、`admin:pause_world`、`admin:rollback`、`admin:mutate_entity`、`admin:trust_policy`、`admin:deploy_override`。每个 scope 定义是否需要双签、是否写 TickTrace、是否进入 public audit feed。不要用一个 `swarm:admin` 覆盖所有能力。

## Missing

- Output State Contract：缺少跨 WebSocket/REST/MCP/gap fetch 的统一 `state_tick`、cache fallback、staleness、visibility_epoch 语义。
- Canonical Transport Audience：缺少唯一语法和唯一权威字段定义，当前多个文档存在同义但不同形态的 audience 示例。
- ECS Schedule Manifest：缺少覆盖全部系统与 optional hooks 的读写集、排序依赖和 CI 校验机制。
- RuleMod Capability Lattice：缺少每个扩展能力的 read/write set、replay encoding、visibility impact、TickTrace schema 绑定。
- Tier2/Tier3 Irreversible Schema Gate：缺少在 Tier1 前必须冻结的 global entity id、snapshot hash chain、TickTrace shard fields、room ownership/shard ownership、cross-room/cross-shard interaction policy。
- Dragonfly Degradation Runbook：已有“cache miss/stale 可从 FDB 重建”，但缺少 cache warm、version compare、stale-read rejection、backpressure 和 full FDB fallback 的操作准则。

## Phase Ordering

1. R2.5 文档冻结（必须先做）：统一 Transport Auth Matrix/audience grammar、Output State Contract、ECS Schedule Manifest、RuleMod Capability Lattice、Tier2/Tier3 irreversible schema gate。此阶段不新增玩法，不写实现。
2. Implementable Core Cut：只实现 Tier1 单 Engine、单 FDB 权威、Dragonfly 非权威缓存、NATS best-effort 推送、WASM-only gameplay、MCP/Web 同级控制面。明确禁用 dynamic CommandAction、Tier2 incremental snapshot、Tier3 shard、multi-region FDB。
3. Determinism Harness First：在 gameplay 功能扩展前，先实现 TickTrace、state_checksum、FDB commit failure restore test、replay verification、schedule manifest CI、schema generation CI。
4. Auth/Gateway Interop Freeze：先让 Browser/REST/MCP/CLI 全部通过同一 canonical request verifier 和 audience parser，再开放 deploy/query。不要让各端各自实现 audience string。
5. RuleMod Minimal Pilot：只开放全局环境/资源池级 capability，禁止实体 combat/ownership custom handler；等 TickTrace/replay/schema 能表达后再开放更多 capability。
6. Tier2/Tier3 Later Gates：只有当 Tier1 metrics 触达 entry threshold，且 Tier2/Tier3 待定项被基准测试和专家评审冻结后，才进入增量快照或分片实现。

## Final Assessment

R-appcert-R2 可以作为架构基线继续推进，但需要一次短而硬的 R2.5 收敛。当前最值得保留的是：WASM-only gameplay、Auth 独立控制面、Source Gate、Tick 三阶段、FDB 权威源、可见性单函数、IDL/manifest 单源生成。当前最不应急着实现的是：dynamic action / RuleMod 深能力、Tier2 incremental snapshot、Tier3 shard、多区域 FDB。只要先把上述 missing contracts 冻结，R2 的爆炸半径可控，后续实现风险明显低于早期版本。
