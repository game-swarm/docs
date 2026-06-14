# R12 Security Reviewer — Stage 1 Findings

> 零历史上下文评审。范围: DESIGN.md, tech-choices.md, specs/p0/01-09。
> 严重度: Critical / High / Medium / Low。

## C1 — PathFind 缓存键缺失可见性维度（跨玩家路径/地形泄露）
P0-2 §4.3 将 PathFind 结果以 `(from, to, 地形hash)` 缓存复用；但 P0-5 §3.0 要求
`path_find` **仅基于可见地形**计算。缓存键不含 `player_id` 或可见性状态，两个 fog-of-war
状态不同的玩家命中同一缓存条目时，会得到一条穿越**调用者不可见地形**的路径——既泄露未侦察
区域的可通行性，也违反「无绕过」不变量。**修复**: 缓存键加入 player 可见性指纹，或按
`(player_id, tick, from, to)` 缓存。

## C2 — world_seed 复用使 seeded_shuffle 顺序可预测
P0-1 §3.1: `seed = Blake3(tick_number || world_seed)`，tick_number 公开。P0-5 数据分级将
`world_seed` 列为 Admin-only，但 Arena 赛后「全知回放」公开。若回放暴露 world_seed，或服主跨
赛复用同一 seed，则所有 tick 的玩家执行顺序可被离线预演 → 玩家可针对资源竞争「卡位」。
**修复**: world_seed 永不复用且永不出现在任何公开回放；或每 tick 混入不可预测熵（已提交指令的承诺哈希）。

## H1 — 双认证生命周期未对齐 + 缓存模块的吊销时机
P0-3 §1.1 证书有效期 24h；§3.1 JWT `exp = iat + 900`（15min）。两者关系（谁授权 deploy、token
过期后证书是否仍有效）未规定。P0-4 §7 模块缓存「每 tick 校验 auth token 仍有效」，但未说明对
24h 证书还是 15min JWT 校验，也未定义 jti 撤销列表如何驱动缓存条目失效。**修复**: 明确
cert↔token 绑定关系，模块缓存失效必须订阅 jti 撤销事件。

## H2 — Admin 来源无限速率 + 全量写，仅 Rollback 双人审计
P0-9 §2.1/§2.3: `Admin` 允许写世界/全局存储/部署/战斗，`rate_limit = 无限制`，仅 `Rollback`
要求双 admin 签名。单个 admin token 泄露即等于完整世界控制权且无速率护栏。**修复**: 对 Admin
写操作加速率上限与审计告警阈值，关键变更（ban、资源注入）纳入双人控制。

## M1 — damage_multiplier 类型混淆
P0-7 §2 `combat.damage_multiplier = 1.0`（浮点）与 §7 校验 `< 1`（整数语义）矛盾，而其他比率字段
用 `fixed<u32,4>`（1.0 = 10000）。浮点 1.0 在定点解析下可能被读成 1（≈0.0001×）或校验误拒。
**修复**: 统一为 `fixed<u32,4>`，校验改 `< FIXED_SCALE`。

## M2 — memory_upkeep 先扣后判负，暗示有符号下溢
P0-7 §4 `resources.deduct(...)` 后再 `if resources.get(res_name) < 0`。若资源为无符号则下溢回绕，
若为有符号则与各处 u32 资源表述不一致。**修复**: 扣减前 `checked_sub`，不足额按可用量扣。

## M3 — MCP 分类配额之和超出 MCP_Query 聚合上限
P0-3 §5.1: 读 50 + 调试 30 + 开发辅助 20 = 100/tick，超过 P0-9 §2.1 给 `MCP_Query` 的 50/tick。
信息抓取预算实际是设计意图的两倍。**修复**: 设置跨类硬聚合上限并对齐两份文档。

## L1 — 单 tick 输出体积内的 JSON 嵌套成本
P0-2 §1.1 允许 256KB、深度 10、100 条指令；单条指令内仍可构造接近上限的嵌套，解析成本未计入
fuel。**修复**: 反序列化成本计入 fuel 预算，或加每条指令字节上限。
