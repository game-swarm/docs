# R34 Speaker 闭合验证裁决

## 裁决概要

**Overall Verdict: PARTIALLY_CLOSED**

本轮 R34 是对 R33/R34 修复项的 Closure Verification，而非 clean-slate 设计评审。Speaker 已读取 task body 指定的全部 5 份报告：

- `/data/swarm/docs/reviews/R34/rev-dsv4-architect.md`
- `/data/swarm/docs/reviews/R34/rev-dsv4-apidx.md`
- `/data/swarm/docs/reviews/R34/rev-dsv4-design-economy.md`
- `/data/swarm/docs/reviews/R34/rev-dsv4-determinism-perf.md`
- `/data/swarm/docs/reviews/R34/rev-dsv4-security.md`

5/5 reviewer 均给出 **PARTIALLY_CLOSED**。合并后裁决：

| Verdict | 票数 |
|---|---:|
| ALL_CLOSED | 0 |
| PARTIALLY_CLOSED | 5 |
| NOT_CLOSED | 0 |

Speaker 额外对若干互相矛盾的报告结论做了当前文档交叉核验：`host_get_random`、`MainActionQuotaExceeded`、Arena tournament 残留、Terminal 市场交易残留、`omitted_count` 等在当前 `/data/swarm/docs` 中已不同于部分 reviewer 记录。此类条目在下文标注为“当前文档已修正/报告陈旧”。

最终结论：**PARTIALLY_CLOSED**。存在 6 个仍需修复的阻塞/高优先级缺口，另有若干 Medium/Low 可直接闭合或 deferred。

## 共识未闭合项（CV-B1..CV-B6）

### CV-B1: D7 special-attack-table 仍未闭合

- **状态**: NOT_CLOSED
- **来源 reviewer**: Architect, API/DX, Design/Economy CrossCheck
- **问题描述**: `specs/reference/special-attack-table.md` 已存在，但 canonical 表仍不是 8 个 IDL special_attack 的一致权威表。当前表包含 Leech/Fabricate/Overload/RangedAttack/Boost/Jammer/Shield/Repair，缺失 IDL special_attack 的 Hack、Drain；同时将 core action RangedAttack/Heal/Repair 混入 special attack canonical table。Leech/Fabricate 参数还与 `02-command-validation.md` 不一致。
- **当前证据**:
  - `specs/reference/special-attack-table.md:16` Leech cost=150、damage type=Kinetic。
  - `specs/core/02-command-validation.md:800` 起 Leech cost=300、damage_type=Corrosive。
  - `specs/reference/special-attack-table.md:17` Fabricate cost=500、cooldown=300。
  - `specs/core/02-command-validation.md:814` 起 Fabricate cost=2000 Energy + 500 Matter、cooldown=500。
  - `specs/reference/special-attack-table.md:49` 的映射表显示 Hack/Drain 不在 canonical table，RangedAttack/Repair 被列入。
- **影响范围**: special attack 参数权威源、IDL/Registry/Validation 一致性、counterplay meta、实现 codegen。
- **修复方向建议**: 以 IDL indices 14–21 为唯一行集重写 canonical table：Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate。删除 RangedAttack/Repair/Boost/Jammer/Shield 作为 canonical special_attack 行的混入，或将其另列为 legacy alias，不计入 8 special attacks。同步 `02-command-validation.md`、`api-registry.md` 和 `07-world-rules.md` 的参数与引用。

### CV-B2: D3 Overload target_id 类型仍未闭合

- **状态**: NOT_CLOSED
- **来源 reviewer**: API/DX, Architect CrossCheck
- **问题描述**: Overload 语义目标是 PlayerId/fuel budget，但 IDL 仍使用 EntityId，validation 文档按 player-level visibility 描述。
- **影响范围**: SDK 类型生成、validation 函数签名、可见性规则、玩家级 fuel budget 操作。
- **修复方向建议**: 将 `game_api.idl.yaml` 中 Overload 的 `target_id` 改为 `PlayerId`，并明确 PlayerId visibility predicate；若保留 EntityId，则必须重写 validation 语义为“由可见 entity 推导 owner player”，并声明 fuel budget 目标如何解析。

### CV-B3: S-H9 SWARM-DEPLOY-V1 canonical payload 缺失

- **状态**: NOT_CLOSED
- **来源 reviewer**: Security
- **问题描述**: 全文档未找到 `SWARM-DEPLOY-V1` 定义。`auth_api.idl.yaml` 有通用 `SWARM-REQUEST-V1`，但 deploy 专用的 certificate/audience/expiry/module/fdb counter binding 未定义。
- **Speaker 当前核验**: 在 `/data/swarm/docs` 中搜索 `SWARM-DEPLOY-V1` 为 0 结果。
- **影响范围**: deploy 签名安全、证书绑定、重放防护、audience binding、模块哈希绑定。
- **修复方向建议**: 在 `game_api.idl.yaml` §Deploy 或 `auth_api.idl.yaml` 增加 `SWARM-DEPLOY-V1` canonical payload，覆盖 method/path/body_hash/timestamp/nonce/certificate_id/player_id/audience/deploy_id/module_hash/fdb_version_counter_predicted，并同步 api-registry 与安全文档。

### CV-B4: R33 B2 global_deposit_delay 仍缺失于 Resource Ledger

- **状态**: NOT_CLOSED
- **来源 reviewer**: Design/Economy, Design/Economy CrossCheck
- **问题描述**: `08-resource-ledger.md` 作为经济唯一权威源，仍只定义 `global_transfer_delay = 100 tick`，未区分 `global_deposit_delay = 10` 与 `global_withdraw_delay = 100`。
- **Speaker 当前核验**: 在 `/data/swarm/docs` 中搜索 `global_deposit_delay` 为 0 结果；`08-resource-ledger.md:75` 起仅有 fee 与 `global_transfer_delay`。
- **影响范围**: global storage deposit/withdraw 执行参数、经济权威链路、IDL/registry 生成。
- **修复方向建议**: 在 `08-resource-ledger.md` §2.1 拆分为 `global_deposit_delay = 10 tick` 与 `global_withdraw_delay = 100 tick`，并同步 `economy.idl.yaml`、`gameplay.md`、`economy-balance-sheet.md` 与 api-registry。

### CV-B5: P-H1 EXECUTE budget 500ms 与统一预算表冲突

- **状态**: NOT_CLOSED
- **来源 reviewer**: Determinism/Performance
- **问题描述**: `01-tick-protocol.md` §1.4 仍写 EXECUTE “硬超时天花板: 500ms”，而 §8.2 统一预算表声明 EXECUTE 不单独超时，由 COLLECT+EXECUTE 总预算控制。
- **当前证据**: `specs/core/01-tick-protocol.md:73` 起仍保留 500ms 硬天花板。
- **影响范围**: tick timeout 语义、实现 watchdog、性能目标 vs 协议硬约束。
- **修复方向建议**: 将 §1.4 的 500ms 改为引用 §8.2：EXECUTE 在 `tick_soft_deadline_ms` 与 `tick_hard_deadline_ms` 下运行，不单独超时；`World ≤400ms / Arena ≤50ms` 仅为性能目标。若需要独立 watchdog，应在 §8.2 明确新增而不是与 §1.4 冲突。

### CV-B6: P-H5 admission hysteresis 仍非对称

- **状态**: NOT_CLOSED
- **来源 reviewer**: Determinism/Performance
- **问题描述**: admission control 降级为 10%/10 tick，恢复为 5% 且需 30+ consecutive ticks，仍可能导致 burst 后长期降级容量。
- **影响范围**: capacity recovery、竞技容量、公平性、负载稳定性。
- **修复方向建议**: 将恢复条件对称化（例如 <50% SLO for 10 ticks → +10%），并可增加 <25% SLO 快速恢复或 admin override。若维持非对称，需要明确这是设计意图并给出稳定性证明。

## 已闭合的重要项

| 项目 | 状态 | 来源 |
|---|---|---|
| B3/D2/B7 combat deferred reducer 与 HP writer intent model | CLOSED | Determinism/Performance |
| D11 per-player snapshot + critical reserve 基础合同 | CLOSED with Medium note | Determinism/Performance |
| D12 T2/T3 核心化、hash chain、logical clock | CLOSED | Architect, Determinism/Performance |
| B5 经济权威源统一结构 | CLOSED | Design/Economy |
| D4 Standard 经济中期自维持区间 | CLOSED | Design/Economy |
| D6 Deploy feedback polling-only | CLOSED | Design/Economy |
| D-H2 Allied Transfer restricted | CLOSED | Design/Economy |
| D-H6 Naming taxonomy | CLOSED | Design/Economy |
| B8 sandbox netns/seccomp + Store reset checklist | CLOSED | Security |
| D8 RuleMod capability-gated compatibility | CLOSED | Security |
| S-H1 transport labels | CLOSED | Security |
| S-H10 no security_class | CLOSED | Security |
| A-H3 S01 非 ClaimController | CLOSED | Architect |
| A-H5 31 systems 计数 | CLOSED | Architect |

## 当前文档交叉核验修正的报告分歧

以下条目在 reviewer 报告中存在互相矛盾或明显读取不同版本。Speaker 以当前 `/data/swarm/docs` 为准记录：

| 条目 | reviewer 分歧 | Speaker 当前核验 |
|---|---|---|
| `host_get_random` | API/DX 说已移除；Security 说存在且一致 | 当前 `/data/swarm/docs` 搜索 `host_get_random` 为 0，按当前状态视为“已移除”。Security 的 B2 结论为陈旧版本，不作为未闭合项。 |
| `MainActionQuotaExceeded` | API/DX 说仍存在 | 当前 `/data/swarm/docs` 搜索 `MainActionQuotaExceeded` 为 0，按当前状态视为已清理，不列入 blocker。 |
| Arena `tournament admin` / active tournament API | Design/Economy 报告列为残留 | 当前搜索 `tournament admin` 为 0。需注意具体 tournament tool 是否仍 active 未完全复核，但该报告列举的字符串残留已消失。 |
| Terminal `市场交易` 残留 | Design/Economy 报告列为未闭合 | 当前 `/data/swarm/docs` 搜索 `市场交易` 为 0，按当前状态视为已清理。 |
| `omitted_count` vs `omitted_categories` | API/DX 报告称分歧 | 当前搜索 `omitted_count` 为 0，`09-snapshot-contract.md` 使用 `omitted_categories`。按当前状态视为已统一到 `omitted_categories`。 |

## 方向专属 High / Medium Gap

### Architect

| ID | Severity | 状态 | 处置建议 |
|---|---|---|---|
| A-G1 TickCommitRecord §2.1 vs §7.1 字段集同名不一致 | Medium | GAP | 直接修复：区分 `TickCommitFdbRecord` 与完整 `TickCommitRecord`，或加前置说明明确 replay-critical subset。 |
| A-G2 B9 “Tier 1 容量目标” 残留 | Low | GAP | 直接修复：改为“默认容量目标”或“baseline capacity target”。 |
| A-G3 A-H1 Leech/Fabricate 未进字段级穷举表 | Medium | GAP | 直接修复：在 `02-command-validation.md` §6 增加 Leech/Fabricate 两行，与 §3.17 参数一致。 |
| A-G4 A-H4 TransferToGlobal/FromGlobal 缺 Phase 2a handler | Medium | GAP | 直接修复：在 manifest 中新增/扩展 handler，或明确路由到 economy operation pipeline 的 system_id。 |

### API/DX

| ID | Severity | 状态 | 处置建议 |
|---|---|---|---|
| API-G1 B1 工具计数 header/注释可能陈旧 | Medium | 需重新核验 | 当前报告与 Security/Architect 版本差异大，建议以当前 IDL 重新生成 api-registry 后跑 check。 |
| API-G2 E-H2 `MilliUnits` 未进 game_api type registry | Medium | GAP | 若 game_api registry 是跨 IDL 综合注册表则直接补入；若不是则说明边界。 |
| API-G3 game_api Auth shortcut 缺 schema_source/alias_of | Low | 部分可能已修 | 当前 Security 报告称 game_api 已有 schema_source/alias_of；建议 API 方向重新核验后闭合或修正。 |
| API-G4 Recycle §3.9 vs §10.3 自相矛盾 | 当前已部分修 | 当前 `02-command-validation.md:606` 与 §10.3 均为 self-action；按当前状态可闭合。 |

### Design/Economy

| ID | Severity | 状态 | 处置建议 |
|---|---|---|---|
| DE-G1 D-H5 NPC/entity tier → PvEAward budget 映射缺失 | Medium | GAP | 直接修复：在 `08-resource-ledger.md` §3 或 `modes.md` NPC 掉落小节建立显式映射表。 |
| DE-G2 R33 B1 structure cost triple inconsistency | High/Residual | 未在本轮完全核验 | 因本轮报告指出仍存在，建议下一修复 wave 专项核验所有 structure cost 权威源。 |

### Determinism/Performance

| ID | Severity | 状态 | 处置建议 |
|---|---|---|---|
| DP-G1 P-H6 Wasmtime pre-warm strategy 缺失 | Medium | GAP | 直接修复：新增双版本并行、后台预编译、覆盖率阈值、原子切换、rollback window。 |
| DP-G2 R/W matrix 多 HP writer vs S15 unique writer 文本冲突 | Medium | GAP | 直接修复：将 S15 限定为 combat damage/heal unique writer，并给矩阵加 domain-specific writer 脚注。 |
| DP-G3 critical entity reserve 无上限 | Medium | Deferred | 可进入 playtest/benchmark-gated 风险项；非本轮 blocker。 |

### Security

| ID | Severity | 状态 | 处置建议 |
|---|---|---|---|
| SEC-G1 auth.md / 03-mcp-security.md / 09-command-source.md 未纳入验证范围 | Medium | UNVERIFIED | 需要独立 closure review 覆盖 S-H4/S-H5/S-H8。 |
| SEC-G2 api-registry Auth RejectionReason staleness | Medium/High | 报告分歧 | 当前文档需以 auth_api.idl.yaml 重新生成并 check；若仍错位则作为 High 修复。 |
| SEC-G3 api-registry changelog/source version stale | Low/Medium | GAP | 同步生成器输出版本，确保 registry 反映 game_api/auth_api 当前版本。 |

## Medium / Low 处置

| ID | 项目 | Severity | 建议处置 |
|---|---|---|---|
| ML-1 TickCommitRecord 同名字段集不一致 | Medium | 直接闭合修复 |
| ML-2 `Tier 1 容量目标` 残留 | Low | 直接闭合修复 |
| ML-3 Leech/Fabricate §6 穷举表缺行 | Medium | 直接闭合修复，依赖 CV-B1 参数统一 |
| ML-4 TransferToGlobal/FromGlobal handler 缺口 | Medium | 直接闭合修复 |
| ML-5 PvE faucet tier/budget 映射缺失 | Medium | 直接闭合修复 |
| ML-6 Wasmtime pre-warm strategy | Medium | 直接闭合修复 |
| ML-7 HP writer matrix domain 注释 | Medium | 直接闭合修复 |
| ML-8 critical entity reserve size bound | Medium | deferred / playtest-gated |
| ML-9 api-registry/generator stale 版本问题 | Medium | 重新生成 + CI check |

## D-items

本轮 Closure Verification 的大部分问题可按既有 R33/R34 裁决直接修复，不需要用户重新裁决。但以下两项存在真实设计选择，Speaker 不替用户裁决：

### D1: Overload target model

- **背景**: API/DX 指出 Overload 语义目标是玩家 fuel budget，但 IDL 使用 `EntityId`。修复可走 PlayerId 直达或 EntityId 推导。
- **方案A: `target_id: PlayerId`** — 推荐。类型直接表达“玩家级 fuel budget 压制”，validation 使用 player-level visibility predicate。
- **方案B: 保留 `EntityId`，由可见 entity 推导 owner player** — 不推荐。兼容旧 wire schema，但语义绕行，易产生“攻击哪个 entity 触发玩家预算”歧义。
- **Speaker 推荐**: A。理由：Overload 的效果域是 player fuel budget，不是 entity HP/state；IDL 类型应与效果域一致。

### D2: EXECUTE watchdog 语义

- **背景**: `01-tick-protocol.md` §1.4 的 500ms 硬天花板与 §8.2 “EXECUTE 不单独超时”冲突。
- **方案A: 删除 EXECUTE 独立硬超时，统一引用 §8.2 总预算** — 推荐。400/50ms 作为性能目标，真正截止由 soft/hard tick deadline 管理。
- **方案B: 保留 EXECUTE 独立 watchdog，但在 §8.2 正式定义** — 可选但不推荐作为默认。需要明确定义 abort 语义、partial apply rollback、FDB commit 行为。
- **Speaker 推荐**: A。理由：当前设计已有 COLLECT+EXECUTE 总预算，单独 500ms 会制造实现分叉；若未来确需 watchdog，应作为新设计完整引入。

## CrossCheck 补漏发现

无独立 Phase 2 补充报告。本轮补漏来自 5 份 closure verification 报告的 CrossCheck 与 Speaker 当前文档核验：

- 当前文档状态与部分 reviewer 报告存在版本漂移，应在下一轮修复前先跑一次生成器/搜索核验，避免修复已消失的字符串残留。
- `special-attack-table.md` 虽已创建，但内容仍未满足“8 IDL special_attack canonical table”的闭合标准，是本轮最高优先级修复。
- `SWARM-DEPLOY-V1` 与 `global_deposit_delay` 均为“搜索 0 结果”的确定缺失，应直接修复。
- 若 `api-registry.md` 由 IDL 生成，当前多份报告反复出现 registry stale，说明 generator/check CI 仍未成为可靠门禁。

## 最终裁决

**PARTIALLY_CLOSED**

- 共识/高优先级未闭合项：6
- D-items：2
- 直接修复 Medium/Low：9
- 已闭合重要项：13+

下一步建议：开启 R35 closure-fix wave，优先修复 CV-B1..CV-B6；其中 CV-B1、CV-B3、CV-B4 可直接按既有裁决修复，CV-B2 与 CV-B5 等待 D1/D2 用户裁决或采用 Speaker 推荐方案后落文档。
