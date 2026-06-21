# R32 API/DX 独立评审 — rev-dsv4-apidx

> 评审范围：11 份指定文档，仅方向相关子集。
> 评审原则：设计阶段评审，不考虑分阶段实现。

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 3 项 Critical 问题（跨文档计数不一致、非 canonical RejectionReason 码、host function 文档缺失），以及多项 High 问题。这些问题必须在合并前修复，否则会导致 SDK 代码生成错误、CI 检查永久失败、以及实现者无法确定正确的 wire enum。

---

## 2. 发现的问题

### Critical

#### C1. Host Function 数量跨文档不一致（三处冲突）

- **api-registry.md §4**（权威源）：`共计 6 个函数`，表格列出 6 个（含 `host_get_random`）
- **codegen.md 第 29 行**：`Host function 数量 (当前 5)`
- **host-functions.md §允许的 Import 表格（第 11–17 行）**：仅列出 5 个函数，**缺失 `host_get_random`**
- **host-functions.md §Host Call Budget（第 63–68 行）**：未单独列出 `host_get_random` 的 per-call 上限（10/tick），仅合并入「其他: 共享剩余配额」
- **host-functions.md §输出上限（第 75–81 行）**：表格缺失 `host_get_random`（256 bytes，见 api-registry.md §4.3）

影响分析：
- `codegen.md` 说当前 5 个 → SDK 代码生成器只会生成 5 个 host function binding，**不会为 `host_get_random` 生成 import stub**
- `host-functions.md` 的 import 表格是开发者实现指南的直接参考——缺失 `host_get_random` 意味着实现者会遗漏这个函数
- `host_get_random` 在 api-registry.md §4.1 表格中明确列出，但 codegen.md 和 host-functions.md 均未同步更新

修复建议：
1. 更新 `codegen.md` 第 29 行：`5` → `6`
2. 在 `host-functions.md` import 表格中增加 `host_get_random` 条目
3. 在 `host-functions.md` §Host Call Budget 中增加 `host_get_random: 10 次` 独立上限
4. 在 `host-functions.md` §输出上限中增加 `host_get_random: 256 bytes`
5. 在 `host-functions.md` 中增加 `host_get_random` 的详细签名和 domain separation 说明（参考 api-registry.md §4.1 的描述）

---

#### C2. MCP 工具数量跨文档不一致（57 vs 56）

- **api-registry.md §3 表头**（权威源，IDL 生成）：`共计 57 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)`
- **mcp-tools.md 第 16/26 行**：`Game API 小计: 56`，分组统计表合计 56
- **interface.md §4.1 第 19 行**：`56 game tools + 11 auth tools`
- **codegen.md 第 27 行**：`MCP tool 数量 (当前 56 active)`

逐类对比（api-registry.md vs mcp-tools.md）：

| 分组 | api-registry.md | mcp-tools.md | 差异 |
|------|:---:|:---:|:---:|
| Onboarding | 11 | 10 | −1 |
| Auth (game_api 内) | 3 | 2 | −1 |
| Play | 16 | 16 | 0 |
| Deploy | 7 | 7 | 0 |
| Debug | 8 | 8 | 0 |
| Admin | 6 | 6 | 0 |
| SDK | 1 | 1 | 0 |
| Arena | 5 | 4 | −1 |
| Resources | 2 | 2 | 0 |
| **合计** | **59 / 57 active** | **56** | −1 active |

> api-registry 有 59 个条目，其中 `swarm_get_terrain` 和 `swarm_get_path` 标记为 `host_only`（非活跃 MCP 工具），故活跃计数 = 57。

影响分析：
- 三个文档引用数均为 56，但权威 Registry 为 57
- v0.4.0 changelog（api-registry.md 第 932 行）明确新增了工具（Onboarding +2, Play +2, Deploy +1, Debug +1, Arena +4），但 mcp-tools.md 和 codegen.md 未完全同步
- codegen.md 本身声明「本文档中的数值需在 IDL 变更时手动更新」（第 24 行），说明本次变更后手动更新遗漏
- CI `--check` 模式会检测到 Registry 与 codegen.md 的计数不一致

修复建议：
1. 更新 `codegen.md` 第 27 行：`56` → `57`
2. 更新 `mcp-tools.md` 第 16/26 行分组统计表，对齐 api-registry.md 的分组计数
3. 更新 `interface.md` §4.1 第 19 行：`56` → `57`
4. 考虑在 CI 中增加检查：`codegen.md` 的声明计数与 `api-registry.md` 生成计数是否一致

---

#### C3. 02-command-validation.md 使用了多项非 canonical RejectionReason 码

api-registry.md §2 定义 47 个 canonical wire enum（35 game + 12 auth）。D2/B 设计决策明确：详细上下文放入 `debug_detail` 字段，**不在 wire enum 中增加新变体**。

但 `02-command-validation.md` 的逐指令校验表（§3.1–§3.15）和拒绝码表（§5.1）中出现了以下**不在 47 个 canonical code 中**的错误码：

| 出现位置 | 错误码 | 说明 |
|---------|--------|------|
| §3.1 Move | `TileBlocked` | 目标格不可通行 |
| §3.1 Move | `StillSpawning` | Drone 正在 spawning |
| §3.8 Spawn | `ExceedsRoomCapacity` | 超出房间能量上限 |
| §3.13 Debilitate | `InvalidDamageType` | 非法的伤害类型 |
| §3.13 Debilitate | `AlreadyDebilitated(damage_type)` | 已有同类型 Debilitate |
| §5.1 拒绝码表 | `MainActionQuotaExceeded` | 每 drone 每 tick 超过 1 个 main action |

此外，多处校验条件的「失败码」列标注为 `(debug_detail)`，但这些条件**在 api-registry.md §2.6 的 condition→RejectionReason→debug_detail 映射表中没有对应条目**。例如：

- `drone.fatigue == 0` → `(debug_detail)` — 疲劳条件没有 canonical mapping
- `drone.carry_used < drone.carry_capacity` → `(debug_detail)` — 无 mapping
- `target_id 是 Source` → `(debug_detail)` — 无 mapping
- `target.hits < target.hits_max` → `(debug_detail)` — 无 mapping
- `目标未被其他玩家 Hack 中` → `(debug_detail)` — 无 mapping

影响分析：
- 实现者无法确定这些条件应该返回哪个 canonical wire code
- 若 `(debug_detail)` 条件都返回同一个 generic code（如 `InvalidCommand`），SDK 无法为不同条件生成 typed exception
- 代码生成器无法从 api-registry.md §2.6 自动生成条件→错误码的完整映射表
- CI 无法自动检测文档与实现的一致性

修复建议：
1. 对 `TileBlocked`、`StillSpawning`、`ExceedsRoomCapacity`、`InvalidDamageType`、`MainActionQuotaExceeded`：决定它们是升格为 canonical wire enum 变体（添加到 IDL 并重新生成 Registry），还是降级为 `debug_detail` 字符串（映射到现有 canonical code）。若降级，需明确指定映射到哪个 canonical code（如 `TileBlocked` → `PositionOccupied` + debug_detail `"TileBlocked: ..."`，`StillSpawning` → `CooldownActive` + debug_detail `"StillSpawning: ..."`）
2. 对 `AlreadyDebilitated(damage_type)`：同样决定升格或降级，若降级需指定 canonical mapping
3. 补齐 api-registry.md §2.6 的 condition→canonical code 映射表，覆盖 02-command-validation.md 中所有标注 `(debug_detail)` 的条件
4. 确保每个校验条件都有明确的 `condition → canonical RejectionReason → debug_detail template` 三元组

---

### High

#### H1. host-functions.md 缺少 `host_get_random` 的完整文档

- **import 表格**（第 11–17 行）：仅 5 个函数，缺失 `host_get_random`
- **输出上限表**（第 75–81 行）：缺失 `host_get_random` 的 256 bytes 上限
- **Host Call Budget**（第 63–68 行）：未独立列出 `host_get_random` 的 10 tick 上限
- **详细签名节**（第 21–59 行）：没有 `host_get_random` 的签名、参数和返回说明
- api-registry.md §4.1 有 domain separation 说明（`(tick_seed, player_id, drone_id, sequence)` 种子），host-functions.md 完全缺失

影响：实现 host function binding 的开发者会遗漏该函数。

修复建议：在 host-functions.md 中补充 `host_get_random` 的完整条目（import 表、签名、输出上限、per-call 预算、domain separation 说明）。

---

#### H2. api-registry.md §2.6 条件映射表不完整

api-registry.md §2.6 声称是「所有 validation 失败遵循：condition → canonical RejectionReason → debug_detail template」的完整映射，但仅覆盖 26 个条件（对应 26 个 Validation 级 RejectionReason codes）。

`02-command-validation.md` 的逐指令校验表（§3.1–§3.15）包含约 **40+ 个校验条件**，其中至少 10+ 个条件（见 C3 列表）在 §2.6 中没有 canonical mapping。

影响：
- §2.6 的完整性声明与实际情况不符
- 代码生成器和 CI validator 无法自动校验逐指令校验表与 canonical enum 的一致性

修复建议：
1. 补齐 §2.6 映射表，使每个 `02-command-validation.md` 中的校验条件都有 canonical code → debug_detail template 映射
2. 对于确实不需要独立 canonical code 的条件（如疲劳），明确映射到最接近的 canonical code（如 `CooldownActive`）并在 debug_detail 中携带具体原因

---

#### H3. `(debug_detail)` 标记缺乏机器可读语义

`02-command-validation.md` §3 的逐指令校验表使用 `(debug_detail)` 作为失败码标记。此标记是文档约定而非机器可读符号——代码生成器或 CI 工具无法解析其含义。

影响：
- CI 无法区分「此条件映射到 canonical code X + debug_detail Y」vs「此条件没有 canonical mapping 是文档 gap」
- 代码生成器无法从此表生成条件→错误码映射

修复建议：
1. 将每行 `(debug_detail)` 替换为明确的 canonical code（如 `CooldownActive`），并在旁边注释 debug_detail 内容
2. 或在 api-registry.md §2.6 中建立完整的机器可读映射表，02-command-validation.md 只引用 canonical code 名称

---

### Medium

#### M1. codegen.md 声明手工维护引入漂移风险

codegen.md 第 24–25 行：
> ⚠️ 本文档自身为手工维护。本文档中的数值（CommandAction 数量、RejectionReason 数量等）需在 IDL 变更时手动更新。

此设计与 api-registry.md 的「全量生成、禁止手写」原则冲突。codegen.md 建议 CI 检测漂移，但自身却是手工维护——形成循环依赖。

影响：每次 IDL 变更都可能忘记更新 codegen.md（本次已发生：host function 5→6、MCP 56→57 未更新）。

修复建议：
1. 将 codegen.md 中的声明计数也纳入自动生成范围（由 `generate_api_registry.py` 同步写入）
2. 或至少将 codegen.md 第 26–34 行的「禁止手写数值」清单由 CI 自动校验与 Registry 的一致性

---

#### M2. 02-command-validation.md §7.1 退还规则表存在重复条目

第 627–637 行（§7.1 退还规则表）：

```
| `InsufficientResource` | 退 50% fuel | 竞争导致——非玩家过错 |
| `InsufficientResource` | 退 50% fuel | 同上 |
...
| `InsufficientResource` | 不退 | 玩家应计算资源 |
```

`InsufficientResource` 出现三次，其中两次退 50%、一次不退。虽然上下文可能不同（资源不足 vs 玩家应计算资源），但表格未区分场景，导致实现者无法确定行为。

影响：fuel refund 逻辑依赖于精确的拒绝原因→退款比例映射，重复且矛盾的条目会导致实现歧义。

修复建议：
1. 检查并去重 §7.1 表，为每个 RejectionReason 提供唯一的退款比例
2. 若同一 canonical code 在不同指令类型中有不同 refund 行为，需在表中明确区分（如 `InsufficientResource (Harvest)` vs `InsufficientResource (Transfer)`）

---

#### M3. api-registry.md §2 的 RejectionReason 编号与 §2.6 无直接关联

§2.2–§2.5 使用连续编号（1–35 for game, 1001–1012 for auth），但 §2.6 的映射表不使用这些编号而是使用名称。这导致 API 使用者需要通过名称查找，而非稳定的数字 ID。

影响：wire format 使用数字编码时，文档与实现之间的映射需要额外转换步骤。

修复建议：在 §2.6 映射表中增加一列「canonical code #」列出对应的数字编号。

---

### Low

#### L1. commands.md Recycle 公式 vs 02-command-validation.md 公式表示不一致

- commands.md 第 120 行：`max(1000, remaining_lifespan × 5000 / total_lifespan) bp × body_cost / 10000`（basis points 表示）
- 02-command-validation.md §3.18 第 490 行：`max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`（十进制百分比表示）
- api-registry.md §10.3：`refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)`（basis points）

三种表示数值等价（1000 bp = 0.1 = 10%, 5000 bp = 0.5 = 50%），但单位不统一会增加实现时的理解成本。

修复建议：统一使用 basis points 表示（与 IDL 和 api-registry 保持一致）。

---

#### L2. host-functions.md §安全约束 WASM 内存上限与 api-registry.md 不一致

- host-functions.md 第 91 行：`WASM 内存上限: 64 MB`
- api-registry.md §5.2：`WASM 线性内存 64 MB; cgroup 进程级 128 MB`

host-functions.md 仅提到 WASM 线性内存，未提进程级上限。

修复建议：在 host-functions.md 中补充进程级 128 MB 的说明，或引用 api-registry.md §5.2。

---

#### L3. 02-command-validation.md §6 字段级穷举校验表格式问题

第 596–613 行的表格列对齐不一致（表头 `Command` 列前多一个空列，且部分行的管道符 `|` 位置偏移）。不影响内容正确性但影响可读性。

---

## 3. 亮点

1. **单事实源架构（IDL → Registry）**：`game_api.idl.yaml` → 自动生成 `api-registry.md` 的流水线设计优秀。CI `--check` 模式确保不漂移。这是 API/DX 质量的基石。

2. **47-code canonical RejectionReason 体系**：D2/B 决策（wire enum 稳定 + debug_detail 承载上下文）是成熟的设计。code range 分离（game 1–35, auth 1001–1012）和 `NotVisibleOrNotFound` 安全合并码体现了对信息泄露的深思熟虑。

3. **detail_level 三级错误提示模型**：competitive/practice/training 的错误信息量分级与 Snapshot Contract 的 Safe Hint Ladder 一致，既保护竞技公平又支持开发调试。

4. **SwarmError JSON-RPC Envelope 设计**：`retry_allowed`、`idempotency_key`、`retry_after_tick` 三个机器可读字段使 SDK 可以生成智能重试逻辑，降低 AI agent 的错误处理负担。这是开发者体验的亮点。

5. **Fixed-Point Type Registry**：用 `BasisPoints`、`ResourceRate_i64`、`milli_distance`、`micro_cost` 替换 f64，在 IDL 层面消除浮点不确定性。API/DX 视角下这是跨语言代码生成的关键保障。

6. **Command Validation Pipeline 的 CommandIntent → RawCommand → ValidatedCommand 三层模型**：清晰的不可信→可信升级路径，且 WASM 禁止注入 `player_id`/`source`/`tick` 字段的设计合同明确无误。

7. **Rhai Mod ABI 合同**：事务性语义、Hook 调度顺序、Capability 白名单、错误层次和降级策略全部明确定义，9 项实现清单可直接作为 conformance test 的依据。

8. **Snapshot Truncation Contract 的确定性截断**：距离桶→entity_id 字典序→从远到近移除的三层排序确保了 replay 确定性，关键实体永不截断的不可截断前缀设计合理。

---

## 4. CrossCheck

以下是我怀疑但超出 API/DX 方向范围的问题，供 Speaker 进行跨方向交叉验证：

- **CX-1**: `02-command-validation.md` 中的非 canonical RejectionReason 码（`TileBlocked`、`StillSpawning`、`InvalidDamageType` 等）是否在其他设计文档（如 gameplay.md、security/）中被引用？→ 建议 **Gameplay reviewer + Security reviewer** 检查这些码是否已作为 wire enum 变体在 IDL 中定义但未同步到 Registry

- **CX-2**: api-registry.md §4.5 Host Function ABI 错误优先级表在 offset 500 处被截断——我没能读取到完整表格。→ 建议 **Engine reviewer** 确认该表是否完整且与 host-functions.md 的「超出预算 → 返回 canonical ABI error code」描述一致

- **CX-3**: `02-command-validation.md` §3.16 特殊攻击状态机矩阵将优先级权威委托给 `specs/core/06-phase2b-system-manifest.md`，该文件不在本次审查范围内。→ 建议 **Gameplay reviewer** 验证该委托链的完整性，以及 manifest 中是否实际定义了优先级顺序

- **CX-4**: Codegen pipeline 文档（codegen.md）声明为手工维护，但 api-registry.md 是自动生成——这两个文档的同步机制是否有 CI 覆盖？→ 建议 **CI/Infra reviewer** 检查 CI pipeline 中是否有检查 `codegen.md` 声明计数与 `api-registry.md` 生成计数一致性的步骤

- **CX-5**: api-registry.md §10 经济操作将费率权威委托给 `specs/core/08-resource-ledger.md`（不在审查范围）。RecycleRefund 公式在三个文档中以不同形式出现（bp vs 百分比）。→ 建议 **Economy reviewer** 确认公式的单一权威源及跨文档一致性