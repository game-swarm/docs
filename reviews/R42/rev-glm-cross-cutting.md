# R42 评审报告 — rev-glm-cross-cutting

> **方向**: Cross-Cutting（跨文档一致性、术语漂移、链接完整性、IDL/Registry 对齐）
> **模型**: GLM-5.2
> **评审范围**: design/ + specs/ + 根目录 *.md（全量阅读 34 文档 + 3 IDL YAML）
> **评审原则**: Phase 1 独立评审，不做跨方向交叉对比。设计即终态，不考虑实现难度。

---

## 1. Verdict

**CONDITIONAL_APPROVE**

文档体系整体架构清晰、跨文档引用网络完整（0 broken links）、权威源声明体系（Registry/Ledger/Manifest 三层权威）运行良好。但存在若干数值漂移、术语残留和 schema 字段不一致问题，均为非阻塞但必须在 fix wave 中闭合。

---

## 2. 发现的问题

### C-C1 [Critical] — `omitted_count` vs `omitted_categories` schema 分叉

**文件**:
- `specs/core/snapshot-contract.md:45-56` — 定义快照截断字段为 `omitted_categories`（对象：`{entities, resources, events}`）
- `specs/security/visibility.md:94,377-391` — 定义快照截断字段为 `omitted_count`（标量整数），并基于此字段定义了分桶脱敏规则
- `specs/reference/api-registry.md:286` — `swarm_get_snapshot` 输出 schema 声明为 `omitted_categories`

**问题**: 同一截断机制在 snapshot-contract（权威源，§1 自称"snapshot truncation 的唯一权威"）和 visibility.md 中使用了**不同的字段名和不同的数据结构**。snapshot-contract 用 `omitted_categories` 对象分三类计数；visibility.md §10.2 的整个脱敏讨论基于 `omitted_count` 标量字段，甚至提出了分桶映射表（`few`/`some`/`many`/`extreme`）。api-registry 侧与 snapshot-contract 一致用 `omitted_categories`。

**影响**: WASM SDK 生成时无法确定快照 schema 到底含哪个字段。若实现者按 visibility.md 的 `omitted_count` 分桶逻辑实现，与 snapshot-contract 的 `omitted_categories` 精确计数冲突；反之亦然。这是设计层面未闭合的 schema 分叉，不是命名差异——数据结构完全不同。

**修复建议**: 统一到 snapshot-contract 的 `omitted_categories` 对象结构（已是权威源 + registry 对齐）。visibility.md §10.2 的脱敏讨论应改为：对 `omitted_categories` 中每个类别的整数值应用分桶映射。删除 visibility.md 中独立的 `omitted_count` 标量定义。

---

### C-H1 [High] — `specs/future/` 幽灵目录引用

**文件**:
- `README.md:16` — "查看技术规范 | `specs/` — core / security / gameplay / **future**"
- `README.md:39` — "├── future/  扩展路线 (T2 增量快照/T3 分片)"

**问题**: `specs/future/` 目录**不存在**。`specs/core/incremental-snapshot.md` 和 `specs/core/shard-protocol.md` 的文件头均明确标注"R33 D12: 原 Tier 2/3 内容，现已纳入核心设计。移除所有 Tier/未来/候选/待定标签"——即 T2/T3 已迁入 `specs/core/`。但根 README.md 仍保留对已不存在的 `specs/future/` 的引用，且仍用"T2 增量快照/T3 分片"的旧称。

**影响**: 新读者按 README 导航会找不到目录，产生文档结构混乱的印象。与 AGENTS.md 中"禁止 future/deferred 等延期词"的设计原则冲突——保留 `future/` 目录名本身就是延期语义残留。

**修复建议**: 更新 README.md 目录结构表，移除 `future/` 行，将 `incremental-snapshot.md` 和 `shard-protocol.md` 归入 `core/` 的描述中。

---

### C-H2 [High] — 旧数字前缀 spec 引用残留

**文件**:
- `specs/security/gateway-protocol.md:3` — "本文档汇聚 **specs/core/01 §4**、**specs/security/03 §2**、**specs/security/05 §3**、**specs/security/09 §7.0**"
- `specs/security/gateway-protocol.md:28,66,153,158` — 多处引用 `specs/security/09 §7.0`、`specs/security/05 §3.3`、`specs/security/03 §5`
- `specs/core/tick-protocol.md:829` — "消除跨文档（**specs/core/01**、**specs/core/04**、**specs/security/09**）分散定义"

**问题**: 所有 spec 文件已移除数字前缀（`specs/core/` 下无 `01-*.md`，实际为 `tick-protocol.md`、`wasm-sandbox.md` 等；`specs/security/` 下无 `03-*.md`，实际为 `mcp-security.md`、`visibility.md`、`gateway-protocol.md` 等）。但 gateway-protocol.md 和 tick-protocol.md 仍用旧的 `specs/core/01`、`specs/security/03/05/09` 编号引用，这些路径**无法解析到任何实际文件**。

**影响**: 读者无法按引用找到目标文档。这些引用不是"看起来旧"——它们指向的编号体系已经不存在，等于死引用。R41 grill-me 已清理过文件名前缀，但正文中的编号引用遗漏了。

**修复建议**: 将所有 `specs/core/01` → `specs/core/tick-protocol.md`，`specs/core/04` → `specs/core/wasm-sandbox.md`，`specs/security/03` → `specs/security/mcp-security.md`，`specs/security/05` → `specs/security/visibility.md`，`specs/security/09` → `specs/security/gateway-protocol.md`（或对应的实际章节）。

---

### C-H3 [High] — `FederationCertificate` 术语残留与 `Intermediate CA` 矛盾

**文件**:
- `specs/reference/auth_api.idl.yaml:340` — "FederationCertificate bridges identity across cooperating servers"
- `specs/reference/auth_api.idl.yaml:92,206,349` — 三处提及 "Intermediate CA" / "intermediate_ca_fingerprint"
- `design/auth.md:31,104,112,225` — 明确声明"单层 CA，不分 Root/Intermediate 层级"，且"4 种证书 → 2 种（ClientAuth + CodeSigning）"为已裁决的当前设计

**问题**: 
1. `FederationCertificate` 在 auth.md §9 的"旧设计 vs 当前设计"表中明确列为**已移除**的旧证书类型（旧设计有 4 种：ClientAuth + CodeSigning + Admin + Federation；当前设计 2 种）。但 `auth_api.idl.yaml:340` 仍使用 `FederationCertificate` 术语描述 federation identity 工具。这与 auth.md 的权威裁决矛盾——federation 是身份映射协议，**不需要独立证书类型**。
2. `auth_api.idl.yaml` 三处使用 "Intermediate CA"，而 auth.md 明确裁决为单层 Server CA，不分 Root/Intermediate。这两个说法直接冲突。

**影响**: IDL YAML 是代码生成的机器输入，`auth_api.idl.yaml` 中的术语会流入生成的 SDK 和 API Registry。`Intermediate CA` 术语如果进入生成的证书 envelope 类型定义，会与 auth.md 的单层 CA 设计产生实现分歧。

**修复建议**: 
1. 将 `auth_api.idl.yaml:340` 的 `FederationCertificate` 改为描述 federation identity token（非独立证书类型，由 ClientAuthCertificate 签发）。
2. 将 `auth_api.idl.yaml` 中所有 "Intermediate CA" / `intermediate_ca_fingerprint` 改为 "Server CA" / `server_ca_fingerprint`，与 auth.md 单层 CA 裁决对齐。

---

### C-H4 [High] — Gateway 实现语言矛盾（Rust vs Go）

**文件**:
- `design/README.md:84,156,204` — 架构图标注"网关 (Rust)"，仓库结构标注"gateway/ # Rust API 网关"，代码规范标注"Rust Gateway: cargo fmt + cargo clippy"
- `design/architecture.md:84` — 架构图标注"Gateway Rust (axum)"
- `specs/security/gateway-protocol.md:13` — 架构图标注"Gateway (Go, 无状态)"

**问题**: design/ 一致声明 Gateway 为 Rust 实现（axum），但 `specs/security/gateway-protocol.md` 的架构图标注为 **Go**。这是实现语言的直接矛盾。

**影响**: 技术选型文档（tech-choices.md）和仓库结构均指向 Rust Gateway。若实现者按 gateway-protocol.md 的 "Go" 描述选型，将与整个技术栈不一致。Gateway 是无状态代理——语言选择不影响游戏语义，但文档必须一致以避免实现混乱。

**修复建议**: 将 `specs/security/gateway-protocol.md:13` 的 "(Go, 无状态)" 改为 "(Rust/axum, 无状态)"，与 design/ 对齐。

---

### C-H5 [High] — Arena 胜利条件描述不一致

**文件**:
- `design/modes.md:22` — Arena 胜利条件为 5 种可配置模式：`fixed_ticks`、`destroy_all_structures`、`full_wipe`、`capture_points_consecutive`、`capture_points_cumulative`
- `specs/gameplay/feedback-loop.md:338` — "胜利条件：**摧毁敌方 Spawn**，或时限结束时分高者胜"

**问题**: modes.md 定义了 5 种可配置的 victory_condition，其中不包含"摧毁敌方 Spawn"这一单独条件（最接近的是 `destroy_all_structures`——摧毁敌方**所有建筑**，不只是 Spawn）。feedback-loop.md 的描述与 modes.md 的权威定义不一致，且 `capture_points` 模式完全未提及。

**影响**: feedback-loop.md 是面向开发者体验的规范，描述了不存在的胜利条件选项，可能导致 SDK 或 Arena UI 实现了错误的游戏结束逻辑。

**修复建议**: 将 `specs/gameplay/feedback-loop.md:338` 改为引用 modes.md 的 5 种可配置 victory_condition，或至少说"胜利条件由房主在创建时配置（见 design/modes.md §9.1.3）"，不自行声明具体条件。

---

### C-M1 [Medium] — 建筑类型列表不一致（13 vs 17）

**文件**:
- `design/gameplay.md:112` — "默认世界提供以下 **13 种**基础类型"，列出：Spawn, Extension, Tower, Storage, Link, Extractor, Lab, Terminal, Observer, PowerSpawn, Factory, Nuker, Depot
- `specs/core/world-rules.md:331-501` — 列出 **17 种**：上述 13 种 + Road, Wall, Rampart, Container
- `specs/reference/api-registry.md:855` (§10.2 BuildCost) — 列出 17 种（含 Road/Wall/Rampart/Container）

**问题**: gameplay.md 的建筑类型列表缺少 Road、Wall、Rampart、Container 四种。world-rules.md 和 api-registry.md 一致列出 17 种。gameplay.md 的"13 种"计数与权威源不符。

**影响**: 读者只看 gameplay.md 会认为只有 13 种建筑，实际引擎支持 17 种。Road 和 Wall 是基础防御/物流建筑，缺失影响新手理解。

**修复建议**: 在 `design/gameplay.md:112` 的建筑类型列表中补充 Road、Wall、Rampart、Container，更新计数为 17（或改为"以下基础类型"不写死数字）。

---

### C-M2 [Medium] — 建筑成本不一致（PowerSpawn / Depot / Nuker）

**文件**:
- `design/gameplay.md` 建筑定义块 — PowerSpawn=5000, Depot=5000, Nuker=100000
- `specs/reference/api-registry.md:855` (§10.2 BuildCost) — PowerSpawn=1200, Depot=600, Nuker=5000

**问题**: 三种建筑成本在 gameplay.md 和 api-registry.md（权威源）之间存在显著差异。特别是 Nuker（100000 vs 5000）差 20 倍，PowerSpawn（5000 vs 1200）差 4 倍。api-registry.md 声明经济数值禁止手写，由 IDL codegen 生成——应以此为准。

**影响**: gameplay.md 是游戏机制设计文档，玩家和 mod 开发者会参考其中的成本值。与 registry 不一致会导致平衡性误判。

**修复建议**: 将 `design/gameplay.md` 中 PowerSpawn/Depot/Nuker 的 cost 值同步到 api-registry.md §10.2 的权威值。或在 gameplay.md 建筑定义块中标注"成本权威值见 API Registry §10.2"。

---

### C-M3 [Medium] — RangedAttack body part cost 不一致（150 vs 100）

**文件**:
- `design/gameplay.md:879` — `cost = { Energy = 150 }`（RangedAttack body part）
- `specs/core/world-rules.md:371` — `cost = { Energy = 100 }`（RangedAttack body part）
- `specs/gameplay/api-idl.md:178` — `RangedAttack: { Energy: 150 }`

**问题**: RangedAttack body part 的生成成本在 gameplay.md 和 api-idl.md 中为 150，但在 world-rules.md 中为 100。这是同一 body part 定义在两个 spec 文件中的数值冲突。

**影响**: body part cost 影响 spawn 成本计算，不一致会导致同一世界配置在不同文档参考下产生不同经济模型。api-registry.md §10.2 SpawnCost 权威值为 RANGED_ATTACK=150，因此 world-rules.md 的 100 是错误值。

**修复建议**: 将 `specs/core/world-rules.md:371` 的 RangedAttack cost 改为 `{ Energy = 150 }`，与 gameplay.md 和 IDL 对齐。

---

### C-M4 [Medium] — world-rules.md body part 定义缺失 `age_modifier` 字段

**文件**:
- `specs/core/world-rules.md:357-393` — Attack, RangedAttack, Heal, Claim, Tough 的 body part 定义块中**均无 `age_modifier` 字段**
- `design/gameplay.md:862-904` — 同一 body part 定义块中包含 `age_modifier`（Attack=-80, RangedAttack=-50, Heal=-30, Claim=-50, Tough=+100）
- `design/gameplay.md:98` — 明确引用 `age_modifier` 定义在 `[[body_part_types]]` 中

**问题**: world-rules.md 是 `[[body_part_types]]` 的配置规范，但其 body part 示例定义缺少 `age_modifier` 字段。gameplay.md 的相同定义块包含该字段。drone lifespan 计算 `age_max = max(MIN_LIFESPAN, BASE_AGE + sum(age_modifier))` 依赖此字段——缺少它意味着 lifespan 计算无法正确执行。

**影响**: 服主按 world-rules.md 的 schema 定义自定义 body part 时不会知道 `age_modifier` 字段的存在，导致自定义 body part 无法参与 lifespan 计算。

**修复建议**: 在 `specs/core/world-rules.md` 的 body part 定义块中补充 `age_modifier` 字段（Attack=-80, RangedAttack=-50, Heal=-30, Claim=-50, Tough=+100），与 gameplay.md 对齐。字段说明表（§7.1）已有 `age_modifier` 行，但示例定义块未体现。

---

### C-M5 [Medium] — `auth_api.idl.yaml` 含 `passkey_register` 工具但 auth.md 声明 passkey 已移除

**文件**:
- `specs/reference/auth_api.idl.yaml` + `specs/reference/api-registry.md:420` — Auth API 工具列表包含 `swarm_passkey_register`
- `design/auth.md:228` — "旧设计 passkey/email/admin 三种强制恢复 → 当前设计 email 可选恢复"，即 passkey 作为**强制恢复**已移除
- `design/tech-choices.md:208` — "passkey/admin 恢复（强制）→ 砍掉强制恢复路径"

**问题**: auth.md 和 tech-choices.md 裁决移除了 passkey 作为**强制恢复**路径，但 auth_api.idl.yaml 仍保留 `swarm_passkey_register` 工具。需要确认：passkey 是完全移除，还是仅移除"强制"属性保留为可选？auth.md §6 只提"email 恢复为可选模块"，未提 passkey 可选。如果 passkey 完全移除，IDL 中的工具是残留；如果保留为可选，auth.md 应明确声明。

**影响**: 这是 D-item 级别的设计裁决未闭合——passkey 的设计定位不明确。如果保留为可选恢复方式，auth.md 需补充说明；如果移除，IDL 和 registry 需清理。

**修复建议**: 标记为 D-item 等用户裁决：passkey 是 (A) 完全移除（清理 IDL/registry 中的 `swarm_passkey_register`）还是 (B) 保留为可选恢复方式（auth.md 补充 passkey 可选模块描述）。

---

### C-M6 [Medium] — ClientAuthCertificate TTL 不一致（24h vs 15min-180d）

**文件**:
- `design/auth.md:122` — `ClientAuthCertificate` TTL = **24h**
- `specs/reference/api-registry.md:652,790` — `ClientAuthCertificate` TTL = **15 min–180 days**（world.toml 可配）

**问题**: auth.md 给出固定 24h TTL，api-registry.md 给出可配置范围 15min-180d。api-registry.md 的范围远宽于 auth.md 的固定值——24h 落在范围内，但 auth.md 没有提及可配置性或范围的上下限。

**影响**: 证书生命周期管理是安全关键路径。TTL 不一致可能导致实现者按 auth.md 硬编码 24h，失去 world.toml 可配置能力；或按 registry 实现宽范围，与 auth.md 的 24h 预期不符。

**修复建议**: 将 `design/auth.md:122` 的 TTL 从 "24h" 改为 "15min–180d（world.toml 可配，默认 24h）"，与 registry 对齐。

---

### C-L1 [Low] — `Dragonfly`/`ClickHouse`/`Rhai` 在"已移除"上下文中残留

**文件**:
- `design/architecture.md:272-274` — 在"原组件 → 替代方案"表中列出 Dragonfly/ClickHouse/Rhai（已移除组件的替代表）
- `design/tech-choices.md:136,148,50` — 在"X 已被移除"声明中提及（移除理由表）
- `design/engine.md:11` — "没有 Rhai 脚本层"

**问题**: 这些术语仅出现在"已移除"的上下文中（替代表、移除理由、对比表），不是活跃引用。从文档完整性角度这是合理的——读者需要知道为什么移除以及替代了什么。但严格按"术语漂移"标准，这些是已移除组件名的残留。

**影响**: 极低。这些是"移除说明"而非"活跃使用"，不构成实际不一致。但与新读者搜索时的术语清洁度略有影响。

**修复建议**: 保持现状。移除说明是设计决策记录的合理部分，不需要清理。仅在确认无歧义时保留。

---

### C-L2 [Low] — `allied_daily_cap` 简写值与权威公式不一致

**文件**:
- `design/economy-balance-sheet.md:230` — "daily_cap=10000"（简写）
- `specs/core/resource-ledger.md:83` — "allied_daily_cap = max(10_000, receiver_gcl × 20_000)"（权威公式）
- `specs/reference/api-registry.md:857` — 包含完整公式 + `allied_daily_cap_world_multiplier`

**问题**: economy-balance-sheet.md 简写为 daily_cap=10000，省略了 GCL 缩放和 world_multiplier。虽然 economy-balance-sheet.md 自称"只做数值验证和模式对比，不重新定义费率"，但简写值可能被误读为固定 10000 上限。

**影响**: 低。resource-ledger.md 和 api-registry.md 的权威公式完整且一致。economy-balance-sheet.md 的简写在上下文中可理解为 Standard 模式 GCL=0 时的下界值。

**修复建议**: 将 `design/economy-balance-sheet.md:230` 的 "daily_cap=10000" 改为 "daily_cap=max(10000, GCL×20000)（Standard 基线）" 或加注"见 Resource Ledger §2.1 权威公式"。

---

### C-L3 [Low] — Heal action range 在 body part 定义和 canonical table 间不一致

**文件**:
- `design/gameplay.md:886` + `specs/core/world-rules.md:379` — Heal body part `range = 1`
- `specs/reference/special-attack-table.md:18` — Heal action `Range = 3`

**问题**: Heal body part 定义中 range=1，但 special-attack-table.md 将 Heal action 的 range 标注为 3。Heal 作为 basic_combat action 通过 ActionRegistry dispatch，其 range 应由 canonical table 定义。body part 的 `range` 字段与 action 的 `Range` 语义可能不同（body part range 是默认值，action range 是权威值），但文档未明确说明两者的关系和优先级。

**影响**: 低。special-attack-table.md 自称 canonical 权威源，实现应以 table 的 range=3 为准。但 body part 定义中的 range=1 会误导不熟悉优先级规则的读者。

**修复建议**: 或将 body part 定义中 Heal 的 range 改为 3（与 canonical table 一致），或在字段说明中明确"body part range 是默认值，ActionRegistry validator 可覆盖；canonical action range 见 special-attack-table.md"。

---

## 3. 亮点

1. **零 broken links**：全仓库 151 个内部 markdown 链接全部可解析。跨文档引用网络健康，CI link-check 维护良好。

2. **三层权威源体系运行有效**：API Registry（schema authority）→ Resource Ledger（经济数学权威）→ Phase 2b System Manifest（调度权威）的权威声明体系在各文档中一致执行。多数数值引用正确指向权威源，非权威文档自觉声明"不重新声明"。

3. **IDL codegen 闭环设计**：game_api.idl.yaml / auth_api.idl.yaml / economy.idl.yaml → api-registry.md 的生成链有 CI diff gate，禁止手写分叉。codegen.md 明确定义了不可手写区域。这一设计从根本上防止了 schema 漂移。

4. **RejectionReason 48 canonical code 体系**：wire enum 稳定 + debug_detail 参数化的设计在 api-registry.md、command-validation.md、mcp-security.md、interface.md 间一致执行。condition → RejectionReason → debug_detail 映射表完整，无新增 wire variant 的裂缝。

5. **确定性合同体系完整**：Blake3 XOF PRNG + BTreeMap + 定点数 + canonical command order + system manifest hash 的确定性保证在 engine.md、tick-protocol.md、phase2b-system-manifest.md 间形成闭环。种子安全（Arena commit-reveal / World operator seed-bump）的混合方案在 tick-protocol.md 中完整定义。

6. **Phase 2a/2b 分离 + Unique Writer Contract**：combat HP 写入（S15）和 StatusState 写入（S22）的唯一 writer 约束在 manifest 的 R/W 矩阵中严格声明，并行安全证明完整。S16-S22b typed buffer 生产 + S22 串行消费的设计消除了并行写入冲突。

---

## 4. CrossCheck

以下为超出 Cross-Cutting 方向范围、怀疑存在但需目标方向确认的问题：

- **CX-1**: `auth_api.idl.yaml` 中 `swarm_passkey_register` 的设计定位（C-M5）→ 建议 **Design & Economy 方向** 检查 passkey 是否作为可选恢复方式保留在 auth 设计中，还是完全移除。

- **CX-2**: Heal action range 在 body part (range=1) 和 canonical table (range=3) 间的差异（C-L3）→ 建议 **Architect 方向** 检查 body part `range` 字段与 ActionRegistry action `range` 的语义关系和优先级规则是否在引擎层面有明确定义。

- **CX-3**: `specs/reference/auth_api.idl.yaml` 中的 "Intermediate CA" 术语（C-H3）→ 建议 **Architect 方向** 检查 auth_api.idl.yaml 的 certificate_types 定义是否与 auth.md 的单层 CA 裁决一致，确保 codegen 不会生成含 Intermediate CA 的 SDK 类型。

- **CX-4**: `design/gameplay.md` 建筑成本（PowerSpawn=5000, Nuker=100000）与 api-registry.md（PowerSpawn=1200, Nuker=5000）的差异（C-M2）→ 建议 **Design & Economy 方向** 确认哪一侧是目标设计值——Nuker 20 倍差异不是笔误级别，可能反映不同的经济平衡意图。

- **CX-5**: feedback-loop.md 的 Arena 胜利条件"摧毁敌方 Spawn"（C-H5）与 modes.md 的 5 种可配置模式（C-H5）→ 建议 **Design & Economy 方向** 确认 Arena 胜利条件是 modes.md 定义的 5 种可配置模式，还是 feedback-loop.md 描述的固定模式。

---

## 附：评审方法说明

本评审逐文件阅读了 design/（9 文档）、specs/core/（11 文档）、specs/security/（5 文档）、specs/gameplay/（3 文档）、specs/reference/（7 文档 + 3 IDL YAML），以及根目录 README.md、AGENTS.md、GETTING-STARTED.md、RUNBOOK.md。通过 ripgrep 系统扫描了 stale terms（FDB/Dragonfly/ClickHouse/Rhai/AdminCertificate/FederationCertificate）、broken links（151 个内部链接全验证）、数值一致性（body part cost / structure cost / TTL / cap 等）、术语一致性（CA 层级 / cert 类型 / Gateway 语言 / 字段名）。所有 finding 均引用 ≥2 个文件。未读取 `reviews/` 目录下任何文件。
