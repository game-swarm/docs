# R7 Game Designer Review — rev-dsv4-designer

> Recovered from Kanban task `t_e3a9fbbf` comment. Original reviewer blocked as review-required with full findings JSON instead of writing a filesystem artifact.

## Verdict

CONDITIONAL_APPROVE

## Findings Summary

- Critical: 1
- High: 5
- Medium: 5
- Low: 3

## Critical

### C1: Leech/Fabricate 与 Vanilla Standard+ / IDL 合同不一致

位置：`design/gameplay.md` 特殊攻击方式 vs `specs/gameplay/08-api-idl.md` §2 commands。

问题：gameplay.md lists 8 special attacks as Standard+ 全部可用，但 IDL commands section only defines first 6. Leech and Fabricate are only in §5.1 with custom body parts.

修正：要么补 Leech/Fabricate 的 full command definitions，要么将 gameplay.md 改为 Standard tier=6 attacks，Leech+Fabricate=Layer 3 extension。

## High

- H1: Overload cooldown conflict: 200 tick drone cooldown vs per-target 50 tick global cooldown。
- H2: Hacked Neutral drone 可能不计入原 owner room cap，形成 friendly hacking cap bypass。
- H3: Fabricate converts enemy drone to friendly structure，但 structure type/handler parameter 未定义。
- H4: room count / territorial expansion 缺少 anti-snowball 机制。
- H5: Market Contracts 出现在 first-hour mechanism 但没有 creation/execution/settlement/default spec。

## Medium

- M1: Arena fog_of_war=false + player_view=full 与 visibility rejection rule 冲突。
- M2: `vanilla.tier` referenced but absent from world.toml schema。
- M3: Recycle 50% refund creates dominant combat retreat strategy。
- M4: TOUGH +100 age vs ATTACK -80 age creates 65x lifespan gap。
- M5: World event trigger threshold undefined for 10% probability。

## Low

- L1: duplicate rejection codes `RoomDroneCapReached` vs `ExceedsRoomCapacity` unclear。
- L2: Leech/Fabricate use `body_part=custom` inconsistent with Standard claim。
- L3: fatigue accumulation formula unspecified。

## Strengths

Move-as-action consistency; information asymmetry depth; anti-dominant strategy layers; newbie threat curve; world.toml configurability; Controller vs Depot logistics; PvE geographic gradient; MCP parity for AI/human players.
