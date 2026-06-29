# R40 CV Delta — R39 Fix Wave Closure Verification

**Verdict: APPROVE**

## Scope

本轮验证 R39 fix wave 的 16 个修复提交（排除 `55dbddf docs: R39 10-reviewer 报告归档`）是否闭合，并执行全仓关键词残留扫描（排除 `reviews/`）。

验证提交范围：

1. `4fa4dc4` docs: fix auth security boundaries
2. `508c07c` docs: sync mcp security auth modes
3. `15ca46d` docs: tighten wasm sandbox security
4. `50749ca` docs: clarify deploy signing example
5. `786f324` docs: fix deploy payload transport labels
6. `12f85f9` docs: clarify getting started deploy hash
7. `08bf83d` docs: clarify interface deploy hash
8. `63edb24` docs: clarify engine deploy cache hash
9. `267d4aa` docs: clarify gameplay deploy idempotency hash
10. `f3b444d` docs: R39 fix B1 — D1 A01 handler + C-BLOCKER-02 S22 Leech + Phase 2a sorted loop + Spawn fix
11. `c2de43b` docs: R39 fix D6 — cross-room 先在 Bevy World 内裁决再写 staging payload
12. `c2471f2` docs: R39 fix — persistence D5 staging→publish + D6 cross-room 前裁决 + direct UPDATE dev-only
13. `017f06f` docs: fix api dx registry counts
14. `75fc273` docs: R39 fix B3 — Economy
15. `f32345c` docs: R39 fix — snapshot-contract COLLECT vs execution rollback 概念分离
16. `8ff9eb7` docs: R39 fix — Economy+Engine 残余

## Closure Checklist

| 项 | 结论 | 证据 |
|---|---|---|
| `06-phase2b-system-manifest.md` Phase 2a sorted command loop | PASS | §1 明确 `Phase 2a: Sorted Command Loop`，使用 `for cmd in sorted(global_queue, key=command.sort_key)`。 |
| `06-phase2b-system-manifest.md` A01 handler not system | PASS | 文中明确 “A01 action_dispatch 是 Phase 2a per-command handler，不计入 manifest system 表”，A01 小节标题也标注 `not a manifest system`。 |
| `06-phase2b-system-manifest.md` S22 Leech 不写 PendingDamage | PASS | S22/S22a 相关伪代码明确 `不写 PendingDamage`，Leech HP 影响由 age acceleration + aging/decay 覆盖。 |
| `06-phase2b-system-manifest.md` manifest hash / 31 systems | PASS | §1 标题为 `System Schedule (31 systems)`，正文、矩阵、验证项均统一为 31 systems。 |
| `01-tick-protocol.md` Phase 2a sorted loop | PASS | Tick 流程图与排序章节均使用 sorted global queue；排序键同用于 Phase 2a inline apply 与 TickCommitRecord。 |
| `01-tick-protocol.md` Spawn 校验+扣费+入队 | PASS | §3.3 明确 Spawn 在 Phase 2a 校验、扣费、入队 `PendingSpawn`，实际创建由 S08 处理。 |
| `01-tick-protocol.md` cross-room staging 前裁决 | PASS | Shadow Write 流程先在 Bevy World 内完成跨房间裁决，再写 affected room staging payload。 |
| `01-tick-protocol.md` TickCommitRecord same-tx | PASS | §6.3.4、§9.4 明确 TickCommitRecord 与状态写入同一 FDB 事务，失败即 abandon/rollback。 |
| `01-tick-protocol.md` Shadow Write production | PASS | §3.5 明确生产采用 staging payload + GlobalTickCommit manifest-only publish，staging 未发布不可见。 |
| `05-persistence-contract.md` D5 staging→publish | PASS | §3 明确 R39 D5：生产统一 per-room staging payload + GlobalTickCommit manifest-only publish。 |
| `05-persistence-contract.md` direct UPDATE dev-only | PASS | 直接 `UPDATE entity/resource/controller/... rows` 标注为 dev/test small profile only，production skip/use Shadow Write。 |
| `05-persistence-contract.md` D6 cross-room before staging | PASS | Shadow Write 分区语义与 `01-tick-protocol.md` 对齐，生产读取仅走 committed manifest。 |
| `09-snapshot-contract.md` COLLECT vs execution rollback | PASS | 文档开头明确 per-player perception snapshot 与 Bevy World execution rollback snapshot 为独立概念，不可混用。 |
| `design/auth.md` C-BLOCKER-06/07/08 + D7/D8/D9 + X1 | PASS | deploy 签名边界、WS canonical payload、per-message seq/MAC、admin certificate fields、seccomp clone policy 均已落文。 |
| `03-mcp-security.md` auth modes / WS canonical | PASS | per-tool auth mode 与 Browser/Agent WS 边界已同步，Agent WS canonical payload 与 registry/auth 对齐。 |
| `04-wasm-sandbox.md` seccomp clone policy | PASS | §4.1 给出 clone flags matrix，禁止 `CLONE_VFORK`、无 `CLONE_THREAD` 的 clone、fork/vfork/clone3。 |
| `08-resource-ledger.md` StorageTax per-unit / Merchant OOS | PASS | StorageTax 以 capacity/tier taxable units 计算；Merchant NPC 明确 Out-of-Scope。 |
| `economy-balance-sheet.md` D12 权威可重算 | PASS | 维护曲线、StorageTax、ledger 引用收敛到权威公式，Balance Sheet 作为可重算来源。 |
| `gameplay.md` Merchant RFC / D11 repair 物理约束 | PASS | Merchant 未作为当前 PvE 经济内容；repair 明确受 range/capacity/queue/Depot local resource 物理约束，不存在全局 repair cap/cost。 |
| `modes.md` Merchant 移除 | PASS | World PvE 文本仅保留 `RFC-MERCHANT`，声明不属于当前 World PvE 内容。 |
| `api-registry.md` D13 三口径 | PASS | CommandAction 数量、公共 `object_id`、Spawn actor/target、ledger/API schema 口径已统一。 |
| `commands.md` object_id / structure_type | PASS | 示例均使用 `object_id`，Build 示例使用 `structure_type`。 |
| `mcp-tools.md` / `codegen.md` / `interface.md` 计数同步 | PASS | API DX 计数同步为 11 个 CommandAction + Action dispatch；interface 不再重列冲突口径，引用 Registry 权威。 |

## Full-Repo Keyword Scan

扫描命令口径：`rg -n --glob '!reviews/**' <pattern> /data/swarm/docs`。

| 残留项 | 结果 | 说明 |
|---|---|---|
| `UNIQUE HitPoints` | PASS | 未命中。 |
| `21 个 CommandAction` | PASS | 未命中。 |
| S22 → `PendingDamage` | PASS | 未发现 S22/Leech 写入 `PendingDamage` 的残留；仅命中“combat writer 写 PendingDamage”和“Leech 不写 PendingDamage”的正确表述。 |
| `A01` 作为 system entry | PASS | A01 命中均为 “per-command handler / not manifest system” 或 buffer 来源说明；未发现将 A01 计入 manifest system 的残留。 |
| `staging 写入后` cross-room | PASS | 未命中。 |
| `PoW 自身限速 / 无额外 IP 限制` | PASS | 未命中。 |

## Notes

- `reviews/` 内仍保留 R39/R37 审核报告中的旧问题描述，这是预期审计轨迹，不纳入残留判定。
- 非 `reviews/` 正文中未发现本轮指定禁用短语残留。

## Final Verdict

**APPROVE** — R39 fix wave 16 commits 的指定闭合项均已验证通过；全仓关键词扫描（排除 `reviews/`）无阻塞残留。
