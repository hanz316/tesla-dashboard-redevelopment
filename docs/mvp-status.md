# Build 0.1 MVP 状态

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

## 未完成/不能宣称完成

- 没有在仪表实机运行，因为 Type-C 未枚举、ADB 无设备。
- 没有实机 UART 录制，因此 door/tire 物理位置尚未最终确认。
- 没有核对实机 base library 的精确 ABI；第一次 deploy 前必须核对。
- 没有实机 backup；当前只有两个 OTA 原包和提取副本。
- 当前 UI 复用原布局，不是最终重设计 UI。
- recording/replay/simulation UI 属于 Phase 3；当前只有 host deterministic simulation。

## 下一可执行里程碑

Build 0.1-real：

1. 在仪表设置里启用 ADB/USB debug，或通过同一 Wi-Fi 获取 IP 后 `adb connect IP:5555`。
2. 运行只读 probe/backup。
3. 核对 ABI 和 `/tmp`。
4. 运行临时 bundle。
5. 只观察，不发送控制。
6. 录制静止车辆、逐档位、逐门、轮胎位置 session。
7. 修正 mapping 并形成 Build 0.2。
