# R43 Phase 1 Clean-Slate 独立评审 — rev-gpt-cross-cutting

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：跨域架构方向本身清晰（COLLECT/EXECUTE 分层、per-shard single writer、MCP 不直接动作、Registry/IDL 单事实源目标都合理），但当前文档集存在多处跨设计域与参考规范之间的权威源冲突。最严重的是 Auth 单层 CA / 两证书模型与 auth_api.idl.yaml 的 Intermediate CA / passkey / admin certificate 残留冲突，以及 API Registry、game_api.idl.yaml、codegen.md 之间对版本、host function 数量、错误 envelope、deploy 流程的互相矛盾。这些问题会直接导致实现者无法判断应按哪个接口和数据流实现，必须先修复再进入下一轮。

## 2. 发现的问题

### F1 — Critical — Auth 设计与 Auth IDL/Registry 残留旧证书模型，破坏认证边界的一致性

文件引用：
- `/data/swarm/docs/design/auth.md:31`：认证原则明确为“单层 CA”。
- `/data/swarm/docs/design/auth.md:32`：证书类型明确只有 `ClientAuthCertificate` 与 `CodeSigningCertificate` 两种。
- `/data/swarm/docs/design/auth.md:181-185`：恢复凭据为 email 可选模块。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:91-93`：仍描述“Server Intermediate CA”。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:204-207`：`swarm_get_server_trust` 输出仍包含 `root_ca_fingerprint` 与 `intermediate_ca_fingerprint`。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:346-350`：证书类型说明仍称由 server Intermediate CA 签发。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:374-382`：仍把 admin scope 写成额外的 `ClientAuthCertificate` 条目，实质上形成第三种证书 profile。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:279-318`：仍保留 passkey recovery 与 email bind 工具；但 design/auth.md 只裁定 email 可选恢复，未裁定 passkey 为目标状态。
- `/data/swarm/docs/specs/reference/api-registry.md:392-423`：Registry 仍把 device/recovery/federation 五个工具列入 Auth API active 口径。

问题描述：
Auth 设计文档已经把认证模型裁定为“应用层证书 + 单层 Server CA + 两种用途隔离证书 + email 可选恢复”。但机器源 `auth_api.idl.yaml` 和 Registry 仍混入旧模型：Intermediate CA、root/intermediate fingerprint、passkey recovery、admin certificate profile、device cap 数值等。由于 Auth 是跨 Gateway、MCP、Deploy、Engine 证书校验的公共控制面，这不是局部措辞问题，而是控制面边界定义不一致。

影响分析：
实现者无法判断：
- trust root API 应返回单个 `server_ca_fingerprint`，还是 root/intermediate 两级 fingerprint；
- admin 是普通 `ClientAuthCertificate + admin scope flag`，还是独立证书 profile；
- passkey 是否是目标状态的一部分；
- Auth API 的 active tool surface 是否应暴露 device/passkey/federation 工具。
这会导致 SDK codegen、Gateway certificate verifier、MCP auth tools 和文档设计相互分叉，后续很难通过 CI 校验修复。

修复建议：
以 `design/auth.md` 的目标模型为准，统一修订 `auth_api.idl.yaml` 与 Registry：
1. 删除 `Intermediate CA`、`Root/Intermediate fingerprint` 表述，统一为单个 `server_ca_fingerprint` / `server_ca_certificate`。
2. 将 admin 操作表述为 `ClientAuthCertificate` 的 `admin` scope，不作为第三种证书类型或重复证书条目。
3. 明确 passkey 是否为 D-item：若不是目标状态，移除 `swarm_passkey_register` 或标为非 active；若用户裁定保留，则同步写入 `design/auth.md` 的恢复模型。
4. 对 device/federation 工具逐项确定是否属于目标 Auth surface；不能让 design 说“两证书 + email 可选”，IDL 又 active 暴露更多未裁定恢复/联邦能力。

### F2 — Critical — API Registry 与 IDL/codegen 的“单事实源”关系自相矛盾，导致接口无法生成或校验

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:1-5`：声明 Registry 是 canonical schema authority，同时 IDL 是实现侧 codegen 输入。
- `/data/swarm/docs/specs/reference/codegen.md:7-9`：声明 IDL 是唯一机器源，Registry 全量由 codegen 生成。
- `/data/swarm/docs/specs/reference/api-registry.md:7`：Registry 标注 `game_api 0.5.0` / `auth_api 0.1.0`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:8`：game API IDL 实际为 `0.4.0`。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:13`：auth API IDL 实际为 `0.2.0`。
- `/data/swarm/docs/specs/reference/api-registry.md:463-474`：Registry 注册 7 个 host functions，包含 `host_get_fuel_remaining`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1576-1652`：IDL 声明 `total_functions: 6`，没有 `host_get_fuel_remaining`。
- `/data/swarm/docs/specs/reference/api-registry.md:740-778`：Registry 要求 JSON-RPC numeric `error.code = -32000`，业务原因在 `error.data.rejection_reason`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1828-1843`：IDL 仍写 `error.code: RejectionReason (string)`。
- `/data/swarm/docs/specs/reference/api-registry.md:872-895`：Registry 的 deploy 是同步提交 `deploy_payload`、`code_signature`、`certificate_id`、`version_counter`。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1041-1064` 与 `1885-1917`：IDL 的 deploy 仍是 `wasm_bytes` + async object-store upload 路径。

问题描述：
Registry、IDL、codegen.md 同时宣称自己或彼此是权威，但实际内容互相冲突。更严重的是冲突集中在 machine-readable API surface：版本号、host function 数量、错误 envelope、deploy 输入输出与持久化路径。这些字段是 SDK、MCP schema、Gateway routing、Replay verifier 的共同契约。

影响分析：
CI 若真实执行 codegen check，无法判断应以 Registry 覆盖 IDL，还是以 IDL 重新生成 Registry；SDK 生成器也会在错误 envelope、host import table、deploy 方法签名上产生不兼容客户端。最终风险是：文档看似有“单事实源”原则，实际却没有任何文件可作为稳定的 schema source。

修复建议：
先裁定单事实源层级，并让所有文档遵守同一个方向。推荐：
1. `*.idl.yaml` 为唯一机器源；`api-registry.md` 为生成产物与人工解释层。
2. 修改 `api-registry.md:1-5`，避免同时宣称 Registry 是 canonical schema authority 又由 IDL 生成；可改为“Registry 是由 IDL 生成的人类可读 canonical publication，冲突时修正 IDL 并重新生成”。
3. 统一版本号：game/auth/economy 在 IDL 与 Registry 头部必须一致。
4. 将 `host_get_fuel_remaining`、numeric JSON-RPC error envelope、同步 deploy_mutation 等已裁定目标写回 `game_api.idl.yaml`，或反向调整 Registry；不能保留双版本。
5. 删除或重写 Registry 末尾的手写 changelog 中与当前目标冲突的旧版本内容，避免读者误以为旧模型仍可实现。

### F3 — High — Deploy 数据流在 design/interface、Registry、game_api.idl.yaml 中分裂为同步提交与异步上传两套架构

文件引用：
- `/data/swarm/docs/design/interface.md:152-157`：`swarm_deploy` 语义为 `deploy_mutation`，同 `module_hash` 重试只扣费一次，依赖 redb `version_counter`。
- `/data/swarm/docs/specs/reference/api-registry.md:872-895`：Deploy 同步提交 `deploy_payload`、签名、证书、version counter，并在 redb 事务内验证和写 manifest。
- `/data/swarm/docs/specs/reference/api-registry.md:908-925`：同一 Registry 又把非 deploy 大对象描述为 async object store，但声明 deploy 不走本节异步路径。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1041-1064`：`swarm_deploy` 输入仍是 `wasm_bytes`，输出 `object_store_key`，说明“WASM blob is asynchronously uploaded”。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1885-1917`：Deploy 章节继续定义 async object-store upload 为 deploy flow step 2。

问题描述：
Deploy 是代码上线链路，必须同时满足签名验证、幂等、replay ordering、tick boundary 激活。当前文档把它同时描述为：
- 同步 redb deploy_mutation（Registry/interface）；
- 异步 blob upload + manifest pointer（game_api.idl.yaml）；
- 非 deploy 大对象可异步（Registry §12）。
这三者未形成清晰的状态机边界。

影响分析：
实现者无法确定 deploy 是否在 `swarm_deploy` 返回前已经完成 payload 可用性验证；也无法确定 `deploy_id` 是 client-generated 还是 server-generated、`object_store_key` 是否属于 public API、`redb_version_counter_predicted` 是否仍需要签入 payload。Replay verifier 和 code signing verifier 会因此产生不同实现。

修复建议：
以同步 deploy_mutation 为目标状态重写 IDL：
1. `swarm_deploy` 输入改为 `deploy_payload + code_signature + certificate_id + version_counter + metadata`，与 Registry 对齐。
2. `object_store_key` 不应作为 deploy 成功的核心输出，除非明确它只是服务端内部/诊断字段。
3. 将 async object-store upload 限定为 replay recording、snapshot archive、RichTraceBlob 等非 deploy 大对象；不要在 deploy flow 中复用。
4. 明确 `deploy_id` 生成方与幂等键：若 `idempotency_key = module_hash`，则部署状态机中不应再要求不可预测的 server-generated deploy_id 参与客户端签名。

### F4 — High — Host Function 与 MCP Tool 边界混淆，API surface 对调用者不直观

文件引用：
- `/data/swarm/docs/design/interface.md:68-88`：Host functions 是 WASM 内只读 import。
- `/data/swarm/docs/specs/reference/api-registry.md:314-315`：`swarm_get_terrain`、`swarm_get_path` 被列在 MCP Play 工具中，但 rate limit 标为“host fn only”。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:843-873`：IDL 同样把 `swarm_get_terrain`、`swarm_get_path` 放入 `mcp_tools.tools`，但 `rate_limit_key: host_only`。
- `/data/swarm/docs/specs/reference/host-functions.md:9-20`：Host import 另有 `host_get_terrain`、`host_path_find`。
- `/data/swarm/docs/specs/reference/mcp-tools.md:58-64`：MCP 文档把世界查看称为 MCP 查询入口，同时说 snapshot 与 WASM 输入相同。

问题描述：
文档试图用同一个 Registry 覆盖 MCP tools 和 WASM host imports，但 `swarm_get_terrain` / `swarm_get_path` 这种命名出现在 MCP tool 表里，又标注 host-only，形成“看起来是 MCP 工具、实际不可作为 MCP 工具调用”的混合语义。MCP 是 AI agent 的操作界面；host function 是玩家 WASM 的 ABI import，二者调用主体、鉴权方式、预算、错误模型都不同。

影响分析：
SDK/codegen 很容易错误地把 host-only 条目暴露成 MCP client 方法，或者把 MCP rate limit 和 WASM host budget 混在一起。对 AI agent 来说，`swarm_get_path` 是否可通过 MCP 调用不直观；对 WASM SDK 来说，`host_path_find` 与 MCP `swarm_get_path` 是否共享 visibility 和 budget 也不清晰。

修复建议：
在 Registry 层拆成两个并列 namespace：
1. `mcp_tools` 只包含可通过 MCP/HTTP 调用的工具，不放 host-only placeholder。
2. `host_functions` 只包含 WASM import ABI。
3. 若确实需要 MCP 路径查询工具，应命名、rate limit、visibility、错误 envelope 独立定义，不使用 `host_only` 伪字段。
4. `mcp-tools.md` 与 `host-functions.md` 引用同一 visibility/fair-share 原则即可，不要共享同一工具行。

### F5 — High — Recycle 指令语义在 reference 文档与 IDL/Registry 中冲突

文件引用：
- `/data/swarm/docs/specs/reference/api-registry.md:60`：Recycle 是 `object_id` self-action。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:155-162`：Recycle 描述为“self-action — no spawn proximity required”。
- `/data/swarm/docs/specs/reference/commands.md:90-96`：Recycle 示例下仍写“校验：drone 在 Spawn 1 格内”。
- `/data/swarm/docs/design/engine.md:331`：Recycle 命令走标准 death_mark → death_cleanup 路径，但未说明是否需要 Spawn proximity。

问题描述：
同一玩家可见 API 对 Recycle 的空间约束给出相反语义：IDL 明确不要求 spawn proximity，commands.md 要求在 Spawn 1 格内。Recycle 影响资源回收、死亡路径、room cap 释放和玩家策略，属于基础 CommandAction，不应存在双版本。

影响分析：
玩家 SDK、教程示例、服务端校验和 replay 可能分叉：客户端以为任意位置可回收，服务端按 Spawn 邻接拒绝；或反之。该类冲突会直接破坏 API 直觉性和 deterministic command validation 的可预期性。

修复建议：
裁定 Recycle 的最终空间约束，并统一三处：
1. 若保持“无需 Spawn 邻接”，删除 commands.md 的 Spawn 1 格校验，并在 engine.md Recycle death path 中补一句“self-action，无位置约束”。
2. 若恢复 Spawn 邻接，则修改 IDL 与 Registry，明确 `target_spawn_id` 或 proximity validation，避免只有 `object_id` 的 self-action 隐含外部目标。

### F6 — Medium — 目标状态文档仍保留 Phase/future/deferred/changelog/date 等历史/分期噪声

文件引用：
- `/data/swarm/docs/design/README.md:58`：明确禁止 future/deferred/Phase/版本分期。
- `/data/swarm/docs/design/engine.md:235`：写有“未来可通过模组扩展”。
- `/data/swarm/docs/design/engine.md:322`：写有“playtest 阶段可能被挑战”。
- `/data/swarm/docs/design/engine.md:506`：写有“SIMD deterministic subset deferred”。
- `/data/swarm/docs/specs/reference/api-registry.md:964-975`：保留按日期和版本的变更记录。
- `/data/swarm/docs/specs/reference/auth_api.idl.yaml:810-826` 与 `/data/swarm/docs/specs/reference/economy.idl.yaml:513-529`：IDL 内保留日期化 changelog。
- `/data/swarm/docs/specs/reference/game_api.idl.yaml:1518-1535`：`rfc_tools` 描述含 future / not active / do not emit 等分期语义。

问题描述：
项目规范要求 design/spec/reference 都呈现目标状态，而不是阶段路线图或历史日志。当前多个被评审文档仍有 future/deferred/阶段/changelog/date/RFC-not-active 等文本。这些不只是文字风格问题：它们让读者无法区分“已裁定目标状态”与“暂存占位”。

影响分析：
评审和实现会继续围绕“当前不实现 / future / RFC-gated”做阶段性解释，违背“设计即终态”。特别是 API Registry/IDL 的 changelog 与旧模型残留混在一起时，会把已经废弃的 bearer token、Intermediate CA、async deploy 等内容重新带入实现判断。

修复建议：
1. 从 design/spec/reference 中移除日期化 changelog；历史交给 git。
2. 将 RFC/future 工具从 active schema 中移除，或作为独立 RFC 文档，不进入目标 API Registry active/all_declared 口径。
3. 将 `deferred`、`future`、`阶段` 等词改成明确裁定：要么是目标状态，要么不在当前设计中。
4. playtest-gated 数值应只描述“数值校准依赖实证数据”的条件，不写阶段化路线。

### F7 — Medium — Mod 发布/运行模型存在“动态安装”与“静态编译进 Engine”之间的抽象断裂

文件引用：
- `/data/swarm/docs/design/engine.md:11`：Mod 是 Bevy Plugin，静态编译进 Engine 二进制，是唯一扩展机制。
- `/data/swarm/docs/design/engine.md:51-68`：安装流程写 `swarm mod add` 解包到 `~/.swarm/mods/`，然后通过 Cargo features 编译引入。
- `/data/swarm/docs/design/engine.md:70-77`：升级/降级/禁用表写“下一 tick 新版本生效 / 旧版本立即恢复 / tick 不再调用 Plugin”。
- `/data/swarm/docs/design/architecture.md:268-275`：Rhai 被 Bevy Plugin 静态编译替代。
- `/data/swarm/docs/design/tech-choices.md:48-80`：强调单一扩展机制、原生编译、静态引入。

问题描述：
设计同时想表达：
- Mod 是 Rust crate + Cargo feature 静态编译进 Engine；
- 服主可 `swarm mod upgrade/downgrade/disable`，下一 tick 或立即生效。
这两者需要一个明确的“重编译/重启/热切换”边界。目前文档没有说明禁用已静态注册的 Bevy Plugin 是 runtime config gating，还是重新构建二进制；升级下一 tick 生效更像动态插件系统，与“静态编译进 Engine”不直观一致。

影响分析：
实现者会在插件系统上做出不同抽象：一种是纯静态 binary + world.toml gating；另一种是运行时动态装载/卸载。两者在安全、确定性、发布流程、replay `mods_lock_hash` 上完全不同。若不澄清，会导致 mod lifecycle 与 tick determinism 的边界模糊。

修复建议：
明确 Mod 生命周期的目标语义：
1. 若坚持静态编译：`swarm mod add/upgrade/remove` 只改变本地源码/lockfile；生效需要 rebuild + Engine restart，tick boundary 只是在重启后选择启用配置。
2. 若要求 tick 级热升级：需要设计动态 plugin ABI、loaded module isolation、state migration、replay lock；这与当前“静态编译唯一机制”冲突，必须重新裁定。
3. 禁用应表述为 world.toml gating + system no-op，还是二进制移除；二者择一。

## 3. 亮点

- COLLECT / EXECUTE 两层计算模型非常清晰：`design/architecture.md:15-25` 与 `design/architecture.md:126-178` 把可水平扩展的玩家 WASM 执行和必须确定性串行的权威模拟分开，符合项目目标，避免把所有组件过度分布式化。
- per-shard single writer + redb 的权威点定义明确：`design/architecture.md:206-219`、`design/architecture.md:278-287` 把 Engine、redb、NATS、Gateway 的权威性边界讲清楚，有助于降低系统耦合。
- MCP 不做游戏动作的原则正确且直观：`design/interface.md:47-50` 与 `specs/reference/mcp-tools.md:112-117` 保证 AI agent 与人类玩家同走 WASM 策略路径，避免 MCP 成为特权操作面。
- CommandAction + ActionRegistry 的抽象方向合理：`api-registry.md:37-84` 将基础命令和 combat/effect action 解耦，给 mod 扩展留下稳定边界，同时保持 CommandAction enum 小而稳定。
- fixed-point 类型注册表是跨平台确定性的好设计：`api-registry.md:20-34` 与 `economy.idl.yaml:13-45` 明确移除 f64，避免 replay 因浮点差异漂移。
- `special-attack-table.md` 作为 vanilla ActionRegistry 的 canonical table 很有价值：字段完整，能直接服务校验矩阵、SDK 文档和 gameplay 描述。

## 4. CrossCheck — 需要跨方向检查

- CX1: Auth API 的 passkey/device/federation 工具是否属于目标状态仍未裁定 → 建议 安全方向 检查 Auth 控制面最小暴露面、证书用途隔离与恢复路径是否一致。
- CX2: deploy 同步提交 vs async object store 的最终状态需要与 persistence-contract 对齐 → 建议 核心引擎/持久化方向 检查 redb replay-critical subset、blob manifest、deploy activation tick boundary 的一致性。
- CX3: MCP tools 与 WASM host functions 的 namespace 分离需要进一步验证 → 建议 API/SDK 方向 检查 codegen 是否会把 host-only 条目错误暴露为 MCP client method。
- CX4: Mod 静态编译与 tick 级 upgrade/disable 语义冲突 → 建议 引擎架构方向 检查 Bevy Plugin lifecycle、world.toml gating、mods_lock_hash 与 replay determinism。
- CX5: Recycle 空间约束会影响经济回收与死亡路径 → 建议 Gameplay/Engine 方向 检查 Recycle validation、refund formula、death_mark/room cap 释放是否形成单一语义。
- CX6: 目标状态文档中的 changelog/RFC/future/deferred 残留较多 → 建议 文档规范方向 检查 design/spec/reference 是否全部移除历史追踪与分期措辞，只保留目标状态。
