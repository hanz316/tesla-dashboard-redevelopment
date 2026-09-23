# Horizon V2 — UI SPEC

状态：**第一版已实现并出图，等待人工视觉验收。**

```text
HORIZON_V2_VISUAL = AWAITING HUMAN VISUAL APPROVAL
```

本轮只做 Horizon。Mono / Pulse / Route / Studio / Energy / Nocturne 保持现状；
UART、指挥官协议、Model A 几何、尾灯几何、仲裁策略一律未改。

---

## 1. 为什么是"设计即数据"

实现方没有视觉能力，不能靠"看起来不错"验收。所以这套 UI 的所有决定都写在
两个机器可读文件里，代码从它们生成，测试再读回来核对。

| 文件 | 内容 |
|---|---|
| [`assets/ui/horizon_v2_layout.json`](../assets/ui/horizon_v2_layout.json) | 画布、面板遮罩、安全区、三大区域、每个组件的 bounds/z-order/token 引用/可见性规则/数据绑定/未知态行为 |
| [`assets/ui/design_tokens.json`](../assets/ui/design_tokens.json) | 颜色、字体层级、间距、圆角、透明度、动画时长、Model A 实测包围盒 |

生成的场景：[`scenes/horizon_v2.scene`](../scenes/horizon_v2.scene)
（32 个节点 = 21 文本 + 10 矢量 + 1 车辆）。

流程是单向的：

```text
layout.json + design_tokens.json
        |  tools/preview/build_horizon_v2.py   (越界/踩遮罩/超安全区直接拒绝生成)
        v
scenes/horizon_v2.scene
        |  tools/preview/scene_preview.py      (Mac 预览 + 截图, 与设备同一份规则)
        v
assets/checkpoints/horizon_v2/*.png
        |  tools/preview/horizon_v2_layout_qa.py + tests/horizon_v2_tests.py
        v
布局/重叠/未知态/调试文本/状态落点 全部自动判定
```

**禁止**文档一套坐标、代码另一套坐标：测试会重新生成场景并逐字节比对。

---

## 2. 画布与物理约束

| 项 | 值 |
|---|---|
| 逻辑画布 | 1920 × 480，坐标 x 0..1919 / y 0..479 |
| 安全区 | 左右 48、上 22、下 24 |
| 面板梯形遮罩 | 上角切 116 px、下角切 51 px（实机标定），`cut(y) = 116 - 65*y/480` |
| 三大区域 | 驾驶员 x 60..430；车辆 x 430..1490；能量 x 1490..1860（只是布局约束，不画框） |

面板遮罩是硬约束：`x >= cut(y)`、`x + w <= 1920 - cut(y)`。
生成器和 QA 都按组件上下边分别计算，因此"看着居中、上机被切"不会发生。

### 2.1 与提示词的偏差（两处，均可复核）

| id | 提示词 | 实际 | 原因 |
|---|---|---|---|
| `speed_x` | 速度 x = 90 | **120** | 遮罩在速度框上沿（y = 105）已到 x ≈ 101.8，x = 90 会让首位数字被切；120 留 18 px 余量 |
| `time_anchor` | 时间 x = 1640 | **右对齐至 1806** | 读作"能量列里的时钟"：与 range/SOC 同一右边界，而不是浮在屏幕中段 |

其余坐标（温度 500/35、导航 pill 中心 960/y18/w620/h62、车辆视觉中心
960/295、range y115、SOC bar 180×12）与提示词一致。

导航 pill 的 y=18 在安全区上边（22）之上 4 px —— 提示词自己如此规定，
已在 layout 里标为 `exempt_from_safe_area`（其内容从 y=48 开始，在安全区内）。

---

## 3. 组件与层级

### 3.1 顶部

| 组件 | 位置 | 绑定 | 未知态 |
|---|---|---|---|
| 温度 | 左 500，垂直中心 74 | `temperature_primary` | `—°C` |
| 时钟 | 右对齐 1806 | 系统时钟 `%H:%M` | 不适用 |
| 导航 pill | 中心 960 / y18 / 620×62 / r10 | `nav_manoeuvre` 有效才出现 | **整块隐藏**（不画空矩形） |
| pill 内容 | 图标 + 距离 + 指路文字 | `nav_icon` / `nav_distance` / `nav_instruction` | 跟随 pill |

### 3.2 驾驶区（左）

| 组件 | 位置 | 字号 | 绑定 | 未知态 |
|---|---|---|---|---|
| 速度 | x120，垂直中心 175 | DISPLAY 120 | `speed` | `—` |
| 单位 | x124，垂直中心 263 | CAPTION 22 | 静态 `km/h` | 不适用 |
| 限速牌 | 386..440 / y118..172 | CAPTION 22 | `speed_limit` | **完全隐藏**（不虚构限速） |
| 档位 | x120/164/208/252，垂直中心 309 | BODY 28 | `gear` | 四个字母隐藏，只画 `—` |
| 驾驶员状态 | x120，垂直中心 359 | CAPTION 22 | `driver_status_text` | 空 |

档位：非当前档 0.28 透明度，当前档 `active_gear` 高亮；未知时整行隐藏只留 `—`，
**绝不允许 UNKNOWN → P**。速度单位放在数字下方而不是右侧，否则三位数会顶到单位。

### 3.3 车辆区（中）

| 项 | 值 |
|---|---|
| 渲染框 | x666 y85 584×387（asset 的 356×236 等比放大 1.64） |
| 可见车辆（关闭态） | x750..1170，y178..411（宽 420，中心 960/295） |
| 全部打开时的并集 | x748..1169，y119..412 |
| 允许区域 | x560..1360，y100..456 |

车辆状态全部来自 `VehicleState → VehicleVisualController → asset layers`：
刹车灯、近光灯、示宽灯按 asset overlay；四个车门 / 前备箱 / 后备箱按 to_state
序列；左/右转向与双闪按循环序列（**双闪 = 左右同时**，没有第四盏灯；后备箱内灯
按 `vehicle_state_moving_lighting.json` 的 TRUNK_MOVING 变体随盖板走）。
Horizon 自己不解释 UART / 指挥官数据。

道路：静态层，一条地平线 + 一个梯形路面 + 两条车道线 + 一层很淡的冷色渐变。
无粒子、无实时模糊、无 WebGL、无 3D 路面网格。

转向反馈：车辆对应灯亮；左右两侧各有一个 `◀` / `▶` 次级提示（CAPTION 22，
`indicator` 绿），只在对应侧亮时出现，不做大箭头。

### 3.4 能量区（右）

| 组件 | 位置 | 字号 | 绑定 | 未知态 |
|---|---|---|---|---|
| 续航 | 右对齐 1806，垂直中心 175 | TITLE 62 | `range` | `— km` |
| RANGE 标签 | 右对齐 1806，垂直中心 230 | CAPTION 22，0.55 透明 | 静态 | 不适用 |
| SOC 条 | 1626..1806，y268..280 | 高 12 / r6 | `actual_soc` | **整条隐藏** |
| SOC 百分比 | 右对齐 1806，垂直中心 312 | BODY 28 | `actual_soc` | `— %` |
| 功耗 | 右对齐 1806，垂直中心 368 | CAPTION 22 | `battery_power` | `— kW` |

SOC 颜色：正常低饱和青 `soc_normal`，≤20 % 转 `soc_low`（琥珀），≤10 % 转
`soc_critical`（红）。规则写在 layout 的 `progress.color_when`，预览器与设备
后端读同一份。

SOC 来源：**指挥官 `actual_soc`**（当前仲裁策略）。指挥官无数据时保持未知，
不启用已被否决的 MCU SOC 字节。

### 3.5 警告

居中偏下（660..1260，垂直中心 435），CAPTION 22，琥珀色，只在 `warning_text`
有效时出现；无警告时不画。

---

## 4. 生产 Horizon 禁止出现

`layout.forbidden_in_production` 列出并逐项自动检查：`CMDR` / `NativeBle` /
`PhoneBridge` / `UART` / `FPS` / `RSS` / `frame time` / `packet` / `checksum` /
`protocol` / `mapping confidence` / `source:` / `quality` / `stale` / `valid` /
`priority` / `debug` / `DEV`。

这些属于 Developer 页（独立 overlay，默认 OFF）。当前 Horizon（v6）上的
`commander.state` / `commander.detail` / `uart.lost` 在 V2 里**全部移除**。

---

## 5. 未知态硬规则

```text
UNKNOWN != 0        UNKNOWN != OFF      UNKNOWN != CLOSED
range -> — km       SOC -> — %          gear -> 四个字母隐藏 + —
temperature -> —°C  speed -> —          speed limit -> 整块隐藏
battery_power -> — kW                   nav -> 整块隐藏
```

自动检查两遍：布局层（每个绑定节点在 unknown 状态必须落到 `invalid_text`，
且占位符里不含数字），像素层（unknown 截图与 neutral 截图必须在三列都不同，
证明是"画了占位符"而不是"整屏空白"）。

---

## 6. 性能约束

保持 asset-driven，不做运行时重效果：

| 层 | 每帧工作 |
|---|---|
| 静态 | 1 个全屏渐变 + 1 个径向氛围 + 1 个路面多边形 + 3 条线 + 导航 pill 底板 |
| 动态矢量 | SOC 条填充 1 个 |
| 动态位图 | 车辆（唯一每帧位图，门/盖序列由状态触发） |
| 动态文本 | 速度、档位、续航、SOC、功耗、温度、时钟、状态、警告、导航 |

每帧位图仅车辆一张；动画序列同一时刻不超过 1-2 个（符合
`docs/RENDERING_CAPABILITY_AUDIT.md` §11 的推导）。目标 T113 稳定 30 fps；
真机帧时 / RSS 仍属 **UNKNOWN UNTIL DEVICE TEST**，本轮未做 60 fps 优化。

---

## 7. 自动化验收（无视觉能力下的"眼睛"）

`tools/preview/horizon_v2_layout_qa.py` 与 `tests/horizon_v2_tests.py` 执行：

1. 组件不越出画布
2. 组件不越出安全区（除非 layout 显式豁免并写明理由）
3. 组件不踩面板梯形遮罩
4. 速度不与车辆（含全开态）重叠
5. 车辆不与续航 / SOC 条重叠，且不侵入左右两列
6. 导航 pill 不压温度 / 时钟
7. 文本墨迹框两两不相交（neutral / unknown / low SOC / navigation 四态各测一次）
8. Model A 完整可见（关闭态与全开并集都在允许区域内），并用 PNG 实测 alpha
   包围盒核对 golden 数字，防止资产漂移
9. 生产 Horizon 无调试文本
10. unknown 截图无假数据（文本层 + 像素层各一遍）

外加：场景可从 layout 重新生成且逐字节一致；12 张截图各 1920×480；
两次渲染逐字节相同（确定性）；每个车辆状态只改变车辆区域（区域外变化像素
必须为 0）。

---

## 8. 产物

| 文件 | 说明 |
|---|---|
| `assets/checkpoints/horizon_v2/horizon_v2_neutral.png` 等 12 张 | 1920×480 确定性截图 |
| `assets/checkpoints/horizon_v2/horizon_v2_contact_sheet.png` | 12 态总览（人工验收用） |
| `assets/ui/horizon_v2_layout.json` | 布局 golden source |
| `assets/ui/design_tokens.json` | token golden source |
| `scenes/horizon_v2.scene` | 生成产物（runtime 读的就是它） |

复现：

```bash
python3 tools/preview/build_horizon_v2.py
python3 tools/preview/horizon_v2_shots.py
python3 tools/preview/horizon_v2_layout_qa.py
python3 tests/horizon_v2_tests.py
```

---

## 9. 下一步

**停下等人工看图。** 验收通过后（用户明确说 OK / 通过 / 可以），才：

1. 把 V2 提升为生产 Horizon（让运行时指向 `horizon_v2.scene`），并把 `status`
   改为 `LOCKED`；
2. 把静态层烘焙进背景位图（设备 `IRenderBackendV6` 适配器），届时每帧只剩
   文本 + SOC 条填充 + 一张车辆位图；
3. 真机帧时 / RSS / 面板 gamma 实测。

```text
HORIZON_V2_VISUAL = AWAITING HUMAN VISUAL APPROVAL
```
