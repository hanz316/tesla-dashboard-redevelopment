# Scene System V1

状态：规范（V1）。实现参考：`tools/preview/scene_preview.py`（Mac 预览器，
已可运行）。设备端运行时按同一份 JSON 消费。

目标：用**极轻量的声明式场景描述**替代"每个页面几千行固定坐标 C++"。
不实现 QML、CSS、JavaScript 或任何脚本语言。

---

## 1. 文件与来源

| 文件 | 作用 |
|---|---|
| `scenes/horizon_v1.scene` | 场景定义（节点树 + 绑定）|
| `assets/manifest.json` | 资产 ID → 文件/序列（图片、序列、叠加层）|
| `tools/preview/scene_preview.py` | Mac 预览器（读取上面两者）|

Mac 预览器与仪表运行时读取**同一份** scene + manifest，避免两套 UI 漂移。

---

## 2. 顶层结构

```jsonc
{
  "scene": "horizon",
  "version": 1,
  "canvas": {
    "width": 1920, "height": 480,
    "safe_area": { "top_corner_cut": 116, "bottom_corner_cut": 51 }
  },
  "manifest": "assets/manifest.json",
  "nodes": [ /* 见下 */ ]
}
```

`safe_area` 是**实机标定**的梯形裁切（上角切 116px、下角切 51px，
见 `docs/RENDERING_CAPABILITY_AUDIT.md`）。预览器与运行时都据此裁切。

---

## 3. 节点类型

| type | 用途 | 关键字段 |
|---|---|---|
| `vector` | 背景/形状（渐变、圆角矩形、进度条）| `shape`, `fill`, `from`/`to`, `radius`, `progress` |
| `text` | 文本/数值 | `bind`, `format`, `font`, `align`, `color` |
| `image` | 静态图片 | `asset` |
| `image_anim` | 帧序列 | `sequence`, `bind` |
| `vehicle_visual` | 车辆合成体（base + 部件序列 + 叠加层 + 转向灯）| `asset`, `parts`, `overlays`, `indicators` |
| `group` | 分组（子节点坐标相对父节点）| `children` |

### 3.1 通用属性

`x` `y` `width` `height` `opacity` `visible` `z` `anchor{x,y}`

绘制顺序按 `z` 升序；`anchor` 决定文本的对齐参考点
（`0.5/0.5` = 以 `x,y` 为中心）。

---

## 4. 绑定（statements，而非脚本）

绑定只做**取值 + 简单判断 + 格式化**，没有表达式求值器。

### 4.1 取值

```jsonc
{ "bind": "speed" }              // VehicleState 信号
{ "bind": "soc.valid" }          // 有效性后缀
{ "bind": "soc.trusted" }        // 可信度后缀（用于已知不可信的 MCU SOC）
{ "source": "clock", "format": "%H:%M" }   // 本地时钟
{ "text": "km/h" }               // 静态文本
```

### 4.2 格式化与枚举映射

```jsonc
{ "bind": "range", "format": "{} km" }
{ "bind": "gear", "value_map": { "1": "P", "2": "R", "3": "N", "4": "D" } }
```

`value_map` 用于枚举/离散值，未命中显示 `--`。

### 4.3 条件（`when` 子句）

条件只支持四种形式，可 `any` / `all` 组合：

```jsonc
{ "signal": "door_fl", "equals": true }
{ "signal": "gear", "equals": 4 }
{ "signal": "speed", "valid": false }
{ "signal": "is_true" /* is_true / is_false */ }
```

### 4.4 三处使用条件

```jsonc
"text_when":  [ { "when": {...}, "text": "--%" } ]        // 覆盖显示文本
"color_when": [ { "when": {...}, "color": "#F5A623" } ]   // 覆盖颜色
"visible_when": { ... }                                    // 控制可见性
```

**实例（V6 语义要求）**：MCU 的 SOC 已知不可信，场景里必须写成

```jsonc
{ "id": "soc", "bind": "soc", "format": "{}%",
  "text_when": [ { "when": { "signal": "soc.trusted", "equals": false },
                   "text": "--%" } ] }
```

即：没有可信来源时不显示数值（而不是把 97% 当成真实电量展示）。

---

## 5. `vehicle_visual` 节点

车辆是**分层合成**，不是一个整图（禁止把概念图当背景）：

```jsonc
{
  "id": "vehicle", "type": "vehicle_visual",
  "x": 650, "y": 34, "width": 720, "height": 400, "z": 10,
  "asset": "vehicle.base",
  "parts": {
    "door_fl": { "sequence": "vehicle.door.fl", "bind": "door_fl" },
    "trunk":   { "sequence": "vehicle.trunk",   "bind": "trunk" }
  },
  "overlays": [
    { "id": "brake", "asset": "vehicle.brake", "bind": "brake", "z": 12 }
  ],
  "indicators": {
    "left": { "sequence": "vehicle.indicator.left", "bind": "indicator_left" }
  }
}
```

行为：

- `parts` 中 `mode: to_state` 的序列：信号为真时显示**末帧**（打开态），
  为假时不绘制（回到 base）
- `indicators` 中 `mode: loop` 的序列：信号为真时按 `fps` 循环播放
- `overlays`：静态叠加（刹车灯/大灯），信号为真时叠加绘制

---

## 6. 运行时契约

```
scenes/*.scene  ──►  SceneLoader  ──►  SceneModel（节点树 + 绑定）
                                          │
                     VehicleState ────────┤ 求值（值/颜色/可见性/帧号）
                                          ▼
                                    RenderFrameV6（已有）──► IRenderBackendV6
                                                                  │
                                              EasyUI / NanoVG 后端（设备）
                                              PIL 后端（Mac 预览）
```

运行时只读 `VehicleState`；场景与动画**禁止**直接访问 UART/BLE。

---

## 7. 明确不做的事

- 不实现 QML / CSS / JavaScript
- 不实现通用表达式求值器（条件只有上面四种）
- 不让场景持有业务逻辑；业务在 VehicleState 与仲裁层
