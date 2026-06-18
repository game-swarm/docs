# R25 Closure Verification — Economy Reviewer (GPT-5.5)

## B2: GAP

B2 未完全闭合。

证据：
- API/经济单一事实源部分已闭合：`specs/reference/api-registry.md` 明确声明 API Registry 由 IDL 自动生成，经济数学权威为 `specs/core/08-resource-ledger.md`；Economy Operations 中 `StorageTax`、`UpkeepDeduction`、`RecycleRefund` 均引用 Resource Ledger。
- Storage tax thresholds 已闭合：`api-registry.md` §5.7 将 tier 1 threshold 标为 30% capacity，tier 2 为 60%，tier 3 为 85%；`specs/core/08-resource-ledger.md` §2.1/§2.2 使用同一 `[(30,0),(60,1),(85,5),(100,20)]` tiered 公式。
- Recycle §2.3→§2.5 已基本闭合：`specs/core/08-resource-ledger.md` §2.5 定义 lifespan-proportional 10%–50% 权威公式，`api-registry.md` §10.2/§10.3 也引用同一公式。
- 但 gameplay upkeep 残留 GAP 未闭合：`design/gameplay.md` §“帝国维护费示例效果”仍直接声明旧数值“小帝国 ≈40/tick、中帝国 ≈275/tick、大帝国 ≈2100/tick、巨帝国 ≈3150/tick”，并附带“Vanilla 默认值...待 B6 闭合时产出”的旧说明，而不是改为引用 Resource Ledger / Economy Balance Sheet。
- 该残留数值与 `design/economy-balance-sheet.md` §1 的 Standard 维护费验证表不一致：1/5/20/50 房间为 55/375/3,000/15,000 per tick。它也与 `specs/core/08-resource-ledger.md` §Empire Upkeep 的 Standard 默认公式引用关系不一致。

结论：B2 仍存在 blocking GAP，原因是 gameplay 中旧维护费曲线/数值仍作为正文事实存在，未改为单一权威引用。

## B3: CLOSED

B3 已闭合。

证据：
- `specs/core/02-command-validation.md` §3.16 明确标注 R24 B3-GAP 修复：特殊攻击优先级以 `06-phase2b-system-manifest.md` §S14 为唯一权威；该处不再重列可冲突的优先级顺序。
- 同一段进一步要求实现者以 `special_attack_reducer` (S14) 的 canonical priority sort 为准，不得从 command-validation 复制/粘贴优先级链。
- `specs/core/06-phase2b-system-manifest.md` §S14 明确给出唯一权威优先级链：`Hack > Drain > Overload > Debilitate > Disrupt > Fortify`，并声明 `02-command-validation.md` 已删除旧优先级表。
- `06-phase2b-system-manifest.md` §Special Attack Unique Writer Contract 还定义 `status_adv` 与 `spec_atk_red` 的唯一写入者关系，支撑唯一权威链落地。

结论：B3 的冲突表删除与唯一权威链标注均已闭合。

## Verdict: REJECT

B3 为 CLOSED，但 B2 仍有 blocking GAP：`design/gameplay.md` 维护费曲线仍保留旧数值/旧说明，未完成“gameplay upkeep (-40~-3,150 → 引用)”闭合要求。