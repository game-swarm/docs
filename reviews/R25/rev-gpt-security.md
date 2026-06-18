# R25 Closure Verification — Security (GPT-5.5)

## B2: GAP

证据：
- `specs/core/02-command-validation.md:276` 的 Recycle 主规范仍声明 `返还 50% 身体部件成本作为能量给 spawn`（`02-command-validation.md:288`）。
- 同一文件后续 `3.18 Recycle 比例退还与 lifespan 约束` 又声明 `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`（`02-command-validation.md:483`、`02-command-validation.md:487`、`02-command-validation.md:490`），并要求 lifespan 末期仅 10% 退还（`02-command-validation.md:497`-`02-command-validation.md:504`）。
- 同一文件的旧 CommandAction 变体仍保留 `标准退还 | body part spawn 总成本的 50%` 与 Tutorial 100% 退还（`02-command-validation.md:708`、`02-command-validation.md:718`、`02-command-validation.md:719`），与 lifespan 挂钩规则冲突。
- 在本任务允许读取的三个文件中，未看到 B2 指定的 storage tax thresholds（10K→30% capacity）与 gameplay upkeep（-40~-3,150→引用）被收敛为 API/经济单事实源；因此 B2-GAP 未闭合。

## B3: CLOSED

证据：
- `specs/core/06-phase2b-system-manifest.md` 在 S14 `special_attack_reducer` 中给出唯一权威优先级链：`Hack > Drain > Overload > Debilitate > Disrupt > Fortify`，并明确 `02-command-validation.md` 已删除旧优先级表（`06-phase2b-system-manifest.md:181`、`06-phase2b-system-manifest.md:185`-`06-phase2b-system-manifest.md:189`）。
- 同一 manifest 还定义了 Special Attack Unique Writer Contract，声明各 status/component 的唯一 writer 与 S14→S22→S15 的归并/推进/伤害应用边界（`06-phase2b-system-manifest.md:216`-`06-phase2b-system-manifest.md:231`）。
- `specs/core/02-command-validation.md` 的同 tick 多命中优先级章节不再重列可冲突优先级表，而是引用 `06-phase2b-system-manifest.md` 的 S14 作为权威（`02-command-validation.md:431`-`02-command-validation.md:437`）。

## Verdict: REJECT

B3 已关闭；B2 仍存在 Blocking GAP：Recycle 经济规则在同一 API/指令文档内存在 50% 固定退还、Tutorial 100% 退还、lifespan 挂钩退还三套口径，同时 storage tax/upkeep 单事实源无法在允许文件中确认闭合。
