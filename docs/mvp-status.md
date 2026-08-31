# Build 0.1 硬件验证状态

状态：`HARDWARE_VALIDATED`。Build 0.1 的任务已经完成，不再作为当前开发目标。

## Build 0.2 当前状态

状态：`IN_PROGRESS`。目标是产品化数据层：统一数据源抽象、信号新鲜度
管理和多数据源接入准备。Build 0.1 的功能保持兼容，不删除、不重写。

### 已实现

- `IDataSource` 接口：`name / source / state / health / tick`
- `SimulationAdapter`：driving/doors/tires 注入与 `disconnect`
- `CommanderAdapter` / `PhoneBridgeAdapter`：占位数据源
- `VehicleState` 扩展：trip、lighting、speed limit、AP/ADAS、电池/电机、
  转向/踏板/轮速等信号
- `FreshnessPolicy` + `Signal::invalidateIfStale`：
  driving 1 s、vehicle 2 s、lighting 3 s、tire/temperature 30 s
- `OriginalMcuAdapter::tick/reset`、frame listener、`DataSourceHealth`
- `ProtocolParser::reset`
- 实机 `DeviceRuntime` 每轮空读调用 `tick()`，UI 显示数据源状态
  （`DATA` / `STALE` / `ERR`），保持原 1920×480 布局

### 验证

- Mac 构建 + 单元测试：通过（覆盖 parser、adapter、stale invalidation、
  reset、frame listener、SimulationAdapter）
- T113 交叉编译：通过；`libzkgui.so` 仍只引用 `open/read/close`，无 `write`

### 待办（按依赖顺序）

1. 实车录制静止/逐门/逐档位/轮胎 session，确认 door 与 tire mapping。
2. 从录制数据反推 lighting、speed limit、AP/ADAS command 解码。
3. UART Record/Replay 数据源 + Developer Mode。
4. 最终产品 UI 与多主题。

## 已完成

### 数据层

- `OriginalMcuAdapter`
- 增量 UART parser：分包、粘包、噪声重同步、checksum 错误统计
- `VehicleState`
- 每个 signal 包含 `value / valid / timestamp / source / quality / unit`
- Speed、Gear、SOC、Range
- Door/Frunk/Trunk（mapping 可配置，当前标记 Inferred）
- Tire Pressure（物理轮位 mapping 可配置）
- 两类温度原始解码
- Unknown command 和 parser health 统计

### 安全

- adapter 没有发送 API
- T113 runtime 以 `O_RDONLY` 打开 `/dev/ttyS5`
- T113 ELF 不引用 `write`
- 不包含 Commander、Camera 或车辆控制实现

### UI/MVP

- 复用原生 1920×480 `main.ftu` 和 `/res/ui` 资源
- 更新 speed、gear、SOC、range
- 使用现有文本控件显示 door summary、四轮胎压、时钟
- 显示 UART、packet、CRC、unknown command health

### 构建验证

- Mac AppleClang build：通过
- 单元测试：通过
- simulator：通过
- T113 GCC 6.4.1/musl cross build：通过
- 输出：`build-t113/libzkgui.so`
- 目标格式：ELF 32-bit LSB ARM EABI5 shared object
- 临时 bundle：`dist/temporary-adb`

## Build 0.1 已完成的实机验证

- Wi-Fi ADB 已连接真实仪表。
- 自定义库从 `/tmp` 启动成功。
- 实机 base library ABI 已核对。
- `/dev/ttyS5` 只读 FD 已核对。
- framebuffer 已读取并验证。
- SPI NOR 和关键系统目录已备份。
- 断电回滚 stock 已验证。

## 仍属于后续 Build 的工作

- 当前 UI 复用原布局，不是最终产品 UI。
- door/tire 物理位置仍需真实车辆逐项确认。
- UART Record/Replay/Developer Mode 尚未完成。
- 多主题、Trip、Warning、PhoneBridge 等按产品化 Roadmap 开发。

## 下一可执行里程碑

Build 0.1-real：

1. 在仪表设置里启用 ADB/USB debug，或通过同一 Wi-Fi 获取 IP 后 `adb connect IP:5555`。
2. 运行只读 probe/backup。
3. 核对 ABI 和 `/tmp`。
4. 运行临时 bundle。
5. 只观察，不发送控制。
6. 录制静止车辆、逐档位、逐门、轮胎位置 session。
7. 修正 mapping 并形成 Build 0.2。
