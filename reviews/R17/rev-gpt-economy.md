# R17 Economy Review (GPT)

Verdict: REQUEST_MAJOR_CHANGES

## Strengths
- 资源模型已经具备完整闭环雏形：faucet / transfer / sink / lockup / unlock 的分类清楚，且 Resource Ledger 给出了统一的执行顺序与 TickTrace 归因。
- 反雪球工具箱是完整的：帝国维护费、累进存储税、全局↔本地转换损耗、Controller age 上限、新手保护期，这些机制方向一致。
- 经济反馈是可观测的：`swarm_get_economy`、趋势工具、税率预警、idle 告警，都有助于玩家理解“为什么亏 / 为什么卡住”。
- 设计上明确拒绝了“无限囤积 = 永动机”这类常见失衡模式，方向正确。

## Concerns

E1 [Critical] 帝国维护费公式与默认参数没有闭合，直接影响整套反雪球证明。
- `design/gameplay.md` §8.7、`economy-balance-sheet.md`、`specs/core/08-resource-ledger.md` 对 upkeep 的说法并不一致。
- Resource Ledger 给出的是 `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)`，并固定了 Standard / Vanilla / Tutorial 的 `base_upkeep` 与 `room_soft_cap`。
- 但 `design/gameplay.md` 同时又写了 `drone_cost=2, room_base=10, room_superlinear=1`，并声称 50 rooms 约 3150/tick；这与前述公式和 balance sheet 中的 50 rooms = 15,000/tick 不一致。
- 结果是：当前文档无法证明“默认 Vanilla / Standard 曲线”到底是哪一条，anti-snowball 的权威单源没有真正闭合。

E2 [High] 存储税的费率模型仍然冲突：tiered tax vs fixed bp/tick。
- `design/gameplay.md` 写的是 0/1/5/20 bp 的累进 tiered tax，并将其作为长期囤积抑制机制。
- `specs/core/08-resource-ledger.md` 却定义 `storage_tax_rate = 10 bp/tick`，而且是全局账本里的固定费率。
- `economy-balance-sheet.md` 也基于 tiered tax 做均衡证明。
- 这意味着“税率随占用率变化”与“固定每 tick 税率”二者不能同时成立；如果不统一，玩家将能轻易利用税率差异做套利或规避。

E3 [High] Allied transfer / P2P transfer 的经济边界仍未统一。
- `design/gameplay.md` 的外交段落写成了 allied 状态下可直接 player↔player transfer，且“免 convert 延迟”。
- `specs/core/08-resource-ledger.md` 则要求 AlliedTransfer 走单独账本，带 2% fee、200 tick delay、24h 限额与日上限。
- 这不是细节差异，而是资源闭环的关键路径差异：如果 allied transfer 免延迟且免费，联盟就会变成绕过本地↔全局损耗的免费管道；如果按 Resource Ledger 执行，则 gameplay 文案需要同步更新。

E4 [High] Market / trading 的“已移除”与“仍注册”互相打架，经济闭环边界未封死。
- `design/gameplay.md` 声称 Market / trading 是 RFC，占位，不在当前设计范围内，且从 IDL / 默认 SDK 移除。
- 但 `specs/reference/api-registry.md` 仍然暴露了 `swarm_list_market_orders`。
- 即便该工具当前只是只读，也说明“市场相关对象”并未真正从权威 API 面清掉；这会让后续经济闭环评审失去单源边界，也容易让实现侧误把 RFC 当成已支持路径。

E5 [Medium] PvE 奖励与世界总量控制方向正确，但上限之间的关系还需要更强的数值约束说明。
- `design/modes.md` 与 `specs/core/08-resource-ledger.md` 都提到 PvE budget / 世界再生总量 30% cap，这很好。
- 但 `design/gameplay.md` 中仍有多处“可再生 / 掉落 / 资源爆发 / 地点奖励”的描述，如果不把这些入口全部显式接到 Resource Ledger，后续很容易出现“看起来是同一个 faucet，实际上分成了多个非对称入口”的实现偏差。
- 这一条不像前面几项那样是立即冲突，但属于闭环证明所缺的最后一层约束。

## Economy Balance Issues
- 维护费与存储税是反雪球主轴，但当前文档把“公式”“默认参数”“示例数值”分散在三处，且彼此不同步；这会让 balance sheet 失去证明力。
- Allied transfer 如果没有被严格纳入统一账本，联盟会天然比单体玩家拥有更低摩擦的资金通道，产生“组织规模优势 > 经营效率”的滚雪球风险。
- Market 虽标注 RFC，但 API 注册表里仍残留相关读取工具，说明系统边界还没完全收口；这会把未来的价格发现、仲裁、税率、跨玩家结算问题提前带进当前设计。
- 目前对大帝国的压制主要靠 upkeep / tax / delay / age 三件套，方向对，但缺少一份真正统一、可直接计算的“标准参数表”。

## Resource Loop Gaps
- 还缺一份单一的“权威经济参数表”，把 upkeep、storage tax、global transfer fee、allied fee、PVE cap、recycle refund 放在同一张表里，并指定唯一生效值。
- `design/gameplay.md` 中的本地存储、全局存储、联盟转移、市场、PvE 掉落之间，仍然存在“哪个算 transfer、哪个算 sink、哪个算 faucet”的边界模糊。
- 需要明确：哪些路径允许绕过 global storage，哪些路径必须经过 Resource Ledger 的统一执行顺序，否则套利点会从“功能”里长出来。
- 需要把所有提到“free / no delay / RFC / placeholder”的路径和实际可用路径做一次最终收口，否则单源权威只是名义上的。

## CrossCheck
- Checked `design/README.md`, `design/gameplay.md`, `design/modes.md`, `design/economy-balance-sheet.md`.
- Checked `specs/reference/api-registry.md`, `specs/reference/game_api.idl.yaml`, `specs/gameplay/06-feedback-loop.md`, `specs/gameplay/08-api-idl.md`, `specs/core/08-resource-ledger.md`.
- Conclusion: the economy architecture is directionally strong, but authority is not yet fully closed; at least three core paths still disagree across the supposedly single-source docs.
