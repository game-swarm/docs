# R41 Phase 1 — Cross-Cutting 评审报告

**评审员**: rev-glm-cross-cutting (GLM-5.5)
**评审日期**: 2026-06-30
**评审范围**: 术语对齐、跨文档引用完整性、spec↔design 对齐、组件名称统一、IDL↔registry 一致性、旧组件残留引用

**读取文件**:
- design/README.md, design/auth.md, design/engine.md, design/interface.md, design/tech-choices.md
- specs/core/07-world-rules.md
- specs/reference/ 全部 7 个文件 (api-registry.md, commands.md, host-functions.md, mcp-tools.md, codegen.md, special-attack-table.md, rhai-mod-abi.md)

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在多处 Critical 级跨文档矛盾，最突出的是 design/engine.md + tech-choices.md 与 specs/core/07-world-rules.md + specs/reference/rhai-mod-abi.md 之间关于模组系统架构的完全对立（Bevy Plugin 静态编译 vs Rhai 脚本 + .swarm-mod 包）。其次为认证证书类型数量、PoW 难度、TTL 范围、Gateway 实现语言等 design↔registry 直接冲突。这些问题必须由用户裁决后统一。

---

## 2. 发现的问题

### CC-1 [Critical] — 模组系统架构根本性矛盾：Bevy Plugin vs Rhai

**涉及文件**:
- `design/engine.md` §3 (line 11): "扩展机制：Mod = Bevy Plugin，静态编译进 Engine 二进制。这是唯一的扩展机制——没有 Rhai 脚本层。"
- `design/tech-choices.md` §3 (line 50): "Rhai 已被移除——Bevy Plugin trait 是唯一的扩展机制。"
- `design/tech-choices.md` §3 模型 (line 54-67): Mod = Rust crate implementing Bevy Plugin trait, `cargo build --features`
- `specs/core/07-world-rules.md` §1 (line 7): "规则模组是**可安装的 Rhai 脚本 + 声明式配置**"
- `specs/core/07-world-rules.md` §5.1 (line 312+): 完整 Rhai 事务性执行模型
- `specs/reference/rhai-mod-abi.md`: 完整 Rhai RuleMod ABI 合同（9 hooks, 8 query helpers, 5 actions, 13 capabilities）
- `design/README.md` §2.2 (line 149-160): mods 表述为 git submodule，但 .swarm-mod 包含 Rhai 脚本

**问题描述**: design 文档（engine.md, tech-choices.md）明确声明 Rhai 已移除，唯一扩展机制是 Rust Bevy Plugin 静态编译。但 specs 文档（07-world-rules.md, rhai-mod-abi.md）定义了一套完整的 Rhai 脚本模组系统——包含 .swarm-mod 打包格式、mod.toml hooks 声明、RhaiActionBuffer 事务语义、9 个 hooks、AST 节点预算等。两个体系中模组的内容完全不同：前者是 Rust crate，后者是 .rhai 脚本文件。

**影响分析**: 这是整个文档集中最严重的跨文档矛盾。实现者无法确定模组系统的目标架构。两套系统的分发方式（git submodule + cargo build vs .swarm-mod tar.gz + swarm mod install）、执行模型（编译期静态 vs 运行时 Rhai 解释）、安全边界（编译期类型安全 vs AST 预算 + capability gate）均完全不同。

**修复建议**: 由用户裁决目标设计——是 Bevy Plugin 静态编译，还是 Rhai 脚本系统，还是两者并存（Rhai for RuleMod, Bevy Plugin for engine-internal mods）。裁决后统一所有文档。如选 Rhai，需删除 engine.md/tech-choices.md 中 "Rhai 已被移除" 的声明；如选 Bevy Plugin，需重写 07-world-rules.md §5.1 和 rhai-mod-abi.md。

> **D-ITEM 标记**: 此项需用户权威裁决。用户历史设计哲学（R27, 2026-06-20）中说"扩展/复杂变体 = Rhai mod 实现"，暗示 Rhai 是目标设计。但 engine.md/tech-choices.md 的"设计即终态"声明与 specs 直接矛盾，需确认哪一方代表当前目标状态。

---

### CC-2 [Critical] — 证书类型数量矛盾：2 种 vs 4 种

**涉及文件**:
- `design/auth.md` §4.2 (line 116-125): "用途隔离——`ClientAuthCertificate` 和 `CodeSigningCertificate` 是仅有的两种证书类型"
- `design/auth.md` §9 (line 225): "4 种证书（ClientAuth + CodeSigning + Admin + Federation）→ 2 种（ClientAuth + CodeSigning）"
- `specs/reference/api-registry.md` §9 (line 788-793): 定义 4 种 Certificate Types: ClientAuthCertificate, CodeSigningCertificate, AdminCertificate, FederationCertificate
- `specs/reference/api-registry.md` §5.8 (line 650-653): 列出 AdminCertificate TTL 和 FederationCertificate TTL

**问题描述**: auth.md 明确声明只有 2 种证书类型，Admin 操作使用 ClientAuthCertificate + admin scope flag，Federation 不需要独立证书类型。但 api-registry.md 定义了 4 种独立的证书类型，各有不同的 audience 和 TTL。

**影响分析**: 认证架构的核心设计决策不一致。实现者无法确定 Admin 和 Federation 操作是否使用独立证书。

**修复建议**: 用户裁决。如 auth.md 为准（2 种），需从 api-registry.md §9 和 §5.8 移除 AdminCertificate 和 FederationCertificate。如 registry 为准（4 种），需更新 auth.md §4.2 和 §9。

---

### CC-3 [Critical] — PoW 难度矛盾：自适应 vs 固定

**涉及文件**:
- `design/auth.md` §4.3 (line 136): "难度自适应调整（`difficulty_bits_min = 20`，`difficulty_bits_max = 32`）"
- `specs/reference/api-registry.md` §3.3 note (line 415): "swarm_register_challenge.difficulty_bits 固定为 24 bits"
- `specs/reference/api-registry.md` §5.8 (line 645): "CSR challenge default difficulty = 24 bits (S-H3)"

**问题描述**: auth.md 说 PoW 难度自适应（20-32 bits），api-registry 说固定 24 bits。

**修复建议**: 用户裁决。如 S-H3 裁决（固定 24 bits）为准，更新 auth.md §4.3。

---

### CC-4 [Critical] — ClientAuthCertificate TTL 矛盾

**涉及文件**:
- `design/auth.md` §4.2 (line 122): ClientAuthCertificate TTL = 24h
- `specs/reference/api-registry.md` §5.8 (line 650): "ClientAuthCertificate TTL = 15 min–180 days"
- `specs/reference/api-registry.md` §9 (line 790): "ClientAuthCertificate TTL = 15 min–180 days"

**问题描述**: auth.md 写 24h，registry 写 15 分钟到 180 天可配。24h 不在 15min-180d 范围内的问题不大，但 auth.md 的"24h"看起来像固定值而非可配范围。

**修复建议**: 统一为可配范围表述（如 registry），auth.md 改为"默认 24h，world.toml 可配 15min-180d"。

---

### CC-5 [Critical] — Gateway 实现语言矛盾：Go vs Rust

**涉及文件**:
- `design/README.md` §2.1 (line 82): "网关 (Go)"
- `design/README.md` §4.2 (line 202): "Go: `gofmt` + `golangci-lint`"
- `design/auth.md` §3 (line 52): "Gateway (Rust)"

**问题描述**: README 说 Gateway 是 Go，auth.md 说 Gateway 是 Rust。

**影响分析**: 影响整个网关层的实现语言选择、代码规范和构建链。

**修复建议**: 确定权威语言，统一所有文档。

---

### CC-6 [High] — 架构图残留已移除组件：Dragonfly + ClickHouse

**涉及文件**:
- `design/README.md` §2.1 (line 131-137): 架构图数据层显示 `redb | Dragonfly | ClickHouse`
- `design/tech-choices.md` §6 (line 136): "Dragonfly 已被移除"
- `design/tech-choices.md` §7 (line 148): "ClickHouse 已被移除"
- `design/engine.md` §3.2 (line 221): "Engine 进程内 Moka cache 更新"（BROADCAST 阶段用 Moka 而非 Dragonfly）

**问题描述**: README 架构图仍显示已移除的缓存和分析组件。engine.md 使用 Moka cache 但架构图未反映。

**修复建议**: 更新 README §2.1 架构图，将 Dragonfly 替换为 "Moka Cache (进程内)"，移除 ClickHouse，改为 "redb Metrics Table"。

---

### CC-7 [High] — `swarm_get_server_trust` 返回 intermediate_ca_fingerprint 但设计为单层 CA

**涉及文件**:
- `specs/reference/api-registry.md` §3.3 (line 413): `swarm_get_server_trust` 输出包含 `intermediate_ca_fingerprint`
- `design/auth.md` §4.1 (line 112): "不分 Root/Intermediate 层级——单层 Server CA"
- `design/auth.md` §9 (line 224): "旧设计 Server Root CA + Intermediate CA 双层 → 单层 Server CA"

**问题描述**: 单层 CA 设计中不应存在 intermediate_ca_fingerprint。

**修复建议**: 从 `swarm_get_server_trust` 输出 schema 中移除 `intermediate_ca_fingerprint`。

---

### CC-8 [High] — mcp-tools.md 认证模型文本引用 "Server Intermediate CA"

**涉及文件**:
- `specs/reference/mcp-tools.md` (line 88): "Server Intermediate CA signs application-layer certificates"
- `design/auth.md` §4.1: 单层 Server CA，无 Intermediate

**问题描述**: mcp-tools.md 的认证模型描述仍在使用双层 CA 术语。

**修复建议**: 改为 "Server CA signs application-layer certificates"。

---

### CC-9 [High] — 建造成本大规模不一致

**涉及文件**:
- `specs/core/07-world-rules.md` §7.2: structure_types 定义了各建筑 cost
- `specs/reference/api-registry.md` §10.2 BuildCost

| 建筑 | 07-world-rules (Energy) | api-registry BuildCost | 一致? |
|------|------------------------|----------------------|-------|
| Spawn | 200 | 300 | ❌ |
| Extension | 50 | 200 | ❌ |
| Tower | 200 | 800 | ❌ |
| Storage | 500 | 500 | ✅ |
| Link | 300 | 400 | ❌ |
| Extractor | 800 | 600 | ❌ |
| Lab | 1000 | 1000 | ✅ |
| Terminal | 500 | 1200 | ❌ |
| Observer | 300 | 500 | ❌ |

此外：
- api-registry BuildCost 包含 Road=10, Wall=50, Rampart=100，但 07-world-rules §7.2 structure_types 中未定义这些类型
- 07-world-rules §7.2 有 PowerSpawn=5000, Factory=1500, Nuker=100000, Depot=5000，但 api-registry BuildCost 中未包含
- RCL 升级表（两文档中均有）提到 "Container" 和 "Road" 作为解锁建筑，但 07-world-rules §7.2 structure_types 未定义 Container

**修复建议**: 以 IDL 为权威源统一所有建造成本。补齐缺失的建筑类型定义（Road, Wall, Rampart, Container）。

---

### CC-10 [High] — Canonical Request Signature headers 不一致

**涉及文件**:
- `design/auth.md` §7 (line 192-196): 4 个 headers — `Swarm-Certificate-Chain`, `Swarm-Timestamp`, `Swarm-Nonce`, `Swarm-Signature`
- `specs/reference/api-registry.md` §9 (line 797-802): 5 个 headers — 上述 4 个 + `Swarm-Cert-Id`
- `specs/reference/api-registry.md` §9 (line 798): `Swarm-Certificate-Chain: <base64 leaf + intermediate>` — 暗示有 intermediate

**问题描述**: (1) api-registry 多出 `Swarm-Cert-Id` header。(2) api-registry 的 Certificate-Chain 值含 "intermediate"，与单层 CA 矛盾。

**修复建议**: auth.md 补充 `Swarm-Cert-Id` header；api-registry 中 Certificate-Chain 值改为 `<base64 leaf>`（移除 intermediate）。

---

### CC-11 [Medium] — world.toml 使用 f64 值但项目强制定点整数

**涉及文件**:
- `specs/core/07-world-rules.md` §2 world.toml: `decay_rate = 0.001`, `damage_multiplier = 1.0`
- `specs/core/07-world-rules.md` §7.6 damage_types: `default_resistance = 1.0`，resistance values `0.5`, `2.0`, `1.5`
- `specs/core/07-world-rules.md` §9 验证代码: `if config.combat.damage_multiplier < 1` — f64 比较
- `specs/reference/api-registry.md` §10 (line 833): "All amounts use integer types (u64/u32), all rates use BasisPoints. No f64."
- `specs/reference/api-registry.md` §0: Fixed-Point Type Registry

**问题描述**: api-registry 明确声明 "No f64"，但 world.toml 配置和 damage_types 使用 float 值。

**修复建议**: 将 world.toml 中所有 float 值转换为定点表示（如 `damage_multiplier = 10000` 表示 1.0, 用 BasisPoints）。resistance values 同理。

---

### CC-12 [Medium] — max_drones_per_player 数值矛盾

**涉及文件**:
- `specs/core/07-world-rules.md` §2 (line 94): `max_drones_per_player = 500`
- `specs/reference/api-registry.md` §5.1 (line 546): "Per-player drone cap = 50 (per-room per-player baseline)"
- `design/engine.md` §3.4.2 (line 315): "50 (per-room per-player baseline; R23 D2/B 三层 cap)"

**问题描述**: world.toml 说 500，registry/engine.md 说 50（per-room per-player baseline）。可能是三层 cap 中的不同层（per-world=500 vs per-room=50），但 world.toml 字段名 `max_drones_per_player` 未明确是哪一层。

**修复建议**: world.toml 中明确区分三层 cap 字段名（如 `max_drones_per_room_per_player`, `max_drones_per_player_world`, `max_drones_global`）或添加注释说明 `max_drones_per_player` 是 per-world 层。

---

### CC-13 [Medium] — RejectionReason 计数：声称 48 但实际枚举 49

**涉及文件**:
- `specs/reference/api-registry.md` §2 (line 88): "RejectionReason — 48 codes"，"canonical code 总数为 48"
- 实际枚举：Validation §2.2 = 28 codes (1-27 + 48), MCP §2.3 = 3 (28-30), Runtime §2.4 = 6 (31-36) = 37 game_api + 12 auth = 49

**问题描述**: 新增的 code #48 `NotEligible` 被加入 §2.2 但总计数 48 未更新为 49。code 48 的编号也跳过了 37-47 的范围，注解说"编号不冲突现有 47"暗示曾考虑过 47 作为上限。

**修复建议**: 更新计数为 49，或重新评估 #48 的编号是否应填入空缺编号（如 37）。

---

### CC-14 [Medium] — CommandAction 计数表述歧义

**涉及文件**:
- `specs/reference/api-registry.md` §1 (line 41): "包含 11 种非战斗基础操作 + Action dispatch"
- `specs/reference/api-registry.md` §1 (line 48): "变体总数: 11 个 CommandAction + ActionRegistry"
- `specs/reference/commands.md` (line 22): "11 Core + Action dispatch（11 vanilla + mod）"

**问题描述**: "11 种非战斗基础操作 + Action dispatch" 读起来是 11 + 1 = 12，但实际 §1.1(8) + §1.2(2) + §1.3(1) = 11 总变体（含 Action dispatch）。表述应改为"10 种非战斗基础操作 + Action dispatch = 11 种 CommandAction 变体"。

**修复建议**: 统一表述为 "10 non-combat operations + 1 Action dispatch = 11 total CommandAction variants"。

---

### CC-15 [Medium] — 特殊攻击表不完整

**涉及文件**:
- `specs/core/07-world-rules.md` §7.8 (line 1132-1146): 特殊攻击方式表只列 6 项 (Hack, Drain, Overload, Debilitate, Disrupt, Fortify)
- `specs/core/07-world-rules.md` §7.5 (line 965-1030): 定义了 8 个 custom_actions (含 Leech, Fabricate)
- `specs/reference/special-attack-table.md` (line 14-26): 完整 11 vanilla actions (3 basic + 8 special)

**问题描述**: §7.8 表遗漏了 Leech 和 Fabricate，与 §7.5 和 special-attack-table.md 不一致。

**修复建议**: 补全 §7.8 表，加入 Leech 和 Fabricate 行。

---

### CC-16 [Medium] — 07-world-rules.md §3 register_systems 代码示例过时

**涉及文件**:
- `specs/core/07-world-rules.md` §3 (line 156-164): 6 个系统 chain: death_mark, spawn, regeneration, combat, decay, death_cleanup
- `design/engine.md` §3.2 Phase 2b (line 248): "R30 B1：31 systems"
- `design/engine.md` §3.2: 复杂并行策略，S11-S13 combat(target partition), S16-S22b status buffers, S22 serial writer

**问题描述**: 07-world-rules.md 的 register_systems 代码示例与 engine.md 的 31-system manifest 不匹配。`combat_system` 作为单一系统出现，但 engine.md 将 combat 拆分为 attack_system, ranged_attack_system, heal_system, special_attack_reducer, damage_application 等多系统。

**修复建议**: 更新 07-world-rules.md §3 代码示例，引用 06-phase2b-system-manifest.md 中的完整系统链，或标注为"概念性示例，权威系统调度见 manifest"。

---

### CC-17 [Medium] — RangedAttack body part 成本不一致

**涉及文件**:
- `specs/core/07-world-rules.md` §7.1 (line 636): RangedAttack `cost = { Energy = 100 }`
- `specs/reference/api-registry.md` §10.2 SpawnCost (line 860): `RANGED_ATTACK = 150`

**修复建议**: 以 IDL 为准统一为 150。

---

### CC-18 [Medium] — passkey 工具存在但 auth.md 未提及

**涉及文件**:
- `specs/reference/api-registry.md` §3.3 (line 423): `swarm_passkey_register` — active tool
- `design/auth.md` §9 (line 227): "passkey/email/admin 三种强制恢复 → email 可选恢复"
- `design/tech-choices.md` §11 (line 208): "passkey/admin 恢复（强制）→ 砍掉强制恢复路径"

**问题描述**: auth.md 和 tech-choices.md 将 passkey 从"强制恢复路径"中移除，但未说明 passkey 是否仍作为可选的设备凭据。api-registry 中 `swarm_passkey_register` 仍为 active 工具。

**修复建议**: auth.md 明确说明 passkey 的状态——是完全移除还是保留为可选设备凭据。如保留，补充相关章节。

---

### CC-19 [Medium] — 07-world-rules.md §10 边界声明与代码示例矛盾

**涉及文件**:
- `specs/core/07-world-rules.md` §10 (line 1277): "核心引擎**不知道规则的存在**"
- `specs/core/07-world-rules.md` §3 (line 152-164): `WorldConfig::register_systems` 直接注册 death_mark_system, spawn_system, combat_system 等——这些是核心引擎系统

**问题描述**: §10 声称核心引擎不知道规则存在，但 §3 的代码示例中 `register_systems` 注册的是核心引擎系统（death_mark, spawn, combat 等），不是规则系统。边界模糊。

**修复建议**: §3 代码应区分"核心引擎系统注册"和"规则系统注册"。或修改 §10 措辞为"核心引擎系统不依赖规则模组的存在"。

---

### CC-20 [Low] — version_counter vs redb_version_counter 双重命名

**涉及文件**:
- `design/README.md` 附录C (line 248): 定义两者，称"语义相同但存储位置不同"
- `design/interface.md` §5.7 (line 156): 使用 `version_counter`
- `specs/reference/api-registry.md` §11 (line 882): 使用 `redb_version_counter`

**修复建议**: 统一为一个术语，或在 interface.md 中添加交叉引用说明。

---

### CC-21 [Low] — CommandAction 编号非连续

**涉及文件**:
- `specs/reference/api-registry.md` §1: 编号为 1-5, 9-13, 22（跳过 6-8, 14-21）

**问题描述**: 非连续编号暗示旧变体被移除但编号未重排。如果 IDL 使用 stable index 则可接受，但对外部读者造成困惑。

**修复建议**: 如为 stable index 设计，添加注释说明编号不连续的原因。

---

## 3. 亮点

1. **API Registry 单事实源架构**: api-registry.md 作为所有 API 合约的权威来源，配合 IDL YAML codegen + CI diff check，从机制上防止手工分叉。codegen.md 明确定义了"禁止手写区域"，是优秀的单一事实源设计。

2. **RejectionReason canonical enum + debug_detail 分离**: 将 48 (或 49) 个 canonical wire code 与丰富的 debug 上下文分离（debug_detail ≤512 bytes, detail_level 三级控制），既保持 wire enum 稳定又提供调试灵活性。命名规范（统一 InsufficientResource 单数、ObjectNotFound）消除了历史命名碎片。

3. **MCP 三口径工具统计**: `all_declared` / `active_only` / `rfc_gated` 三口径清晰区分了"IDL 声明"、"运行时可用"和"RFC 占位"，避免了工具计数歧义。

4. **Phase 2a/2b 职责分离**: engine.md 将玩家命令（Phase 2a inline, 先到先得竞争）与被动系统（Phase 2b deferred, serial spine + parallel sets）分离，ActionRegistry dispatch 只生成 intent 不直接修改 HP——这保证了确定性同时保留了竞争语义。系统 R/W matrix 和 RoomCap 生命周期约束的定义非常精确。

5. **Fixed-Point Type Registry**: api-registry.md §0 统一定义了所有定点类型（BasisPoints, ResourceRate_i64, MilliUnits 等），从源头消除 f64 跨平台舍入差异。special_param_bps / special_param_ppm 的区分（basis points vs parts-per-million）提供了不同精度需求的定点方案。

6. **Rhai RuleMod 事务性语义**（如 Rhai 确实为目标设计）: RhaiActionBuffer 的"全部成功→apply / 任一失败→丢弃"模型，配合 AST 节点预算（确定性度量）和墙钟仅用于告警，是确定性系统中处理脚本副作用的优秀设计。capability default-deny + direct_ecs_writer 的三重约束（manifest + CI + audit）也设计得周全。

7. **Deploy deploy_mutation 同步提交**: swarm_deploy 在单个 redb WriteTransaction 中原子验证+写入 manifest + 递增 version_counter，消除了异步上传路径的竞态。replay 以 version_counter 全序重放，合同清晰。

---

## 4. CrossCheck — 需要跨方向检查

| ID | 问题描述 | 建议目标方向 | 检查关注点 |
|----|---------|------------|-----------|
| CX-1 | [CC-1] Rhai vs Bevy Plugin 模组系统矛盾——engine.md/tech-choices.md 说 Bevy Plugin 唯一，07-world-rules.md/rhai-mod-abi.md 有完整 Rhai 系统 | 引擎架构方向 | 确认模组扩展机制的最终目标设计：是纯 Bevy Plugin、纯 Rhai、还是分层（Rhai for RuleMod + Bevy Plugin for engine mods）？检查 engine.md §3 和 tech-choices.md §3 中的"Rhai 已被移除"是否为过时残留 |
| CX-2 | [CC-5] Gateway 语言 Go vs Rust——README 说 Go，auth.md 说 Rust | 引擎架构方向 + 认证方向 | 确认 Gateway 的权威实现语言。检查 README §2.1 架构图、§4.2 代码规范、auth.md §3 架构图中的语言标注一致性 |
| CX-3 | [CC-9] 建造成本在 07-world-rules.md 和 api-registry.md 之间大量不一致（9 个建筑中 7 个不匹配） | 游戏机制方向 + API 方向 | 确认建造成本权威源。检查 game_api.idl.yaml 中的 BuildCost 定义，与 07-world-rules.md §7.2 structure_types 和 api-registry.md §10.2 对齐 |
| CX-4 | [CC-11] world.toml 使用 f64（decay_rate, damage_multiplier, default_resistance）但项目强制定点整数 | 游戏机制方向 + API 方向 | 确认 world.toml 配置的定点表示方案。检查 damage_types 的 resistance 值是否应改为 BasisPoints |
| CX-5 | [CC-16] 07-world-rules.md §3 register_systems 代码示例与 engine.md 31-system manifest 不匹配 | 引擎架构方向 | 确认 07-world-rules.md §3 代码示例是否应更新为引用 06-phase2b-system-manifest.md，或标注为概念性示例 |
| CX-6 | [CC-7/CC-8/CC-10] 三处独立引用 intermediate CA 但设计为单层 CA | 认证方向 | 检查所有文档中是否还有其他 "intermediate" CA 残留引用。swarm_get_server_trust output、mcp-tools.md auth model、api-registry.md §9 Certificate-Chain header 均需修正 |
| CX-7 | [CC-2/CC-3/CC-4] 证书类型数(2vs4)、PoW难度(自适应vs固定24)、TTL(24h vs 15min-180d) 三个独立认证矛盾 | 认证方向 | 集中检查 auth.md 全文与 api-registry.md §3.3/§5.8/§9 的对齐。可能需要一次 auth-focused 的一致性 pass |
| CX-8 | 07-world-rules.md §7.2 structure_types 定义 13 种但缺失 Container/Road/Wall/Rampart，而 RCL 表和 BuildCost 引用了这些建筑 | 游戏机制方向 | 确认是否应补齐这 4 种建筑类型定义，或从 RCL 表和 BuildCost 中移除引用 |

---

*评审完成。本报告为 Phase 1 独立评审，未与其他 reviewer 的评审进行交叉对比。*
