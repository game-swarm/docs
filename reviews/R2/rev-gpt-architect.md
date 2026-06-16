# Swarm 架构评审报告 — R2

**评审员**: rev-gpt-architect (GPT-5.5 — Architect)
**评审范围**: `docs/design/DESIGN.md`, `docs/ROADMAP.md`, `docs/specs/01-09`, `docs/api/*` 的 R2 架构一致性与可实现性
**评审视角**: 成功/失败架构模式识别、抽象层次、接口直觉性、新人实现路径、阶段排序

---

## Verdict

**REQUEST_CHANGES（文档层变更后再进入实现）**

R2 的主设计方向是对的：AI 与 human 统一走 WASM、MCP 定位为管理/观察界面、Tick 被拆成 COLLECT/EXECUTE/BROADCAST、可见性收敛到 `is_visible_to`，这些都是可成功落地的架构选择。

但当前不是“设计已稳定，只剩实现”的状态。最大问题不是某个单点规则写错，而是 **DESIGN、specs、IDL、ROADMAP 四层同时声称自己是权威，却在关键合同上互相矛盾**。这会让新人按不同文档实现出不同系统，且每个实现者都能合理地说“我是按文档做的”。在 Swarm 这种高确定性、高公平性、可回放的系统里，这类 split-brain specification 是实际会炸的模式。

建议：R2 可以判定为“核心方向通过”，但必须先做一轮 **Spec Convergence Patch**，把 Overload、Direction、Command limits、Tick ECS 顺序、IDL/runtime extension 边界统一后，再允许按 spec 写代码。

---

## Strengths

1. **MCP 定位修正正确**
   - `specs/03-mcp-security-contract.md` 明确 MCP 不做 `move/attack/build` 等直接动作，AI 必须和 human 一样编写/部署 WASM。
   - 这是关键架构胜利：避免了 “AI special executor” 这类会破坏公平性、权限边界和测试模型的失败模式。

2. **单一执行器模型清晰**
   - `specs/01 §2.1` 明确唯一执行器为 `WasmSandboxExecutor`。
   - 这让 fuel metering、determinism、replay、anti-cheat 可以落在同一条路径上，抽象层次合理。

3. **Tick 生命周期分层方向正确**
   - COLLECT / EXECUTE / BROADCAST 是成熟多人仿真服务常见的成功模式。
   - BROADCAST failure 不回滚已提交 tick，这一点很重要，避免把非权威输出面变成世界状态的隐式事务参与者。

4. **Visibility 单函数原则正确**
   - `specs/05` 把 snapshot、MCP、WS、REST、replay 都要求走 `is_visible_to` 或明确例外。
   - 这比到处写局部过滤逻辑可靠得多，也适合做泄露检测测试。

5. **Source Gate / 服务端注入身份是正确边界**
   - `CommandIntent -> RawCommand -> ValidatedCommand` 的分层是直观的，新人能理解“不可信输入只有 sequence + action”。
   - `player_id/tick/source/auth` 由服务端注入，避免客户端伪造来源。

6. **ROADMAP 从“100% 完成”变成 checklist 是进步**
   - 即使当前仍有状态可信度问题，至少追踪粒度已经从口号式完成度变成模块/测试级追踪。

---

## Concerns

### A1 — Blocker: DESIGN/specs/IDL 对 Overload 的安全合同 split-brain

**现状**:

- `DESIGN.md §8` 已写：Overload 必须满足 `is_visible_to(target, attacker)`、同一目标 50 tick 全局冷却、结果静默，不能泄露 target fuel 状态。
- `specs/02 §3.12` 仍写：`target_player.fuel_budget > MAX_FUEL × 0.2 -> TargetFuelTooLow`，且“无 range 限制——Overload 是逻辑攻击”。
- `specs/08` 仍有 `TargetFuelTooLow` rejection，并在 Overload validator 中使用 `target_fuel_above(0.2)`。

**为什么会炸**:

这是典型的“安全修复只改设计总览，没改 executable spec”的失败模式。实现者通常会按更靠近代码生成/校验矩阵的 spec/IDL 落地，而不是按 DESIGN 的自然语言落地。结果是 R1 已经指出的信息泄露又被实现回来。

**必须改**:

- 从 `specs/02` 和 `specs/08` 删除/废弃 `TargetFuelTooLow` 的外显拒绝语义。
- Overload 校验表增加 `visible_target_player` 或等价语义，并定义“玩家可见”的实体判定：是看见任意该玩家实体？看见 Controller？还是看见 player metadata 即可？
- 定义 per-target global cooldown 的 key：建议 `target_player_id -> last_overload_tick`，不要用 `(source,target)`，否则多攻击者协同仍可穿透。
- 区分“validator 接受命令”和“apply 阶段因 fuel floor 无效果但静默成功”的语义。

---

### A2 — Blocker: Direction 与世界拓扑不一致，新人会实现出六边形移动

**现状**:

- `DESIGN.md §3.1a` 和 `specs/01 §1.1` 都定义正方形房间、N/S/E/W 四方向出口。
- `specs/02` 的 Move 示例/校验仍是 `TopRight`，并写“合法六边形邻居”。
- `specs/08` 的 `Direction` enum 是 `[Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft]`。

**为什么会炸**:

这不是小命名问题，而是空间模型合同问题。路径、距离、碰撞、range、room exit、可见性半径都会依赖网格拓扑。六边形 enum 一旦进入 SDK/IDL 生成，就会污染 TS/Rust SDK 和 replay schema，后续迁移成本很高。

**必须改**:

把 canonical direction 改成 `North/South/East/West` 或 `N/S/E/W`，并统一：DESIGN、specs/01、specs/02、specs/08、api/commands、SDK 示例、测试生成器。

---

### A3 — Blocker: Tick Phase 2b 顺序与并行语义仍未收敛

**现状**:

- `DESIGN.md` 当前倾向：`death_mark -> spawn -> combat -> death_cleanup` 是主线，`regeneration` 与 `decay` 可并行，只需在 `death_cleanup` 前完成。
- `specs/01 §3.4` 仍写 `.chain()`：`death_mark -> spawn -> regeneration -> combat -> decay -> death_cleanup`。

**为什么会炸**:

Tick 顺序是游戏语义，不只是实现细节。资源再生在 combat 前还是后，会影响同 tick 资源竞争、tower/DoT、spawn 出生即战斗、死亡清理前后可见性。更危险的是，DESIGN 说部分并行，spec 说全 chain 串行——实现者可能在 Bevy schedule 中写出“看起来 deterministic、实际语义不同”的系统图。

**建议裁决**:

R2 必须选择一个 canonical schedule，并在 DESIGN + specs/01 + tests 中写成同一张依赖图。我的倾向是采用 DESIGN 的分层模型：

```text
mainline: death_mark -> spawn -> combat -> death_cleanup
parallel-before-cleanup: regeneration, decay
```

但前提是明确 regeneration/decay 与 combat 没有读写冲突；如果有任何共享 component/resource，就回退到全 `.chain()`。

---

### A4 — High: “IDL 单一真相源”与“world.toml/Rhai 动态扩展”抽象冲突

**现状**:

- `specs/08` 前半部说 `game_api.idl` 是 Command/Validator/SDK/MCP schema 的单一真相源，“不一致即编译错误”。
- 同文件后半部又说所有特殊攻击通过 `world.toml [[custom_actions]] + [[special_effects]]` 动态注册，甚至可由 Rhai 新增 handler，SDK 和 MCP schema 自动包含所有已注册 action。

**为什么会炸**:

这是两个不同层级的抽象被硬塞成一个：

- compile-time IDL 适合稳定核心 API、ABI、基础 Command envelope。
- runtime registry 适合世界规则扩展、mod、custom action。

如果不拆清楚，会出现两种失败：
1. 生成器以为所有 action 编译期已知，运行时新增 action 后 SDK/validator 不认识。
2. 运行时 registry 太自由，破坏了 “不一致即编译错误” 的安全承诺。

**建议**:

改成两层合同：

- **Core IDL**: Command envelope、基础类型、host function ABI、registry query API。
- **World Action Manifest**: 每个 world 启动时生成/签名/版本化的 action manifest，SDK/MCP 读取 manifest 后获得 custom action schema。

这样“IDL 是基础协议真相源”，“manifest 是某个 world 的规则真相源”，二者不冲突。

---

### A5 — High: MCP schema 生成边界有回归风险

**现状**:

`specs/08` 写 IDL 会生成 “MCP tool schemas JSON”，同时 `specs/03` 明确 MCP 绝不包含 `swarm_move/swarm_attack/...` 这类直接游戏动作。

**风险**:

如果“从 Command IDL 自动生成 MCP schema”没有加边界，未来很容易把 gameplay commands 暴露成 MCP tools，重新引入 R1 已修正的 “MCP as controller” 问题。

**必须写清**:

- IDL 可以生成 MCP 的 `swarm_get_schema` / docs resource / action manifest，不得生成可执行 gameplay tool。
- MCP tool schema 与 WASM Command schema 是不同输出面：前者用于管理/观察/部署，后者用于玩家代码的 tick 输出。

---

### A6 — High: Snapshot/rollback 设计正确但成本没有工程边界

**现状**:

`specs/01 §3.5` 要求 EXECUTE 前完整 `world.snapshot()`，FDB commit 失败时 `world.restore(snapshot)`，并列出所有 Resource/Component。

**为什么会炸**:

全量 Bevy World 深拷贝每 tick 在小世界可行，但在 500 players、数十万 entity/component 的 world 中，内存带宽和 allocator 压力可能直接吃掉 500ms EXECUTE budget。这个模式在模拟器里常见，成功案例通常会配套：delta journal、copy-on-write、archetype-level clone benchmark 或 transaction-local mutation log。

**建议**:

R2 不必先实现优化，但必须给 acceptance gate：

- benchmark world size：players/entities/components 数量。
- snapshot+restore p95/p99 时间预算。
- memory overhead 上限。
- 若超预算，Phase 1 切到 mutation journal / diff log，而不是继续 full clone。

---

### A7 — High: Command limits 文档自相矛盾，会导致 DoS 防线错位

**现状**:

- `specs/02 §1.1`：顶层 `maxItems = 100`，总字节数 ≤ 256KB。
- `specs/02 §6`：`MAX_COMMANDS_PER_PLAYER = 100/tick`。
- 同文件字段级穷举表下方又写：每 tick 每玩家 ≤ 500 条指令，整批 ≤ 1MB。

**为什么会炸**:

限流/校验边界必须是“机器可执行合同”。100 vs 500、256KB vs 1MB 会让 gateway、WASM runtime、validator、SDK 四处各自取值。攻击者只需要找到最大口径入口，就能绕过较小口径的假设。

**建议**:

把 limits 抽成一张 canonical table，并要求所有 schema/validator/SDK 从同一常量生成。

---

### A8 — Medium: ROADMAP 的“全部完成”与 spec 裂口并存，追踪语义不可信

**现状**:

`ROADMAP.md` 总览显示 engine/sandbox/gateway/frontend 全部完成，specs/01-09 多处标为 ✅ 完整对齐。但 R2 实际仍存在 Overload、Direction、Tick order、limits 等合同裂口。

**为什么会炸**:

这是项目管理层面的“green dashboard theater”。当 ROADMAP 表示“实现完成”但 spec 自身仍互相矛盾，下游会误以为可以跳过设计收敛直接编码。

**建议**:

ROADMAP 的 ✅ 不应只表示“代码或文档有东西”，而应绑定三类证据：

1. DESIGN/spec/API 一致性检查通过。
2. 对应测试存在并通过。
3. 生成物与真相源无 diff。

---

### A9 — Medium: MCP transport 仍是会老化的技术选择点

**现状**:

DESIGN 架构图和 `specs/03` 仍写 `HTTP/SSE` / “仅 HTTP/SSE”。`specs/03` 已补 Host/CORS/body/batch 等安全合同，这是好事，但 transport contract 仍过窄。

**建议**:

不要把 SSE 写成长期唯一协议。建议改成：

- Browser-facing: HTTPS + Streamable HTTP/SSE fallback，强 Origin + Host 校验。
- Non-browser agent: HTTPS/mTLS 或 OAuth bearer，Origin 可缺失但必须走 client type / auth policy。
- Engine internal MCP server: bind 127.0.0.1，外部只通过 gateway/nginx。

---

## Missing

1. **Canonical invariants document**
   - 需要一页列出不可破坏的不变量：唯一执行器、MCP 不执行游戏动作、所有输出面 visibility、Tick deterministic、IDL/manifest ownership、rollback semantics。

2. **Spec convergence tests**
   - 当前缺少“文档一致性测试”的概念。至少应自动检查：Direction enum、RejectionReason、command limits、MCP forbidden tools、Tick schedule 关键字符串/生成物一致。

3. **World Action Manifest 版本策略**
   - 如果 world.toml/Rhai 可扩展 action，必须定义 manifest id、版本、hash、客户端缓存、回放使用哪个 manifest。

4. **Replay 与动态规则的绑定**
   - 回放不能只记录 command 和 state，还要记录当时的 world rules manifest/hash，否则未来规则变化后 replay 不能验证。

5. **Performance acceptance criteria**
   - snapshot/restore、visibility cache、path_find、serialization、broadcast fanout 都需要目标 world size 下的 p95/p99 budget。

6. **Newcomer implementation path**
   - 目前新人会在 DESIGN/specs/IDL/ROADMAP 之间迷路。需要明确：“实现者按 specs + generated constants 实现；DESIGN 是背景；ROADMAP 只追踪状态”。

7. **Error semantics for silent effects**
   - Overload 这类“validator 接受但 apply 可能无效果且静默”的 command，需要统一 result model，否则 TickTrace、refund、UX explanation 会各写各的。

---

## Phase Ordering

### R2 Gate — 先做 Spec Convergence Patch（必须）

1. 统一 Overload 合同：visibility、silent floor、global cooldown、TargetFuelTooLow 删除/内部化。
2. 统一 Direction：方形网格 N/S/E/W，更新 IDL/spec/API 示例。
3. 统一 Tick Phase 2b schedule：选择 canonical dependency graph，DESIGN 与 specs/01 同步。
4. 统一 Command limits：100/500、256KB/1MB 只能保留一组权威值。
5. 拆清 Core IDL vs World Action Manifest，禁止 gameplay command 生成 MCP executable tools。

### Phase 1 — 生成链与一致性防线

1. 从 canonical constants/IDL/manifest 生成 SDK、validator skeleton、API docs。
2. CI 增加 generated diff check。
3. CI 增加 forbidden MCP gameplay tools check。
4. CI 增加 docs/spec consistency smoke checks。

### Phase 2 — 核心 Tick + WASM 最小闭环

1. WasmSandboxExecutor + COLLECT cache。
2. Source Gate 注入身份。
3. Inline command loop。
4. Canonical Phase 2b schedule。
5. TickTrace + replay hash。

### Phase 3 — Visibility + MCP read/deploy surface

1. `is_visible_to` cache。
2. snapshot/MCP/WS/REST/replay leakage tests。
3. MCP deploy/list/validate/get_snapshot/get_replay，但不开放 gameplay actions。

### Phase 4 — Performance hardening

1. snapshot/restore benchmark。
2. visibility serialization benchmark。
3. path_find/query quotas。
4. broadcast gap recovery。

### Phase 5 — Dynamic rules / modding

1. World Action Manifest。
2. custom_actions schema/version/hash。
3. replay binds to manifest hash。
4. Rhai handler capability boundaries。

---

## Bottom Line

Swarm R2 的架构方向已经从 R1 的核心误区里走出来了：AI 不再是特殊玩家，MCP 不再是控制器，WASM 是统一执行面。这是正确的大方向。

但现在最危险的是“看起来每份文档都很完整，合起来却不是同一个系统”。在进入实现前，应先完成一次小而硬的 spec convergence。否则后续代码评审会变成反复争论“到底哪份文档才算真相源”，而不是验证实现是否正确。
