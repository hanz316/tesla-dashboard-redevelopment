# BACKUP INVENTORY

更新：2026-08-31（America/Toronto）

设备：`Zkswe_T113_SPINOR`（10.80.6.196 / 10.0.0.216，Wi-Fi ADB）

状态分类：

- `PRESENT_IN_GITHUB`：已随仓库或 GitHub Release 上传
- `LOCAL_ONLY`：仅存在于 Mac 本地
- `MISSING`：丢失
- `NEEDS_RECAPTURE`：需要重新从实机采集

## 1. SPI NOR 原始分区备份（raw MTD）

来源：`captures/raw-mtd-10.80.6.196:5555-20260831T064438Z/`

状态：`PRESENT_IN_GITHUB`（Release 归档）+ `LOCAL_ONLY`（原始目录）

六个分区均按 `/proc/mtd` 尺寸校验，完整 SHA-256 见该目录 `SHA256SUMS`：

| 分区 | 大小 | SHA-256（前缀） |
|---|---|---|
| mtd0 uboot | 384 KiB | `095639f0...` |
| mtd1 boot | 6 MiB | `28b8a8e0...` |
| mtd2 res | 21.375 MiB | `3ea1c02d...` |
| mtd3 config | 3 MiB | `bc1a75fe...` |
| mtd4 boot_logo | 256 KiB | `7c81d2d2...` |
| mtd5 data | 1 MiB | `7fac0bb3...` |

## 2. 实机系统目录备份

来源：`captures/system-files-20260831T065200Z/`（bin/sbin/lib/late/data/system）
与 `captures/backup-10.80.6.196:5555-20260831T062456Z/`（live `/res` 41 MB + `/etc`）

状态：`PRESENT_IN_GITHUB`（Release 归档）+ `LOCAL_ONLY`（原始目录）

## 3. 运行时/验证证据

来源：

- `captures/runtime-build0.1-validated-20260831T182800Z/`（fds/maps/process/logcat/fb0.raw/framebuffer PNG/SHA256SUMS）
- `captures/device-20260831T062423Z/`（只读 probe 22 项）
- `captures/framebuffer-20260831T070000Z/`
- `captures/live-vs-english.json`

状态：`PRESENT_IN_GITHUB`（Release 归档）；精简文本版本已在仓库
`releases/dashboard-build-0.1-hardware-validated/`。

## 4. GitHub Release 归档

Release：`device-backup-2026-08-31`

归档：`device-backup-2026-08-31.tar.gz`（62 MB）

SHA-256：

```text
8886b2045b329d78ee9096c5265cab97647f3ec3c2e73316dda4c1eef9823363
```

包含：raw-mtd 六分区、system-files、live /res+/etc backup、Build 0.1
validated runtime 证据、device probe、framebuffer 原始帧、live-vs-english 对比。

## 5. 工具链/SDK（非备份，状态记录）

| 项 | 位置 | 状态 |
|---|---|---|
| T113 musl 交叉工具链（GCC 6.4.1） | `toolchains/`（854 MB） | `LOCAL_ONLY`，可重新下载 |
| FlyThings IDE / platform-tools | `toolchains/` | `LOCAL_ONLY` |
| FlyThings T113 SDK packages | `sdk/t113/packages` | `LOCAL_ONLY` |
| Docker 构建镜像 `tesla-dashboard-t113-builder` | 本机 docker | `LOCAL_ONLY`（可重建） |

## 6. 缺失项

无。所有已记录备份均存在；若本机丢失，可从 Release 归档恢复或重新采集。
