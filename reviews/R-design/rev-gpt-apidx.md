# R-design Clean-Slate Review — API/DX

Reviewer: rev-gpt-apidx (GPT-5.5)
Perspective: API / Developer Experience / SDK ergonomics / MCP tool contract

## Verdict: REQUEST_MAJOR_CHANGES

总体方向正确：MCP 不是 gameplay command channel、AI 与人类都通过 WASM 代码参战、`game_api.idl` 统一生成 SDK/MCP schema、应用层证书与用途隔离的安全模型，这些都是很强的 API/DX 基础。

但从 clean-slate API/DX 角度看，当前设计仍存在多个会在实现前就“炸”的接口层问题：同一个概念在不同文档中出现不同 wire format、命名和版本语义；世界可配置/模组能力与 Tier gate 冲突；认证与部署 onboarding 过重且缺少 progressive-disclosure；SDK 生成、ABI/hash、错误模型、能力发现和兼容性策略还没有收敛成一个新人能照着写代码的稳定开发者契约。因此建议在进入实现前做一次 API Contract Freeze：先冻结 IDL、wire format、错误码、versioning、capability discovery、SDK workflow，再允许引擎/网关/SDK 各自实现。

---

## Strengths

1. **AI/Human 公平路径很清晰**
   - `interface.md` 明确 MCP 不提供 `swarm_move` / `swarm_attack` 等 gameplay action，AI agent 必须和人类一样生成/部署 WASM。
   - 这是正确的抽象边界，避免 MCP 变成“特权玩家 API”。

2. **Deferred Command Model 是正确的游戏 API 形态**
   - `tick(snapshot) → Command[]` 统一所有 mutating 操作，由引擎校验和排序执行。
   - 这比 OOP/host-function mutating API 更适合确定性、回放、反作弊和多语言 SDK。

3. **IDL-first 意识存在**
   - 设计多次提到 `game_api.idl → codegen → SDK/MCP schema`，并要求 MCP 工具具备 input/output/error schema。
   - 如果严格执行，这会显著降低 Rust/TS/MCP/Web UI 之间的 drift。

4. **Auth 设计安全边界较强**
   - 应用层证书、用途隔离证书、CSR、自托管/离线友好、AI agent 自注册、request canonicalization 都覆盖到了。
   - `refresh_token` 被定义为 Web session compatibility 而非 trust root，这一点很健康。

5. **规则可见性对 AI/DX 友好**
   - `swarm_get_world_rules`、SDK artifact、world-specific manifest、规则 i18n 等设计让 AI agent 可以读取并适配规则，而不是靠人类读 Wiki。

6. **Debug/Explain API 方向正确**
   - `swarm_explain_last_tick`、`swarm_dry_run_commands`、`swarm_get_replay`、经济/效率查询等是编程游戏必需的 developer loop。

---

## Concerns / Findings

### A1 — High — Wire format 契约自相矛盾：JSON、结构化数据、FlatBuffers 同时出现但没有分层规则

文档中对同一条 WASM 热路径出现多种描述：

- `gameplay.md` §8.5 写：`tick(snapshot_json) → commands_json`，并说引擎将快照 JSON 写入 WASM 线性内存。
- `interface.md` §5 写：快照格式为结构化数据（非纯文本 JSON）。
- `engine.md` §3.4 写：tick 内 snapshot 和 CommandIntent 使用 binary canonical encoding（FlatBuffers），JSON 仅保留为调试/SDK/compat 格式。

这会直接导致 SDK、sandbox、replay、MCP docs 和测试无法对齐。新人会问：我到底返回 JSON Command 还是 FlatBuffers Command？`tick(ptr,len)` 传入的是 JSON bytes、FlatBuffers bytes，还是 SDK 解码后的对象？

**Recommendation**：冻结三层 wire contract：

- Hot path ABI: `tick(input_ptr, input_len) -> output_region`，payload 固定为 `SwarmBinarySnapshotV1` / `SwarmBinaryCommandsV1`。
- Debug/compat: JSON 仅作为 `swarm_dry_run_commands`、docs 示例、CLI inspect 格式。
- SDK surface: TypeScript/Rust 用户永远操作 typed object；SDK 负责编解码，不暴露 wire format。

并在所有文档中统一命名：`SnapshotWireFormat = binary canonical`，`DebugJsonFormat = JSON`。

---

### A2 — High — Command 命名和 shape 未冻结，示例中 `cmd` / `action` / PascalCase / snake_case 混用

同一类命令在不同位置被写成：

- `commands.push({ cmd: "spawn", body: [...] })`
- `{ "action": "Move", ... }`
- `CommandAction::ClaimController`
- `build.Extension` / `body_part.Move`
- MCP tool 使用 `swarm_*` snake_case
- Body part 使用 `Move`, `RangedAttack`, `Claim`

这些差异看似小，实际会制造 SDK codegen、文档搜索、AI 生成代码、错误提示和 replay trace 的长期混乱。

**Recommendation**：定义唯一 canonical command envelope，例如：

```json
{
  "type": "move",
  "entity_id": "drone_...",
  "seq": 12,
  "params": { "direction": "north" }
}
```

并建立命名规则：

- Wire enum: lower_snake_case (`move`, `claim_controller`, `ranged_attack`)
- Rust enum: PascalCase (`Move`, `ClaimController`, `RangedAttack`)
- TS API: camelCase helper (`commands.move(...)`)
- MCP tools: `swarm_verb_object`
- Config keys: lower_snake_case

IDL codegen 必须生成转换层，文档示例只能使用一种 public style。

---

### A3 — High — “世界可配置一切”与 “Tier 1 Core IDL 冻结” 的 API 边界冲突

`gameplay.md` 前半部分说所有游戏内容都通过 `world.toml` / `[[custom_actions]]` / `[[body_part_types]]` / `[[special_effects]]` 定义，引擎核心不硬编码任何游戏内容；但 `engine.md` 的 Tier Entry Gate 又说：

- Tier 1 冻结 Core IDL；
- Dynamic CommandAction、Rhai custom handler、world-specific SDK artifact 是 future-disabled / Tier 2；
- Leech / Fabricate 是 Tier 2+。

同时 `gameplay.md` 又给了默认 world.toml 中 8 个特殊攻击注册，其中包括 Leech / Fabricate，并描述新 CommandAction 自动暴露给 SDK/MCP。

这会让 SDK 作者无法判断：Tier 1 SDK 到底需要支持 dynamic action 吗？Vanilla SDK 是否包含 Leech/Fabricate？如果 `world.toml` 添加 action，旧 WASM 是拒绝部署还是运行时不可见？

**Recommendation**：把扩展能力拆成三个严格 API class：

1. `core_action`：进入 `game_api.idl`，长期兼容。
2. `parameterized_core_action`：world.toml 只能调参数，不改变 SDK type。
3. `extension_action`：必须生成 world-specific SDK，manifest hash 改变，旧模块部署拒绝。

并明确 Tier 1 只能支持前两类。所有文档中将 Leech/Fabricate 从 Tier 1 默认 world.toml 删除，或正式提升为 core action，不能两边同时存在。

---

### A4 — High — Auth onboarding 对新人/AI agent 过重，缺少“最短成功路径”

Auth 文档非常完整，但从 DX 看，首次注册需要理解：server trust、Root CA fingerprint、PoW、CSR、certificate profile、ClientAuthCertificate、CodeSigningCertificate、canonical request、device_label、certificate renewal、refresh token compatibility、possibly email/passkey/federation。

这对安全设计是合理的，但对新人和 AI agent 的第一小时体验不友好。尤其 AI agent 需要通过 MCP 自注册，如果每一步都暴露成底层 tool，LLM 很容易漏掉持久化凭据、选错 certificate profile 或把 secret 写进日志。

**Recommendation**：提供 high-level onboarding API/SDK wrapper，而非只暴露底层工具：

- CLI: `swarm login --server <url> --username <name>`
- MCP resource: `docs/auth/quickstart-ai`
- SDK one-shot: `Auth.registerOrRecover({ username, keyStore, mode: "agent" })`
- 返回 typed `CredentialHandle`，默认持久化到 agent-safe store。

底层 `swarm_register_challenge` / `swarm_submit_csr` 保留，但文档默认路径应从 high-level flow 开始。

---

### A5 — High — MCP 工具目录过大但缺少 profile/capability 分层，会压垮 AI tool selection

`interface.md` 和 `auth.md` 合计定义了大量 MCP tools：世界查看、部署、调试、学习、经济、认证、锦标赛、资源管理等。对人类文档可读，但对 AI agent function calling 来说，几十个 `swarm_*` 工具并列出现会降低选择准确率。

典型失败模式：AI 看到 `swarm_get_snapshot`、`swarm_get_objects_in_range`、`swarm_inspect_entity`、`swarm_get_world_rules`、`resources/read`、`swarm_get_schema` 同时存在，不知道先调用哪一个；认证恢复工具和常规 gameplay 工具混在一个 namespace，容易误用高风险 tool。

**Recommendation**：引入 MCP capability profile：

- `onboarding`: trust/auth/register/docs
- `play`: snapshot/world_rules/player_status/economy
- `deploy`: validate/deploy/list/rollback
- `debug`: explain/dry_run/replay/profile
- `admin`: admin/recovery/epoch/config

`swarm_get_schema(profile="play")` 只返回当前阶段最小工具集。AI onboarding 文档应规定工具调用顺序，而不是只给完整工具表。

---

### A6 — Medium — SDK artifact 与 ABI/hash 的生命周期还不够可操作

设计提到：

- `swarm_sdk_fetch(world_id)`
- `target_manifest_hash`
- `engine_abi_version`
- `mod_manifest_hash = Blake3(world.toml || mods.lock || engine_abi_version)`
- Vanilla 固定 hash `vanilla-v1`

但缺少开发者需要的关键语义：

- SDK artifact 的 semver 如何与 `engine_abi_version` 对齐？
- TypeScript SDK 是 npm package、tarball、还是 MCP resource？
- 离线 CI 如何 pin SDK？
- `world.toml` 调参“不改变 manifest_hash”的规则如何机器判定？哪些字段是 ABI-affecting？
- 模组升级后旧部署是继续运行、暂停、还是强制重编译？

**Recommendation**：定义 `SdkManifest` schema：

```json
{
  "world_id": "...",
  "engine_abi_version": 1,
  "sdk_schema_version": 1,
  "manifest_hash": "...",
  "abi_affecting_inputs": [...],
  "non_abi_inputs": [...],
  "artifacts": {
    "typescript": { "url": "...", "integrity": "..." },
    "rust": { "url": "...", "integrity": "..." }
  },
  "compatibility": { "accepts_manifest_hashes": [...] }
}
```

并让 `swarm_validate_module` 返回明确的 remediation：`fetch_sdk`, `rebuild`, `redeploy`, `wait_for_rules_update`。

---

### A7 — Medium — Error model 分散，缺少全局 Problem Details envelope 和 retry semantics

Auth 有错误码表，但 gameplay/deploy/debug/economy/MCP tools 没有统一错误 envelope。当前会出现几类不一致：

- Auth 错误含 HTTP code、说明、可重试；
- Command rejection 由 TickTrace/RejectionReason 记录；
- SDK mismatch 返回人类字符串；
- MCP JSON-RPC error 与 HTTP error、WebSocket close reason 未统一；
- `swarm_explain_last_tick` 可能解释的是 command rejection，不是 request error。

**Recommendation**：定义全局 `SwarmError`：

```json
{
  "code": "sdk_mismatch",
  "message": "Module built for manifest X; world is Y",
  "category": "deploy",
  "retry": "after_action",
  "remediation": {
    "action": "swarm_sdk_fetch",
    "params": { "world_id": "..." }
  },
  "correlation_id": "..."
}
```

并区分：

- `RequestError`: tool/request 没有成功提交；
- `CommandRejection`: tick 中某条 command 被拒；
- `SimulationWarning`: 成功执行但有潜在问题；
- `SecurityEvent`: auth/admin/security 事件。

---

### A8 — Medium — “只读 host function 不计入指令预算但计入 fuel” 对 SDK 使用者不够透明

`interface.md` 写 host query 不计入指令预算但计入 fuel。对 SDK 用户来说，这意味着 `path_find`、`get_objects_in_range`、`get_world_rules` 调用过多会导致 tick fuel exhaustion，但 API 示例没有显示 cost model。

已知失败案例类似 Screeps：新人不断调用 pathfinding 或全局查询，代码“看起来正确”，但 CPU 爆掉；AI agent 更容易生成这种代码。

**Recommendation**：SDK 必须暴露 budget-aware API：

- `Game.cpu.fuelRemaining()` / `Game.cpu.estimateCost(op)`
- pathfinding 默认缓存，重复 query 自动 memoize
- `swarm_profile` 返回 host-call breakdown
- SDK docs 对每个 host function 标注 relative cost
- `swarm_explain_last_tick` 对 fuel exhaustion 给出具体调用热点，而不是只说超配额。

---

### A9 — Medium — MCP/Web UI/WASM 三个“视野”接口边界需要更明确

设计有三层信息出口：

- WASM snapshot：受 fog_of_war / drone 感知限制；
- MCP：AI 的屏幕和鼠标，与 Web UI 同级；
- WebSocket/Web UI：人类玩家视野、观战、回放。

但部分工具如 `swarm_inspect_entity`、`swarm_get_replay`、`swarm_get_world_rules`、`swarm_get_economy` 没有明确每个字段的 visibility classification。Replay 又可能含完整 OverloadPressure contribution、TickTrace、完整世界配置。

**Recommendation**：所有 output schema 字段增加 visibility class：

- `public`
- `owner_visible`
- `ally_visible`
- `currently_visible`
- `replay_private`
- `admin_only`

MCP/WebSocket/replay 都通过同一 visibility filter 生成，避免某个调试接口意外泄露 fog-of-war 信息。

---

### A10 — Low — 文档作为开发者入口仍偏“系统设计”，缺少最小可运行示例路径

设计文档覆盖面很大，但新人入口不够线性。读者看完仍缺少一个明确路径：

1. 注册/登录；
2. 拉 SDK；
3. 写最小 `tick()`；
4. 本地 validate；
5. deploy；
6. 查看 last tick rejection；
7. 修复并 redeploy。

**Recommendation**：在 design 或 specs/reference 中加入 `First 30 Minutes`：

- Human TS quickstart
- AI agent MCP quickstart
- Rust quickstart
- CI/CD deploy example
- 常见错误与自动修复建议

这不是“教程文案”问题，而是 API 设计验证：如果 quickstart 写不顺，说明 API 还没收敛。

---

## Missing

1. **Canonical IDL 样例缺失**
   - 需要至少给出 `Command`, `WorldSnapshot`, `ModuleManifest`, `SwarmError`, `CertificateBundle`, `SdkManifest` 的正式 schema 片段。

2. **API compatibility policy 缺失**
   - 哪些变更是 patch/minor/major？
   - 旧 WASM 模块支持多久？
   - replay 需要 pin 哪些版本？

3. **MCP capability discovery 缺失**
   - `swarm_get_schema` 应支持按 profile、world、auth state、admin scope 返回不同 schema。

4. **Secret-handling DX 缺失**
   - AI agent credential store 的默认路径、权限、轮换、日志脱敏测试需要成为 SDK contract，而不是只写安全建议。

5. **Deploy lifecycle 状态机缺失**
   - validate → upload → precompile → sign/verify → activate_at_tick → rollback 的状态、幂等键、失败恢复需要统一。

6. **Command rejection taxonomy 缺失**
   - 需要可机器处理的 rejection code，例如 `not_visible`, `out_of_range`, `insufficient_resource`, `action_slot_used`, `fuel_exhausted`, `sdk_mismatch`。

7. **Schema examples 的 golden tests 缺失**
   - 文档中的 JSON/TOML/TypeScript 示例应被 CI 解析验证，避免 drift。

---

## Recommendations

1. **先冻结 API Contract，再冻结实现设计**
   - 输出一个 `api-contract.md` 或 `specs/reference/00-api-contract.md`，集中定义 IDL、wire format、naming、error envelope、versioning。

2. **建立 single source of truth**
   - 所有 MCP schemas、TS/Rust SDK types、docs examples、replay decoder 都从同一个 IDL 生成。
   - 手写示例必须进入 golden tests。

3. **把 Auth 包成 progressive onboarding**
   - 默认文档使用 high-level `swarm login` / `Auth.registerOrRecover()`；高级文档再解释 CSR/cert/canonical request。

4. **给 AI agent 单独设计 MCP workflow**
   - 不要只暴露工具列表。提供明确步骤：discover server → register/login → fetch SDK → inspect rules → generate module → validate → deploy → explain tick。

5. **把 extension model 重新收敛**
   - 明确 Tier 1 禁止 dynamic CommandAction，或正式支持 world-specific SDK；不要两种叙述共存。

6. **统一 visibility filtering**
   - MCP、Web UI、WASM snapshot、replay 都必须声明使用同一 visibility policy engine。

7. **错误必须带 remediation**
   - 面向 AI/DX 的系统，错误码不应只描述失败，还应告诉 agent 下一步该调用哪个工具。

---

## Phase Ordering

这里的 ordering 不是实现阶段，而是设计冻结顺序。建议按以下顺序推进设计收敛：

1. **API primitives freeze**
   - `EntityId`, `PlayerId`, `RoomId`, resource amount, fixed-point number, timestamp/tick, manifest hash, certificate id。

2. **Wire format freeze**
   - WASM hot path binary format、debug JSON format、MCP JSON-RPC envelope、WebSocket event envelope。

3. **IDL/schema freeze**
   - `WorldSnapshot`, `Command`, `CommandRejection`, `SwarmError`, `SdkManifest`, `CertificateBundle`。

4. **Capability/profile freeze**
   - MCP profiles: onboarding/play/deploy/debug/admin；visibility classes；rate-limit classes。

5. **SDK workflow freeze**
   - TS/Rust quickstarts、SDK fetch/build/validate/deploy、offline CI pinning、manifest mismatch remediation。

6. **Auth onboarding freeze**
   - High-level registration/recovery APIs first，low-level CSR/cert APIs second。

7. **Gameplay/rules extension freeze**
   - Tier 1 core actions 与 Tier 2+ extension actions 的边界最终定稿。

---

## Final Assessment

这个设计不像“方向错了”的失败案例；相反，它像很多成功平台在早期都会遇到的典型问题：系统架构已经很强，但 API contract 还没有被当作产品本身冻结。若现在直接实现，最可能出现的失败不是引擎跑不起来，而是 SDK、MCP、Web UI、Auth、Replay 各自实现了“看起来合理但互不兼容”的接口。

因此 verdict 是 **REQUEST_MAJOR_CHANGES**：不是推翻设计，而是要求在实现前进行 API/DX contract 收敛。完成上述收敛后，整体设计可进入 CONDITIONAL_APPROVE 或 APPROVE。