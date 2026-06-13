# Security Review — Claude Opus 4.8 (Round 3)
**Verdict**: CONDITIONAL_APPROVE — Phase 0 gate on C1+C2+H4+H5

## Critical
- **C1**: Tick() 输出 JSON 无 schema 校验——WASM 可返回超长/恶意 Command JSON 绕过 P0-2 validator
- **C2**: Fuel refund model 可被滥用探测——退 50% 燃料可用作低成本信息采集

## High
- **H1**: Rhai mod 确定性未闭合——`state.players()` 迭代顺序影响 `deduct_resource` 累计舍入
- **H2**: compile-time DoS 防线单一——仅靠 worker process timeout
- **H3**: `swarm_simulate` 无隔离边界——可被用作免费探索工具
- **H4**: P0-9 Tutorial source 有 gameplay mutation 能力但无 validation contract
- **H5**: P0-2 仍含 MCP 时代遗留假设——需重新审计

## Medium (M1-M8)
- M1: Rhai `modify_entity` 权限过广
- M4: Replay/TestHarness 绕过 Source Gate 需 ingress isolation 文档
- M5: deploy 参数注入（version_tag/language 未校验）
- M8: WASM→player_id 绑定未显式声明

Gate on: C1+C2+H4+H5.
