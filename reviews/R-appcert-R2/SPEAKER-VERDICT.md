# R-appcert-R2 — Speaker Verdict

## 裁决概要

本轮 R-appcert-R2 共读取 14/14 份评审报告，覆盖 7 个方向 × 2 个模型：Architect、Security、Designer、Determinism、Performance、Economy、API/DX。所有父任务均完成并写入 `/data/swarm/docs/reviews/R-appcert-R2/rev-*.md`，本 Speaker verdict 基于这些原始报告综合，不引入新的设计评审立场。

整体收敛信号明确：评审官普遍认可 R2 的主方向——AI 与人类玩家统一通过 WASM 路径进入游戏，MCP/Web 作为控制面与观察面而非 gameplay 旁路；应用层证书、Source Gate、CommandIntent/RawCommand 分层、Tick 三阶段、可见性统一函数、IDL 单一真相源、Replay/TickTrace 方向均被多方向肯定。

但 R2 尚未达到可直接实现的冻结状态。主要问题不是“架构概念错误”，而是若干实现前必须冻结的合同仍分散、矛盾或未定：API/IDL 合同、tick/replay/确定性合同、Tier1 性能预算、安全握手/高权限保护、经济与体验边界。按任务原则，本轮是设计阶段评审，不因实现难度而降级；有明确设计方案的项应直接采纳为 R2.5 收敛补丁。

Freeze 状态：未冻结。建议进入 R2.5 文档冻结轮，只收敛协议/合同/默认值，不新增玩法或新系统。

## Overall Verdict

REQUEST_MAJOR_CHANGES

理由：14 份报告中 13 份为 `CONDITIONAL_APPROVE`，1 份为 `REQUEST_MAJOR_CHANGES`；但多方向、多模型均指出进入实现前必须关闭的 High/Critical 合同缺口。若仅按多数 verdict 可接近 Conditional Approve，但按“设计阶段、不考虑实现难度、合适方案直接采用”的原则，跨方向共识 blocker 未关闭前不能进入实现。

## 14/14 Verdict Matrix

| Direction | GPT-5.5 | DeepSeek V4 Pro | Direction Verdict |
|---|---|---|---|
| API/DX | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Determinism | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Performance | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Economy | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

Severity roll-up from reviewer reports:

| Direction | Critical | High | Medium | Low/Info |
|---|---:|---:|---:|---:|
| API/DX | 2 | 10 | 6 | 5 |
| Architect | 3 | 6 | 6 | 3 |
| Security | 0 | 8 | 11 | 6 |
| Designer | 0 | 2 | 4 | 7 |
| Determinism | 0 | 6 | 5 | 5 |
| Performance | 2 | 6 | 7 | 4 |
| Economy | 0 | 3 | 6 | 6 |
| Total | 7 | 41 | 45 | 36 |

注：统计按原报告 severity 计数，未去重；Speaker 共识项按语义聚类去重。

## Consensus Strengths

### S1: 统一 gameplay 执行路径

同意者：rev-gpt-architect、rev-gpt-security、rev-gpt-designer、rev-gpt-economy、rev-gpt-apidx、rev-gpt-determinism、rev-dsv4-security。

共识：MCP 不直接提供 move/attack/build 等 gameplay action；AI agent 与人类玩家一样通过 WASM 部署代码，所有状态变更流经统一校验管线。这是 R2 最大的架构修正成果，保留。

### S2: Source Gate + CommandIntent/RawCommand 分层

同意者：rev-gpt-architect、rev-gpt-apidx、rev-gpt-security、rev-gpt-determinism、rev-dsv4-security、rev-dsv4-apidx。

共识：客户端提交 intent，服务端注入 player_id/source/tick/auth 并生成 RawCommand/ValidatedCommand，可降低身份伪造、跨来源重放和旁路执行风险。保留并进一步冻结排序、序列化和错误模型。

### S3: Tick 三阶段与确定性骨架成立

同意者：rev-gpt-architect、rev-gpt-performance、rev-gpt-determinism、rev-dsv4-determinism、rev-dsv4-security、rev-dsv4-performance。

共识：COLLECT/EXECUTE/BROADCAST 分层、FDB 原子提交、WASM 只读 host functions、TickTrace/replay 方向正确。需补齐具体合同，不需推翻模型。

### S4: 应用层证书与用途隔离方向正确

同意者：rev-gpt-security、rev-dsv4-security、rev-gpt-economy、rev-gpt-architect、rev-gpt-apidx。

共识：Server Root/Intermediate CA、用途隔离证书、canonical request、CRL/epoch bump、CVE-SLA 是强安全基础。需补齐 WS 认证、Intermediate CA 私钥存储、高权限限流和 nonce/version 统一。

### S5: 游戏体验从技术 demo 转向可玩系统

同意者：rev-gpt-designer、rev-dsv4-designer、rev-gpt-economy、rev-dsv4-economy。

共识：首小时教程、安全模式、soft_launch、PvE 过渡、Replay/观战、轻物流和反雪球意识已有骨架。需将 onboarding、长期目标、反雪球与经济参数冻结为玩家/AI/服主可理解的合同。

## Consensus Blockers

### B1: API/IDL 单一真相尚未真正冻结

方向 × 模型矩阵：

| Direction | Reviewer Evidence |
|---|---|
| API/DX | rev-dsv4-apidx C1/C2/H1-H7；rev-gpt-apidx A1-A4/A8 |
| Architect | rev-dsv4-architect C3；rev-gpt-architect A4 |
| Designer | rev-gpt-designer G1/G2 |
| Security | rev-gpt-security L2/M1；rev-dsv4-security H2 |
| Determinism | rev-gpt-determinism A2/A9 |

问题：IDL 宣称是单一真相，但 PlayerId `u32`/`u64`、`seq`/`sequence`、`SpawnDrone`/`Spawn`、Direction `TopRight`/四方向、拒绝码命名、deploy payload、MCP tool schema、MCP response schema、starter bot 示例等仍存在漂移。AI/新人第一段代码可能直接无法通过 schema 校验，SDK 与服务端也可能生成互不兼容的类型。

修正要求：

1. 冻结 `game_api.idl` 为唯一权威，统一 `PlayerId` 为 `u64` 或明确采用另一单一类型；同步 `auth.md`、`02-command-validation.md`、`08-api-idl.md`、所有 SDK/MCP 示例。
2. 统一 Command envelope 字段名、Command action 名、Direction enum、RejectionReason enum；删除或修正所有旧名。
3. 为所有 MCP tools 定义 input/output/error JSON Schema，尤其是 `swarm_sdk_fetch`、`swarm_get_player_status`、deploy、validate、dry-run、snapshot/docs/schema tools。
4. 将 GETTING-STARTED、commands、mcp-tools、starter bot 代码片段改为从 IDL/schema 生成或纳入 copy-paste smoke test。
5. 冻结 canonical JSON/CBOR 边界：哪些对象用于签名、排序、TickTrace、replay，哪些只是调试显示。

### B2: Tick/replay/确定性合同仍有实现分叉风险

方向 × 模型矩阵：

| Direction | Reviewer Evidence |
|---|---|
| Determinism | rev-gpt-determinism A1-A7；rev-dsv4-determinism D1-D4 |
| Architect | rev-gpt-architect A1/A3/A5/A6；rev-dsv4-architect C1/D2/D3 |
| Performance | rev-gpt-performance A3/A4；rev-dsv4-performance D10 |
| Security | rev-gpt-security H3；rev-dsv4-security H3/M4 |

问题：部署生效时序、Command 全局排序键、TickTrace 写入失败语义、BROADCAST failure 后输出可观察性、FDB rollback 与“空 tick/燃料 refund”、ECS `.chain()` vs 并行、snapshot truncation、RNG namespace、security epoch effective_tick、RuleMod/dynamic action 边界等未统一。若实现者各自选择合理解释，线上 tick 与 replay 可能分叉。

修正要求：

1. 新增或集中维护 `DETERMINISM-CONTRACT.md` 等价章节，冻结 tick phase、deploy effective_tick、command ordering key、RNG stream namespace/offset、state checksum、TickTrace authoritative fields、rollback/retry/refund、security event effective_tick。
2. 明确 TickTrace 与状态是否同 FDB transaction；若 TickTrace 写失败，tick 必须如何处理，禁止“状态成功但审计不完整”与“同事务无缺口”并存。
3. 统一 ECS schedule manifest：哪些系统必须 `.chain()`，哪些可并行；regeneration/decay、combat、seed rotation、death/spawn 等必须有权威顺序。
4. 统一 WASM output >256KB 语义为一种可实现规则；建议采用整批丢弃而非保留不可解析前缀。
5. 为 snapshot truncation 增加引用完整性合同：目标实体、source entity、特殊攻击反馈、reference drone、omitted_count 如何保证不泄露信息且不产生不可调试失败。
6. 收紧 RuleMod/Rhai dynamic handler：固定点数、禁止 f64、禁止第二套状态修改路径，所有扩展 action 仍进入 Command Validation 单一路径。

### B3: Tier1 性能预算与规模默认值相互冲突

方向 × 模型矩阵：

| Direction | Reviewer Evidence |
|---|---|
| Performance | rev-dsv4-performance D1-D5；rev-gpt-performance A1-A5 |
| Architect | rev-dsv4-architect C1/D3；rev-gpt-architect A2/A6 |
| Determinism | rev-dsv4-determinism D1/D4；rev-gpt-determinism A8/A9 |
| Security | rev-dsv4-security H4；rev-gpt-security M3 |
| Economy | rev-gpt-economy A3/A7 |

问题：Tier1 目标、per-player drone cap、全量 snapshot、Bevy World 深拷贝、FDB full-state write、Arena 300ms tick 与 2500ms COLLECT budget、每玩家每 tick fork/kill、JSON ABI 热路径、pathfinding/visibility/cache 无界或未定等存在硬冲突。若按当前数字进入实现，可能在 MVP 目标下直接失去 tick budget。

修正要求：

1. 冻结 Tier1 默认规模：总 drone/entity 上限、per-player 上限、房间/建筑/Source/Controller 最坏情况、Arena 与 World 分离预算。
2. 修正 drone cap 与 snapshot budget：要么降低 Tier1 `max_drones_per_player`，要么引入 `max_total_drones` hard cap，并同步所有文档。
3. Arena 使用独立 tick/collect/simulate/path_find budget，不得继承 World 2500ms COLLECT。
4. 明确 WASM sandbox 生命周期：不采用每玩家每 tick fork/kill，或给出满足 3s tick/500 player 的池化/预热/实例复用方案。
5. 明确热路径 ABI：JSON 可保留为调试/SDK/compat 格式，但实时 tick snapshot/CommandIntent 需有可预算的 binary/canonical encoding 或明确性能门槛。
6. 冻结 FDB transaction size 与状态写入策略；若 Tier1 每 tick full-state write，给出每日写入量预算和 key layout 上限，否则改为 keyframe/delta 方案。
7. 为 pathfinding cache、visibility cache、simulate/docs/schema tools 设置全局和 per-player 限流、cache size、eviction、冷启动策略。

### B4: 安全认证与高权限控制面合同未完整闭合

方向 × 模型矩阵：

| Direction | Reviewer Evidence |
|---|---|
| Security | rev-gpt-security H1-H3；rev-dsv4-security H1/H2/M1-M6 |
| Architect | rev-gpt-architect A7；rev-dsv4-architect D1/D5 |
| API/DX | rev-gpt-apidx A4/A7/A8；rev-dsv4-apidx H4/L2 |
| Performance | rev-gpt-performance A5；rev-dsv4-performance D8/D11 |
| Economy | rev-gpt-economy A1/A6 |

问题：应用层证书方向正确，但 WS application-certificate 握手、Intermediate CA 私钥存储、Admin recovery dual-auth tool signature、admin 限流、nonce registry vs version_counter、audience 字符串、refresh token grace、CRL/verification cache TTL、CodeSigning compromise detection、Rhai re-sign tooling等仍未冻结。高权限操作不能因为“需要管理员证书”而没有资源保护。

修正要求：

1. 冻结唯一 WebSocket 证书握手协议：必须包含证书链、cert id、timestamp、nonce、signature、transport、canonical payload；禁止仅凭 `swarm-cert.<cert_id>` 建立认证连接。
2. 明确 Intermediate CA 私钥存储最低要求：文件权限、HSM/soft-HSM 可选项、rotation、backup、operator runbook。
3. Admin recovery/rollback/epoch bump/batch revoke 等高权限 MCP tools 必须在 schema 中显式表达双签、冷却、审计、break-glass、幂等键。
4. 统一 nonce/version_counter 模型：哪些操作使用 FDB 持久 nonce，哪些使用版本计数，跨分片与 crash 后 replay 窗口如何处理。
5. 统一 audience 字符串 canonical grammar，禁止宽松匹配。
6. 收紧 refresh token grace、CRL/verification cache TTL、CodeSigningCertificate compromise detection 与 Rhai batch re-sign tooling。
7. 为认证热路径定义 p99 latency budget 和缓存失效协议；read/query 与 deploy/admin 的安全强度可分层，但边界必须写明。

### B5: 经济、反雪球与玩家体验合同尚未达到实现前可冻结状态

方向 × 模型矩阵：

| Direction | Reviewer Evidence |
|---|---|
| Economy | rev-gpt-economy A1-A6；rev-dsv4-economy M1-M3 |
| Designer | rev-gpt-designer G2-G5；rev-dsv4-designer C1/G1-G6/M1-M4 |
| Performance | rev-dsv4-performance D12；rev-gpt-performance A7 |
| Security/API | rev-gpt-security M3；rev-gpt-apidx A1/A6 |

问题：World 模式不追求公平是可接受设计，但 PoW 成本、自适应治理、全局存储税/市场反垄断、实体膨胀外部化、late-game anti-snowball、market/trading spec、账号删除资产处置、证书生命周期成本、AI MCP onboarding 完成标准、长期目标系统仍不够硬。若留到实现后“调参数”，会变成根本性游戏经济/留存风险。

修正要求：

1. 冻结 PoW 经济治理：目标 P50/P95 注册耗时、单云核批量注册成本、每 1000 账号攻击成本、难度调整输入与上下限。
2. 补齐 market/trading 设计或显式 deferral；若 deferral，所有 Terminal/market references 标注不可用或 Phase gate。
3. 冻结全局/本地存储、transfer cost/time、storage tax、market monopoly countermeasure 的默认值与最小安全下限。
4. 设计实体膨胀惩罚的归因机制，避免富玩家把 snapshot/path_find/visibility 成本外部化给受害者。
5. 形成 anti-snowball contract：World 为什么允许不公平、哪些机制保护新玩家、哪些参数服主可调、AI 如何查询。
6. 为账号删除 in-transit resource、asset transfer/recycle/abandon、证书/设备/agent fleet 成本建立经济规则。
7. 为 AI onboarding MCP resources 定义可验证完成标准：从 docs/schema/sdk fetch 到 validate/deploy/explain 的 golden path。
8. 补一个长期目标系统说明：不要求新增复杂玩法，但需解释殖民地年龄/GCL/RCL/Arena/PvE/replay/market 等如何形成非线性追求，而不只是扩张指标。

## Direction-Specific High

### API-H1: MCP 工具与 SDK 生成物 schema 不完整

来源：rev-dsv4-apidx H7/C2，rev-gpt-apidx A3/A6。

处置：所有 MCP tools 必须具备 inputSchema/outputSchema/error schema；`swarm_sdk_fetch`、`swarm_get_schema`、`swarm_get_docs`、`swarm_get_player_status` 需进入工具目录、scope、rate limit、response schema。

### ARCH-H1: Output State Contract 缺失

来源：rev-gpt-architect A1，rev-dsv4-architect D1/D3。

处置：冻结 `state_version/tick_version` 合同，约束 Bevy/FDB/Dragonfly/NATS/WebSocket/MCP query/replay 的读源与滞后语义，避免“已提交但不可观察”或 stale cache 被误认为权威。

### SEC-H1: WS 与 Admin 高权限路径需协议级冻结

来源：rev-gpt-security H1/H2，rev-dsv4-security H1/H2。

处置：WS 不能只有 cert_id；Admin tools 不能只在 prose 中双签，必须进入 MCP schema 与 canonical signing body。

### DES-H1: 首小时与 AI onboarding 缺少可执行验收

来源：rev-gpt-designer G1/G2，rev-dsv4-designer G6/M3。

处置：提供 starter bot smoke test、MCP learning pack completion criteria、Replay-driven docs 或等价可验证教程链路。

### DET-H1: Command ordering 与 deploy effective_tick 必须单一权威

来源：rev-gpt-determinism A1/A2，rev-dsv4-determinism D1。

处置：冻结部署何时对 COLLECT 生效、RawCommand 排序 key 是否包含 source、同 tick retry/replay 如何重建完全一致结果。

### PERF-H1: Tier1 hard budget registry 缺失

来源：rev-dsv4-performance D1/D2/D3，rev-gpt-performance A1/A2/A3。

处置：建立 Tier1 budget registry，列出 tick、COLLECT、EXECUTE、BROADCAST、snapshot bytes、FDB bytes、WASM instance、auth p99、cache size、global concurrency 的硬值。

### ECON-H1: PoW/market/storage/anti-snowball 经济边界不足

来源：rev-gpt-economy A1/A2/A3，rev-dsv4-economy M1/M3。

处置：冻结经济默认值与安全下限，补 market 或延期声明，建立反垄断/反实体膨胀/反批量账号的设计闭环。

## Medium/Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---|---|
| ML1 | ABI 向后兼容窗口 | R2.5 docs | 定义 ABI 公告期、兼容窗口、旧模块行为 |
| ML2 | `additionalProperties: false` 与扩展 action 交互 | R2.5 docs | world action manifest 扩展字段必须经 IDL 生成 |
| ML3 | Snapshot tick 语义对 WASM 作者不直观 | R2.5 docs | 在 API 文档加注释与示例 |
| ML4 | Seed rotation epoch boundary CI | Phase 1 test plan | 加 FDB rollback 注入测试，不阻塞设计方向 |
| ML5 | RoomCap release timing coupling | R2.5 docs | ECS schedule manifest 标出 death/spawn/cap 顺序 |
| ML6 | Dragonfly nonce post-crash replay | R2.5 security | 高价值操作改 FDB nonce 或幂等键 |
| ML7 | CSR client-supplied challenge defense-in-depth | R2.5 security | challenge 由服务端权威绑定，客户端字段仅作 echo 或删除 |
| ML8 | Refresh token grace 300s 偏长 | R2.5 security | 缩短或按设备风险分层 |
| ML9 | Rhai re-sign tooling | Phase 1 tooling | 设计 batch re-sign runbook 与 dry-run |
| ML10 | Federation CRL 60s latency | R2.5 security | 明确风险接受或 push invalidation |
| ML11 | Certificate renewal / device lifecycle cost | R2.5 economy | 添加 active cert/device 上限或成本 |
| ML12 | Account deletion in-transit resources | R2.5 economy | 定义 transfer/depot/market order 删除语义 |
| ML13 | Replay/community product surface | Phase 1 UX | 不阻塞核心架构，但纳入 UX backlog |
| ML14 | Arena fog-of-war depth | Phase 1 gameplay | 作为模式调参，不阻塞 R2.5 合同冻结 |
| ML15 | `swarm_get_docs/schema` DoS | R2.5 security/perf | 加 cache、ETag、rate limit、size limit |
| ML16 | CVE SLA 数字漂移 | R2.5 docs | 统一 Critical/High 响应时间，CVE-SLA 为权威 |

## D-items

D-items 是本轮不作为共识 blocker、但必须显式记录的 deferred/design debt。

| ID | Item | 来源 | 处理方式 |
|---|---|---|---|
| D1 | Tier2/Tier3 仍是候选协议，不应被主设计当作已冻结承诺 | rev-gpt-architect A2、rev-gpt-performance A6、rev-gpt-determinism A8、rev-dsv4-architect D6 | R2.5 标注 entry gate 与非冻结状态；实现 Phase 1 不依赖候选细节 |
| D2 | territorial snowball 在 vanilla World mode 中是接受的设计债 | rev-dsv4-designer C1、rev-gpt-designer G4、rev-gpt-economy A4 | 写入 anti-snowball contract，说明 World 与 Arena 的不同目标 |
| D3 | Overload 反馈透明度与集中攻击可读性 | rev-dsv4-designer G1/G2、rev-dsv4-performance D12 | Phase 1 UX/telemetry 设计，不阻塞核心协议 |
| D4 | Drone personality / diplomacy / behavior visualization / player economy feedback loop | rev-dsv4-designer M1-M4 | Product backlog，不进入 R2.5 blocker |
| D5 | Public spectate delay 与 Arena 最小值 | rev-dsv4-architect D8、designer concerns | R2.5 默认值即可，深度设计延期 |
| D6 | Path cache hit rate optimization | rev-gpt-performance A7 | Benchmark backlog；cache bound 是 blocker，命中率优化不是 |
| D7 | Economic simulation benchmarks | rev-gpt-economy missing items | Phase 1/Phase 2 validation；R2.5 需列场景，不需真实数值模拟结果 |

## Next Steps

1. 启动 R2.5 文档冻结补丁，只处理 B1-B5，不新增玩法、模式或大系统。
2. 先建立 5 个权威 registry/contract：API/IDL registry、Determinism Contract、Tier1 Budget Registry、Security/Auth Canonical Grammar、Economy/Anti-snowball Contract。
3. 对所有文档执行 stale reference scan：`PlayerId`、`SpawnDrone`、`seq`、`TopRight`、`PlayerNotFound`、`TargetNotVisible`、deploy payload、CVE SLA、rate limit、drone cap、Arena budget。
4. 为 GETTING-STARTED/starter bot 建立 copy-paste smoke test，至少验证 schema 与 dry-run 路径。
5. 完成 R2.5 后重新发起完整 clean-slate review；若 14/14 不再出现 Critical，且 High 仅为实现/benchmark gate，可降为 CONDITIONAL_APPROVE。

## Statistics

### Verdict Distribution

| Verdict | Count | Reviewers |
|---|---:|---|
| REQUEST_MAJOR_CHANGES | 1 | rev-dsv4-apidx |
| CONDITIONAL_APPROVE | 13 | all remaining 13 reviewers |
| APPROVE | 0 | — |
| REJECT | 0 | — |

### Consensus Strength Assessment

| Consensus Area | Directions | Models | Strength |
|---|---:|---:|---|
| API/IDL single truth gap | 5/7 | 2/2 | Very Strong |
| Tick/replay/determinism contract gap | 4/7 | 2/2 | Very Strong |
| Tier1 performance budget conflict | 5/7 | 2/2 | Very Strong |
| Security/auth/admin contract gap | 5/7 | 2/2 | Very Strong |
| Economy/onboarding/anti-snowball contract gap | 4/7 | 2/2 | Strong |
| Core architecture direction is correct | 7/7 | 2/2 | Very Strong |
| Unified WASM gameplay path is correct | 6/7 | 2/2 | Very Strong |

### Speaker Conclusion

R-appcert-R2 已经从“方向性不确定”收敛到“方向正确但合同未冻结”。本轮不建议推倒重来；也不建议直接进入实现。正确动作是 R2.5 合同冻结：关闭 B1-B5 后再进行完整重审。
