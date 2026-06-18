# R25 Closure Verification — API/DX (GPT-5.5)

## B2: GAP

证据：
- `specs/reference/api-registry.md:1-9` 已明确 API Registry 由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 自动生成，并声明 CommandAction、RejectionReason、MCP Tools、Host Functions、Economy Operations、容量限制均以 Registry 为准；`codegen.md:7-10` 也要求 IDL 为唯一机器源、Registry 全量生成、CI diff check 阻塞漂移。
- `specs/reference/api-registry.md:543-557` 已将 economy 限制统一为 percentage-based storage tax：30%/60%/85% capacity 阈值，而非旧 10K 阈值；`api-registry.md:738-740` 将 `StorageTax`、`UpkeepDeduction`、`RecycleRefund` 注册为 Economy Operations，并把 `StorageTax`/`UpkeepDeduction` 指向 `specs/core/08-resource-ledger.md` 的权威公式。
- `specs/reference/api-registry.md:752-753` 已给出 `RecycleRefund` 的 lifespan-proportional 10%–50% canonical formula，并注明 `StorageTax` 使用 `resource-ledger.md` §2.2 tiered formula；`api-registry.md:859-860` changelog 也记录 economy 0.1.1 将 StorageTax 改为 30/60/85/100% capacity、UpkeepDeduction 改为 superlinear empire upkeep。
- 但 `specs/reference/commands.md:114-120` 仍在派生展示文档中直接声明 Recycle “退还 50% body part 资源 / `body_cost(body) × 0.5`”，与 Registry 的 lifespan-proportional 10%–50% formula 冲突。该残留仍会误导 SDK/API 用户，因此 R24 B2 Recycle §2.3→2.5 残留未完全闭合。

结论：B2 主要权威链已收敛，但存在派生 API 参考残留的 Recycle 固定 50% 冲突；按 Closure Verification 规则判定为 GAP。

## B3: CLOSED

证据：
- `specs/reference/api-registry.md:67-82` 将 8 个特殊攻击统一注册在 CommandAction/CustomActionRegistry 路径：所有特殊攻击通过 `CommandAction::Custom(type)` 路由至 `CustomActionRegistry`，并关联同名 `[[special_effects]]` handler；这为 API/DX 参考层提供唯一入口。
- `specs/reference/commands.md:22-24` 明确“权威指令清单见 API Registry §1”，并说明 8 种特殊攻击通过 `CommandAction::Custom(type)` 路由到 `CustomActionRegistry`；`commands.md:132-134` 的特殊攻击章节同样采用 CustomActionRegistry + `[[special_effects]]` 说明。
- 在允许读取的 API/DX 参考文件中，未发现独立的特殊攻击优先级冲突表；`commands.md` 仅保留使用示例和上下文说明，且入口指向 API Registry/CustomActionRegistry。

结论：B3 在 API/DX 参考层已闭合；特殊攻击权威入口一致，没有发现 `02-command-validation` 风格的冲突优先级表残留。

## Verdict: REJECT

原因：B3 CLOSED，但 B2 仍有 Blocking GAP：`commands.md` 的 Recycle 固定 50% 退款说明与 `api-registry.md` 的 lifespan-proportional 10%–50% canonical formula 冲突。