# Tesla 第三方仪表重新开发

当前稳定基线：`dashboard-build-0.1-hardware-validated`

当前开发阶段：Build 0.2 产品化重新开发。

本仓库以原仪表 MCU 为第一版车辆数据源，数据链严格分层：

```text
/dev/ttyS5 (38400, read-only)
        -> OriginalMcuAdapter (IDataSource)
        -> VehicleState (freshness policy)
        -> FlyThings mainActivity / host simulator
```

Build 0.2 引入统一数据源接口 `IDataSource`，为后续 Replay /
Simulation / Commander / PhoneBridge 数据源预留同一 `VehicleState`
输出契约；每个信号带来源、质量、时间戳和单位，并按 `FreshnessPolicy`
自动过期失效。

## 当前结果

- 两个 OTA 包均已完整提取；英文版 1565 个文件，中文版 1548 个文件。
- 已确认平台为 Allwinner T113、32-bit ARM EABI5、musl hard-float、FlyThings/EasyUI。
- 已确认车辆 UART 为 `/dev/ttyS5`、38400 baud；协议帧为 `2E CMD LEN PAYLOAD CHECKSUM`。
- 已实现只读 `OriginalMcuAdapter` 和带来源、质量、时间戳、单位的 `VehicleState`。
- Build 0.2 已实现 `IDataSource` 抽象、`SimulationAdapter` 和过期失效机制。
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

## 下一步（Build 0.2）

- 实车录制 door/tire 物理位置并修正 mapping（从 Inferred 升为 Confirmed）。
- 根据录制 session 扩展 UART command 解码（lighting、speed limit、AP/ADAS）。
- UART Record/Replay 数据源与 Developer Mode。
- 多主题与最终产品 UI（保留 1920×480 布局与 `/res` 资源）。

## 构建与验证

Mac 端：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/dashboard_simulator
```

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
