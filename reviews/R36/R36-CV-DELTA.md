# R36 CV Delta — R35 Fix Wave 增量闭合验证

**Reviewer**: Closure Verification Reviewer (DSv4/Delta)  
**Scope**: 仅验证 R35 fix wave 指定 20 个文件在 `/tmp/swarm-review-R36/` 中的增量修复正确性与新漂移。  
**Reference**: `/data/swarm/docs/reviews/R35/SPEAKER-VERDICT.md`

## Verdict

**REQUEST_CHANGES**

R35 fix wave 已修复一部分核心方向（例如 `host_get_random(sequence: u64)` 在主要 WASM host 文档中基本统一、S01 不再直接处理 combat 的意图在 system manifest 中落地、D7 alliance 上限 10 与 cap 约束已写入部分设计文档），但仍存在多处 Blocker/High 级别未闭合或因局部修改引入的新漂移。特别是 API Registry 与派生文档仍不一致，Action 模型迁移不彻底，Deploy/CSR/WS 安全合同仍保留旧语义。

## Delta 验证摘要

| R35 项 | 增量判断 | 说明 |
|---|---|---|
| B1 API/IDL/Registry 派生链漂移 | 未闭合 | MCP 工具数、RejectionReason 总数、Auth 工具数仍跨文件冲突。 |
| B2 RNG ABI | 基本闭合但有残留 | `u64 sequence` 已在主要 host function 文档统一；Registry 的 RNG 派生描述仍使用旧 `(tick_seed, player_id, drone_id, sequence)`，与 sandbox/interface 的 `derive_rng(domain, world_seed, tick, actor_or_entity_id, sequence)` 不完全一致。 |
| B3 fuel/wall/cgroup | 部分闭合 | 三层口径和 worker_pool 默认值已有修正；本轮未发现新增阻断漂移。 |
| B4 HP writer / ECS R/W | 未完全闭合 | S01 不写 HP 已修正，但 S15 “UNIQUE” 与 S10/S22/S24 同写 HitPoints 的矩阵/说明仍自相矛盾。 |
| B5 persistence / replay-critical | 部分闭合 | RichTraceBlob audit_gap 方向在 tick-protocol 中修正；本轮未发现新增阻断漂移。 |
| B6 Deploy hash/upload/signature | 未闭合 | D4 同步 deploy 裁决与 Registry/security 文档中的 async/object-store 叙述冲突；CSR/deploy payload 字段也不一致。 |
| B7 经济默认值/公式 | 部分闭合 | `{Energy: 5000}`、alliance=10 方向有落地；但 gameplay 中 world.toml 示例仍保留 `global_storage_capacity=100000`、Matter 默认资源、float-like 成本示例。 |
| B8 transport audience / WS auth | 未闭合 | Registry WS payload/seq 仍为旧合同，和 auth/security 的 canonical payload 不一致。 |
| B9/D3 Action 模型迁移 | 未闭合 | 多处仍把 combat/special action 当直接 `CommandAction` 或 `[[custom_actions]]`。 |
| ML items | 部分闭合 | 一些文案与引用修正完成，但 ML-2/ML-3/ML-5 等仍有残留。 |

## 新发现 / 未闭合问题

### R36-CV-1 — MCP 工具计数仍漂移（B1 / ML-2）

**Severity**: Blocker  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:261`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:276`
- `/tmp/swarm-review-R36/specs/reference/mcp-tools.md:5`
- `/tmp/swarm-review-R36/specs/reference/mcp-tools.md:29`
- `/tmp/swarm-review-R36/specs/reference/mcp-tools.md:42`

**Evidence**:
- API Registry 声称 `game_api.idl.yaml (57 tools)`，并在 `Game API 工具清单 (57)` 重列。
- `mcp-tools.md` 顶部仍写 `56 个 Game API 活跃工具 + 11 个 Auth API 工具`，总览表又写 `Game API 小计 56`、`Auth API 12`。
- `mcp-tools.md` 内部分组也与 Registry 不一致：Onboarding 10 vs Registry Onboarding 11；Play 16 vs Registry Play 15；Arena 4 vs Registry “1 active + RFC” 表述。

**Impact**: B1 要求工具数/派生文档闭合，本轮仍有 56/57、11/12 并存，不能证明 IDL → Registry → MCP docs 的生成链闭合。

**Required fix**: 以 IDL/Registry 机器输出为唯一权威，重新生成 `mcp-tools.md` 或删除所有手写计数；同时明确 RFC/gated tools 是否计入 active count。

### R36-CV-2 — RejectionReason 总数与 enum 边界仍漂移（B1 / CX3）

**Severity**: Blocker  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:90`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:123`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:156`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:154`
- `/tmp/swarm-review-R36/specs/reference/codegen.md:28`

**Evidence**:
- API Registry 写 `canonical code 总数为 48`，Validation 级写 `28 codes`，但表内编号为 1..27 后新增 `48 NotEligible`。
- `02-command-validation.md` 仍写权威 enum 共 `47 个 canonical code（35 game + 12 auth）`。
- `codegen.md` 只引用 Registry 计数，但没有闭合 47/48 的漂移。

**Impact**: SDK typed exception、JSON-RPC `error.data.rejection_reason` 与 validation 文档仍无法一致生成。

**Required fix**: 裁定并统一为 47 或 48；若保留 `NotEligible`，需更新所有派生文档、IDL 注释、codegen 校验和旧码映射；若不保留，应从 Registry 移除并用 `debug_detail` 表达。

### R36-CV-3 — CSR email binding 裁决未在 API Registry 闭合（D5 / S-H5）

**Severity**: High  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:402`
- `/tmp/swarm-review-R36/design/auth.md:705`
- `/tmp/swarm-review-R36/design/auth.md:762`

**Evidence**:
- D5 裁决为 CSR 不接收 email，证书签发后通过已认证 `swarm_bind_email` 绑定。
- `design/auth.md` 已写 `swarm_submit_csr` 不接受 `email`，邮箱绑定必须通过 `swarm_bind_email`。
- 但 `api-registry.md` Auth API canonical 表仍把 `swarm_submit_csr` 输入写成 `{..., email?, recovery_password?}`。

**Impact**: Registry 是 API 权威源；只要 Registry 仍暴露 `email?`，D5 的 PII bootstrap 风险未闭合。

**Required fix**: 从 Registry/Auth IDL 的 `swarm_submit_csr` 输入中移除 `email?`；统一工具名为 `swarm_bind_email` 或 `swarm_recovery_email_bind`，避免 API 名称再次分叉。

### R36-CV-4 — PoW 默认难度 24 vs 20 仍冲突（S-H3）

**Severity**: High  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:637`
- `/tmp/swarm-review-R36/design/auth.md:633`
- `/tmp/swarm-review-R36/design/auth.md:883`
- `/tmp/swarm-review-R36/design/gameplay.md:366`

**Evidence**:
- Registry Limits 仍写 `CSR challenge default difficulty = 20 bits`。
- `design/auth.md` 和 `design/gameplay.md` 多处写默认 `difficulty_bits = 24`。

**Impact**: R35 S-H3 明确要求统一默认值；Registry 作为权威源仍与安全设计不一致。

**Required fix**: 将 Registry/Auth IDL 默认值统一为 24 bits，或重新裁定 20 bits 并同步所有安全/设计文档。

### R36-CV-5 — Deploy flow 仍混合同步 D4 与异步 object store 模型（B6 / D4）

**Severity**: Blocker  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:329`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:337`
- `/tmp/swarm-review-R36/specs/security/09-command-source.md:107`
- `/tmp/swarm-review-R36/specs/security/09-command-source.md:118`
- `/tmp/swarm-review-R36/specs/security/03-mcp-security.md:232`

**Evidence**:
- D4 裁决为同步 `swarm_deploy(wasm_bytes, metadata, code_signature)`。
- `09-command-source.md` 正确写客户端通过 `swarm_deploy` 同步发送 WASM bytes + metadata + DeployPayload + 证书，不接受先签名后异步补传 bytes。
- 但 `api-registry.md` 对 `swarm_deploy` 的说明仍写 `WASM blob 异步上传至 object store`，`03-mcp-security.md` 也写 `异步 blob 上传至 object store`。
- Registry 的 `swarm_deploy` schema 仍只有 `{player_id, drone_id, wasm_bytes, metadata}`，缺少 D4/B6 要求的显式 `code_signature` / `certificate_id` / `version_counter` 或 DeployPayload 双层签名字段。

**Impact**: 部署签名对象、TOCTOU 防护、replay verifier 与 SDK deploy API 仍无法一致实现。

**Required fix**: Registry schema 必须显式落地同步 deploy payload：`wasm_bytes`、`metadata`/`metadata_hash`、`deploy_payload`、`code_signature`、`certificate_id`、`version_counter`，并删除异步 blob 作为默认上传流程的表述；object store 只能作为后台持久化/缓存结果而非客户端 upload contract。

### R36-CV-6 — WebSocket per-message security contract 仍分叉（B8）

**Severity**: Blocker  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:440`
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:444`
- `/tmp/swarm-review-R36/design/auth.md:812`
- `/tmp/swarm-review-R36/design/auth.md:821`
- `/tmp/swarm-review-R36/specs/security/03-mcp-security.md:162`

**Evidence**:
- `design/auth.md` 与 `03-mcp-security.md` 要求每方向独立计数，严格 `seq == last_seq + 1`，签名 payload 为 `SWARM-WS-MSG-V1\n<transport>\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>\n<audience>`。
- Registry 仍写 `seq 必须 > 上次接收值`，MAC 覆盖 `(seq, tick, payload)`。
- Registry 还写每消息签名由 `Swarm-Request-Signature` 头携带，覆盖 `(method, uri, timestamp, seq, body_hash)`，这是 HTTP request signature 风格，不是 R35 B8 的 WS canonical payload。

**Impact**: WS 重放防护和跨 transport audience binding 无法生成一致 SDK/网关实现。

**Required fix**: Registry §3.5 改为引用同一 WS canonical payload，使用 `direction/session_id/tick/body_hash/audience`，并统一严格递增语义为 `seq == last_seq + 1`。

### R36-CV-7 — Action 模型迁移未彻底，仍残留 direct CommandAction 示例与 custom_actions（D3 / B9）

**Severity**: Blocker  
**Files**:
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:602`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:607`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:669`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:676`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:810`
- `/tmp/swarm-review-R36/specs/core/02-command-validation.md:824`
- `/tmp/swarm-review-R36/design/gameplay.md:1010`
- `/tmp/swarm-review-R36/design/gameplay.md:1156`

**Evidence**:
- `02-command-validation.md` §8 声明 combat/effect action 全部通过 `ActionRegistry`，但字段级穷举校验表仍把 `Attack`/`RangedAttack`/`Heal`/special attacks 作为顶层 Command 行列出。
- 同文后续示例仍使用 `{ "action": "RangedAttack", ... }`、`{ "action": "Leech", ... }` 这种旧顶层 action 形态，而非 `{ "action": { "type": "Action", "payload": ... } }` 或 Registry 定义的 dispatch 形态。
- Leech/Fabricate 属性表仍写注册方式为 `[[custom_actions]]`，与 D3 裁决“11 vanilla combat/effect action 统一进 ActionRegistry；vanilla 不作为 mod custom extension”冲突。
- `design/gameplay.md` 仍大量使用 `[[custom_actions]]` 预注册 8 个 special action，并有 `action: "Leech" // 新 CommandAction` 旧语义残留。

**Impact**: D3 的核心迁移目标未达成；SDK discriminated union、validation schema、World Action Manifest 仍可能生成旧 `CommandAction` combat variant。

**Required fix**: 对所有 combat/effect 示例统一改成 `CommandAction::Action { type, payload }` 的 wire shape；`[[custom_actions]]` 仅用于 mod 扩展，vanilla 11 action 改为内置 `ActionRegistry`/`[[action_registry]]` 或生成表引用。

### R36-CV-8 — HP writer contract 仍自相矛盾（B4）

**Severity**: High  
**Files**:
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:224`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:229`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:258`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:319`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:432`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:441`
- `/tmp/swarm-review-R36/specs/core/06-phase2b-system-manifest.md:443`

**Evidence**:
- S15 被声明为 `UNIQUE HitPoints writer`，并说 CI 应拒绝任何其他 system 写 `HitPoints`。
- 同文又允许 S10 regen、S22 status_advance、S24 decay 写同一 `HitPoints` component，并用 domain-specific writer 注释解释。
- S22 写 `Entity (hits/armor/efficiency/interrupted via effect application)`，R/W matrix 中 S22 对 `HitPoints` 为 W；S24 对 `HitPoints` 也为 W。

**Impact**: B4 要求 HP 写入责任可由 CI 静态验证；当前“UNIQUE writer”与“domain-specific 多 writer”并存，CI 规则不可实现。

**Required fix**: 二选一闭合：要么 S15 真正成为唯一 `HitPoints` writer，S10/S22/S24 只能写 pending buffer；要么删除 UNIQUE 表述，定义可机器验证的多 writer 顺序/语义域规则，并更新 CI gate 描述。

### R36-CV-9 — RNG derive 公式描述仍有旧口径残留（B2）

**Severity**: Medium  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/api-registry.md:469`
- `/tmp/swarm-review-R36/specs/reference/host-functions.md:66`
- `/tmp/swarm-review-R36/specs/core/04-wasm-sandbox.md:234`
- `/tmp/swarm-review-R36/design/interface.md:83`

**Evidence**:
- ABI 宽度 `sequence: u64` 已在主要文件统一。
- `host-functions.md` 与 `04-wasm-sandbox.md` 使用 `derive_rng("swarm.host_random.v1", world_seed, tick, actor_or_entity_id, sequence)` + length-delimited encoding。
- Registry 仍描述为 `(tick_seed, player_id, drone_id, sequence)`，未引用 domain separator/length-delimited encoding。

**Impact**: ABI 宽度已修，但跨语言 replay 的 seed 派生语义仍可能分叉。

**Required fix**: Registry §4.1 的 RNG 说明同步为同一 `derive_rng(domain, world_seed, tick, actor_or_entity_id, sequence)` 规范。

### R36-CV-10 — Vanilla/经济默认示例仍有旧资源和容量值残留（B7 / D6 / ML-5）

**Severity**: Medium  
**Files**:
- `/tmp/swarm-review-R36/design/gameplay.md:309`
- `/tmp/swarm-review-R36/design/gameplay.md:384`
- `/tmp/swarm-review-R36/design/gameplay.md:1027`
- `/tmp/swarm-review-R36/design/gameplay.md:1290`
- `/tmp/swarm-review-R36/design/gameplay.md:1291`
- `/tmp/swarm-review-R36/design/gameplay.md:1303`
- `/tmp/swarm-review-R36/design/gameplay.md:1990`

**Evidence**:
- 正文默认值已写 `global_storage_capacity = 1000000`，但 world.toml 示例仍是 `global_storage_capacity = 100000`。
- D6 裁决为 Vanilla 默认单一 `{Energy: 5000}`，但 world.toml 示例仍包含 `Matter`、`starting_amount = 1000/500`、spawn/build 成本含 Matter。
- `special_param` 字段仍为 `float`，示例有 `0.5`/`2.0`，与 ML-5 “Resource Ledger 出现 float multiplier，修复为 bp/ppm 定点类型”的方向冲突。

**Impact**: 示例会继续诱导实现/服主配置复制旧经济曲线；固定点数值规范仍不彻底。

**Required fix**: 将示例标注为“advanced multi-resource non-vanilla”或改为 Vanilla `{Energy: 5000}`；容量示例统一 1,000,000；`special_param` 改为 bps/ppm 或 typed fixed-point 字段。

### R36-CV-11 — Rhai actions API / capability 计数仍不一致（API-H3 / ML-3）

**Severity**: Medium  
**Files**:
- `/tmp/swarm-review-R36/specs/reference/rhai-mod-abi.md:29`
- `/tmp/swarm-review-R36/specs/reference/rhai-mod-abi.md:112`
- `/tmp/swarm-review-R36/specs/reference/rhai-mod-abi.md:151`
- `/tmp/swarm-review-R36/specs/reference/rhai-mod-abi.md:311`
- `/tmp/swarm-review-R36/specs/reference/rhai-mod-abi.md:312`
- `/tmp/swarm-review-R36/design/gameplay.md:1578`
- `/tmp/swarm-review-R36/design/gameplay.md:1616`

**Evidence**:
- `rhai-mod-abi.md` 明确只有 5 个 `actions.*` API，但 `design/gameplay.md` 的白名单列出 `deduct_resource/award_resource/damage_entity/set_entity_flag/emit_event/log_info/log_warn` 等 7 个。
- `rhai-mod-abi.md` 写 `12 个 capability 全部可授权`，但同文件当前可见 capability 表只列出少量项目且包含 `direct_ecs_writer` 例外；未给出 12 项完整权威列表。
- API-H3 要求 `actions.*` 返回类型/错误类型合同，当前只有“Action 失败跳过”策略，没有统一 `Result<T, RhaiActionError>` 结构。

**Impact**: Rhai ABI 无法稳定生成 SDK/类型绑定，`direct_ecs_writer` 边界仍难以审计。

**Required fix**: 给出完整 capability enum（精确 12 或修正计数），统一 actions API 名称和返回类型，明确 `direct_ecs_writer` 是否进入默认 ABI 或仅为 gated extension。

## 已确认修复较好的点

- `host_get_random(sequence: u64)` 已在 `host-functions.md`、`04-wasm-sandbox.md`、`design/interface.md` 中统一为 `u64`。
- `06-phase2b-system-manifest.md` 已明确 S01 不处理 combat/special action，A01 Action dispatch 写 intent buffer，S11-S13 不直接写 HP。
- `design/auth.md` 已落实 CSR 不带 email、签发后绑定邮箱、PoW 默认 24 bits、多层准入链等安全修复方向。
- `design/gameplay.md` 已在正文中写入 D6 `{Energy: 5000}` 与 D7 active alliance 上限 10 + `alliance_transfer_cap_per_tick`。
- `01-tick-protocol.md` 对 JCS/NFC、EXECUTE 预算目标、worker_pool 默认 256、RichTraceBlob audit_gap 等方向已有明显修正。

## 最终结论

**REQUEST_CHANGES**

R36 不能通过 closure verification。阻断原因不是缺少说明，而是 R35 fix wave 后仍存在多个权威源与派生文档的结构性漂移：MCP 工具数、RejectionReason 总数、CSR schema、Deploy schema、WS canonical payload、Action 模型、HP writer contract 均未闭合。建议先按上述 R36-CV-1..R36-CV-11 修复并重新生成 Registry/派生文档，再进入下一轮 closure verification。
