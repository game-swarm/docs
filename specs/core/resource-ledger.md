# Resource Ledger — 统一资源入口（单一经济权威）

> 详见 design/gameplay.md

## 原则

1. **单一入口**：所有资源流动（本地、全局、联盟、PvE 奖励、回收、建造消耗）通过同一个 Resource Ledger API 结算。
2. **确定性账本**：每笔资源变动记录到 TickTrace，具有 `(tick, source, target, resource_type, amount, operation, fee_paid)` 归因。
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
         │ PvE     │    │ Recycle │    │ Build/    │
         │ Award   │    │ Refund  │    │ Spawn     │
         │ (Faucet)│    │ (Sink)  │    │ (Sink)    │
         └─────────┘    └─────────┘    └───────────┘
```

所有操作类型通过 `ResourceOperation` 枚举统一：

| 操作 | 方向 | 说明 |
|------|:---:|------|
| `LocalTransfer` | Source → Target | drone 间本地转移 |
| `GlobalDeposit` | Local → Global | 存入全局仓库 |
| `GlobalWithdraw` | Global → Local | 从全局仓库提取 |
| `AlliedTransfer` | Player A → Player B | 联盟间转移（受限） |
| `PvEAward` | World → Player | NPC 掉落/任务奖励 |
| `RecycleRefund` | Entity → Owner | 回收退还 |
| `BuildCost` | Owner → Structure | 建造消耗 |
| `SpawnCost` | Owner → Drone | 生成消耗 |
| `UpkeepDeduction` | Owner → World | 维护费扣除 |
| `StorageTax` | Storage → World | 存储税 |
| `ContractSettlement` | Contract → Participants | 合约结算（独立 RFC surface） |

---

## 2. 费率模型（定点）— 唯一经济权威

> **B6/D3/D4 裁决**：本文档为 Swarm 经济系统中所有费率、公式、参数的**唯一定义源**。
> `design/economy-balance-sheet.md`、`design/gameplay.md` §8、`design/engine.md` 中所有经济计算必须引用本节参数，不得独立定义公式。

### 2.1 统一参数表（全部使用 basis points，禁止浮点数）

| 参数 | 值 | 单位 | 说明 |
|------|-----|------|------|
| **Global Transfer** | | | |
| `global_deposit_fee` | 100 | bp | 存入全局仓库费率 (1.00%) |
| `global_withdraw_fee` | 500 | bp | 提取费率 (5.00%) |
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
| **New Player Gate** | | | |
| `new_player_transfer_lock` | 500 | tick | 新玩家 player↔player 转移双向锁：禁止发送与接收 |
| `soft_launch_duration` | 1500 | tick | safe_mode 结束后 PvE-only 保护期 |

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

**World 启动经济**：Standard World 的 1-room balance sheet 长期为负——若无初始资源与免维护期，新玩家将在 safe/soft_launch 期间陷入 upkeep deficit 死亡螺旋。

#### 新增配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `starting_resources` | `{Energy: 5000}` | 新玩家初始资源包 —  Vanilla 默认单一 Energy |
| `free_upkeep_controllers` | 1 | 免维护费的 controller 数量 |
| `free_upkeep_drones` | 3 | 免维护费的 drone 数量 |
| `free_upkeep_ticks` | 2000 | 免维护费持续 tick 数（自首次 spawn 起） |

**结算规则**：
- 前 `free_upkeep_controllers` 个 controller 和前 `free_upkeep_drones` 个 drone 在 `free_upkeep_ticks` 内免 `UpkeepDeduction`
- 超过免维护数量的 drone/controller 正常扣费
- 免维护到期后，最后一个免维护 tick 结束时一次性重算剩余容量，无追溯扣费
- 反 smurf 约束：免维护绑定 player identity，同一身份（证书）只享受一次；新身份在 `new_player_transfer_lock` 期内不得向其他玩家发送资源，也不得从其他玩家接收资源

#### Growth Path 示例（Standard World，1 room → RCL3 → 5 rooms）

| Tick 范围 | 阶段 | Faucet | Sink | Break-even? |
|-----------|------|--------|------|-------------|
| 0–500 | Tutorial / Safe mode | starting_resources + Controller income (50/tick) | 0（免维护） | ✅ 净增长 |
| 500–1500 | Soft launch | Controller + Harvester (2×) | 2 drone upkeep | ✅ 轻微盈余 |
| 1500–2000 | RCL 升级 | Controller + Harvester (3×) + PvE | RCL2 升级成本 + 3 drone | ⚠️ 接近平衡 |
| 2000+ | Full economy | 完整 faucet | Empire upkeep | ✅ 自维持 |

**说明**：免维护到期（tick 2000）时，玩家应有 ≥2 rooms + 5 drones + 完整 faucer 管道。实际 break-even tick 取决于玩家 build 效率。

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

`new_player_transfer_lock` canonical 语义：锁定期内禁止任何 player↔player 资源转移的发送与接收，覆盖 `AlliedTransfer`、本地 player transfer 以及 `ContractSettlement` RFC surface。该锁不影响玩家自身账户内的 `GlobalDeposit` / `GlobalWithdraw`（local↔global 转换）、`PvEAward`、`RecycleRefund`、`BuildCost`、`SpawnCost` 或其它非交易式账本操作。

Allied transfer 附加约束：
- 双方必须是同一联盟成员 ≥ 100 tick
- 双方均非 `new_player_transfer_lock` 期内（发送方与接收方都必须已解锁）
- 同目标两次转移间 ≥ `allied_transfer_cooldown`
- 24h 内对同一接收者 ≤ `allied_daily_cap`

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
| T5 | 赛季/竞技 (Arena/Tournament) | 由规则模块定义 | N/A | Out-of-Scope — Arena 使用独立奖励池 |

**映射规则**：
- NPC tier 由 `world.toml` `[[npc_templates]]` 的 `tier` 字段定义
- `PvEAward.amount = base_reward × player_multiplier`，受 Player/Global/Zone/Event 四维上限约束
- 同一 tick 同一 NPC entity 被多个玩家击杀时，按击杀贡献比例分配（先到先得、overkill 不额外产出）

---

## 4. 确定性执行顺序

每 tick 的资源操作按以下顺序执行（在 apply 阶段内）：

```
1. WorldStartupSubsidy   (starting_resources 注入，首次进入时一次性)
2. UpkeepDeduction     (所有 drone/建筑维护费；免维护期内前 N 个 controller/drone 跳过)
3. StorageTax          (仓库存储税)
4. PvEAward            (NPC spawn/drop → 按预算裁决)
5. LocalTransfer       (drone 间转移)
6. GlobalDeposit       (本地→全局)
7. GlobalWithdraw      (全局→本地)
8. AlliedTransfer      (联盟转移 → 按预算裁决)
9. BuildCost           (建造消耗)
10. SpawnCost           (生成消耗)
11. RecycleRefund      (回收退还)
```

同 tick 内同一玩家的多个同类型操作，按 Command sequence 顺序执行。

---

## 5. TickTrace 归因

每笔资源变动记录到 TickTrace：

```json
{
  "tick": 12345,
  "operations": [
    {
      "op": "LocalTransfer",
      "source": "drone:D42",
      "target": "drone:D43",
      "resource": "Energy",
      "amount": 500,
      "fee_paid": 0,
      "basis_points_used": 0
    }
  ],
  "balance_delta": {
    "drone:D42": {"Energy": -500},
    "drone:D43": {"Energy": +500}
  },
  "ledger_checksum": "abc123..."
}
```

---

## 6. ResourceAmount / ResourceRate 定点建模

使用 D1 裁决的定点方案。所有计算公式以 §2 统一参数表为准，此处仅声明类型约束：

```
ResourceAmount: i64            # 资源量，整数
ResourceRate: i64              # 速率 (amount/tick)，整数
FeeBps: u16                    # 费率 (basis points, 0-10000)
TransferDelay: u32             # 延迟 (tick)
```

**公式引用**（权威定义见 §2）：
- Global transfer fee: `amount * global_deposit_fee / 10000`（存入） / `amount * global_withdraw_fee / 10000`（提取）
- Allied transfer fee: `amount * allied_transfer_fee / 10000`
- Storage tax: 连续边际税率公式见 §2.2
- Recycle refund: lifespan 10%-50% 公式见 §2.5

### Empire Upkeep（帝国维护费）

维护费使用 world.toml 中 `[[empire_upkeep_mod]]` 定义的 tiered 公式。默认 Vanilla 规则：

```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
base_upkeep = 50 (Standard) / 30 (Vanilla) / 10 (Tutorial)
room_soft_cap = 10 (Standard) / 15 (Vanilla) / 20 (Tutorial)
```

维护费在 Resource Ledger 执行顺序中位于第 1 步（`UpkeepDeduction`），从玩家全局存储扣除。若全局存储不足，扣至 0 并记录 `UpkeepDeficit` 到 TickTrace。维护费 deficit 累积——连续 3 tick deficit 触发 drone 饥饿惩罚（效率 −50%），连续 10 tick deficit 触发 drone 强制死亡（age 加速 ×10）。

**Recycle 权威公式见 §2.5**。回收退还比例 = `max(recycle_refund_min, remaining_lifespan / total_lifespan × recycle_refund_base)`，全部使用 basis points 定点计算。新手保护（Tutorial 前 500 tick）退还 100%，由 world.toml `tutorial_recycle_refund_full_ticks` 控制。

---

## 7. 独立 RFC Surface

以下入口不属于 active Resource Ledger：

| 入口 | 状态 | 替代方案 |
|------|------|---------|
| Contract Settlement | RFC | Challenge Board 用非资源奖励 |
| Merchant NPC | RFC | — |
| Drone P2P Offer | RFC | Allied Transfer (受限) 部分覆盖 |

---

## 8. 与现有文档的关系

- `design/gameplay.md` §8 (经济系统): 本文档为权威实现合同。
- `specs/gameplay/api-idl.md` §TransferToGlobal/FromGlobal: 使用本文档费率。
- `design/engine.md` §3.4.2 (容量合同): 本文档补充资源维度。
