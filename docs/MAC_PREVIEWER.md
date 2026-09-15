# Mac Previewer 架构

目的：**不接真机**也能预览 1920×480 的 Horizon 组合效果，并让 Mac 与仪表
共用同一套描述文件，避免两套 UI 漂移。

状态：架构 + **已落地最小实现**（`tools/preview/scene_preview.py`，可运行）。

---

## 1. 为什么可行

场景系统（`docs/SCENE_SYSTEM_V1.md`）是声明式的、平台无关的：

```
scenes/*.scene  +  assets/manifest.json  +  VehicleState(mock)
                        │
        ┌───────────────┴────────────────┐
        ▼                                ▼
Mac previewer (PIL, 本仓库)      设备 runtime (EasyUI + NanoVG)
```

两个后端消费**同一份** scene/manifest；差异只在绘制后端。

## 2. 已实现的最小版本

```bash
python3 tools/preview/scene_preview.py --list-states
python3 tools/preview/scene_preview.py --scene scenes/horizon_v1.scene --state driving
python3 tools/preview/scene_preview.py --all-states     # 输出全部场景到 assets/preview/
```

已支持：

- 读取 `*.scene` 与 `assets/manifest.json`
- **VehicleAssetProvider**：自动在 `RENDERED_MODEL3` 与 `PLACEHOLDER` 之间
  选择；`--require-model3` 可强制生产语义（无正式资产即**拒绝渲染**）
- 节点类型：`vector`（垂直渐变/径向辉光/圆角矩形+进度）、`text`、
  `image`、`image_anim`、`vehicle_visual`、`group`
- 绑定：`bind` / `valid` / `trusted` 后缀、`value_map`、`format`、
  `text_when` / `color_when` / `visible_when`
- 车辆分层合成：base + 门/箱序列 + 刹车/大灯叠加 + 转向灯循环
- 梯形安全区裁切（上 116 / 下 51）
- 内置 mock 状态：`parked` `driving` `door_open` `all_open` `stale` `lost`
- 动画相位 `--t 0..1`（用于查看循环序列的中间帧）

## 3. Mock 数据边界（重要）

- Mock **只存在于预览器**（`MOCK_STATES`）与 Developer Mode
- 生产运行时**禁止**自动显示假数据；信号无效时只能显示 `--`/不可用
- 生产 Horizon **禁止**使用占位车辆：`--require-model3` 会直接报错退出
- 使用占位车辆时预览图会绘制 `DEV PREVIEW` 横幅
- 预览器输出目录 `assets/preview/` 不提交（见 `.gitignore`）

## 4. 与设备端的关系

| 层 | Mac 预览器 | 设备运行时 |
|---|---|---|
| 场景解析 | Python（已实现）| C++（待实现，接口同 JSON）|
| 绑定求值 | Python（已实现）| C++（同规则）|
| 绘制 | PIL | EasyUI 控件 + NanoVG |
| 车辆合成 | `vehicle_visual` 合成（已实现）| `IRenderBackendV6` + `ZKImageAnim` |
| 文本 | PIL + 系统字体 | `ZKTextView`（FreeType）|

设备端实现路径：`SceneModel` → 求值 → `RenderFrameV6` → `IRenderBackendV6`
（边界已存在于 V6 代码）。

## 5. 后续增量（按性价比）

1. 交互窗口（SDL2）：滑动条切换 mock 状态、实时改场景参数
2. 场景热重载：保存 `*.scene` 立即重绘
3. 与真实录制联动：把 `captures/uart-record-*.bin` 回放进 VehicleState，
   预览真实行车数据下的表现（连接现有 Replay 能力）
4. 截图对比：同一场景分别用 Mac 与设备渲染，做像素差异报告

## 6. 已知限制

- PIL 不做抗锯齿路径裁剪，视觉细节与 NanoVG 不完全一致（仅用于布局/状态预览）
- 字体为 macOS 系统字体，设备用 `/res/ui/font.ttf`，字形宽度会有差异
- 未实现 `visible_when` 的父子继承与 group 变换
