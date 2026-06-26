# R35 — API/Developer Experience 独立评审

**评审员**: rev-dsv4-apidx (DeepSeek V4 Pro)  
**日期**: 2026-06-26  
**方向**: API/DX — 类型系统完备性、错误处理覆盖、代码生成友好度  
**模式**: Phase 1 Clean-Slate 独立评审（仅方向相关子集）

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

发现 4 项 Critical 计数不一致（MCP 工具 56/57/58 四处不同、host function 5 vs 6 两处不同、RejectionReason 47 vs 48、host_get_random sequence 参数类型 u32 vs u64）、3 项 High 内部分类错位，以及若干中低级别交叉引用问题。IDL → Registry → 派生文档的生成链完整性存在结构性断裂——多处在 IDL 变更后未更新计数声明。必须在合并上游前修复，否则 CI 一致性检查将持续阻塞。

---

## 2. 发现的问题

### Critical

**B1: MCP 工具总数跨 4 文档不一致 — 56 / 57 / 58 三值共存**

- **位置**: 
  - `specs/reference/api-registry.md` §3 标题: "57 tools"，但 Play 段实际 16 行（非声明的 15），真实行数合计 = 58
  - `specs/reference/mcp-tools.md` 第 5 行/第 26 行: "56 个 Game API 活跃工具 + 11 个 Auth API 工具"，但该文档自身分类合计 = 10+3+16+7+8+6+1+4+2 = 57（与声明 56 矛盾）
  - `specs/reference/codegen.md` 第 27 行: "MCP tool 数量 (当前 56 active)"
  - `design/interface.md` 第 19 行: "57 game tools + 11 auth tools"
- **影响**: IDL 生成链信任根基断裂。CI `--check` 模式无法裁定哪个数字是 ground truth——生成产物声称 57 但实际有 58 行（Play 16 非 15），派生文档声称 56。任何下游 SDK stub 生成、MCP 能力面暴露、rate limit 聚合均因此数字不确定。
- **修复建议**: 
  1. 以 IDL YAML 源为 ground truth，重新运行 `generate_api_registry.py` 刷新 Registry 全部自动计数（含分类标题）
  2. 将 `codegen.md` 第 27 行的 "56" 更正为 IDL 真实值
  3. 将 `mcp-tools.md` 的 per-category 计数同步至 Registry 生成的分类
  4. 将 `interface.md` 第 19 行的分类数同步至 Registry
  5. 增加 CI check：`hermes codegen generate --check` 应交叉验证 codegen.md 中声明的计数与 Registry 一致

**B2: Host function 计数不一致 — api-registry/host-functions/interface 6 vs codegen 5**

- **位置**:
  - `specs/reference/api-registry.md` §4.1: 6 个 host function（host_get_terrain, host_get_objects_in_range, host_path_find, host_get_world_config, host_get_world_rules, host_get_random）
  - `specs/reference/host-functions.md` §允许的 Import: 6 个
  - `design/interface.md` §5.1 代码块: 6 个
  - `specs/reference/codegen.md` 第 29 行: **"Host function 数量 (当前 5)"**
- **影响**: codegen.md 声称 5 是 stale value——host_get_random 加入后未更新。若 codegen 工具以此值校验 IDL output，将误报不一致。SDK 开发者查阅 codegen.md 会以为只有 5 个 host import 可用。
- **修复建议**: 将 codegen.md 第 29 行 "5" → "6"，并确保 codegen.md 中所有禁止手写数值清单与 IDL ground truth 一致。建议 codegen.md 中此类数字改为注释 "(由 IDL 自动确定——以 Registry 为准)"，避免手工维护漂移。

**B3: RejectionReason 计数声明与实际不符 — 声称 47 (35+12) 实际 48 (36+12)**

- **位置**: `specs/reference/api-registry.md` §2
  - §2.2 Validation 标题: **"26 codes"**，但表中 #1-#27 共 27 行（MainActionQuotaExceeded 为 R33 B6 新增，#27）
  - §2 gametotal: 声称 35 game codes，实际 = 27+3+6 = 36
  - §2 总声称: 47，实际 = 36+12 = 48
- **影响**: MainActionQuotaExceeded (#27) 加入后 Validation 计数、game 小计、总计的声明均未更新，CI 生成校验将报告 IDL 源与声明不一致。commands.md 第 222 行引用 "47 个 canonical code" 同样落后。SDK exception class 生成可能缺漏 #27。
- **修复建议**: 重跑 `generate_api_registry.py` 刷新 §2 全部计数声明。同步更新 `commands.md` 第 222 行和第 5 行的 RejectionReason 引用总数。增加 CI cross-check: IDL count == Registry header count == derived docs count。

**B4: host_get_random sequence 参数类型跨文档不一致: u32 vs u64**

- **位置**:
  - `specs/reference/api-registry.md` §4.1 第 6 行: `(sequence: **u64**, out_ptr: i32, out_len: i32) -> i32`
  - `design/interface.md` §5.1 代码块: `fn host_get_random(sequence: **u32**, out_ptr: i32, out_len: i32) -> i32`
  - `specs/reference/host-functions.md` 第 64 行: `i32 host_get_random(sequence: **u32**, out_ptr: i32, out_len: i32) -> i32`
- **影响**: **阻塞 ABI 实现**——WASM 导入签名在 u32 vs u64 之间是 breaking change。若引擎实现按 u64 提供，SDK 按 u32 生成 binding，WASM 模块加载即 crash。domain separation 语义依赖 sequence 宽度（u64 支持 2^64 domain 值，u32 仅 2^32），影响 replay 随机流隔离能力。
- **修复建议**: 以 `game_api.idl.yaml` 为唯一地面真相。若 IDL 定义为 u64，修正 interface.md 和 host-functions.md 中的签名为 u64；若 IDL 定义为 u32，修正 api-registry.md 为 u32。增加 CI 签名交叉验证：所有文档中的 host function ABI 签名必须与 IDL 一致。**标记为 D-item 待用户裁决**（IDL YAML 源不可读，需用户确认）。

### High

**B5: Auth API 工具计数跨文档不一致 — 11 vs 12**

- **位置**:
  - `specs/reference/api-registry.md` §3.3 标题: **"12"**（7 CSR lifecycle + 5 device/recovery/federation）
  - `design/interface.md` 第 19 行: **"11 auth tools"**
  - `specs/reference/mcp-tools.md` 第 5 行: **"11 个 Auth API 工具"**，第 27 行: **"Auth API: 12"**
- **影响**: mcp-tools.md 内部自相矛盾（行 5 说 11，行 27 说 12）。interface.md 的概念表落后于 Registry 实际。若 MCP server capabilities 协商基于 interface.md 计数，会少暴露 1 个 auth 工具。
- **修复建议**: 以 Registry §3.3 的 12 为准，修正 interface.md 第 19 行为 "12 auth tools"，修正 mcp-tools.md 第 5 行为 "12 个 Auth API 工具"。

**B6: MCP 工具 per-category 计数 mcp-tools.md vs api-registry 不一致**

- **位置**:
  - `specs/reference/mcp-tools.md` §工具总览: Onboarding=10, Play=16
  - `specs/reference/api-registry.md` §3.2: Onboarding=11 (标题), Play=15 (标题，实际 16 行)
- **影响**: mcp-tools.md 的 Onboarding=10 遗漏了 `swarm_get_objectives`（0.4.0 新增）。Play=16 可能是正确的（Registry 标题 15 落后但实际行数 16）。两个文档各自指向不同分类数量，SDK capability profile 分组依赖这些数字。
- **修复建议**: Registry 重新生成后统一分类数与 mcp-tools.md。建议 mcp-tools.md 的分类计数改为 "(sync from Registry)" 注释，手动维护是持续漂移源。

**B7: rhai-mod-abi.md 内部 Capability 计数不一致 — 13 vs 12**

- **位置**: 
  - `specs/reference/rhai-mod-abi.md` §4.1 表格列出 **13** 个 capability（spawn_npc 到 direct_ecs_writer）
  - `specs/reference/rhai-mod-abi.md` §9 实现清单第 5 项: "**12** 个 capability 全部可授权"
- **影响**: 实现者遵循清单第 5 项 "12 个" 将遗漏 1 个 capability。若遗漏的是 `direct_ecs_writer`（🔴 Critical 级），则模组最高风险路径完全缺失。
- **修复建议**: §9 第 5 项 "12 个" → "13 个"。增加 CI 校验：rhai-mod-abi.md §4.1 表行数 = §9 第 5 项声明的数字。

### Medium

**B8: 09-snapshot-contract 经济操作命名与 api-registry 不一致**

- **位置**:
  - `specs/core/09-snapshot-contract.md` §3.1: "GlobalDeposit" (fee 1%), "GlobalWithdraw" (delay 100 tick, fee 5%)
  - `specs/reference/api-registry.md` §10.2: "TransferToGlobal" / "TransferFromGlobal" 
- **影响**: 文档使用不同操作名（GlobalDeposit vs TransferToGlobal），参数也不同（09-snapshot-contract GlobalDeposit fee=1%, GlobalWithdraw delay=100 tick; api-registry 和 commands.md 则说 TransferToGlobal delay=10 tick, fee=1%; TransferFromGlobal delay=5 tick, fee=5%）。API 消费者查看 snapshot-contract 的 "GlobalDeposit" 无法在 Registry 中找到对应操作。**注意**: 09-snapshot-contract 可能是旧版经济参数——需以 resource-ledger.md 为权威。
- **修复建议**: 将 09-snapshot-contract.md §3.1 的经济操作名统一为 api-registry 的 CommandAction 名称（TransferToGlobal / TransferFromGlobal）。确认延迟/费率以 `specs/core/08-resource-ledger.md` 的权威值为准，对齐三个文档。

**B9: host-functions.md host_get_random `sequence` 签名与 Registry 不一致 — 同 B4**

- **位置**: `specs/reference/host-functions.md` 第 64 行: `host_get_random(sequence: u32, ...)`
- **影响**: 与 B4 相同——如果 Registry 和 IDL 为 u64，此文档签名错误会导致 SDK stub 生成 ABI 不匹配。
- **修复建议**: 与 B4 同步修复。`host-functions.md` 应引用 Registry 签名而非自行声明。

**B10: codegen.md 自身是手写文档但包含硬编码数值——结构脆弱**

- **位置**: `specs/reference/codegen.md` §禁止手写的数值: CommandAction 数量=21, MCP tool 数量=56, RejectionReason 数量=47, Host function 数量=5, MAX_DRONES_PER_PLAYER=50
- **影响**: codegen.md 第 24 行自我承认 "本文档自身为手工维护……需在 IDL 变更时手动更新"。这在实践中已证明不可靠——56/47/5 三个数字已落后于 IDL 实际。即使 CI `--check` 可检测漂移，仍需人工修复，而人工修复不可靠。
- **修复建议**: 
  - 方案 A（推荐）: 将 codegen.md 中所有硬编码数值替换为 "由 IDL 自动生成——以 api-registry.md 为准"，消除手动维护点
  - 方案 B: 在 `generate_api_registry.py` 中同时生成 codegen.md 的数值段，纳入自动生成链

### Low

**B11: commands.md §3.8 Spawn 延迟参数分散 — 多个文档声称不同值**

- **位置**: 
  - `specs/reference/commands.md` 第 88 行: "spawn 需求 tick 数 = body 长度"
  - `specs/core/02-command-validation.md` §3.8: 无明确延迟 tick 数，提及 spawning_grace=1 tick
- **影响**: 低——这些是 gameplay 参数更精确地在 resource-ledger 或 world.toml 中定义。仅标记为提醒。
- **修复建议**: 在 commands.md 中标注 "(以 resource-ledger.md 权威值为准)"，避免未来修改时遗漏。

**B12: snapshot-contract §3.1 StorageTax 声明 0.1%/tick 与 registry 分层税率不一致**

- **位置**: `specs/core/09-snapshot-contract.md` 第 202 行: "StorageTax | 消耗 | 仓库存储税（0.1%/tick）"
- **影响**: Registry §10.2 和 resource-ledger 使用分层税率（0/1/5/20 bp 按容量分档），"0.1%/tick" 的单一数字描述不准确。
- **修复建议**: 将 §3.1 StorageTax 描述改为 "分层存储税（见 resource-ledger.md §2.2）"并引用 Registry。

---

## 3. 亮点

1. **Registry 单事实源设计原则健全**: `api-registry.md` 的 IDL→生成链设计（§开头明确 "手写修改将被覆盖"、CI gate `--check`）在理念上正确。CommandAction、RejectionReason、Host Functions、MCP Tools 的枚举完整性覆盖了 API surface 全部触点。**结构本身是出色的——只是数据漂移尚未被 CI 强制执行。**

2. **RejectionReason debug_detail 映射表** (§2.6): Validation Condition → canonical RejectionReason → debug_detail template 的完整映射（33 行模板）是跨文档可追溯性的典范。每个引擎 condition 都有唯一 canonical code + 参数化模板——这正是 D2/B 设计决策的彻底落地。

3. **Snapshot Truncation Contract** (09-snapshot-contract.md §1): 确定性截断顺序（距离桶 + entity_id 字典序 + 从最远桶末尾移除）、关键实体永不截断 + size reserve (128KB/256KB)、competitive mode degraded 标记——完整的 API 契约覆盖了边界条件。玩家不会因截断而丢失战术合法性关键实体。

4. **CommandIntent → RawCommand → ValidatedCommand 三段式管线** (02-command-validation.md §2): 类型系统正确——WASM 只能输出 CommandIntent (sequence+action)，player_id/source/tick 全部服务端注入，ValidatedCommand 携带预校验缓存。这杜绝了 WASM 伪造身份的攻击面。

5. **special-attack-table.md 的 canonical 参数表 + override prevention**: 明确声明 "所有 design/spec/IDL 文档必须引用此表，不得重新声明可冲突的参数"，并在 CI 以 IDL index 校验——这是正确的单事实源约束。

6. **rhai-mod-abi.md 的 direct_ecs_writer 声明格式**: affected_components/affected_resources 白名单 + manifest_hash + CI 校验 10 项要求——对最高风险 capability 的审计覆盖完整。

---

## 4. CrossCheck

以下问题从 API/DX 视角可疑但超出本方向评审范围，需指定目标方向检查：

- **CX1: [host_get_random sequence 参数类型 u32 vs u64 — D-item]** → 建议 **Core/Engine 方向** 检查 `game_api.idl.yaml` 中 `host_get_random` 的实际定义，确认 sequence 宽度。此差异影响 WASM ABI 签名和 replay 随机流隔离能力。**待用户裁决后统一所有文档。**

- **CX2: [09-snapshot-contract 经济操作参数 (GlobalDeposit 1%/100tick) vs Registry/commands (TransferToGlobal 1%/10tick) 不一致]** → 建议 **Economy 方向** 检查 `specs/core/08-resource-ledger.md` 中的权威延迟与费率参数，确认 TransferToGlobal/TransferFromGlobal 的正确值。

- **CX3: [api-registry.md RejectionReason §2 Validation 段漏掉 Pipeline 级 codes (InvalidJson, SchemaViolation) 对 SDK error type 生成的影响]** → 建议 **Core/Engine 方向** 检查 Pipeline 级错误（"不计入 enum，统一前置处理"）是否应在 SDK 中也有对应的 throwable exception type。当前 SDK 可能无法 catch 这两个前置错误。

- **CX4: [commands.md §7.1 退还规则表中 InconsistentResource 重复出现两次 + debug_detail 与 canonical code 混淆]** → 建议 **Gameplay/Economy 方向** 检查 refund 表是否应合并重复行且明确哪些条件映射到 canonical RejectionReason。

- **CX5: [codegen.md §禁止手写数值 列表含 MAX_DRONES_PER_PLAYER=50 — 此值本身可能是 world.toml 可配置项]** → 建议 **Core/Engine 方向** 检查 world.toml 中 `drone.max_drones_per_player` 的默认值与 IDL 声明的 50 是否一致，以及 IDL 是否应区分 "default" vs "hard cap"。

---

*评审完成。4 Critical、3 High、5 Medium、2 Low。需修复后重新生成 Registry + 同步全部派生文档，方可 APPROVE。*