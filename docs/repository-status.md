# Repository Completeness Report

更新：2026-08-31（America/Toronto）

目的：核对 GitHub 仓库与 Mac 本地项目的一致性，确认之前的关键工作
是否完整上传。GitHub 仓库：`https://github.com/hanz316/tesla-dashboard-redevelopment`

## 1. Git 状态

| 项 | 值 |
|---|---|
| 当前分支 | `build-0.2` |
| 最新 commit | `a11d76d` Build 0.2: wire data source health into device runtime and UI |
| `main` | `4fca3dc` Validate Build 0.1 on T113 hardware |
| 本地 vs GitHub | 完全同步（无未推送 commit、无未提交改动） |
| 其他线程新提交 | 无（fetch 后无新 commit） |

## 2. GitHub 已包含（72 个 tracked 文件）

### 代码

- CMake 构建：`CMakeLists.txt`、`cmake/t113-musl-toolchain.cmake`、`docker/t113-build.Dockerfile`
- 核心库 `dashboard_core`：
  - `include/dashboard/`：`data_source.h`、`original_mcu_adapter.h`、`protocol_parser.h`、`signal.h`、`source_adapters.h`、`vehicle_state.h`
  - `src/core/`：`original_mcu_adapter.cpp`、`protocol_parser.cpp`、`vehicle_state.cpp`
- T113 设备侧：`device/flythings/`（`device_runtime.*`、`main.cpp`、`main_activity.*`）
- 主机模拟器：`apps/simulator/main.cpp`
- 单元测试：`tests/dashboard_tests.cpp`

### 脚本与工具

- `scripts/`：probe / backup / backup_raw_mtd / build_t113 / deploy_temporary_adb / package_temporary_bundle
- `tools/`：`unpack_zkswe.py`、`compare_firmware.py`、`download_flythings_package.py`、`device_base64.cpp`
- `deploy/temporary-adb/EasyUI.cfg`

### 文档

- `README.md`
- `docs/`：`phase0-phase1-investigation.md`、`protocol-table.md`、`safe-deployment.md`、`mvp-status.md`、`hardware-validation-2026-08-31.md`、`repository-status.md`、`backup-inventory.md`

### 发布基线（releases/dashboard-build-0.1-hardware-validated/）

- `libzkgui.so`（SHA-256 见 `SHA256SUMS`）
- `main.ftu`（实机版本）
- `EasyUI.cfg`
- `framebuffer.png`
- `device-probe/`（22 个实机只读探针文件）
- `runtime-validation/`（fds/maps/process/logcat + SHA256SUMS）
- `flash-reference/`（proc-mtd + SHA256SUMS）

### 固件分析产物

- `artifacts/firmware/comparison.json`（英文/中文 OTA 全量对比）

## 3. Mac 本地有、GitHub 未包含（按设计排除）

以下内容按 `.gitignore` 排除，不在 git 历史中；其中备份类资产已上传
GitHub Release，见 `docs/backup-inventory.md`。

| 路径 | 大小 | 内容 | 处理 |
|---|---|---|---|
| `captures/` | 179 MB | 实机备份、截图、日志、runtime 验证 | Release `device-backup-2026-08-31` + 本地保留 |
| `toolchains/` | 854 MB | T113 musl 工具链、FlyThings IDE、platform-tools | 本地保留（可重新下载） |
| `sdk/` | 1.5 MB | FlyThings T113 SDK packages | 本地保留 |
| `build/` `build-t113/` | - | 构建产物 | 可再生 |
| `dist/` | 52 KB | 临时部署 bundle | 可再生 |
| `artifacts/firmware/*_appfs/` 等 | 239 MB | 解包后的固件文件系统 | 可重新解包 |

## 4. 结论

- 代码、文档、脚本、Build 0.1 发布基线：**完整在 GitHub**。
- 实机备份二进制（MTD 分区、/res、系统目录）：**本地完整，已上传 GitHub Release**。
- 工具链/SDK：**本地完整**，未上传（体积大且可重新获取）。
- 无丢失项；无需重新采集。
