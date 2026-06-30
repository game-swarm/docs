# Vanilla Action Canonical Table

> **权威源**：本文档是 11 个 vanilla `ActionRegistry` action 的 canonical 参数表。所有 design/spec/IDL 文档必须引用此表，不得重新声明可冲突的参数。
> IDL 定义见 [game_api.idl.yaml](game_api.idl.yaml) §1 `command_action.action_registry`。校验矩阵见 [command-validation.md](../core/command-validation.md) §3。IDL indices 14–24 为唯一 vanilla action 行集。

## 概述

所有战斗/效果动作通过 `CommandAction::Action { type, payload }` 派发至 `ActionRegistry`。Vanilla 注册表包含 11 个内置动作：3 个 `basic_combat`，8 个 `special_attack`。Mod 可通过 world action manifest 注册额外 action，但不能覆盖 vanilla 名称。

Standard/Arena 模式全量启用。Tutorial/Novice 模式可通过 `world.toml` 的 vanilla action allowlist 覆盖。TickTrace 记录 `world_action_manifest_hash` 以确保 replay 确定性。

## Canonical Table

| # | Action | IDL Index | Category | Body Part | Damage Type | Resistance | Cost | Cooldown (ticks) | Range | Channel Time | Counterplay | Validation Schema |
|---|--------|-----------|----------|-----------|-------------|------------|------|------------------|-------|-------------|-------------|-------------------|
| 1 | **Attack** | 14 | `basic_combat` | `Attack` | Kinetic | Target `Kinetic` 抗性 | — | fatigue gate | 1 | 瞬发 | Fortify 抗性减伤 | `command-validation.md` §3 — 近战攻击目标 |
| 2 | **RangedAttack** | 15 | `basic_combat` | `RangedAttack` | Kinetic | Target `Kinetic` 抗性 | — | fatigue gate | 3 | 瞬发 | Fortify 抗性减伤 | `command-validation.md` §3 — 远程攻击目标 |
| 3 | **Heal** | 16 | `basic_combat` | `Heal` | — | — | — | fatigue gate | 3 | 瞬发 | Disrupt 不可打断瞬发治疗 | `command-validation.md` §3 — 治疗或修复目标 |
| 4 | **Hack** | 17 | `special_attack` | `Claim` | Psionic | Target `Psionic` 抗性 | 1000 Energy | 200 (global) | 1 | 5 ticks (持续施法) | ✅ Disrupt 打断 / Fortify 清除 | `command-validation.md` §3 — 5-stage 控制夺取 |
| 5 | **Drain** | 18 | `special_attack` | `Work` + `Carry` | EMP | Target `EMP` 抗性 | 200 Energy/tick | 50 (per drone) | 1 | 持续 (移动/Disrupt 中断) | ✅ Disrupt 打断 / Fortify 清除 | `command-validation.md` §3 — 从目标建筑/存储窃取资源 |
| 6 | **Overload** | 19 | `special_attack` | `RangedAttack` | EMP | Target `EMP` 抗性 | 300 Energy | 200 (per drone) | 5 (LOS required) | 瞬发 | ✅ Disrupt 打断恢复 / Fortify 清除 | `command-validation.md` §3 — 目标为 PlayerId，燃料预算压制 |
| 7 | **Debilitate** | 20 | `special_attack` | `Work` | Corrosive | Target `Corrosive` 抗性 | 200 Energy | 150 (per drone) | 3 | 瞬发 | ❌ 不可反制（Debilitate 非持续性） / ✅ Fortify 清除易伤 | `command-validation.md` §3 — 目标指定 damage_type 抗性 ×2 |
| 8 | **Disrupt** | 21 | `special_attack` | `Attack` | Sonic | Target `Sonic` 抗性 | 100 Energy | 50 (per drone) | 1 | 瞬发 | ❌ 不可反制（打断已发生） | `command-validation.md` §3 — 打断目标当前持续动作 |
| 9 | **Fortify** | 22 | `special_attack` | `Tough` | — | — | 400 Energy | 300 (per drone) | 1 (self/ally) | 瞬发 | ✅ 不可被 Disrupt 打断（瞬发增益） | `command-validation.md` §3 — 护盾+净化，per-target 300 tick 冷却 |
| 10 | **Leech** | 23 | `special_attack` | `Attack` | Kinetic | Target `Kinetic` 抗性 | 300 Energy | 100 (per drone) | 1 | 瞬发 | ❌ 不可反制（瞬发吸血） | `command-validation.md` §3 — 伤害目标并自愈 50% |
| 11 | **Fabricate** | 24 | `special_attack` | `Work` + `Carry` | — | — | 2000 Energy + 500 Matter | 500 (per drone) | 1 | 5 ticks (可被打断) | ✅ Disrupt 打断施法 | `command-validation.md` §3 — 转换敌方 drone 为己方结构 |

### 字段说明

| 字段 | 说明 |
|------|------|
| `IDL Index` | `game_api.idl.yaml` 中 `command_action.action_registry.vanilla_actions[].index`，为跨文档引用权威键 |
| `Category` | `basic_combat` 为基础战斗动作；`special_attack` 为特殊攻击动作 |
| `Body Part` | 执行该 action 所需的 drone body part |
| `Damage Type` | 造成的伤害类型（`—` 表示该 action 不造成伤害） |
| `Resistance` | 目标抗性类型对效果的减免影响 |
| `Cost` | 每次执行的资源消耗（`—` 表示无额外资源消耗） |
| `Cooldown (ticks)` | 冷却时间（tick 数），标注 per-drone、global 或 fatigue gate |
| `Range` | 最大作用距离（格数）；LOS = line-of-sight required |
| `Channel Time` | 持续施法时间（tick 数）；瞬发 = 立即生效 |
| `Counterplay` | 反制手段（Disrupt 打断 / Fortify 清除 / 抗性减伤 / 不可反制） |
| `Validation Schema` | 校验规范的引用来源 |

## 引用此表的文档

- **IDL**: [game_api.idl.yaml](game_api.idl.yaml) §1 `command_action.action_registry`（11 个 vanilla `ActionRegistry` action，indices 14–24）
- **Registry**: [api-registry.md](api-registry.md) §1（Action dispatch 与 vanilla action 分类）
- **Validation**: [command-validation.md](../core/command-validation.md) §3（逐 action 校验矩阵）
- **Gameplay**: [design/gameplay.md](../../design/gameplay.md)（Combat 与 action 描述引用）
- **World Rules**: [world-rules.md](../core/world-rules.md)（`world.toml` action registry 配置）

## 与 ActionRegistry 的映射

| Action | IDL Index | Category | 备注 |
|--------|-----------|----------|------|
| Attack | 14 | `basic_combat` | 近战攻击目标 |
| RangedAttack | 15 | `basic_combat` | 远程攻击目标 |
| Heal | 16 | `basic_combat` | 治疗或修复目标 |
| Hack | 17 | `special_attack` | 5-stage 控制夺取 |
| Drain | 18 | `special_attack` | 持续窃取资源 |
| Overload | 19 | `special_attack` | 燃料压制（PlayerId 目标） |
| Debilitate | 20 | `special_attack` | 易伤/效率压制 |
| Disrupt | 21 | `special_attack` | 打断攻击 |
| Fortify | 22 | `special_attack` | 护盾+净化 |
| Leech | 23 | `special_attack` | 吸血攻击 |
| Fabricate | 24 | `special_attack` | 构造转换 |

> **注意**：此表以 IDL indices 14–24 为唯一 vanilla action 行集。`Attack`、`RangedAttack`、`Heal` 属于 `basic_combat`；其余 8 个属于 `special_attack`。CI 校验以 IDL `index` 与 `category` 为准。
