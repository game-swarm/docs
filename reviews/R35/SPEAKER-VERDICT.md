# R35 Speaker 裁决

## 裁决概要

**Overall Verdict: REQUEST_MAJOR_CHANGES**

Speaker 已实际读取 `/data/swarm/docs/reviews/R35/` 下全部 10 份 Phase 1 独立评审报告：

- `rev-gpt-architect.md`
- `rev-dsv4-architect.md`
- `rev-gpt-apidx.md`
- `rev-dsv4-apidx.md`
- `rev-gpt-design-economy.md`
- `rev-dsv4-design-economy.md`
- `rev-gpt-determinism-perf.md`
- `rev-dsv4-determinism-perf.md`
- `rev-gpt-security.md`
- `rev-dsv4-security.md`

未发现独立 Phase 2 补充报告文件；本裁决中的 CrossCheck 补漏来自各 reviewer 报告的 CrossCheck 小节汇总。

| Verdict | 票数 |
|---|---:|
| APPROVE | 0 |
| CONDITIONAL_APPROVE | 2 |
| REQUEST_MAJOR_CHANGES | 8 |
| REJECT | 0 |

最终裁决为 **REQUEST_MAJOR_CHANGES**。本轮问题不是单纯措辞/编号，而是多处权威源、ABI、预算模型、经济公式和安全枚举之间的结构性分叉。必须先闭合共识 Blocker 与 D-items，再进入 R36。

## 共识 Blocker（B1..B9）

### B1: API/IDL/Registry 派生链结构性漂移

- **来源 reviewer**: rev-gpt-apidx, rev-dsv4-apidx, rev-gpt-security, rev-gpt-design-economy, rev-gpt-determinism-perf CrossCheck
- **问题描述**: `api-registry.md` 自称为 IDL 生成的 API 单事实源，但 MCP 工具数、Auth 工具数、RejectionReason 数、Host Function 数、Host Function 签名、codegen.md 计数、commands 示例字段等在 Registry、mcp-tools、codegen、commands、interface、validation 之间反复漂移。典型证据包括 MCP 工具 56/57/58 并存、Auth 11/12 并存、RejectionReason 47/48 并存、Host Function 5/6 并存。
- **影响范围**: SDK codegen、MCP capability discovery、typed exception、CI `--check`、开发者复制示例、AI agent 工具可用性判断。
- **修复方向建议**: 以 IDL YAML 与 generator 输出为唯一机器权威，重新生成 `api-registry.md`，并同步 `mcp-tools.md`、`codegen.md`、`commands.md`、`design/interface.md`。所有手写计数改为生成片段或删除；CI 必须校验 IDL count == Registry header count == derived docs count == example schema validation。

### B2: `host_get_random` / RNG ABI 与派生公式不一致

- **来源 reviewer**: rev-dsv4-apidx, rev-gpt-apidx, rev-dsv4-security, rev-gpt-determinism-perf, rev-gpt-security CrossCheck
- **问题描述**: `host_get_random(sequence)` 在 Registry 中为 `u64`，在 `host-functions.md`、`04-wasm-sandbox.md`、`design/interface.md` 等位置出现 `u32`；同时 RNG seed 派生公式在 engine 与 tick-protocol 中存在拼接顺序、domain separator 表述差异。
- **影响范围**: WASM host import ABI、Rust/TS SDK binding、随机流 domain separation、replay determinism、跨语言随机序列一致性。
- **修复方向建议**: 定义唯一 `derive_rng(domain, world_seed, tick, actor/entity/source, sequence)` 规范，使用 length-delimited encoding 与明确 domain separator。`host_get_random` 参数宽度需按 D2 裁决统一后写入 IDL/Registry，并由生成器同步所有文档。

### B3: WASM fuel、wall-clock deadline、cgroup CPU 与容量推导口径冲突

- **来源 reviewer**: rev-gpt-architect, rev-gpt-determinism-perf, rev-dsv4-determinism-perf, rev-dsv4-architect CrossCheck, rev-gpt-security CrossCheck
- **问题描述**: 设计将 CPU 配额描述为 Wasmtime fuel/指令计数，容量公式又用 `PER_CORE_FUEL_RATE` 推导全局 budget；同时 sandbox cgroup 固定 `cpu.max = 250000 3000000`，per-player sandbox wall-clock deadline 又为 2500ms。1000-player 推导还假设 1000 workers，但默认 `worker_pool_max = 256`。
- **影响范围**: live tick admission、玩家公平 fuel quota、cgroup throttling 归因、timeout vs fuel_exhausted 分类、1000-player 容量声明、运维 sizing。
- **修复方向建议**: 明确三层资源口径：`wasmtime_fuel_units`（确定性计费）、`sandbox_wall_deadline_ms`（防 hang）、`cpu_cgroup_quota`（OS 防 DoS）。容量公式必须使用经 benchmark 校准的 `fuel_schedule_version -> calibrated_fuel_per_core_ms`，并说明 cgroup 是 per-worker 还是 sandbox pool 级。重写 1000-player 推导，使用默认 `worker_pool_max=256` 或显式标注需要运维调至 1000。

### B4: Phase 2a/2b HP 写入责任与 ECS R/W 矩阵冲突

- **来源 reviewer**: rev-gpt-architect, rev-gpt-determinism-perf, rev-dsv4-architect CrossCheck, rev-dsv4-determinism-perf metadata
- **问题描述**: `engine.md` 要求 Phase 2a Attack/RangedAttack/Heal 只生成 `PendingDamage`/`PendingHeal`，S15 统一归并写 HP；但 `06-phase2b-system-manifest.md` 中 S01 `command_executor` 仍声明写 `Entity(hits)` / `HitPoints`，同时 S10、S15、S22、S24 又存在多条 HP 写入路径，"unique writer" 语义被降级成不清晰的 domain-specific writer。
- **影响范围**: ECS determinism、CI R/W 静态验证、combat/heal/status effect 结算顺序、double-apply 风险、replay hash。
- **修复方向建议**: 显式拆分 `PendingDamage`、`PendingHeal`、`PendingStatusEffect`、`HitPoints`。S01 只能写 pending buffer，不得写 `HitPoints`。S15 是 combat/heal HP writer；若 S10/S22/S24 仍可改 HP，必须定义严格顺序、过滤条件、semantic domain 与 CI 规则，不能用模糊注释绕开冲突。

### B5: Persistence replay-critical 字段、TickTrace 与 RichTraceBlob 边界不一致

- **来源 reviewer**: rev-gpt-architect, rev-gpt-determinism-perf, rev-dsv4-architect CrossCheck
- **问题描述**: `05-persistence-contract.md` 一处称 TickCommitRecord 为 10 个 replay-critical 字段，另一处给出扩展结构；`api-registry.md` 又有 22 字段 TickInputEnvelope，`engine.md` 列出 deploy/rollback/admin/terminal_state 等封套字段。对象存储 RichTraceBlob 有时被描述为非 replay 必需，有时又作为正常 replay 输入或 `unreplayable` 触发条件。
- **影响范围**: deterministic replay、audit gap 判定、FDB/Object Store 分层、state checksum/hash chain、replay verifier 输入、存储实现。
- **修复方向建议**: 建立唯一机器权威 schema，并拆成三类：`TickCommitRecord`（FDB same-tx replay-critical）、`TickInputEnvelope`（collect/WASM 输入诊断）、`RichTraceBlob`（debug async）。`deterministic_replay` 不依赖 RichTraceBlob；RichTraceBlob 缺失只能标记 `audit_gap`，不得单独触发 `unreplayable`。

### B6: Deploy 流程与代码签名/hash 对象不一致

- **来源 reviewer**: rev-dsv4-security, rev-gpt-security, rev-gpt-architect CrossCheck, rev-dsv4-security CrossCheck
- **问题描述**: `swarm_deploy` 在 API Registry 中包含同步 `wasm_bytes`，而 persistence contract 描述异步 blob 上传；deploy 签名中的 `module_hash` 在安全文档中是 `Blake3(WASM bytes)`，在 persistence 中又被写作编译后 native artifact 的 hash。Registry schema 还缺少 deploy payload 的显式 `code_signature` / `certificate_id` / `version_counter` 字段或双层签名说明。
- **影响范围**: code signing、供应链完整性、object store / manifest / activation 状态机、TOCTOU、防重放、SDK deploy API。
- **修复方向建议**: 先裁定 deploy 流程（见 D4）。无论同步或异步，signed identity 必须固定为 `wasm_module_hash = Blake3(canonical WASM bytes)`；compiled artifact 使用独立 `compiled_artifact_hash`，不得复用 `module_hash`。Registry 明确请求签名与代码签名的双层模型。

### B7: 经济权威公式与默认参数会改变资源曲线

- **来源 reviewer**: rev-gpt-design-economy, rev-dsv4-design-economy, rev-dsv4-apidx CrossCheck
- **问题描述**: 存储税 tiered 公式量纲错误会把税额放大 100 倍；`global_storage_capacity` 在 world.toml 示例为 100,000，而 Resource Ledger/API Registry/Balance Sheet 等为 1,000,000；Empire Upkeep 在 Resource Ledger 与 Rhai 示例默认参数相差约 10×；存储税均衡证明为空壳。
- **影响范围**: anti-hoarding、anti-snowball、2–10 房间自维持区间、50 房软上限、Vanilla/Standard 默认经济曲线、服主配置。
- **修复方向建议**: 修正存储税量纲公式并保持 75% 示例为 105/tick；统一 `global_storage_capacity=1,000,000` 或按用户裁决更新所有源；将 Rhai empire-upkeep 默认参数校准到 Resource Ledger 或明确其非官方示例；补充 storage tax equilibrium proof 或登记为 playtest-gated 的参数校准项但保留目标状态语言。

### B8: Transport audience / WebSocket per-message 认证合同分叉

- **来源 reviewer**: rev-dsv4-security, rev-gpt-security, rev-dsv4-apidx CrossCheck
- **问题描述**: Transport audience 标签在 `api-registry.md`、`auth.md`、`09-command-source.md`、`03-mcp-security.md` 中集合不同（如 `browser-http`、`browser-ws`、`wasm-sdk`、`replay-viewer` 缺失/独有）；WebSocket per-message MAC/signature payload 在 auth/security 与 Registry 中字段不同，`seq == last_seq + 1` 与 `seq > last_seq` 语义冲突。
- **影响范围**: 应用层证书签发/验证、跨 transport 重放防护、Browser WS/Agent/CLI/WASM SDK 互通、confused deputy、审计。
- **修复方向建议**: 以 IDL/Registry 为机器权威补齐 transport enum，并让所有安全文档引用同一枚举。统一 WS canonical payload 为包含 direction、session_id、seq、tick、body_hash 的格式，明确 direction 独立计数、严格递增、失败断开+审计，不复用 HTTP request signature 的简化描述。

### B9: Special attack core/custom 边界与 Leech/Fabricate 规范不闭合

- **来源 reviewer**: rev-gpt-architect, rev-dsv4-architect, rev-gpt-apidx, rev-dsv4-design-economy CrossCheck
- **问题描述**: 8 种 special attack 同时被写作 core CommandAction、CustomActionRegistry 路由和 manifest handled commands。Leech/Fabricate 缺少与 Hack/Drain/Overload 等同等级的校验小节；Drain/Fabricate 示例字段与 Registry schema 不一致；Fabricate 抗性在同一文档中 EMP/Psionic 冲突。
- **影响范围**: CommandAction IDL、SDK discriminated union、World Action Manifest、status effect pipeline、special attack counterplay、validation/replay。
- **修复方向建议**: 按 D3 裁决确定 core vs custom。若采用 core 方案，则 8 种 special attack 全部为 core enum，CustomActionRegistry 仅用于第三方/world mod 扩展；新增 Leech/Fabricate 独立校验小节并引用 canonical special-attack table；所有示例字段纳入 IDL 或删除。

## CrossCheck 补漏发现

无独立 Phase 2 补充报告。本轮补漏来自 10 份 Phase 1 报告的 CrossCheck 小节：

| ID | 来源 | 目标方向 | 补漏内容 | 处置建议 |
|---|---|---|---|---|
| CX1 | API/DX | Core/Engine | `host_get_random` sequence 宽度需查 IDL 权威 | 纳入 B2 / D2 |
| CX2 | API/DX | Economy | `09-snapshot-contract` 中 GlobalDeposit/GlobalWithdraw 与 Registry/commands 的 TransferToGlobal/FromGlobal 参数不一致 | Medium 直接修复：经济操作名与延迟/费率统一到 Resource Ledger/Registry |
| CX3 | API/DX | Core/SDK | Pipeline 错误 `InvalidJson`、`SchemaViolation` 是否进入 SDK typed exception | Medium：定义 pipeline error 与 canonical rejection enum 边界 |
| CX4 | Determinism | Security | Rhai mod 是否可绕过 ECS 调度直接修改 IndexMap | 与 `direct_ecs_writer` capability 一并审查 |
| CX5 | Determinism/Security | Runtime | deterministic SIMD opt-in 缺跨 ARM/x86 验证矩阵 | Medium：标记 benchmark/test-gated，默认禁用保持安全 |
| CX6 | Determinism | Ops/Storage | FDB staging GC 10s 是否能在 1000-player 积压下保持 <15s | Medium：补 FDB key layout、GC throughput 与 conflict range |
| CX7 | Design/Economy | Core/Engine | Allied Transfer 是否绕过 Resource Ledger delay 管线 | High：与 transfer gateway 统一入口一并验证 |
| CX8 | Design/Economy | Security | Drone 消息机制可能成为非正式 OTC 市场底层 | Medium：确认消息 payload 不能绕过 Resource Ledger 结算 |
| CX9 | Security | Ops/Infra | 多存储 credential / network policy 未统一 | Medium：后续 Ops/Infra 评审覆盖 |
| CX10 | Architect | Docs/Speaker | 多个权威引用文件未纳入某些方向白名单 | Medium：R36 前修正任务模板/白名单与文档索引 |

## 方向专属 High

### Architect

| ID | 来源 | 问题 | 处置建议 |
|---|---|---|---|
| A-H1 | rev-dsv4-architect | Refund credit deploy-reset 时序窗口：MANIFEST_COMMIT 与 activation tick 描述导致旧 credit 可跨模块携带 | High 直接修复：清零触发点改为 MANIFEST_COMMIT 同事务；定义 session_id 生命周期 |
| A-H2 | rev-gpt-architect | Entity creation visibility：Build immediate vs Spawn pending queue 与全局 pending flush 规则冲突 | High/Medium：定义 `visible_same_tick` / `interactable_same_tick` 合同；倾向所有 creation pending，必要时用 `ReservedTile` |

### API/DX

| ID | 来源 | 问题 | 处置建议 |
|---|---|---|---|
| API-H1 | rev-gpt-apidx | Registry 内部 SwarmError / JSON-RPC 错误 envelope 双定义 | High/Critical：采用唯一 wire contract，建议标准 JSON-RPC numeric `error.code` + `error.data.rejection_reason` |
| API-H2 | rev-gpt-apidx | CommandAction 示例字段与权威 schema 冲突（Spawn/Build/body_parts/object_id 等） | High：所有示例由 IDL 示例块生成或 CI schema-validate |
| API-H3 | rev-gpt-apidx | Rhai `actions.*` API 缺返回类型/错误类型合同 | Medium/High：定义 `Result<T, RhaiActionError>`、错误枚举与 buffer 行为 |

### Design/Economy

| ID | 来源 | 问题 | 处置建议 |
|---|---|---|---|
| DE-H1 | rev-gpt-design-economy | New Player Transfer Lock 方向语义冲突：禁发送/禁接收/双向锁并存 | High：定义唯一 canonical 语义，倾向 player↔player 双向锁，local↔global 自身转换不受影响 |
| DE-H2 | rev-gpt-design-economy | Active alliance 上限 5 vs 10 冲突 | D-item（D7）：需用户裁决联盟经济规模 |
| DE-H3 | rev-dsv4-design-economy | Vanilla 起始资源 Energy only vs Energy+Minerals/Matter 冲突 | D-item（D6）：需用户裁决默认资源模型 |
| DE-H4 | rev-gpt-design-economy | 指定评审 spec 路径不存在，task 白名单与实际文件编号漂移 | High：修复任务模板/文档索引，必要时重跑受影响方向 |

### Determinism / Performance

| ID | 来源 | 问题 | 处置建议 |
|---|---|---|---|
| DP-H1 | rev-dsv4-determinism-perf | 1000-player 容量推导假设 1000 workers，但默认 worker_pool_max=256 | 已并入 B3；重写推导或标注部署前提 |
| DP-H2 | rev-gpt-determinism-perf | canonical JSON 文档额外引入 NFC normalization，与 RFC 8785/JCS 不一致 | Medium/High：以 JCS 为唯一规则；若需 NFC，作为 schema validation 或 codec version 前置 pass |
| DP-H3 | rev-gpt-determinism-perf | GlobalTickCommit 语义疑似超出 FDB 单事务能力边界 | Medium/High：定义 manifest-only publish、事务大小、conflict range 与 200 rooms p99 budget |

### Security

| ID | 来源 | 问题 | 处置建议 |
|---|---|---|---|
| S-H1 | rev-gpt-security | CVE/SLA 指定路径 `08-cve-sla.md` 缺失，与实际 `CVE-SLA.md`/引用路径不一致 | High：统一 canonical 路径并确保任务模板、文档引用和索引一致 |
| S-H2 | rev-gpt-security | CSR admission control 内部冲突：多层 per-IP/per-ASN/global queue vs “PoW 自身限速、无额外 IP 限制” | High：CSR 提交必须引用 L1-L6 多层准入链，不重复声明冲突数值 |
| S-H3 | rev-gpt-security | PoW 默认难度 24 bits vs Registry 20 bits | High：统一默认值；推荐 24 bits，或重新评估 20 bits 防滥用模型 |
| S-H4 | rev-gpt-security | WASM sandbox netns 文档自相矛盾 | High：统一为独立 netns 无接口/无路由 + seccomp 禁 socket 双层防护 |
| S-H5 | rev-dsv4-security | CSR 阶段 email 明文传输风险 | High：证书签发后通过已认证 `swarm_bind_email` 绑定，或在 trust response 中提供加密公钥 |

## Medium / Low 处置

| ID | Severity | 项目 | 建议处置 |
|---|---|---|---|
| ML-1 | Medium | `09-snapshot-contract` 经济操作命名 GlobalDeposit/Withdraw vs TransferToGlobal/FromGlobal | 直接闭合修复，统一命名与参数权威源 |
| ML-2 | Medium | `codegen.md` 手写计数导致持续漂移 | 直接闭合修复，删除硬编码或纳入 generator |
| ML-3 | Medium | Rhai capability 13 vs 12、`direct_ecs_writer` 边界不清 | 与 B9/安全边界一并修复 |
| ML-4 | Medium | PvE 掉落表与 Ledger PvEAward tier 数值不一致 | 直接闭合修复，modes 引用 Ledger tier 或新增 tutorial tier |
| ML-5 | Medium | Resource Ledger 出现 float multiplier | 直接闭合修复为 bp/ppm 定点类型 |
| ML-6 | Medium | Storage tax equilibrium proof 空壳 | 补数学推导；参数校准可 playtest-gated，但机制目标需闭合 |
| ML-7 | Medium | FDB challenge TTL “自动清理”未定义 | 直接闭合修复，定义 GC worker 扫描周期与批量删除边界 |
| ML-8 | Medium | Refresh token grace IP/UA 异常阈值未定义 | 直接闭合修复，定义 IP prefix/ASN/UA/geo jump 规则 |
| ML-9 | Medium | MCP HTTP body 5MB vs wasm_module blob 64MB | 直接闭合修复，区分 `max_wasm_upload_bytes` 与内部 blob cap |
| ML-10 | Medium | Snapshot cap 与 COLLECT timeout 交互未分析 | 直接闭合修复，在 tick-protocol 时序中说明 truncation 计入 COLLECT |
| ML-11 | Medium | IndexMap 动态插入确定性依赖 ECS 顺序但未桥接 | 直接闭合修复，写明 ECS system order + StableEntityId 保证插入顺序 |
| ML-12 | Medium | EXECUTE 400/50ms 预算是目标还是硬超时措辞不一 | 直接闭合修复，统一为性能目标，硬截止由 tick deadline 控制 |
| ML-13 | Medium | `omitted_count` training 模式调试精度 | Deferred/可选：按 detail_level 定义分桶/精确值 |
| ML-14 | Low | MVP/Phase/playtest 阶段措辞残留 | 直接闭合文案修复；不改变机制设计 |
| ML-15 | Low | Markdown 相对链接从 design/ 指向 specs/ 路径错误 | 直接闭合修复并加 link check |

## D-items

### D1: API error envelope wire contract

- **背景**: `api-registry.md` 内部出现两套错误合同：`error.code` 为 canonical string，或标准 JSON-RPC numeric `error.code` + `error.data.rejection_reason`。这是 SDK typed exception 的基础合同，不能两者并存。
- **方案A: 标准 JSON-RPC envelope** — 推荐。`error.code` 使用 numeric range（如 `-32000`），canonical enum 放在 `error.data.rejection_reason`；SDK 只从 `data.rejection_reason` 生成 typed exception。
- **方案B: 非标准 string `error.code`** — 不推荐。typed exception 直观，但破坏 JSON-RPC 客户端兼容性，且与后文标准 JSON-RPC 描述冲突。
- **Speaker 推荐**: A。理由：保留 JSON-RPC 兼容性，同时通过 `rejection_reason` 提供强类型错误；更适合 MCP/SDK 多客户端生态。

### D2: `host_get_random(sequence)` 参数宽度

- **背景**: Registry 为 `u64`，多个派生文档为 `u32`。这是 WASM ABI breaking choice。
- **方案A: 统一为 `u64 sequence`** — 推荐。以 Registry/API ABI 为权威，保留充足 domain space；Rust 绑定自然，TS SDK 明确使用 bigint 或安全 wrapper。
- **方案B: 统一为 `u32 sequence`** — 可行但不推荐。ABI 更小、JS number 更方便，但压缩随机 domain，且需要回改 Registry。
- **Speaker 推荐**: A。理由：RNG ABI 应面向长期 replay/domain separation 安全；JS 易用性可由 SDK wrapper 解决，不应压缩底层 ABI。

### D3: Special attack core vs custom 建模

- **背景**: 8 种 special attack 已被多轮设计认定为核心目标，但 R35 文档仍混用 core CommandAction 与 CustomActionRegistry。
- **方案A: 8 种 special attack 全部作为 core CommandAction enum** — 推荐。CustomActionRegistry 仅用于第三方/world mod 扩展；World Action Manifest 记录启用参数/handler hash，但不改变其核心身份。
- **方案B: 只保留 `CustomAction { type, payload }`，8 种 vanilla special attack 也由 manifest 注册** — 不推荐。扩展性强，但削弱 core IDL 类型、SDK discriminated union 和“8 种目标设计”的清晰度。
- **Speaker 推荐**: A。理由：符合既有“核心机制=最终设计直接写入文档”的原则，降低 SDK/codegen 与 validation 分叉。

### D4: Deploy upload flow

- **背景**: API Registry 当前像同步 `wasm_bytes` RPC，persistence contract 当前像异步 blob upload，两者不能并存。
- **方案A: 同步 `swarm_deploy(wasm_bytes, metadata, code_signature...)`** — 推荐。服务端在请求内计算 `wasm_module_hash` 并提交 manifest；object store 写入可后台 best-effort/状态化，但 signed identity 是 WASM bytes。实现简单、TOCTOU 少。
- **方案B: 异步两阶段 upload URL + manifest submit** — 不推荐作为默认。适合大模块/复杂上传，但需要新增 `swarm_get_upload_url`、blob reference、预签名 URL、TOCTOU/GC 处理。
- **Speaker 推荐**: A。理由：当前 WASM upload cap 只有 5MB，单 RPC 足够；同步模型更容易保证签名对象、manifest 对象和激活对象一致。

### D5: CSR email binding 时机

- **背景**: `swarm_submit_csr` 可带 email，但 CSR 发生在证书签发前；若支持 HTTP/无 TLS 场景，email 可能明文暴露。
- **方案A: CSR 不接收 email，证书签发后用已认证 `swarm_bind_email` 绑定** — 推荐。
- **方案B: CSR email 字段使用服务端加密公钥加密，`swarm_get_server_trust` 返回 encryption public key** — 可行但更复杂。
- **Speaker 推荐**: A。理由：最小化未认证入口 PII，避免在 bootstrap 阶段引入额外加密公钥分发和错误处理。

### D6: Vanilla 默认起始资源模型

- **背景**: Resource Ledger/Balance Sheet/API Registry 写 `{Energy: 5000, Minerals: 2000}`，gameplay 的 Official Vanilla Ruleset 写单一 `Energy`，world.toml 示例又使用 `Matter`。
- **方案A: 单一 Energy** — 推荐。修改 Resource Ledger、Balance Sheet、API Registry 的 `starting_resources` 为 `{Energy: 5000}`，移除 Minerals/Matter 默认引用；多资源留给 mod/advanced worlds。
- **方案B: Energy + Minerals（或 Matter）** — 不推荐作为默认。需更新 Official Vanilla Ruleset，并裁定 Minerals vs Matter 命名；提升新手经济复杂度。
- **Speaker 推荐**: A。理由：Vanilla/Golden Path 应最小化资源维度；多资源可作为 world/mod 扩展，不应污染默认学习曲线。

### D7: Active alliance 上限

- **背景**: gameplay 写每玩家最多 5 个 active alliance，API Registry/economy limits 写 10。该值直接影响 Allied Transfer 网络密度与联盟输血能力。
- **方案A: 上限 5** — 推荐。更新 IDL/Registry 为 5，保持联盟网络稀疏，降低联盟经济绕过 anti-snowball 的风险。
- **方案B: 上限 10** — 不推荐，除非补充更强的联盟输血限制/证明。外交空间更大，但会显著放大资源互助网络。
- **Speaker 推荐**: A。理由：Restricted Allied Transfer 的设计目标是有限互助而非大规模联盟仓储；5 更符合 anti-snowball 与 no-teleport 约束。

## R36 入场条件

R36 前必须满足以下条件：

1. **B1 Registry/IDL 生成链闭合**：重新生成 Registry 与派生文档，CI 能证明计数、签名、示例 schema 一致。
2. **B2/B3 ABI 与预算模型闭合**：`host_get_random` ABI、RNG 派生函数、fuel/wall-clock/cgroup 三层模型、worker pool 容量推导统一。
3. **B4/B9 ECS 与 special attack 边界闭合**：Phase 2a 不直接写 HP；8 special attack 的 core/custom 身份、Leech/Fabricate 校验、canonical 参数表统一。
4. **B5/B6 persistence/deploy 闭合**：TickCommitRecord/RichTraceBlob/replay-critical schema 与 deploy hash/upload/signature 流程统一。
5. **B7 经济数学闭合**：存储税公式、容量、upkeep 默认参数、起始资源、联盟上限等权威值统一；未决 D-items 已由用户裁决并落文档。
6. **B8 安全认证闭合**：transport audience、WS payload、CSR admission/PII、PoW 默认值、sandbox netns、CVE/SLA 路径统一。
7. **任务模板/白名单闭合**：不存在指定评审文件缺失或编号漂移；所有被文档称为权威源的文件能被审查任务覆盖。

## 评审统计（5 方向 × 2 model verdict 矩阵）

| 方向 | GPT-5.5 | DeepSeek V4 Pro | 合并判断 |
|---|---|---|---|
| Architect | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Design/Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Determinism/Performance | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |

## 最终裁决

**REQUEST_MAJOR_CHANGES**

- 共识 Blocker：9
- Direction 专属 High：14
- Medium/Low 批量处置项：15
- D-items：7

Speaker 不替用户裁决 D-items。下一步建议先逐项裁决 D1..D7，再启动 R35 fix wave；修复后重新运行 closure verification，而不是直接进入 R36。