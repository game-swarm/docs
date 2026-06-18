# R25 Closure Verification — 架构评审 (GPT-5.5)

## B2: GAP

证据：
- `specs/reference/api-registry.md:554-556` 已把 storage tax thresholds 改为 capacity 百分比：30% / 60% / 85%，其中 tier 1 明确为 **30% capacity**，满足 “10K→30% capacity” 的闭环要求。
- `specs/reference/api-registry.md:739-740` 已把 `StorageTax` 与 `UpkeepDeduction` 收敛到 API/economy registry，并引用 Resource Ledger 权威公式；`UpkeepDeduction` 不再在 registry 中展开旧的 gameplay 数字表，而是引用 `specs/core/08-resource-ledger.md` 的 Empire Upkeep。
- `specs/reference/api-registry.md:738` 与 `specs/reference/api-registry.md:752` 已声明 `RecycleRefund` 为 lifespan-proportional 10%–50% 公式，满足 Recycle 向 lifespan 约束公式迁移。
- 但 `specs/core/02-command-validation.md:288` 仍保留 “返还 50% 身体部件成本作为能量给 spawn。” 这一旧固定比例声明；同文件后续 `specs/core/02-command-validation.md:483-504` 又声明 lifespan-proportional 10%–50% 修正。

架构结论：B2 未完全闭合。API/economy 单事实源方向已经基本建立，但 Recycle 在允许验证文件内仍存在同文件内的旧固定 50% 语义与新 lifespan 公式并存。这个残留属于“看起来只是说明文字，实际会让实现者按错误规则实现”的典型冲突源；因此 B2 不能判 CLOSED。

## B3: CLOSED

证据：
- `specs/core/02-command-validation.md:433-437` 已删除旧的特殊攻击优先级表，并明确声明特殊攻击优先级以 `06-phase2b-system-manifest.md` 的 S14 为唯一权威；该处没有再重列可冲突的 Hack/Drain/Overload 顺序表。
- `specs/core/06-phase2b-system-manifest.md:181-194` 在 S14 `special_attack_reducer` 中定义完整 pipeline：parallel collect → merge sort → reducer resolve → deliver to S22，并明确唯一权威优先级链为 `Hack > Drain > Overload > Debilitate > Disrupt > Fortify`。
- `specs/core/06-phase2b-system-manifest.md:216-231` 补充 per-status unique writer contract 与 pending intents 归并结构，避免多个系统重复写同一特殊攻击状态。

架构结论：B3 已闭合。唯一权威链位置直观，读者会被导向 manifest S14，而不是在 command-validation 中维护第二份优先级表。

## Verdict: REJECT

原因：两项均 CLOSED 才能 APPROVE；当前 B3 CLOSED，但 B2 存在 Blocking GAP。建议最小修复为删除或改写 `specs/core/02-command-validation.md:288` 的旧固定 50% Recycle 句子，使 §3.9 直接引用 §3.18 或 API Registry / Resource Ledger 的 lifespan-proportional 10%–50% 公式。
