# R7 Security Review — rev-claude-security

> Recovered from Kanban parent task `t_c4cd7f5` metadata. The reviewer completed with structured metadata but no filesystem artifact was found.

## Verdict

CONDITIONAL_APPROVE

## Findings Summary

- Critical: 0
- High: 2
- Medium: 6
- Informational: 4

## High

### H1: WS transport 把 JWT 放 URL query string

位置：`specs/security/03` §2.1 + `specs/12` §3.1。

问题：Browser WS token in query string can leak via nginx logs, Referer, browser history, screen share.

修正：握手后首条消息 auth，或 cookie+CSRF；至少 nginx log_format 屏蔽 token 参数并禁止 Referer 转发。

### H2: refund credit 在 reconnect + same-session deploy 例外下绕过 deploy-reset

位置：`specs/core/02` §7.2 + `specs/security/09` §7.1。

问题：60s reconnect + same-session deploy exception can preserve refund credit through deploy reset and recreate v1 farm refunds → v2 spend attack.

修正：三选一：删除 same-session 例外；例外限定 ≤20 tick 且累计 credit ≤MAX_FUEL×1%；或 reconnect 路径强制 credit 清零。

## Medium

- M1: Overload 中的 `is_visible_to(player)` 未在 visibility spec 定义。
- M2: `path_find cache_miss_penalty` 可通过 fuel 消耗反映 visibility_fingerprint 变化。
- M3: `spectate_delay` 只以 tick 计数，Arena 300ms tick 下 50 tick≈15s。
- M4: TickTrace WAL 仅本地磁盘，与“无审计缺口”承诺冲突。
- M5: prompt injection delimiter 由 SDK 负责，raw MCP 绕过即失效。
- M6: Rhai `actions.*` 基础 capability 隐式授予且无 quota。

## Informational

world_seed forward-secrecy hardening; `mcp_audit.parameters` size policy; public spectator policy fingerprint; rollback dual-signature time window.

## Highlights

Source/capability matrix; Phase 2a TOCTOU convergence into `validate_and_apply`; visibility-priority + equivalent rejection codes; Recycle/Overload invariant proofs.
