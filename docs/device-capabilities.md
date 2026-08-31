# 实机能力矩阵

更新：2026-08-31（America/Toronto）

设备：`Zkswe_T113_SPINOR`（Wi-Fi ADB `10.0.0.216:5555`）

## 平台

| 项 | 值 | 状态 |
|---|---|---|
| SoC | Allwinner T113-Sx | CONFIRMED_ON_DEVICE |
| CPU | 双核 Cortex-A7 / ARMv7 / NEON / VFPv4 | CONFIRMED_ON_DEVICE |
| RAM | 249,964 KiB | CONFIRMED_ON_DEVICE |
| Flash | 32 MiB SPI NOR（6 分区） | CONFIRMED_ON_DEVICE |
| OS | ZKOS 2.6.2（Linux + musl） | CONFIRMED_ON_DEVICE |
| FlyThings | V2.1 | CONFIRMED_ON_DEVICE |
| EasyUI | 2.2.0 | CONFIRMED_ON_DEVICE |
| ABI | ARM 32-bit EABI5 hard-float | CONFIRMED_ON_DEVICE |
| 工具链 | T113 musl GCC 6.4.1（Docker 镜像） | CONFIRMED |

## 接口/外设

| 项 | 值 | 状态 |
|---|---|---|
| 车辆 UART | `/dev/ttyS5` 38400 8N1 只读 | CONFIRMED_ON_DEVICE |
| 配置 UART | `/dev/ttyS1` 115200（EasyUI cfg） | CONFIRMED_STATIC |
| BT UART | `/dev/ttyS3`（blink 栈） | CONFIRMED_ON_DEVICE |
| 相机节点 | `/dev/video0`、`/dev/video4` 存在 | CONFIRMED_ON_DEVICE |
| TVD | `5c01000.tvd0`，`tvd_back_det=0`（当前无信号，前摄损坏） | CONFIRMED_ON_DEVICE |
| 触摸 | `/dev/input/event1` | CONFIRMED_ON_DEVICE |
| 显示 | 1920×480 逻辑，fb0 480×3840 双页 32bpp，60 Hz | CONFIRMED_ON_DEVICE |
| 音频 | ALSA（`/res/ui/alsa`）、PCM 播放 | CONFIRMED_STATIC |
| Wi-Fi | wlan0，可 AP 可 STA | CONFIRMED_ON_DEVICE |
| 存储 | `/tmp` tmpfs、`/res` SquashFS RO、`/data` JFFS2 RW | CONFIRMED_ON_DEVICE |

## 蓝牙（BLE GATT Central 调查）

栈：`/res/bin/blink`（Realtek 系，`BLINK_8733/8761/8821`），
经 `/dev/BT_serial`（pty）与应用通信。

证据：

- 支持 A2DP sink、HFP、SPP、HID、PBAP、HiCar LE
- 含 LE 命令：`hci_le_create_connection`、`hci_le_connection_update`、
  `BLINK_SET_LE_ADV`、`HICAR_LE_ADV/PARA/REG_UUID`
- 含 GATT client 字符串：`GATT_SEARCH_START/STOP`、
  `GATT_CHARACTERISTIC_VALUE_QUERY_RESULT`、`GATT_NOTIFICATION/INDICATION`
- 配对列表含 BLE 外设（白色鼠标），说明设备以 Central 连接过 BLE 外设

结论：

```text
BLE_GATT_CENTRAL = LIKELY
```

理由：栈层具备 LE 连接 + GATT 客户端能力；剩余不确定项是应用侧
`BLINK_*` 命令是否开放任意 GATT service（如 FFF0/FFF1）的通用查询，
需一次受控 BLE 扫描/服务发现测试确认（只读，不涉及 Commander 控制）。

## 库/API 支持

| 库 | 来源 | 状态 |
|---|---|---|
| libeasyui.so / liblog.so / libzkhardware.so / libzknet.so | FlyThings SDK | CONFIRMED |
| libstdc++ / libgcc | 实机 | CONFIRMED（CXXABI_1.3.10 / GLIBCXX_3.4.22） |
| BlueZ | 无（vendor blink 栈） | NOT_SUPPORTED |
| hcitool/hciconfig | 无 | NOT_SUPPORTED |

## 已知限制

- 前摄损坏：`/dev/video0` 存在但 TVD 无信号
- 无 BlueZ：BLE 集成须走 blink 的 vendor API/协议
- `/tmp` 断电清空：临时部署默认路径
- 系统时钟为 epoch（1970），日志时间仅作相对参考
