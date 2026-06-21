# R31 API/Developer Experience Review — rev-dsv4-apidx

> Phase 1 独立评审。仅基于方向相关子集文档。不考虑分阶段实现难度。

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

核心问题：`02-command-validation.md` 的逐指令校验矩阵引入了 8 个不在 canonical 47 码中的 ad-hoc 错误码，直接违反了 api-registry.md 的「单一权威来源」原则。MCP 工具计数在三个文档间不一致（59/57/56）。Host function 计数同样不一致（6/5/5）。这些问题必须先修复才能进入实现阶段。

---

## 2. 发现的问题

### Critical

**C1 — 02-command-validation.md §3 校验矩阵引入非 canonical 错误码**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` §3.1–§3.15, §5.1
- 问题描述：逐指令校验矩阵中使用了以下不在 canonical 47 码中的错误码：
  - `TileBlocked` (§3.1 Move)
  - `StillSpawning` (§3.1 Move)
  - `AlreadyDebilitated(damage_type)` (§3.13 Debilitate)
  - `InvalidDamageType` (§3.13 Debilitate)
  - `ExceedsRoomCapacity` (§3.8 Spawn)
  - `MainActionQuotaExceeded` (§5.1 拒绝码表)
  - `PermissionDenied` (§5.1, 09-snapshot-contract.md §4.2 引用)
  - `InvalidTarget` (§5.1, 09-snapshot-contract.md §4.2 引用)
- 影响分析：api-registry.md §2 明确声明 "共计 47 个 canonical code" 且 "详细上下文信息放入 debug_detail 字段，而非增加 RejectionReason enum 变体"。但 validation spec 引入了没有 canonical mapping 的错误码。这导致：
  1. SDK codegen 无法为这些错误码生成 typed exception
  2. Replay verifier 遇到这些码时无法验证一致性
  3. 违反 D2/B 设计决策
- 修复建议：
  - `TileBlocked` → 映射到 `PositionOccupied`（canonical #14），detail 为 `"PositionOccupied: x=<x>, y=<y>, reason=TileBlocked"`
  - `StillSpawning` → 映射到 `CooldownActive`（canonical #12），detail 为 `"CooldownActive: action=Spawn, reason=StillSpawning"`
  - `AlreadyDebilitated(damage_type)` → 映射到 `CooldownActive`（canonical #12），detail 为 `"CooldownActive: action=Debilitate, damage_type=<type>, reason=AlreadyActive"`
  - `InvalidDamageType` → 映射到 `InvalidResourceType`（canonical #22，语义最接近），或新增一个 canonical code
  - `ExceedsRoomCapacity` → 映射到 `InsufficientResource`（canonical #3），detail 为 `"InsufficientResource: type=RoomEnergy, required=<needed>, available=<available>"`
  - `MainActionQuotaExceeded` → 映射到 `CommandBufferFull`（canonical #33），detail 为 `"CommandBufferFull: reason=MainActionQuotaExceeded, drone_id=<id>"`
  - `PermissionDenied` → 映射到 `NotAuthorized`（canonical #29）或 `NotOwner`（canonical #2）
  - `InvalidTarget` → 映射到 `NotVisibleOrNotFound`（canonical #7）或 `ObjectNotFound`（canonical #1），具体取决于上下文
  - **或者在 api-registry.md §2 中正式注册这些缺失的 canonical code**

**C2 — MCP 工具计数跨文档不一致**

- 文件：
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md` §3 header: 声称 "共计 57 个活跃工具 (game_api)"
  - 同一文档 §3.2 表格实际行数：11 (Onboarding) + 3 (Auth) + 16 (Play) + 7 (Deploy) + 8 (Debug) + 6 (Admin) + 1 (SDK) + 5 (Arena) + 2 (Resources) = **59**
  - `/tmp/swarm-review-R31/specs/reference/mcp-tools.md` §工具总览: Onboarding=10, Auth=2, Play=16, Deploy=7, Debug=8, Admin=6, SDK=1, Arena=4, Resources=2 = **56**
  - `/tmp/swarm-review-R31/design/interface.md` §4.1: "56 game tools + 11 auth tools"
- 影响分析：codegen 文档 (§禁止手写的数值) 声明的计数 `当前 56 active` 与 api-registry 表格实际行数 (59) 相差 3。CI diff check 如果依赖这些计数值，会产生错误的通过/失败判断。开发者在不同文档间切换时无法确定权威数字。
- 修复建议：
  1. 更新 api-registry.md §3 header 为正确的行数（59），或解释为何 header 声明 57 而表格有 59 行
  2. 更新 mcp-tools.md 分类计数匹配 api-registry.md 表格（新增 `swarm_get_objectives` 使 Onboarding 10→11；Arena `swarm_get_leaderboard` 计入 4→5；Auth section 的 3 个 alias 工具应计入）
  3. 更新 codegen.md 禁止手写数值段中的 MCP tool 数量（56→59）
  4. 更新 interface.md 中的计数引用

### High

**H1 — Host function 计数跨文档不一致**

- 文件：
  - `/tmp/swarm-review-R31/specs/reference/api-registry.md` §4: "共计 6 个函数"（含 `host_get_random`）
  - `/tmp/swarm-review-R31/specs/reference/codegen.md` §禁止手写的数值: "Host function 数量 (当前 5)"
  - `/tmp/swarm-review-R31/specs/reference/host-functions.md` §允许的 Import: 仅列出 5 个（缺少 `host_get_random`）
  - `/tmp/swarm-review-R31/design/interface.md` §5.1: 列出 5 个 host function（缺少 `host_get_random`）
- 影响分析：`host_get_random` 在 api-registry §4.1 作为函数 #6 正式注册，有完整的 ABI 签名、预算约束、per-call fuel 成本、输出上限。但 codegen.md 和 host-functions.md 的计数和表格都未更新。SDK 代码生成可能遗漏 `host_get_random` 的 import 声明。
- 修复建议：
  1. 更新 codegen.md 中 "Host function 数量" 为 6
  2. 更新 host-functions.md §允许的 Import 表格添加 `host_get_random`
  3. 更新 interface.md §5.1 添加 `host_get_random` 签名
  4. 更新 interface.md 中的注意文字（"以下为概念签名"段，目前列 5 个）

**H2 — 02-command-validation.md §7.1 Refund 表有重复/冲突条目**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` lines 629-638
- 问题描述：`InsufficientResource` 出现 3 次，分别映射到不同 refund 策略：
  - Line 630: `InsufficientResource` → 退 50% fuel（竞争导致）
  - Line 632: `InsufficientResource` → 退 50% fuel（同上，完全重复）
  - Line 636: `InsufficientResource` → 不退（玩家应计算资源）
- 影响分析：同一 rejection code 有三种不同的 refund 行为声明。引擎实现无法确定权威 refund 策略。玩家 WASM 无法可靠预测 fuel 退还行为。
- 修复建议：
  - 合并为单一条目，明确区分：竞争型 `InsufficientResource`（如多人争抢同一 Source）退 50%；预计算型 `InsufficientResource`（如 build_cost 超过自身持有量）不退
  - 或者在 RejectionReason 中拆分出 `ResourceContended`（竞争资源不足，退 50%）和保持 `InsufficientResource`（预计算不足，不退）
  - 删除完全重复的行 632

**H3 — api-registry.md §2.2 header 计数与 §2 header 计数不一致**

- 文件：`/tmp/swarm-review-R31/specs/reference/api-registry.md`
  - §2 header: "共计 47 个 canonical code（35 from game_api + 12 from auth_api）"
  - §2.2 header: "Validation 级 — 26 codes"
  - §2.3 header: "MCP 层 — 3 codes"
  - §2.4 header: "Runtime 级 — 6 codes"
  - §2.1: "Pipeline 级 — 不计入 enum，统一前置处理"（Pipeline 2 codes 不计入）
  - 验算: 26 + 3 + 6 = 35 game_api codes. 35 + 12 auth = 47. ✓
- 问题描述：实际上 §2.2 Validation 级表格中只有 26 行（#1-#26），但 §3.1 校验矩阵中出现了不在 canonical 表中的 `TileBlocked`、`StillSpawning` 等 8 个新码。如果这些码应被注册为 canonical，则总数不再是 47；如果不应注册，则 validation spec 必须修正到 26 个 canonical 码范围内。
- 影响分析：这是 C1 的另一面——validation spec 引入的 ad-hoc 码要么需要注册进 canonical 表（更新 §2 header 计数），要么需要从 validation spec 移除。
- 修复建议：与 C1 同步修复

### Medium

**M1 — codegen.md 自身为手工维护且计数已过时**

- 文件：`/tmp/swarm-review-R31/specs/reference/codegen.md` §禁止手写的数值
- 问题描述：codegen.md 声明 "本文档自身为手工维护" 并承认 "本文档中的数值需在 IDL 变更时手动更新"。但当前 Host function 数量 (5) 和 MCP tool 数量 (56) 均已过时。文档的设计意图（codegen 生成 → CI diff check）是正确的，但其自身的计数声明容易被误认为权威源。
- 影响分析：如果 CI 同时检查 "本文档中的计数声明" 与 "--check 输出的一致性"（如建议），则过时的计数会导致 CI 误报。
- 修复建议：
  1. 将 codegen.md 中所有计数值指向 api-registry.md（例如 "见 api-registry.md §3 header"），而非声明具体数字
  2. 或者让 codegen 生成脚本同时输出一个 `codegen-counts.json`，CI 跨校验

**M2 — `command_index` 暗示 batch API 但未在工具注册表中定义**

- 文件：`/tmp/swarm-review-R31/specs/reference/api-registry.md` §8 SwarmError JSON-RPC Envelope
- 问题描述：`command_index` 字段定义为 "u32 (optional, batch command index)"，暗示存在批量指令提交 API。但 §3 MCP Tools 中没有 `swarm_submit_commands` 或类似的批量工具。WASM 的 tick() 输出天然是 CommandIntent[] 数组，但 MCP 侧的工具都是单操作工具。
- 影响分析：如果 `command_index` 仅用于 WASM tick() 输出的批量结果（即 tick 返回的 N 条指令中的第 K 条被拒绝），则字段说明应明确此上下文。如果也用于 MCP 批量 API，则该 API 需要注册。
- 修复建议：
  - 明确 `command_index` 的适用范围：是 `tick() → CommandIntent[]` 返回数组的索引，还是也用于某个未来/现有的 MCP 批量 API
  - 若仅为 WASM tick 内部使用，可标注 "仅 WASM tick() 输出上下文"

**M3 — host-functions.md 缺少 `host_get_random` 的详细签名和说明**

- 文件：`/tmp/swarm-review-R31/specs/reference/host-functions.md`
- 问题描述：api-registry.md §4.1 已注册 `host_get_random` 为函数 #6（含 ABI 签名、预算、上限），但 host-functions.md 中完全没有提及。开发者参考 host-functions.md 将不知道此函数存在。
- 影响分析：SDK 的 host function import 声明如果从 host-functions.md 派生，会遗漏 `host_get_random`。
- 修复建议：在 host-functions.md 中添加 `host_get_random` 的完整签名和说明

**M4 — Leech/Fabricate body part 需求未明确**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` §3.18 (§8 Leech/Fabricate)
- 问题描述：Leech 和 Fabricate 的校验描述中只说 "drone 有对应 body part"，但没有指定具体是哪个 body part。Commands.md §Leech 同样只写 "drone 有对应 body part"。相比之下，其他 special attack 都明确指定了 body part（Hack→Claim, Drain→Work+Carry, Overload→RangedAttack 等）。
- 影响分析：API 使用者（SDK stub 生成、WASM 开发者）无法确定执行 Leech/Fabricate 需要什么样的 drone 配置。Tier 2 特性可以暂时不完整，但 body part 需求是 schema 必填项。
- 修复建议：
  - 在 api-registry.md §1.3 或 commands.md §Leech/Fabricate 中明确 body part 要求
  - 建议：Leech → `Attack`（吸血本质上是一种攻击），Fabricate → `Work`（构造类操作）
  - 若确实尚未确定，标注 `⏳ Tier 2 — body part TBD` 而非模糊的 "对应 body part"

**M5 — interface.md §4.1 概念分类表中的工具名与 registry 不一致**

- 文件：`/tmp/swarm-review-R31/design/interface.md` §4.1
- 问题描述：概念分类表中列出了 `swarm_list_modules`（Deploy 类）和 `swarm_get_economy_trend`、`swarm_get_drone_efficiency` 等。但该表明确声明 "不列完整表" 且 "不得用于实现引用"。问题在于 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_objectives`、`swarm_get_available_actions`、`swarm_profile` 等 0.4.0 新增工具未被提及——作为概念概览，遗漏新工具会误导开发者。
- 影响分析：开发者阅读 interface.md 作为入口时，会认为这是工具的全貌，从而遗漏在 api-registry 中已注册的新工具。
- 修复建议：在概念分类表中添加注释说明 "0.4.0 新增: swarm_get_docs, swarm_get_schema, swarm_get_objectives, swarm_profile, swarm_get_available_actions" 或更新分类表行列

### Low

**L1 — 02-command-validation.md 使用 `(debug_detail)` 作为「错误码」列值，格式不规范**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` §3.1–§3.15 校验矩阵
- 问题描述：校验矩阵的「失败码」列中大量使用 `(debug_detail)` 作为值（如 "drone.fatigue == 0 → (debug_detail)"）。虽然语义上正确（fatigue 信息应进入 debug_detail），但从表格格式角度看，`(debug_detail)` 不是一个有效的错误码——它没有说明底层映射到哪个 canonical RejectionReason。
- 影响分析：引擎实现者看到 `(debug_detail)` 不知道应该返回 `CooldownActive` 还是其他 canonical code。实际上 fatigue 检查失败应返回 `CooldownActive` 并附带 fatigue 信息到 debug_detail。
- 修复建议：将 `(debug_detail)` 替换为实际的 canonical mapping，例如：
  - `drone.fatigue == 0` → `CooldownActive`（detail: "fatigue > 0"）
  - `drone.body 缺少 X 部件` → `NotEnoughBodyParts`（已有部分条目正确使用）
  - `target 是友方` → `NotOwner` 或保持 `(debug_detail)` 但标注 canonical 映射

**L2 — TickValidationFailed 不在 canonical RejectionReason 中**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` §1.1, §2.1
- 问题描述：当 WASM tick() 输出顶层 schema 校验失败（JSON 畸形、未知字段、超深）或 CommandIntent 包含禁止字段时，文档说 "记录到 TickTrace 为 `TickValidationFailed`"。但 `TickValidationFailed` 不在 47 个 canonical RejectionReason 中。
- 影响分析：`TickValidationFailed` 是 tick 级事件（整个 tick 输出被拒绝），而 canonical RejectionReason 是 per-command 的。但 Replay 需要能够序列化此事件。建议将 `TickValidationFailed` 注册为特殊的 terminal_state 值或 Runtime 级错误。
- 修复建议：将 `TickValidationFailed` 映射到 `SchemaViolation`（§2.1 Pipeline 级 — 但 Pipeline 级不计入 enum），或增加为 Runtime 级 canonical code

**L3 — 02-command-validation.md §3.17 "Overload 抗永久锁死证明" 引用未定义符号**

- 文件：`/tmp/swarm-review-R31/specs/core/02-command-validation.md` §3.17 line 474
- 问题描述：证明中说 "下一次 Overload 削减 500k → budget = max(2M, 2.1M - 500k) = 2M"。但这假设 MAX_FUEL = 10M。`MAX_FUEL` 和 `MIN_FUEL` 未在本文件或 api-registry.md §5 中明确定义为权威常量。api-registry.md §5.2 有 "Fuel 上限: 10,000,000" 但未命名为 `MAX_FUEL`。host-functions.md 有 "Fuel 上限: 10,000,000" 同样未命名。
- 影响分析：证明依赖未定义常量，降低了可验证性。
- 修复建议：在 api-registry.md §5.2 中明确命名 `MAX_FUEL = 10,000,000`，或在证明中直接使用数值

---

## 3. 亮点

1. **Fixed-point type registry (§0)** — 将 `f64` 完全替换为 fixed-point 整数类型（BasisPoints, ResourceRate_i64, milli_distance 等），保证跨平台确定性。这是 API 设计中最难做对的部分之一，这里的处理非常彻底。

2. **detail_level 三级模型 (§2)** — competitive/practice/training 三级错误详情控制，既保护竞技公平性（competitive 模式仅返回 canonical code），又为开发者提供充分调试信息（training 模式）。与 09-snapshot-contract.md §4 Safe Hint Ladder 完全对齐。

3. **单事实源原则明确且一致** — api-registry.md 作为权威源、其他文档只能引用的设计在全文档中得到了明确声明和部分执行。IDL → codegen → Registry 的生成链是正确方向。

4. **RejectionReason validation condition 映射表 (§2.6)** — 每个 validation condition 到 canonical RejectionReason 再到 debug_detail 模板的完整映射，使引擎实现有明确的错误生成路径。这是很多 API 设计缺失的关键部分。

5. **CommandIntent 禁止字段检测** — WASM tick() 输出若包含 `player_id`/`source`/`tick` 字段则整个输出被拒绝。这防止了 WASM 模块伪造身份信息的安全攻击面。

6. **Replay 完整性** — TickTrace Envelope 的 22 个字段（§6）覆盖了 replay 所需的全部状态（module hash, wasmtime version, snapshot hash, world config hash, mods lock, world action manifest hash 等），保证了 replay 可验证性。

7. **Allied Transfer 拦截设计** — 运输中拦截（09-snapshot-contract.md §3.2a）是完整设计而非 MVP 占位，含成功率公式、escort 防御、确定性 RNG、三方通知、审计日志——所有边界条件闭合。

8. **Rhai mod ABI** — 事务性语义、12 个 capability 白名单、6 级错误层次、自动化降级机制，为 mod 开发者提供了清晰的可编程合约。

---

## 4. CrossCheck

以下问题需要跨方向确认，标注目标方向和具体关注点：

- **CX-1: RejectionReason count 47 是否需要扩展到 55+** → 建议 **Security reviewer** 检查 C1 中列出的 8 个 ad-hoc 错误码（TileBlocked, StillSpawning 等）是否应该正式注册为 canonical code，以及是否影响反作弊/审计的完整性。

- **CX-2: `command_index` 的适用范围** → 建议 **Engine reviewer** 确认 `command_index` 是否仅用于 WASM tick() 内的 CommandIntent[] 数组索引（M2），还是也计划用于未来 MCP 批量 API。如果有批量 API 计划，需同步更新 MCP Tools 注册表。

- **CX-3: host_get_random 的 domain separation 安全性** → 建议 **Security reviewer** 检查 `host_get_random` 以 `(tick_seed, player_id, drone_id, sequence)` 为种子的 domain separation 是否足够防止跨 drone/跨 tick 的随机数预测攻击。

- **CX-4: Overload anti-lockout 证明的数学正确性** → 建议 **Gameplay reviewer** 验证 §3.17 证明中的最坏情况分析（2M 下限 + 50 tick 恢复 + 500k 削减循环）是否在所有 world.toml 可配参数下成立。

- **CX-5: Rhai mod ABI 与 WASM sandbox 的隔离边界** → 建议 **Security reviewer** 检查 Rhai 的 `actions.*` API 是否可能被滥用为绕过 WASM fuel metering 的旁路（例如 mod 通过 `actions.award` + `actions.deduct` 组合实现等效的 WASM 计算）。

- **CX-6: Snapshot critical entity list 完备性** → 建议 **Gameplay reviewer** 检查 09-snapshot-contract.md §1.4 的关键实体列表是否遗漏了任何影响战术合法性的实体类型（例如：正在被己方 Fortify 护盾保护的目标？正在 Drain 的源？）。

- **CX-7: Leech/Fabricate body part 定义** → 建议 **Gameplay reviewer** 确认 Leech 和 Fabricate 所需的 body part（M4），以便 api-registry.md §1.3 和 commands.md 能够完成 schema 定义。

- **CX-8: Allied Transfer 拦截的可见性约束** → 建议 **Security reviewer** 检查 09-snapshot-contract.md §3.2a 中 "攻击方必须 `is_visible_to(attacker, receiver_room)`" 是否足够防止通过拦截判定来探测不可见玩家的 transfer 活动（oracle attack）。

---

*评审完成时间: 2026-06-21 | API 版本: 0.4.0*