# Build 0.1 实机验证报告

## 结果

Build 0.1 已在真实 T113 仪表运行。该结果关闭了以下技术风险：

- FlyThings T113 交叉编译链可用
- 自定义 `libzkgui.so` ABI 与实机兼容
- `/tmp/EasyUI.cfg` 临时启动路径可用
- stock `/res/ui/main.ftu` 可由新应用加载
- `/dev/ttyS5` 可以由新进程以只读方式打开
- framebuffer 可以无损读取并恢复为 1920×480 画面
- 断电会清空 `/tmp` 并恢复 stock 应用

## 实机系统

```text
Model: Zkswe_T113_SPINOR
Firmware: t113_zkswe_da
System: 2.6.2
FlyThings: V2.1
EasyUI: 2.2.0
CPU: 2 x Cortex-A7 / ARMv7 / NEON / VFPv4
RAM: 249964 KiB
```

## Flash 与挂载

| MTD | Size | Name | Runtime mount |
|---|---:|---|---|
| mtd0 | 384 KiB | uboot | - |
| mtd1 | 6 MiB | boot | boot image/rootfs |
| mtd2 | 21.375 MiB | res | `/res`, SquashFS RO |
| mtd3 | 3 MiB | config | `/late`, SquashFS RO |
| mtd4 | 256 KiB | boot_logo | - |
| mtd5 | 1 MiB | data | `/data`, JFFS2 RW |

六个分区已通过 ADB sync 的块设备只读读取，并按 `/proc/mtd` 尺寸验证，总计 32 MiB。`mtd0` 另通过临时 Base64 工具交叉读取，两个路径 SHA-256 完全相同。

## 应用运行证据

```text
Process: /bin/zkgui
Mapped app: /tmp/tesla-dashboard-mvp/lib/libzkgui.so
VmSize: 27240 kB
VmRSS: 3664 kB
Vehicle UART: /dev/ttyS5
UART FD mode: read-only
```

日志确认：

- `initEasyUICfg ok`
- `registerActivity name: mainActivity OK`
- FTU/controls 初始化完成
- 无 undefined symbol
- 无 crash/segfault
- 无 zkswe crash loop

## Framebuffer

- fb0 virtual size：480×3840
- bits per pixel：32
- stride：1920 bytes
- 双缓冲页：2 × 480×1920
- 逆旋转后：1920×480

基线截图：`releases/dashboard-build-0.1-hardware-validated/framebuffer.png`。

## 实机与英文 OTA 差异

- English OTA `/res`：1565 files
- Live `/res`：1567 files
- identical：827
- changed：738
- live-only：`ui/1.ttf`、`ui/navibar/mcu_update_bg.png`
- live `libzkgui.so` 与 English OTA 大小相同但哈希不同
- live `main.ftu` 为 3071 bytes，English OTA 为 3079 bytes
- Build 0.1 使用的 8 个 control ID 已针对 live `libzkgui.so` 重新核对，一致

## 回滚验证

仪表从手机热点切换到家庭网络的过程中发生了断电/重启。重连后：

- `/tmp/EasyUI.cfg` 不存在
- `/tmp/tesla-dashboard-mvp` 不存在
- stock `/bin/zkgui` 正常启动

这验证了临时部署不会改变持久化系统。
