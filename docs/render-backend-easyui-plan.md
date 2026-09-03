# IRenderBackendV6 → EasyUI 2.2 后端实现方案

更新：2026-09-03（V6-H1 实机交接）

目标：在不重写 Horizon 状态/动画/布局逻辑的前提下，把
`RenderFrameV6`（`include/dashboard/render_model_v6.h`）渲染到 T113
EasyUI 2.2。本文基于 SDK 头文件确认的真实 API，不编造接口。

## 1. 已确认的 EasyUI 2.2 API（SDK 头文件证据）

| 能力 | API | 来源 |
|---|---|---|
| 控件位置 | `setPosition(const LayoutPosition&)` | `control/ZKBase.h` |
| 可见性 | `setVisible(bool)` | `control/ZKBase.h` |
| 背景图 | `setBackgroundPic(const char*)` | `control/ZKBase.h` |
| 背景色 | `setBackgroundColor(uint32_t ARGB)` | `control/ZKBase.h` |
| 透明度 | `setAlpha(uint8_t)` | `control/ZKBase.h` |
| 层序 | `setLayerIndex(int)` | `control/ZKBase.h` |
| 文本 | `setText(...)` / `setTextColor(int ARGB)` / `setTextSize(uint32)` | `control/ZKTextView.h` |
| 画线/矩形/三角形 | `ZKPainter::drawLines/fillRect/fillTriangle` | `control/ZKPainter.h` |
| 控件查找 | `BaseApp::findControlByID(int)` / `ZKWindow::findControlByID` | `app/BaseApp.h` |

**未提供**：控件旋转/缩放 API；通用裁剪（ClipPush/Pop）；运行时向
窗口添加控件的公开 API（控件由 FTU 定义）。

**结论**：V6 后端必须建立在"FTU 预置控件池"之上，按 ID 查找控件并
逐帧更新位置/文本/图片/颜色/可见性。Horizon 当前只发
Image/Text/SolidRect/Line + opacity（`src/core/horizon_v6.cpp`），
**没有 rotation/scale**，因此 EasyUI 能力足够。

## 2. RenderCommand → EasyUI 映射

| RenderCommand | EasyUI 实现 |
|---|---|
| `Image` | 预置 `ZKBase`（图片槽控件）→ `setVisible` + `setBackgroundPic(asset_path)` + `setPosition` + `setAlpha` |
| `Text` | 预置 `ZKTextView` → `setText` + `setTextColor` + `setTextSize` + `setPosition` + `setVisible` |
| `SolidRect` | 预置 `ZKTextView/ZKBase` 纯色槽 → `setBackgroundColor`；或 ZKPainter `fillRect` |
| `Line` | ZKPainter `drawLines`（若 FTU 含 painter）|
| `GradientRect` | EasyUI 无原生渐变；当前 Horizon 不发此命令。若未来需要：后端切成带 Alpha 的色带或预处理渐变 PNG |
| `ClipPush/Pop` | EasyUI 无原生裁剪；后端按矩形近似（控件本身就是矩形），记录为 unsupported 统计 |
| `transform.rotation/scale` | 不支持 → `stats.unsupported_commands++`（Horizon 当前不产生）|
| `transform.opacity` | `setAlpha(uint8(opacity*255))` |

## 3. 需要的 FTU 控件池（规格，供 FlyThings IDE 制作）

一个 `v6_horizon.ftu`（1920×480，控件不可触摸）：

| 组 | 控件数 | 类型 | 用途 |
|---|---:|---|---|
| 背景 | 1 | ZKTextView/窗口 | 纯色或环境渐变底 |
| Road layer | 6 | ZKBase 图片槽 | 路面/深度带 |
| Lane 组 | 8 | ZKBase 图片槽 | 车道线（按可见性开关）|
| AP corridor | 4 | ZKBase | AP 通道 |
| Blind zone L/R | 2 | ZKBase | 盲区 |
| Surrounding 槽 | 8 | ZKBase | 粗周边车辆占位 |
| Vehicle layers | 6 | ZKBase | 车身分层 PNG（按资产目录懒加载）|
| Primary data | 6 | ZKTextView | 速度/档位/SOC/续航/警告等 |
| Context Rail | 2 | ZKTextView | 上下文条 |
| Turn/safety | 4 | ZKTextView/ZKBase | 转向/安全覆盖 |
| Painter（可选） | 1 | ZKPainter | 线/矩形 fallback |

共约 48 个控件。所有控件 ID 在 `render_backend_easyui_ids.h` 常量中，
后端按 ID 查找，避免魔法数。

## 4. 资产与 RAM 策略

- 资产目录：`v6_asset_catalog.cpp` 已定义 ID 与估算内存
- 懒加载：只解码"共享 + 当前页 + safety"资产；离屏页资产释放
- 不预解码全部目录（避免 RAM 风险）
- `RenderBackendStats.missing_assets` 统计缺失，missing 时不伪造画面

## 5. Motion OFF / LOW / FULL

- OFF：静态层渲染，跳过动画/道路滚动
- LOW：30fps 上限，只更新必要层
- FULL：30fps 目标（T113 不追 60）
- 后端记录 `frame_time_us`、`commands_submitted`，供实机统计

## 6. 实施顺序

1. 用 FlyThings IDE 按上面规格制作 `v6_horizon.ftu`（可编辑源进入仓库）
2. 实现 `EasyUIRenderBackendV6`（编译进 `BUILD_FLYTHINGS_DEVICE`）
3. `main_activity` 的 timer 里：V6 Cockpit → RenderFrameV6 →
   `RenderPresenterV6(EasyUIBackend)` 呈现
4. /tmp 部署 → framebuffer 截图 → Motion OFF/LOW/FULL 的
   FPS/CPU/RSS/资产 RAM 实测 → 回写本文件与 `hardware-validation.md`

## 7. 当前阻塞

- 可编辑 V6 FTU 源（平台缺口，需 FlyThings IDE 制作）
- 实机在线（车通电 + 同网）后才能实测
