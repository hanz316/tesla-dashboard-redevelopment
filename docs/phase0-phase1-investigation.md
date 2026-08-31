# Phase 0/1 系统与硬件调查报告

调查日期：2026-08-30（America/Toronto）

更新：2026-08-31 已通过 Wi-Fi ADB 连接实机并完成 SPI NOR、`/res`、`/etc`、`/lib`、`/late`、`/bin`、`/sbin`、`/system`、`/data` 备份。Type-C 仍不能枚举，但已不再阻塞系统读取。最新证据见 `hardware-validation-2026-08-31.md`。

## 1. 结论摘要

该设备不是 Android 应用仪表，而是 Allwinner T113 上运行的 FlyThings/EasyUI Linux 应用。OTA 包不是整机固件，而是 `/res` 类应用分区内容：UI、`libzkgui.so`、应用附带库、工具和翻译资源。启动入口由 `EasyUI.cfg` 指向 `/res/lib/libzkgui.so`。

车辆数据链已确认是原 MCU 经 `/dev/ttyS5`、38400 baud 发送私有 UART 帧。第一版可以保留 MCU，重新实现应用层，无需先重做 Tesla CAN。

当前 Type-C 连接没有被 macOS 枚举，ADB 也看不到设备，所以无法读取实机的 kernel、分区、driver、base filesystem 或完成备份。固件分析没有因此中止。

## 2. Type-C / ADB 只读检查

### 2.1 当前观测

| 检查项 | 结果 | 状态 |
|---|---|---|
| macOS `SPUSBDataType` | 空列表 | NOT PRESENT |
| USB4/Thunderbolt 两端口 | `receptacle_no_devices_connected` | NOT PRESENT |
| 外接物理磁盘 | 无 | NOT PRESENT |
| 新增 `/dev/cu.*` / `/dev/tty.*` | 无；只有 Mac 调试口和蓝牙音频设备 | NOT PRESENT |
| 新增网络接口 | 无 USB/RNDIS/NCM 网卡 | NOT PRESENT |
| ADB 37.0.1 `devices -l` | 空列表 | NOT PRESENT |
| VID/PID/USB descriptors | 无法读取，因为未枚举 | UNKNOWN |

这不是“ADB 驱动未安装”造成的假阴性：安装项目内 ADB 后仍为空，同时 macOS USB 总线本身也没有设备。

### 2.2 最可能原因

1. 仪表设置里 USB 调试/ADB 模式未开启；当前端口可能处于 host、充电或关闭状态。
2. Type-C 线只有供电，或插入的仪表端口不是 USB device/OTG 端口。
3. 仪表没有完整上电；Mac 与仪表仅建立了供电关系。
4. 仪表 USB gadget 未绑定 UDC。

固件中的 `setusbconfig` 明确支持：

- ADB：VID/PID `18d1:d002`
- MTP：`1f3a:1006`
- Mass Storage：`1f3a:1000`
- MTP+ADB：`1f3a:1007`
- Mass Storage+ADB：`1f3a:1002`
- disabled/none：`1f3a:1001`
- gadget manufacturer/product：`Allwinner` / `Tina`

因此设备一旦正确进入 ADB 模式，macOS 应至少出现 USB 枚举，ADB 才有机会连接。

## 3. 输入固件与完整性

### 3.1 原始压缩包

| 包 | 大小 | SHA-256 |
|---|---:|---|
| `0908English.rar` | 20,935,579 | `0c1abda1280dfff7a5e4409aeecdab5ce8d1258292b7c72c7f6c3eb36943c8c2` |
| `TSL_中文.zip` | 20,907,405 | `4bff486f01982bcd79c8f6080aad6c6b67fb7d91e57c3d7412d65273bec36472` |

两个包都只含：

- `update.img`
- 空文件 `zkautoupgrade`
- 内容为 `100` 的 `zkrebootdelay`

`zkautoupgrade` 会触发自动升级，不能用于首轮上机测试。

### 3.2 `update.img` 格式

两镜像都以 `ZKSWEV1.0-1801270` 开头。格式不是普通裸 SquashFS：

```text
0x000..0x01f  ZKSWE 外层头
0x020..0x033  SquashFS 超级块前 20 字节
0x034..0x24f  540 字节厂商元数据
0x250..EOF    SquashFS 超级块剩余部分和文件系统数据
```

重建后两者均严格识别为：

- SquashFS 4.0
- little-endian
- XZ compression
- block size 131072
- English：1585 inodes，创建时间 2025-09-08 08:11:19 UTC
- Chinese：1568 inodes，创建时间 2024-12-20 09:01:25 UTC

厂商超级块中的 fragment count 写为 524，但实际只存在一个完整 512-entry fragment metadata block。分析副本把该字段规范化为 512 后，`unsquashfs` 无错误完整提取。原始 `update.img` 未修改。

可复现工具：

- `tools/unpack_zkswe.py`
- `tools/compare_firmware.py`

## 4. OTA 应用文件系统

### 4.1 目录

| 目录 | English | Chinese | 内容 |
|---|---:|---:|---|
| `bin` | 21 | 21 | Wi-Fi/P2P、USB、音频、投屏辅助程序 |
| `etc` | 1 | 1 | `EasyUI.cfg` |
| `lib` | 52 | 52 | `libzkgui.so` 和应用随包库 |
| `tr` | 11 | 10 | 多语言 JSON |
| `ui` | 1480 | 1464 | FTU、字体、图片资源 |

这个 OTA 没有 kernel、bootloader、device tree、完整 `/etc`、分区表或完整 rootfs。不能用它推断整机所有 driver/base library；这些必须从实机读取。

### 4.2 启动配置

`etc/EasyUI.cfg` 关键项：

```json
{
  "baud": "115200",
  "rotateScreen": 270,
  "startupLibPath": "/res/lib/libzkgui.so",
  "touchDev": "/dev/input/event1",
  "uart": "ttyS1",
  "resPath": "/res/ui/"
}
```

`ttyS1/115200` 是 EasyUI 配置 UART，不是车辆 MCU UART。`libzkgui.so` 自己另外打开 `/dev/ttyS0` 和 `/dev/ttyS5`。

### 4.3 平台/ABI

| 项目 | 结论 | 证据状态 |
|---|---|---|
| SoC family | Allwinner T113/T113-Sx | CONFIRMED |
| OS/libc | Linux + musl | CONFIRMED |
| CPU ABI | ARM 32-bit LSB EABI5 hard-float | CONFIRMED |
| GUI | FlyThings/EasyUI | CONFIRMED |
| 逻辑 UI | 1920×480，screen rotation 270 | CONFIRMED |
| 主库 | `/res/lib/libzkgui.so` | CONFIRMED |

证据包括 `/lib/ld-musl-armhf.so.1`、`sunxi` 音频/USB 字符串、T113 sysfs 地址和官方 T113 musl GCC 6.4.1 工具链。

OTA 缺少但主程序依赖的 base libraries：

- `libeasyui.so`
- `liblog.so`
- `libzkhardware.so`
- `libzknet.so`
- `libstdc++.so.6`
- `libgcc_s.so.1`
- `libc.so`

已从 FlyThings 官方依赖仓库取得前四项的 T113 SDK 版本用于构建；实机实际版本仍需 ADB 核对。

## 5. 英文版与中文版差异

文件级结果：

- English：1565 files
- Chinese：1548 files
- shared：1545
- byte-identical：792
- changed：753
- English-only：20
- Chinese-only：3

753 个 changed 中有 741 个位于 `ui`，说明多数差异是资源/FTU。代码层只有 `lib/libzkgui.so` 不同。

主要差异：

- English `libzkgui.so`：1,333,496 bytes
- Chinese `libzkgui.so`：1,206,512 bytes
- Chinese-only：`ui/wifisetting.ftu`、`ui/font1.ttf`、一个 AP 夜间档位图片
- English-only：俄语翻译、camera 图标、AP/light/massage/time navbar 图标及若干 UI 修正资源
- Chinese 主库包含 `wifisettingActivity`；English 不包含该 Activity
- English 包具有更完整的 camera UI；Chinese `camera.ftu` 仅 275 bytes
- `EasyUI.cfg` 仅 brightness 默认值和字体名不同

当前没有证据证明中文版拥有额外车辆 UART command。两个版本都保留同一协议框架；更深的函数级 binary diff 属于后续 ProtocolTable 扩展工作。

机器可读完整对比：`artifacts/firmware/comparison.json`。

## 6. UART 与 MCU 数据链

### 6.1 端口

原程序 `UartContext::init()` 明确打开：

- `/dev/ttyS0`：9600 baud
- `/dev/ttyS5`：38400 baud

`parseProtocol()` 只处理 port id `5`，因此车辆 MCU 数据口是 `/dev/ttyS5`。

### 6.2 帧格式

```text
0x2E | CMD | LEN | PAYLOAD[LEN] | CHECKSUM
```

精确校验算法已从 `calculate_crc16` 汇编确认（函数名误导，结果实际为 8 bit）：

```text
sum = CMD + LEN + each payload byte
checksum = (~sum) & 0xFF
```

原解析器：

- 接受任意分包/粘包并搜索 `0x2E` 重新同步
- 校验失败丢弃当前帧并记录日志
- UART read buffer 最大约 16 KiB
- 回调得到 command、完整 raw frame 和长度

## 7. Camera / USB / Network 调查（不作为阻塞项）

Camera 证据：

- 默认 `/dev/video0`，另有 `/dev/video4`
- `ZKCameraView` 支持 dev path、channel、format size、frame rate、rotation
- Allwinner TVD sysfs：`5c01000.tvd0/tvd0_attr/tvd_back_det`
- UI 设置包含 `ahd_select`、`AHD-AUTO`、`AHD-HAND`

推断：原相机更像接入 Allwinner TV decoder 的 AHD/CVBS 方案，而不是纯 USB UVC。需要实机 `/dev/video*`、driver、media topology 和线路测试才能最终确认。状态：LIKELY / FUTURE INVESTIGATION。

Network/Bluetooth 证据：

- `hostapd`、`p2p_supplicant`、`dnsmasq`、`mdnsd`
- `libusb`、CarPlay、AirPlay、HiCar、LyLink 相关库
- Bluetooth 辅助程序使用 `/dev/ttyS3`
- USB gadget 支持 ADB、MTP、Mass Storage 组合

## 8. Phase 0 未完成项

以下项目因实机未枚举而不能确认：

- CPU exact model/revision、RAM、kernel version
- flash type、MTD/eMMC partition table
- mounted filesystem 与 writable partition
- running services/processes 和实际启动顺序
- 实机 base library 精确版本
- `/dev/tty*`、`/dev/video*`、`/dev/input*` 实际节点
- Wi-Fi/Bluetooth chipset/driver
- boot/rootfs/res 分区备份
- MCU firmware 是否存在及其位置

下一次连接后首先运行 `scripts/probe_device_readonly.sh`，随后运行 `scripts/backup_device_readonly.sh DEVICE_SERIAL`。在这两步完成前不做持久化部署。
