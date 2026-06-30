# R41 Phase 1 Clean-Slate 独立评审 — Cross-Cutting

## 1. Verdict

REQUEST_MAJOR_CHANGES

当前文档集存在多处跨文档事实源冲突，尤其是扩展机制（Rhai RuleMod vs Bevy Plugin 静态编译）、基础设施组件（Dragonfly/ClickHouse 是否存在）、认证证书类型（2 类 vs 4 类）与 API/IDL 链接完整性。这些不是文字润色问题，而是会直接导致实现者无法判断目标架构的阻塞级不一致。建议先统一“单一事实源”与术语边界，再进入下一轮评审。

## 2. 发现的问题

### C1 — Critical — 扩展机制在设计与 spec/reference 中互相否定

文件引用：
- `/tmp/swarm-review-R41/design/engine.md:11`
- `/tmp/swarm-review-R41/design/tech-choices.md:48-51`
- `/tmp/swarm-review-R41/specs/core/07-world-rules.md:7-15`
- `/tmp/swarm-review-R41/specs/core/07-world-rules.md:312-392`
- `/tmp/swarm-review-R41/specs/reference/rhai-mod-abi.md:1-4`

问题描述：
`engine.md` 明确写“Mod = Bevy Plugin，静态编译进 Engine 二进制。这是唯一的扩展机制——没有 Rhai 脚本层”；`tech-choices.md` 也写“Rhai 已被移除——Bevy Plugin trait 是唯一的扩展机制”。但 `specs/core/07-world-rules.md` 仍把规则模组定义为“可安装的 Rhai 脚本 + 声明式配置”，并大篇幅定义 RhaiActionBuffer、Rhai hook、Rhai 签名、Direct ECS writer。`specs/reference/rhai-mod-abi.md` 还声明自身是 Rhai RuleMod 的“权威合同”。

影响分析：
这是跨文档最严重的架构分叉。实现者无法判断：
- Mod 是否需要运行 Rhai engine；
- `.swarm-mod` 是 Rust crate / Bevy Plugin，还是 tar.gz + `.rhai` 脚本；
- world.toml 的 `[[mods]]` 是编译期 feature 选择，还是运行期脚本安装；
- RuleMod ABI 是否仍需实现。

该冲突会污染 Engine、world rules、mod packaging、CI gate、TickTrace replay 边界和安全模型，必须阻塞。

修复建议：
裁定一个唯一扩展模型，并同步删除或改写另一套体系：
- 若目标是 Bevy Plugin 静态编译：删除/归档 Rhai RuleMod ABI，重写 `07-world-rules.md` 为 Rust Plugin + manifest/action registry 合同，并移除 `.rhai`、AST budget、RhaiActionBuffer、`swarm mod pack` 的 Rhai 语义。
- 若目标是 Rhai RuleMod：回改 `engine.md` 与 `tech-choices.md`，不要声称 Rhai 已移除，且需要解释 Rhai 与 Bevy Plugin 的分层边界。

---

### C2 — High — README 架构图仍保留已移除的数据层组件

文件引用：
- `/tmp/swarm-review-R41/design/README.md:131-136`
- `/tmp/swarm-review-R41/design/README.md:170-175`
- `/tmp/swarm-review-R41/design/tech-choices.md:134-153`

问题描述：
`README.md` 架构图和数据模型仍列出 `Dragonfly` 作为热缓存、`ClickHouse` 作为分析/审计数据层；但 `tech-choices.md` 明确写 `Dragonfly 已被移除`，由 Engine 进程内 Moka Cache 替代；`ClickHouse 已被移除`，由 redb metrics table + Gateway 聚合替代。

影响分析：
这会让整体架构图误导实现者和部署者：
- 是否需要部署 Dragonfly/ClickHouse；
- Gateway 查询是走外部缓存/OLAP，还是 fan-out 到 Engine；
- 运维依赖面与故障面不同。

修复建议：
将 `design/README.md` 的系统架构图与数据模型更新为：
- redb：世界状态、TickCommitRecord、metrics table；
- Engine 进程内 Moka Cache：热读缓存；
- Object Store / append-only log：RichTraceBlob/keyframe 大对象（若仍为目标设计）；
- Gateway fan-out 聚合代替 ClickHouse。
并删除 Dragonfly/ClickHouse 的存储位置表项，或标为“已移除”而非当前架构。

---

### C3 — High — Gateway 语言/边界在 README 与 Auth 设计中不一致

文件引用：
- `/tmp/swarm-review-R41/design/README.md:82-87`
- `/tmp/swarm-review-R41/design/README.md:154`
- `/tmp/swarm-review-R41/design/auth.md:51-57`
- `/tmp/swarm-review-R41/design/auth.md:90-97`

问题描述：
`README.md` 将 Gateway 定义为 `网关 (Go)`，仓库结构中也写 `gateway/ # Go API 网关`；但 `auth.md` 架构图写 `Gateway (Rust)`，并描述 Certificate Auth handler、CSR submit、renew 等位于该 Gateway。

影响分析：
Gateway 是跨 Auth、MCP、WebSocket、REST/gRPC 的边界组件。语言与职责不一致会影响：
- 证书校验库与 Ed25519/CSR 实现归属；
- Gateway 与 Engine 的接口边界；
- repo/module 划分；
- 安全审计范围。

修复建议：
统一 Gateway 的语言与职责。如果 Gateway 目标仍是 Go，则 `auth.md` 应写 Go Gateway + 独立 Auth Service/Domain 的语言与接口边界；如果 Auth 控制面已迁移 Rust，则 README 仓库结构与架构图也应同步。

---

### C4 — High — 认证证书类型与恢复路径在 auth.md、tech-choices、API Registry 中冲突

文件引用：
- `/tmp/swarm-review-R41/design/auth.md:31-33`
- `/tmp/swarm-review-R41/design/auth.md:120-125`
- `/tmp/swarm-review-R41/design/auth.md:181-186`
- `/tmp/swarm-review-R41/design/auth.md:220-228`
- `/tmp/swarm-review-R41/design/tech-choices.md:207-208`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:417-425`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:636-653`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:786-793`

问题描述：
`auth.md` 与 `tech-choices.md` 声称仅有两种证书：`ClientAuthCertificate` 与 `CodeSigningCertificate`；Admin 操作只是 ClientAuth + admin scope flag，Federation 不需要独立证书类型；强制 passkey/admin 恢复被移除，email 为可选恢复。可是 API Registry 仍定义：
- `AdminCertificate` 与 `FederationCertificate` 两种额外证书类型；
- Auth 限制中有 AdminCertificate/FederationCertificate TTL；
- `swarm_passkey_register`、`swarm_recovery_email_bind`、`swarm_federation_identity` 等工具。

影响分析：
该冲突会导致 Auth API、证书 envelope、scope/audience、MCP auth category 与实现模型不一致。尤其是 Admin/Federation 是否为证书类型会影响 certificate parser、audience 校验、renew/revoke、TickTrace auth events。

修复建议：
以用户权威裁决为准统一：
- 若“仅两种证书类型”是目标设计：API Registry §9、§5.8 与 auth_api 生成内容必须删除 AdminCertificate/FederationCertificate 类型，Admin/Federation 改为 ClientAuth scopes / identity mapping；passkey 若仅可选 bootstrap，应在 `auth.md` 中明确其工具是否保留、是否 active。
- 若 API Registry 是目标：`auth.md` 必须撤回“仅有两种证书类型”和“Federation 不需要独立证书类型”的表述。

---

### C5 — High — API Registry 自称由 IDL 生成，但任务允许的 reference 目录中缺失 IDL 源文件

文件引用：
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:1-9`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:983-1013`
- `/tmp/swarm-review-R41/specs/reference/codegen.md:7-18`
- `/tmp/swarm-review-R41/specs/reference/codegen.md:36-52`

问题描述：
API Registry 声称由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 自动生成，且冲突时以 IDL YAML 为准；Codegen 文档也把这些 IDL 文件定义为唯一机器源。但本次审阅的 `/tmp/swarm-review-R41/specs/reference/` 目录只包含 7 个 Markdown 文件，未包含任何 `.idl.yaml`。因此“权威源”在评审输入中不可见，Registry 生成链不可验证。

影响分析：
Cross-Cutting 评审无法验证“IDL ↔ registry 一致性”这一任务明确关注点。更重要的是，若设计包对实现者也只暴露 Registry 而不暴露 IDL，则 SDK/codegen/CI 的单事实源合同不可实施。

修复建议：
将 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 纳入 `specs/reference/` 并作为评审/实现输入；或修改文档，不再声称缺失文件是权威源。CI 命令中的路径也应与实际目录一致。

---

### C6 — Medium — 多个 design 文档中的相对链接从当前位置解析会失效

文件引用：
- `/tmp/swarm-review-R41/design/interface.md:9`
- `/tmp/swarm-review-R41/design/interface.md:29`
- `/tmp/swarm-review-R41/design/interface.md:86`
- `/tmp/swarm-review-R41/design/interface.md:115`
- `/tmp/swarm-review-R41/design/tech-choices.md:3`
- `/tmp/swarm-review-R41/design/tech-choices.md:28`
- `/tmp/swarm-review-R41/design/tech-choices.md:92`

问题描述：
`design/interface.md` 中多处链接写为 `specs/reference/api-registry.md`、`specs/reference/auth_api.idl.yaml`，从 `design/` 目录解析会指向 `design/specs/...`，实际应为 `../specs/reference/...`。`design/tech-choices.md` 同样将 core/security specs 链接写成 `specs/core/...`，从 `design/` 下解析会失效。

影响分析：
这直接破坏跨文档引用完整性，尤其是 interface/tech-choices 都依赖 Registry 与 core specs 作为权威来源。链接失效会让读者无法跳转到单事实源，也会影响 docs lint / markdown link check。

修复建议：
统一修正 design 目录下所有到 specs 的链接为 `../specs/...`。建议加入 CI markdown-link-check，至少覆盖 design 与 specs/reference 的相对链接。

---

### C7 — Medium — special attack 数量与表格内容不一致

文件引用：
- `/tmp/swarm-review-R41/specs/reference/special-attack-table.md:8-10`
- `/tmp/swarm-review-R41/specs/reference/special-attack-table.md:14-26`
- `/tmp/swarm-review-R41/specs/core/07-world-rules.md:1130-1142`
- `/tmp/swarm-review-R41/specs/core/07-world-rules.md:961-1030`

问题描述：
`special-attack-table.md` 明确 Vanilla ActionRegistry 包含 11 个内置动作：3 个 basic_combat + 8 个 special_attack，并列出 Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate。`07-world-rules.md` 的 `[[custom_actions]]` 示例也列出 8 个特殊攻击，但 §7.8 “特殊攻击方式”汇总表只列出 6 个，缺少 Leech 与 Fabricate。

影响分析：
这会导致 gameplay/world rules 层对“vanilla 默认启用哪些特殊攻击”理解不一致，影响 action allowlist、balance 表、SDK 帮助文档和测试用例。

修复建议：
`07-world-rules.md` §7.8 不应重新维护不完整表格；改为引用 `specs/reference/special-attack-table.md`，或补全 Leech/Fabricate 并标注该表为派生摘要、非权威。

---

### C8 — Medium — Controller repair cap 规则互相冲突

文件引用：
- `/tmp/swarm-review-R41/design/engine.md:452-463`
- `/tmp/swarm-review-R41/specs/core/07-world-rules.md:828-848`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:561-563`

问题描述：
`engine.md` 明确写“移除全局 repair cap”，维修仅受 `repair_range`、`repair_capacity` 和物理分布限制。API Registry 全局容量限制也写“无全局 repair cap”。但 `07-world-rules.md` §7.3 仍保留“多个 Controller 的总 age 回退量不超过每 tick 自然增长的 50%”的维修硬上限。

影响分析：
这影响 drone 生命周期、Controller 升级收益、维修系统实现与经济平衡。实现者无法判断是否需要跨 Controller 汇总 age 回退量，这属于系统级状态聚合，和“物理约束足够”的设计边界完全不同。

修复建议：
删除 `07-world-rules.md` 的 50% 全局 repair cap，改为引用 `engine.md` 的物理约束规则与 Registry 的权威容量限制；或若 50% cap 被重新裁决为目标设计，则必须同步改写 `engine.md` 与 Registry。

---

### C9 — Medium — Host function `host_get_random` 成本在 Registry 与派生参考中不一致

文件引用：
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:502-512`
- `/tmp/swarm-review-R41/specs/reference/host-functions.md:62-70`

问题描述：
Registry §4.4 定义 `host_get_random` fuel 成本为 `200 + 10/32 bytes`；`host-functions.md` 则写 `100 base + 1 per output byte`。两者都看起来像实现级成本合同。

影响分析：
Host function fuel 是 replay/fairness 关键边界。若 SDK、测试、实现分别参考不同文档，会导致 quota 估算、TickTrace host_cost_table_version 与 replay 对账不一致。

修复建议：
以 API Registry 为权威，`host-functions.md` 删除具体成本或改成完全引用 Registry §4.4；若保留派生表，必须由 codegen 同步生成。

---

### C10 — Medium — MCP/auth 文档残留 Intermediate/Root CA 旧术语

文件引用：
- `/tmp/swarm-review-R41/design/auth.md:29-31`
- `/tmp/swarm-review-R41/design/auth.md:104-115`
- `/tmp/swarm-review-R41/specs/reference/mcp-tools.md:84-93`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:797-799`
- `/tmp/swarm-review-R41/specs/reference/api-registry.md:413`

问题描述：
`auth.md` 明确采用单层 Server CA，不分 Root/Intermediate，且 Server CA 不进系统/browser trust store。但 `mcp-tools.md` 仍描述“Server Intermediate CA signs application-layer certificates”“pin 服务器 Root CA fingerprint”；API Registry 中 `Swarm-Certificate-Chain` 示例仍写 `leaf + intermediate`，`swarm_get_server_trust` 返回字段仍为 `root_ca_fingerprint, intermediate_ca_fingerprint`。

影响分析：
这会导致证书链编码、trust pinning UI、server trust API 与 CA 运维模型不一致。尤其 API 字段名含 root/intermediate 会固化旧模型，不只是文档术语问题。

修复建议：
统一术语为单层 `server_ca_fingerprint` / `server_ca_certificate`。若出于兼容保留字段，需在 Registry 中明确 deprecation 与固定空值语义；否则应从 auth_api IDL 删除 root/intermediate 字段。

---

### C11 — Low — README 仍引用未授权本轮评审且可能不存在的 design 文档，导航完整性无法验证

文件引用：
- `/tmp/swarm-review-R41/design/README.md:11-19`

问题描述：
README 导航列出 `design/gameplay.md`、`design/modes.md`、`RUNBOOK.md`、`AGENTS.md` 等，但本任务明确禁止读取未列出的文件，因此本轮无法验证这些链接与内容是否存在/一致。仅从 Cross-Cutting 视角看，README 对整体设计入口的完整性依赖这些文件。

影响分析：
不是阻塞问题，但 Speaker/后续审查应确保导航中的所有文件在干净设计包中存在且链接可解析。

修复建议：
在后续允许范围内运行 docs link checker；若文件不在当前设计包，应从 README 导航移除或改为明确外部根目录引用。

## 3. 亮点

1. API Registry 的“单一事实源”意图清晰：`api-registry.md:11-17` 明确声明 IDL 生成、机器可读优先、版本化和 CI gate；`codegen.md:5-18` 也定义了 IDL → Registry/SDK 的生成链。这是正确方向。

2. CommandAction 与 ActionRegistry 分层设计较清楚：`api-registry.md:37-85` 将基础命令与 combat/effect action dispatch 分离，`special-attack-table.md:1-10` 为 vanilla action 建立 canonical 表，有利于减少 enum 爆炸和 mod 扩展冲突。

3. `engine.md` 对 Tick 生命周期、Phase 2a/2b、Action dispatch 与 combat/status pipeline 的职责分离描述深入，尤其 `engine.md:250-262` 将 HP 变更统一推迟到 Phase 2b，避免同 tick action 顺序导致 HP 结果差异，架构边界合理。

4. 确定性约束覆盖面较好：`engine.md:270-276` 明确 PRNG、ECS system 顺序、确定性数据结构；`api-registry.md:658-688` 将 TickTrace Envelope 扩展到 22 个 replay 关键字段，有助于审计和回放闭合。

5. 应用层证书“不进系统 trust store”的安全边界在 `auth.md:112-115` 表达明确，符合自托管/内网部署目标，也符合用户此前的 Swarm 认证偏好。

## 4. CrossCheck — 需要跨方向检查

CX-1: Rhai RuleMod 与 Bevy Plugin 二选一后，安全边界会完全不同 → 建议 Security 检查模组签名、capability gate、direct ECS writer 是否仍成立。

CX-2: Dragonfly/ClickHouse 移除后，查询/分析路径依赖 Engine Moka Cache + Gateway fan-out → 建议 Performance/Operations 检查跨 shard 聚合延迟、缓存一致性和故障降级。

CX-3: Auth 证书类型从 4 类收敛到 2 类会影响 admin/federation scope 语义 → 建议 Security/Auth 检查 audience、scope、renew/revoke、nonce window 与 federation identity flow。

CX-4: API Registry 缺失 IDL 源导致 codegen 不可验证 → 建议 Tooling/CI 检查 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 是否应纳入评审包，以及 `generate_api_registry.py` / `hermes codegen` 命令是否实际存在。

CX-5: `host_get_random` fuel 成本不一致可能影响 replay 与公平计费 → 建议 Determinism/Runtime 检查 host_cost_table_version、fuel_schedule_version 与 TickTrace 对账规则。

CX-6: Controller repair cap 冲突会改变生命周期与经济平衡 → 建议 Gameplay/Economy 检查 drone aging、Controller repair、Depot repair 与 upkeep 是否形成可滥用闭环。

CX-7: 特殊攻击表在 world rules 中缺 Leech/Fabricate → 建议 Gameplay 检查 Standard/Arena/Tutorial action allowlist 与 11 vanilla action 是否一致。

CX-8: MCP 工具中 `swarm_get_messages` 仍 active，而 `commands.md` 标注 `SendMessage` 为 Out-of-Scope RFC → 建议 Interface/API 检查消息系统是只读历史机制、系统事件，还是遗留 drone 间通信接口。
