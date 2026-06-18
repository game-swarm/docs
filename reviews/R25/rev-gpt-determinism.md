# R25 Closure Verification — 确定性评审 (GPT-5.5)

Scope: 仅验证 R24 残留 B2/B3 GAP 是否闭合；未进行开放式新问题审计。

## B2: GAP

结论：B2 未闭合。

证据：

1. Storage tax thresholds (10K → 30% capacity)
   - 在允许读取的四个文件中，未找到 `10,000` / `10000` / `30%` storage tax threshold 的规范性定义或指向单一权威源的引用。
   - `design/README.md` 仅声明 `specs/reference/` 为 API 参考目录，未给出该经济规则的权威链接或数值绑定。
   - `06-phase2b-system-manifest.md` 仅将 S29 `resource_ledger` 标为 `Linked to: specs/core/08-resource-ledger.md`，但本次允许范围未包含该文件；在允许范围内无法确认 storage tax 已由单一事实源闭合。

2. Gameplay upkeep (-40 ~ -3,150 → 引用)
   - 在允许读取的四个文件中，未找到 `-40` / `-3,150` / `3150` upkeep 数值或明确的权威引用。
   - `design/README.md` 仅列出 vanilla mod `empire-upkeep`，未把 upkeep 数值绑定到可验证的单一事实源。

3. Recycle §2.3 → §2.5 / 单一事实源
   - `02-command-validation.md` §3.9 仍写有固定规则：`返还 50% 身体部件成本作为能量给 spawn`。
   - 同文件 §3.18 又写入比例公式：`refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`，并说明半寿 25%、剩余 20%/10% lifespan 为 10%。
   - 这两个规则在同一允许文件内并存且未声明 §3.18 覆盖 §3.9，Replay 实现可合理选择不同规则，导致 `tick(seed, state, commands) -> new_state` 对 Recycle refund 不闭包。

## B3: CLOSED

结论：B3 已闭合。

证据：

1. `06-phase2b-system-manifest.md` §S14 明确唯一权威优先级链：`Hack > Drain > Overload > Debilitate > Disrupt > Fortify`，并标注这是 Swarm 引擎中该优先级链的唯一定义。
2. 同一 §S14 定义 deterministic merge sort：S11-S13 先写 per-system sub-buffer，再由 serial collector 按 `(priority_class, intent_source.entity_id, intent_target.entity_id)` 归并排序，禁止依赖 nondeterministic push order。
3. `02-command-validation.md` §3.16 已删除旧优先级表，只保留指向 `06-phase2b-system-manifest.md` §S14 的引用，并明确不得复制/粘贴优先级链。
4. `01-tick-protocol.md` §3.4 也将 ECS 系统执行顺序委托给 Complete Tick Execution Manifest，并在摘要中保留 `special_attack_reducer → pending_intents buffer → canonical priority sort → status_advance_system` 链路。

## Verdict: REJECT

B3 已闭合；B2 仍有 Blocking GAP。特别是 Recycle refund 在同一文件内存在固定 50% 与 lifespan 比例公式两套可执行语义，且 storage tax / gameplay upkeep 在允许文件范围内没有可验证的单一事实源引用。因此不能给出 APPROVE。