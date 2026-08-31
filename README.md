# Tesla 第三方仪表重新开发

当前版本：`0.1.0`（Phase 0/1 调查完成，Phase 2 MVP 已构建，等待实机验证）

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
- Mac 端单元测试通过；T113 目标 `libzkgui.so` 交叉编译成功。
- 目标库只引用 `open/read`，不引用 `write`；代码没有车辆控制发送 API。
- 已生成 `/tmp` ADB 临时运行 bundle；未刷写、未部署到实机。
- 当前 Mac 没有枚举到仪表，ADB 也没有设备，因此实机备份和上机验证仍待完成。

详细证据见：

- `docs/phase0-phase1-investigation.md`
- `docs/protocol-table.md`
- `docs/safe-deployment.md`
- `docs/mvp-status.md`

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
