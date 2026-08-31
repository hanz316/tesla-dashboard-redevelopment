# dashboard-build-0.1-hardware-validated

状态：`HARDWARE_VALIDATED`

该基线证明自定义 T113 FlyThings 应用可以通过 Wi-Fi ADB 从 `/tmp` 在真实仪表运行，并保持车辆 UART 严格只读。

## 已冻结的构建产物

| 文件 | SHA-256 |
|---|---|
| `libzkgui.so` | `79ff08a97c291e55a1a3af40e38402a2cd1a20d068c288f5f2dcc82d967c9bcb` |
| `main.ftu`（实机版本） | `a8abc8bc78b0c4aaa2115330edcffae72f630976d06c93aa890e2a133d579110` |
| `EasyUI.cfg` | `264571f53722c6a9eecbf7e353389d909c63140729de9a280f6897f963b20ef9` |

完整本目录哈希见 `SHA256SUMS`。

## 实机验证

- Device：`Zkswe_T113_SPINOR`
- SoC：dual-core Cortex-A7 / ARMv7
- RAM：249,964 KiB
- System：ZKOS 2.6.2 / FlyThings V2.1 / EasyUI 2.2.0
- 启动方式：`/tmp/EasyUI.cfg`
- 映射库：`/tmp/tesla-dashboard-mvp/lib/libzkgui.so`
- `zkswe`：running
- RSS：3,664 KiB
- VSIZE：27,240 KiB
- UART：FD 18 -> `/dev/ttyS5`
- FD mode：`lr-x------`，只读
- Framebuffer：1920×480 landscape，由 480×3840 双缓冲 framebuffer 解码
- ABI：实机 `libstdc++.so.6.0.22` 支持到 `CXXABI_1.3.10` / `GLIBCXX_3.4.22`

证据位于：

- `device-probe/`
- `runtime-validation/`
- `framebuffer.png`

## SPI NOR 原始备份

原始分区镜像保存在本机只读备份目录：

`/Users/hanssmacbookair/tesla-dashboard-redevelopment/captures/raw-mtd-10.80.6.196:5555-20260831T064438Z/`

Git 仅保存分区表和 SHA-256 引用，见 `flash-reference/`。完整镜像共 32 MiB：

- `mtd0-uboot.img`
- `mtd1-boot.img`
- `mtd2-res.img`
- `mtd3-config.img`
- `mtd4-boot_logo.img`
- `mtd5-data.img`

## 文件级备份

- `/res`：1567 files
- `/etc`：15 files
- `/lib`：35 files
- `/late`：50 files
- `/bin`：43 files
- `/sbin`：2 files
- `/system`：71 files
- `/data`：28 regular files；3 runtime sockets skipped

完整文件备份保存在 `captures/`，不进入 GitHub 以避免把设备镜像和运行时配置混入源码历史。

## 工具链

| 工具链 | SHA-256 |
|---|---|
| FlyThings `t113_musl.tar.gz` | `d11ba62324b0382f448b1a015d7dc08e422b0113d5957eef02165cb7c4deb53c` |
| FlyThings IDE `toolchain-t113.zip` | `2bef92be18025dee4d82601b5d58b1c755a94162cd4b8d8db4ed9ed6d9c246a6` |

构建入口：`scripts/build_t113.sh`。

## 部署与回滚

部署只写：

```text
/tmp/EasyUI.cfg
/tmp/tesla-dashboard-mvp/lib/libzkgui.so
```

实机断电/重启后 `/tmp` 清空，已观察到系统自动恢复 `/res` stock 应用 PID 57。没有写入 flash、`/res` 或 `/data`。

## 已知限制

- 该版本复用 stock `main.ftu`，用于硬件可运行性验证，不是产品 UI。
- Developer 字符串在 stock 小控件中有截断/重叠。
- 尚未完成真实车辆逐门、逐档位、轮位验证。
- UART Record/Replay/Developer Mode 在 Build 0.2/0.3 实现。
