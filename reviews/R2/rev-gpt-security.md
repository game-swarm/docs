# R2 安全审计评审 — rev-gpt-security

Reviewer: rev-gpt-security (GPT-5.5)
评审日期: 2026-06-16
评审轮次: R2
评审范围:
- /data/swarm/docs/design/DESIGN.md
- /data/swarm/docs/ROADMAP.md
- /data/swarm/docs/specs/01-09
- /data/swarm/docs/reviews/R2/rev-dsv4-architect.md
- /data/swarm/docs/reviews/R2/rev-dsv4-security.md
- /data/swarm/docs/reviews/R2/designer-cross-review-dsv4.md
- R1 安全评审归档: rev-gpt-security / rev-dsv4-security

评审视角: 已知漏洞模式匹配、API 滥用检测、供应链风险嗅探、DoS 向量、跨文档安全合同一致性。

## Verdict

REQUEST_MAJOR_CHANGES

核心架构方向仍然正确：MCP 不提供 gameplay action、AI/人类同走 WASM、Source Gate 注入身份、Deferred Command Model、WASM 进程隔离、统一 visibility filter、Rhai action buffer 这些安全支柱没有被破坏。

但 R2 仍未达到安全冻结标准。R1 已指出的若干阻断项只修到了 DESIGN.md，specs 与 API docs 仍保留可实现成漏洞的旧合同。安全风险不是“实现时注意一下”能解决的：当前文档让不同实现者可以合理地实现出两套不兼容甚至不安全的行为。

最低放行条件：先修复 Critical 1-3，然后再进入实现冻结。High 项建议在同一修订批次内关闭；Medium 可进入 Phase 1 追踪。

---

## Critical

### C-1: Overload 安全合同仍分裂，specs/02 与 specs/08 可实现出远程 fuel DoS + 侧信道

证据:
- DESIGN.md §8 Overload 已写入三项正确约束：`is_visible_to(target, attacker)`、同一目标 50 tick 全局冷却、静默结果。
- specs/02 §3.12 仍保留 `TargetFuelTooLow`，并写“无 range 限制——Overload 是逻辑攻击”。校验表仍是 Range = N/A，未要求 `target_visible`，未要求 `target_global_cooldown(50)`。
- specs/08 IDL 的 Overload validator 仍为 `target_player, enemy_target, target_fuel_above(0.2), fatigue`，同样缺少 visibility 与 target-global cooldown。
- /data/swarm/docs/api/commands.md 仍列出 `TargetFuelTooLow`。

攻击模式:
- 攻击者不需要接近目标实体，只需知道 player_id，即可对目标玩家级 fuel budget 发起逻辑攻击。
- `TargetFuelTooLow` 返回码直接泄露目标是否已低于 fuel floor，违反“静默结果”。
- 只有 per-drone 200 tick cooldown 时，大号玩家可以用多个 drone 对同一目标协同压制；缺少 per-target 50 tick 全局冷却会把 Overload 变成跨地图 griefing 原语。

影响:
- 这是 gameplay 层面的 DoS primitive：敌方可以远程降低目标玩家所有 WASM 执行能力。
- 这是协议一致性漏洞：实现者按 specs 而不是 DESIGN 落地，就会复现 R1 已指出的问题。

必须修正:
1. specs/02 §3.12 删除 `TargetFuelTooLow`，改为“低于下限时静默 no-op，但对攻击者仍返回通用 Accepted/泛化结果”。
2. specs/02 §3.12 增加 `target_visible` / `is_visible_to(target_owner or target_entity, attacker)`。
3. specs/02 §3.12 增加 `target_global_cooldown(50)`，并明确 key: `(target_player_id, last_overloaded_tick)`。
4. specs/08 IDL Overload validator 改为包含 `visible_target`、`target_global_cooldown(50)`，删除 `target_fuel_above(0.2)` 作为拒绝条件；fuel floor 只能在 apply 阶段静默 clamp。
5. api/commands.md 同步删除 `TargetFuelTooLow` 或标注为 Admin-only audit reason，不可暴露给攻击者。

### C-2: 命令数量 / JSON 大小限制仍自相矛盾，DoS 防线不可实现

证据:
- specs/02 §1.1: `maxItems=100`、tick 输出总字节数 ≤ 256KB。
- specs/02 §6: 单条指令 ≤64KB、整批 ≤1MB、每 tick 每玩家 ≤500 条（含 Admin 来源）。
- specs/04 ABI 又以 256KB 作为 CommandIntent JSON 输出上限。

攻击模式:
- 按较宽松 §6 实现时，单玩家每 tick 可提交 500 条、1MB JSON；500 活跃玩家可产生极大的 parse/schema validation/rejection detail/TickTrace/ClickHouse 写入压力。
- “含 Admin 来源”会诱导把管理批操作塞进实时 tick pipeline，与玩家 budget 混用，导致实时系统被管理任务拖垮或反过来拒绝玩家指令。
- rejection detail 若记录完整 RawCommand，会把输入放大到持久审计日志。

必须修正:
1. 全仓统一为 R1 裁决值：`MAX_COMMANDS_PER_PLAYER = 100/tick`、`MAX_TICK_OUTPUT_BYTES = 256KB`、`MAX_COMMAND_BYTES = 16KB`。
2. specs/02 §6 删除冲突限制，改为引用 §1.1 的权威常量。
3. Admin bulk operation 明确不进入实时 tick pipeline；走离线 maintenance job / admin transaction queue，独立 budget 与审计。
4. 增加 `MAX_REJECTION_DETAIL_BYTES`：TickTrace 中 RawCommand body 默认 hash + truncated preview。

### C-3: MCP transport 安全合同仍没有闭合 browser / non-browser 边界，落入已知 MCP DNS rebinding 攻击模式

证据:
- specs/03 §2 仍写 MCP Server “仅 HTTP/SSE”，默认绑定 127.0.0.1 经 gateway/nginx 暴露。
- specs/03 §5.3 有 Host header、CORS Origin、JSON-RPC batch 禁用，但没有完整拆分 browser Web UI 与 non-browser AI/CLI transport。
- 现有 MCP 生态已有 DNS rebinding 类 advisory：MCP TypeScript SDK CVE-2025-66414、MCP Python SDK CVE-2025-66416；MCP Inspector 也出现过浏览器驱动本地工具服务的严重 RCE 事件（CVE-2025-49596 报道）。这与“HTTP/SSE + loopback/private endpoint + 浏览器可发请求”的攻击形态高度相似。

攻击模式:
- 恶意网页通过浏览器访问 localhost/private-network MCP endpoint。
- 如果 token/cookie/Origin/Host/SNI/aud 绑定任一处实现宽松，网页可驱动 MCP read/debug/deploy。
- SSE reconnect / long polling 可进一步用于连接耗尽。

必须修正:
1. 明确两套 transport contract:
   - Browser Web UI: SameSite=strict cookie 或显式 Authorization，CSRF token，严格 Origin，Fetch Metadata (`Sec-Fetch-Site`) 校验。
   - MCP agent/CLI: mTLS 或 signed request；不依赖 Origin；缺失 Origin 不是错误，但带 browser fetch metadata 且 Origin 不在白名单必须拒绝。
2. Token `aud` 必须绑定 `gateway_origin + world_id + transport_class`；Host header、SNI、public origin 三者一致才通过。
3. 增加 DNS rebinding / loopback 测试矩阵：恶意 Origin、缺失 Origin、伪造 Host、proxy rewritten Host、CORS preflight 绕过、SSE reconnect、Private Network Access preflight。
4. 将 “仅 HTTP/SSE” 更新为当前 MCP transport 路线；至少说明 SSE 是兼容模式，Streamable HTTP / mTLS agent transport 需要独立安全合同。

---

## High

### H-1: spectate_delay 只在 specs/05 声明，配置示例与 validate_config 仍允许 World 实时全图旁观

证据:
- specs/05 §3.5 声明：World 模式下 `public_spectate = true` 时 `spectate_delay >= 50`。
- specs/05 §8.5 示例仍显示 `spectate_delay = 0`。
- DESIGN.md §8.3 world.toml 示例也显示 `spectate_delay = 0`。
- specs/07 `validate_config()` 未检查 public_spectate + persistent + delay。

影响:
- 服主只要把 `public_spectate` 从 false 改为 true 而忘记改 delay，就变成实时全图情报广播。
- 旁观者可把实时信息传给参赛玩家，fog-of-war 失效。

建议:
- `validate_config()` 强制：`if world.mode == persistent && visibility.public_spectate && visibility.spectate_delay < 50 { error }`。
- 示例改为 `spectate_delay = 50` 并注释“World public spectate 最小值”。
- 更安全的默认：若 public_spectate 从 false 切到 true 且 delay 未显式设置，自动 clamp 到 50 并记录 warning。

### H-2: WASM 部署“证书 + 私钥签名”模型仍混淆，可能变成伪签名或高价值私钥集中点

证据:
- specs/03 §1.1 写证书含 Ed25519 public_key，同时写“服务端生成的临时密钥对”。
- 同一节又写“客户端附带证书 + 私钥签名(Blake3(WASM bytes))”。
- specs/09 §3.1 又说“不用客户端 keypair”，但如果客户端不生成 keypair，就不清楚谁持有签名私钥。
- 架构评审也指出 “Blake3 签名” 表述容易被误解为 HMAC/keyed hash，而不是 Ed25519 signature over digest。

影响:
- 若服务端生成并下发私钥，Auth Service compromise 可签任意玩家部署，不可否认性也不存在。
- 若实际只是 bearer token，保留“私钥签名”会让实现者误以为已具备防重放/防篡改能力。

建议（二选一，必须写死）:
1. 客户端生成 Ed25519 keypair，服务端只签 public key 证书；private key 永不离开客户端。部署签名为 `Ed25519_Sign(client_sk, domain_sep || module_hash || player_id || world_id || version_tag || nonce || exp)`。
2. 不做客户端签名，采用短期 bearer token + TLS/mTLS + server-side module hash audit；删除“私钥签名”全部表述。

无论选哪种，都必须加入 nonce/replay protection，证书 aud 绑定 world_id/gateway_origin，Tick 执行只接受与已认证部署记录绑定的 `module_hash`。

### H-3: `swarm_simulate` / `swarm_dry_run_commands` 是最小请求最大开销接口，线上预算不足

证据:
- specs/03 把 `swarm_simulate` 归为 `swarm:read`，World 5/tick / Arena 3/tick。
- specs/06 鼓励本地 `swarm sim --ticks=5000 --speed=100x`，但没有把线上 MCP simulate 与本地 CLI 明确分离。
- specs/09 将 Simulate budget 写为 `0.5× MAX_FUEL`，但没有每日/每小时总 fuel 预算。

攻击模式:
- AI agent 合法调用 simulate，把 engine 当免费搜索/优化计算资源。
- 若 simulate 运行在实时 engine process 或共享 worker pool，会抢占 tick scheduler。

建议:
- MCP 在线 simulate: `max_ticks <= 10`、`max_entities <= visible_entities_cap`、`max_output <= 256KB`、`max_cpu_ms`、`max_fuel_per_hour`。
- 5000 tick 模拟只能是本地 CLI 或异步 job queue，不在实时 engine process 内执行。
- simulate/dry-run 使用独立 worker pool 与 cgroup，不共享 tick scheduler 线程池。

### H-4: Wasmtime pin 与预编译缓存需要 emergency playbook；当前只写 SLA 不够

证据:
- specs/04 pin `wasmtime = "=30.0"`，严重 CVE 72h SLA。
- 当前检索到 Wasmtime 2026 advisories：CVE-2026-34971 / GHSA-jhxm-h53p-jm7w，aarch64 Cranelift guest heap access miscompile 可导致 sandbox escape，CVSS 9.0。
- specs/04 缓存键主要是 `(module_hash, wasmtime_version)`；DESIGN 提到 `(module_hash, wasmtime_version)`。

风险:
- Wasmtime/Cranelift 是核心 TCB。JIT/compile bug 可能让恶意 WASM 在预编译阶段进入 native cache。
- “=30.0” 保证 repeatability，但会延迟安全修复；安全补丁或 distro rebuild 不一定改变 semver 字符串。

建议:
- 增加 Wasmtime emergency playbook：全局暂停新部署、按世界暂停玩家 WASM、强制 cache namespace bump、按 arch/backend 失效预编译缓存。
- 缓存键加入 `wasmtime_build_commit + target_arch + compiler_backend + config_hash + security_epoch`。
- 编译 sandbox 与执行 sandbox 分离 seccomp/cgroup；执行进程不应拥有编译/JIT 所需的更宽 syscall。
- cargo audit 之外增加 advisory watcher 和 “known vulnerable runtime blocklist”。

### H-5: RuleMod 供应链“签名必需”已进 specs/07，但 DESIGN 与安装流程仍保留可选 checksum / tag 跟随语义

证据:
- DESIGN.md §8.7 mods.lock 写 checksum “可选”。
- specs/07 后半段增加 `.rhai.sig` / `mod.toml.sig`，未签名拒绝加载。
- 安装/更新命令仍是 `swarm mod add <git-url> --tag`、`swarm mod update`，强调 git pull + checkout tag。

风险:
- tag force-push、repo compromise、mod.toml 配置篡改都能影响世界规则。
- 仅签脚本不够；权限 manifest、normalized config、dependency graph 也需要进入签名/lock。

建议:
- DESIGN 与 specs 统一：checksum 必需，不是可选。
- `mods.lock` 必须包含 normalized manifest hash / file Merkle hash / declared permissions / author key fingerprint。
- `swarm mod update` 默认只更新 lock 候选，不自动启用；需要 diff review。
- 增加 capability manifest：模组声明需要 `deduct_resource` / `award_resource` / `damage_entity` / `set_entity_flag` 等权限，默认最小授权。

### H-6: `player_view=full` + MCP deploy scope 组合会造成 out-of-band 情报注入

证据:
- specs/05 §3.5 写 `player_view = full` 时玩家屏幕 / MCP 可见全地图，但 WASM snapshot 仍按 `is_visible_to`。
- specs/05 §8.4 把教学世界设置为 fog_of_war=false / player_view=full。

风险:
- AI agent 同时拥有 full view 与 deploy 能力时，可把全图信息编译进下一版 WASM，即使 tick snapshot 被过滤，也已经产生 out-of-band 情报注入。

建议:
- 任何 full-view 世界必须隔离：不与正式 World/Arena 互通，不计排名，不允许资源/资产迁移。
- MCP full view 使用独立 scope `swarm:spectate`，不得与 `swarm:deploy` 同时授予同一 token。
- Arena 赛后 full replay 与 deploy token 必须时间隔离。

---

## Medium

### M-1: path_find / terrain “公开”削弱 fog-of-war，需要明确地形情报模型

证据:
- specs/04 §3.2 写 `host_get_terrain` 地形公开，无需过滤；`host_path_find` 仅基于可见地形计算路径。
- specs/05 §3.0 又写 path_find 仅基于可见地形。

问题:
- 若 terrain 真公开，则 path_find 可用于远程地图探测，fog-of-war 只隐藏实体，不隐藏战略地形。
- 若 terrain 不公开，则 `host_get_terrain` 与 specs/05 不一致。

建议:
- 二选一并写明：公开地形是有意设计，还是 unexplored terrain 应返回 `LocationNotVisible`。
- 若公开地形，文档应承认它是游戏规则而非安全隔离，并避免把 terrain secrecy 当反作弊能力。

### M-2: `host_get_objects_in_range` / `path_find` 缺少 truncated / explored_nodes 上限

证据:
- specs/04 给 `host_get_objects_in_range` 64KB 响应上限，但未定义超限时返回 `truncated`。
- path_find 只有 `MAX_PATH_LENGTH=100`，缺少最大探索节点数。

风险:
- 密集区域返回被截断时，玩家无法区分“没有实体”与“结果太多被截断”。
- 不可达路径可能迫使 A* 探索大量节点，尤其跨房间寻路时。

建议:
- objects_in_range 返回 `{ items, truncated, total_visible_count? }`，按距离稳定排序。
- path_find 增加 `MAX_EXPLORED_NODES` 与 `MAX_CROSS_ROOM_PATH_COST`。

### M-3: TOML 中仍出现浮点写法，与确定性合同冲突

证据:
- DESIGN.md / specs/07 示例有 `memory_upkeep_cost = { Energy = 0.01 }`、`decay_rate = 0.001`、`damage_multiplier = 1.0`。
- DESIGN §8.8 要求禁 f64，使用整数 + fixed-point。

风险:
- 实现者可能直接用 TOML float → 跨平台 determinism 与回放校验风险。

建议:
- 所有配置示例改为 fixed-point 整数，例如 `damage_multiplier = 10000`、`memory_upkeep_cost = { Energy = 100 } # 0.01 × 10000`。
- validate_config 拒绝 float literal。

### M-4: seed_rotation_interval 可配置但 validate_config 无上下限

证据:
- specs/01 §3.1 允许 `seed_rotation_interval = 10000`。
- specs/07 validate_config 未校验。

风险:
- 0 / 极小值导致 seed epoch 记录膨胀；极大值等于长期不轮换。

建议:
- 强制 `seed_rotation_interval ∈ [100, 100000]`，默认 10000。
- shuffle domain separation 使用 `Blake3("swarm-shuffle-v1" || seed || tick)`。

### M-5: Audit / TickTrace 大字段与日志注入需要独立上限

证据:
- specs/03 ClickHouse `parameters String`, `result String`。
- specs/02 rejection response 包含原始 RawCommand 与 detail。

风险:
- 恶意 version_tag、module metadata、MCP params 可放大日志写入或污染查询/展示。

建议:
- 审计字段结构化，untrusted string length cap + escaping。
- 大字段 hash + truncated preview。
- `version_tag` 字符集与长度单独限制。

### M-6: Bevy 依赖风险主要是 determinism drift，不是传统 CVE

当前检索 crates.io bevy_ecs security 未见 advisory。Bevy 的主要风险是快速演进导致调度/迭代顺序行为变化，影响 replay determinism。

建议:
- pin Bevy minor/patch。
- 每次升级运行 replay determinism corpus。
- 文档补充 ECS query ordering contract：任何影响状态的 query 结果必须显式排序或使用 deterministic storage。

---

## Informational

### I-1: R2 正向改进确认

已确认以下 R1 方向在 R2 中明显改善:
- DESIGN.md 中 MCP 明确仍是“屏幕和鼠标”，不是 gameplay action controller。
- AI 和人类同走 WASM，唯一执行器仍是 WasmSandboxExecutor。
- Rhai 增加了事务性 action buffer、AST 节点预算、进程隔离、签名机制。
- Tick protocol 增加了 Bevy World snapshot / restore 与 COLLECT cache。
- specs/03 加入 Host/CORS/batch 禁用等 HTTP 安全基线，虽然还需要 transport 分层。

### I-2: 与其他 R2 评审的交叉一致性

本评审与 rev-dsv4-security 高度一致：Overload 与 command limits 是 Critical。与 rev-dsv4-architect 的 D1/D2/D3/D5 也一致，其中 D1/D2 是安全阻断项，D3 是 High，D5 是架构/SDK 一致性问题但也会影响校验正确性。

### I-3: 亮点仍然成立

- Deferred Command Model 是最强安全决策：WASM 只能返回 JSON intent，所有 mutating 操作由服务端统一校验。
- Source Gate + server-injected auth context 能系统性防 IDOR / mass assignment。
- 统一 `is_visible_to` 抽象是防调试接口泄露的正确基础。
- WASM sandbox 的多层防御（fuel、epoch、WASI 禁用、import whitelist、seccomp、cgroup、无网络、per-tick worker）方向正确。
- Prompt injection 被显式建模（untrusted 字段、玩家名字符集、SDK delimiter），这是 AI 游戏中非常必要的安全设计。

---

## 放行清单

必须在重新评审前关闭:
1. Overload specs/02 + specs/08 + api docs 与 DESIGN 同步。
2. 命令数量/大小上限全仓统一，删除 500/1MB/64KB 冲突。
3. MCP transport contract 拆分 browser/non-browser，并加入 DNS rebinding 测试矩阵。

建议同批关闭:
4. spectate_delay validate_config + 示例修正。
5. WASM 部署签名模型二选一并明确。
6. simulate/dry-run 线上预算与隔离 worker。
7. Wasmtime emergency playbook 与 cache key security_epoch。
8. RuleMod checksum/signature/capability manifest 统一为必需。

结论：当前设计不应直接冻结实现；修完上述 P0/P1 安全合同后，可进入 CONDITIONAL_APPROVE。