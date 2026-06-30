# WASM Host Functions 参考

> 权威源: [api-registry.md](api-registry.md) §4；IDL YAML 与本文档必须同步。

> **权威定义见 [API Registry](api-registry.md) §4**。本文档提供实现指南。
>
> 详见 `specs/core/wasm-sandbox.md`

## 允许的 Import

| 模块 | 函数 | 用途 |
|------|------|------|
| `env` | `host_get_terrain` | 查询地形 |
| `env` | `host_get_objects_in_range` | 查询范围内的实体 |
| `env` | `host_path_find` | 寻路 |
| `env` | `host_get_world_config` | 读取世界配置 |
| `env` | `host_get_world_rules` | 读取世界规则 |
| `env` | `host_get_random` | 确定性随机字节 |
| `env` | `host_get_fuel_remaining` | 查询当前 tick 剩余 fuel |

## 详细签名

### host_get_terrain
```c
i32 host_get_terrain(room_id: u32, out_ptr: i32, out_len: i32) -> i32
```
返回 room_id 对应房间的完整地形数据，写入 `out_ptr` 缓冲区（最大 `out_len` 字节）。
- 返回字节数 ≤ 8KB
- 返回值：实际写入字节数（≥0），负数=错误码

### host_get_objects_in_range
```c
i32 host_get_objects_in_range(x: i32, y: i32, range: u32, out_ptr: i32, out_len: i32) -> i32
```
返回以 (x,y) 为中心、range 半径内的实体 JSON 列表。
写入 `out_ptr` 指向的 WASM 线性内存缓冲区（最大 `out_len` 字节）。
返回值：>=0 = bytes_written，<0 = canonical ABI error code（见 API Registry §4.5）。
- 每 tick 最多调用 5 次（计入 host call budget）

### host_path_find
```c
i32 host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, opts_ptr: i32, opts_len: i32, out_ptr: i32, out_len: i32) -> i32
```
从 (from_x, from_y) 到 (to_x, to_y) 的最短路径。
`opts_ptr`/`opts_len` 传递寻路选项（JSON，可为空：`opts_len=0` 使用默认设置）。
写入 `out_ptr` 缓冲区。
- 每 tick 最多调用 10 次（计入 host call budget）

### host_get_world_config
```c
i32 host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32
```
按 key 读取世界配置项（如 `world.rules.rs` 等）。

### host_get_world_rules
```c
i32 host_get_world_rules(rule_id_ptr: i32, rule_id_len: i32, out_ptr: i32, out_len: i32) -> i32
```
按 `rule_id` 查询指定规则模块的数据。`rule_id_len=0` 时返回完整规则集。
写入 `out_ptr` 缓冲区。
- 每 tick 最多调用 1 次

### host_get_random
```c
i32 host_get_random(sequence: u64, out_ptr: i32, out_len: i32) -> i32
```
返回确定性随机字节。引擎内部 PRNG 使用 `derive_rng("swarm.host_random.v1", world_seed, tick, actor_or_entity_id, sequence)` 派生随机流；编码采用 length-delimited field encoding（field_tag + uLEB128 length + bytes），所有整数使用 little-endian 固定宽度，domain separator 必须作为第一个字段写入，保证不同 tick、actor/entity/source 与 `u64 sequence` 产生独立且可 replay 的随机序列。
写入 `out_ptr` 缓冲区。
- 最大输出：256 bytes
- fuel 成本：见 [API Registry](api-registry.md) §4.4，canonical 为 `200 + 10/32 bytes`
- 每 tick 最多调用 10 次

### host_get_fuel_remaining
```c
u64 host_get_fuel_remaining() -> u64
```
返回当前 WASM store 剩余 fuel budget。该函数只读，不观察真实时间、CPU 负载或宿主资源状态。
- 最大输出：8 bytes
- fuel 成本：见 [API Registry](api-registry.md) §4.4，canonical 为 `20`
- 无单独次数上限，按基础 fuel cost 计入 Host call 总预算

## Host Call Budget

所有 host function 调用计入总预算：
- **总计**: 1000 次/tick
- `host_path_find`: 10 次
- `host_get_objects_in_range`: 5 次
- `host_get_random`: 10 次
- `host_get_fuel_remaining`: 无单独次数上限
- 其他: 共享剩余配额

超出预算 → 返回 canonical ABI error code `-4 ERR_BUDGET_EXHAUSTED`（per-call）或 `-5 ERR_PLAYER_BUDGET`（per-player）。权威错误码优先级见 [API Registry](api-registry.md) §4.5。

## 输出上限

> 权威定义见 [API Registry](api-registry.md) §4.3。

| 函数 | 最大输出 |
|------|---------|
| `host_path_find` | **8 KB** |
| `host_get_objects_in_range` | **64 KB** |
| `host_get_world_config` | **16 KB** |
| `host_get_world_rules` | **16 KB** |
| `host_get_terrain` | **8 KB** |
| `host_get_random` | **256 bytes** |
| `host_get_fuel_remaining` | **8 bytes** |

## 安全约束

> 权威容量限制见 [API Registry](api-registry.md) §5。

| 约束 | 值 |
|------|-----|
| 模块大小上限 | 5 MB |
| 输出 JSON 上限 | 256 KB |
| WASM 内存上限 | 64 MB |
| Fuel 上限 | 10,000,000 |
| Host call 总预算 | 1,000/tick |
| 网络访问 | ❌ 禁止（无 WASI socket） |
| 文件系统 | ❌ 禁止（无 WASI fs） |
| 禁止 import | ❌ Move/Attack/Build/Spawn 等 mutating 函数 |

## 设计合同

所有游戏状态变更必须通过 `tick() → Command[]` JSON 延迟模型提交。
Host function 只提供**只读查询**。WASM 模块不能直接修改世界状态。
