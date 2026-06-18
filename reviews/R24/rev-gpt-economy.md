# R24 Closure Verification — 经济评审 (GPT-5.5)

Verdict: REQUEST_MAJOR_CHANGES

## Scope

本轮仅验证 R23 共识 Blocker / D-items 中经济方向范围：
- B1：经济启动 + D1/A starting_resources + free_upkeep + D4/A repair cap
- B2：经济参数一致性

未进行开放式新问题发现；以下 GAP 均限定在 B2「经济参数一致性」验证范围内。

## Verification Results

### [B1] CLOSED

已正确闭合经济启动、初始资源、免维护与 Controller repair cap。

证据：
- `specs/core/08-resource-ledger.md` §2.3 Starting Resources & Free Upkeep Waiver：
  - `starting_resources = {Energy: 5000, Minerals: 2000}`
  - `free_upkeep_controllers = 1`
  - `free_upkeep_drones = 3`
  - `free_upkeep_ticks = 2000`
  - 明确结算规则：前 N 个 controller/drone 在免维护期内跳过 `UpkeepDeduction`，到期后不追溯扣费。
- `specs/core/08-resource-ledger.md` §2.4 Controller Repair 权威公式：
  - `repair_cost = body_cost × (1 - repair_cap / 10000) × (1 + distance_from_nearest_controller × distance_decay_bp / 10000)`
  - `repair_cap = 3500 bp (35%)`
  - `distance_decay_bp = 500 bp (5% per tile)`
- `design/economy-balance-sheet.md` §3 模式差异：
  - Tutorial / Vanilla / Standard 分别列出 `starting_resources`、`free_upkeep_controllers`、`free_upkeep_drones`、`free_upkeep_ticks`、`repair_cap`、`repair_distance_decay`。
  - Standard / Vanilla 均为 `{Energy: 5000, Minerals: 2000}`、1 controller、3 drone、2000 tick、repair cap 3500 bp、距离衰减 500 bp。
- `specs/reference/api-registry.md` §5.1 游戏限制：
  - Registry 中同步列出 Starting resources、Free upkeep controllers/drones/ticks、Repair cap、Repair distance decay。

结论：B1 所要求的启动经济与 D1/A、D4/A 参数在 Resource Ledger、Balance Sheet、API Registry 中均有明确落点，且核心数值一致。

### [B2] GAP — Critical

经济参数一致性仍未闭合。虽然 Resource Ledger 已声明为经济数学权威，但同一批允许检查的文档中仍存在会导致实现者/评审者读取到不同经济参数的冲突。

具体缺失 / 冲突：

1. `design/gameplay.md` §2.7 / §帝国维护费示例效果仍保留旧版 empire-upkeep 模型与数值：
   - 文档写法：`drone_cost=2, room_base=10, room_superlinear=1`，示例为 1 房约 40/tick、5 房约 275/tick、20 房约 2100/tick、50 房约 3150/tick。
   - 但权威 Resource Ledger §Empire Upkeep 定义为：
     - `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`
     - Standard: `base_upkeep = 50`, `room_soft_cap = 10`
     - 对应 `design/economy-balance-sheet.md` §1：1 房 55/tick、5 房 375/tick、20 房 3000/tick、50 房 15000/tick。
   - 这不是注释性差异，而是公式、参数维度和数量级均不同。

2. `design/gameplay.md` 的全局存储传输时间与 Resource Ledger 权威参数不一致：
   - `design/gameplay.md` §资源存储模型 / §全局存储反制机制：
     - `transfer_to_global_time = 10 tick`
     - `transfer_from_global_time = 5 tick`
   - `specs/core/08-resource-ledger.md` §2.1 统一参数表：
     - `global_transfer_delay = 100 tick`
   - 如果 Ledger 是唯一权威，则 gameplay 中仍需改为引用 Ledger 或删除硬编码数值，否则同一经济动作存在 5/10/100 tick 三种可读解释。

3. `specs/reference/api-registry.md` 内部对 Storage Tax 阈值同时存在百分比阈值与绝对阈值，未完全一致：
   - §10.2 Economy Resource Operations 与 Resource Ledger 一致：0–30%、30–60%、60–85%、85–100%。
   - 但 §5.7 Economy 限制仍写：
     - tier 1 threshold = 10,000 units
     - tier 2 threshold = 100,000 units
     - tier 3 threshold = 1,000,000 units
   - Resource Ledger §2.2 与 Balance Sheet §1/§6 使用的是容量百分比 tier。绝对阈值表会让实现者误以为 tier 与 `global_storage_capacity` 无关。

4. `specs/core/08-resource-ledger.md` §6 的公式引用存在小错位：
   - §6 列表写 `Recycle refund: lifespan 10%-50% 公式见 §2.3`。
   - 实际 Recycle 权威公式位于 §2.5；§2.3 是 Starting Resources & Free Upkeep。
   - 该问题本身不是经济数值冲突，但会削弱「单一权威源」的可追踪性。

## Strengths

- Resource Ledger 已明确声明为经济系统唯一数学权威，并集中定义 starting resources、free upkeep、storage tax、repair cap、recycle、upkeep 等关键参数。
- B1 的核心启动经济链路已经形成闭环：初始资源 → 免维护窗口 → growth path → repair cap / distance decay → API Registry 暴露。
- Balance Sheet 对 Standard 1/5/20/50 房间维护费做了数值验证，能支撑 anti-snowball 评审。

## Concerns

E1. B2 仍有 Critical 级一致性缺口：`design/gameplay.md` 保留旧维护费模型，与 Resource Ledger / Balance Sheet 的权威公式冲突。

E2. 全局存储 transfer delay 在 gameplay 与 Resource Ledger 中未统一，可能影响经济物流成本与 No Teleport 约束实现。

E3. API Registry 的 Economy limits 中仍有绝对 storage tax threshold，与同文档 §10.2 和 Resource Ledger 的百分比 tier 不一致。

## Economy Balance Issues

- B1 启动期经济压力已合理闭合：Standard 1-room 长期负流量由 starting_resources + free_upkeep_ticks 缓冲，目标是在 tick 2000 前形成自维持。
- 但 B2 未闭合前，维护费曲线无法被视为最终可实现参数：读 gameplay 会得到 50 房约 3150/tick，读 Ledger/Balance Sheet 会得到 15000/tick。这会直接改变大帝国软上限强度。

## Resource Loop Gaps

- Resource Ledger 的操作顺序与资源入口是闭环的。
- 当前 gap 不在资源入口缺失，而在跨文档经济参数未完全收敛：尤其 upkeep、global transfer delay、storage tax threshold。

## Required Closure for B2

B2 需要至少完成以下文档收敛后才能 CLOSED：
1. 将 `design/gameplay.md` 中旧 empire-upkeep 示例替换为 Resource Ledger 公式，或删除硬编码数值并仅引用 Ledger + Balance Sheet。
2. 将 `design/gameplay.md` 的 global transfer time 参数改为引用 Resource Ledger 的统一参数，或在 Ledger 中明确区分 deposit/withdraw 两个 delay 并同步所有文档。
3. 修正 `specs/reference/api-registry.md` §5.7 storage tax threshold，避免绝对单位阈值与百分比 tier 并存。
4. 修正 Resource Ledger §6 对 Recycle 公式的小节引用。
