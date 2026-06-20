# R28 Closure Verification — rev-dsv4-apidx (DeepSeek V4 Pro)

> R28 API/DX Closure Verification。验证 R27 共识项 B2、D-H2、ML 的文档闭合状态。
> Scope: 仅验证编号项，禁止发现新问题。
> Docs reviewed: api-registry.md, codegen.md, 02-command-validation.md, commands.md, 08-api-idl.md

## Verdict: CONDITIONAL_APPROVE

核心 B2 项（D1-D5）全部正确闭合。2 个中等 GAP（02-command-validation.md 残留非 canonical 代码、ObjectiveType enum 缺失）+ 1 个已追踪 ML-8 待完成项，均不阻塞 SDK 生成或 API 合同冻结。

---

## B2: API/IDL/codegen 单事实源 → CONDITIONALLY CLOSED

### CLOSED items

**D1 — `object_id` 缺失** → CLOSED
- api-registry.md §1 line 41: `共享字段 object_id: EntityId` — 所有 21 个 CommandAction 变体均包含。此声明为共享字段 header，避免在每行重复。IDL 中每个 action schema 均含 `object_id`。

**D2 — RejectionReason 计数 79 → 47** → CLOSED
- api-registry.md §2 line 90: `共计 47 个 canonical code（35 from game_api + 12 from auth_api）`
- codegen.md line 28: `RejectionReason 数量 (当前 47)`

**D3 — CommandAction 计数 19 → 21** → CLOSED
- api-registry.md §1 line 44: `变体总数: 21`
- codegen.md line 26: `CommandAction 数量 (当前 21)`
- Leech + Fabricate 保留为 Tier 2，正确计入 21。

**D5/D10 — codegen.md 自矛盾/双路径** → CLOSED
- codegen.md line 24: 自声明为手工维护文档，附带 CI `--check` 校验提示
- 单一 codegen 工具：`hermes codegen generate`（line 47-51）
- api-registry.md 附录 A 保留 `python3 scripts/generate_api_registry.py` 作为实现细节引用，但 codegen.md 是权威入口

**D1 裁决 — JSON-RPC error envelope 统一为 numeric** → CLOSED
- api-registry.md §8 line 677-690: `error.code = -32000`（JSON-RPC numeric），`error.data.rejection_reason` 承载 canonical RejectionReason enum
- 明确声明 SDK 从 `rejection_reason` 生成 typed exception

**Host function 类型冲突** → CLOSED
- api-registry.md §4.1 line 408: `host_get_objects_in_range range: u32` — 统一为 `u32`
- §4.5: ABI 错误优先级表完整，budget 错误码使用 canonical `ERR_BUDGET_EXHAUSTED(-4)` / `ERR_PLAYER_BUDGET(-5)` / `ERR_GLOBAL_BUDGET(-6)`

**Auth namespace** → CLOSED
- api-registry.md §2.3: game_api `InvalidCertificate`(28) 与 auth_api `InvalidCertificate`(1001) 正确命名空间隔离
- §2.5 命名规范说明了两层 `NotAuthorized`(29 vs 1002) 的区别

### GAPs (non-blocking)

**GAP-1: 02-command-validation.md 残留 6 个非 canonical RejectionReason 码** (Medium)

R27 X4 修复要求: "把逐指令表中的非 canonical 项统一标为 debug_detail 或映射到 canonical code"

当前状态 — 部分已标注 `(debug_detail)`（如 "非 Drone", "fatigue", "非己方"），但以下 6 个条目仍使用非 canonical 码且未标注：
- L169: `TileBlocked` → 应映射到 canonical 或标注 `(debug_detail)`
- L171: `StillSpawning` → 同上
- L269: `ExceedsRoomCapacity` → 同上
- L374: `InvalidDamageType` → 同上
- L375: `AlreadyDebilitated(damage_type)` → 同上
- L548: `MainActionQuotaExceeded` → 不在 canonical 47 中

影响：SDK 作者逐指令阅读时可能误认这些为稳定 wire enum。低风险，因为 commands.md L226 已标注旧码废弃声明且 api-registry.md 是权威源。

**GAP-2: game_api.idl.yaml D1 裁决未同步** (Low)
- IDL YAML L1672 仍写 `error.code string`，而 Registry §8 已按 D1/A 裁决改为 `error.code = -32000` numeric
- IDL 是机器可读权威源，应优先同步

---

## D-H2: swarm_get_objectives API → CLOSED (enum gap)

**工具注册** → CLOSED
- api-registry.md §3.2 Onboarding L244: `swarm_get_objectives` 完整注册
  - Input: `{player_id?, scope?}` — 可选参数
  - Output: `{objectives: [{id, type, description, required, current, reward, priority, expires_at?}]}`
  - Rate limit: 5/tick
  - Scope: `swarm:read`
- Onboarding 计数: 11 → correct
- 总 MCP 工具: 57 → correct (was 56)

**GAP-3: ObjectiveType enum 缺失** (Medium)

R27 D-H2 commit 8af9bc0 message: "+ObjectiveType enum"。但全文搜索 `ObjectiveType` 返回 0 结果。Output schema 中的 `type` 字段引用该枚举但无定义。API/DX 层面，SDK codegen 需要 ObjectiveType 的 variant 定义才能生成正确的 TS/Rust 类型。建议在 api-registry.md 或 game_api.idl.yaml 中补充 ObjectiveType 枚举定义（如 `Survive, Expand, Harvest, Defend, Attack, Build, Research, Trade` 等）。

---

## ML 项 (API/DX-relevant)

### ML-8: IDL 字段 required/optional/default 注解 → KNOWN INCOMPLETE

api-registry.md §3 L395 自声明：`当前 YAML 中仅部分字段有标注——需补齐全部工具。`
这是 R27 修复后留下的追踪标记。已部分完成（MCP 工具表中的 `?` 标记如 `{player_id?}`, `{topic?}`, `{scope?}` 可用于推断 optionality），但未完成全部工具的 required/optional/default 三元组标注和 per-tool errors 列表。此状态已在文档中明确标记为待完成，不阻塞当前合同。

### ML-9: Auth API shortcut schema 重复 → CLOSED

- api-registry.md §3.3 L339: `R27 ML-9` 注释说明 game_api 中的 `swarm_auth_login`/`swarm_auth_refresh` 为简化形态，§3.3 为完整 schema
- game_api Auth category（§3.2）保留了 Note 说明完整 schema 见 §3.4 Auth API 工具
- SDK 不生成重复函数：已明确 game_api 中的 2 个 auth 工具为 capability shortcut，不参与独立 SDK 生成
- ⚠️ 缺少机器可读的 `schema_source=auth_api` 字段——当前仅为 prose 说明（Minor gap, already tracked）

### ML-12: InsufficientResources 清理 → CLOSED for API/DX docs

- api-registry.md §2.2 L127: `InsufficientResource` — `统一单数形式；废弃 InsufficientResources, InsufficientEnergy`
- api-registry.md §2.5 命名规范 L197: `统一使用 InsufficientResource（单数），废弃 InsufficientResources/InsufficientEnergy`
- codegen.md: 无残留
- 02-command-validation.md: 无残留
- 09-snapshot-contract.md L269/295: 仍保留 `InsufficientResources`（旧形式）— 此文件为核心引擎快照合同，非 API/DX 文档，不在本轮验证范围。

---

## Strengths

- 单事实源方向已从 R27 的 CRITICAL 状态大幅收敛：D1-D5 + codegen path + error envelope + host ABI 核心冲突全部解决
- `object_id` 共享字段声明是优雅的解决方案——避免了 21× 重复声明，同时满足 SDK codegen 的类型完备性
- MCP 工具表已建立统一的九列结构（Input/Output Schema + Rate Limit + Required Scope + Subject Source + Replay Class + Visibility Filter + Rate Limit Key + 来源 IDL），为 SDK stub 生成提供了机器可读基础
- D-H2 `swarm_get_objectives` 提供了 AI agent 宏目标 API，Onboarding 从 10 增至 11 工具
- JSON-RPC error envelope 已按 D1/A 裁决统一

## Concerns (non-blocking)

1. **02-command-validation.md 残留码**：6 个非 canonical 码未标注 `(debug_detail)`，对逐指令阅读的 SDK 作者产生误导风险
2. **ObjectiveType enum 缺失**：`swarm_get_objectives` Output schema 引用 `type` 字段但无枚举定义
3. **IDL YAML ↔ Registry 未对齐**：game_api.idl.yaml 的 D1 error.code 未同步
4. **ML-8 追踪项**：YAML field annotations + per-tool errors 仍在进行中

## Type Gaps

| Gap | Location | Impact |
|-----|----------|--------|
| ObjectiveType enum | api-registry.md / game_api.idl.yaml | SDK codegen 无法生成 `type` 字段的 typed enum |
| Non-canonical codes in validation matrix | 02-command-validation.md | SDK authors may import stale codes |
| `schema_source` field missing | api-registry.md MCP auth tools | Machine-readability gap for SDK dedup |

## Error Handling Coverage

- ✅ Canonical RejectionReason: 47 codes across 5 layers, properly namespaced
- ✅ Auth layer: 12 codes with 1000+ namespace offset, distinct from game_api codes
- ✅ Host function ABI: 9 error codes with priority ordering
- ✅ detail_level: competitive/practice/training three-tier detail control
- ⚠️ MCP per-tool errors: listed as ML-8 tracking item, not yet complete
- ✅ JSON-RPC error envelope: unified to numeric code + data.rejection_reason

## Summary

| Item | Status | Details |
|------|--------|---------|
| B2-D1 (`object_id`) | CLOSED | Shared field declared, all 21 variants covered |
| B2-D2 (RejectionReason 47) | CLOSED | api-registry + codegen aligned |
| B2-D3 (CommandAction 21) | CLOSED | api-registry + codegen aligned |
| B2-D5/D10 (codegen path) | CLOSED | Single path, hand-maintained with CI |
| B2 X4 (validation cleanup) | GAP-1 | 6 non-canonical codes in 02-command-validation.md |
| B2 D1/Y (error envelope) | GAP-2 | IDL YAML not synced to D1/A verdict |
| D-H2 (swarm_get_objectives) | GAP-3 | Tool registered, ObjectiveType enum missing |
| ML-8 (field annotations) | INCOMPLETE | Tracked in api-registry.md, WIP |
| ML-9 (auth alias) | CLOSED | prose annotation, `schema_source` field pending |
| ML-12 (InsufficientResources) | CLOSED | api-registry.md clean; non-API doc residual N/A |

**R29 建议**: 闭合 GAP-1/GAP-2/GAP-3 后进入 narrower CV。GAP-1 为标注性修改（~6 行），GAP-2 为 IDL YAML 一行同步，GAP-3 需补充 ObjectiveType enum 定义（~10 行）。三项均为低工作量 non-blocking 修复。