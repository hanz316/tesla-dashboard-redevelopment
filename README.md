# Tesla 第三方仪表重新开发

当前稳定基线：`dashboard-build-0.1-hardware-validated`

当前开发阶段：Build 0.2 产品化重新开发。

本仓库以原仪表 MCU 为第一版车辆数据源，数据链严格分层：

```text
/dev/ttyS5 (38400, read-only)
        -> OriginalMcuAdapter
        -> VehicleState
        -> FlyThings mainActivity / host simulator
```

## 当前结果

- 两个 OTA 包均已完整提取；英文版 1565 个文件，中文版 1548 个文件。
- 已确认平台为 Allwinner T113、32-bit ARM EABI5、musl hard-float、FlyThings/EasyUI。
- 已确认车辆 UART 为 `/dev/ttyS5`、38400 baud；协议帧为 `2E CMD LEN PAYLOAD CHECKSUM`。
- 已实现只读 `OriginalMcuAdapter` 和带来源、质量、时间戳、单位的 `VehicleState`。
- Mac 端单元测试通过；T113 目标 `libzkgui.so` 交叉编译成功并已在真实仪表运行。
- 目标库只引用 `open/read`，不引用 `write`；代码没有车辆控制发送 API。
- `/tmp` ADB 临时运行、进程映射、UART FD、日志和 framebuffer 已验证。
- 32 MiB SPI NOR 六分区原始备份和关键系统文件备份已完成。
- 断电恢复 stock 应用已验证。

详细证据见：

- `docs/phase0-phase1-investigation.md`
- `docs/protocol-table.md`
- `docs/safe-deployment.md`
- `docs/mvp-status.md`
- `docs/hardware-validation-2026-08-31.md`

## 构建与验证

Mac 端：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/dashboard_simulator
```

### 1920×480 图形模拟器（开发平台）

与 T113 实机共用同一份 `dashboard_core`；可用真实 UART 录制回放或合成
数据驱动，用于先开发/预览 UI、动画与功能，再上车验证：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel --target dashboard_simulator_gui

# 交互窗口（1920×480 逻辑，1152×288 窗口）
./build/dashboard_simulator_gui captures/uart-record-realcar-geardoor.bin

# 无头模式：渲染 3 帧存 BMP（CI/验证用）
./build/dashboard_simulator_gui --screenshot /tmp/dash.bmp <recording>

# 无头模式：回放约 1.2s 后打印解析状态（数据链路验证）
./build/dashboard_simulator_gui --dump-state <recording>
```

快捷键：`Space` 切换回放/合成、`S` 冻结数据（观察 stale → `--`）、
`↑/↓` 调整合成速度、`Esc` 退出。

依赖：`brew install sdl2 sdl2_ttf sdl2_image pkgconf`

T113 目标：

```bash
bash scripts/build_t113.sh
bash scripts/package_temporary_bundle.sh
```

## 安全边界

- 不运行 `sendProtocolTo`，不发送 `0x88` 控制命令。
- 不使用 `update.img`、`zkautoupgrade`、remount 或 flash 进行首轮验证。
- 首次上机只允许 ADB 写入 `/tmp`，断电恢复原程序。
- 在实机只读调查和备份完成前，不允许持久化部署。
