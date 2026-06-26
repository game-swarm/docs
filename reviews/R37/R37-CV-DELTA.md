# R37 CV Delta — R36 Fix Wave 增量闭合验证

**Reviewer**: Closure Verification Reviewer (Delta Scan)  
**Scope**: 验证 R36 CV fix 4 commits (`8c59716`, `d2bbdd0`, `caa2c1a`, `5baa4cb`) 对 R36-CV-STANDARD S1-S6 与 R36-CV-DELTA CV-1~CV-11 的闭合情况，并检查新漂移。

## Verdict

**REQUEST_CHANGES**

R36 fix wave 已闭合大部分 Registry/API/IDL/设计层漂移：MCP 工具数、RejectionReason 48、CSR no email、PoW 24、Deploy 同步、WS canonical payload、RNG derive、PLAYTEST-GATED 路径叙事、world-rules fixed-point、Rhai capability 13 等均有明确修复。但增量验证仍发现 **2 个 R36 残留未闭合**，且链接抽查存在新的/既存的可点击性问题，因此不能 APPROVE。

## 逐项闭合结果

| R36 项 | 结论 | 核验摘要 |
|---|---:|---|
| S1 / CV-7 Action 模型迁移 | **未闭合** | `08-api-idl.md` 与 `design/interface.md` 已改为 11 CommandAction + `Action` dispatch；但 `02-command-validation.md` 字段级表和示例仍把 combat/special action 写成顶层 `{ "action": "RangedAttack" }` 等旧形态。 |
| S2 / CV-7 Leech/Fabricate `[[custom_actions]]` | 闭合 | Leech/Fabricate 属性表已改为 `ActionRegistry vanilla action`，vanilla 不再通过 `[[custom_actions]]` 注册。 |
| S3 / CV-2 RejectionReason 47/48 | 闭合 | 非 reviews 文档未再命中 47 canonical 残留；Registry、commands、codegen、interface 均统一为 48。 |
| S4 / CV-9 RNG derive | 闭合 | Registry、host-functions、sandbox、interface 均改为 `derive_rng(domain, world_seed, tick, actor_or_entity_id, sequence)`，无旧 `(tick_seed, player_id, drone_id, sequence)` 残留。 |
| S5 cross-file links | **未完全闭合** | R36 指定的 `design/auth.md → ../specs/reference/api-registry.md` 已修；但快速抽查仍发现 `design/auth.md` 中 `specs/security/03-mcp-security.md` 从 `design/` 相对解析会断。 |
| S6 PLAYTEST-GATED | 闭合 | stale 路径已更新为 `specs/core/08-resource-ledger.md`、`design/economy-balance-sheet.md`；PG-2 已改为“已规范化，待 playtest 验证平衡性”。 |
| CV-1 MCP 工具计数 | 闭合 | `api-registry.md` 与 `mcp-tools.md` 均为 Game API 57、Auth API 12，分组计数同步。 |
| CV-3 CSR email | 闭合 | `swarm_submit_csr` Registry/Auth schema 不再接收 `email?`；邮箱绑定保留在认证后 recovery/email bind 工具。 |
| CV-4 PoW 24 vs 20 | 闭合 | Registry Limits 与 challenge schema 均为 24 bits，未见 20 bits 默认残留。 |
| CV-5 Deploy 同步 | 闭合 | `swarm_deploy` schema 已显式包含 `deploy_payload`、`code_signature`、`certificate_id`、`version_counter`，并声明同步 FDB 原子事务。 |
| CV-6 WS security | 闭合 | Registry §3.5 已采用 `SWARM-WS-MSG-V1`、`direction/session_id/seq/tick/body_hash/audience` 与 `seq == last_seq + 1`。 |
| CV-8 HP writer contract | **未闭合** | S15 仍声明 `UNIQUE HitPoints writer`，但 R/W matrix 仍标 S10/S22/S24 写 `HitPoints`，并新增 domain-specific writer 注释，继续与 UNIQUE/CI gate 表述冲突。 |
| CV-10 Vanilla/economy/floats | 部分闭合 | `world.toml` 容量与 Vanilla `{Energy: 5000}`方向已修，`special_param` 改为 bps/ppm；未把 Matter/Fabricate 是否非-vanilla 的口径完全裁清，但不构成本轮主要 blocker。 |
| CV-11 Rhai actions/capability | 闭合 | `rhai-mod-abi.md` 给出 5 个 actions API 与 13 个 capability；`design/gameplay.md` 白名单同步为 5 个。 |

## Blockers

### R37-CV-D1 — Action dispatch 示例仍保留旧 wire shape

**涉及 R36 项**: S1 / CV-7  
**Severity**: Blocker

证据：
- `specs/core/02-command-validation.md:591` 字段级穷举表仍将 `Attack`、`RangedAttack`、`Heal`、`Hack`、`Drain`、`Overload`、`Debilitate`、`Disrupt`、`Fortify`、`Leech`、`Fabricate` 与基础 Command 并列，读者仍会理解为顶层 `CommandAction`。
- `specs/core/02-command-validation.md:676`、`:721`、`:735`、`:749`、`:763`、`:777`、`:791`、`:805`、`:819` 的 JSON 示例仍为 `{ "action": "RangedAttack", ... }` / `{ "action": "Leech", ... }` 等旧形态，而非 `CommandAction::Action { type, payload }` 的 wire shape。

影响：D3 的核心目标是删除 combat/effect 顶层 `CommandAction`，统一通过 `ActionRegistry` dispatch。当前文字虽声明边界，但示例和校验表仍足以诱导 SDK/schema/实现生成旧 discriminated union。

要求：将字段级表改成 `Action(type=...)` 或单独标为 ActionRegistry validation table；所有 combat/effect JSON 示例改为统一 dispatch 形态，并保持与 `api-registry.md` / `08-api-idl.md` 一致。

### R37-CV-D2 — HP writer contract 仍与矩阵自相矛盾

**涉及 R36 项**: CV-8  
**Severity**: High / Blocker for CI-verifiable closure

证据：
- `specs/core/06-phase2b-system-manifest.md:222` 标题仍为 `S15: damage_application (UNIQUE HitPoints writer)`。
- `specs/core/06-phase2b-system-manifest.md:224` 声明不存在任何其他 system 直接修改 HitPoints。
- `specs/core/06-phase2b-system-manifest.md:229` 声明 CI 应拒绝任何其他 system 对 `HitPoints` 的写操作。
- 但矩阵中 `specs/core/06-phase2b-system-manifest.md:424`、`:441`、`:443` 仍分别标 S10、S22、S24 对 `HitPoints` 为 W，且 `:432` 的 domain-specific writer 注释又说明三者写入同一 component。

影响：R36 原问题要求“HP 写入责任可由 CI 静态验证”。当前同时存在 “S15 UNIQUE” 与 “domain-specific 多 writer”，CI 规则仍不可实现。

要求：二选一闭合：要么保留 S15 真唯一 writer，S10/S22/S24 改写 pending buffer；要么删除 UNIQUE/CI 拒绝其他 writer 表述，定义机器可验证的多 writer 顺序/语义域规则。

## Fast Grep 结果

按任务要求在非 `reviews/**` 范围执行快速扫描：

| 检查 | 结果 |
|---|---|
| `21 个 CommandAction` | 未命中 |
| RejectionReason `47` canonical | 未命中 |
| vanilla `[[custom_actions]]` 注册 | 未发现 vanilla 通过 `[[custom_actions]]` 注册；命中均为“仅服主扩展/不通过 custom_actions”说明 |
| `special_param` float / `0.5` / `2.0` | 未发现旧 float 示例；仅命中 fixed-point 禁浮点说明 |

## 链接完整性抽查

- R36 S5 指定断链中，`design/auth.md` 指向 API Registry 的链接已修为 `../specs/reference/api-registry.md`。
- 快速脚本排除 `reviews/**` 后仍发现多处相对路径问题，其中与本轮修复邻近的 `design/auth.md:837` 使用 `[MCP 安全规范](specs/security/03-mcp-security.md)`，从 `design/` 目录解析为 `design/specs/security/03-mcp-security.md`，目标不存在；应为 `../specs/security/03-mcp-security.md`。
- 另有 `design/gameplay.md` / `design/interface.md` / `design/tech-choices.md` 等多处设计文档头部或正文使用仓库根相对路径，在 Markdown 解析器中从当前文件目录解析会断；建议单独做一次 link normalization。

## 已确认无新增漂移的方向

- CSR bootstrap 不再接收 email；邮箱绑定留在认证后工具。
- PoW 默认难度统一为 24 bits。
- Deploy API 从 async object-store 叙事收敛为同步 `deploy_mutation`。
- WS per-message security 收敛为 canonical payload + strict seq。
- RNG ABI 与派生公式已同步。
- MCP 工具数与 Auth 工具数已同步。
- Rhai capability 计数统一为 13，actions API 白名单统一为 5。
- `PLAYTEST-GATED.md` 不再把已规范化 special attack 状态机描述为规范缺失。

## Final Verdict

**REQUEST_CHANGES**

R36 fix wave 不满足“18 项全部闭合 + 无新漂移”。至少需先修复 `02-command-validation.md` 的 Action dispatch 旧示例/校验表，以及 `06-phase2b-system-manifest.md` 的 HitPoints writer contract 矛盾；随后建议跑全仓 Markdown link checker，修复邻近断链后再进入 R38 closure verification。
