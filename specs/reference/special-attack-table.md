# Vanilla Action Derived Contract Table

> 本表从 `design/gameplay.md` 的 Vanilla action profile 派生 11 个 `ActionRegistry` action 的实现参数。Design 是上游；本表、IDL 与其他 specs 必须同步，但不得要求 design 反向引用本表。
> IDL 定义见 [game_api.idl.yaml](game_api.idl.yaml) §1 `command_action.action_registry`。校验矩阵见 [command-validation.md](../core/command-validation.md) §3。IDL indices 14–24 为唯一 vanilla action 行集。

## 概述

所有战斗/效果动作通过内部 `CommandAction::Action { action_type, payload }` 派发至 `ActionRegistry`；wire `type` 为具体 action 名称。Vanilla 注册表包含 11 个内置动作：3 个 `basic_combat`，8 个 `special_attack`。Mod 可通过 world action manifest 注册额外 action，但不能覆盖 vanilla 名称。

`SpecialAttacksModPlugin` 的启用、版本、来源、hash 与签名由 `mods.lock` 控制；严格 typed gameplay 参数来自 `world.toml [mods.special-attacks]`，缺省字段使用 versioned design-profile 默认值。Tutorial 和 Novice profile 使用对应 allowlist；World/Arena profile 默认使用完整 8 项 special action 集。TickTrace 记录 resolved config 与 action manifest hash，确保 replay 使用同一注册表。

## Canonical Table

| # | Action | IDL Index | Category | Body Part | Damage Type | Resistance | Cost | Cooldown (ticks) | Range | Channel Time | Counterplay | Validation Schema |
|---|--------|-----------|----------|-----------|-------------|------------|------|------------------|-------|-------------|-------------|-------------------|
| 1 | **Attack** | 14 | `basic_combat` | `Attack` | Kinetic | Target `Kinetic` 抗性 | — | fatigue gate | 1 | 瞬发 | Fortify 抗性减伤 | `command-validation.md` §3 — 近战攻击目标 |
| 2 | **RangedAttack** | 15 | `basic_combat` | `RangedAttack` | Kinetic | Target `Kinetic` 抗性 | — | fatigue gate | 3 | 瞬发 | Fortify 抗性减伤 | `command-validation.md` §3 — 远程攻击目标 |
| 3 | **Heal** | 16 | `basic_combat` | `Heal` | — | — | — | fatigue gate | 1 | 瞬发 | Disrupt 不可打断瞬发治疗 | `command-validation.md` §3 — 治疗或修复目标 |
| 4 | **Hack** | 17 | `special_attack` | `Claim` | Psionic | Target `Psionic` 抗性 | 1000 Energy | 200 (player-global actor-side) | 1 | 5 ticks (持续施法) | ✅ Disrupt 打断 / Fortify 清除 | `command-validation.md` §3 — 5-stage 控制夺取 |
| 5 | **Drain** | 18 | `special_attack` | `Work` + `Carry` | EMP | Target `EMP` 抗性 | 200 Energy/tick | 50 (per drone) | 1 | 持续 (移动/Disrupt 中断) | ✅ Disrupt 打断 / Fortify 清除 | `command-validation.md` §3 — 从目标建筑/存储窃取资源 |
| 6 | **Overload** | 19 | `special_attack` | `RangedAttack` | EMP | Target `EMP` 抗性 | 300 Energy | 200 (source-drone) + 50 (target-player-global) | 5 (LOS required) | 瞬发 | ✅ Disrupt 打断恢复 / Fortify 清除 | `command-validation.md` §3 — 目标为 PlayerId，燃料预算压制 |
| 7 | **Debilitate** | 20 | `special_attack` | `Work` | Corrosive | Target `Corrosive` 抗性 | 200 Energy | 150 (per drone) | 3 | 瞬发 | ❌ 不可反制（Debilitate 非持续性） / ✅ Fortify 清除易伤 | `command-validation.md` §3 — 目标指定 damage_type 抗性 ×2 |
| 8 | **Disrupt** | 21 | `special_attack` | `Attack` | Sonic | Target `Sonic` 抗性 | 100 Energy | 50 (per drone) | 1 | 瞬发 | ❌ 不可反制（打断已发生） | `command-validation.md` §3 — 打断目标当前持续动作 |
| 9 | **Fortify** | 22 | `special_attack` | `Tough` | — | — | 400 Energy | 300 (source-drone + target-recipient) | 1 (self/ally) | 瞬发 | ✅ 不可被 Disrupt 打断（瞬发增益） | `command-validation.md` §3 — 护盾+净化，per-target 300 tick 冷却 |
| 10 | **Leech** | 23 | `special_attack` | `Attack` | Kinetic | Target `Kinetic` 抗性 | 300 Energy | 100 (per drone) | 1 | 瞬发 | ❌ 不可反制（瞬发吸血） | `command-validation.md` §3 — 伤害目标并自愈 50% |
| 11 | **Fabricate** | 24 | `special_attack` | `Work` + `Carry` | — | — | 5000 Energy | 500 (per drone) | 1 | 5 ticks (可被打断) | ✅ Disrupt 打断施法 | `command-validation.md` §3 — `target_id` only; output type resolved from typed config ordered allowlist Tower/Storage/Wall, canonical default Tower |

### 字段说明

| 字段 | 说明 |
|------|------|
| `IDL Index` | `game_api.idl.yaml` 中 `command_action.action_registry.vanilla_actions[].index`，为稳定的下游 wire reference key |
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
| Debilitate | 20 | `special_attack` | 指定 damage type 抗性 ×2，持续 50 tick |
| Disrupt | 21 | `special_attack` | 打断攻击 |
| Fortify | 22 | `special_attack` | 护盾+净化 |
| Leech | 23 | `special_attack` | 吸血攻击 |
| Fabricate | 24 | `special_attack` | 构造转换 |

> **注意**：此表以 IDL indices 14–24 为唯一 vanilla action 行集。`Attack`、`RangedAttack`、`Heal` 属于 `basic_combat`；其余 8 个属于 `special_attack`。当前轻量 checker 校验三种基础 action 的 range；`index` 与 `category` 仍需在变更评审中对照 IDL。
