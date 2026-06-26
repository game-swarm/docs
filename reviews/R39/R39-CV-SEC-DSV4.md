# R39-CV-SEC-DSV4 安全评审报告

## 评审范围

- `design/auth.md`
- `specs/security/03-mcp-security.md`
- `specs/security/09-command-source.md`
- `specs/core/04-wasm-sandbox.md`

重点检查：Auth 控制面、MCP transport/audience、Deploy 签名与重放、WASM sandbox 边界、未认证端点 DoS 防护。

## 总体结论

当前 DSv4 安全设计已经覆盖了大多数关键边界：应用层证书作为唯一权威凭证、Browser 与 Agent transport 拆分、WebSocket per-message 签名、WASM deferred command model、只读 host functions、netns + seccomp 双层网络隔离、Intermediate CA 强制保护、CSR 多层 admission control 等方向均正确。

但当前文本仍存在若干会导致实现分叉或安全降级的合同冲突。最严重的是 `DeployPayload` 把服务端编译后才知道的 `compiled_artifact_hash` 放进客户端签名 payload，同时又声明客户端不得自报；其次是未认证 CSR 端点的限流表述互相矛盾，可能让实现者仅依赖 PoW。建议修复 Blocker/High 后再冻结为实现合同。

---

## 阻塞问题（Blocker）

### B1. `DeployPayload` 签名字段包含 `compiled_artifact_hash`，与“服务端计算/客户端不得自报”矛盾

**位置**：

- `specs/security/09-command-source.md:75`
- `specs/security/09-command-source.md:81`
- `specs/security/09-command-source.md:96`
- `specs/security/09-command-source.md:118`
- `specs/security/09-command-source.md:266`
- `specs/core/04-wasm-sandbox.md:41`
- `specs/core/04-wasm-sandbox.md:412`

**问题**：

`09-command-source.md` §3.2 声明客户端签名的 `DeployPayload` 包含 `compiled_artifact_hash` 字段。但同一文档又说明：

- `compiled_artifact_hash` 是服务端编译后写入，用于运行时 artifact/cache 完整性；
- `compiled_artifact_hash` 不得替代 `wasm_module_hash` 做代码签名；
- §7.3 明确写 “compiled_artifact_hash 由服务端编译后计算，客户端不得自报”。

这三者无法同时成立：客户端在部署提交时无法知道服务端编译 artifact hash，也不应被允许自报它；如果签名 payload 强制包含该字段，要么实现者会让客户端填空/占位并签名，导致签名 payload 与最终 manifest 不同；要么实现者会接受客户端自报 artifact hash，破坏 artifact 完整性边界。

**影响**：严重。该冲突直接影响代码签名信任边界、编译缓存投毒防护、artifact 完整性验证和 replay/audit 中 `wasm_module_hash` vs `compiled_artifact_hash` 的职责分离。

**建议**：

1. 从客户端签名的 `DeployPayload` 中移除 `compiled_artifact_hash`。
2. 客户端签名只覆盖：`domain, wasm_module_hash, metadata_hash, player_id, world_id, module_slot, version_counter, signed_at, audience`。
3. 服务端验证签名与 `wasm_module_hash == Blake3(wasm_bytes)` 后，编译并计算 `compiled_artifact_hash`。
4. 服务端 manifest 写入 `{signed_deploy_payload_hash, wasm_module_hash, metadata_hash, compiled_artifact_hash, compiler_policy_version, security_epoch}`。
5. `04-wasm-sandbox.md` 缓存键可继续使用 `compiled_artifact_hash`，但必须声明它是服务端派生字段，不属于客户端签名 payload。

---

## 严重问题（High）

### H1. CSR 提交限流合同自相矛盾，可能退化为“PoW 自身限速”

**位置**：

- `design/auth.md:259`
- `design/auth.md:264`
- `design/auth.md:266`
- `design/auth.md:267`
- `design/auth.md:877`
- `design/auth.md:884`
- `design/auth.md:890`
- `design/auth.md:971`
- `design/auth.md:977`

**问题**：

`design/auth.md` §5.2 和 §10.7 已经正确声明 CSR 提交必须经过多层 admission control：PoW、per-IP、per-ASN、global semaphore、bounded queue、audit throttle，并明确 PoW 不能替代速率限制。

但 §10.8 “未认证端点保护” 表中又写：

`CSR 提交 | PoW 自身限速 | 无额外 IP 限制`

这与前文权威准入链直接冲突。实现者若以 §10.8 表为准，会把 CSR 提交实现成仅 PoW 防护，从而允许云 VM/botnet 并行求解 PoW 后压垮 CSR 验证、FDB challenge 读写或证书签发路径。

**影响**：高。该问题影响未认证入口的 DoS 防护，且攻击发生在用户完成认证前，无法依赖账号级限流缓解。

**建议**：

- 将 §10.8 表中 CSR 提交改为：`多层 CSR admission control（见 §5.2 / §10.7）`。
- 删除 “无额外 IP 限制” 表述，或明确仅指 “不使用 Dragonfly nonce；仍强制 per-IP/per-ASN/semaphore/queue”。
- 保留 §5.2 作为唯一权威参数表，§10.8 只引用不重复声明数值。

### H2. Agent endpoint 与 HTTP 安全表的 Origin 规则可能互相覆盖

**位置**：

- `specs/security/03-mcp-security.md:86`
- `specs/security/03-mcp-security.md:93`
- `specs/security/03-mcp-security.md:112`
- `specs/security/03-mcp-security.md:117`
- `specs/security/03-mcp-security.md:306`
- `specs/security/03-mcp-security.md:311`

**问题**：

文档前半部分正确拆分了 Browser 与 Agent/CLI：Browser endpoint 使用 Origin/CSRF/Fetch Metadata；Agent endpoint 使用应用层证书和 canonical request signature，不依赖 Origin，并拒绝 browser-style Origin/CSRF header。

但 §5.3 “HTTP 安全合同” 表写：

`CORS Origin | 白名单 | 不使用 *，非浏览器客户端拒绝缺失 Origin`

如果该表被实现者视为所有 HTTP/MCP 端点的通用合同，会直接与 Agent/CLI 的安全模型冲突：原生 HTTP 客户端通常没有可信 Origin；要求 Origin 反而鼓励客户端伪造浏览器 header，破坏 Browser/Agent transport 分离。若实现者忽略 §5.3，则 Browser endpoint 的 Origin 约束又可能被弱化。

**影响**：高。该冲突会导致 endpoint 分流与跨协议混淆防御实现不一致。

**建议**：

- 将 §5.3 拆成两张表：Browser HTTP/SSE 安全合同、Agent/CLI HTTP 安全合同。
- Browser 表保留 Origin/Host/CSRF/Fetch Metadata。
- Agent 表明确：拒绝或忽略 Origin/CSRF；强制 `X-Swarm-Transport`、应用层证书、canonical signature、audience 精确匹配。
- “非浏览器客户端拒绝缺失 Origin” 应改为 “Browser endpoint 拒绝缺失/不匹配 Origin；Agent endpoint 不接受 Origin 作为认证信号”。

### H3. seccomp `clone` 允许项与 “fork/vfork 禁止” 表述不够精确

**位置**：

- `specs/core/04-wasm-sandbox.md:264`
- `specs/core/04-wasm-sandbox.md:280`
- `specs/core/04-wasm-sandbox.md:450`
- `specs/core/04-wasm-sandbox.md:457`
- `specs/core/04-wasm-sandbox.md:474`

**问题**：

`04-wasm-sandbox.md` 同时声明：

- seccomp 允许 `clone (仅 CLONE_VM | CLONE_VFORK)`；
- `fork/vfork` 禁止；
- pids.max = 16；
- CI 要验证 PID namespace 内 fork 失败。

这里的问题不是允许 Wasmtime 内部线程本身，而是 `CLONE_VFORK` 语义接近 vfork，文档又要求 `fork/vfork` 禁止，容易让实现者写出过宽的 BPF 条件。若 seccomp 只按 syscall 名放行 `clone`，而没有严格校验 flags，sandbox 内代码或 runtime 依赖变化可能扩大到非预期进程/线程创建面。

**影响**：高。sandbox 进程创建边界是逃逸防线之一；BPF 条件不精确会削弱 pid namespace、pids.max 与 no-exec 策略的组合保证。

**建议**：

- 明确允许的 clone flags 精确集合，例如仅允许 Wasmtime 所需线程创建 flags，并禁止 `CLONE_NEWUSER`、`CLONE_NEWPID`、`CLONE_NEWNET`、`CLONE_FS` 等 namespace/进程语义。
- 删除 `CLONE_VFORK`，除非有明确 Wasmtime 版本证据必须使用；若保留，解释为何不等价于允许 vfork，并给出 BPF flags mask。
- CI 增加 `clone` flags matrix：允许线程路径通过，`fork`/`vfork`/namespace clone 全部返回 EPERM。

---

## 中等问题（Medium）

### M1. Deploy hash 命名跨文档仍残留 `module_hash`，与 `wasm_module_hash`/`compiled_artifact_hash` 分层不一致

**位置**：

- `specs/security/03-mcp-security.md:55`
- `specs/security/03-mcp-security.md:56`
- `specs/security/03-mcp-security.md:59`
- `specs/security/09-command-source.md:67`
- `specs/security/09-command-source.md:95`
- `design/auth.md:171`
- `design/auth.md:295`

**问题**：

`09-command-source.md` 和 `design/auth.md` 已经使用更精确的 `wasm_module_hash` / `compiled_artifact_hash` 分层，但 `03-mcp-security.md` §1.1 仍使用泛化 `module_hash + metadata` 和 “module_hash 进入世界状态”。在安全上下文中，这个泛称容易与 compiled artifact hash、module slot hash 或 API registry 中旧 `module_hash` 混淆。

**影响**：中。不是直接漏洞，但会导致代码签名、部署幂等、运行时 artifact 验证和审计字段命名不统一。

**建议**：

- `03-mcp-security.md` §1.1 改为 `wasm_module_hash + metadata_hash`。
- 补一句：`compiled_artifact_hash` 由服务端编译后写入 manifest，不属于客户端签名输入。
- 若保留 `module_hash` 作为开发者口语，增加术语表说明它等价于 `wasm_module_hash`，不得指 compiled artifact。

### M2. Auth 证书验证缓存位置在 Engine/Gateway 间职责略模糊

**位置**：

- `design/auth.md:76`
- `design/auth.md:100`
- `design/auth.md:101`
- `design/auth.md:338`
- `design/auth.md:343`
- `design/auth.md:951`
- `specs/security/03-mcp-security.md:101`
- `specs/security/03-mcp-security.md:107`

**问题**：

`design/auth.md` 同时描述 Engine 持有 certificate verifier / revoked certificate cache，Gateway 负责 canonical request 验签入口并注入 Principal；`03-mcp-security.md` 又把 nginx/网关写成验证 `Swarm-Certificate-Chain + canonical request signature` 的入口。

这是合理的双层模型，但当前文本没有明确：Gateway 验签后的 principal/certificate snapshot 是否仍需 Engine 二次验证；Engine 内 LRU 证书链缓存是否用于所有 MCP 请求，还是仅用于 tick/deploy 运行期。若实现者只在 Gateway 验签，Engine 内 admin/test/replay 路径可能缺少统一 Principal 校验；若每层都独立查 CRL，又可能产生缓存延迟差异。

**影响**：中。边界模糊可能导致重复验证、缓存不一致或内部调用绕过 Gateway principal 注入。

**建议**：

- 增加 “Gateway verifies transport request; Engine authorizes command/source using immutable Principal snapshot” 的固定流水线。
- 明确 Engine 不信任客户端字段，只信任 Gateway/Auth Service 注入的 principal，并按 source gate 再校验 scope/audience。
- 明确 CRL cache 的失效源和最大延迟对 Gateway 与 Engine 是否一致。

### M3. Spectator WebSocket 使用 audience 字符串但无证书，语义需降级为 endpoint label

**位置**：

- `specs/security/03-mcp-security.md:167`
- `specs/security/03-mcp-security.md:170`
- `specs/security/09-command-source.md:195`
- `design/auth.md:940`
- `design/auth.md:945`

**问题**：

文档声明 spectator WS 不接受 `Swarm-Certificate-Chain`、不执行证书握手、只读；同时又给出 audience：`swarm-aud-v1:spectator-ws:<server_id>:<world_id>:public`。由于 audience 通常是证书/canonical request 签名中的验证字段，spectator 无证书时这个字符串不能作为认证安全属性。

**影响**：中。若实现者误以为 spectator audience 可替代 Origin/endpoint/path 保护，会高估其安全性。

**建议**：

- 明确 spectator audience 只是 endpoint/telemetry label，不参与证书验证。
- Spectator 安全边界应只依赖：只读 handler、公开数据过滤、连接/事件限流、Host/Origin（浏览器场景）和无写操作 schema。

---

## 轻微问题（Low）

### L1. `swarm_list_modules` 与旧工具变更记录在安全规范中仍显得像状态追踪

**位置**：

- `specs/security/03-mcp-security.md:231`
- `specs/security/03-mcp-security.md:235`
- `specs/security/03-mcp-security.md:237`

**问题**：

`03-mcp-security.md` §4.1 现在声明 `swarm_list_modules` active，并保留 “变更记录：swarm_rollback 已替换” 这类历史表述。按照文档约定，规范应描述目标状态，不应保留变更记录。

**建议**：

- 删除 “变更记录” 字样，改成目标态：回滚仅通过 Admin profile 的 `swarm_admin_rollback` 暴露。
- `swarm_list_modules` active 状态继续以 API Registry 为权威。

### L2. `03-mcp-security.md` 内部出现字面 `\n\n` 转义残留

**位置**：

- `specs/security/03-mcp-security.md:264`

**问题**：

该行包含字面 `\n\n`，影响 Markdown 可读性，可能是批量 patch 残留。

**建议**：拆成正常 Markdown 段落，不影响安全合同本身。

---

## 正向确认

- Browser 与 Agent/CLI transport 分离方向正确：Browser 依赖 Origin/CSRF/Fetch Metadata；Agent/CLI 依赖应用层证书与 canonical signature。
- `agent-mcp`、`agent-ws`、`cli-rest`、`spectator-ws` audience 已从旧 `browser-ws` 模型收敛，跨 transport 重放防护方向正确。
- `ClientAuthCertificate` / `CodeSigningCertificate` / `AdminCertificate` 用途隔离、Admin 短 TTL、Intermediate CA 强制 HSM/KMS/0600 检查均是必要安全边界。
- CSR 多层 admission control、argon2id worker pool、dummy argon2id 与恢复凭据限流组合是合理的未认证入口防护模型。
- WASM deferred command model、禁止 mutating host functions、只读 host functions 走 visibility filter，可以防止 WASM 直接绕过命令校验管线。
- WASM sandbox 的独立 netns + seccomp socket syscall 双层隔离、Store reset checklist、host_get_random length-delimited domain separation 都是正确方向。

## 建议的冻结前修复顺序

1. 先修复 `DeployPayload`，移除客户端签名中的 `compiled_artifact_hash`，确立服务端派生字段边界。
2. 修复 CSR 未认证端点表，删除 “PoW 自身限速 / 无额外 IP 限制” 冲突表述。
3. 拆分 Browser 与 Agent HTTP 安全合同，避免 Origin 规则跨 endpoint 覆盖。
4. 精确化 sandbox `clone` seccomp flags 与 CI matrix。
5. 清理 `module_hash` 命名、spectator audience 语义和 Markdown/变更记录残留。

## 评审结论

**结论：请求修改（Request Changes）。**

DSv4 安全架构总体方向正确，但 B1 与 H1/H2/H3 都属于实现冻结前必须收敛的安全合同问题。尤其 B1 会直接破坏代码签名与 artifact 完整性边界；H1 则可能把未认证 CSR 入口退化为可被分布式 PoW 绕过的 DoS 面。修复上述问题后，安全方向可进入下一轮 Closure Verification。
