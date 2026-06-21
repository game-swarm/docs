# R34 Architect 独立评审 — R33 闭项验证

**评审员**: Architect (DeepSeek V4 Pro)
**日期**: 2026-06-21
**范围**: R33 闭项验证 — B1 / B3 / B9 / D7 / D12 / A-H1 / A-H3 / A-H4 / A-H5

---

## 1. Verdict

**PARTIALLY_CLOSED** — 9 项中 4 项完全闭合 (B1, D12, A-H3, A-H5)，1 项 Critical 未闭合 (D7)，4 项存在 Medium/High 残差 (B3, B9, A-H1, A-H4)。

---

## 2. 逐项验证

### B1: IDL → Registry → SDK 单事实源链 — ✅ CLOSED

| 检查项 | IDL 声明 | Registry 声明 | 一致性 |
|--------|---------|-------------|:---:|
| CommandAction 变体总数 | 21 (game_api) | 21 | ✅ |
| Core (1–11) | category: core, index 1–11 | §1.1 核心指令 (11) | ✅ |
| Global Storage (12–13) | category: global_storage, index 12–13 | §1.2 Economy Operation (2) | ✅ |
| Special Attack (14–21) | category: special_attack, index 14–21 | §1.3 特殊攻击 (8) | ✅ |
| ID 一致性 | Hack(14)/Drain(15)/Overload(16)/Debilitate(17)/Disrupt(18)/Fortify(19)/Leech(20)/Fabricate(21) | 完全一致 | ✅ |
| MCP Tools 计数 | game_api: 57, auth_api: 12 | Registry §3: "57 tools, 12 auth tools" | ✅ |
| Registry 交叉引用 | IDL 注释: "Canonical parameters: see special-attack-table.md" | Registry L77: "Canonical 参数表见 special-attack-table.md" | ✅ |

**Evidence**:
- `game_api.idl.yaml` L75: `total_variants: 21`
- `api-registry.md` L48: `变体总数: 21`
- `game_api.idl.yaml` L503: `total_tools: 57`
- `api-registry.md` L268: `game_api.idl.yaml (57 tools), auth_api.idl.yaml (12 auth tools)`

**结论**: IDL→Registry 链完全一致。CommandAction 变体名、索引、分类、参数均对齐。工具计数匹配。CLOSED。

---

### B3: TickCommitRecord / TickTrace / ReplayArtifact — ⚠️ GAP (Medium)

#### RichTraceBlob → audit_gap — ✅

RichTraceBlob 定位在 3 处文档中一致：
- `05-persistence-contract.md` §2.1: "缺失 → terminal_state = audit_gap（审计记录缺失，可从相邻 tick/keyframe 重建）"
- `05-persistence-contract.md` §2.2: "对象存储写入失败仅导致 terminal_state = audit_gap，绝不会导致 unreplayable"
- `05-persistence-contract.md` §7.2: Blob 损坏终端状态表 — `audit_gap` 定义为 "Blob 缺失或部分损坏，但状态可从相邻 tick 重建"

✅ RichTraceBlob → audit_gap only 在所有路径一致。

#### TickCommitRecord Schema 内部不一致 — ⚠️ GAP

`05-persistence-contract.md` 中 **同名为 "TickCommitRecord" 的结构有两套不同的字段集**：

| 位置 | 声明 | 字段集 |
|------|------|--------|
| §2.1 (L36-56) | "以下 10 个字段组成 TickCommitRecord" | commands, rejections, fuel, deploy_activation_decision, canonical_codec_version, snapshot_hash, commands_hash, state_checksum, manifest_hash, world_config_hash |
| §7.1 (L304-317) | "TickCommitRecord 结构（R16 B3 扩展）" | tick, collect_id, attempt_id, commit_id, snapshot_hash, commands_hash, wasm_status, fuel_ledger, state_checksum, system_manifest_hash |

**差异分析**:
- §2.1 独有的字段: commands, rejections, fuel, deploy_activation_decision, canonical_codec_version, world_config_hash
- §7.1 独有的字段: tick, collect_id, attempt_id, commit_id, wasm_status, fuel_ledger
- 共有字段: snapshot_hash, commands_hash, state_checksum (≈ manifest_hash / system_manifest_hash)

**影响**: 实现者无法确定 TickCommitRecord 的权威字段集。若 §2.1 是 "replay-critical FDB subset" 而 §7.1 是完整 Rust struct，应在文档中明确命名区分（如 `TickCommitFdbRecord` vs `TickCommitRecord`），而非都叫 "TickCommitRecord" 且字段不同。

**修复建议**: 
- 方案 A: §2.1 重命名为 "TickCommitFdbRecord (Replay-Critical Subset)"，明确其仅为 FDB 原子提交字段子集；§7.1 保留 "TickCommitRecord" 为完整 Rust struct
- 方案 B: 在 §2.1 前加前置说明 "以下为 TickCommitRecord 中必须在 FDB 事务中原子提交的 10 个 replay-critical 字段（完整 struct 见 §7.1）"

#### 跨文档一致性

`design/engine.md` §3.3 的 `TickInputEnvelope` 与 `05-persistence-contract.md` 的 TickCommitRecord 字段集也不同——但 TickInputEnvelope 是 replay 输入封套，属于不同语义层，非冲突。

**B3 结论**: RichTraceBlob→audit_gap ✅。TickCommitRecord 内部 schema 不一致 ⚠️ — **GAP**, severity Medium。

---

### B9: MVP/Phase/TBD 清理 — ⚠️ GAP (Low)

扫描范围: `/data/swarm/docs/design/` + `/data/swarm/docs/specs/core/`
排除: Phase 2a/2b（tick 管线阶段名）、R33/R32 引用、PLAYTEST-GATED.md

#### 已清理项 ✅

| 原残留位置 | 当前状态 |
|-----------|---------|
| `design/engine.md` L170 "目标 MVP = 500" | 已改为 "目标 = 500 活跃玩家" ✅ |
| `design/modes.md` L12 "MVP 核心" | 已改为 "✅ 核心" ✅ |
| `design/gameplay.md` L980 "MVP阶段" | 已移除 ✅ |
| `design/gameplay.md` L530 "Tier 2 特性" | 已改为 "不存在 Tier 2/Phase/Future 语义" ✅ |

#### 残存项 ⚠️

| 文件 | 行号 | 内容 | 说明 |
|------|------|------|------|
| `specs/core/02-command-validation.md` | L584 | `Tier 1 容量目标: 50 players × 10 drones = 500 total` | RESIDUAL — "Tier 1" 为开发阶段标签，非游戏机制术语（不同于 resource-ledger 的 storage_tax_tier 和 shard-protocol 的 shard tier） |

> `specs/core/09-snapshot-contract.md` L5 的 "MVP 经济边界（DH1）" 为 R15 修复项描述中的历史引用——设计文档说明修复来源，非残存阶段标记。不计入 GAP。

**B9 结论**: 主要 MVP/Phase 标签已清理。1 处 "Tier 1" 残存 — **GAP**, severity Low。

---

### D7: special-attack-table.md — ❌ NOT CLOSED (Critical)

#### GAP 1: Hack 和 Drain 缺失 — Critical

IDL 定义的 8 个 special_attack (indices 14–21):

| IDL Index | IDL Name | 在 canonical table 中？ |
|-----------|----------|:----------------------:|
| 14 | Hack | ❌ **缺失** |
| 15 | Drain | ❌ **缺失** |
| 16 | Overload | ✅ (行 #3) |
| 17 | Debilitate | ✅ (映射为 "Boost") |
| 18 | Disrupt | ✅ (映射为 "Jammer") |
| 19 | Fortify | ✅ (映射为 "Shield") |
| 20 | Leech | ✅ (行 #1) |
| 21 | Fabricate | ✅ (行 #2) |

Canonical table 列出的 8 个攻击为: Leech, Fabricate, Overload, RangedAttack, Boost, Jammer, Shield, Repair。

- **Hack 和 Drain 完全缺失** — 2/8 的 IDL special attacks 不在 canonical 参数表中
- RangedAttack (IDL index 7, category: core) 和 Repair/Heal (IDL index 8, category: core) 被列入 "special attack" 表——但它们是 core actions，不是 special_attack

**影响**: 实现者查阅 canonical 表获取 Hack/Drain 参数时找不到任何条目——必须到非 canonical 来源（02-command-validation.md, gameplay.md）查找。表标题 "8 Special Attack Canonical Table" 声称覆盖 8 个特殊攻击，但实际仅覆盖 6 个。

#### GAP 2: 参数与 02-command-validation.md 不一致 — High

| 攻击 | 字段 | canonical table | 02-command-validation.md | 冲突 |
|------|------|:---:|:---:|:---:|
| Leech | Cost (Energy) | 150 | 300 (L811) | ❌ 2× |
| Leech | Damage Type | Kinetic | Corrosive (L809) | ❌ 类型不同 |
| Fabricate | Cost (Energy) | 500 | 2000 Energy + 500 Matter (L824) | ❌ 4× + 缺少 Matter |
| Fabricate | Cooldown | 300 | 500 (L823) | ❌ |

> `07-world-rules.md` L972 也列出 Fabricate cost = {Energy: 2000, Matter: 500}，与 02-command-validation.md 一致但与 canonical table 冲突。

**影响**: 特殊攻击参数在 3 个文档间漂移。玩家无法确定 Leech 消耗 150 还是 300 Energy，Fabricate 是否需要 Matter。这些是 counterplay 决策的核心数值——不一致导致 meta 无法建立。

#### GAP 3: canonical table 内部 Validation Schema 引用错误

表格中 Leech 和 Fabricate 的 Validation Schema 列均引用 `02-command-validation.md §3.10`:

| 攻击 | Validation Schema |
|------|-------------------|
| Leech | `02-command-validation.md §3.10 派生` |
| Fabricate | `02-command-validation.md §3.10 派生` |

但 `02-command-validation.md` §3.10 是 **Hack**，不是 Leech 或 Fabricate。Leech 在 §3.17（L800-825），Fabricate 在 §3.17 末尾（L814-825）。引用错误。

**D7 结论**: Critical GAP — Hack/Drain 缺失 + 参数漂移。**NOT CLOSED**。

---

### D12: T2/T3 纳入核心 — ✅ CLOSED

| 检查项 | 状态 |
|--------|:---:|
| `specs/core/10-incremental-snapshot.md` 存在 | ✅ |
| `specs/core/11-shard-protocol.md` 存在 | ✅ |
| 文件内无 T2/T3/Tier 标签 | ✅ |
| `specs/future/` 目录已删除 | ✅ (search 0 results) |

**Evidence**:
- `10-incremental-snapshot.md` L4: `原 Tier 2 内容，现已纳入核心设计。移除所有 "Tier/未来/候选/待定" 标签。`
- `11-shard-protocol.md` L4: `原 Tier 3 内容，现已纳入核心设计。移除所有 "Tier/未来/候选/待定" 标签。`

**D12 结论**: CLOSED。

---

### A-H1: Leech/Fabricate validation in 02-command-validation.md — ⚠️ GAP (Medium)

#### 已修复 ✅

`02-command-validation.md` 现在包含 Leech 和 Fabricate 的独立校验节：
- §3.17 Leech (L800-813): 注册方式、damage_type (Corrosive)、base_damage (15)、消耗 (300 Energy)、效果 (50% 自愈)
- §3.17 Fabricate (L814-825): 注册方式、冷却 (500 tick)、消耗 (2000 Energy + 500 Matter)、效果

#### 残存 GAP ⚠️

**§6 字段级穷举校验表 (L591-613) 缺少 Leech/Fabricate 行**:

当前穷举表覆盖: Move, Harvest, Transfer, Withdraw, Build, Attack, RangedAttack, Heal, Spawn, Recycle, Hack, Drain, Overload, Debilitate, Disrupt, Fortify, ClaimController — **17 行，不含 Leech 和 Fabricate**。

Leech/Fabricate 虽然在 §3 中有逐字段校验，但在 §6 穷举表中缺失——该表是 "validate_and_apply() 单一路径中执行" 的权威校验清单。

**修复建议**: 在 §6 穷举表中加 Leech 和 Fabricate 两行，含所有权 (entity_id)、范围 (range=1)、资源 (Energy≥300 / Energy≥2000+Matter≥500)、特殊校验 (damage_type, body_parts, target HP, effect semantics)。

**A-H1 结论**: Leech/Fabricate 校验节已添加。穷举表缺行 — **GAP**, severity Medium。

---

### A-H3: S01 ClaimController removed — ✅ CLOSED

`06-phase2b-system-manifest.md` 系统清单:

| System ID | Name | Handled Commands |
|-----------|------|-----------------|
| S01 | `command_executor` | Move/Harvest/Attack/RangedAttack/Heal/Claim/Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate |
| S02 | `controller_system (phase 2a)` | Claim, UpgradeController |

**Evidence** (`06-phase2b-system-manifest.md` L26-29):
```
[S01] command_executor     (Move/Harvest/Attack/
                             RangedAttack/Heal/Claim
                             +PendingSpecialAttack)
[S02] controller_system    (phase 2a inline)
```

S01 是通用 `command_executor`，处理所有命令的基础执行（含 Claim 的基础校验）。
S02 是专门的 `controller_system`，处理 Claim/UpgradeController 的 Controller 状态变更。
S01 ≠ ClaimController — **没有名为 "ClaimController" 的 S01**。

**A-H3 结论**: CLOSED。

---

### A-H4: TransferToGlobal/FromGlobal Phase 2a handler — ⚠️ GAP (Medium)

#### 问题

`game_api.idl.yaml` 定义 `TransferToGlobal` (index 12) 和 `TransferFromGlobal` (index 13) 为 CommandAction 变体，属于 `global_storage` 类别。

`api-registry.md` §1.2 (L68-L73) 声明:
> "引擎将其路由至 Economy Operation 管线进行验证和执行"

但 **`06-phase2b-system-manifest.md` 的 Phase 2a inline handlers (S01-S06) 均不处理 TransferToGlobal/FromGlobal**:

| System | Handled Commands |
|--------|-----------------|
| S01 cmd_exec | Move/Harvest/Attack/.../Leech/Fabricate |
| S02 ctrl_2a | Claim, UpgradeController |
| S03 build | Build |
| S04 recycle | Recycle |
| S05 transfer | Transfer, Withdraw |
| S06 spawn_val | Spawn |

S05 处理 Transfer/Withdraw（本地传输），但不处理 TransferToGlobal/FromGlobal（全局存储）。

#### 影响

TransferToGlobal/FromGlobal 缺少明确的 Phase 2a handler 声明——实现者无法确定这两个命令在哪个系统中执行。Registry 说 "路由至 Economy Operation 管线" 但没有对应的 system_id 映射。Resource Ledger (S29) 在 Phase 2b 末尾执行，不负责 Phase 2a inline apply。

**修复建议**: 在 manifest Phase 2a 中新增 S05b `global_transfer_system`（或扩展 S05）明确声明 TransferToGlobal/FromGlobal 的 handler，或在 S29 resource_ledger 文档中明确声明其 inline handler 映射。

**A-H4 结论**: **GAP**, severity Medium。

---

### A-H5: system numbering corrected — ✅ CLOSED

`grep '"31 systems"' /data/swarm/docs/` → **0 results**。

当前文档中使用 "31 systems" 的位置:
- `06-phase2b-system-manifest.md` L20: `## 1. System Schedule (31 systems)` — 正确（6 Phase 2a + 25 Phase 2b = 31）
- `06-phase2b-system-manifest.md` L76: `共计 31 个 system` — 正确
- `design/engine.md` L210: `31 systems（R30 B1：Phase 2a inline 6 + Phase 2b deferred 25）` — 正确

**A-H5 结论**: CLOSED。

---

## 3. CrossCheck

| ID | 问题 | 建议方向 |
|----|------|---------|
| CX1 | D7: special-attack-table.md 缺失 Hack/Drain，参数与 02-command-validation.md 和 gameplay.md 冲突 (Leech cost 150 vs 300, Fabricate cost 500 vs 2000+500Matter, cooldown 300 vs 500) → **建议 Gameplay/Design Reviewer** 裁决 8 个特殊攻击的 canonical 参数值（以哪个文档为准），然后统一修正所有冲突文档 |
| CX2 | D7: canonical table 的 Validation Schema 列引用 `02-command-validation.md §3.10` 但 Leech/Fabricate 在 §3.17 → **建议 API/Index Reviewer** 验证所有特殊攻击的校验引用是否正确 |
| CX3 | B3: 05-persistence-contract.md §2.1 vs §7.1 TickCommitRecord 字段集不一致 → **建议 Speaker** 裁决采用方案 A（重命名区分）还是方案 B（加前置说明） |

---

## 4. 汇总

| 闭项 | 状态 | Severity |
|------|:----:|:--------:|
| B1 | CLOSED | — |
| B3 | GAP | Medium |
| B9 | GAP | Low |
| D7 | NOT CLOSED | **Critical** |
| D12 | CLOSED | — |
| A-H1 | GAP | Medium |
| A-H3 | CLOSED | — |
| A-H4 | GAP | Medium |
| A-H5 | CLOSED | — |

**关键阻塞项**: D7 (Critical) — Hack/Drain 完全缺失于 canonical special-attack-table，参数与 validation 文档冲突。此项必须修复后方可视为 R33 完全闭合。