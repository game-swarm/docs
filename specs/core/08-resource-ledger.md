# Resource Ledger — 统一资源入口

> **R15 B9 修复**。本文档定义 Swarm 引擎中所有资源流动的唯一切入点（Transfer Gateway），消除 local transfer / global transfer / allied transfer / PvE award / Market 等多入口的资源逃逸路径。

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
| `MarketTrade` | Player A ↔ Player B | 市场交易 (Future RFC) |
| `ContractSettlement` | Contract → Participants | 合约结算 (Future RFC) |

---

## 2. 费率模型（定点）

| 费率参数 | 值 | 单位 | 说明 |
|---------|-----|------|------|
| `global_deposit_fee` | 100 | bp | 存入全局仓库费率 (1%) |
| `global_withdraw_fee` | 500 | bp | 提取费率 (5%) |
| `global_transfer_delay` | 100 | tick | 全局提取延迟 |
| `allied_transfer_fee` | 200 | bp | 联盟转移费率 (2%) |
| `allied_transfer_delay` | 200 | tick | 联盟转移延迟 |
| `allied_transfer_cooldown` | 500 | tick | 同目标联盟转移冷却 |
| `allied_daily_cap` | 10,000 | units | 每日联盟转移上限 |
| `storage_tax_rate` | 10 | bp/tick | 仓库存储税 (0.1%/tick) |
| `new_player_transfer_lock` | 500 | tick | 新玩家禁止接收资源 |
| `recycle_refund_base` | 5000 | bp | 基础退还比例 (50%) |
| `recycle_refund_min` | 1000 | bp | 最低退还比例 (10%) |

Allied transfer 附加约束：
- 双方必须是同一联盟成员 ≥ 100 tick
- 双方均非 `new_player_transfer_lock` 期内
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

---

## 4. 确定性执行顺序

每 tick 的资源操作按以下顺序执行（在 apply 阶段内）：

```
1. UpkeepDeduction     (所有 drone/建筑维护费)
2. StorageTax          (仓库存储税)
3. PvEAward            (NPC spawn/drop → 按预算裁决)
4. LocalTransfer       (drone 间转移)
5. GlobalDeposit       (本地→全局)
6. GlobalWithdraw      (全局→本地)
7. AlliedTransfer      (联盟转移 → 按预算裁决)
8. BuildCost           (建造消耗)
9. SpawnCost           (生成消耗)
10. RecycleRefund      (回收退还)
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

使用 D1 裁决的定点方案：

```
ResourceAmount: i64            # 资源量，整数
ResourceRate: i64              # 速率 (amount/tick)，整数
FeeBps: u16                    # 费率 (basis points, 0-10000)
TransferDelay: u32             # 延迟 (tick)
```

所有计算公式：

```
fee = amount * fee_bps / 10000
recycle_refund = body_cost * remaining_lifespan * 5000 / total_lifespan / 10000
recycle_refund = max(body_cost * 1000 / 10000, recycle_refund)  # min 10%
```

### Empire Upkeep（帝国维护费）

维护费使用 world.toml 中 `[[empire_upkeep_mod]]` 定义的 tiered 公式。默认 Vanilla 规则：

```
upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)
base_upkeep = 50 (Standard) / 30 (Vanilla) / 10 (Tutorial)
room_soft_cap = 10 (Standard) / 15 (Vanilla) / 20 (Tutorial)
```

维护费在 Resource Ledger 执行顺序中位于第 1 步（`UpkeepDeduction`），从玩家全局存储扣除。若全局存储不足，扣至 0 并记录 `UpkeepDeficit` 到 TickTrace。维护费 deficit 累积——连续 3 tick deficit 触发 drone 饥饿惩罚（效率 −50%），连续 10 tick deficit 触发 drone 强制死亡（age 加速 ×10）。

**Recycle 权威公式**：Resource Ledger 为回收的单一权威源。回收退还比例 = `max(10%, remaining_lifespan / total_lifespan × 50%)`。即 drone 在寿命 10% 时回收退还 10%，在寿命 100% 时退还 50%。`recycle_refund_base` = 5000 bp (50%)，`recycle_refund_min` = 1000 bp (10%)。新手保护（Tutorial 前 500 tick）退还 100%，由 world.toml `tutorial_recycle_refund_full_ticks` 控制。

---

## 7. Future RFC 入口

以下入口为 Future RFC，**不进入当前 Resource Ledger**：

| 入口 | 状态 | 替代方案 |
|------|------|---------|
| Market Orders | Future RFC | 暂不开放 |
| Contract Settlement | Future RFC | Challenge Board 用非资源奖励 |
| Merchant NPC | Future RFC | — |
| Drone P2P Offer | Future RFC | Allied Transfer (受限) 部分覆盖 |

---

## 8. 与现有文档的关系

- `design/gameplay.md` §8 (经济系统): 本文档为权威实现合同。
- `specs/gameplay/08-api-idl.md` §TransferToGlobal/FromGlobal: 使用本文档费率。
- `design/engine.md` §3.4.2 (容量合同): 本文档补充资源维度。
