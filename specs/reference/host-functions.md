# WASM Host Functions 参考

> 权威源: [game_api.idl.yaml](game_api.idl.yaml) → [api-registry.md](api-registry.md) (生成)

> **权威定义见 [API Registry](api-registry.md) §4**。本文档提供实现指南。
>
> 详见 `specs/core/04-wasm-sandbox.md`

## 允许的 Import

| 模块 | 函数 | 用途 |
|------|------|------|
| `env` | `host_get_terrain` | 查询地形 |
| `env` | `host_get_objects_in_range` | 查询范围内的实体 |
| `env` | `host_path_find` | 寻路 |
| `env` | `host_get_world_config` | 读取世界配置 |
| `env` | `host_get_world_rules` | 读取世界规则 |

## 详细签名

### host_get_terrain
```c
i32 host_get_terrain(x: i32, y: i32) -> i32
```
返回指定坐标的地形类型：0=Plain, 1=Wall, 2=Swamp, 3=Lava。

### host_get_objects_in_range
```c
i32 host_get_objects_in_range(x: i32, y: i32, range: i32, out_ptr: i32, out_len: i32) -> i32
```
返回以 (x,y) 为中心、range 半径内的实体 JSON 列表。
写入 `out_ptr` 指向的 WASM 线性内存缓冲区（最大 `out_len` 字节）。
返回值：0=成功，负数=错误码。
- 每 tick 最多调用 5 次（计入 host call budget）

### host_path_find
```c
i32 host_path_find(from_x: i32, from_y: i32, to_x: i32, to_y: i32, out_ptr: i32, out_len: i32) -> i32
```
从 (from_x, from_y) 到 (to_x, to_y) 的最短路径。
写入 `out_ptr` 缓冲区。
- 每 tick 最多调用 10 次（计入 host call budget）

### host_get_world_config
```c
i32 host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32
```
按 key 读取世界配置项（如 `world.rules.rs` 等）。

### host_get_world_rules
```c
i32 host_get_world_rules(out_ptr: i32, out_len: i32) -> i32
```
返回当前世界规则集的 JSON。

## Host Call Budget

所有 host function 调用计入总预算：
- **总计**: 1000 次/tick
- `host_path_find`: 10 次
- `host_get_objects_in_range`: 5 次
- 其他: 共享剩余配额

超出预算 → 返回 -1，tick 继续执行（非致命错误）。

## 输出上限

> 权威定义见 [API Registry](api-registry.md) §4.3。

| 函数 | 最大输出 |
|------|---------|
| `host_path_find` | **8 KB** |
| `host_get_objects_in_range` | **64 KB** |
| `host_get_world_config` | **16 KB** |
| `host_get_world_rules` | **16 KB** |
| `host_get_terrain` | **8 KB** |

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
