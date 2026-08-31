# 仪表数据接口契约（给 ChatGPT 仪表线程）

更新：2026-08-31

本文件定义仪表 UI/功能开发可以消费的数据接口。所有代码与实机验证
都在 GitHub `main` 分支（当前 HEAD 见 `git log`）。

## 1. 数据源现状

| 数据源 | 状态 | 说明 |
|---|---|---|
| Original MCU（`/dev/ttyS5`） | ✅ 实机验证可用 | 40fps、0 CRC 错误；speed/gear/soc/range/doors/temp 已实测 |
| UART 录制回放 | ✅ 可用 | 真实录制在本地，模拟器可回放；录制格式见下文 |
| Simulation | ✅ 可用 | `SimulationAdapter` |
| Commander | 🔶 接口预留，数据未接入 | SDK 来自 Commander 协议线程；传输（BLE/PhoneBridge）待接 |
| PhoneBridge | 🔶 接口预留 | 未来经 Wi-Fi 收手机数据 |

## 2. 统一接口 `IDataSource`

`include/dashboard/data_source.h`：

- `VehicleState state()` —— 全部车辆信号（每个 `Signal<T>` 带
  value/valid/timestamp/source/quality/unit）
- `DataSourceHealth health()` —— status/last_update/packets/errors
- `void tick(now_ms)` —— 供上层定期调用，源自身处理过期
- `name()` / `source()`

UI 只通过 `IDataSource` 读 `VehicleState`，不关心来源。

## 3. VehicleState 信号（`include/dashboard/vehicle_state.h`）

### 实机已验证（Original MCU）

- `speed`（km/h，实测 0 与静止）
- `gear`（P/R/N/D，实车确认 Park↔Drive）
- `soc`（MCU 值恒定 97，**不可信**，未来用 Commander `actual_soc` 覆盖）
- `range`（km，实测与车辆一致 ±1）
- `door_fl/fr/rl/rr`、`frunk`、`trunk`（FL=bit0 实车确认）
- `tire_fl/fr/rl/rr`（bar，静止不报，待行驶验证）
- `temperature_primary/secondary`（实测 22°C）

### 预留（Commander 提供，UI 可直接读）

- 功率：`front_motor_power`、`rear_motor_power`、`total_motor_power`
- 电池/BMS：`pack_voltage`、`pack_current`、`pack_power`、
  `energy_remaining`、`energy_full_estimate`、`actual_soc`、
  `battery_temperature`、`max/min_cell_voltage`、`cell_delta`
- DC/DC：`dcdc_*`
- 刹车温度：`brake_temp_fl/fr/rl/rr`
- 气候：`ambient_temperature`、`cabin_temperature`
- `accelerator_position`

未接数据时这些信号 `valid=false`，UI 显示 `--` / 不可用，不要显示 0 或模拟值。

## 4. 信号仲裁（多源时）

`SignalSourcePriority`（data_source.h）：每个信号组可声明
`primary`/`fallback`。示例：

- speed/gear/doors/tires：Primary=OriginalMcu，Fallback=Commander
- battery/motor 功率：Primary=Commander

合并规则：Primary 新鲜则用 Primary；否则 fallback 新鲜则用 fallback；
否则不可用。不要"谁最后写就显示谁"。

## 5. 录制格式（UART Replay）

原始字节流，帧格式 `2E CMD LEN PAYLOAD CHECKSUM`（checksum =
`~(CMD+LEN+sum(PAYLOAD)) & 0xFF`）。回放工具：

- `apps/simulator_gui/replay_source.{h,cpp}` —— 按捕获节奏喂给 adapter
- 实机录制：`captures/uart-record-realcar-*.bin`（SHA-256 在
  `docs/protocol-table.md`）

## 6. Commander 接入点（预留，不要现在实现协议）

- `CommanderAdapter`（source_adapters.h）：实现 `IDataSource`，读只读
  - `ICommanderTransport`：`NativeBleTransport`（仪表 BLE GATT central，
    能力 LIKELY）/ `PhoneBridgeTransport`（正式 fallback）
  - `CommanderStatus`：connected/authenticated/vin/firmware/packet_rate…
  - `RawCanFrame`：未来 Raw CAN decoder 的输入结构
- 安全边界：第一阶段只读，禁止车辆控制 / Raw CAN TX / 配置写入
- 模块化：未来 OTA 可单独更新 Commander 模块（feature flag），不影响
  核心仪表

## 7. UI 可立即使用的数据流示例

```cpp
dashboard::OriginalMcuAdapter adapter;          // 或任意 IDataSource
adapter.feed(bytes, len, now_ms);               // UART 数据
const auto& s = adapter.state();                // 读信号
if (s.speed.valid) { /* 显示 s.speed.value km/h */ }
else { /* 显示 "--" */ }
```

模拟器里已有完整示例（`apps/simulator_gui/main.cpp` 的
`renderPremium`），含梯形安全区（上角 116px、下角 51px）。
