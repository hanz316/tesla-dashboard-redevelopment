# Horizon 完整视觉重设计（A / B / C 三方向）

状态：**三个候选方向已实现并出图，等待人工视觉选择**。
本轮**没有**改动 runtime、UART、VehicleState、Commander、PhoneBridge。

基线 commit：`a5073d6`。

> 本文件里的三套设计**不是**"同一布局换颜色"。它们在 speed composition、
> vehicle placement、energy composition、spatial hierarchy 上都是不同结构。
> 但三套读的是**同一个** VehicleState，用同一份 mock state。

---

## 1. 全屏构图前提

| 项目 | 值 |
|---|---|
| 画布 | 1920×480 |
| 安全区 | 梯形，上角切 116 px、下角切 51 px（实机标定） |
| 车辆 | V3 Cycles 渲染，`assets/rendered/horizon_redesign/vehicle_pair/` |
| 背景 | near-black spatial gradient，非纯黑 |
| 内容来源 | 只来自 VehicleState；mock 仅存在于 previewer |

### 1.1 正常状态必须安静

三套设计在正常行驶状态下**都没有**：

- `DRIVE`
- `ALL CLOSED`
- `UART OK`

"全部关闭"由**没有警告、没有开门高亮**自然表达。UART 状态属于 Developer
Mode；只有 `UART LOST` 会通过 warning 路径浮现。

### 1.2 上下文严重性

| 什么时候 | 出现什么 | 平时 |
|---|---|---|
| 门打开 | 极简状态行 | 不显示 |
| 前备箱/后备箱打开 | 同上 | 不显示 |
| UART LOST | 警告行（琥珀） | 不显示 |
| SOC 不可信 | 隐藏百分比，保留 range | — |

### 1.3 一个跨三套的硬规则

SOC 有三种**必须区分**的情况，不能塌缩成一种：

| 情况 | 处理 |
|---|---|
| trusted | 画百分比 |
| 存在但 known-untrusted | **整个隐藏**（不画 97%，也不画假值），只留 range |
| 不存在（UART LOST） | 走正常 invalid 路径，画一个暗色占位 |

实现在 previewer 的 `soc_percent_rules()` / `untrusted_only()`，
并已用像素统计逐状态验证（见 §6）。

---

## 2. A — OEM MINIMAL

**设计逻辑**：最克制。信息靠排版、间距和留白说话，车辆居中偏大。
这是最接近量产高端数字仪表逻辑的一版：两个信息区各自**只有一个读数**
和一个**极细的分隔线**，没有面板、没有卡片、没有边框。

- speed：大号 DIN 数字（右对齐）+ 极低权重 `KM/H` + 一条竖分隔线 + 单独的挡位字母。
  速度、单位、挡位共用一个基线与一条分隔线，形成一个组件而不是三行文字。
- energy：**一条细竖线**（`vbar`，4 px）+ 大号百分比 + range。
  不用 progress bar，用"剩余量从底部升起"的细竖线。
- top rail：temperature 左、clock 右，共用一条基线，下面一条几乎看不见的横线。
- 车辆：700×401，居中，下方一块极软的 ambient pool（没有可辨的椭圆边缘）。
- context：出现在**左侧信息列下方**（speed 分隔线之下）。这是 A 里唯一
  永远不被车辆覆盖的区域。

**结构**：21 nodes —— 9 vector / 11 text / 1 vehicle。

## 3. B — SPATIAL HMI

**设计逻辑**：车辆与 UI 处在**同一个空间场**里。核心是一个大半径浅弧
（r=1400，位于画面上方极远处），它同时是"车脚下的地线"和"能量读数"。
能量不是右栏的一个控件，而是空间里的一段弧。

- 空间：两条镜像 `hgradient` 在车下交汇形成地平带；一条 41 刻度的浅弧
  作为地面；soft ambient pool。
- speed：UltraLight 大数字。**一条短线把速度块与车连接起来**，让数字
  读起来是"挂在车上"而不是"在左栏里"。
- gear：**竖排 P / R / N / D 标尺**，只有当前挡位点亮，其余 25% 透明度。
- energy：SOC 点亮同一条地弧的一段（从右向左填），读数在弧的右端。
- top rail：**移到底部**（y=446），因为顶部整个空间归车辆。
- context：左上开阔处，配一条指向车辆的短线。

**结构**：27 nodes —— 12 vector / 14 text / 1 vehicle。

## 4. C — PERFORMANCE LUXURY

**设计逻辑**：仪表结构感。用精密刻度与对齐线建立"机械精度"，速度与能量
各自带一套刻度系统，但不做赛车仪表。

- top：一条横贯 **113 刻度**（每 8 格一长刻度）的精密导轨；温度和时间
  嵌在导轨两端，成为导轨的读数而不是漂浮的角落文字。
- speed：Condensed DIN 大数字 + **下方一条线性刻度尺**（39 刻度，
  按 speed/240 点亮）+ 挡位横排 P R N D，当前挡位下方一条短高亮线。
- energy：**纵向分段刻度柱**（25 格，每 4 格一长格，从底部点亮）
  + 一条细能量线 + 百分比 + range。
- 背景：一条横贯车后的宽光带（两条镜像 `hgradient`）。
- context：**右下**，能量读数集群的脚下，配一个竖向短刻度。

**结构**：30 nodes —— 15 vector / 14 text / 1 vehicle。

---

## 5. Runtime primitives 归属

### 5.1 三套各用了什么

| 设计 | vector 形状 | text | vehicle |
|---|---|---|---|
| A | vgradient ×1, radial ×2, line ×3, vbar ×1, roundrect ×2 | 11 | 1 |
| B | vgradient ×1, hgradient ×2, arc ×2, ticks ×1, radial ×1, line ×5 | 14 | 1 |
| C | vgradient ×1, hgradient ×2, radial ×1, tickrow ×2, vticks ×1, vbar ×1, line ×7 | 14 | 1 |

### 5.2 哪些是 EasyUI

| 元素 | EasyUI 侧 |
|---|---|
| 车辆静态图 | 图像控件 + `IRenderBackendV6` |
| 门开动画 | `ZKImageAnim` 流式播放 delta 序列（见 `DELTA_ANIMATION_PIPELINE.md`） |
| 文本（速度、挡位、SOC、range、时间、温度、context） | 文本控件（ZKTextView 或等价物） |
| 静态背景位图（可缓存） | 图像控件 |

### 5.3 哪些是 NanoVG / AGG

所有非文本几何都走 NanoVG 路径（AGG CPU 光栅），对应关系：

| scene 形状 | NanoVG |
|---|---|
| `vgradient` / `hgradient` | `nvgLinearGradient` + 全屏 rect |
| `radial` | `nvgRadialGradient`（previewer 用 48 圈近似） |
| `line` | `nvgMoveTo` / `nvgLineTo` / `nvgStroke` |
| `arc` | `nvgArc` + `nvgStroke`（能量扫描段是同一条路径的第二个弧） |
| `ticks` / `tickrow` / `vticks` | 生成的短线路径批量 stroke |
| `vbar` | `nvgRoundedRect` ×2（track + fill） |
| `polygon` | `nvgBeginPath` + `nvgFill` |
| `roundrect` | `nvgRoundedRect` |

**没有**使用：Qt、WebGL、OpenGL、blur shader、runtime 3D、particle engine。
所有"高级感"来自构图、排版、间距、光照与运动，不是 GPU 特效。

### 5.4 哪些是 Blender asset

只有车辆：

- `vehicle_pair/open/000.png`（关闭姿态）
- `vehicle_pair/open/001.png`（Door_FL 52° 打开）

两张是同一次渲染、同一相机、同一 framing，所以门在图上的位置与比例完全一致。
静态图与 delta 序列都来自这条管线。

---

## 6. 已验证的行为（像素级）

因为实现方无法"看"图，四个状态的行为都用像素统计验证过，而不是靠肉眼声明。

| 检查 | A | B | C |
|---|---|---|---|
| context 区域在 normal 状态下亮像素 | 61 | 0 | 0 |
| door_fl_open 时同区域亮像素 | 695 | 532 | 468 |
| uart_lost 时同区域亮像素 | 633 | 438 | 358 |
| normal → soc_untrusted 变化像素 | 4,694 | 3,974 | 3,542 |
| 变化是否只在能量区 | 是 | 是 | 是 |
| uart_lost 下速度/SOC 变暗为占位 | 是 | 是 | 是 |
| context 文字是否与车辆重叠 | 否 | 否 | 否 |

> context 在 A 的 normal 状态下有 61 个亮像素：那是速度数字底部与分隔线的
> 抗锯齿残留，不是状态文字（状态文字出现时会跳到 600+）。

**实现过程中修正的两个真实缺陷**（都是无法看图时容易漏掉的）：

1. 第一版把 context / warning 文字放在**车辆正上方居中**，而车辆层级更高，
   文字会被车顶压住。三套现在都改到车辆包围盒之外。
2. `MOCK_STATES.update()` 曾写在 `MOCK_STATES = {...}` **之前**，导致
   previewer 直接 `NameError`。已修。

---

## 7. 预计 runtime cost 差异

**全部为估算，真机数字仍然 UNKNOWN UNTIL DEVICE TEST。**

真正的开销排序不是"元素个数"，而是**填充面积**：

| 成本项 | A | B | C |
|---|---|---|---|
| 全屏/大面积渐变填充 | 1 全屏 + 2 中等 | 1 全屏 + 2 条带 | 1 全屏 + 2 条带 |
| 大半径弧 + 刻度 | 无 | 1 弧 + 41 刻度 | 2 刻度尺 + 113 + 39 + 25 刻度 |
| 细线 / 圆角矩形 | 5 | 5 | 9 |
| 文本节点 | 11 | 14 | 14 |
| **相对成本** | **最低** | **中** | **最高** |

关键结论与优化：

1. **1 px 刻度几乎免费**（C 的 113 刻度是 113 条短线），C 比 A 贵的地方
   主要是它多出的刻度尺与能量柱路径，不是刻度数量本身。
2. 最贵的是**大面积渐变**。A/B/C 的背景梯度、地平带、光带与 ambient pool
   都是**静态**的：它们只在状态切换时变化，可以和车辆底图一起**烘焙成一张
   背景位图**，每帧只画文本与动态刻度。这样每帧 NanoVG 工作量可以降到
   个位数路径。
3. 车辆的门动画是唯一"每帧变"的位图，走 delta 管线（600px/60fps 估计占
   帧预算 18%）。
4. 三套都**不依赖**所有元素 60fps：轻量文本/刻度可以高刷，复杂车辆动画
   按真机 benchmark 选 30 或 60。设计在"车辆 30fps + UI 高刷"下依然成立。

---

## 8. 还需真机验证

- NanoVG 在 A7 上填满 1920×480 渐变与多段弧的**真实耗时**。
- 文本渲染走 EasyUI 控件还是 NanoVG，其每帧成本差异。
- 静态背景能否缓存成位图（若可以，成本几乎全部消失）。
- 30 / 60 fps 在真机上是否可达。
- 车辆 delta 序列与 scene 的真实接线（`IRenderBackendV6` 边界）。
- 面板实际 gamma / 亮度：本轮的亮度判断是在 Mac 上做的，
  梯形屏上的最终观感可能不同。
- AP / ADAS：本轮**没有**伪造周围车辆。没有精确 object data 时只允许
  abstract lane/corridor、盲区状态、方向性存在提示。

## 9. Mock state 说明

`tools/preview/scene_preview.py` 的 `MOCK_STATES` 新增：

```
normal_drive    speed 88, gear D, SOC 63 (trusted), range 253, 22°C
door_fl_open    speed 0, gear P, door_fl true, SOC 63 (trusted)
uart_lost       没有任何遥测（每个值都必须渲染成 unavailable）
soc_untrusted   speed 88, gear D, SOC 97 但 soc_trusted=false, range 253
```

**这些只存在于 Mac developer preview。** 生产路径禁止任何伪造数据。

## 10. 产物

| 文件 | 内容 |
|---|---|
| `horizon_redesign_comparison.png` | 12 格总览（行 = 状态，列 = A/B/C） |
| `<a|b|c>/horizon_redesign_<design>_normal_drive.png` | 正常行驶 |
| `..._door_fl_open.png` | 左前门打开 |
| `..._uart_lost.png` | 数据链丢失 |
| `..._soc_untrusted.png` | SOC 不可信 |

复现：

```bash
python3 tools/preview/build_redesign_scenes.py
V=$PWD/assets/rendered/horizon_redesign/vehicle_pair/open
for s in a b c; do python3 tools/preview/scene_preview.py \
  --scene scenes/horizon_redesign_$s.scene --all-states --vehicle-crop \
  --vehicle-image $V/000.png --vehicle-image-for door_fl_open=$V/001.png \
  --out assets/rendered/horizon_redesign/$s; done
```

`build_redesign_scenes.py` 生成 `scenes/horizon_redesign_{a,b,c}.scene`；
提交的是 **.scene 文件**（runtime 与 previewer 读的就是它）。
