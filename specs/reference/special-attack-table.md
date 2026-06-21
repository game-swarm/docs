# 8 Special Attack Canonical Table

> **权威源**：本文档是 8 个特殊攻击的唯一 canonical 参数表。所有 design/spec/IDL 文档必须引用此表，不得重新声明可冲突的参数。
> IDL 定义见 [game_api.idl.yaml](game_api.idl.yaml) §1.3 special_attack。校验矩阵见 [02-command-validation.md](../core/02-command-validation.md) §3.10-3.17。

## 概述

所有 8 个特殊攻击通过 `CommandAction` 路由至 `CustomActionRegistry`，在引擎中以 `custom_action_def` 注册。每个关联同名 `[[special_effects]]` handler。

Standard/Arena 模式全量启用。Tutorial/Novice 模式默认禁用，服主可通过 `world.toml` 的 `vanilla.special_attacks_enabled` 列表覆盖。TickTrace 记录 `world_action_manifest_hash` 以确保 replay 确定性。

## Canonical Table

| # | Attack | Body Part | Damage Type | Resistance | Cost (Energy) | Cooldown (ticks) | Range | Channel Time | Counterplay | Validation Schema |
|---|--------|-----------|-------------|------------|---------------|------------------|-------|-------------|-------------|-------------------|
| 1 | **Leech** | `Attack` | Kinetic | Target `Kinetic` 抗性 | 150 | 100 (per drone) | 1 | 瞬发 (0 ticks) | ❌ 不可反制（瞬发吸血） | `02-command-validation.md` §3.10 派生 — 伤害目标并自愈 50% |
| 2 | **Fabricate** | `Work` + `Carry` | — | — | 500 | 300 (per drone) | 1 | 5 ticks (可被打断) | ❌ 不可反制（构造完成即永久） | `02-command-validation.md` §3.10 派生 — 转换敌方 drone 为己方结构 |
| 3 | **Overload** | `RangedAttack` | EMP | 目标 `EMP` 抗性 | 300 | 200 (per drone) | 5 (LOS required) | 瞬发 | ✅ Disrupt 打断恢复 / Fortify 清除 | `02-command-validation.md` §3.12 — 目标为 PlayerId，燃料预算压制 |
| 4 | **RangedAttack** | `RangedAttack` | Kinetic | 目标 `Kinetic` 抗性 | 100 | 10 (per drone) | 3 | 瞬发 | —（基础远程攻击） | `02-command-validation.md` §3.6 — 远程攻击目标实体 |
| 5 | **Boost** | `Work` | — | — | 200 | 150 (per drone) | 1 | 瞬发 | ❌ 不可反制（Buff 已施加） | 提升己方 drone 效率/速度 50%，持续 100 ticks |
| 6 | **Jammer** | `Attack` | Sonic | 目标 `Sonic` 抗性 | 100 | 50 (per drone) | 1 | 瞬发 | ❌ 不可反制 | 打断目标当前持续动作（Drain/Hack/Fabricate channel 等） |
| 7 | **Shield** | `Tough` | — | — | 400 | 300 (per drone) | 1 (self/ally) | 瞬发 | ✅ 不可被 Disrupt 打断（瞬发增益） | `02-command-validation.md` §3.15 派生 — 护盾+净化，per-target 300 tick 冷却 |
| 8 | **Repair** | `Heal` | — | — | 200 | 50 (per drone) | 3 | 瞬发 | ❌ 不可反制 | 恢复目标 HP（drone 或 structure），不可降低 age |

### 字段说明

| 字段 | 说明 |
|------|------|
| `Body Part` | 执行该特殊攻击所需的 drone body part |
| `Damage Type` | 造成的伤害类型（`—` 表示该攻击不造成伤害） |
| `Resistance` | 目标抗性类型对效果的减免影响 |
| `Cost (Energy)` | 每次执行的 Energy 消耗 |
| `Cooldown (ticks)` | 每 drone 的执行冷却（tick 数） |
| `Range` | 最大作用距离（格数）；LOS = line-of-sight required |
| `Channel Time` | 持续施法时间（tick 数）；瞬发 = 立即生效 |
| `Counterplay` | 反制手段（Disrupt 打断 / Fortify 清除 / 不可反制） |
| `Validation Schema` | 校验规范的引用来源 |

## 引用此表的文档

- **IDL**: [game_api.idl.yaml](game_api.idl.yaml) §1.3 special_attack（8 个 CommandAction 定义）
- **Registry**: [api-registry.md](api-registry.md) §1.3 特殊攻击（参数与分类）
- **Validation**: [02-command-validation.md](../core/02-command-validation.md) §3.10-3.17（逐攻击校验矩阵）
- **Gameplay**: [design/gameplay.md](../../design/gameplay.md)（Combat 描述引用）
- **World Rules**: [07-world-rules.md](../core/07-world-rules.md)（`world.toml` `special_attacks_enabled` 配置）

## 与 CommandAction 的映射

| Special Attack | CommandAction Index | IDL Name | 备注 |
|---------------|---------------------|----------|------|
| Leech | 20 | `Leech` | 吸血攻击 |
| Fabricate | 21 | `Fabricate` | 构造转换 |
| Overload | 16 | `Overload` | 燃料压制（PlayerId 目标） |
| RangedAttack | 7 | `RangedAttack` | 核心远程攻击（同时属于 core 和 special_attack） |
| Boost | — | `Debilitate` 的反向 | 效率增益（当前 IDL 以 Debilitate 反向语义覆盖） |
| Jammer | 18 | `Disrupt` | 打断攻击 |
| Shield | 19 | `Fortify` | 护盾+净化 |
| Repair | 8 | `Heal` | 维修（同时属于 core 和 special_attack） |

> **注意**：部分特殊攻击名与当前 IDL 中 `command_action` 的 `name` 字段不同。此表为 canonical 语义名称，IDL 名称历史保留。新代码/文档应优先使用此表名称。CI 校验以 IDL `index` 为准，名称映射由 codegen 处理。