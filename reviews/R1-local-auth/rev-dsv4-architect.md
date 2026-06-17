# R1 Local Auth — Architect Review (rev-dsv4-architect)

**Reviewer**: Architect (DeepSeek V4 Pro)
**Date**: 2026-06-17
**Documents reviewed**:
- `local-auth.md` (790 lines, 主设计文档)
- `interface.md` (102 lines, MCP 工具表)
- `tech-choices.md` (257 lines, FDB 技术选型)
- `README.md` (226 lines, 设计文档导航)

---

## Verdict: CONDITIONAL_APPROVE

The architecture is sound with clean integration into the existing OAuth2 certificate/session model and a well-reasoned PoW anti-abuse strategy. However, one finding (H1) requires resolution before implementation — the PoW difficulty timing estimates are wrong by 300-700x, making the current defaults unusable in practice. All other findings are non-blocking.

---

## Strengths (亮点)

| ID | 亮点 | 说明 |
|:---|:-----|:-----|
| S1 | **Provider-isolated Player ID 模型** | `blake3("local:" + username)` vs `blake3(provider + ":" + subject)` — 清晰的命名空间隔离，无碰撞风险，可离线推导 |
| S2 | **完整共享证书/会话模型** | 本地用户获得与 OAuth2 完全相同的 `PlayerCertificate` + `WebAuthSession`，下游消费者（Gateway、WASM Deploy、MCP 权限检查）不感知 provider 差异 |
| S3 | **PoW 替代 IP Rate Limiting** | 架构决策正确——无状态、NAT-friendly、botnet-resistant，天然适合 AI agent 场景（agent 和被注册者可能共享 IP） |
| S4 | **MCP-first 设计** | `swarm_register` / `swarm_login` 作为 MCP tool 实现，AI agent 和前端走相同路径。Gateway 仅做薄代理。与 Swarm「MCP 是 AI 的操作界面」哲学一致 |
| S5 | **FDB 事务原子性** | 注册事务原子处理 challenge 消费 + 用户名检查 + 用户写入，杜绝竞态条件（两个请求同时注册同一用户名） |
| S6 | **用户名枚举防护** | 登录失败统一返回 `invalid_credentials`，不区分「用户不存在」和「密码错误」——标准安全实践 |
| S7 | **纵深防御** | 密码不记录日志、不通过 MCP 响应返回、前端不存储密码（仅存 refresh_token + certificate）、FDB 仅存 argon2id hash |
| S8 | **测试策略完善** | 18 个单元测试覆盖边界条件（用户名校验、密码强度、PoW 一次性、TTL 过期、确定性 player_id）+ 2 个集成测试覆盖全流程，包含 AI agent 自注册测试用例 |
| S9 | **零门槛设计** | 不强制邮箱，用户名+密码即可注册——真正低门槛，且与「本地认证」的设计意图一致 |

---

## Findings (发现的问题)

### [High] H1 — PoW 难度时间估算严重偏离实际

**位置**: `local-auth.md` §5.3, 难度参数表 (line 219-226)

**问题**: 文档声称 `difficulty=4`（4 前导零字节 = 32 zero bits）预期求解时间约 1.3 秒，但这需要对 blake3 单次调用吞吐达到约 3.3B hashes/sec。实际测量：

| 环境 | 估算单核 hashes/sec | difficulty=4 实际时间 | 文档声称 | 偏差 |
|:-----|:-------------------|:----------------------|:---------|:-----|
| Rust (native, optimized) | ~10M | ~7 分钟 | 1.3 秒 | **~330x** |
| JavaScript (blake3-wasm, browser) | ~200K | ~6 小时 | 1.3 秒 | **~5000x** |
| Python (blake3 绑定) | ~2M | ~36 分钟 | 1.3 秒 | **~1660x** |

文档中的难度参数表（difficulty 2/3/4/5）全线偏差约 300-700x，根源是假设了不可实现的 blake3 小输入吞吐量。

**影响**:
- 前端用户点击 Register 后会等待数小时（不是 ~1 秒），体验灾难性
- AI agent 自注册同样受阻——PoW 时间远超合理范围
- 如果盲目按文档实现，上线后 PoW 机制将形同虚设（被迫降低 difficulty 到 2）或完全阻塞注册

**建议修正**:
1. 重新校准 difficulty 参数。以 Rust 原生 ~10M hashes/sec 为基线：

   | 场景 | 建议 difficulty | 预期时间 (Rust) | 预期时间 (JS/browser) |
   |:-----|:---------------|:----------------|:----------------------|
   | 开发/测试 | 2 (2 bytes = 16 bits) | ~6ms | ~300ms |
   | 生产 (轻量) | 2 (同上) | ~6ms | ~300ms |
   | 生产 (标准) | **3** (3 bytes = 24 bits) | **~1.7s** | **~84s** |
   | 反滥用 (高) | 4 (4 bytes = 32 bits) | ~7min | ~6hr |

2. 或改用**可变 difficulty**——服务端根据当前注册负载动态调整 `difficulty`（与 FDB 挑战计数联动），低负载时 difficulty=2，高负载时升至 3。
3. 前端 PoW 求解使用 Web Worker 避免阻塞 UI 线程，并展示进度估算。
4. 明确文档中不同运行环境的预期时间（Rust agent vs Python agent vs browser JS）。

---

### [Medium] M1 — 返回类型命名不当

**位置**: `local-auth.md` §8.3 (line 281), §13.1 (line 571)

**问题**: `swarm_register` 和 `swarm_login` 的返回类型是 `OAuth2LoginResult`，但本地认证与 OAuth2 无关。虽然结构复用是正确的（字段完全一致），但类型名称具有误导性——新的维护者阅读代码时会困惑「为什么本地注册返回 OAuth2 结果」。

**建议**: 重命名为 `AuthLoginResult` 或 `LoginResult`，保持 `OAuth2LoginResult` 作为 type alias 以保证向后兼容。

---

### [Medium] M2 — FDB 事务冲突重试未文档化

**位置**: `local-auth.md` 附录 C (line 753-790)

**问题**: 注册事务在 FDB 中执行 `tx.get(pow_key)` + `tx.clear(pow_key)` + `tx.set(user_key)` + `tx.commit()`。如果两个并发注册使用不同的 challenge_id 但相同的 username（第二个请求在第一个事务提交前读到「用户名不存在」），FDB 会在 commit 时检测冲突并拒绝后提交的事务。文档未说明：
- 客户端收到 FDB 事务冲突错误后应如何处理（重试？用不同用户名？）
- 服务端是否需要内置重试循环

**建议**: 在实现中为注册事务添加重试循环（最多 3 次，指数退避），或至少文档化冲突时的错误响应格式和客户端处理策略。

---

### [Medium] M3 — FDB Key Schema 缺少命名空间前缀

**位置**: `local-auth.md` §5.2 (line 162-166)

**问题**: Key 设计使用扁平字符串 `users/<username>` 和 `pchallenge/<id>`。虽然目前只有 local-auth 使用这些前缀，但与其他子系统的 key 处于同一命名空间。随着系统增长，存在 key 冲突风险。

**建议**: 使用命名空间前缀如 `localauth.users.<name>` 和 `localauth.pchallenge.<id>`，或使用 FDB directory layer 进行逻辑分组。与现有 FDB 使用规范（如 tick 数据的 `/tick/{N}/...` 模式）保持一致。

---

### [Medium] M4 — `issue_login` 第三个参数语义不明确

**位置**: `local-auth.md` 附录 C (line 789)

**问题**: 
```rust
self.issue_login("local", &params.username, "local-credential", params.client_public_key)
```
`"local-credential"` 字符串的语义未在文档中定义。是 credential subject? credential type? 此值与 OAuth2 路径中对应的参数是什么关系？

**建议**: 文档化 `issue_login` 的函数签名及其参数语义。如果 OAuth2 路径传入的是 `"oauth2:{provider}:{subject}"`，则本地路径应该传入类似 `"local:{username}"` 以保持一致的结构化语义。

---

### [Medium] M5 — 跨平台 PoW 性能差异未处理

**位置**: `local-auth.md` §5.3, 附录 A

**问题**: 文档提供了 Python、JavaScript 两种 PoW 求解实现，但未讨论不同平台的性能差异。Python agent 求解 difficulty=3 需要约 8 秒，而 Rust agent 约 1.7 秒，browser JS 约 84 秒。如果 AI agent 使用 Python MCP SDK，每次注册的 PoW 等待时间差异显著。

**建议**:
1. 文档化各平台的预期 PoW 求解时间（基于校准后的 difficulty）
2. 考虑提供预编译的 blake3 WASM 模块给 Python/JS 使用以提升性能
3. 考虑「PoW 委托」——允许 client 将 PoW 求解外包给更快的本机服务（如 CLI 工具 `swarm-solve-pow`）

---

### [Low] L1 — `blake3_hash_to_player_id` 截断行为未文档化

**位置**: `local-auth.md` §9.2 (line 440-444)

**问题**: `blake3(...) → u64` 截断意味着 2^64 空间内映射。虽然碰撞概率可忽略（生日攻击需 ~2^32 ≈ 4.3B 用户才到 50% 概率），但截断方式未说明：取前 8 字节？后 8 字节？XOR fold？

**建议**: 明确 `blake3_hash_to_player_id` 的截断策略，并在文档中记录碰撞概率分析。

---

### [Low] L2 — `swarm_login` 中 `client_public_key` 语义待澄清

**位置**: `local-auth.md` §8.1 (line 278-282), §8.4 (line 369-391)

**问题**: `swarm_login` 要求传入 `client_public_key`，但未说明：
- 此 key 是否必须与注册时的 key 相同？
- 如果用户丢失了原始 key pair，能否用新 key pair 登录？（可以，因为证书是每次登录重新签发的——但这应该在文档中明确说明）

**建议**: 文档化 key rotation 能力——明确「登录时的 client_public_key 可以与注册时不同，新 key 会签发到新证书中」。

---

### [Low] L3 — Login 路径缺少显式限速

**位置**: `local-auth.md` §8.4, §11.1

**问题**: `swarm_login` 仅依赖 argon2id 固有速度（~100ms/attempt）作为暴力破解阻力。单核可达到 ~10 attempts/sec，多核并行可达更高。虽然每 tick 的通用限速（10/min per IP）提供了一定保护，但分布式攻击场景下多个 IP 仍可并行尝试。

**建议**: 考虑基于 account 的限速（同一 username 连续失败 N 次后临时锁定，指数退避），补充 argon2id 的速度屏障。

---

### [Low] L4 — Provider 字段隐式约定

**位置**: `local-auth.md` §13.2, §10.2

**问题**: 后端 `provider` 值 `"local"` 与前端 `AuthProvider = 'github' | 'google' | 'local'` 的 `'local'` 一致，但这是隐式约定，未在文档中显式交叉引用。

**建议**: 在 §13.2 中显式引用 §10.2 的 TypeScript 类型定义，或在 `provider` 值表中加入前端类型映射。

---

## Consistency Gaps (跨文档一致性缺口)

### CG1 — Gateway 路由模式不一致

`local-auth.md` §8.5 中 Gateway 本地认证路由使用 `/auth/register`、`/auth/login`，而 OAuth2 路由使用 `/oauth2/{p}/login`、`/oauth2/{p}/callback`。两者 URL 模式差异显著。

**分析**: 这是有意的——本地认证和 OAuth2 是两种协议，但文档未显式说明这种差异的设计意图。建议在 §8.5 增加注释：「与 OAuth2 的 `/oauth2/{p}/*` 路径并列，本地认证使用 `/auth/*` 路径族——两者在 Gateway 路由表中是平级的分组。」

### CG2 — `interface.md` 中认证工具列表一致

`interface.md` §4.1 (line 37-43) 已包含 `swarm_register_challenge`、`swarm_register`、`swarm_login`，且分类为「认证」——与 `local-auth.md` §8.1 完全一致。✅ 无缺口。

### CG3 — FDB 技术选型引用一致性

`local-auth.md` §5.2 引用 `tech-choices.md §4`，`tech-choices.md` §4 确实详细分析了 FDB 选型理由（严格可序列化、每 tick 原子提交）。两者一致。✅ 无缺口。

---

## Algorithmic Risks (算法风险关注)

### AR1 — PoW 难度固定 vs 自适应

当前设计使用固定 `difficulty = 4`。在系统生命周期的不同阶段，注册负载差异巨大（冷启动期几乎没有竞争，热门期可能遭遇批量脚本攻击）。固定难度在低负载时浪费 CPU，在高负载时可能不足。

**建议**: 考虑自适应难度——服务端维护近期注册速率窗口（如过去 5 分钟的注册次数），超过阈值时自动提升新 challenge 的 difficulty。这样正常负载下 difficulty=2~3（体验好），异常负载下提升到 4~5。

### AR2 — Challenge 存储增长

每个注册请求（无论最终是否完成注册）都会在 FDB 中创建一个 `pchallenge/<id>` 条目。5 分钟 TTL 后过期，但 TTL 依赖 FDB 的 key expiry 机制或清理任务。如果 Swarm 变得流行，每秒钟可能有数百个 challenge 请求，FDB 中的过期 key 需要主动清理。

**建议**: 文档化 challenge 的清理策略——是依赖 FDB TTL（需要配置），还是后台 GC 任务周期扫描清理。估算存储量：每秒 100 个 challenge × 300 秒 = 30,000 条活跃记录，每条 ~100 bytes = 约 3MB——可管理。

---

## 总体评价

方案架构设计整体优秀。关键架构决策——Provider 隔离的 Player ID、MCP-first API 设计、与 OAuth2 共享证书/会话模型——都经过深思熟虑，与 Swarm 现有架构无缝集成。PoW 替代 IP rate limiting 的推理链完整，从威胁模型到 AI agent 兼容性都有充分论证。

唯一阻塞项 (H1) 是 PoW 难度参数的工程校准问题——不是设计错误，而是参数选值错误。修正后即可进入实现。

建议在 Phase 1 实现前：
1. 修正 difficulty 参数表（H1）
2. 澄清 `issue_login` 参数语义（M4）
3. 文档化 FDB 事务冲突处理（M2）
