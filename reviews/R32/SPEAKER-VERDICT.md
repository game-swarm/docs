# R32 Speaker 裁决

## 裁决概要

**整体 Verdict: REQUEST_MAJOR_CHANGES**

R32 Clean-Slate 的大方向继续成立：确定性执行、API Registry 单事实源、WASM deferred command model、Resource Ledger、证书用途隔离、Replay/Rich Trace 分层等核心架构都有明显进步。但 10 份独立报告共同显示：当前设计仍存在多处跨文档权威源冲突、replay/commit 原子性语义冲突、API/IDL 派生文档漂移，以及经济数学目标不闭合。按照“多方向 + 多模型一致”的共识规则，本轮必须请求重大修改。

### 评审统计（5×2 matrix）

| 方向 | DSV4 Verdict | GPT Verdict |
|---|---|---|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Design & Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Determinism & Performance | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |

### 票数统计

| Verdict | 票数 |
|---|---:|
| APPROVE | 0 |
| CONDITIONAL_APPROVE | 1 |
| REQUEST_MAJOR_CHANGES | 9 |
| REJECT | 0 |

### Provenance

已逐份读取全部 10 份 Phase 1 reviewer 报告：

- rev-dsv4-architect.md
- rev-dsv4-security.md
- rev-dsv4-design-economy.md
- rev-dsv4-apidx.md
- rev-dsv4-determinism-perf.md
- rev-gpt-architect.md
- rev-gpt-security.md
- rev-gpt-design-economy.md
- rev-gpt-apidx.md
- rev-gpt-determinism-perf.md

R32 review 目录仅发现上述 10 份报告，无 Phase 2/CrossCheck 补充报告文件。

---

## 共识 Blocker（B1..B9）

### B1. Room-partition 全局原子提交语义不可成立

- **问题描述**: `01-tick-protocol.md` / `05-persistence-contract.md` 同时声称 per-room FDB transaction 已独立 durable commit，又声称 GlobalTickCommit 失败时不存在部分提交、可全局回滚。已提交的 FDB room delta 无法靠 Bevy 内存快照撤销；当前文档没有 staged keyspace、publish marker、read fence、rollback/GC 协议或可验证 2PC 状态机。
- **来源 reviewer**: GPT Architect A-H1；GPT Determinism DNP-3；DSV4 Determinism M1 间接指出 room-partition abandon 可用性风险；GPT Security S-H6 / GPT API CX-5 也指向 persistence/deploy/replay 边界。
- **影响范围**: tick commit、crash recovery、read/query path、replay verifier、cross-room operations、FDB key layout、operator runbook。
- **修复方向建议**: 明确改为 shadow write + atomic publish：per-room 事务只写 `/staging/{tick}/{room}`；GlobalTickCommit 是唯一发布点，写入 global head、room hashes、manifest hash；所有读路径从 committed global head 进入；未发布 staging rows 由 GC 清理。若选择真正 FDB 单事务/2PC，则删除“先独立 per-room durable commit 后全局回滚”的文本，写出 prepare/commit/abort、idempotency、crash recovery 协议。

### B2. TickCommitRecord / RichTraceBlob / Object Store replay-critical 边界冲突

- **问题描述**: Persistence Contract 一处声明 FDB 中 replay-critical subset 足够 deterministic replay，Object Store 只保存 RichTraceBlob，blob 缺失只产生 `audit_gap`；另一处又写 blob pending/failed 导致 “replay 不可用” 或 `unreplayable`。Deploy WASM module blob 又和 replay/security audit 语义混在一起。
- **来源 reviewer**: GPT Architect A-H2；GPT Security S-H6；GPT Determinism DNP-2；DSV4 Security L2；DSV4 Architect 亮点中也确认当前设计意图应为 FDB replay-critical + Object Store rich trace 分层。
- **影响范围**: deterministic replay、rich debug replay、anti-cheat audit、deploy activation、WASM module retention、GC、CI replay gate、incident recovery。
- **修复方向建议**: 写出三层分离合同：`deterministic_replay` 仅依赖 FDB TickCommitRecord + keyframe/delta；`rich_debug_replay` 依赖 RichTraceBlob，缺失为 `audit_gap`；visual/replay artifacts 可缺失或重建。WASM module blob 单独分类：若 replay 不重新执行 WASM，则 FDB 必须原子记录 deploy activation result、module hash、terminal_state、commands_hash；若要求重新审计 WASM，则 module blob 可用性进入 replay-critical SLA，不能再称 Object Store 非 replay-critical。

### B3. API Registry / IDL 单事实源被派生文档漂移破坏

- **问题描述**: MCP tool 数量在 56/57 间冲突，Host Function 数量在 5/6 间冲突，`host_get_random` 在 Registry 存在但 sandbox/host-functions/codegen/interface 缺失，API Registry changelog 与正文不一致。Auth 工具也存在 `auth.md` 定义约 20 个工具但 Registry 仅 11 auth tools 的缺口。
- **来源 reviewer**: DSV4 API C1/C2/H1；GPT API R32-API-H1/H2；GPT Architect A-H5/A-L1；GPT Security S-M1/CX-2；DSV4 Security C2；GPT Design DE-3。
- **影响范围**: SDK/codegen、MCP tool discovery、capability profile、WASM import ABI、sandbox allowlist、API security matrix、CI drift checks、AI agent onboarding。
- **修复方向建议**: 以 IDL → generated Registry 为唯一权威，禁止手写 count literals 或至少由 CI 校验。统一 `57 game active tools + 11 auth tools` 的口径或重新生成为正确口径；补齐所有 auth tools 的 IDL/Registry 条目及 security columns；Host Functions 全文统一为 6 个并补 `host_get_random` 的签名、预算、输出上限、domain separation、SDK wrapper 名称映射。

### B4. CommandAction schema 与执行/校验文档不闭合

- **问题描述**: Registry 声明 21 个 CommandAction 和公共 `object_id`，但 `commands.md`、`02-command-validation.md`、engine/manifest 中 Spawn/Build/Recycle/TransferToGlobal/TransferFromGlobal 等字段 shape 与执行系统不一致。Recycle 同时出现 `target_id`、`spawn_id`、`object_id` 三种语义；Overload 在 Registry 为 EntityId，但 validation 要求 player_id；Leech/Fabricate 已作为核心 action 注册却缺 validation/body-part 完整定义。
- **来源 reviewer**: GPT API R32-API-C1；DSV4 Architect C1/C2/H2/H3；GPT Determinism DNP-8；GPT Design DE-3/DE-7；DSV4 API C3/CX-3；GPT Architect A-H4。
- **影响范围**: TypeScript discriminated union、JSON schema validation、player examples、AI code generation、Phase 2a handlers、Resource Ledger execution path、special attack reducer。
- **修复方向建议**: 从 IDL/Registry 自动生成 command examples，禁止手写字段名。建立 21 action → validation matrix → Phase 2a/Sxx handler → ledger operation 的闭合表。对 Recycle、Overload、TransferToGlobal/FromGlobal、Leech/Fabricate 做一次性语义裁决并同步 Registry、commands、validation、manifest、SDK。

### B5. RejectionReason / SwarmError / Safe Hint Ladder 错误模型双轨冲突

- **问题描述**: Registry 规定 47 个 canonical RejectionReason wire enum，细节进入 `debug_detail`；但 `02-command-validation.md`、Visibility、Snapshot、admission/ABI 文档继续使用未注册或旧错误码：`TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`AlreadyDebilitated`、`MainActionQuotaExceeded`、`NotEligible`、`Fatigued`、`OnCooldown`、`ERR_CPU_SATURATED` 等。`SwarmError/detail_level` 与 Snapshot `CommandError/safe_message/fix_hint/hint_level` 未映射。
- **来源 reviewer**: DSV4 API C3/H2/H3；GPT API R32-API-C2/H3；GPT Architect A-H4；GPT Security S-M2；DSV4 Security S-M2；GPT Determinism CX-4。
- **影响范围**: wire compatibility、SDK typed exceptions、JSON-RPC error envelope、oracle 防线、training/practice/competitive hint behavior、CI validation mapping。
- **修复方向建议**: 建立机器可读的 `condition -> canonical RejectionReason -> debug_detail/fix_hint template` 完整表，覆盖所有 validation conditions。未注册码要么正式进入 IDL/Registry，要么降级为 debug_detail，不得在下游文档直接发明。将 Safe Hint Ladder 收敛到 `SwarmError.data` schema：`safe_message`、`fix_hint`、`debug_detail` 与 `detail_level/world.hint_level` 一一映射。

### B6. ECS Phase 2b manifest 的 system 计数、R/W matrix、Unique Writer contract 冲突

- **问题描述**: Manifest 同时写 29 systems 和 31 systems；S11-S13 文本称只写 PendingDamage/PendingHeal，但 R/W matrix 标为 HitPoints W；S15 被称为 HitPoints unique writer，但 S10/S22/S24 等也写或影响 HitPoints/Resource/Fuel；S15/S11-S13 缺 `Without<DeathMark>` guard 的风险也被架构报告指出。
- **来源 reviewer**: DSV4 Architect C3/C4/M2/M3；GPT Architect A-H3；GPT Determinism DNP-4；DSV4 Determinism M2；GPT Architect CX-4。
- **影响范围**: ECS schedule manifest hash、parallel safety proof、CI R/W conflict check、combat/recovery/status/death determinism、static unique writer verification。
- **修复方向建议**: 统一为机器可读 schedule source。全文件计数改为 31 或重新编号；R/W matrix 新增 PendingDamage/PendingHeal typed buffer 列；明确 HitPoints writer 模型：多 writer 按固定序列合法，或所有非 S15 写入先进入 buffer，由单一 committer 提交。为 DeathMark 相关系统补 filter/guard，并让 CI 校验写 HitPoints/DeathMark 的系统必须声明相关约束。

### B7. Standard 经济曲线与“自维持 / break-even”目标冲突

- **问题描述**: Balance Sheet 显示 Standard 在 free_upkeep 后几乎全阶段净亏损：1 房 -33/tick，2 房优化仍 -54，5 房 -195，10 房 -225，20/50 房大幅亏损；但 Resource Ledger Growth Path 声称 2000+ Full economy “自维持”。Anti-snowball 证明也缺乏数学推导。
- **来源 reviewer**: DSV4 Design C1/H1；GPT Design DE-1；父任务 summaries 中两模型均标为 REQUEST_MAJOR_CHANGES；Security CrossCheck 也要求评估全赤字带来的 griefing/储备优势风险。
- **影响范围**: Standard mode player motivation、newbie protection、anti-snowball、PvE budget、storage/upkeep tuning、economy dashboard、长期持久世界定位。
- **修复方向建议**: 需要用户裁决经济目标（见 D1）。若目标是可自维持，则以 Resource Ledger 为数学权威重校准 `base_upkeep`、source/RCL/PvE 收入、soft cap 与效率档位，写出 break-even corridor；若目标是燃烧经济，则全局删除“自维持/break-even”承诺并重新论证持久世界体验。

### B8. Security trust-boundary 合同多处自相矛盾

- **问题描述**: Agent/CLI/browser audience 枚举与示例冲突；CSR admission 在 `per-IP ≤1/30s`、`10/min`、`PoW 自身限速无额外 IP 限制` 间冲突；Admin rate limit 在“无限制”、`10/h`、单工具 `5/min/30/tick` 间冲突；WS per-message MAC payload 有无 tick 字段不一致；WASM sandbox “无网络命名空间” 与“独立网络栈”冲突；body_hash canonicalization 未定义。
- **来源 reviewer**: GPT Security S-H1/S-H2/S-H3/S-H4/S-H5；DSV4 Security C1/H1/H2/H3/H4/M2；GPT API/Security CrossChecks；DSV4 API RejectionReason findings 间接影响安全错误模型。
- **影响范围**: transport replay protection、registration DoS、admin abuse、WS replay、sandbox escape hardening、cross-language request signing、Auth/MCP SDK interoperability。
- **修复方向建议**: 建立安全合同单事实源：transport audience 枚举机器可读；CSR/Admin admission 只有一张权威表；WS signature payload 唯一格式（建议含 direction/session_id/seq/tick/body_hash）；sandbox 明确独立 netns + 无外部接口 + UDS fd；body_hash 使用明确 canonical JSON 或 raw bytes 规则并加入 SDK fixtures。

### B9. 确定性资源计量与容量模型不闭合

- **问题描述**: WASM 输出超限语义“整批丢弃”与“截断保留前 256KB”冲突；capacity 推导存在算术错误（1000×5ms/40 cores 应为 125ms 非 25ms）且 worker_pool 默认 256、hard cap 1000、cgroup cpu.max、aggregate admission 没有统一；fuel 被描述为 CPU 指令数，但 Wasmtime fuel、host function fuel、hardware admission 不是同一单位；IndexMap 插入顺序和 canonical_json 大整数序列化仍有确定性边界缺口。
- **来源 reviewer**: GPT Determinism DNP-1/DNP-5/DNP-7；DSV4 Determinism H1/H2/M3；GPT Architect A-M1；Security/API host_get_random findings 也牵涉 RNG/fuel/replay。
- **影响范围**: replay determinism、fuel fairness、tick overrun、capacity planning、benchmark gates、cross-language canonical codec、Resource/Source map iteration order。
- **修复方向建议**: 统一输出超限为“整批丢弃，不解析前缀”；将 public fuel 术语改为 deterministic engine fuel units，版本化 `fuel_schedule_version/host_cost_table_version/wasmtime_build_commit`；修正 capacity math 并以 empirical p95/p99 gate + global CPU admission 为准；IndexMap 改 BTreeMap 或规定 canonical insertion order；canonical_json 明确任意精度整数、不经 IEEE 754。

---

## CrossCheck 补漏发现

无 Phase 2 补充报告。R32 目录仅包含 10 份 Phase 1 reviewer 报告。

Phase 1 CrossCheck 中高频需要后续复核的方向如下，已并入 B-items 或 D-items：

| CrossCheck 主题 | 来源 | Speaker 处置 |
|---|---|---|
| Room-partition staged commit / FDB key layout / read path | Architect, Determinism, Security | 升为 B1 |
| Object Store vs replay-critical / WASM module blob | Architect, Security, Determinism, API | 升为 B2，D6 |
| API/IDL tool count、auth tools、host_get_random | API, Security, Design, Architect | 升为 B3 |
| CommandAction/RejectionReason mapping | API, Architect, Security, Determinism | 升为 B4/B5 |
| Economy 全赤字是否目标 | Design/Economy, Security CX | 升为 B7，D1 |
| WS MAC payload 与 body_hash canonicalization | Security, API | 并入 B8，D4/D5 |
| Rhai capability default-deny | API CX, Security CX | 方向专属 High / D7 |
| Tutorial Golden Path vs safe mode/PvE | Design/Economy | Medium 处置 |
| SIMD deterministic subset / sandbox relaxed clock | Determinism, Security CX | Medium deferred |

---

## 方向专属 High

### Architect 专属 High

| ID | 问题 | 来源 | 处置 |
|---|---|---|---|
| A-H1 | Phase 2a Build inline entity creation 与 pending_entities flush 规则冲突 | DSV4 Architect H1 | High，需在实体可见性语义中闭合；不升共识 Blocker，因主要单方向发现 |
| A-H2 | Recycle 参数/语义冲突 | DSV4 Architect H2 + GPT API C1 涉及 | 并入 B4，且作为 D2 |
| A-H3 | Leech/Fabricate body part 映射缺失 | DSV4 Architect H3 + Design DE-7 | 并入 B4/D3 |
| A-H4 | Capacity / worker pool 概念混用 | GPT Architect A-M1 | 并入 B9 |

### Security 专属 High

| ID | 问题 | 来源 | 处置 |
|---|---|---|---|
| S-H1 | Recovery credential side-channel：dummy argon2id 与 dummy token I/O 不对称 | DSV4 Security H2 | High，修正文档安全声明并补 FDB dummy write / jitter |
| S-H2 | Federation CRL fallback `allow_with_warning` 缺少 production gate | DSV4 Security H3 | High，要求 world.toml validation gate；可直接修复 |
| S-H3 | Admin CAS 原子性失败/回滚语义不够显式 | DSV4 Security H4 | High/Medium 边界，补 FDB transaction atomic statement |
| S-H4 | Agent/CLI audience 冲突 | GPT Security S-H1 | 并入 B8 |
| S-H5 | CSR/Admin 限流冲突 | GPT Security S-H2/S-H3 | 并入 B8 |

### Design & Economy 专属 High

| ID | 问题 | 来源 | 处置 |
|---|---|---|---|
| E-H1 | Anti-snowball 证明缺乏数学推导 | DSV4 Design H1 | High，随 B7 修复经济曲线时一并补证明 |
| E-H2 | Phase/MVP/P0/P1+ 语义残留 | GPT Design DE-2；GPT API L1 | High/Low 跨方向，需 clean-slate 文案修复，不升 Blocker |
| E-H3 | Economy 权威源含 float 与 storage tax 概述冲突 | GPT Design DE-4；DSV4 Design L2 | High，需统一 fixed-point |
| E-H4 | Resource Ledger 遗漏 global_deposit_delay | DSV4 Design H2；GPT Design DE-5 | Medium/High，直接修复为 deposit/withdraw 双参数 |

### API/DX 专属 High

| ID | 问题 | 来源 | 处置 |
|---|---|---|---|
| API-H1 | TypeScript SDK 生成合同不足 | GPT API M1 | Medium/High，建议补 TS discriminated union/branded IDs 合同 |
| API-H2 | Rhai `capabilities` 省略即授权全部 declared capabilities | GPT API M2 | Medium/High 安全 footgun，需用户裁决（D7） |
| API-H3 | `debug_detail` 标记缺乏机器可读语义 | DSV4 API H3 | 并入 B5 |
| API-H4 | host-functions 缺 `host_get_random` 完整文档 | DSV4 API H1 / GPT API H2 | 并入 B3 |

### Determinism & Performance 专属 High

| ID | 问题 | 来源 | 处置 |
|---|---|---|---|
| D-H1 | IndexMap 插入顺序未指定确定性排序规则 | DSV4 Determinism H1 | High，需 BTreeMap 或 canonical insertion order（D8） |
| D-H2 | canonical_json 大整数序列化未规定 arbitrary precision | DSV4 Determinism H2 | High，直接修复并加 fixtures |
| D-H3 | RNG host function 命名/派生公式不统一 | GPT Determinism DNP-6 + API/Architect | 并入 B3/B9 |
| D-H4 | WASM 输出超限语义冲突 | GPT Determinism DNP-1 | 并入 B9 |

---

## Medium / Low 处置

| ID/主题 | Severity | 来源 | 处置建议 |
|---|---|---|---|
| Parallel Set C 仅含单 system | Medium | DSV4 Architect M1 | 直接闭合：移除 parallel set 标签或并入 serial spine |
| R/W matrix Controller 列歧义 | Low | DSV4 Architect L1 | 直接闭合：拆分 Controller component vs Room.controller_level |
| engine keyframe K=100 缺交叉引用 | Low | DSV4 Architect L2 | 直接闭合：引用 Registry §5.4 |
| Refresh token rotation 60s grace | Medium | DSV4 Security M1 | Deferred/security hardening：考虑 15–30s 或旧 token 不签发新 access token |
| WASM compile cache key 缺 wasmtime version | Medium | DSV4 Security M3 | 直接闭合：加入 `wasmtime_version` 与 build commit 并存 |
| IndexedDB certificate + XSS | Medium | DSV4 Security M4 | Deferred/security doc：补 CSP、Monaco sandbox、XSS 后证书轮换假设 |
| 账号删除 in-transit cargo dangling source | Low | DSV4 Security L1 | 直接闭合：源不存在则 world discard pool + WARN audit |
| Tutorial replay class 重复/缺失 | Low | DSV4 Security L3 | 直接闭合：合并 Tutorial source 并声明 replay_class |
| global_storage_capacity 示例 100k vs 1M | Medium | DSV4 Design M1 | 直接闭合：示例改 1,000,000 |
| Balance Sheet 1 房 free_upkeep 表格语义 | Medium | DSV4 Design M2 | 直接闭合：拆成 free_upkeep 内/后两行 |
| Tutorial allied_transfer_enabled 是否 true | Medium | DSV4 Design M3 | Deferred：非阻塞，若保留 true 需解释 Tutorial 为什么启用 |
| UpkeepDeduction 后 StorageTax deficit 边界 | Low | DSV4 Design L1 | 直接闭合：说明 0 存储税率为 0 |
| special_param float | Low/Medium | DSV4 Design L2 | 直接闭合：改 BasisPoints/u32 |
| codegen.md 手工维护漂移风险 | Medium | DSV4 API M1 | 直接闭合：计数由生成器写入或 CI 校验 |
| refund table `InsufficientResource` 重复矛盾 | Medium | DSV4 API M2 | 直接闭合：按场景拆分唯一 refund rule |
| RejectionReason 编号与 §2.6 无关联 | Medium | DSV4 API M3 | 直接闭合：映射表加 code # |
| Recycle refund bp/decimal 表示不一致 | Low | DSV4 API L1 | 直接闭合：统一 basis points |
| host-functions 64MB/128MB 描述不完整 | Low | DSV4 API L2 | 直接闭合：补 cgroup 进程级 128MB 或引用 Registry |
| table formatting | Low | DSV4 API L3 | 直接闭合 |
| room-partition tick abandon 概率 | Medium | DSV4 Determinism M1 | Deferred/ops：补可用性模型与 benchmark gate |
| S22 status sort 开销 | Medium | DSV4 Determinism M2 | Deferred/perf gate：增加 p99 benchmark 或 BTreeSet 优化 |
| pathfinding cache_miss_penalty 依据 | Medium | DSV4 Determinism M3 | 直接闭合：补 2000 fuel 估算来源与 benchmark gate |
| Store reset 线性内存清零描述 | Low | DSV4 Determinism L1 | 直接闭合：说明不要求 64MB 全量清零 |
| Deploy activation pending 30s 与 tick 边界 | Low | DSV4 Determinism L2 | 直接闭合：每 tick 检查，累计 ≤30s |
| max active alliances 5 vs 10 | Medium | GPT Design DE-6 | 需要参数权威化，可与经济修复一并处理；默认倾向 5 |
| Tutorial Golden Path vs safe_mode/PvE timing | Medium | GPT Design DE-8 | 直接闭合：Tutorial scripted PvE 独立于 World PvP safe/soft_launch |
| 历史 R-label 修复标签残留 | Low | GPT/DSV4 Design/API | 直接闭合：移入 changelog 或删除正文历史痕迹 |
| SIMD deterministic subset / relaxed clock | Medium | CrossCheck | Deferred：未来启用 SIMD/relaxed 模式前必须 sandbox/determinism 复核 |

---

## D-items

### D1: Standard 经济目标 — 可自维持经济还是燃烧经济

- **背景**: Balance Sheet 显示 Standard free_upkeep 后全阶段净亏损，但 Resource Ledger 声称 2000+ Full economy “自维持”。这是设计目标层面的分歧，不只是参数 typo。
- **方案A: 可自维持 / break-even corridor** — **推荐**。重调维护费、收入、RCL/PvE/效率收益，使 5–10 房高效代码可小幅正收益，20 房顶尖代码+PvE 接近平衡，50 房明显亏损形成 soft cap。
- **方案B: 燃烧经济 / 储备消耗设计** — **不推荐**。保留全赤字，删除“自维持/break-even”表述，明确玩家靠储备、PvE、联盟延长生命周期，最终衰退。
- **Speaker 推荐**: A。Swarm 是持久编程世界，核心动机应是“代码优化带来可持续性窗口”，而不是所有正常成长路径都进入死亡螺旋；A 也更符合新手保护和长期策略学习。

### D2: Recycle 最终语义

- **背景**: Registry 写 Recycle `target_id`；validation 示例写 `spawn_id`；另有段落只需 `object_id`。这会破坏 command schema 与经济退款路径。
- **方案A: Self-action Recycle** — **推荐**。Recycle 回收 `object_id` 自身，不需要 `spawn_id`/`target_id`；资源退还到全局存储或 Resource Ledger 指定账户。
- **方案B: Spawn-anchored Recycle** — **不推荐**。Recycle 必须在 spawn range=1，需要 `spawn_id`，包括 structure 也必须位于 spawn 附近。
- **Speaker 推荐**: A。字段最少、类型最清晰，避免 structure 回收与 spawn 地理限制产生额外歧义；若要防远程回收滥用，可由回收延迟/退还比例而非 spawn 参数控制。

### D3: Leech/Fabricate body part、cost、resistance 权威表

- **背景**: Leech/Fabricate 已作为核心 8 个特殊攻击的一部分，但缺 validation 小节、body part 映射，并且 cost/resistance 在 gameplay/special_effect/custom_actions 间冲突。
- **方案A: 纳入核心 Special Attack Authority Table** — **推荐**。为 8 个特殊攻击建立单一权威表，字段包括 body part、range、cooldown、cost、damage/effect、resistance、counter、same-type stacking；Leech/Fabricate 作为核心条目一次性定义。
- **方案B: 保留 custom_actions/mod 化定义** — **不推荐**。Leech/Fabricate 仍由 custom_actions 定义，核心文档只保留占位或委托。
- **Speaker 推荐**: A。用户既定设计哲学是核心机制 = 最终设计直接写入文档；8 个 special attacks 已是目标设计，不能靠 mod/custom_actions 占位。

### D4: WS per-message MAC payload 格式

- **背景**: auth/security/api 文档对 WS message signature 是否包含 tick 不一致；Security reviewer 建议加入 direction/session_id 以消除跨方向/跨连接重放。
- **方案A: 扩展 canonical payload** — **推荐**。`SWARM-WS-MSG-V1\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>`，handshake signature 与 per-message signature 分开命名。
- **方案B: 最小修复为 seq/tick/body_hash** — **可接受但不推荐**。统一为 `SWARM-WS-MSG-V1\n<seq>\n<tick>\n<body_hash>`，不加入 direction/session_id。
- **Speaker 推荐**: A。A 同时解决跨 tick、跨方向、跨 session replay；成本主要是 SDK fixture 更新，收益大于复杂度。

### D5: canonical body_hash / canonical_json 策略

- **背景**: Request signature 的 `body_hash` 未定义 canonical body；command_hash 的 `canonical_json()` 未规定大整数任意精度序列化，跨语言 Go/Rust/TS 可能分叉。
- **方案A: 采用 RFC 8785 JCS + 任意精度整数约束** — **推荐**。JSON body 使用 JCS；整数不得经 IEEE 754；binary body hash raw bytes；空 body hash empty bytes；加入 u64 boundary fixtures。
- **方案B: 项目自定义 compact sorted-key JSON** — **不推荐**。自定义 `serde_json` 风格输出，并在各语言重写。
- **Speaker 推荐**: A。跨语言签名/SDK 场景应尽量采用标准 canonicalization；同时显式补足 u64/2^53 边界要求。

### D6: WASM module blob 是否 replay-critical

- **背景**: RichTraceBlob 非 replay-critical 已较明确，但 WASM module blob 在 deploy activation、安全审计、未来重新执行 replay 中地位不清。
- **方案A: Deterministic replay 不依赖 WASM blob** — **推荐**。Replay verifier 验证 FDB 记录链、module hash、activation result、terminal_state、commands_hash，不重新执行历史 WASM；module blob 缺失影响 rich/security audit，不影响 deterministic replay。
- **方案B: WASM blob 进入 replay-critical SLA** — **不推荐**。要求长期保留或可恢复 module blob，否则 replay 不完整；object store/module retention 进入 critical path。
- **Speaker 推荐**: A。符合当前 TickCommitRecord/FDB replay-critical 分层，降低对象存储对核心 replay 的耦合；安全审计可另设 module blob retention policy，但不要把 deterministic replay 建在异步 blob 上。

### D7: Rhai capabilities 省略时的默认授权语义

- **背景**: Rhai ABI 写“不写 capabilities = 全部 declared capabilities 授权”，这对服主是 least-privilege footgun。
- **方案A: Default-deny / default-safe** — **推荐**。省略 `capabilities` 仅授权 `default=true` 且模组声明的 capabilities；全部授权必须显式 `capabilities = "all_declared"` 或列出数组。
- **方案B: 保持 all-declared 默认** — **不推荐**。保留最短配置最大授权，但加强文档警告。
- **Speaker 推荐**: A。安全默认值必须符合最小惊讶原则；文档警告不能替代默认安全。

### D8: IndexMap 确定性策略

- **背景**: IndexMap 迭代顺序取决于插入顺序，不同创建路径可能导致 replay checksum 分叉。
- **方案A: 改用 BTreeMap / canonical ordered map** — **推荐**。Resource/Source 等 deterministic map 默认按 key 或 registry order 排序。
- **方案B: 保留 IndexMap + 强制 canonical insertion order** — **不推荐**。规定所有插入前按 key 或 ResourceRegistry order 排序，并由 CI spot-check。
- **Speaker 推荐**: A。A 从数据结构层消除隐式前提，减少实现者负担；B 依赖所有调用点永远记得排序，风险更高。

---

## 最终裁决

**REQUEST_MAJOR_CHANGES**

本轮不建议进入修复外的下一阶段。最小通过条件：先闭合 B1–B9 中的共识 Blocker，并对 D1–D8 逐项取得用户裁决；随后由修复任务按单事实源原则更新目标设计文档、Registry/IDL 派生链与 CI 校验约束。裁决阶段不修改设计文档。

---

## D-items 裁决记录（2026-06-21）

| ID | 裁决 | 详情 |
|----|------|------|
| D1 | **设计聚焦意图** | 设计目标已正确（自维持+边际递减）。Balance Sheet 具体数值标注为估值插图，精确参数见 spec/Resource Ledger。删除与叙事矛盾的定值 deficit 承诺 |
| D2 | **A — Self-action Recycle** | `object_id` 自身回收，不需 `target_id`/`spawn_id`。资源退还到全局存储 |
| D3 | **A — 纳入核心权威表** | Leech/Fabricate 与其他 6 种特殊攻击同表，字段含 body_part/range/cooldown/cost/damage/resistance/counter |
| D4 | **A — 扩展 canonical payload** | `SWARM-WS-MSG-V1\n<direction>\n<session_id>\n<seq>\n<tick>\n<body_hash>`，handshake 与 per-message 分签 |
| D5 | **A — RFC 8785 JCS** | canonical_json 采用 RFC 8785 JCS + 任意精度整数约束，禁止 IEEE 754 路径 |
| D6 | **A — 回放不依赖 blob** | Deterministic replay 仅依赖 FDB TickCommitRecord + keyframe/delta。WASM module blob 缺失仅影响 rich audit（audit_gap） |
| D7 | **A — Default-deny** | Rhai 省略 `capabilities` 仅授权 `default=true` 的能力。全部授权需显式声明 |
| D8 | **A — BTreeMap** | 确定性 map（Resource registry、entity iterator、player list）改用 BTreeMap。key Ord 自动保证迭代顺序 |