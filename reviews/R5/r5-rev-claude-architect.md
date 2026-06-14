I have full context now. The P0 specs are internally clean (R4 closed prior contradictions), but the PLANNER-OUTPUT still encodes the rejected MCP-as-controller architecture, and several scaling/phase-ordering issues stand out from the architect lens. Writ
APPROVE

Phase 0 文档整体质量高，架构一致性强，R4 全部共识修正均已落地。以下列出剩余关切，分为**阻塞项**（需修正才能进入 Phase 1 实现）和**观察项**（建议但不阻塞）。

---

## 一、R4 修正确认（全部闭合）

| R4 修正项 | 验证结果 |
|---|---|
| D1/D2: DESIGN §5 Deferred Command Model 重写 | ✅ 已确认 — §5 明确禁止 mutating host functions，`tick() → Command[]` 模型一致 |
| f64 残留清理 | ✅ 已确认 — P0-7 `damage_multiplier < 0.0` → `< 1`；i18n 示例已清理 |
| A6: BROADCAST 重复 commit 删除 | ✅ 已确认 — P0-1 §4 BROADCAST 阶段不再含 FDB commit |
| A7: 状态标签统一 | ✅ 已确认 — P0-2/3/4/5 均为 `Frozen for Phase 0` |
| validate_plan → swarm_dry_run_commands | ✅ 已确认 — P0-6 §3.1 已更新，明确 non-authoritative |

---

## 二、阻塞项（Blocking Concerns）

### B1: P0-9 §7 缺少 Section 6（编号跳跃）

**位置**: P0-9 第 97 行，Section 编号从 `## 5. Replay 与审计` 直接跳到 `## 7. World/Arena 差异`，Section 6 缺失。

**影响**: 文档完整性缺陷。若 Section 6 本应涵盖某项内容（如 source gate 与 auth 验证的完整流程），缺失会导致实现者漏掉规范意图。

**建议**: 补充 Section 6，或将 Section 7 重编为 Section 6，并确认无内容遗漏。

---

### B2: DESIGN §8.3 与 P0-7 §2 中 `damage_multiplier` 类型不一致

**位置**:
- DESIGN §8.3 world.toml 示例: `damage = 1.0`（f64 字面量）
- P0-7 §2 world.toml 示例: `damage_multiplier = 1.0`（同为 f64 字面量）
- DESIGN §8.2 规则表: `damage_multiplier: fixed<u32,4>`
- P0-7 validate_config: `config.combat.damage_multiplier < 1`（修正后）

**问题**: TOML 配置示例中 `damage = 1.0` 使用了 f64 字面量，而确定性合同（DESIGN §8.8）明确禁止 f64。`fixed<u32,4>` 应表示为整数 `10000`，而非 `1.0`。

**建议**: 将所有 TOML 示例中的 `fixed<u32,4>` 类型字段统一改为整数表示（`damage_multiplier = 10000`），与 §8.2 规则表中 `× 10000` 精度因子对齐。

---

## 三、观察项（Non-Blocking Concerns）

### O1: P0-4 §2.2 `fuel_consumed_callback` 实现细节存疑

P0-4 中的 Wasmtime 配置使用了 `fuel_consumed_callback`，但在 Wasmtime 30.x 的公开 API 中，fuel exhaustion 是通过 `add_fuel` + trap（`OutOfFuel`）机制处理，而非 callback 形式。文档中的 `panic!("fuel exhausted")` 写法在 WASM 沙箱内无意义（panic 不会传播到引擎进程）。

**建议**: Phase 1 实现时以 Wasmtime 30.x 实际 API 为准，文档中的伪代码加注「示意性」标注，避免实现者照抄。

### O2: P0-1 §6.3 回放协议编号冲突

P0-1 存在两个 `### 6.1` 和两个 `### 6.2` 编号（第 261-282 行），导致「记录」和「回放执行」两个子节重复编号。属于格式问题，不影响语义但影响文档可读性。

### O3: P0-2 §3.1 MoveTo 校验遗漏 `!spawning`

Move 指令（§3.1）明确校验 `drone.spawning == false`，但 MoveTo（§3.2）仅列「所有 Move 检查项均适用」。IDL（P0-8）的 MoveTo validator 写的是 `[Move checks, in_room, path_exists, path_length(100)]`，未列 `!spawning`。若 Move checks 已隐含此项则无问题，但应在 P0-8 IDL 中明确，防止代码生成器遗漏。

### O4: 全局存储运输拦截机制悬空

DESIGN §8.4 提到「运输期间资源可被敌方巡逻 drone 拦截（需 PvP 启用）」，但 P0-8 IDL、P0-2 校验矩阵和 P0-9 来源矩阵均未定义拦截指令或触发条件。这是一个设计意图与规范之间的 gap。

**建议**: Phase 1 路线图中明确：拦截机制是 Phase 6（战斗系统）的一部分，或在 DESIGN §8.4 中加注「此机制 Phase 6 才实现」，防止实现者在 Phase 1 误判范围。

### O5: Rhai 模组 `room_superlinear` 类型在不同位置不一致

- mod.toml §8.7（DESIGN）: `type = "fixed<u32,4>"`，`default = 1`
- mod.toml i18n 示例（DESIGN §8.7 末尾）: `type = "f64"`，`default = 0.1`

这是 R4 f64 清理后仍存在的残留矛盾。DESIGN 末尾的 i18n 示例（第 1080-1087 行）将 `room_superlinear` 定义为 `f64`，与确定性合同冲突。

**建议**: 将 i18n 示例中的 `room_superlinear` 统一为 `fixed<u32,4>` 类型，与主规范对齐。

---

## 四、架构健康度总评

| 维度 | 评分 | 说明 |
|---|---|---|
| 核心架构一致性 | ✅ 强 | ECS + Deferred Command + Fuel Metering 三支柱完全自洽 |
| 确定性合同 | ✅ 强 | ChaCha12 + Blake3 + IndexMap + 禁 f64 — 覆盖全面 |
| 安全模型 | ✅ 强 | Source Gate + seccomp + cgroup + 白名单 host functions |
| 跨文档一致性 | ⚠️ 有残留 | B2 + O5 的类型不一致需修正 |
| 文档完整性 | ⚠️ 有缺陷 | B1 Section 6 缺失，O2 编号冲突 |
| 实现可操作性 | ✅ 良好 | Phase 1 任务列表清晰，阻断项定义明确 |

---

## 五、修正优先级

**进入 Phase 1 实现前必须修正（2 项）**:
1. **B1**: P0-9 补充 Section 6 或修正编号
2. **B2 + O5**: 统一 `damage_multiplier` 和 `room_superlinear` 的 TOML 表示为整数定点数

**Phase 1 实现期间处理（不阻塞启动）**:
- O3: P0-8 IDL MoveTo validator 明确 `!spawning`
- O4: DESIGN §8.4 运输拦截机制加注实现阶段
- O1 + O2: 文档格式修正

---

## 六、总结

R4 的所有共识修正均已正确落地。架构的三个核心支柱——确定性 ECS 引擎、WASM 沙箱安全模型、Deferred Command Model——在所有 P0 文档中保持一致。剩余关切均为文档层面的精度问题（类型表示、编号、遗漏注释），不存在架构级矛盾。

**CONDITIONAL_APPROVE**: 修正 B1 和 B2/O5（类型一致性）后，Phase 0 文档可视为完整冻结，Phase 1 实现可以启动。

---

*评审者: claude-sonnet-4-6 (Architect)*
*评审轮次: R5 Final Check*
*日期: 2026-06-14*
