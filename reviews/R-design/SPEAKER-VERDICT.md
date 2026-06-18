# Swarm R-design — Speaker 共识裁决

## 一、裁决概要

本轮为 R-design clean-slate 设计评审，评审输入为 `/data/swarm/docs/design/README.md`、`auth.md`、`engine.md`、`gameplay.md`、`interface.md`、`modes.md`、`tech-choices.md` 七份设计文档。14/14 评审报告均已产出并纳入综合：7 个方向（Architect / Security / Designer / Determinism / Economy / Performance / API-DX）× 2 个模型（GPT-5.5 / DeepSeek V4 Pro）。

**总体 Verdict: REQUEST_MAJOR_CHANGES**

收敛判断：

- 设计愿景与核心方向获得广泛认可：WASM-only gameplay path、MCP 作为管理/观察界面、deferred command、ECS tick、应用层证书、确定性 replay、Rhai 可信规则层、World/Arena 分离，均被多名评审视为正确方向。
- 但当前文档尚未达到可冻结实现的合同完整度。多数 Critical/High 并非“游戏不可行”，而是关键边界没有冻结、跨文档合同互相矛盾或容量模型不自洽。
- GPT 系列 6/7 给出 `REQUEST_MAJOR_CHANGES`；DeepSeek 系列 7/7 给出 `CONDITIONAL_APPROVE`。分歧不是方向性否定，而是对“实现前必须修正多少合同空洞”的门槛不同。
- Speaker 裁决按保守实现门槛处理：存在多方向、多模型交叉确认的 Critical/High 问题，因此本轮不能进入实现冻结。

Freeze 状态：**未冻结**。进入下一轮前应先关闭下列共识 Blocker，尤其是 ABI/Command/Replay、sandbox/host function、tick/FDB/容量预算、auth/nonce/transport、Rhai/Tier 边界五类合同。

---

## 二、共识 Blocker

### 🔴 B1 — 玩家 API / Wire Format / Command / Replay 输入封套未冻结

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| API-DX | rev-dsv4-apidx | C2, H4, M1 |
| API-DX | rev-gpt-apidx | A1, A2, A6, A7 |
| Determinism | rev-gpt-determinism | A1, A7 |
| Determinism | rev-dsv4-determinism | D2, D7 |
| Architect | rev-gpt-architect | A7 |
| Security | rev-gpt-security | H8 |

**问题**：同一条玩家 WASM 与引擎交互链路中同时出现 JSON、结构化数据、FlatBuffers、CommandIntent、typed SDK object 等多种描述；Command schema、RejectionReason、WorldSnapshot、host function ABI、MCP error envelope、TickInputEnvelope 均未形成一个唯一权威合同。Replay 所需的完整输入集合也未冻结：module_hash、生效 tick、wasm_status、timeout/trap/fuel exhausted、deploy/rollback/admin events、snapshot_hash、raw_commands canonical order 等缺失。

**裁决**：这是本轮最强的跨方向共识 blocker。没有 B1，SDK、WASM sandbox、MCP、replay、TickTrace、state_checksum 都无法稳定实现。

**修正要求**：

- 创建或补齐一个权威 `game_api.idl` / `command-schema`，冻结 Command enum、字段、验证规则、RejectionReason、canonical ordering。
- 明确三层格式：hot path binary canonical/FlatBuffers；SDK typed object；JSON 仅为 debug/compat，不作为权威 replay 或 WASM ABI。
- 定义 `WorldSnapshot`、`SnapshotWireFormat`、`CommandWireFormat`、host function 输出 ABI（字节序、对齐、buffer 上限、error code）。
- 定义 `TickInputEnvelope`，每 tick 持久化 replay 的完整权威输入，包括 module/version/effective_tick、wasm_status、fuel、snapshot_hash、commands_hash、deploy/admin events、world_config_hash、mods_lock_hash、engine_abi_version、wasmtime_version。
- 定义统一 `SwarmError` / JSON-RPC error envelope，并给出 retry/idempotency/rejection 区分。

---

### 🔴 B2 — Sandbox 生命周期、WASM 确定性边界与 Host Function 成本模型不闭合

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Architect | rev-gpt-architect | A1 |
| Performance | rev-gpt-performance | A3, A5 |
| Security | rev-gpt-security | H3, H4 |
| Determinism | rev-gpt-determinism | A2, A9 |
| API-DX | rev-dsv4-apidx | H4 |
| Architect | rev-dsv4-architect | M3 |
| Security | rev-dsv4-security | M4 |
| Performance | rev-dsv4-performance | D2 |

**问题**：文档一处写 per-tick fork/kill，另一处写 WASM instance pool；这不仅是实现细节，而是安全隔离、性能预算、tick 间状态、memory reset、WASI capability、fuel reset、replay 兼容的核心合同。Host functions（尤其 `host_path_find`、objects-in-range、world rules）被说成“只读且计入 fuel”，但 Wasmtime fuel 不会自动覆盖 host Rust 侧 CPU/内存/路径搜索成本。

**裁决**：必须在实现前冻结 sandbox threat model 与 lifecycle。当前状态会导致安全实现、性能实现、确定性实现各走一套。

**修正要求**：

- 二选一并写为唯一权威：`long-lived sandbox worker pool + per-tick clean Store/Instance reset`，或 `per-tick process fork/kill`。若采用 pool，删除/修正 per-tick fork 文案。
- 明确 WASI 默认关闭；禁 clock/random/filesystem/network/env/process；threads/atomics/SIMD 规则固定；Wasmtime version 与 target features 固定。
- 定义 worker/process/uid/cgroup/seccomp/AppArmor/Landlock/rlimit 边界、OOM/timeout/trap 后替换策略、max ticks before recycle。
- 对每个 host function 定义 per-tick call limit、max output bytes、max pathfinding nodes、range、CPU cost units、fuel/host_call_budget 扣减、确定性错误码。
- Pathfinding 必须冻结算法或至少冻结 neighbor order、cost type、tie-break、cache key、cache hit/miss 等价性。

---

### 🔴 B3 — Tick deadline、Tier1 容量、Snapshot、FDB commit 与存储预算数字不自洽

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Performance | rev-gpt-performance | A1, A2, A4 |
| Performance | rev-dsv4-performance | D1, D2, D4, D6, D10 |
| Economy | rev-gpt-economy | A1 |
| Architect | rev-gpt-architect | A5 |
| Determinism | rev-gpt-determinism | A4 |
| Architect | rev-dsv4-architect | AR-2, AR-3 |
| Determinism | rev-dsv4-determinism | D5 |

**问题**：文档同时给出 Tier1 `50 players × 10 drones = 500 total`、`500 active players`、`50,000 total drones/entities`、`snapshot per-player 256KB`、`snapshot total 128MB`、`全量 Bevy snapshot ≤16MB/tick`、FDB transaction limit 16MB、World tick 3s/COLLECT 2500ms/WASM per-player 2500ms 等数字。这些数字不是同一套容量模型。若按最坏路径理解，tick deadline、FDB commit、TickTrace 留存和运维成本都会失控。

**裁决**：必须先重算性能/容量模型，不能把 16MB FDB limit 或 128MB snapshot 当成模糊预算。B3 同时影响架构、经济、确定性和性能。

**修正要求**：

- 冻结唯一 Tier1 capacity contract：active_players target/hard cap、active_drones/entities target/hard cap、rooms_loaded、visible_rooms p95、snapshot bytes p50/p95/max、commands max、pathfinding requests max。
- 改为 deadline-driven tick pipeline，明确 snapshot build、sandbox dispatch/execution、command collect、execute、commit、broadcast、slack 的 p50/p95/p99 预算与超时降级。
- 明确 sandbox deadline：到截止未返回的玩家本 tick 产生 deterministic no-op / timeout rejection，不拖延整个 tick。
- 定义 `TickCommitProtocol`：state_delta、TickTrace、metrics、keyframe、object storage pointer 哪些权威；超过大小上限时 deterministic fail-safe 或降级；chunking 必须有 canonical order 与 commit marker。
- FDB 每 tick事务不应承载大 blob；建议 FDB 存 head/manifest/hash/pointer，小事务推进 world head，大型 TickTrace/keyframe 进入对象存储或 append-only log。
- 加入 TickTrace/keyframe retention 与热/冷存储成本表（7/30/180 天）。

---

### 🔴 B4 — Auth / Nonce / Transport / Admin Recovery / 授权矩阵合同不完整

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Security | rev-gpt-security | C1, H2, H5, H8 |
| Security | rev-dsv4-security | C1, H1, H4 |
| Performance | rev-dsv4-performance | D1, D3, D6 |
| Architect | rev-gpt-architect | A4 |
| Architect | rev-dsv4-architect | H1 |
| API-DX | rev-dsv4-apidx | H1, H5 |

**问题**：应用层证书模型方向正确，但多个安全边界未冻结或互相矛盾：HTTP/不可信代理场景与 WebSocket 握手后免签名冲突；Dragonfly nonce 被用于热路径但崩溃后 TTL 窗口可重放；部分 mutation/admin/recovery 是否持久消费 challenge 不清；管理员恢复流程可能把 `reset_url` 返回给管理员；MCP/REST 工具缺逐方法授权、scope、owner、visibility、rate limit、replay class 矩阵；auth 状态在 FDB/Dragonfly/Gateway/Auth Service/Engine 间权威边界不清。

**裁决**：这是安全与实现边界 blocker。当前文本会让实现者在认证、重放、防越权、admin recovery 上作出不一致解释。

**修正要求**：

- 明确生产默认 HTTPS/WSS；若支持 HTTP/WS，必须有应用层帧完整性/加密、sequence number、server push 签名，不能使用“握手后免签名”的绝对规则。
- 为每个 MCP/REST/WS 方法标注 replay class：read_replay_safe / idempotent_mutation / non_idempotent_mutation / admin_critical。
- Dragonfly nonce 仅用于 read-only replay-safe 查询；所有 mutation/admin/recovery/revoke/deploy/federation/cert issuance 必须使用 FDB version counter、idempotency key 或一次性 challenge，并在事务内消费。
- 生成 `authz_matrix.md` 或 IDL annotations：required_usage、scope、resource_owner、visibility_filter、rate_limit、admin_override、additionalProperties=false。
- Admin recovery 只创建 pending recovery record；恢复链接不得直接返回给管理员，应发送给用户已验证邮箱或 out-of-band 用户验证通道；离线部署需双 admin + 用户短码/签名 challenge。
- 明确 Auth Service / Gateway / Engine 的权威边界：Auth 负责证书/CRL/recovery/session；Gateway 负责 transport、canonicalization、验签、rate limit、Principal 注入；Engine 只消费最小化 principal/certificate snapshot。

---

### 🔴 B5 — Rhai 规则模组、Tier/MVP、默认规则集与扩展 API 边界未冻结

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Architect | rev-gpt-architect | A3, A6 |
| Determinism | rev-gpt-determinism | A5 |
| API-DX | rev-gpt-apidx | A3 |
| Architect | rev-dsv4-architect | H2, H5 |
| Performance | rev-dsv4-performance | D5 |
| Security | rev-gpt-security | H9 |
| Security | rev-dsv4-security | H3 |
| Designer | rev-gpt-designer | G3 |

**问题**：文档一方面强调世界规则高度可配置，另一方面又要求 Tier1 Core IDL 冻结；Leech/Fabricate 等能力在某处是 Tier2+，另一处又出现在默认 world.toml；Rhai 模组可信但可回滚，但多模组执行顺序、action log、rollback 范围、可见性、全局视角、AST 超限后事件/metrics/resource side effect 是否回滚均未闭合。供应链侧 `mods.lock` checksum 可选且 Rhai 在引擎进程内运行，扩大风险。

**裁决**：B5 是实现范围与可扩展性 blocker。若不冻结，SDK manifest、world-specific SDK、Core IDL、mods.lock、replay、security review 都无法稳定。

**修正要求**：

- 写唯一 Capability Matrix：Core IDL v1、Vanilla v1 default、Tier1 parameterized core actions、Tier2 extension actions、Future/RFC，逐项列出。
- Leech/Fabricate 等争议能力必须二选一：进入 Core/Vanilla v1，或从默认 world.toml 示例移除并标注 future。
- Rhai 模组采用 deterministic action log 模型：read-only snapshot → produce action log → validate logs → deterministic merge → apply once。
- Mod order 固定为 dependency topo sort + stable name/revision tie-break；state iterator order 固定；超限 rollback 包括 action log、events、metrics、resource deductions。
- 区分 RuleMod 全局规则视角与 PlayerVisibleScript 可见性过滤，不要让经济/维护费模组受 player fog-of-war 影响。
- `mods.lock` 必须包含 immutable commit hash 与 content hash，启动 hash mismatch 应拒绝加载而非告警。

---

### 🔴 B6 — Snapshot / Visibility / Truncation / Overload 感知边界不明确

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Performance | rev-dsv4-performance | D2, D9 |
| Security | rev-dsv4-security | H2, M7 |
| Determinism | rev-gpt-determinism | A8, A10 |
| Determinism | rev-dsv4-determinism | D6 |
| Architect | rev-dsv4-architect | C2 |
| Economy | rev-gpt-economy | A7 |
| API-DX | rev-gpt-apidx | A9 |
| Performance | rev-gpt-performance | A1, A5 |

**问题**：Tier1 声明 `Snapshot per-player = 256KB`，但超过 cap 时是 deterministic truncation、分页、拒绝该玩家 tick、还是降级 detail 未定义。可见性和 Overload 校验在 Phase1 snapshot 与 Phase2a 当前世界状态之间有语义差异；MCP/Web UI/WASM 三种视野边界不够硬。Snapshot cap 还会产生经济外部性：敌方/NPC/建筑堆叠可能让受害者的 snapshot 超限。

**裁决**：B6 与 B1/B3/B4 相互依赖，但需要独立闭合，因为它直接影响游戏公平、replay、AI 观察输入、隐私和性能。

**修正要求**：

- 定义 `SnapshotBuildResult`：正常、truncated、over_budget_rejected 的精确语义。
- 若截断，必须使用固定 priority bucket + stable id order，并暴露 `snapshot.truncated=true`、`omitted_counts`、bucket 统计；不得依赖 ECS query 原始顺序。
- 若拒绝，必须写入 TickInputEnvelope，玩家输出 deterministic empty/no-op/rejection。
- 明确 WASM snapshot 始终受 fog_of_war 过滤；MCP/Web UI 的 player_view/spectate 不能改变 WASM 输入。
- Overload/visibility 若使用 Phase2a 当前 World 状态，应在 gameplay 与 engine 中显式声明；若冻结 tick-start snapshot，也要接受相应玩法后果。
- 将可见实体造成的 snapshot 压力纳入 room/entity cap、density tax、attacker cost 或 anti-abuse 策略。

---

### 🟠 B7 — Vanilla World 经济与首小时产品默认体验尚未成为可验证闭环

| 方向 | 评审员 | 原始 ID |
|---|---|---|
| Economy | rev-gpt-economy | A2, A3, A4, A5 |
| Economy | rev-dsv4-economy | E1, E2, E3 |
| Designer | rev-dsv4-designer | G1, G2, G5 |
| Designer | rev-gpt-designer | G1, G2, G5, G6 |
| API-DX | rev-gpt-apidx | A4, A5 |
| Architect | rev-gpt-architect | A3 |

**问题**：World 经济默认规则存在多处设计立场不清：empire upkeep 是 Phase1+ deferred 还是 Vanilla 核心；累进存储税单位可能被理解为每 tick 百分比导致资产小时级蒸发；PoW 成本不足以防 free-farm/Sybil；Faucet/Sink/Transfer/Lockup 总账缺失；Market 多处被引用但又是 Phase2；默认资源体系在单 Energy 与多资源示例间摇摆。设计师方向还指出首小时可玩路径、AI-only MCP onboarding、PvE 纯农弱支配策略和长期非扩张成就不足。

**裁决**：B7 不否定游戏机制，但阻塞“默认 Vanilla 可玩性”和经济实现。若只作为研究原型可降为 High；若目标是可上线 World/Arena 默认规则，则必须在 Phase1 前闭合。

**修正要求**：

- 写 Vanilla World v1 economic ledger：每项规则标注 Faucet / Sink / Transfer / Lockup / Unlock，并给出目标资源总量日增长区间。
- 明确 empire upkeep 三层：protocol hook、Vanilla default 是否启用、server operator 是否可关闭/替换。
- 统一税率单位，禁止 `%/tick` 与 `每10万单位税率` 混用；给 24h 示例税负表。
- 为新账号经济产出加入闸门：前 N tick 不可转移、交易/市场解锁、PvE drop 绑定、同源账号组 quota、自适应 PoW 结合行为图。
- 定义“10 分钟有趣”golden path 和 AI agent onboarding 最短成功路径：登录、fetch SDK、编译、deploy、观察反馈、debug、第一场 Arena/PvE challenge。
- 冻结 Market Phase：若 Phase2，则 Phase1 文档不得让 economy/UI/SDK 假设市场存在。

---

## 三、方向专属 High 优先级

以下项未全部升级为共识 Blocker，但属于方向内 High 或单方向强信号，应进入修正清单或由用户裁决。

| ID | 方向 | 问题 | 裁决 | 时限 |
|---|---|---|---|---|
| S-H1 | Security | Browser refresh token / certificate material 存 localStorage，XSS 后近似账号接管 | 接受为 High；改为 HttpOnly Secure cookie + WebCrypto non-extractable / OS keychain / passkey-backed；若保留 localStorage 必须写入威胁模型 | Phase1 前 |
| S-H2 | Security | Server Intermediate CA 私钥保护仅为 advisory；CA compromise 可 mint 任意证书 | 补充强制配置、启动检查、HSM/文件权限/轮换/审计合同 | Phase1 前 |
| S-H3 | Security | Code signing 技术选型中出现 Blake3 MAC，易被误实现为对称“签名” | 删除 MAC-as-signature；Blake3 仅 hash/PRNG/KDF，code signing 使用 Ed25519 CodeSigningCertificate | 立即 |
| S-H4 | Security | Argon2id login/recovery 分布式 DoS 放大 | 加全局 argon2 semaphore/worker pool、dummy PHC、adaptive PoW、fail-closed | Phase1 前 |
| A-H1 | Architect | Controller repair formula 使用 float/u32 且 cap scope 不清 | 改为定点/整数公式，明确全局 cap 或 per-controller 容量 | 立即 |
| A-H2 | Architect | Phase2b parallel systems 对 DeathMark entity 的读写语义缺失 | decay/regeneration 明确跳过 DeathMark 或重排系统；写入 engine | 立即 |
| P-H1 | Performance | Arena 300ms tick 未单独建模 FDB commit/sandbox/API 开销 | Arena 独立预算，不得继承 World 3s 模型 | Phase1 前 |
| P-H2 | Performance | MCP read/debug/replay/simulate 可能绕开 tick 热路径限流 | MCP read 分 hot/warm/cold，定义 cost units、response cap、async job/backpressure | Phase1 前 |
| API-H1 | API-DX | `swarm_sdk_fetch` 缺 input/output/error/rate-limit schema | 加入 interface 工具表，是 AI agent 自举入口 | 立即 |
| API-H2 | API-DX | MCP tool catalog 过大，缺 capability profile | 拆 onboarding/play/deploy/debug/admin profiles，`swarm_get_schema(profile=...)` 返回最小集 | Phase1 前 |
| D-H1 | Designer | 特殊攻击 Tier/default 规则冲突与渐进引导不足 | 与 B5 合并：冻结特殊攻击进入 Core/Vanilla 的范围；新手模式渐进解锁 | Phase1 前 |
| D-H2 | Designer | Replay/旁观具备基础但社区传播产品闭环不足 | 分享 URL、战报卡、highlight、自动摘要可作为 Phase2 产品项，不阻塞协议冻结 | Phase2 |
| E-H1 | Economy | 联邦资产/排名愿景与 auth identity-only 模型冲突 | 先冻结 federation identity-only；资源/排名跨世界列 Future/RFC | 立即 |

---

## 四、Medium / Low 处置建议

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---|---|
| M1 | Player shuffle seed 表述 `hash(tick_number, world_seed)` vs `Blake3(tick_number || world_seed)` 不统一 | Phase1 前 | 统一为带 endian/domain separator 的公式，如 `Blake3("shuffle" || world_seed || tick.to_le_bytes())` |
| M2 | NPC/event PRNG 缺 per-entity / named stream seeding | Phase1 前 | 为 shuffle/room_gen/npc_event/personality/drop_table 定义命名 stream 和 entity/sequence seed |
| M3 | `state_checksum` 覆盖范围不清 | Phase1 前 | 明确 WorldState、mod_state/action_log、tick_metrics、config/hash/pointer 是否进入 checksum |
| M4 | Resource amount overflow / fixed-point rounding 未定义 | Phase1 前 | 所有数值定义 overflow policy、rounding mode、saturating/checked 语义 |
| M5 | `swarm_simulate` 语义与预算未定义 | Phase1 前 | 定义是否执行其他玩家 WASM、最大 tick、资源配额、热路径隔离、determinism 声明 |
| M6 | `swarm_deploy` 幂等性与 module retention 未定义 | Phase1 前 | idempotency_key / same module_hash retry 只扣费一次；定义 module GC/retention |
| M7 | Market 占位影响 Phase1 economy/UI/API 假设 | Phase1 前 | 若 Phase2，Phase1 只能保留 RFC，不允许默认规则依赖 market |
| M8 | Federation CRL stale fallback 与 sync budget | Phase1 前 | 明确 reject_for_code/reject_all/allow_with_warning 的安全后果、缓存 TTL 与 FDB/CPU budget |
| M9 | Public spectate/replay privacy 与 anti-stream-sniping | Phase2 | 对 Arena 加 spectate_delay、private replay、visibility sanitization、share permission |
| M10 | Move-as-action 新手 UX、debug command provenance | Phase1/2 | 提供教程、解释器、command→state diff→code line 追踪；非协议 blocker 但影响 adoption |
| M11 | Drone personality / efficiency 市场价值定义 | Phase2 | 明确纯装饰，不影响 tick；若可交易需 UI 标注，避免 pay-to-win 误解 |
| M12 | Cross-room movement fatigue `+1` 语义 | Phase1 | 明确 per-exit/per-room/per-tick，写入 gameplay examples |
| M13 | ClickHouse small-batch merge pressure | Implementation | 作为性能测试/批量写入设计项，不阻塞设计合同 |
| M14 | Frontend PixiJS/Monaco 渲染目标低于后端 entity cap | Phase2 | 加前端 LOD/aggregate rendering 计划 |

---

## 五、D-items — 需要用户裁决的设计决策

| ID | 决策项 | 选项 | Speaker 建议 |
|---|---|---|---|
| D1 | Sandbox lifecycle | A. per-tick fork/kill；B. long-lived worker pool + per-tick clean Store/Instance reset | 建议 B。性能可行，但必须补强 reset/cgroup/seccomp/worker recycle 合同 |
| D2 | 不安全传输支持程度 | A. 生产只支持 HTTPS/WSS；HTTP 仅 dev；B. 支持 HTTP/WS 并做应用层 AEAD/帧签名 | 建议 A 为默认，B 作为明确 `insecure_transport=true` 的高级模式或 future |
| D3 | Leech/Fabricate 与特殊攻击范围 | A. 纳入 Core/Vanilla v1；B. 从 Tier1 默认移除，保留 Future/Tier2 extension | 若目标是冻结快，建议 B；若玩法依赖它们，必须现在补 IDL/SDK/replay 合同 |
| D4 | Vanilla World 是否默认启用 empire upkeep | A. 默认启用 protocol hook + Vanilla formula；B. 仅提供 hook，具体由模组/服主启用 | 建议至少冻结 hook 与 maintenance ledger；默认公式是否启用需用户定调 |
| D5 | Snapshot over cap 行为 | A. deterministic truncation；B. hard reject/no-op；C. pagination/streaming | WASM tick 输入建议 A 或 B，不建议 C 作为 hot path；Speaker 倾向 A + explicit truncated flag |
| D6 | Federation 范围 | A. identity-only；B. 资源/排名/资产桥接进入近期路线 | 建议 A。资源桥接会打开经济与安全复杂度，应另立 RFC |
| D7 | Market phase | A. Phase1 最小市场；B. Phase2/Future，Phase1 文档不依赖 | 建议 B，除非 Vanilla economy 明确需要 trade sink/source |
| D8 | 首小时优先级 | A. 先冻结协议/引擎，教程后置；B. Phase1 前必须有 10 分钟 playable golden path | 若目标是公开测试，建议 B；若目标是底层 prototype，可作为 Phase1 exit gate |

---

## 六、文档维护项（立即执行）

- 新增/补齐 API 合同索引页：将 Command schema、WorldSnapshot、host ABI、SwarmError、request signing、module_hash、SDK manifest、authz matrix 统一链接。
- 将所有裸 float 规则值（`0.01`、`0.05`、`0.5`、`1.0` 等）替换为定点/整数/basis points 示例，并写 canonical parser 拒绝 TOML float。
- 删除或修正 `tech-choices.md` 中 “Blake3 MAC / keyed hash 用于代码签名” 表述。
- 删除或修正 sandbox per-tick fork/kill 与 engine instance pool 的冲突描述。
- 清理 Leech/Fabricate、Vanilla world.toml、Tier1 Core IDL 三者之间的状态冲突。
- 给每个 MCP tool 增加 schema/error/rate-limit/authz/replay class，至少先覆盖 deploy、snapshot、replay、debug、economy、admin/recovery。
- 在 README 中修正 federation 愿景：若当前为 identity-only，不应暗示资源/排名已可跨世界转移。
- 给 Tier1 capacity 添加单一表格，避免 500 drones、50,000 entities、16MB/tick、128MB/tick 同时作为目标。

---

## 七、下一轮入场条件

下一轮 R-design re-review 建议在以下条件满足后启动：

- [ ] B1：Command / Snapshot / host ABI / TickInputEnvelope / error envelope 已有权威合同。
- [ ] B2：Sandbox lifecycle 与 host function cost model 已二选一并全文一致。
- [ ] B3：Tier1 capacity + tick deadline + FDB commit/storage budget 已重算并形成单表。
- [ ] B4：Transport、nonce replay class、admin recovery、authz matrix 已补齐。
- [ ] B5：Capability Matrix、Rhai action log/rollback、mods.lock supply-chain 合同已冻结。
- [ ] B6：Snapshot cap/truncation/visibility/Overload 语义已冻结。
- [ ] B7：Vanilla economy ledger、upkeep stance、tax unit、PoW/free-farm gate、market phase 已明确。
- [ ] D1-D8 用户裁决项至少给出方向，避免下一轮评审重复围绕同一开放设计分歧。

---

## 八、评审统计矩阵

| Direction | GPT-5.5 Verdict | GPT C/H/M/L | DeepSeek V4 Pro Verdict | DSV4 C/H/M/L | Speaker 备注 |
|---|---:|---:|---:|---:|---|
| Architect | REQUEST_MAJOR_CHANGES | 2 / 5 / 2 / 0 | CONDITIONAL_APPROVE | 3 / 5 / 4 / 3 | 双方同意核心架构方向正确，但边界合同未冻结 |
| Security | REQUEST_MAJOR_CHANGES | 1 / 9 / 6 / 3 | CONDITIONAL_APPROVE | 1 / 4 / 7 / 4 | 共同关注 nonce、admin recovery、Rhai/mod、CRL/federation；GPT 对 WS/transport 更严厉 |
| Designer | CONDITIONAL_APPROVE | 0 / 3 / 5 / 1 | CONDITIONAL_APPROVE | 0 / 1 / 4 / 3 | 玩法方向获认可；主要问题是 onboarding、PvE/PvP 激励、特殊攻击默认范围 |
| Determinism | REQUEST_MAJOR_CHANGES | 2 / 4 / 5 / 2 | CONDITIONAL_APPROVE | 0 / 2 / 4 / 1 | 均认为 determinism intent 强，但 replay envelope、wire format、Rhai/seed/snapshot 需闭合 |
| Economy | REQUEST_MAJOR_CHANGES | 1 / 4 / 4 / 1 | CONDITIONAL_APPROVE | 0 / 0 / 3 / 5 | GPT 将 FDB/tick 成本与宏观经济视为 blocker；DSV4 认为是校准/完整性问题 |
| Performance | REQUEST_MAJOR_CHANGES | 2 / 4 / 4 / 2 | CONDITIONAL_APPROVE | 2 / 4 / 4 / 3 | 双方高度一致：容量、tick budget、FDB/auth/cache/pathfinding 必须重算 |
| API-DX | REQUEST_MAJOR_CHANGES | 0 / 5 / 4 / 1 | CONDITIONAL_APPROVE | 2 / 6 / 6 / 2 | 双方一致要求冻结 SDK/ABI/schema/error/rate-limit/onboarding 合同 |

汇总：

- 14/14 artifacts 纳入统计，无缺位。
- Verdict 分布：`REQUEST_MAJOR_CHANGES` 6/14；`CONDITIONAL_APPROVE` 8/14；`APPROVE` 0/14。
- 严重度汇总（按 reviewer 自报/heading 统计）：Critical 16，High 56，Medium 62，Low 31。
- 共识强度：B1-B6 为跨 ≥4 方向且两模型家族均有信号的强共识；B7 为 Economy+Designer+API/Architect 交叉的中强共识，取决于项目是否要求默认 Vanilla 立即可玩。

---

## 九、Speaker 最终裁决

**REQUEST_MAJOR_CHANGES**。

Swarm 的高层设计方向没有被推翻；相反，多数评审承认其核心架构选择先进且自洽。但当前文档还混合了愿景、示例、future capability、Tier1 contract、implementation hint，多处关键数值和边界条件未形成唯一权威。若现在进入实现，最大风险不是“做不出来”，而是 SDK、sandbox、auth、replay、tick storage、经济默认规则分别按不同解释落地，后续返工成本极高。

建议下一步不是重写设计，而是做一次 **contract freeze pass**：围绕 B1-B7 创建短而硬的合同表/IDL/矩阵，删除冲突示例，明确 D-items。完成后再启动下一轮 clean-slate 评审。

### D-items 裁决结果（用户已确认，2026-06-18）

| ID | 裁决 | 记录 |
|----|------|------|
| D1 | **B** — worker pool + per-tick clean Store/Instance reset | 须补强 reset/cgroup/seccomp/worker recycle 合同 |
| D2 | **A** — 生产 HTTPS/WSS only | HTTP/WS 仅 dev；用户补充：自签名证书确认步骤 = 服务器指纹确认 |
| D3 | **保留** Leech/Fabricate，作为核心能力 | 全局元裁决：移除文档中所有 Tier/Phase 标记，设计呈现统一干净状态 |
| D4 | **A** — Vanilla 默认启用 empire upkeep | Protocol hook + Vanilla 默认公式；服主可关闭/替换 |
| D5 | **C** — 分页传输 | 理由：snapshot 给玩家仅展示用，drone WASM 决策走 fog_of_war 过滤输入；分页不影响 tick 热路径 |
| D6 | **identity-only** | 同一证书可跨世界认证；资源/排名桥接排除 |
| D7 | **移除 Market 子系统，保留扩展接口** | 新增设计项：**drone 间消息/对话机制**，实现点对点资源交换，允许欺骗（博弈论要素） |
| D8 | **B** — 实现后必须有 10 分钟 playable golden path | 登录→fetch SDK→编译→deploy→观察→debug→首次 PvE 须可走通 |

> **元裁决**：全局移除文档中所有 Tier/Phase 标记（Tier1/Tier2/Phase1/Phase2/Future/RFC 等），设计文档呈现统一干净目标状态。
