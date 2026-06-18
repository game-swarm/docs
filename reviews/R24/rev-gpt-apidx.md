# R24 Closure Verification — API/DX (GPT-5.5)

Verdict: CONDITIONAL_APPROVE

## Strengths

- `api-registry.md` 明确声明 YAML IDL 为唯一机器可读权威源，Registry 为生成产物，其他文档只能引用，不得重新声明可冲突列表。
- MCP 工具表已补齐输入/输出 schema、rate limit、scope、subject_source、replay_class、visibility_filter、rate_limit_key 等 DX 关键列。
- `RejectionReason` 已收敛为 canonical wire enum，并通过 `debug_detail` / `detail_level` 提供可用调试信息，避免错误码无限膨胀。
- 三层 drone cap 已在全局容量限制中明确落位，且给出 world.toml 可调范围与上限值。

## Concerns

### [B2] GAP

API 单事实源已部分闭合，但仍存在派生文档/生成链与 Registry 的可见不一致，闭合不完整：

- `specs/reference/api-registry.md:1-9` 声明本文档由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 自动生成，且是所有 API 合约的单一权威来源；`api-registry.md:11-17` 进一步要求新增指令/错误码/工具/函数必须注册，未注册 CI 拒绝。
- `design/interface.md:17-21` 指向 Registry §3 作为权威工具清单，并声明概念表不得用于实现引用，方向正确。
- 但 `design/interface.md:19` 写作 “56 game tools + 11 auth tools”，而 `api-registry.md:207-211` 写作 “54 个活跃工具 (game_api) + 11 个 Auth API 工具”，同一 Registry 内 `api-registry.md:226-331` 也标注 Game API 工具清单为 54；与此同时 `api-registry.md:854-857` changelog 又写 “MCP tools 总数为 56 active”。
- `specs/reference/codegen.md:20-27` 禁止手写数值列出 `CommandAction 数量 (当前 19)`、`MCP tool 数量 (当前 56 active)`、`RejectionReason 数量 (当前 79)`，但 `api-registry.md:37-43` 的 CommandAction 为 21，`api-registry.md:86-90` 的 RejectionReason 为 47 canonical code，`api-registry.md:207-211` 的 game tools 为 54。
- `specs/reference/mcp-tools.md:3-6` 声明权威工具清单见 Registry §3 — 56 个 Game API 活跃工具 + 11 个 Auth API 工具；这与 `api-registry.md:207-211` / `api-registry.md:226-331` 的 54 个 game tools 不一致。

结论：B2 的“权威源声明”和“派生文档只引用 Registry”已经建立，但 codegen/派生参考文档仍保留旧计数或相互矛盾计数。作为 API/DX 关闭验证，这会让 SDK 作者和 MCP 客户端生成器无法判断应以 54 还是 56 个 game tools、21 还是 19 个 CommandAction、47 还是 79 个 RejectionReason 为准。因此 B2 未完全 CLOSED。

### [D2/B] CLOSED

三层 drone cap 已正确闭合：

- `specs/reference/api-registry.md:456-471` 将全局容量限制设为权威上限，并明确：`Per-player drone cap = 50`、`Per-room drone cap = 500`、`Global drone cap = 10,000`。
- `api-registry.md:468-471` 说明 per-player cap 为 world.toml 可调、per-room per-player baseline，per-room cap 为 world.toml/RCL room-level total 且与 per-player cap 取较小值，global cap 为全局活跃 drone 上限。
- `specs/reference/commands.md:81-87` 的 Spawn 校验包含“房间有空槽位”，与 room cap 校验路径一致；`api-registry.md:121-134` 注册了 `RoomDroneCapReached` canonical rejection code，可为三层 cap 冲突提供稳定 wire code。
- `design/interface.md:110-118` 和 `commands.md:220-226` 将额外上下文放入 `debug_detail`，可表达是 per-player / per-room / global 哪一层触发，而不扩张 wire enum。

## Missing

- B2 还缺一次以 IDL 生成结果为准的跨文件计数同步：`api-registry.md`、`codegen.md`、`mcp-tools.md`、`design/interface.md` 中的工具数、CommandAction 数、RejectionReason 数需要完全一致。
- D2/B 无缺失；本轮仅验证三层 drone cap，不扩展新问题。

## API Consistency Issues

- `api-registry.md` 自身在 §3 与 changelog 中对 MCP tool 数量出现 54/56 不一致。
- `codegen.md` 的禁止手写数值表仍保留旧数字：CommandAction 19、RejectionReason 79、MCP tools 56，与当前 Registry 表格不一致。
- `mcp-tools.md` 和 `design/interface.md` 引用 Registry 但仍手写 56 game tools，削弱了“只引用、不重声明可冲突事实”的 B2 目标。
