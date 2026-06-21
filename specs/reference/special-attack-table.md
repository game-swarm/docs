# 8 Special Attack Canonical Table

> **权威源**：本文档是 8 个特殊攻击的唯一 canonical 参数表。所有 design/spec/IDL 文档必须引用此表，不得重新声明可冲突的参数。
> IDL 定义见 [game_api.idl.yaml](game_api.idl.yaml) §1.3 special_attack。校验矩阵见 [02-command-validation.md](../core/02-command-validation.md) §3.10-3.17。IDL indices 14–21 为唯一行集。

## 概述

所有 8 个特殊攻击通过 `CommandAction` 路由至 `CustomActionRegistry`，在引擎中以 `custom_action_def` 注册。每个关联同名 `[[special_effects]]` handler。

Standard/Arena 模式全量启用。Tutorial/Novice 模式默认禁用，服主可通过 `world.toml` 的 `vanilla.special_attacks_enabled` 列表覆盖。TickTrace 记录 `world_action_manifest_hash` 以确保 replay 确定性。

## Canonical Table

| # | Attack | IDL Index | Body Part | Damage Type | Resistance | Cost | Cooldown (ticks) | Range | Channel Time | Counterplay | Validation Schema |
|---|--------|-----------|-----------|-------------|------------|------|------------------|-------|-------------|-------------|-------------------|
| 1 | **Hack** | 14 | `Claim` | Psionic | Target `Psionic` 抗性 | 1000 Energy | 200 (global) | 1 | 5 ticks (持续施法) | ✅ Disrupt 打断 / Fortify 清除 | `02-command-validation.md` §3.10 — 5-stage 控制夺取 |
| 2 | **Drain** | 15 | `Work` + `Carry` | EMP | Target `EMP` 抗性 | 200 Energy/tick | 50 (per drone) | 1 | 持续 (移动/Disrupt 中断) | ✅ Disrupt 打断 / Fortify 清除 | `02-command-validation.md` §3.11 — 从目标建筑/存储窃取资源 |
| 3 | **Overload** | 16 | `RangedAttack` | EMP | Target `EMP` 抗性 | 300 Energy | 200 (per drone) | 5 (LOS required) | 瞬发 | ✅ Disrupt 打断恢复 / Fortify 清除 | `02-command-validation.md` §3.12 — 目标为 PlayerId，燃料预算压制 |
| 4 | **Debilitate** | 17 | `Work` | Corrosive | Target `Corrosive` 抗性 | 200 Energy | 150 (per drone) | 3 | 瞬发 | ❌ 不可反制（Debilitate 非持续性） / ✅ Fortify 清除易伤 | `02-command-validation.md` §3.13 — 目标指定 damage_type 抗性 ×2 |
| 5 | **Disrupt** | 18 | `Attack` | Sonic | Target `Sonic` 抗性 | 100 Energy | 50 (per drone) | 1 | 瞬发 | ❌ 不可反制（打断已发生） | `02-command-validation.md` §3.14 — 打断目标当前持续动作 |
| 6 | **Fortify** | 19 | `Tough` | — | — | 400 Energy | 300 (per drone) | 1 (self/ally) | 瞬发 | ✅ 不可被 Disrupt 打断（瞬发增益） | `02-command-validation.md` §3.15 — 护盾+净化，per-target 300 tick 冷却 |
| 7 | **Leech** | 20 | `Attack` | Corrosive | Target `Kinetic` 抗性 | 300 Energy | 100 (per drone) | 1 | 瞬发 | ❌ 不可反制（瞬发吸血） | `02-command-validation.md` §3.10 派生 — 伤害目标并自愈 50% |
| 8 | **Fabricate** | 21 | `Work` + `Carry` | — | — | 2000 Energy + 500 Matter | 500 (per drone) | 1 | 5 ticks (可被打断) | ❌ 不可反制（构造完成即永久） | `02-command-validation.md` §3.10 派生 — 转换敌方 drone 为己方结构 |

### 字段说明

| 字段 | 说明 |
|------|------|
| `IDL Index` | `game_api.idl.yaml` 中 `command_action.variants[].index`，为跨文档引用权威键 |
| `Body Part` | 执行该特殊攻击所需的 drone body part |
| `Damage Type` | 造成的伤害类型（`—` 表示该攻击不造成伤害） |
| `Resistance` | 目标抗性类型对效果的减免影响 |
| `Cost` | 每次执行的资源消耗 |
| `Cooldown (ticks)` | 冷却时间（tick 数），标注 per-drone 或 global |
| `Range` | 最大作用距离（格数）；LOS = line-of-sight required |
| `Channel Time` | 持续施法时间（tick 数）；瞬发 = 立即生效 |
| `Counterplay` | 反制手段（Disrupt 打断 / Fortify 清除 / 不可反制） |
| `Validation Schema` | 校验规范的引用来源 |

## 引用此表的文档

- **IDL**: [game_api.idl.yaml](game_api.idl.yaml) §1.3 special_attack（8 个 CommandAction 定义，indices 14–21）
- **Registry**: [api-registry.md](api-registry.md) §1.3 特殊攻击（参数与分类）
- **Validation**: [02-command-validation.md](../core/02-command-validation.md) §3.10-3.17（逐攻击校验矩阵）
- **Gameplay**: [design/gameplay.md](../../design/gameplay.md)（Combat 描述引用）
- **World Rules**: [07-world-rules.md](../core/07-world-rules.md)（`world.toml` `special_attacks_enabled` 配置）

## 与 CommandAction 的映射

| Special Attack | IDL Index | IDL Name | 备注 |
|---------------|-----------|----------|------|
| Hack | 14 | `Hack` | 5-stage 控制夺取 |
| Drain | 15 | `Drain` | 持续窃取资源 |
| Overload | 16 | `Overload` | 燃料压制（PlayerId 目标） |
| Debilitate | 17 | `Debilitate` | 易伤附加 |
| Disrupt | 18 | `Disrupt` | 打断攻击 |
| Fortify | 19 | `Fortify` | 护盾+净化 |
| Leech | 20 | `Leech` | 吸血攻击 |
| Fabricate | 21 | `Fabricate` | 构造转换 |

> **注意**：此表以 IDL indices 14–21 为唯一行集，是 8 个 special_attack 的 canonical 权威表。RangedAttack/Heal/Repair/Boost/Jammer/Shield 不属于 special_attack（它们分别是 core action、non-special-attack action 或防御体系的一部分），不列入此表。CI 校验以 IDL `index` 为准。