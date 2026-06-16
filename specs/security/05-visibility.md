```toml
[visibility]
fog_of_war = true
player_view = "drone"
public_spectate = false
spectate_delay = 50
```

---

## 10. Oracle 防线 —— 跨接口信息泄露闭合

以下规则确保所有管理/调试/查询接口不会绕过 `is_visible_to` 形成 oracle。

### 10.1 MCP 查询面约束

| 条件 | `player_view` | MCP read/query 可见范围 |
|------|:--:|------|
| competitive world (fog_of_war=true) | `drone` | = WASM snapshot（`is_visible_to` 过滤） |
| competitive world | `full` | ❌ 不允许——`validate_config` 拒绝此组合 |
| non-competitive (tutorial/coop/sandbox) | `full` | 全地图（允许——公平竞技不适用） |

**规则**：`fog_of_war=true` 且 `player_view=full` 的组合在 `world.toml` 验证阶段被拒绝启动。MCP agent 在 competitive world 中永远只能看到与 WASM `tick(snapshot)` 相同的可见范围。

### 10.2 `omitted_count` 脱敏

当前设计：`omitted_count` 告知被截断丢弃的实体精确数量——形成 oracle（攻击者可通过观察 `omitted_count` 变化推断被隐藏的实体数量）。

**修正**：`omitted_count` 改为分桶值：

| 实际丢弃数 | 返回的 `omitted_count` |
|:--|:--|
| 0 | `0`（无截断） |
| 1-10 | `"few"` |
| 11-50 | `"some"` |
| 51-200 | `"many"` |
| >200 | `"extreme"` |

`total_visible_count` 同样分桶。`truncated` 布尔值保留——玩家只需知道"是否发生了截断"。

### 10.3 dry_run / simulate / explain_last_tick 脱敏

| 接口 | 脱敏策略 |
|------|---------|
| `swarm_dry_run_commands` | 仅返回 `Ok` / `RejectionReason`（等价脱敏版）——不返回被拒绝指令的具体目标信息 |
| `swarm_simulate` | 模拟结果仅包含自身实体状态变化——不包含其他玩家的实体、资源、指令 |
| `swarm_explain_last_tick` | 仅解释自身 drone 的执行结果——不暴露其他玩家的 action、rejection detail、资源变化 |

### 10.4 特殊攻击拒绝码等价策略

所有特殊攻击（Overload/Hack/Drain/Debilitate/Disrupt/Fortify/Leech/Fabricate）的不可见目标拒绝码统一为以下等价类：

| 实际情况 | 返回码 |
|---------|--------|
| 目标不存在 | `NotVisibleOrNotFound` |
| 目标存在但不可见 | `NotVisibleOrNotFound` |
| 目标不可被该攻击类型指定 | `NotEligible` |
| 目标在冷却中（per-target global cooldown） | `NotEligible` |
| 攻击者自身条件不足（fatigue/cooldown/资源） | 具体的自身状态码（`Fatigued`/`OnCooldown`/`InsufficientEnergy`） |

攻击者**永远无法**通过拒绝码区分"目标不存在"与"目标不可见"——两类都返回 `NotVisibleOrNotFound`。"不满足攻击条件"与"在冷却中"统一返回 `NotEligible`。仅自身状态码暴露自身信息（合法——玩家已知自身状态）。
