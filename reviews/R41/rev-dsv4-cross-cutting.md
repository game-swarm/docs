# R41 Cross-Cutting 评审 — rev-dsv4-cross-cutting

**评审日期**: 2026-06-30
**评审范围**: 跨文档术语一致性、引用完整性、spec↔design 对齐
**模型**: deepseek-v4-pro

---

## 1. Verdict

**CONDITIONAL_APPROVE**

存在 3 个 Critical 级别问题（Gateway 语言冲突、已移除组件残留引用、Rhai 移除声明矛盾），需要用户裁决后修正。High/Medium 问题可并行修复。整体设计文档的术语和引用框架基本完整，核心技术方向一致。

---

## 2. 发现的问题

### Critical

#### C1: Gateway 组件语言冲突 — Go vs Rust

- **文件**: `design/README.md` L82 vs `design/auth.md` L52
- **描述**: README 架构图中标注 "网关 (Go)"，而 auth.md 架构图标注 "Gateway (Rust)"，并包含 "Certificate Auth handler" 子组件。两者描述同一 Gateway 组件但使用不同语言标签。
- **影响**: 这是读者建立技术栈心智模型的入口点。两个文档对同一组件的语言声明矛盾，会导致实现者/评审者产生根本性混淆——Gateway 到底是用 Go 还是 Rust？auth.md 中嵌套的 Certificate Auth handler 暗示 Gateway 是 Rust（因为 Rust 实现 certificate 验证更合理），但 README 明确写 Go。
- **修复建议**: 需要用户决策：
  - **方案 A**: Gateway 统一为 Rust（与 auth 集成在 Rust 生态中更自然；Go 作为独立 gateway 语言需要跨进程调用 Rust cert verifier）
  - **方案 B**: Gateway 统一为 Go（保持 README 声明；auth 功能通过 sidecar/gRPC 调用 Auth Service）
  
  无论选择哪个，必须在两个文档中统一表述。

#### C2: 已移除组件在 README 中的残留引用 — Dragonfly 和 ClickHouse

- **文件**: `design/README.md` L134-L137、L170-L175
- **描述**: `design/tech-choices.md` §6 明确声明 "Dragonfly 已被移除——进程内缓存覆盖所有读加速场景"，§7 声明 "ClickHouse 已被移除——per-shard 数据量不需要列式存储"。但 README 的架构图（L134-L137）仍显示 Dragonfly 和 ClickHouse 作为数据层组件，数据模型表（L170-L175）仍将 Dragonfly 列为热缓存、ClickHouse 列为分析数据。
- **影响**: README 是读者第一个接触的文档——残留的已移除组件会造成严重的误导，让新读者以为系统仍然依赖 Dragonfly Redis 和 ClickHouse OLAP。
- **修复建议**: 
  1. 架构图中数据层替换为：`redb (世界状态) | Moka Cache (进程内缓存) | redb metrics table (分析)`
  2. 数据模型表中删除 Dragonfly 和 ClickHouse 行，替换为 Moka Cache 和 redb metrics table
  3. 正文 §2.2 仓库结构中 gateway/ 标注与 C1 裁决一致

#### C3: Rhai 移除声明与 RuleMod 系统矛盾

- **文件**: `design/tech-choices.md` §3 vs `specs/core/07-world-rules.md` §5.1, `specs/reference/rhai-mod-abi.md` 全文
- **描述**: tech-choices.md §3 明确声明 "Rhai 已被移除——Bevy Plugin trait 是唯一的扩展机制"，并在对比表中将 Rhai 标记为「已移除」。然而 `07-world-rules.md` 详细定义了 Rhai 事务性执行模型、Hook 表面、Helper API、Capability 白名单、Direct ECS Writer 等完整子系统，`rhai-mod-abi.md` 更是专门为 Rhai RuleMod 编写的可实现 ABI 合同（316 行）。
- **影响**: 这是设计文档中最大的自相矛盾——tech-choices 说 Rhai 已移除且 Bevy Plugin 是唯一扩展机制，但 RuleMod 子系统大量依赖 Rhai。这两种说法不能共存。新读者会完全困惑：Rhai 到底在不在系统中？
- **修复建议**: 需要用户澄清两种解释：
  - **方案 A**: "Rhai 已被移除"仅指**玩家代码扩展层**——即之前可能存在过的 Rhai 玩家脚本路径被移除，玩家只能通过 WASM 控制 drone。RuleMod（世界规则）使用 Rhai 是独立子系统。tech-choices 需要将声明精确化为："Rhai 玩家脚本已被移除——Bevy Plugin trait 是唯一的引擎扩展机制；Rhai 仍用于 RuleMod（世界规则系统，见 rhai-mod-abi.md）"
  - **方案 B**: Rhai 完全移除，RuleMod 也改用 Bevy Plugin。这意味着 07-world-rules.md 和 rhai-mod-abi.md 需要重写为 Bevy Plugin 模型。
  
  目前两套文档质量都很高（Rhai RuleMod ABI 尤为详尽），倾向方案 A（精确化声明）。但需要用户裁决。

### High

#### H1: 跨文档相对路径引用错误

- **文件**: 多个 design/ 文档
- **描述**: 以下引用使用了不正确的相对路径（从 `design/` 目录出发）:
  - `design/interface.md` L9: `[API Registry](specs/reference/api-registry.md)` → 应为 `../specs/reference/api-registry.md`
  - `design/interface.md` L29: `[auth_api.idl.yaml](specs/reference/auth_api.idl.yaml)` → 应为 `../specs/reference/auth_api.idl.yaml`
  - `design/tech-choices.md` L3: 四个引用均从 `specs/` 开始 → 应为 `../specs/`
  - `specs/core/07-world-rules.md` L3: `design/gameplay.md` → 应为 `../../design/gameplay.md`
  - `specs/reference/commands.md` L7: `specs/gameplay/08-api-idl.md` → 应为 `../gameplay/08-api-idl.md`
- **影响**: 在文件系统或 GitHub 渲染中这些链接无法正确跳转，降低文档可用性。
- **修复建议**: 全局修正所有相对路径，确保从每个文件的所在目录出发路径正确。可编写 CI 检查脚本（linkcheck）在 PR 时自动检测死链。

#### H2: 仓库根路径假定不一致 — `docs/` vs 无 `docs/`

- **文件**: `design/README.md` L144-L157 vs 实际文件布局
- **描述**: README §2.2 仓库结构以 `swarm/` 为根，下设 `docs/`、`engine/`、`sandbox/` 等。但评审文件布局是 `/tmp/swarm-review-R41/design/`、`/tmp/swarm-review-R41/specs/`——没有 `docs/` 中间层。`design/README.md` L142 注释 `# 设计文档、技术规范` 表明这些文件应在 `docs/` 下，但 L144-L145 的行内路径 `docs/design/` 和 `docs/specs/` 与实际扁平化布局不一致。
- **影响**: 路径引用混乱。如果实际仓库使用 `docs/design/` 和 `docs/specs/` 结构，则所有跨文档引用路径需要额外一级 `docs/` 前缀。如果使用扁平结构（design/ 和 specs/ 在根目录），则 README §2.2 需要修正。
- **修复建议**: 需要用户确认实际仓库结构。目前 `specs/reference/rhai-mod-abi.md` 中的引用路径 `specs/core/07-world-rules.md` 表明假定无 `docs/` 层级。建议所有文档统一使用 `docs/` 层级（更标准的 Rust 项目结构），或统一不使用 `docs/`。

#### H3: Depot 建筑类型 — engine.md 结构定义 vs world-rules 配置不一致

- **文件**: `design/engine.md` §3.1 控制器升级表 vs `specs/core/07-world-rules.md` §7.2
- **描述**: engine.md RCL 升级表中 RCL 3 解锁 "Storage, Depot"，但 engine.md §3.1 Structure 结构体定义中没有 Depot 专属字段，只有通用的 `structure_type: StructureType`。07-world-rules.md §7.2 列出了 13 种基础建筑类型，包含完整的 Depot 配置（含 `repair_capacity`、`repair_range`、`repair_aging` 等字段）。Depot 的维修能力（repair_aging=5）与 Controller 的 repair 形成两种不同的维修路径——这在 engine.md §3.4.5 中完全没有提及。
- **影响**: engine.md 的维修公式只描述了 Controller repair，没有提及 Depot 的维修能力。实现者只看 engine.md 会遗漏 Depot 维修路径。
- **修复建议**: engine.md §3.4.5 需增加 Depot 维修说明，与 Controller repair 区分清楚（Depot 消耗资源、有独立容量、可被占领）。

### Medium

#### M1: Fuel 计量术语漂移 — "CPU 指令计数" vs "wasmtime fuel units"

- **文件**: `design/README.md` L43 vs `design/engine.md` §3.4.2 L340-L344
- **描述**: README L43 对比表中写 "CPU 指令计数（fuel metering）"，暗示是真实 CPU 指令级计量。但 engine.md §3.4.2 明确澄清 fuel 是 wasmtime fuel units，"非 CPU instructions 或真实时间"，且 "不同 wasmtime 版本/配置的 fuel 消耗不可直接比较"。术语从 "CPU 指令计数" 漂移到 "wasmtime fuel units" 可能造成读者误解。
- **影响**: 低——engine.md 有详细解释。但 README 作为入口文档应避免过度简化导致误导。
- **修复建议**: README L43 改为 "Fuel 计量（WASM 指令权重，确定性）" 或类似表述，避免 "CPU 指令计数" 这个不精确的说法。

#### M2: Controller 维修硬上限公式 — engine.md vs world-rules.md

- **文件**: `design/engine.md` §3.4.5 vs `specs/core/07-world-rules.md` §7.3 L847
- **描述**: engine.md §3.4.5 描述的维修约束为物理约束：repair_range、repair_capacity、drone 物理分布——并明确 "移除全局 repair cap"。而 07-world-rules.md §7.3 L847 引入了一个硬上限公式：`max(0, age + 1 - min(0.5, controller_count × 0.5))`—"多个 Controller 的总 age 回退量不超过每 tick 自然增长的 50%"。这个公式出现在 world-rules 中但 engine.md 没有提及。
- **影响**: 如果 engine.md 声称移除了全局 repair cap 但 world-rules 仍施加 50% 增长上限，这是一个跨文档逻辑冲突。需要确认：engine.md 的 "移除全局 repair cap" 是否指 D7 决策？如果是，world-rules 的 50% 上限是新增还是残留？
- **修复建议**: 需要用户裁决：50% 上限是目标设计还是世界可配置参数。engine.md 和 world-rules.md 需要在此点上对齐。

#### M3: special-attack-table.md 中 Body Part 字段与 world-rules 不完全对齐

- **文件**: `specs/reference/special-attack-table.md` vs `specs/core/07-world-rules.md` §7.1
- **描述**: special-attack-table.md 中 Hack 使用 `Claim` body part，Fortify 使用 `Tough` body part。world-rules.md §7.1 的 body part 定义中，Claim 的 action 绑定为 `ClaimController`（不包含 Hack），Tough 只有被动效果无 action。Hack 和 Fortify 作为 ActionRegistry 中的 action 通过 `world.toml` 的 `[[custom_actions]]` 配置，其 body part 绑定在 world-rules 中定义——但 special-attack-table 作为 canonical 表固定了这些绑定。如果服主修改 body part 绑定，special-attack-table 会过时。
- **影响**: 低——canonical 表定义默认值，world.toml 可覆盖。但需要在表中标注哪些字段是可配置的。
- **修复建议**: special-attack-table.md 增加一列标注哪些参数是 world.toml 可覆盖的。

### Low

#### L1: 架构图 Gateway 子组件差异

- **文件**: `design/README.md` §2.1 架构图 vs `design/auth.md` §3 架构图
- **描述**: README 架构图中 Gateway 的子组件为 "WS Hub | Auth (CA/CSR) | API Router"，auth.md 中 Gateway 只标注 "Certificate Auth handler" + 一组 /auth/* 路由。两个架构图对 Gateway 内部结构的详细程度不同。
- **影响**: 低——不同文档关注不同视角是合理的，但标注应一致。
- **修复建议**: 统一 Gateway 子组件描述或明确标注 "简化视图"。

#### L2: `design/README.md` L5 引号不一致

- **文件**: `design/README.md` L5
- **描述**: 「你的代码就是你的军队。Write once, fight forever.」— 中文部分使用中文弯引号「」，但视觉上在终端可能渲染异常。
- **影响**: 微不足道。
- **修复建议**: 统一使用 ASCII 引号或保持当前风格（无功能影响）。

---

## 3. 亮点

1. **术语表（Glossary）设计优秀** — `design/README.md` 附录 C 提供了 8 个关键术语的精确定义（TickCommitRecord、RichTraceBlob、ReplayArtifact、RawCommand、CommandIntent 等），每个术语标注了存储层。这极大减少了跨文档术语歧义。

2. **API Registry 单一事实源模式** — `api-registry.md` 作为所有 API 合约的权威源，清晰标注 IDL 来源、CI gate、禁止手写原则。其他文档（commands.md、host-functions.md、mcp-tools.md）严格引用 Registry 而非重新声明——这种纪律性在大型项目中至关重要。

3. **Rhai RuleMod ABI 合同详尽** — `rhai-mod-abi.md` 是一份高质量的 ABI 合同文档：包含事务性语义、9 个 hook 完整定义、query/actions API、13 个 capability 白名单、6 级错误层次、签名验证流程、CI 校验要求。可直接作为实现合同使用。

4. **special-attack-table.md 设计良好** — 11 个 action 的 canonical 参数表包含 IDL Index（跨文档权威键）、反制手段、校验规范引用——信息密度高且可验证。

5. **确定性数据结构声明清晰** — engine.md §3.3 明确声明 `BTreeMap`（跨平台一致）、`IndexMap`（插入顺序确定）、禁止 `std::HashMap`。这是确定性系统的核心约束，表述准确无误。

6. **Auth 文档职责分离明确** — auth.md §3 的 "职责分离" 表清晰列出 Auth Service、Engine、Gateway 各自持有和不持有的数据/密钥——对安全审计者非常友好。

---

## 4. CrossCheck

以下为我方向范围外但怀疑可能有问题的事项，建议对应方向检查：

- **CX-1: Gateway 语言冲突** → 建议 **Speaker** 在 Phase 2 汇总时协调 C1。当前 README 说 Go、auth.md 说 Rust。需要单一决策。

- **CX-2: Rhai 移除 vs RuleMod** → 建议 **架构师评审员 (rev-dsv4-architecture)** 检查 tech-choices §3 的 "Rhai 已被移除" 声明是否与 07-world-rules.md 的 RuleMod Rhai 系统冲突。如果两者并存但用途不同，tech-choices 需要精确化声明范围。

- **CX-3: Depot 维修路径缺失** → 建议 **游戏机制评审员 (rev-dsv4-gameplay)** 检查 Depot 的 repair 能力是否与 Controller repair 形成完整的维修体系。engine.md §3.4.5 只描述了 Controller repair。

- **CX-4: 50% 维修上限冲突** → 建议 **架构师评审员** 检查 engine.md §3.4.5（"移除全局 repair cap" — D7 决策）与 07-world-rules.md §7.3（50% 增长上限）之间的矛盾。需要用户裁决哪一个是对的。

- **CX-5: README 架构图 DRAGONFLY/CLICKHOUSE 残留** → 建议 **Speaker** 汇总 C2，确保 README 架构图与 tech-choices 的组件清单对齐。

- **CX-6: 文档根路径 (docs/ vs 扁平)** → 建议 **Speaker** 在 Phase 2 协调 H2——统一所有跨文档引用的路径前缀假设。

- **CX-7: Controller upgrade 表重复** → 建议 **Speaker** 检查 engine.md §3.1 和 07-world-rules.md §7.3 中两处 RCL 表的权威性。若出现分歧，需要指定权威源。