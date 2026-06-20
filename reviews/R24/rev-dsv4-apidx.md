# R24 API/DX 评审 — DeepSeek V4 Pro

> 评审方向：API / 开发者体验
> 评审焦点：spec ↔ design 对齐检查

---

## Verdict: REQUEST_MAJOR_CHANGES

spec/reference/ 层的 IDL (game_api.idl.yaml) 与 design 文档之间存在 4 个 Critical 级别的函数签名矛盾，以及多处数值和枚举计数漂移。api-registry.md 自称由 IDL 自动生成，但与 IDL 源文件存在明显偏差，破坏了"单事实源"原则。必须修复后才能进入实现。

---

## Strengths

- gateway-protocol.md 的 Transport Auth Matrix（§9）定义了完整的 5 transport × auth material 映射，与 design/interface.md 的 MCP 架构和 design/auth.md 的证书模型一致
- codegen.md 明确了 IDL → SDK/Registry 的输入输出链，CI check 机制阻止手写分叉
- api-registry.md 的命名规范（§2 命名规范）明确统一了 RejectionReason 的合并规则（InsufficientResource 单数、ObjectNotFound 统一形式、NotVisibleOrNotFound 安全合并），消除了旧码碎片
- debug_detail 设计（D2/B）是高质量 API/DX 实践 — 保持 wire enum 稳定同时提供丰富调试数据

---

## Critical Findings

### C1 — CommandAction 变体计数：IDL 19 vs api-registry 21

| 维度 | 值 |
|------|-----|
| **design/interface.md:§5.4** | 引用 api-registry §1"权威定义"，未声明计数 |
| **api-registry.md:§1** | "变体总数: 21" — 列出 21 个（11 core + 2 global + 8 special） |
| **commands.md:§指令列表** | "21 指令（11核心+2Global+8特殊）" |
| **game_api.idl.yaml:§1** | `total_variants: 19` — 列出 11 core + 2 global + **6 special**（不含 Leech/Fabricate） |
| **codegen.md:§禁止手写的数值** | "CommandAction 数量 (当前 19)" — **与 IDL 一致** |

**冲突描述**：IDL 将 Leech 和 Fabricate 归类为 `custom_actions.known`（非 core enum 变体），因此 core 变体计数为 19。但 api-registry.md §1 将它们作为 #20 和 #21 计入 CommandAction 主表（标注 ⏳ Tier 2），总数为 21。commands.md 跟随 api-registry 的 21 而非 IDL 的 19。codegen.md 的声明（19）与 IDL 一致但与 api-registry 矛盾。

**修正建议**：统一决策——Leech/Fabricate 是否属于 core CommandAction enum。若否，从 api-registry §1 主表中移除（保留在 custom_actions 引用中），api-registry 计数统一为 19，commands.md 同步更新。两者已标记 Tier 2，建议移出 core enum 保留在 custom_actions，与 IDL 保持一致。

### C2 — host_get_terrain 签名：IDL (room_id) vs design (x, y)

| 维度 | 签名 |
|------|------|
| **game_api.idl.yaml:§4 host_functions** | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` — 查询整个房间的地形网格，通过 out buffer 返回 |
| **api-registry.md:§4.1** | `(room_id: u32, out_ptr: i32, out_len: i32) -> i32` — **与 IDL 一致** |
| **design/interface.md:§5.1** | `fn host_get_terrain(x: i32, y: i32) -> i32;` — 查询**单个坐标**的地形类型，返回值即类型 |
| **host-functions.md:§host_get_terrain** | `i32 host_get_terrain(x: i32, y: i32) -> i32` — 与 design 一致，返回 0=Plain, 1=Wall 等 |
| **specs/gameplay/08-api-idl.md:§2 (get_terrain)** | `params: [x: i32, y: i32], returns: i32` — 与 design 一致 |

**冲突描述**：这是两种完全不同的 API 语义：(1) IDL 定义批量查询整个房间的地形（通过输出缓冲区），(2) design 定义逐点查询单个坐标的地形（返回值直接是 terrain type i32）。签名参数完全不同——`(room_id, out_ptr, out_len)` vs `(x, y)`。五个文档中 IDL+api-registry 持一种意见，design+host-functions+08-api-idl 持另一种。

**修正建议**：决定最终语义并统一所有文档。建议保留 IDL 的批量房间查询语义（减少 WASM↔host call 次数，与两阶段快照架构一致）——如采纳，需更新 design/interface.md §5.1、host-functions.md、08-api-idl.md §2。如坚持逐点查询，则需修改 IDL 和 api-registry。

### C3 — host_path_find 签名：IDL (8 params with opts) vs design (6 params)

| 维度 | 签名 |
|------|------|
| **game_api.idl.yaml:§4 host_functions** | `(from_x, from_y, to_x, to_y, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32` — 8 参数 |
| **api-registry.md:§4.1** | `(from_x, from_y, to_x, to_y, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32` — 与 IDL 一致 |
| **design/interface.md:§5.1** | `fn host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32;` — 6 参数，无 opts |
| **host-functions.md:§host_path_find** | `i32 host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len) -> i32` — 6 参数 |
| **specs/gameplay/08-api-idl.md:§2 (path_find)** | `params: [from_x, from_y, to_x, to_y, out_ptr, out_len]` — 6 参数 |

**冲突描述**：IDL 为 path_find 增加了 `opts_ptr/opts_len` 参数（用于传递 pathfinding options 如 avoid_walls、prefer_roads 等），但 design 层的三个文档均未包含此参数。这是 API 扩展方向不明确的表现——IDL 为未来扩展预留了 opts 参数，但 design 未描述此能力。

**修正建议**：若 opts 参数是已确定的 design 决策，需更新 design/interface.md、host-functions.md、08-api-idl.md 的签名并添加 opts 结构体定义。若 opts 是未来 RFC，应从 IDL 当前签名中移除，在 RFC tracking 中记录。

### C4 — host_get_world_rules 签名：IDL (4 params with rule_id) vs design (2 params)

| 维度 | 签名 |
|------|------|
| **game_api.idl.yaml:§4 host_functions** | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` — 4 参数，可按 rule_id 筛选 |
| **api-registry.md:§4.1** | `(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32` — 与 IDL 一致 |
| **design/interface.md:§5.1** | `fn host_get_world_rules(out_ptr: i32, out_len: i32) -> i32;` — 2 参数，返回全部规则 |
| **host-functions.md:§host_get_world_rules** | `i32 host_get_world_rules(out_ptr: i32, out_len: i32) -> i32` — 2 参数 |
| **specs/gameplay/08-api-idl.md:§2 (get_world_rules)** | `params: [out_ptr: i32, out_len: i32]` — 2 参数 |

**冲突描述**：IDL 定义的签名允许按 `rule_id` 筛选特定规则模块，但 design 层的签名是一次性返回全部规则集。4 参数版本更灵活（可减少 WASM 内存压力），但与 design 的简化语义矛盾。

**修正建议**：与 C3 相同处理方式——若 rule_id 筛选是已确定的 design，更新 design 文档；若是未来 RFC，从 IDL 移除。

---

## High Findings

### H1 — object_id 未在 IDL CommandAction 参数中声明

| 维度 | object_id 状态 |
|------|---------------|
| **game_api.idl.yaml:§1 CommandAction variants** | 所有 19 个 variant 的 parameters 中**均不包含** object_id |
| **api-registry.md:§1 CommandAction table** | 参数列**均不显示** object_id |
| **commands.md:§指令列表** | **所有** JSON 示例均包含 `"object_id": "d1"` 在 action 内 |
| **specs/gameplay/08-api-idl.md:§2 commands** | **所有** command 定义的 params 均包含 `object_id: ObjectId` |
| **specs/core/02-command-validation.md:§2.1** | CommandIntent 示例: `"object_id": 1001` 在 action 内 |

**冲突描述**：`object_id`（执行动作的 drone ID）是 CommandIntent 的核心字段——所有校验规则（ownership、fatigue、body parts、range）都依赖它。08-api-idl.md 和 commands.md 的 JSON 示例一致将它作为 action 参数，但 IDL 源文件完全没有声明它。这意味着 codegen 从 IDL 生成的 SDK 类型定义将**缺少 object_id 字段**，导致 SDK ↔ 引擎类型不匹配。

**修正建议**：将 `object_id: EntityId (required)` 添加到 IDL 中所有 19 个 CommandAction variant 的 parameters 列表中。这是实现阻断性缺失——SDK 生成的 Command 类型缺少最关键的字段。

### H2 — api-registry MCP 工具计数：intro 54 vs 表格 56

| 维度 | 值 |
|------|-----|
| **api-registry.md:§3 intro** | "共计 54 个活跃工具 (game_api)" |
| **api-registry.md:§3.2 实际表格** | 10+2+16+7+8+6+1+4+2 = **56** 个 game tools |
| **game_api.idl.yaml:§3 mcp_tools** | `total_tools: 56` |
| **design/interface.md:§4.1** | "56 game tools + 11 auth tools" |
| **codegen.md:§禁止手写的数值** | "MCP tool 数量 (当前 56 active)" |

**冲突描述**：api-registry 的 §3 导言段声称 54 个 game 工具，但下方实际表格计数为 56。IDL、design、codegen 均一致为 56。这是 api-registry 导言段的手写错误——未与生成表格同步更新。

**修正建议**：将 api-registry.md §3 intro 段的 "54" 修正为 "56"。

### H3 — codegen.md RejectionReason 计数：79 vs 47

| 维度 | 值 |
|------|-----|
| **codegen.md:§禁止手写的数值** | "RejectionReason 数量 (当前 79)" |
| **game_api.idl.yaml:§2** | `total_canonical_codes: 35` |
| **auth_api.idl.yaml:§3** | `total_canonical_codes: 12` |
| **api-registry.md:§2** | "共计 47 个 canonical code（35 from game_api + 12 from auth_api）" |

**冲突描述**：codegen.md 声称 79 个 RejectionReason，但两个 IDL 源总和为 35+12=47。79 与 47 的差异为 32，无法用简单遗漏解释。这是 codegen.md 中的严重漂移值，会误导 CI 校验。

**修正建议**：将 codegen.md 中的 79 修正为 47，并添加注释 "35 (game_api) + 12 (auth_api)"。

### H4 — RangedAttack body_cost：08-api-idl.md 100 vs economy IDL 150

| 维度 | 值 |
|------|-----|
| **specs/gameplay/08-api-idl.md:§body_cost** | `RangedAttack: { Energy: 100 }` |
| **specs/reference/economy.idl.yaml:§2.6 SpawnCost** | `RANGED_ATTACK: cost: 150` |
| **api-registry.md:§10.2 SpawnCost** | "RANGED_ATTACK=150" |

**冲突描述**：08-api-idl.md 的 body_cost 表将 RangedAttack 列为 100 Energy，但 economy.idl.yaml（权威成本定义）和 api-registry.md 均列为 150。差值 50 显著影响 spawn cost 和资源模型。

**修正建议**：将 08-api-idl.md §body_cost 的 RangedAttack 从 100 修正为 150，与 economy IDL 保持一致。

---

## Medium Findings

### M1 — Recycle 退款比例：08-api-idl.md 固定 50% vs economy IDL 比例制

| 维度 | 退款模型 |
|------|---------|
| **specs/gameplay/08-api-idl.md:§2 Recycle** | `refund: registry.body_cost(body) * 0.5` — **固定 50%** |
| **economy.idl.yaml:§2.1 RecycleRefund** | lifespan-proportional — `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp → [10%, 50%] |
| **api-registry.md:§10.2** | lifespan-proportional formula |
| **specs/core/02-command-validation.md:§3.9** | "返还 lifespan-proportional 比例（10%–50%）" |

**冲突描述**：08-api-idl.md 仍保留旧版固定 50% 退款语义，未更新为 R22/R23 确定的比例制模型。虽然注释引用 api-registry 为权威，但其自身的 `refund` 字段给出固定 50% 的错误信息。

**修正建议**：将 08-api-idl.md Recycle 的 refund 字段更新为 lifespan-proportional formula，或直接删除数字引用改为 "见 economy.idl.yaml §2.1"。

### M2 — api-registry 系统性漂移：手写值与 IDL 源不一致

api-registry.md 在以下位置与 IDL 源存在偏差：

| 位置 | api-registry 值 | IDL 值 | 来源 |
|------|----------------|--------|------|
| §3 intro MCP 工具计数 | 54 | 56 | game_api.idl.yaml |
| §1 CommandAction 计数 | 21 | 19 | game_api.idl.yaml |
| §5.1 Per-player drone cap | 50 | 500 | game_api.idl.yaml |

**冲突描述**：api-registry.md 宣称"由 IDL 自动生成，手写修改将被覆盖"，但存在至少 3 处与 IDL 源不一致的值。这表明要么生成管道未运行，要么生成后进行了手工修改。这破坏了"单事实源"原则——读者无法确定 IDL 和 api-registry 何者为准。

**修正建议**：运行 `generate_api_registry.py --check` 确认所有漂移项，然后从 IDL 源重新生成 api-registry.md。同时需要决定 per_player_drone_cap 的正确值（IDL 的 500 vs design 的 50），将此决策反映到 IDL 中再重新生成。

### M3 — swarm_get_terrain MCP 工具状态模糊

| 维度 | 状态 |
|------|------|
| **design/interface.md:§4.1 table** | 列为"世界查看"类别 | 
| **api-registry.md:§3.2 Play table** | 存在但 marked `rate_limit: "— (host fn only)"` + `rate_limit_key: host_only` |

**冲突描述**：design 将 `swarm_get_terrain` 视为 MCP 工具（与 swarm_get_snapshot、swarm_list_drones 等并列），但 api-registry 将其 rate_limit 标记为 "host fn only"——暗示该工具不可通过 MCP 调用，仅作为 host function 存在。若确为 host function only，则不应出现在 MCP 工具表中；若确为 MCP 工具，则应有正常 rate limit。

**修正建议**：明确 swarm_get_terrain 的定位——是从 MCP 工具表中移除（若仅为 host function），还是分配常规 rate limit 并移除 "host fn only" 标记（若同时为 MCP 工具）。

### M4 — host_get_world_config budget 限制不一致

| 维度 | per-tick 上限 |
|------|-------------|
| **api-registry.md:§4.2** | host_get_world_config 上限: **5/tick** |
| **host-functions.md:§Host Call Budget** | host_get_world_config 未列单独上限，仅提 "其他: 共享剩余配额" |
| **design/interface.md:§5.5** | 引用 api-registry §4，未重复数值 |

**冲突描述**：api-registry 为 host_get_world_config 设置了明确的 5/tick 上限，但 host-functions.md 的预算说明未列出此限制（仅列出 path_find 10 次、get_objects_in_range 5 次）。开发者看到 host-functions.md 可能误认为 host_get_world_config 无单独调用上限。

**修正建议**：将 host-functions.md §Host Call Budget 补充 `host_get_world_config: 5/tick`，与 api-registry 保持一致。

---

## Type Gaps

1. **CommandIntent 结构未在 IDL 中完整建模**：IDL 仅定义 `CommandAction` variant 参数，但未定义顶级 `CommandIntent { sequence: u32, action: CommandAction }` 的 envelope 结构。codegen 生成的 SDK 类型将缺少此包装层。

2. **host function opts 结构体未定义**：host_path_find 的 `opts_ptr/opts_len` 参数在 IDL 中存在，但 opts 的二进制格式（struct layout、字段列表、默认值）未在任何文档中定义——SDK 生成器和 WASM 开发者均无法使用此特性。

3. **Arena-specific per-tool budget 未在 IDL 中独立声明**：design/engine.md §3.4.1 区分 World 和 Arena 的每阶段预算（如 COLLECT 2500ms vs 200ms），但 IDL 的 limits 段仅声明 World 的 per-sandbox deadline (2500ms)，未声明 Arena 的独立预算值。这意味着 Arena 模式的 codegen SDK 无法获得正确的容量限制。

---

## Error Handling Coverage

- **Pipeline 级错误 (InvalidJson, SchemaViolation)**: ✅ 已在 IDL rejection_reason §2.1 定义，api-registry 已记录
- **Validation 级 (26 codes)**: ✅ 覆盖完整，命名规范明确  
- **MCP 级 (3 codes)**: ✅ 覆盖 RateLimited, InvalidCertificate, NotAuthorized
- **Runtime 级 (6 codes)**: ✅ 覆盖 FuelExhausted, TimeoutExceeded 等
- **Auth 级 (12 codes)**: ✅ 独立 namespace 1001-1012，无冲突
- **Host function ABI errors**: ✅ 9 级优先级明确，确定性错误报告
- **debug_detail 字段**: ✅ D2/B 设计保证 wire enum 稳定 + 调试丰富度
- **detail_level 三级控制**: ✅ competitive/practice/training 覆盖不同场景

**总体评估**：错误处理覆盖完整。47 个 canonical code + 9 级 ABI error priority + 3 级 detail_level 形成完整的错误报告体系。无缺失的错误路径。

---

## 评审数据

| 维度 | 数量 |
|------|------|
| 已读取文档 | 14 个文件（design/interface.md, design/engine.md, design/tech-choices.md, design/README.md, specs/reference/api-registry.md, specs/reference/game_api.idl.yaml, specs/reference/economy.idl.yaml, specs/reference/auth_api.idl.yaml, specs/reference/commands.md, specs/reference/host-functions.md, specs/reference/mcp-tools.md, specs/reference/codegen.md, specs/gateway-protocol.md, specs/core/02-command-validation.md, specs/gameplay/08-api-idl.md） |
| Critical 发现 | 4 (C1-C4) |
| High 发现 | 4 (H1-H4) |
| Medium 发现 | 4 (M1-M4) |
| Type Gaps | 3 |
| 跨文档冲突位置 | 22 处 |