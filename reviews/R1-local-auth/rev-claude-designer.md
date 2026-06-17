# R1 Clean-Slate 评审 — Designer 视角 (Claude)

**评审员**: rev-claude-designer
**评审对象**: Swarm 本地用户认证设计 (`design/local-auth.md` 790 行 + interface.md / tech-choices.md / README.md 上下文)
**评审视角**: 设计师 — 用户体验、API 简洁度、场景覆盖、可用性
**轮次**: R1 (clean-slate, 独立评审)

---

## Verdict

**REQUEST_MAJOR_CHANGES**

设计的骨架立得住:argon2id + OWASP 2025 参数、PoW 一次性消费 + FDB 原子事务、与 OAuth2 共享证书系统、确定性 player_id —— 这些核心选择都是经得起推敲的。但作为面向「人类 / AI / Agent 代理」三类完全异质用户群的统一认证表面,**§13 附录 C 的 FDB 事务伪代码暴露了一个 Critical 级别的 PoW 绕过路径**(challenge_id 与 challenge 字符串、difficulty 之间无服务端绑定校验),且若干关键 UX 路径(前端 PoW 阻塞、AI agent 凭据丢失后的处置、错误码体系不完整)只有一句话带过、没有真正落地。

需要修订完整后再次评审,而非进入实现。

---

## 发现的问题

### Critical

**[Critical] G1 — PoW 校验存在服务端绑定缺失漏洞 (附录 C §13)**

§13 给出的 FDB 事务伪代码:

```rust
// 1. 验证 PoW(一次性使用)
let pow_key = format!("pchallenge/{}", params.challenge_id);
if tx.get(pow_key.as_bytes(), false).await?.is_none() {
    return Err(McpError::invalid_params("challenge not found or already used"));
}
tx.clear(pow_key.as_bytes());

// 2. 验证 PoW 解
if !verify_pow(&params.challenge, &params.nonce, DIFFICULTY) {
    return Err(McpError::invalid_params("invalid_pow"));
}
```

存在两处绑定缺失:
- `tx.get(pow_key)` 仅用作存在性标记,**没有读取 FDB 中存储的 `{challenge, difficulty, ttl}` 结构,没有把它与 `params.challenge` / `DIFFICULTY` 比对**
- §4 架构图明确写了 `"pchallenge/<id>" → {challenge, difficulty, ttl}` ,但 §13 完全没用这些字段

后果:
- 攻击者请求一个真实 challenge_id,但在 register 调用中**用客户端构造的简单 challenge 字符串替换** —— 因为 challenge_id 只查存在,verify_pow 用 params.challenge,所以攻击者只需对自选的弱字符串求 nonce
- 更糟:`DIFFICULTY` 是常量(看 §13 第二个参数 `DIFFICULTY` 直接来源未明)。如果实现者把它从客户端 params 取(API 设计本身又允许 difficulty 字段经过客户端往返),则 difficulty=0 通过校验
- PoW 防线退化为 0,批量注册成本归零

**修复建议**:
1. §13 改写为先 `let stored: ChallengeRecord = tx.get(pow_key).deserialize()?;`,再校验 `stored.challenge == params.challenge && now < stored.created_at + stored.ttl`,verify_pow 必须使用 `stored.difficulty`(服务端权威值),而非来自客户端
2. §8.3 register 请求 schema 中删除 `challenge` 字段(冗余),只保留 `challenge_id + nonce + 用户信息`(同时解决 M1)
3. §11.1 威胁表新增一行「challenge 字段绑定欺骗 → 缓解:服务端只信任 FDB 存储的 challenge + difficulty」


### High

**[High] G2 — 三种注册场景的「错误恢复」UX 完全空白**

§3 列了三种场景的 happy path,但每一种的失败路径都没设计:

- **人类前端**: PoW 求解中断会怎样? 用户切走标签页 30 秒,JS 引擎被 throttle,1.3s 变 30s,用户以为卡死刷新页面 — 此时 challenge_id 已经在客户端,服务端还没消费,新 challenge 又拿一个,**第一个 challenge 占着 5 分钟 TTL 但永远不会被用** — 这本身不是漏洞,但前端 UX 应该明确说明:刷新后不要尝试 resume 旧 challenge,直接重新发起
- **AI agent 自注册**: agent 凭据丢失(进程崩溃 / context 截断)怎么办? 设计明确说「AI agent 将 username + password + certificate + refresh_token 视为持久化凭据」,但**没说凭据丢失后能不能找回**。§12.2 把密码重置推到后续版本 — 那 AI agent 的 password 一旦丢就永远丢了,player_id 还在 FDB 里,资产还在,但永远无法再登录。这是一条死锁路径,设计应明确说明:AI agent 必须在 swarm_register 成功后立即把凭据写入持久化存储,且建议 username 用可恢复种子生成(而非 random_hex(8))
- **Agent 代理注册**: agent 替人类注册,密码到底由 agent 生成还是人类提供? §3.3 说「人类只需提供意图和密码」,但 §3.2 又说 AI 可自行生成密码。两个流程在「谁记住密码」这件事上语义冲突 — agent 替人类注册的场景下,密码必须由人类提供并能被人类记住,否则人类下次登录会失败

**修复建议**: §3 每个子场景结尾加「错误恢复」段落,明确凭据丢失、网络中断、challenge 过期、PoW 求解超时各自的处理路径。代理注册场景明确「密码必须人类提供 + 弱密码引导文案」。

**[High] G3 — 前端 PoW 阻塞主线程的可用性问题未设计**

§5.3 `difficulty=4 ~1.3s` 在「单核」前提下成立,但前端 JavaScript 实际场景:
- 移动端低端 ARM 实测 blake3-wasm 性能 ~1/3 桌面,**1.3s 变 4s**
- §10.1 UI 文案写「Register needs ~1s PoW proof」 — 移动端用户会看到 4 秒无响应的 Register 按钮,直觉就是「卡死了」
- §附录 B JavaScript 示例代码用 `while(true)` 循环 + `nonce++` —— 这会**完全阻塞 UI 线程**,即使在桌面也会让按钮在求解期间无法响应、整个页面冻结

**修复建议**:
1. §10.1 必须明确前端 PoW **必须运行在 Web Worker 中**,主线程显示进度条(已尝试次数 / 预期次数),且每 100ms `postMessage` 一次进度
2. 附录 B 的 JS 代码示例改为 Web Worker 版本(否则实现者会照抄到主线程)
3. UI 文案改为「Solving registration challenge... ~1-5s」,并在超过 8 秒时显示「Slow device? You can wait or [Cancel]」按钮
4. 考虑「difficulty 自适应」:服务端检测到客户端是移动端 UA 时返回 difficulty=3(降到 ~5ms 桌面 / ~15ms 移动),但严格保持「服务端权威 difficulty」(关联 G1 修复)

**[High] G4 — `swarm_login` 不需要 PoW 的论证不完整**

§8.1 说「swarm_login 不需要 PoW —— 每 tick 已限速(10/min per IP),且 argon2id 本身足够慢」 —— 但:
- §11.2 整个一节论证「为什么 PoW 而非 IP rate limiting」 — 列举了 IP 限速对 AI agent / NAT / botnet 的所有缺陷
- 那么登录路径仍然依赖 IP 限速,**§11.2 列举的所有缺陷照样适用**:NAT 后多用户、botnet 分布式爆破、AI agent 共享 IP
- argon2id ~100ms 单次 attempt 听起来慢,但分布式爆破 1000 个节点并行 = 100ms / 1000 = 0.1ms 有效尝试间隔,完全够用
- 单用户密码爆破场景:针对一个具体 username,攻击者从不同 IP 用字典攻击,IP 限速不触发(每 IP 只试 9 次/分钟),但目标用户密码空间在数小时内被覆盖

**修复建议**:
- 要么 login 也加 PoW(可用更低的 difficulty=2,~1ms 用户无感,但每尝试仍需 CPU 工作)
- 要么补充「单用户密码错误次数限速」(per username 5 次/小时,触发后强制 PoW),与 IP 限速正交
- 在 §11.1 威胁表新增「分布式低速密码爆破」行,并明确缓解措施
- §8.1 的「argon2id 本身足够慢」论证需要量化:列出在 difficulty=4 PoW 防御 vs 仅 argon2id 防御下,1000 节点 botnet 爆破 8 字符密码的预期时间对比
