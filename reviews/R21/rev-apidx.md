# R21 API/DX — B20-1 清零验证

**评审员**: rev-dsv4-apidx (API/DX)
**日期**: 2026-06-18
**来源文件**: `/tmp/swarm-review-R21/design/interface.md`, `specs/reference/api-registry.md`, `specs/reference/game_api.idl.yaml`

---

## Verdict: CLOSED

B20-1 四项残留全部清零。

## 验证证据

1. **旧 MCP 工具完整表 → 概念概述 + api-registry.md 指针**: interface.md §4.1 已替换为分类概念表（7 类别 + 代表性工具），明确声明「不列完整表」「以 Registry 为准」并指向 api-registry.md §3。Confirmed.

2. **swarm_deploy replay_class → deploy_mutation**: interface.md L158 明确标注 `replay_class: deploy_mutation`，不复用旧 `replay_class` 名称。Confirmed.

3. **RejectionReason 35 变体 → 47 canonical codes**: interface.md L118 引用 api-registry.md §2「47 canonical codes (35 game + 12 auth)」，与 IDL 的 35 game + api-registry 的 12 auth 一致。Confirmed.

4. **Phantom tools 不在权威表中**: `swarm_get_schema`、`swarm_submit_csr`、`swarm_token_refresh`、`swarm_change_password`、`swarm_federated_login` 五个幻影工具仅在 interface.md L33 的「已移除的工具」声明中出现，概念表（L23-31）和 api-registry.md 全文均无残留。Confirmed.
