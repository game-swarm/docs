# R41 Phase 1 Clean-Slate — Architect Review

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前设计在核心方向上有大量成熟内容：确定性 tick、WASM sandbox、redb replay-critical 分层、Source Gate、visibility oracle 防线都已经具备目标状态设计深度。但文档集内部仍存在多个会直接误导实现的架构级冲突，尤其是：README/安全/MCP 文档仍保留已移除组件与旧信任模型；Command Source 与 Auth/Tech Choices 的权威模型冲突；Spawn/EntityCreation/SpawningGrace 的时序合同互相矛盾；持久化 replay 路径中 deterministic replay 与 object-store 依赖表述冲突。这些不是措辞问题，而是会导致接口、实现边界、安全审计与 replay 语义分叉的阻塞问题，因此请求重大修改。

## 2. 发现的问题

### A-H1 — 顶层架构图仍保留已移除组件与旧实现语言

Severity: High

文件引用：
- `/tmp/swarm-review-R41/design/README.md:82-87`
- `/tmp/swarm-review-R41/design/README.md:131-136`
- `/tmp/swarm-review-R41/design/tech-choices.md:134-155`
- `/tmp/swarm-review-R41/design/auth.md:52-56`

问题描述：
`design/README.md` 的顶层架构图仍声明 Gateway 为 Go，并在数据层列出 Dragonfly 与 ClickHouse：
- README `Gateway (Go)` 与 auth 文档中的 `Gateway (Rust)` 冲突。
- README 数据层列出 `Dragonfly (热缓存)`、`ClickHouse (分析 + 审计)`，但 `tech-choices.md` 明确写明 Dragonfly 已被 Moka Cache 移除，ClickHouse 已被 redb metrics table + Gateway 聚合替代。

影响分析：
README 是入口文档与架构总览。这里保留旧组件会造成实现者、部署者和 reviewer 对真实系统边界产生错误理解：
- Gateway 语言会影响 repo/module 边界、认证 middleware、SDK 生成与运维责任归属。
- Dragonfly/ClickHouse 是否存在会影响数据流、部署拓扑、审计表存储、故障模型与性能预算。
- 该冲突还会污染后续文档，因为 README 的架构图通常被当作全局 mental model。

修复建议：
将 README 架构图与 tech-choices 的终态保持一致：
- Gateway 统一为 Rust，或若确实要 Go，则同步修改 auth/tech-choices 并给出单一权威裁决。
- 删除 Dragonfly/ClickHouse 数据层框，改为 Engine 内 Moka Cache、redb metrics table、Gateway fan-out aggregation。
- 如果审计日志仍需要独立分析存储，应在 tech-choices 中重新裁决，不要在 README 与 MCP/security 文档中残留旧 ClickHouse。

### A-H2 — Auth 信任模型在 auth、command-source、mcp-security 三处不一致

Severity: Critical

文件引用：
- `/tmp/swarm-review-R41/design/auth.md:31-33`
- `/tmp/swarm-review-R41/design/auth.md:120-125`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:20-21`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:66-68`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:112-113`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:132`
- `/tmp/swarm-review-R41/specs/security/03-mcp-security.md:46-54`
- `/tmp/swarm-review-R41/specs/security/03-mcp-security.md:198-220`

问题描述：
`design/auth.md` 裁定为单层 Server CA、仅两种证书类型：`ClientAuthCertificate` 与 `CodeSigningCertificate`，Admin 通过 ClientAuthCertificate + admin scope 表达，不需要独立 AdminCertificate/FederationCertificate。

但 `09-command-source.md` 与 `03-mcp-security.md` 仍保留旧模型：
- Source 矩阵把 Admin 写成 `AdminCertificate + signed request`。
- 注册流程写 `Server Intermediate CA`，吊销中出现 `Server Intermediate CA`。
- 部署验证写 `Server Root CA`。
- MCP security 证书 usage 仍包含 `admin | federation`，issuer_chain 仍为 `Server Intermediate CA → Server Root CA fingerprint`。

影响分析：
这是认证根与能力模型的根本冲突，会直接导致：
- 证书 schema/codegen 无法确定是否存在 Admin/Federation usage。
- CRL、epoch bump、scope 校验与 deploy 验证逻辑实现分叉。
- 安全审计无法判断 compromised CA 是 Server CA、Root CA 还是 Intermediate CA。
- Admin 权限到底是 scope 还是独立证书类型不清，会影响最小权限、密钥轮换和双签策略。

修复建议：
以 `design/auth.md` 的终态为准，批量清理所有旧 CA/证书术语：
- `Server Root CA` / `Server Intermediate CA` 统一替换为 `Server CA`。
- `AdminCertificate` 改为 `ClientAuthCertificate + admin scope + per-tool admin_cert_required/authz policy`，或重新裁决三证书模型；但必须全局一致。
- `usage: admin | federation` 从 MCP/security schema 中移除，除非 auth 文档重新声明它们是正式证书类型。
- Command Source 中的 revocation reason `intermediate_ca_compromise` 改为与单层 Server CA/epoch bump 一致的事件名。

### A-H3 — Rhai / RuleMod 残留与“Bevy Plugin 是唯一扩展机制”冲突

Severity: High

文件引用：
- `/tmp/swarm-review-R41/design/engine.md:11-12`
- `/tmp/swarm-review-R41/design/tech-choices.md:48-87`
- `/tmp/swarm-review-R41/design/tech-choices.md:200-208`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:31-32`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:47-48`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:178-179`
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:303-309`

问题描述：
engine 与 tech-choices 明确声明 Mod = Bevy Plugin 静态编译，Rhai 已移除，且这是唯一扩展机制。但 Command Source 仍保留 `RuleMod` source，并描述为 Rhai 规则模组 actions，含 Rhai op budget、RuleMod 在 World/Arena 中的行为，以及 RawCommand 顺序中 RuleMod actions。

影响分析：
这会破坏扩展机制的抽象边界：
- 如果 RuleMod/Rhai 仍可产生 actions，则 Bevy Plugin 并非唯一扩展机制。
- Source Gate 与 validate_and_apply 必须为 Rhai 设计 capability sandbox、op budget、auth context，这与当前“服主信任的静态 Rust Plugin”完全不同。
- 安全模型会错误地把 mod 当作半可信脚本来源，而不是 engine 进程内 trusted code。
- Arena 赛前锁定、replay、manifest hash 到底记录 Plugin set 还是 RuleMod actions 也会混乱。

修复建议：
删除 `RuleMod` source 及 Rhai 相关能力/预算/排序描述。若需要表达 mod 触发的系统效果，应建模为：
- Engine/Plugin trusted system，纳入 system manifest / ActionRegistry hash / world manifest；
- 不作为外部 RawCommand source；
- 不经过玩家 Source Gate，而通过 ECS system schedule 与 manifest hash 保证确定性。

### A-H4 — Spawn 创建、同 tick 可见性与 SpawningGrace 合同互相矛盾

Severity: Critical

文件引用：
- `/tmp/swarm-review-R41/design/engine.md:256-260`
- `/tmp/swarm-review-R41/specs/core/02-command-validation.md:272-274`
- `/tmp/swarm-review-R41/specs/core/06-phase2b-system-manifest.md:177-192`
- `/tmp/swarm-review-R41/specs/core/06-phase2b-system-manifest.md:393-405`

问题描述：
设计同时声明了两组互斥合同：

1. Spawn 时序与 SpawningGrace：
- S08 `spawn_system` 创建 drone。
- S09 `spawning_grace_system` 紧接着为新生 drone 添加 `SpawningGrace { remaining: 1 }`。
- 该组件用于让新生 drone 在“本 tick”免疫所有伤害，防止出生即斩。

2. Entity Creation Visibility Contract：
- 所有实体创建路径统一写入 `PendingEntityCreation`。
- 新实体在当前 tick 结束 flush 前不加入可交互世界索引。
- `visible_same_tick=false`、`interactable_same_tick=false`。
- 从下一 tick 开始参与快照、命令校验和系统迭代。

若新生 drone 本 tick 不可见、不可交互、也不进入系统扫描，则 S09 无法读取“newly spawned Drone”并为其添加 grace；同时它本 tick 本来就不会被 combat 系统攻击，SpawningGrace 的“本 tick 免疫”没有对象。若 S08 直接创建并让 S09/S11-S15 可见，则又违反了统一 PendingEntityCreation 合同。

影响分析：
这是 tick 时序与 ECS visibility 的阻塞矛盾，会影响：
- 出生保护是否必要、何时生效、持续几个 tick。
- RoomCap 释放/消费与实体可交互性的关系。
- Combat filter 是否能看到新生实体。
- Replay 中新 entity id 分配与 status component 写入顺序。
- Spawn resource refund 与 Phase 2b 创建失败的语义。

修复建议：
二选一并全局统一：

方案 A（推荐，保持 PendingEntityCreation 纯净）：
- S08 只写 PendingEntityCreation，新 drone 下一 tick 才进入世界。
- 移除“本 tick 出生即斩”问题，因为本 tick 不可交互。
- 将 SpawningGrace 改为 `spawn_protection_until_tick = created_tick + 1` 或创建时携带初始 component，在 flush 后下一 tick 首次可交互时生效。
- S09 改为处理上一 tick flush 后的新实体，而非同 tick pending entity。

方案 B：
- 允许 Spawn 作为例外同 tick materialize，但必须在 Entity Creation Contract 中明确例外，并说明 stable id、visibility、interaction、combat filter 与 RoomCap 的特殊规则。
- 不建议，因为会破坏“所有实体创建路径统一 PendingEntityCreation”的抽象简洁性。

### A-H5 — CommandAction / ActionRegistry 迁移未完全闭合，旧 Attack/Heal 等指令仍以独立命令形态出现

Severity: High

文件引用：
- `/tmp/swarm-review-R41/design/engine.md:250-254`
- `/tmp/swarm-review-R41/specs/core/06-phase2b-system-manifest.md:88-93`
- `/tmp/swarm-review-R41/specs/core/02-command-validation.md:223-256`
- `/tmp/swarm-review-R41/specs/core/02-command-validation.md:289-428`
- `/tmp/swarm-review-R41/specs/core/02-command-validation.md:655-704`

问题描述：
engine 与 manifest 明确声明 R35 D3 后 `CommandAction` 不再包含 `Attack`/`RangedAttack`/`Heal` 等 combat variant，所有 combat 与 special attacks 统一通过 `Action { type, payload }` + ActionRegistry dispatch。

但 `02-command-validation.md` 前半部分仍保留 `### 3.5 Attack`、`### 3.7 Heal`、`### 3.10 Hack` 等独立指令形态 JSON，例如 `{ "type": "Attack", ... }`、`{"type":"Hack",...}`。后半部分又声明这些应通过 `CommandAction::Action` dispatch。

影响分析：
这会导致 wire schema 与 validator 实现分叉：
- 玩家/SDK 不知道应该发 `{type:"Attack"}` 还是 `{type:"Action", action_type:"Attack"}`。
- Source Gate、schema validation、canonical serialization、command_hash 可能对同一动作产生两种编码。
- Replay 与 TickTrace 无法保证 command action taxonomy 唯一。
- API Registry 作为权威源时会与 command-validation 的示例冲突，影响 codegen。

修复建议：
重写 `02-command-validation.md` §3：
- 只保留 11 种非 combat 基础 CommandAction 的独立校验。
- Attack/RangedAttack/Heal + 8 special attacks 全部移动到 ActionRegistry 小节，统一示例为 `{ "type": "Action", "action_type": "...", "payload": ... }` 或 registry 中规定的 canonical shape。
- 旧独立 action 表若保留，只能作为“ActionRegistry handler 参数表”，不得展示为顶层 CommandIntent。

### A-H6 — Command Source 的 deploy 顺序与 tick/deploy 激活语义冲突

Severity: High

文件引用：
- `/tmp/swarm-review-R41/specs/security/09-command-source.md:301-313`
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:123-127`
- `/tmp/swarm-review-R41/design/engine.md:266-267`

问题描述：
Command Source §8.1 声明 RawCommand 顺序为：Admin、Deploy、WASM tick 输出，并写“Deploy 命令（先部署，后 WASM 执行可引用新代码）”。但 Persistence Contract 的 deploy 不变量明确声明：同一 tick 内 deploy 不影响当前 tick，部署在 `activation_tick >= current_tick + 1` 生效；engine 也强调 tick 时使用预编译模块，COLLECT 开始前确定 active module。

影响分析：
这会引发严重 TOCTOU 与 replay 分歧：
- 如果 Deploy 在 WASM 前生效，则同 tick 的 COLLECT 快照和 module set 不再是 tick 开始时固定输入。
- 如果 Persistence 是权威，则 Command Source 的顺序描述会误导实现者在 Source Gate/RawCommand sort 中把 Deploy 当作 gameplay tick 内命令。
- Arena/World 的 deploy timing 也会不一致，影响公平性与 replay。

修复建议：
将 Deploy 从“RawCommand gameplay ordering”中移出，明确为控制面 mutation：
- deploy RPC 可在 tick N 提交 manifest；
- module activation decision 记录在 tick N 的 deploy_activation_decision；
- COLLECT 使用 tick 开始时的 active_module；
- 新模块最早 tick N+1 生效。
Command Source §8.1 应只描述进入 gameplay command queue 的命令，Deploy/MCP_Query 不应与 WASM action 同列排序。

### A-H7 — Persistence replay 文本仍暗示 deterministic replay 依赖 Object Store / RichTraceBlob

Severity: Medium

文件引用：
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:34-42`
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:58-62`
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:216-226`
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:238-245`
- `/tmp/swarm-review-R41/specs/core/05-persistence-contract.md:321-349`

问题描述：
Persistence Contract 前半部分反复强调 deterministic replay 只需要 redb TickCommitRecord 10 字段 + keyframe/delta chain，Object Store/RichTraceBlob 缺失只产生 audit_gap，不会 unreplayable。但 §5.1 “正常 Replay” 的步骤却从 object store 获取 `tick_trace_blob` 并反序列化 TickCommitRecord；§5.3 Replay Verifier 输入也包含 `object_store_blobs`，且写成 `fdb_manifest_list`；§7.2 又把 RichTraceBlob delta chain 损坏描述为可能导致 replay verifier 链断裂。

影响分析：
该冲突会让实现者无法判断 replay verifier 的真实依赖：
- TickCommitRecord 到底在 redb 还是 RichTraceBlob 中？
- Object Store 404 是否只是 rich audit gap，还是会导致 replay verifier 无法运行？
- `unreplayable` 是 deterministic replay 失败，还是 rich debug replay 失败？
- 文中 `fdb_manifest_list` 疑似 typo，也增加权威合同不清。

修复建议：
拆成两个明确流程：
1. Deterministic replay：只读 redb TickCommitRecord + independent keyframe/delta chain，不拉 RichTraceBlob。
2. Rich debug replay：可选拉 object store RichTraceBlob，失败只标记 audit_gap/rich_debug_unavailable。

同时：
- 修正 `fdb_manifest_list` 为 `redb_manifest_list` 或实际术语。
- 删除“RichTraceBlob delta chain 断裂导致 deterministic replay 链断裂”的表述，或改名为 rich_trace_chain。
- `unreplayable` 仅用于 redb/keyframe replay-critical 数据无法恢复，不用于 rich blob 缺失。

### A-H8 — Visibility 文档允许 `fog_of_war=false` 让 drone 感知全图，需明确其是否仍属于正式游戏模式

Severity: Medium

文件引用：
- `/tmp/swarm-review-R41/specs/security/05-visibility.md:127-139`
- `/tmp/swarm-review-R41/specs/security/05-visibility.md:311-349`

问题描述：
Visibility 文档一方面强调 competitive world 中 `fog_of_war=true && player_view=full` 被拒绝，MCP agent 永远只能看到与 WASM snapshot 相同范围；另一方面配置表允许 `fog_of_war=false`，并在教学世界示例中说明 drone snapshot 包含全地图。

问题不在于教学/合作世界可全图，而在于该配置是否被严格限定为 non-competitive/tutorial/coop/sandbox mode。当前 §9 表格列出 WorldConfig.visibility 默认与组合场景，但没有像 `sandbox.relaxed` 那样给出启动期硬校验：哪些 world.mode 可设置 `fog_of_war=false`、是否允许 Standard World、是否影响排行榜/公开世界。

影响分析：
如果标准 World 允许 `fog_of_war=false`，则 MCP/WASM 可见性安全合同不再是全局不变量，玩家和 AI 可获得全图信息，破坏公平与 oracle 防线。若仅用于教学/合作，应把它建模为 mode-level capability，而不是普通可配置项。

修复建议：
增加 `validate_config` 硬规则：
- `fog_of_war=false` 仅允许 `world.mode in {tutorial, coop, sandbox, development}` 或明确的 non-competitive profile。
- Standard World / ranked World / public competitive World 必须 `fog_of_war=true`。
- Arena 的全图规则作为 Arena mode 固有规则，不通过 WorldConfig 任意开关表达。

### A-H9 — MCP 安全文档仍把审计日志写入 ClickHouse，与技术选型冲突

Severity: Medium

文件引用：
- `/tmp/swarm-review-R41/design/tech-choices.md:146-155`
- `/tmp/swarm-review-R41/specs/security/03-mcp-security.md:374-392`

问题描述：
tech-choices 明确 ClickHouse 已移除，分析改为 redb metrics table + Gateway 聚合。但 MCP security §7 仍定义 `mcp_audit` ClickHouse MergeTree 表并要求保留 90 天。

影响分析：
审计日志是安全证据链的一部分，存储位置和不可修改性必须清晰。ClickHouse 残留会导致：
- 部署清单与运维 runbook 错误预期 ClickHouse。
- 审计保留、篡改防护、备份恢复策略与 redb/object store 分层不一致。
- “ClickHouse 已移除”的技术选型不可信。

修复建议：
将 MCP audit 存储改为当前终态之一：
- redb audit table + append-only hash chain；或
- object store append-only log + redb pointer/hash；或
- 如果确实需要 ClickHouse，则撤销 tech-choices 中“已移除”的裁决并重新纳入架构图。

### A-H10 — README 文档导航引用未授权/未评审文件作为核心事实源，容易形成 Clean-Slate 评审边界外依赖

Severity: Low

文件引用：
- `/tmp/swarm-review-R41/design/README.md:11-19`
- `/tmp/swarm-review-R41/specs/security/03-mcp-security.md:238-242`

问题描述：
README 导航将 gameplay/interface/RUNBOOK/AGENTS 等列为核心文档，MCP security 也大量指向 API Registry/IDL 之外的 interface 文档。对于本次方向聚焦评审，这不是直接错误；但从文档架构看，多个核心合同分散在未同时审阅的文档中，且当前已发现 interface/MCP/security/auth 之间存在旧术语残留风险。

影响分析：
设计文档如果依赖多个未同步的“权威源”，容易造成局部修复后再次漂移。尤其 API/ActionRegistry/visibility/MCP/auth 是跨模块边界，必须有明确单一事实源与生成校验。

修复建议：
保留导航，但在每个跨域文档开头增加 authority boundary：
- 本文件权威定义什么；
- 哪些内容只引用，不重复；
- 冲突时以哪个 IDL/registry/spec 为准；
- CI 如何检测重复声明漂移。

## 3. 亮点

1. Tick 执行模型的分层方向正确。Phase 2a sorted command loop + Phase 2b serial spine/parallel sets 的分离清晰，尤其是 `ActionRegistry handler → intent buffer → reducer/status writer` 的模式，能把玩家命令顺序、公平竞争与 HP/status 统一结算分开。

2. Determinism contract 覆盖面较完整。文档明确使用 stable entity id、canonical command order、BTreeMap/IndexMap 约束、fixed-point integer、floor rounding、manifest hash 与 codec version，这些都直接支撑 replay 与跨平台一致性。

3. WASM sandbox 设计深度足够。Wasmtime fuel、epoch interruption、WASI 禁用、module prevalidation、seccomp/cgroup/netns、Store reset checklist、恶意样本库与 CVE SLA 都不是表面描述，已经达到可指导实现的合同级细节。

4. Source Gate 的基本原则正确。CommandIntent 不允许客户端自报 player_id/source/tick/auth，由服务端注入 RawCommand envelope，这个边界对防伪造、防 replay 与审计都非常关键。

5. Visibility oracle 防线有系统性。统一 `is_visible_to`、输出面逐项过滤、snapshot/MCP/WS/REST/replay tick 基准、特殊攻击拒绝码等价策略、omitted_count 分桶，这些设计能有效降低跨接口信息泄露。

6. Persistence 的 replay-critical vs rich debug 分离是正确方向。redb 小对象权威提交、object store 异步 rich blob、keyframe 独立存储、hash chain、commit retry 不重跑 WASM，这些选择与项目的确定性目标一致。

7. 技术选型整体有克制。移除 Dragonfly/ClickHouse/Rhai、收敛到 redb + Moka + Bevy Plugin，避免了早期过度工程化，符合单 shard/静态分片/确定性 replay 的目标状态。

## 4. CrossCheck — 需要跨方向检查

CX-1: API Registry / IDL 是否仍包含 `AdminCertificate`、`FederationCertificate`、Root/Intermediate CA、旧独立 combat CommandAction → 建议 API/IDL 方向检查 `game_api.idl.yaml`、`auth_api.idl.yaml` 与 Registry 生成内容是否已与 auth 终态一致。

CX-2: `02-command-validation.md` 中 RejectionReason 表多处旧码、debug_detail 与 special attack 等价拒绝码可能和 API Registry canonical enum 不一致 → 建议 API 方向检查所有 rejection code 的唯一枚举、脱敏映射与 SDK codegen。

CX-3: `special-attack-table.md` 未在本任务授权读取，但 command-validation/manifest 多次引用其为权威参数表 → 建议 Gameplay/API 方向检查 8 种 special attack 在 registry、table、validation、manifest 中的 cooldown/cost/range/resistance 是否一致。

CX-4: redb metrics table + Gateway 聚合是否足以替代 ClickHouse 的 90 天 MCP/security audit 查询需求 → 建议 Observability/Infra 方向检查审计日志保留、不可篡改、查询性能与合规导出路径。

CX-5: `fog_of_war=false`、`player_view=full`、Arena 全知、Spectator 延迟全图四种可见性模式之间的 mode validation 需要统一 → 建议 Gameplay/Security 方向检查 world.toml schema 与 validate_config 是否能阻止 competitive world 配置误用。

CX-6: Spawn/EntityCreation 的最终裁决会影响玩法手感、出生保护与 room cap 经济 → 建议 Gameplay 方向检查“新生实体下一 tick 才可交互”是否符合 spawn 体验与 combat counterplay。

CX-7: Wasmtime `=30.0`、fuel costing、SIMD deterministic subset 与 host cost table version 需要实测验证 → 建议 Performance/Determinism 方向检查 wasmtime 版本 pin、fuel schedule drift 与 cross-arch replay fixture。

CX-8: MCP security 文档中 Browser endpoint / Agent endpoint / WebSocket per-message signature 的具体 header、nonce、timestamp、CSRF 与 app-cert 组合可能需要威胁建模 → 建议 Security 方向检查跨 transport replay、DNS rebinding、Origin/Host/Fetch Metadata 与 signed request canonicalization。
