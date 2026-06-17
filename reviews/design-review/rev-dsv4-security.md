# R7 Security Review — rev-dsv4-security

> Recovered from Kanban task `t_948384b2` summary + full comment thread. Original reviewer completed successfully but did not leave a filesystem artifact in `/data/swarm/docs/reviews/R7/`.

## Verdict

CONDITIONAL_APPROVE

## Findings

- Critical: 0
- High: 2
- Medium: 4
- Low: 2

## High

### H1: Rhai `actions.set_entity_flag` 的 `allowed_flags` 白名单未定义

位置：`specs/core/07-world-rules.md` §5.1。

问题：`actions.set_entity_flag(entity_id, flag, value)` 要求 flag 必须在 `allowed_flags` 白名单中，但白名单具体内容未定义。若未在 engine 或 `world.toml` schema 显式声明，Rhai 模组可能设置未预期 flag，绕过 combat/ownership/visibility 语义。

修正：在 specs/core/07 §5.1 补默认 `allowed_flags` 列表，并声明非白名单 flag 在 action buffer apply 阶段拒绝 + 审计。

### H2: `host_path_find` 确定性失败返回协议未指定

位置：`specs/core/04-wasm-sandbox.md` §8 + `specs/core/02-command-validation.md` §4.3。

问题：超过 100,000 explored_nodes 后只写 deterministic fail，未定义返回码/空路径语义，SDK 无法区分 unreachable 与 quota exhausted。

修正：定义 `PATHFIND_QUOTA_EXCEEDED=-3`，`len=0`，并区分 `-1` unreachable、`-3` quota exceeded、`0` success。

## Medium

- M1: `snapshot_len` timing oracle residual。
- M2: `host_path_find` explored_nodes quota 仅在 specs/04 定义，specs/02 缺失。
- M3: session reconnect refund credit window 缺少 decay。
- M4: `swarm_get_world_rules` 与 `swarm_get_schema` 限流不一致。

## Low

- L1: WASM sandbox per-player process fork pressure 未量化。
- L2: `soft_launch` 结束后 PvP broadcast race window。

## Bright Spots

visibility oracle closure; multi-layer sandbox depth; Source Gate + CommandIntent zero-trust; Recycle proportional refund; Rhai transactional execution with trust chain; Overload anti-lockout proof; DNS rebinding layered defense.
