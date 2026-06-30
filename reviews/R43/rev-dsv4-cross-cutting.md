# R43 跨领域独立评审 — rev-dsv4-cross-cutting

> **评审员**: Architect Reviewer (DeepSeek V4 Pro)
> **视角**: 跨领域一致性 — 认证/引擎/接口/架构/经济/指令系统 6 域对齐
> **评审范围**: 15 个指定文件（design 6 + reference 9）

---

## 1. Verdict

**REQUEST_MAJOR_CHANGES**

存在 4 个 Critical 级跨域不一致——认证 CA 层数矛盾、RejectionReason 编号/auth 码对齐断裂、Recycle 校验规则二义、Swarm-Cert-Id 头字段三文档分歧。这些问题需要在合并设计文档前修正，否则实现侧将面临不可调和的冲突指令。

---

## 2. 发现的问题

### 2.1 Critical

#### C1: auth_api.idl.yaml 使用 "Intermediate CA" vs design/auth.md 声明单层 CA

- **文件**: `design/auth.md` §4.1 vs `specs/reference/auth_api.idl.yaml` §1.2(swarm_submit_csr), §3(certificate_types), §1.7(swarm_get_server_trust)
- **描述**: `design/auth.md` §4.1 明确声明："不分 Root/Intermediate 层级……单层 Server CA 密钥对直接签发证书"。但 `auth_api.idl.yaml` 在多处引用 "Intermediate CA"：
  - §1.2 `swarm_submit_csr` description: "Server Intermediate CA"
  - §3 `certificate_types` description: "signed by the server's Intermediate CA"
  - §1.7 `swarm_get_server_trust` output_schema 包含 `intermediate_ca_fingerprint` 字段
- **影响**: 实现侧从 YAML IDL 生成代码将产生 Intermediate CA 逻辑（双层证书链验证），与 design 的单层模型冲突。这会导致证书验证路径不同、CA 密钥管理方案不同，直接破坏认证系统的可实施性。
- **建议**: 三处必须统一。若 design/auth.md 的"单层"判决为终态，则 auth_api.idl.yaml 需：(a) 将所有 "Intermediate CA" 替换为 "Server CA"；(b) `swarm_get_server_trust` output_schema 移除 `intermediate_ca_fingerprint` 只保留 `root_ca_fingerprint`（或重命名为 `server_ca_fingerprint`）；(c) 变更日志补充说明。此决策需用户确认方向——确认后由 **architect** 或 **design-economy** 方向执行统一修改。

#### C2: RejectionReason 48-code 计数与名称集在两个事实源间断裂

- **文件**: `specs/reference/api-registry.md` §2 vs `specs/reference/game_api.idl.yaml` §2 vs `specs/reference/auth_api.idl.yaml` §5
- **描述**:
  - `api-registry.md` §2 声明总数 48，其中 §2.5 声称 "11 canonical codes" 但表格中仅列出 10 个（#39–#48）。
  - `game_api.idl.yaml` §2 声明 `total_canonical_codes: 35`（不含 auth 码）。
  - `auth_api.idl.yaml` §5 声明 `total_canonical_codes: 12` 使用 namespace_offset 1000（codes 1001–1012）。12 + 35 = 47 ≠ 48。
  - **名称冲突**：`api-registry.md` §2.5 Auth 码中包含 `RefreshTokenInvalid`(#42) 和 `TokenRevoked`(#44)——这些是 bearer token 模型遗留码，与 R33 B4 证书链重写不兼容。`auth_api.idl.yaml` §5 定义了 12 个证书链原生码（`CertRevoked`, `InvalidCSR`, `DeviceLimitReached`, `CertificateLimitReached`），其中有 4 个在 `api-registry.md` 的 10 个 auth 码中完全不存在。
- **影响**: RejectionReason 是跨 Engine/Gateway/Auth/MCP 的 wire contract。两个 IDL 源的码集不一致意味着：(a) 48 总数可能是算术错误或合并遗漏；(b) token-era 遗留码（RefreshTokenInvalid, TokenRevoked）如被 codegen 生成，会污染证书链模型；(c) auth_api.idl.yaml 独有的码（CertRevoked, InvalidCSR, DeviceLimitReached, CertificateLimitReached）若未进入 registry 表格，CI gate 无法检测缺失。
- **建议**: 由 **codegen** 方向重新执行 IDL → registry 生成，逐字段比较两 IDL 的 RejectionReason 变体，确认 48 的正确构成。`RefreshTokenInvalid` 和 `TokenRevoked` 应移除或标记 deprecated，auth_api.idl.yaml 的 12 码应完整映射到 registry。参见 CrossCheck CX1。

#### C3: Recycle 命令校验规则 — commands.md 与 game_api.idl.yaml 直接矛盾

- **文件**: `specs/reference/commands.md` line 95 vs `specs/reference/game_api.idl.yaml` §1 Recycle variant
- **描述**:
  - `commands.md` line 95: "校验：drone 在 **Spawn 1 格内**"
  - `game_api.idl.yaml` line 157–162: "Recycle own drone (**self-action — no spawn proximity required**) / 参数仅 `object_id`"
  - `design/engine.md` §3.2: 只说 Recycle 走 death_mark → death_cleanup，未提及 proximity
- **影响**: 实现侧从 commands.md 和 game_api.idl.yaml 收到相反指令——一个要求 proximity check，一个明确无 proximity required。这是不可调和的矛盾，会直接导致实现阻塞。
- **建议**: 以 game_api.idl.yaml 为准（它直接描述 CommandAction schema），commands.md 的校验描述必须同步修正。由 **gameplay** 方向确认 Recycle 的最终校验规则。

#### C4: Canonical Request Signature 头字段 — api-registry.md 丢失 Swarm-Cert-Id

- **文件**: `design/auth.md` §7 vs `specs/reference/auth_api.idl.yaml` §4 vs `specs/reference/api-registry.md` §9
- **描述**:
  - `design/auth.md` §7 列出 5 个 headers: `Swarm-Certificate`, `Swarm-Cert-Id`, `Swarm-Timestamp`, `Swarm-Nonce`, `Swarm-Signature`
  - `auth_api.idl.yaml` §4 列出同样 5 个 headers
  - `api-registry.md` §9 仅列出 4 个 headers：`Swarm-Certificate`, `Swarm-Timestamp`, `Swarm-Nonce`, `Swarm-Signature`——**缺 Swarm-Cert-Id**
  - `api-registry.md` §9 追加声明: "certificate_id is read from the certificate body, not from a request header"
- **影响**: 三文档两派——design + auth IDL 说 header 中有 `Swarm-Cert-Id`，api-registry 说 cert_id 从 certificate body 读而非 header。客户端实现者依据不同文档会构造不同的请求格式，Gateway 验证逻辑会因此产生二义性。
- **建议**: 裁定单一事实。若保持 header（design/auth_idl 方向），api-registry.md 需补回头字段并移除矛盾文本。若去除 header（api-registry 方向），design 和 auth_idl 需同步修改。此决策需用户确认——确认后由 **architect** 方向执行统一修改。

### 2.2 High

#### H1: auth_api.idl.yaml replay_class 值 `non_idempotent_mutation` 未在 api-registry.md §13 注册

- **文件**: `specs/reference/auth_api.idl.yaml` §8 vs `specs/reference/api-registry.md` §13
- **描述**: `auth_api.idl.yaml` security_columns 中 `replay_class` 包含 `non_idempotent_mutation`（用于 swarm_submit_csr）。`api-registry.md` §13 Security Columns Reference 中 canonical values 列表为 `non_replayable, read_replay_safe, idempotent_mutation, admin_critical, deploy_mutation`——缺少 `non_idempotent_mutation`。
- **影响**: SDK codegen 从 IDL 产生的 tool stub 使用 `non_idempotent_mutation` replay class，但 registry 未注册此值，CI diff check 可能出现 false positive 或忽略缺失。
- **建议**: 将 `non_idempotent_mutation` 补入 api-registry.md §13 canonical values。

#### H2: design/auth.md §4.2 与 auth_api.idl.yaml §3 certificate_types 中 Admin 证书的表示不一致

- **文件**: `design/auth.md` §4.2 vs `specs/reference/auth_api.idl.yaml` §3
- **描述**: `design/auth.md` §4.2 说 "Admin 操作 = ClientAuthCertificate + admin scope flag（不需要独立证书类型）"——将 admin 视为 ClientAuthCertificate 的 scope 变体。`auth_api.idl.yaml` §3 将 admin 列为第三种 `ClientAuthCertificate` variant（独立 type 条目，含独立 audience/scope/ttl）。语义上可兼容（admin 仍是 ClientAuth 类型），但 YAML 结构将其显式分离，与 design 的"不是独立类型"措辞有张力。
- **影响**: 中等问题——实现者可能产出三等分证书类型系统而非二等分 + scope flag。
- **建议**: 统一措辞。若保持 design 意图，在 auth_api.idl.yaml 中将 admin variant 的 `type` 字段合并入 ClientAuthCertificate 的 scopes 维度或添加注释说明它是 scope variant 而非独立证书类型。

#### H3: api-registry.md changelog 残留已移除的 bearer token 工具引用

- **文件**: `specs/reference/api-registry.md` §变更记录
- **描述**: v0.3.0 changelog 记录 "新增 Auth category (swarm_auth_login, swarm_auth_refresh)"。这是 R33 B4 证书链重写之前的状态。当前 design/auth.md 和 auth_api.idl.yaml 均基于证书链模型，不存在 `swarm_auth_login`/`swarm_auth_refresh` 工具。
- **影响**: changelog 是历史记录，不应要求删除。但若有人从 changelog 逆向查找这些工具名，会发现它们从未在 Registry 表中出现过——形成误导。
- **建议**: 在 v0.5.0 changelog 条目中追加说明 "superseded auth tools (swarm_auth_login/refresh) removed in R33 B4" 以闭合引用。

### 2.3 Medium

#### M1: economy.idl.yaml AlliedTransfer daily_cap 与 api-registry.md 描述精度差异

- **文件**: `specs/reference/economy.idl.yaml` §2.7 vs `specs/reference/api-registry.md` §10.2
- **描述**: `economy.idl.yaml` 定义 `daily_cap: 10000`（简单常量）。`api-registry.md` §10.2 AlliedTransfer 描述更详细："Daily cap: `max(10_000, receiver_gcl × 20_000) × allied_daily_cap_world_multiplier / 100` units per receiver"——包含 GCL 倍率和 world multiplier。economy.idl.yaml 未体现此公式。
- **影响**: 经济系统实现若只看 economy.idl.yaml，会硬编码 day_cap=10000；若按 api-registry.md 实现则需 dynamic 计算。
- **建议**: economy.idl.yaml §2.7 将 `daily_cap` 替换或补充为公式引用，指向 resource-ledger.md §2.1。

#### M2: engine.md struct 中 Resource 使用 `BTreeMap<String, u32>` vs IDL 使用结构化 ResourceType

- **文件**: `design/engine.md` §3.1 vs `specs/reference/game_api.idl.yaml` type_registry
- **描述**: engine.md 中 Rust struct 定义 `Resource { amounts: BTreeMap<String, u32> }` 使用 String key 表示资源类型。IDL 中 ResourceType 为显式 enum variant（已在 game_api.idl.yaml 中多处使用如 `resource: ResourceType`）。二者可共存（引擎内部表示 vs wire 契约），但引擎侧用 String 意味着类型安全依赖运行时校验而非编译期 exhaustive match。
- **影响**: 低级问题——不阻碍设计一致性，但增加引擎实现时的类型安全风险。
- **建议**: engine.md struct 伪代码改为 `BTreeMap<ResourceType, u32>` 或加注说明 String key 实际映射到 ResourceType enum。由 **engine** 方向确认内部表示。

#### M3: mcp-tools.md Rate Limiter 节含与 Registry 脱节的 source-level tokens/s 表

- **文件**: `specs/reference/mcp-tools.md` §Rate Limiter
- **描述**: mcp-tools.md §Rate Limiter 包含一个 source-level tokens/s 表（WASM=1000, MCP_Query=100, MCP_Deploy=10 等），标注 "Legacy / Reference Only" 同时指出 "实际限流以 registry per-tool rate limit 为准"。api-registry.md §3.1 的 per-tool rate limit 表与此处数值不一致（如 Deploy 在 registry 为 10/h 而非 10/s）。
- **影响**: 容易误导实现者——他们可能先看到 mcp-tools.md 的简化模型。
- **建议**: 从 mcp-tools.md 移除此表（仅保留指向 Registry §3.1 的链接），或添加粗体警告声明该表已废弃。

### 2.4 Low

#### L1: Phase 2b 系统数量引用一致但来源文档链不完整

- **描述**: engine.md 说 "31 systems（R30 B1）"，architecture.md 说 "31 systems per tick"。两者来源于 `phase2b-system-manifest.md`——该文件在本文档列表中不可见（不在 15 文件之列），但两个 design 文档都引用了它。由于设计评审只能基于给定文档，无法验证 31 这个数量本身的正确性，但指向外部 manifest 的引用是正常的。
- **建议**: 保持现状。若 Speaker 需要验证 31 的来源，应检查 phase2b-system-manifest.md（非本评审范围）。

#### L2: design/README.md 术语表与 api-registry.md 中 TickInputEnvelope 字段列表差一个字段

- **描述**: README.md 术语表 §C `TickInputEnvelope` 定义列出了 `module_hash, wasmtime_version, fuel_schedule_version, snapshot_hash, commands_hash, deploy/rollback/admin events, world_config_hash, mods_lock_hash, terminal_state`——共 10 项描述。engine.md §3.3 描述更详细（15+ 字段）。api-registry.md §6 给出完整的 22 字段表。术语表是概览，engine 和 registry 是详细定义——层级不同，不算冲突。
- **建议**: 保持现状。

---

## 3. 亮点

1. **两层计算模型（WASM/COLLECT vs Engine/EXECUTE）的边界在 6 个 design 文档间描述一致。** architecture.md 的核心判断（WASM 不可信只产 command，Engine 权威单 writer）在 engine.md、tech-choices.md、interface.md 中以不同表述重复验证——没有一处出现 WASM 被赋予写权限或 Engine 被降级为非权威的描述偏差。

2. **确定性保证的跨文件引用链完整且单向正确。** engine.md §3.3 → api-registry.md §6 TickTrace Envelope 22 字段 → api-registry.md §11 deploy_mutation 防重放 → api-registry.md §12 persistence async upload——整个 replay 确定性边界从一个文件可追踪到所有依赖文档，无循环引用。

3. **固定点类型替换（f64 → BasisPoints/ResourceRate_i64 等）在三个 IDL YAML 和 api-registry.md §0 之间完全一致。** game_api.idl.yaml type_registry、economy.idl.yaml §1 types、api-registry.md §0 Fixed-Point Type Registry 三处定义的类型名、底层类型、量纲均无冲突。这是 R35 重构后的大范围一致，值得肯定。

4. **design/auth.md 和 auth_api.idl.yaml 在 canonical request signature payload format 上的对齐度较高**（除了 C4 的 header 问题和 C1 的 CA 层数问题）。payload 字段顺序、encoding 规则（UTF-8, LF, no BOM）、validation order 在三文档间基本一致。

5. **"Mod = Bevy Plugin" 的单一扩展机制在 engine.md §3.0 和 tech-choices.md §3 之间描述自洽。** Rhai 移除声明在 tech-choices.md §11 和 engine.md 两处呼应。两层信任边界（WASM 沙箱 vs 引擎内 Mod）在两个文档中的表格表达完全一致。

---

## 4. CrossCheck — 需要跨方向检查

- **CX1: [RejectionReason 48 码的准确构成]** → 建议 **codegen** 方向检查：重新执行 `generate_api_registry.py --check`，对比 game_api.idl.yaml(35码) + auth_api.idl.yaml(12码, namespace 1000+) → api-registry.md(声称48码) 的实际差异。确认：(a) 48 是否为正确的合计（35+12+?=48）；(b) `RefreshTokenInvalid`/`TokenRevoked` 是 registry 旧残留还是 auth IDL 中确实存在；(c) auth IDL 独有码是否已映射到 registry 表格。

- **CX2: [auth_api.idl.yaml 中 "Intermediate CA" 的来源]** → 建议 **design-economy** 方向检查 design/auth.md 的 CA 层数判决是否有后续修订（R34+ 修改），以及 auth_api.idl.yaml 是否在 R33 B4 后未同步更新。检查 `swarm_get_server_trust` 的 intermediate_ca_fingerprint 字段是否与 design/auth.md §4.1 明确矛盾。

- **CX3: [Recycle proximity 的最终规范]** → 建议 **gameplay** 方向检查 commands.md line 95 "Spawn 1 格内" 是否来自更早版本的 Recycle 规则、game_api.idl.yaml "no spawn proximity required" 是否是 R35+ 更新但 commands.md 未同步。同时检查 design/gameplay.md（不在本评审范围）中 Recycle 的描述。

- **CX4: [Swarm-Cert-Id header 的存废]** → 建议 **architect** 方向裁决：api-registry.md §9 移除 Swarm-Cert-Id 并将 cert_id 声明为从证书 body 读取，这与 design/auth.md 和 auth_api.idl.yaml 的行为不同。需要确认实际认证流程中 cert_id 的来源——由客户端在 header 显式声明还是服务端从证书解析。

- **CX5: [auth_api.idl.yaml §1.7 swarm_get_server_trust 输出字段命名]** → 建议 **security** 方向检查：此工具输出 `root_ca_fingerprint` + `intermediate_ca_fingerprint`，但设计采用单层 CA。若改为单层，字段应重命名为 `server_ca_fingerprint` 并移除 intermediate 字段。确认 Server CA 在 API 层的正确术语。

- **CX6: [api-registry.md §3.4 capability profile 与 auth_api.idl.yaml transport labels 的对齐]** → 建议 **interface** 方向检查：capability profiles (onboarding/play/deploy/debug/admin/arena) 的分组逻辑是否覆盖 auth_api.idl.yaml 中 12 个工具的 `transport` 标签（agent-mcp/cli-rest/wasm-sdk）。确认 MCP client 的能力面暴露是否正确。