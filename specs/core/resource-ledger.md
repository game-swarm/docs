# Resource Ledger — 统一资源入口（单一经济权威）

> 详见 design/gameplay.md

## 原则

1. **单一入口**：所有资源流动（本地、全局、联盟、PvE 奖励、回收、建造消耗）通过同一个 Resource Ledger API 结算。
2. **确定性账本**：每笔资源变动记录到 TickTrace，具有 `(tick, source_account, target_account, resource_type, amount_requested, amount_delivered, fee_paid, operation)` 归因。
3. **定点费率**：所有百分比和费率使用 basis points (1 bp = 0.01%) 或 ppm (1 ppm = 0.0001%)，禁止浮点数。
4. **可审计**：每 tick 产出 ResourceBalance 摘要，验证 `Σ inflows - Σ outflows = Δ storage`。

---

## 1. Transfer Gateway 架构

```
                   ┌──────────────────────────────┐
                   │     Resource Ledger           │
                   │  (唯一权威资源账本)             │
                   └──────────┬───────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌─────▼─────┐
   │ Local   │          │ Global  │          │ Allied    │
   │ Transfer│          │ Transfer│          │ Transfer  │
   │ (即时)  │          │ (延迟)  │          │ (受限)    │
   └─────────┘          └─────────┘          └───────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         ┌────▼────┐    ┌────▼────┐    ┌─────▼─────┐
         │ Faucet  │    │ Recycle │    │ Build/    │
         │ Award   │    │ Refund  │    │ Spawn     │
         │ (Faucet)│    │ (Sink)  │    │ (Sink)    │
         └─────────┘    └─────────┘    └───────────┘
```

核心操作与 extension-gated settlement variants 通过 `ResourceOperation` envelope 统一。Extension-gated variants 默认 inactive；只有 owning Plugin 提供预算、费率、TickTrace、授权与反滥用规则后才可进入 active Resource Ledger：

| 操作 | 方向 | 说明 |
|------|:---:|------|
| `LocalTransfer` | Source → Target | drone 间本地转移 |
| `GlobalDeposit` | Local → Global (+ optional Sink) | 存入全局仓库；Mode B 产生 1% burn sink leg |
| `GlobalWithdraw` | Global → Local (+ optional Sink) | 从全局仓库提取；Mode B 产生 1% burn sink leg |
| `AlliedTransfer` | Player A → Player B | 联盟间转移（受限） |
| `PvEAward` | World → Player | NPC 掉落/任务奖励 |
| `ControllerPassiveIncome` | World → Player | Controller 被动基础收入 |
| `WreckageSalvage` | World → Player | 被摧毁 drone 残骸回收，受 faucet 预算限制 |
| `RecycleRefund` | Entity → Owner | 回收退还 |
| `BuildCost` | Owner → Structure (+ optional Sink) | 建造消耗；Mode B 额外 5% sink leg |
| `SpawnCost` | Owner → Drone | 生成消耗 |
| `UpkeepDeduction` | Owner → World | 维护费扣除 |
| `StorageTax` | Storage → World | 存储税 |
| `WorldStartupSubsidy` | World → New Player | 首次 world/player entry 的一次性初始资源注入；不进入 recurring S29 顺序 |
| `CodeUpdateCost` | Player → World | accepted new deploy 的 typed fee；与 manifest/cooldown/refund reset 原子提交，AlreadyDeployed 不收取 |
| `PluginSettlement::{plugin_id}:{settlement_kind}` | Plugin-defined accounts | Extension-gated；默认 inactive；所有市场/合约/托管/报价等结算必须使用 namespaced PluginSettlement envelope |

---

## 2. 费率模型（定点）— 派生实现合同

> 本节从 `design/economy-balance-sheet.md` 与 `design/gameplay.md` 的目标行为派生，将其展开为定点参数和可执行公式。Design 是语义与默认值的上游；本合同不得反向覆盖 design。

### 2.1 统一参数表（全部使用 basis points，禁止浮点数）

| 参数 | 值 | 单位 | 说明 |
|------|-----|------|------|
| **Global Transfer** | | | |
| `global_deposit_fee` | 100 | bp | 存入全局仓库费率 (1.00%) |
| `global_withdraw_fee` | 100 | bp | 提取费率 (1.00%) |
| `global_deposit_delay` | 10 | tick | 全局存入延迟（资源锁定，不可立即使用） |
| `global_withdraw_delay` | 100 | tick | 全局提取延迟 |
| **Allied Transfer** | | | |
| `allied_transfer_fee` | 200 | bp | 联盟转移费率 (2.00%) |
| `allied_transfer_delay` | 200 | tick | 联盟转移延迟 |
| `allied_transfer_cooldown` | 500 | tick | 同目标联盟转移冷却 |
| `allied_daily_cap` | `max(10_000, receiver_gcl × 20_000)` | units | 每日联盟转移上限（按接收方 GCL 缩放，最低 10,000） |
| `allied_daily_cap_world_multiplier` | 100 | u32 (scale×100) | 世界模式乘数（Standard=100=1.0×, Arena=50=0.5×, Tutorial=500=5.0×） |
| **Storage Tax (连续边际曲线)** | | | |
| `storage_tax_anchor_0` | `(300000 ppm, 0 bp)` | utilization, bp | 30% 容量处边际税率 |
| `storage_tax_anchor_1` | `(600000 ppm, 1 bp)` | utilization, bp | 60% 容量处边际税率 |
| `storage_tax_anchor_2` | `(850000 ppm, 5 bp)` | utilization, bp | 85% 容量处边际税率 |
| `storage_tax_anchor_3` | `(1000000 ppm, 20 bp)` | utilization, bp | 100% 容量处边际税率 |
| `storage_tax_curve` | `quadratic_smoothstep` | enum | 分段三次 Hermite smoothstep 插值，端点连续 |
| **Recycle** | | | |
| `recycle_refund_base` | 5000 | bp | 基础退还比例 (50%) |
| `recycle_refund_min` | 1000 | bp | 最低退还比例 (10%) |
| **Drone Lifespan** | | | |
| `MIN_LIFESPAN` | 100 | tick | body part modifier 后的最小寿命 |
| `BASE_AGE` | 1500 | tick | drone 基础寿命 |
| `drone_decay_rate` | 10000 | bp | 每 tick 基础 age 增长倍率 |
| **Vanilla Resource Set** | | | |
| `vanilla_resource_set` | `[Energy]` | enum list | Vanilla/Standard 默认资源集合只有 Energy；multi-resource worlds 属于 advanced/modded world |
| **Controller Passive Income** | | | |
| `controller_passive_income_base` | 40 | Energy/tick/controller | Controller 被动收入基础值，使 1-3 房基础代码保持正流 |
| `controller_passive_income_rcl_bonus` | 5 | Energy/tick/RCL | 每个 Controller 按 RCL 增加被动收入 |
| **Wreckage Salvage** | | | |
| `wreckage_salvage_min` | 500 | bp | 残骸最低回收比例 (5%) |
| `wreckage_salvage_max` | 1500 | bp | 残骸最高回收比例 (15%)，严格低于 Recycle |
| `wreckage_decay_ticks` | 100 | tick | 残骸线性衰减窗口，超时消失 |
| `wreckage_world_budget_share` | 1000 | bp | Wreckage faucet 占世界资源预算上限 (10%) |
| **New Player Gate** | | | |
| `soft_launch_duration` | 1500 | tick | safe_mode 结束后 PvE-only 保护期；PvP 开启时间由 `pvp_unlock_tick` 独立配置 |
| `pvp_unlock_tick` | 2000 | tick | PvP 规则开启 tick；不与 `free_upkeep_ticks` 绑定 |
| **Mode B Economy Overrides** | | | |
| `mode_b_global_deposit_burn` | 100 | bp | Mode B `GlobalDeposit` 额外/替代 burn sink leg (1.00%) |
| `mode_b_global_withdraw_burn` | 100 | bp | Mode B `GlobalWithdraw` 额外/替代 burn sink leg (1.00%) |
| `mode_b_build_cost_extra_burn` | 500 | bp | Mode B `BuildCost` 额外 sink leg (5.00%) |

### 2.2 存储税连续边际税率公式

```
u_ppm = floor(stored_units × 1_000_000 / storage_capacity_units)
marginal_rate_bp(u_ppm) =
    smoothstep_interpolate([
      (300_000, 0),
      (600_000, 1),
      (850_000, 5),
      (1_000_000, 20)
    ])
storage_tax(tick) = floor( ∫[0, stored_units] marginal_rate_bp(x / storage_capacity_units) dx / 10_000 )
```

`smoothstep_interpolate` 对相邻锚点使用 `s(t)=3t²-2t³`，并用整数 ppm 计算 `t_ppm`。低于 30% 容量时边际税率为 0；高于 100% 的写入由容量规则拒绝。积分通过固定 1,000 ppm 步长的左闭右开整数求和近似执行，所有中间值使用 `u128`，提交时 floor 到整数资源单位。该曲线保留 30/60/85/100% 的可解释锚点，同时消除阶梯边界跳变。

**示例**（容量 1,000,000，存储量 750,000 = 75%）：积分覆盖 30%–60% 与 60%–75% 两段，按 smoothstep 曲线求和后约为 45/tick；具体值由固定步长整数积分产生，replay 必须逐 tick 一致。

### 2.3 Starting Resources & Free Upkeep Waiver

> **裁决**：第一个 controller 和前 N 个 drone 免维护费（数量可配置）。

**World 启动经济**：Standard World 的 1-3 room baseline 在基础代码下保持正流。初始资源与免维护期提供操作缓冲，但经济可持续性来自 Controller passive income、Source 采集与低常数维护费，而不是依赖保护期遮蔽赤字。

#### 新增配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `starting_resources` | `{Energy: 5000}` | 新玩家初始资源包 — Vanilla 默认单一 Energy |
| `free_upkeep_controllers` | 1 | 免维护费的 controller 数量 |
| `free_upkeep_drones` | 3 | 免维护费的 drone 数量 |
| `free_upkeep_ticks` | 2000 | 免维护费持续 tick 数（自首次 spawn 起）；不决定 PvP 开启时间 |

**结算规则**：
- `WorldStartupSubsidy` 是玩家首次进入时的一次性入口注入，发生在 recurring per-tick ledger 之外；它仍写入 TickTrace/audit，但不属于 §4 每 tick 执行序列。
- 前 `free_upkeep_controllers` 个 controller 和前 `free_upkeep_drones` 个 drone 在 `free_upkeep_ticks` 内免 `UpkeepDeduction`
- 超过免维护数量的 drone/controller 正常扣费
- 免维护到期后，最后一个免维护 tick 结束时一次性重算剩余容量，无追溯扣费
- 反滥用约束：免维护绑定 player identity，同一身份（证书）只享受一次；玩家间转账使用统一转账规则、anti-snowball 数学限制、per-player/per-alliance rate limit 与审计，不设置新手双向转账锁

#### Growth Path 示例（Standard World，1 room → RCL3 → 5 rooms）

| Tick 范围 | 阶段 | Faucet | Sink | Break-even? |
|-----------|------|--------|------|-------------|
| 0–500 | Tutorial / Safe mode | starting_resources + Controller income (50/tick) | 0（免维护） | ✅ 净增长 |
| 500–1500 | Soft launch | Controller passive income + Harvester (2×) | 2 drone upkeep | ✅ 盈余 |
| 1500–2000 | RCL 升级 | Controller passive income + Harvester (3×) + PvE | RCL2 升级成本 + 3 drone | ✅ 正流 |
| 2000+ | Full economy | 完整 faucet | Empire upkeep | ✅ 自维持 |

**说明**：免维护到期与 PvP 开启互不绑定。玩家在 1-3 rooms 的基础代码路径保持正流；实际扩张速度取决于 build 效率。

### 2.4 Controller / Depot Age Repair

Age repair 不作为 Resource Ledger 收支公式结算：Controller repair 免费，只受物理约束限制；Depot repair 消耗 Depot 本地存储资源，作为本地结构维护/功能消耗记录。

Controller repair 约束：
- `repair_range` 由 RCL 决定（RCL1=1 格，RCL8=5 格）
- `repair_capacity` 为每 Controller 每 tick 可服务的 drone 数上限
- drone 必须位于 repair range 内；超出容量的 drone 按确定性队列顺序等待

Depot repair 约束：
- Forward Depot 固定 `repair_range=1`
- `repair_capacity` 与 `repair_aging` 由结构类型定义
- 每 tick repair 前从 Depot 本地存储扣除 `maintenance`；资源不足则本 tick 停止 repair

全局 `repair_cap`、`repair_cost`、`distance_decay_bp` 不属于基础经济账本权威公式；若世界或模组需要比例收费 repair，可作为自定义规则在 `WorldRule`/mod 层定义，并不得覆盖本文的 Vanilla 默认语义。

### 2.5 Recycle 权威公式

```
recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000
recycle_refund = max(body_cost × recycle_refund_min / 10000, recycle_refund)
```

即 drone 在寿命 10% 时回收退还 10%，在寿命 100% 时退还 50%。`recycle_refund_base` = 5000 bp (50%)，`recycle_refund_min` = 1000 bp (10%)。新手保护（Tutorial 前 500 tick）退还 100%，由 world.toml `tutorial_recycle_refund_full_ticks` 控制。

Allied transfer 附加约束：
- 双方必须是同一联盟成员 ≥ 100 tick
- 同目标两次转移间 ≥ `allied_transfer_cooldown`
- 24h 内对同一接收者 ≤ `allied_daily_cap`
- Transfer 受统一 rate limit、allied cap、intercept/audit 规则约束；没有新手专用的发送/接收锁

---

## 3. PvE Budget 账本

PvE 资源产出通过 4 维账本控制，防止 faucet 无限放大：

| 维度 | 上限 | 重置周期 |
|------|------|---------|
| Global | ≤ 世界再生总量 × 30% | per tick |
| Zone | ≤ 区域基础再生 × 50% | per tick |
| Player | ≤ player_controller_level × 1000 | per tick |
| Event | ≤ event_budget_pool | per event |

当任一维度超限：
- 超出部分不产出，记录 `PvEBudgetExhausted` 到 TickTrace
- 不影响其他维度/玩家的产出

### 3.1 NPC/Entity Tier → PvEAward Budget 映射

PvE 奖励根据 NPC/entity tier 映射到玩家预算，防止无上限 faucet：

| Tier | Entity 示例 | 基础奖励 (Energy/Unit) | 玩家倍数 | 说明 |
|------|------------|----------------------|---------|------|
| T0 | 环境 Source、被动再生 | 0（环境物） | N/A | 环境再生不计入玩家 PvE budget |
| T1 | 低级 NPC (Scout Drone) | 100–500 | ×1.0 | 新手友好，低奖励 |
| T2 | 中级 NPC (Guard Drone) | 500–2000 | ×1.0 | 标准 PvE 目标 |
| T3 | 高级 NPC (Boss Drone) | 2000–10000 | ×1.0 | 高风险高回报 |
| T4 | 世界事件 (Periodic Event) | 5000–50000 | ×0.5 | 事件奖励打折，防事件滥用 |
| T5 | 赛季/竞技 (Arena/Tournament) | 由规则模块定义 | N/A | Extension — Arena 使用独立奖励池 |

**映射规则**：
- NPC tier 由 `world.toml` `[[npc_templates]]` 的 `tier` 字段定义
- `PvEAward.amount = base_reward × player_multiplier`，受 Player/Global/Zone/Event 四维上限约束
- 同一 tick 同一 NPC entity 被多个玩家击杀时，按击杀贡献比例分配（先到先得、overkill 不额外产出）

---

## 4. 确定性执行顺序

命令触发操作在 Stage 2a 按 canonical RawCommand tuple inline 结算：`LocalTransfer/GlobalDeposit/GlobalWithdraw/AlliedTransfer/BuildCost/SpawnCost/RecycleRefund`。`CodeUpdateCost` 在 deploy control-plane redb transaction 结算；`WorldStartupSubsidy` 在首次 entry 结算。两者不进入 S29。

S29 recurring settlement 使用以下固定顺序：

```
1. UpkeepDeduction
2. StorageTax
3. PvEAward
4. ControllerPassiveIncome
5. WreckageSalvage
6. PluginSettlement（只处理 active extension records，按 `(plugin_id, settlement_kind, operation_id)` 排序）
```

同一 recurring 类型内按 `(player_id, operation_id)` 字节序升序。

---

## 5. TickTrace 归因

每笔资源变动记录到 TickTrace。`ops`、`balance_delta`、`account_delta` 为当前 tick 视图，`cumulative_account_delta` 与 `ledger_checksum` 跨 tick 保留。S29 `resource_ledger_system` 在 tick 末 finalizes 当前 tick，写入 `ResourceLedgerTraceSnapshot`，然后清空当前 tick ops/delta；checksum 与累计账户 delta 不清空。

```json
{
  "tick": 12345,
  "operations": [
    {
      "op": "LocalTransfer",
      "source_account": "player:42",
      "target_account": "player:43",
      "resource": "Energy",
      "amount_requested": 500,
      "amount_delivered": 500,
      "fee_paid": 0,
      "basis_points_used": 0
    }
  ],
  "balance_delta": {
    "drone:D42": {"Energy": -500},
    "drone:D43": {"Energy": +500}
  },
  "account_delta": {
    "player:42": {"Energy": -500},
    "player:43": {"Energy": 500}
  },
  "conservation_imbalance": {},
  "ledger_checksum": "blake3-u64 rolling integer"
}
```

`conservation_imbalance` MUST be empty for every accepted tick trace. Fees and burns are explicit sink account legs; faucets and system awards are explicit system account legs, so conservation is checked over ledger accounts rather than inferred from player balances alone. The world `state_checksum` includes the serialized `ResourceLedger`; replay rejects both state mismatches and standalone `resource_ledger` tampering.

---

## 6. ResourceAmount / ResourceRate 定点建模

使用 D1 裁决的定点方案。所有计算公式以 §2 统一参数表为准，此处仅声明类型约束：

```
ResourceAmount: u32            # 非负资源余额/command amount；扣减前校验，禁止下溢
ResourceDelta: i64             # ledger account leg 的有符号变化
ResourceRate: i64              # 速率 (amount/tick)，可正可负
FeeBps: u16                    # 费率 (basis points, 0-10000)
TransferDelay: u32             # 延迟 (tick)
```

**公式引用**（从 design 下沉，§2 展开整数公式）：
- Global transfer fee: `amount * global_deposit_fee / 10000`（存入） / `amount * global_withdraw_fee / 10000`（提取）
- Allied transfer fee: `amount * allied_transfer_fee / 10000`
- Storage tax: 连续边际税率公式见 §2.2
- Recycle refund: lifespan 10%-50% 公式见 §2.5

### Empire Upkeep（帝国维护费）

维护费使用 `world.toml [mods.empire-upkeep]` 的 typed 参数。默认 Vanilla 规则：

```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
base_upkeep = 50 (Standard) / 30 (Vanilla) / 10 (Tutorial)
room_soft_cap = 10 (Standard) / 15 (Vanilla) / 20 (Tutorial)
```

维护费在 Resource Ledger 执行顺序中位于第 1 步（`UpkeepDeduction`），从玩家全局存储扣除。若全局存储不足，扣至 0 并记录 `UpkeepDeficit` 到 TickTrace。维护费 deficit 累积——连续 3 tick deficit 触发 drone 饥饿惩罚（效率 −50%），连续 10 tick deficit 触发 drone 强制死亡（age 加速 ×10）。

**Recycle 权威公式见 §2.5**。回收退还比例 = `max(recycle_refund_min, remaining_lifespan / total_lifespan × recycle_refund_base)`，全部使用 basis points 定点计算。新手保护（Tutorial 前 500 tick）退还 100%，由 world.toml `tutorial_recycle_refund_full_ticks` 控制。

---

## 7. Plugin Settlement Workflows

本节 workflows 均为 extension-gated/inactive，不能由核心系统直接执行。Owning Plugin 必须先提供预算、费率、TickTrace、授权与反滥用规则，并通过统一 `PluginSettlement::{plugin_id}:{settlement_kind}` Resource Ledger envelope 结算，禁止旁路余额写入。

All settlement IDs are domain-separated BLAKE3-derived IDs under the owning plugin namespace. ID `0` is invalid. A settlement command must authorize the actor before checking duplicate terminal receipts; duplicate receipts are idempotent only for an actor that is still authorized for that settlement phase.

| Workflow | Reserve leg | Settlement legs | Idempotency / auth rule |
|----------|-------------|-----------------|--------------------------|
| `PluginSettlement::{plugin_id}:{settlement_kind}` | `player:{actor} → reserve:{plugin_id}:{settlement_id}:{leg}` or plugin-defined system account, if the plugin schema allows it | Plugin-defined account movements, each emitted as explicit source/target/sink/system legs with no hidden mint/burn | Plugin validates namespace, actor authorization, phase, duplicate terminal receipt idempotency, budgets, fees, expiry and anti-abuse rules before Resource Ledger accepts the operation |

---

## 8. 与现有文档的关系

- `design/gameplay.md` §2.2 (资源与经济): design 定义目标行为；本文档下沉为实现分类账合同。
- `specs/gameplay/api-idl.md` §global_storage_commands: 使用本文档费率。
- `design/engine.md` §3.4.2 (容量合同): 本文档补充资源维度。
